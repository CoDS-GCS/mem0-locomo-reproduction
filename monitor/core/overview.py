"""P7: progress, counts, funnel and temporal lens (cached per data version)."""
import time
from collections import Counter, defaultdict

from . import analysis as AN
from .util import rel_words, evidence_ids

STEPS = ["Evidence turns", "Fact extracted", "Memory created", "Memory survived", "Retrieved in top 30", "Answered correctly"]
_cache = {}


def progress(exp, res):
    out = {"mode": exp.mode, "stage": exp.runner.get("stage"), "stage_detail": exp.runner.get("detail"), "convs": []}
    now = time.time()
    out["last_change"] = exp.last_change
    out["idle_min"] = round((now - exp.last_change) / 60, 1) if exp.last_change else None
    out["warn_idle"] = bool(out["idle_min"] is not None and out["idle_min"] > 20 and exp.runner.get("stage") not in ("finished", "stopped"))
    out["runner_tail"] = exp.runner.get("lines", [])[-12:]
    cnt = Counter()
    none_n = 0
    errors = 0
    skipped = 0
    for c in exp.ds.convs:
        row = {"c": c["idx"], "users": []}
        for u in c["users"]:
            bl = exp.B.get((c["idx"], u), [])
            st = Counter(b["status"] for b in bl)
            for b in bl:
                for e in (b["final"] or {}).get("memory_events") or []:
                    cnt[e.get("event")] += 1
                errors += sum(1 for e in b["events"] if e.get("error"))
                for gp in b["groups"][-1:]:
                    none_n += sum(1 for d in ((gp.get("update") or {}).get("decisions") or []) if d.get("event") == "NONE")
            skipped += st.get("skipped", 0)
            row["users"].append({"user": u, "total": len(bl), "ok": st.get("ok", 0), "status": dict(st)})
        al = exp.addlog.get(c["idx"], {})
        row["bar"], row["crashes"], row["skipped_lines"] = al.get("bar", {}), al.get("crashes", 0), al.get("skipped", [])[-3:]
        row["finished"] = exp.runner.get("conv_finished", {}).get(c["idx"])
        out["convs"].append(row)
    out["counts"] = {"ADD": cnt["ADD"], "UPDATE": cnt["UPDATE"], "DELETE": cnt["DELETE"], "NONE": none_n}
    out["errors"], out["skipped_batches"] = errors, skipped
    total_q = sum(len(c["qa"]) for c in exp.ds.convs)
    out["search"] = {"answered": res.n_answered, "total": total_q}
    out["judge_runs"] = len(res.eval)
    out["j"] = res.j_summary()
    out["has_addlogs"] = exp.has_addlogs
    return out


def compute(exp, res):
    key = (exp.version, res.version)
    hit = _cache.get("all")
    if hit and hit[0] == key:
        return hit[1]
    rows = []
    for c in exp.ds.convs:
        for q in c["qa"]:
            if q["category"] == 5 or not evidence_ids(q["evidence"]):
                continue
            A = AN.analyze(exp, res, c["idx"], q["qi"])
            rows.append({"c": c["idx"], "qi": q["qi"], "cat": q["category"], "level": A["level"], "reason": A["reason"], "correct": A.get("correct"),
                         "unknown": A["reason"] == "unknown" and A["level"] < 6, "despite": bool(A.get("answered_ok_despite_loss"))})
    # temporal lens over distinct evidence turns with relative words
    lens = defaultdict(list)
    seen = set()
    for c in exp.ds.convs:
        for q in c["qa"]:
            if q["category"] == 5:
                continue
            for dia in evidence_ids(q["evidence"]):
                loc = c["dia"].get(dia)
                if not loc or (c["idx"], dia) in seen:
                    continue
                seen.add((c["idx"], dia))
                turn = c["sessions"][loc[0]]["turns"][loc[1]]
                if not turn["rel"]:
                    continue
                for i, u in enumerate(c["users"]):
                    if not exp.has_addlogs:
                        continue
                    P = AN.trace_path(exp, c["idx"], u, i, dia, None)
                    if P.get("chosen") and P.get("datev_birth"):
                        lab = P["datev_birth"]["label"]
                        ex = {"c": c["idx"], "dia": dia, "user": u, "turn": turn["text"], "memory": P["chosen"]["versions"][P["chosen"]["birth_v"] - 1]["text"] if P["chosen"]["birth_v"] else "", "session": P["session_date"], "words": turn["rel"]}
                    elif P["loss"] in ("no_fact", "none_decision"):
                        lab, ex = "no_memory", {"c": c["idx"], "dia": dia, "user": u, "turn": turn["text"], "memory": "", "session": P.get("session_date"), "words": turn["rel"]}
                    else:
                        lab, ex = "pending", {"c": c["idx"], "dia": dia, "user": u, "turn": turn["text"], "memory": "", "session": P.get("session_date"), "words": turn["rel"]}
                    lens[lab].append(ex)
    val = {"rows": rows, "lens": {k: v for k, v in lens.items()}}
    _cache["all"] = (key, val)
    return val


def funnel(exp, res):
    data = compute(exp, res)
    out = {"steps": STEPS, "cats": {}}
    groups = {"all": data["rows"]}
    for cat in (1, 2, 3, 4):
        groups[str(cat)] = [r for r in data["rows"] if r["cat"] == cat]
    for name, rows in groups.items():
        reach = [sum(1 for r in rows if r["level"] >= k) for k in range(1, 7)]
        unk = [sum(1 for r in rows if r["level"] < k and r["unknown"] and r["level"] == k - 1) for k in range(1, 7)]
        out["cats"][name] = {"n": len(rows), "reach": reach, "unknown": unk, "despite": sum(1 for r in rows if r["despite"])}
    out["caveat"] = None if exp.has_addlogs else ("Without add-stage logs 'Retrieved in top 30' can only be estimated by text resemblance between the evidence turn and the retrieved memories "
                                                 "(>= 50% of the turn's content words). That is a WEAK signal: on the finished Kuzu run such a memory was found for 53% of the correctly answered and 41% of the wrongly answered questions.")
    out["na"] = [] if exp.has_addlogs else [1, 2, 3]       # 0-based step indexes that cannot exist without add-stage logs
    return out


def funnel_list(exp, res, cat, step, mode):
    data = compute(exp, res)
    rows = data["rows"] if cat == "all" else [r for r in data["rows"] if str(r["cat"]) == cat]
    if mode == "reach":
        sel = [r for r in rows if r["level"] >= step]
    elif mode == "unknown":
        sel = [r for r in rows if r["level"] == step - 1 and r["unknown"]]
    else:   # dropped at this step: passed the previous one, not this one
        sel = [r for r in rows if r["level"] == step - 1 and not r["unknown"]]
    out = []
    for r in sel[:400]:
        q = exp.conv(r["c"])["qa"][r["qi"]]
        out.append({"c": r["c"], "qi": r["qi"], "question": q["question"], "gold": q["answer"], "cat": r["cat"], "reason": AN.REASONS.get(r["reason"], r["reason"])})
    return {"n": len(sel), "items": out}


def lens(exp, res):
    d = compute(exp, res)["lens"]
    labels = ["kept_word", "dropped", "correct", "invented", "unverified", "no_memory", "pending"]
    return {"counts": {k: len(d.get(k, [])) for k in labels}, "examples": {k: d.get(k, [])[:25] for k in labels}, "available": exp.has_addlogs}
