"""Trace evidence turns through the pipeline and find the first lost link. All linking rules are described on the About page."""
import re
from collections import defaultdict

from .util import OVERLAP_MIN, overlap, date_verdict, evidence_ids, rel_words

TEXT_ONLY_MIN = 0.5   # no add-stage logs: only text resemblance is available, so be strict
LEVELS = ["evidence", "extracted", "created", "survived", "retrieved", "correct"]
TEMPORAL_Q = re.compile(r"^\s*(when|what (year|month|date|day|time))\b|\bhow long\b", re.I)

REASONS = {
    "no_fact": "no fact extracted",
    "none_decision": "no memory created (decision NONE)",
    "date_dropped": "date dropped",
    "date_invented": "date invented",
    "overwritten": "overwritten by a later UPDATE",
    "deleted": "deleted",
    "not_retrieved": "not retrieved (not in top 30)",
    "wrong": "retrieved but answered wrong",
    "correct": "correct",
    "unknown": "cannot be known yet",
}


def is_temporal(q):
    return q["category"] == 2 or bool(TEMPORAL_Q.search(q["question"]))


def batch_of(exp, c, user, dia):
    conv = exp.conv(c)
    loc = conv["dia"].get(dia)
    if not loc:
        return None, None, None
    si, pos = loc
    for b in exp.B.get((c, user), []):
        if b["si"] == si and pos in b["pos"]:
            return b, conv["sessions"][si]["turns"][pos], conv["sessions"][si]
    return None, None, None


def final_group(b):
    return b["groups"][-1] if b["groups"] else None


def trace_path(exp, c, user, uidx, dia, row):
    """One evidence turn x one store. Every stage is True / False / None (None = cannot be known)."""
    b, turn, sess = batch_of(exp, c, user, dia)
    P = {"user": user, "uidx": uidx, "dia": dia, "stages": {}, "loss": None, "facts": [], "cands": [], "chosen": None, "rank": None, "score": None}
    if b is None:
        P["loss"] = "unknown"
        P["note"] = f"turn {dia} not found in the dataset"
        return P
    P["batch"] = {"seq": b["seq"], "skey": b["skey"], "bi": b["bi"], "status": b["status"]}
    P["turn_text"] = turn["text"]
    P["session_date"] = sess["date"]
    st = P["stages"]
    mems = None
    if row is not None:
        mems = row["speaker_1_memories"] if uidx == 0 else row["speaker_2_memories"]
    if exp.has_addlogs:
        if b["status"] != "ok":
            # not added yet (or skipped): everything after the dataset is unknown
            st.update(extracted=None, created=None, survived=None, retrieved=None)
            P["loss"] = "unknown"
            P["note"] = f"batch status: {b['status']}"
            return P
        g = final_group(b)
        facts = (g or {}).get("extract", {}) and g["extract"].get("facts")
        if g is None or g.get("extract") is None or facts is None:
            st["extracted"] = None
            P["note"] = "no LLM log for this batch (extraction call missing)"
        else:
            P["facts"] = [(f, overlap(turn["text"], f)) for f in facts]
            ok = any(o is None or o >= OVERLAP_MIN for _, o in P["facts"]) if facts else False
            st["extracted"] = bool(ok)
        evs = (b["final"] or {}).get("memory_events") or []
        P["events"] = evs
        cands = []
        for ev in evs:
            if ev.get("event") in ("ADD", "UPDATE"):
                o = overlap(turn["text"], ev.get("memory") or "")
                cands.append({"id": ev["id"], "event": ev["event"], "text": ev.get("memory"), "overlap": o})
        good = [x for x in cands if x["overlap"] is None or x["overlap"] >= OVERLAP_MIN]
        P["cands"] = cands
        if st.get("extracted") is False:
            st.update(created=False, survived=False, retrieved=False)
            P["loss"] = "no_fact"
            return P
        if not good:
            st.update(created=False, survived=False, retrieved=False)
            P["loss"] = "none_decision"
            return P
        st["created"] = True
        best = max(good, key=lambda x: (x["overlap"] or 0))
        chain = exp.chains.get(user, {}).get(best["id"], [])
        birth = next((v for v in chain if v["seq"] == b["seq"]), chain[0] if chain else None)
        final = chain[-1] if chain else None
        P["chosen"] = {"id": best["id"], "versions": chain, "birth_v": birth["v"] if birth else None}
        dv0 = date_verdict(turn["text"], birth["text"], sess["date"]) if birth else None
        dvF = date_verdict(turn["text"], final["text"], sess["date"]) if final and final["event"] != "DELETE" else None
        P["datev_birth"], P["datev_final"] = dv0, dvF
        if final and final["event"] == "DELETE":
            st["survived"] = False
            P["loss"] = "deleted"
            st.update(retrieved=False)
            return P
        P["lost_v"] = None
        for v in chain:
            if birth and v["v"] > birth["v"]:
                o = overlap(turn["text"], v["text"] or "")
                dvv = date_verdict(turn["text"], v["text"] or "", sess["date"]) if v["event"] != "DELETE" else None
                if v["event"] == "DELETE" or (o is not None and o < OVERLAP_MIN) or (dv0 and dvv and dv0["label"] in ("correct", "kept_word") and dvv["label"] in ("dropped", "invented")):
                    P["lost_v"] = v["v"]
                    break
        lost_text = final is not None and final is not birth and (overlap(turn["text"], final["text"]) is not None and overlap(turn["text"], final["text"]) < OVERLAP_MIN)
        worse = bool(dv0 and dvF and dv0["label"] in ("correct", "kept_word") and dvF["label"] in ("dropped", "invented"))
        if lost_text or worse:
            st["survived"] = False
            P["loss"] = "overwritten"
            P["why"] = "later UPDATE removed the content" if lost_text else "later UPDATE lost or changed the date"
            st["retrieved"] = False
            if mems is not None and final:
                hit = next((i for i, m in enumerate(mems) if m[0] == final["text"]), None)
                if hit is not None:
                    P["final_rank"], P["final_score"] = hit + 1, mems[hit][2]
            return P
        st["survived"] = True
        final_text = final["text"] if final else best["text"]
        P["final_text"] = final_text
        if mems is not None:
            hit = next((i for i, m in enumerate(mems) if m[0] == final_text), None)
            st["retrieved"] = hit is not None
            if hit is not None:
                P["rank"], P["score"] = hit + 1, mems[hit][2]
            # evidence information may sit in another stored memory of the same speaker (text match as a hint)
            P["alt"] = _best_in_top(turn["text"], mems)
        else:
            st["retrieved"] = None
        return P
    # no add-stage logs (Kuzu run): text match between the evidence turn and the retrieved memories only
    if mems is None:
        st.update(extracted=None, created=None, survived=None, retrieved=None)
        return P
    alt = _best_in_top(turn["text"], mems)
    alt = alt if alt and alt["overlap"] >= TEXT_ONLY_MIN else None
    P["alt"], P["noadd"] = alt, True
    st.update(extracted=None, created=None, survived=None, retrieved=bool(alt))
    if alt:
        P["rank"], P["score"] = alt["rank"], alt["score"]
    return P


def _best_in_top(turn_text, mems):
    best = None
    for i, m in enumerate(mems):
        o = overlap(turn_text, m[0])
        if o is not None and (best is None or o > best["overlap"]):
            best = {"rank": i + 1, "overlap": o, "text": m[0], "score": m[2]}
    return best


def path_level(P):
    s = P["stages"]
    if P.get("noadd"):
        return 5 if s.get("retrieved") else 1
    lvl = 1  # the evidence turn exists
    for name in ("extracted", "created", "survived", "retrieved"):
        if s.get(name) is True:
            lvl += 1
        else:
            break
    return lvl


def analyze(exp, res, c, qi):
    conv = exp.conv(c)
    q = conv["qa"][qi]
    row = res.row(c, qi) if res else None
    verd, erow = res.verdicts(c, qi, conv["qa"]) if res else ({}, None)
    ev = evidence_ids(q["evidence"])
    A = {"c": c, "qi": qi, "q": q, "evidence": ev, "turns": [], "has_row": row is not None, "verdicts": verd,
         "n_runs": len(verd), "temporal": is_temporal(q)}
    if not ev:
        A.update(level=0, reason="unknown", detail="no evidence turn listed for this question")
        return A
    worst = None
    for dia in ev:
        paths = [trace_path(exp, c, u, i, dia, row) for i, u in enumerate(conv["users"])]
        best = max(paths, key=path_level)
        known = [p for p in paths if p["stages"].get("extracted") is not None or p["stages"].get("retrieved") is not None]
        A["turns"].append({"dia": dia, "paths": paths, "best": best["uidx"], "level": path_level(best)})
        if worst is None or path_level(best) < worst[0]:
            worst = (path_level(best), dia, best)
    lvl, dia, P = worst
    s = P["stages"]
    issues = []
    if P["loss"] in ("no_fact", "none_decision", "unknown"):
        issues.append(P["loss"])
    else:
        # chronological order of what can go wrong after the memory was created
        dv = P.get("datev_birth") if exp.has_addlogs else None
        if A["temporal"] and dv and dv["label"] in ("dropped", "invented"):
            issues.append("date_dropped" if dv["label"] == "dropped" else "date_invented")
        if P["loss"] in ("overwritten", "deleted"):
            issues.append(P["loss"])
        if s.get("retrieved") is False and P["loss"] is None:
            issues.append("not_retrieved")
    reason = issues[0] if issues else None
    A["issues"] = issues
    correct = None
    if verd:
        correct = sum(verd.values()) * 2 >= len(verd)     # majority of the judge runs
    A["correct"] = correct
    if reason is None:
        if s.get("retrieved") is None and not exp.has_addlogs and row is None:
            reason = "unknown"
        elif s.get("retrieved") is None:
            reason = "unknown"
        elif correct is None:
            reason = "unknown"
        else:
            reason = "correct" if correct else "wrong"
    rtext = REASONS[reason] if (reason != "not_retrieved" or exp.has_addlogs) else "no retrieved memory resembles the evidence turn (cannot tell never created from not retrieved: no add logs)"
    A.update(reason=reason, reason_text=rtext, loss_turn=dia, loss_user=P["user"], level=lvl + (1 if (lvl == 5 and correct) else 0))
    A["answered_ok_despite_loss"] = bool(correct) and reason not in ("correct", "unknown", "wrong")
    return A
