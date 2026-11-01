"""Exp 5 vs Exp 4 on ONE conversation: does putting the date in the message text change anything besides the dates?
Read-only (changes nothing). Run from the Exp 5 folder, venv active, after that conversation finished the add stage:
    python side_effects.py 0

Every place where Mem0 reads the message text, and what this script measures for it:
  1. fact extractor      -> facts per call; memories with a date; date close to / far from the memory's own session
                            date; "last week" turned into the session date; memories only about the OTHER speaker
  2. update step         -> ADD / UPDATE / DELETE / NONE decisions (from the LLM log, NONE included);
                            UPDATEs that changed or removed a date
  3. graph entities +    -> relations stored; date nodes; date nodes that are just the session date copied from
     graph relations        the brackets (like nate -participated_on-> 21_january,_2022); relative-word nodes
  4. graph delete step   -> relations deleted
  5. errors              -> failed add() calls, failed LLM calls
Sources: Qdrant (memories), Neo4j (graph), logs/events_<user>.jsonl and logs/llm_conv<N>.jsonl of both folders.
"""
import collections
import datetime as dt
import json
import os
import re
import sys

from dotenv import dotenv_values
from neo4j import GraphDatabase
from qdrant_client import QdrantClient, models

N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
E5 = os.getcwd()
E4 = os.path.expanduser("~/mem0-repro/paper-eval-neo4j-gemini")
env5 = dotenv_values(os.path.join(E5, ".env"))
env4 = dotenv_values(os.path.join(E4, ".env"))
EXPS = [("Exp 4", E4, env4.get("QDRANT_COLLECTION", "locomo_gem_neo4j"), env4.get("NEO4J_URL", "bolt://localhost:7688"), env4),
        ("Exp 5", E5, env5.get("QDRANT_COLLECTION", "locomo_gem_neo4j_date"), env5.get("NEO4J_URL", "bolt://localhost:7689"), env5)]

MONTHS = {m.lower(): i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                               "September", "October", "November", "December"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
MON = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
YEAR = r"((?:19|20)\d\d)"
PATTERNS = [(re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?(?: of)? {MON},? {YEAR}\b", re.I), ("d", "m", "y")),
            (re.compile(rf"\b{MON} (\d{{1,2}})(?:st|nd|rd|th)?,? {YEAR}\b", re.I), ("m", "d", "y")),
            (re.compile(rf"\b{YEAR}-(\d\d)-(\d\d)\b"), ("y", "m", "d")),
            (re.compile(rf"\b{MON},? {YEAR}\b", re.I), ("m", "y"))]
RELATIVE = re.compile(r"\b(yesterday|today|tonight|tomorrow|last (?:week|weekend|month|year|night|friday|saturday|sunday|"
                      r"monday|tuesday|wednesday|thursday|summer|winter|spring|fall)|this (?:week|weekend|month|year)|"
                      r"next (?:week|month|year|weekend|summer)|recently|(?:a few|two|three|\d+) (?:days|weeks|months|years) "
                      r"ago|(?:a|one) (?:week|month|year) ago)\b", re.I)
EARLIER = re.compile(r"\b(last (?:week|weekend|month|year|summer|winter|spring|fall)|(?:a few|two|three|\d+) "
                     r"(?:weeks|months|years) ago|(?:a|one) (?:week|month|year) ago)\b", re.I)


def dates_in(text):
    found, taken = [], []
    for rx, order in PATTERNS:
        for mt in rx.finditer(text or ""):
            if any(a < mt.end() and mt.start() < b for a, b in taken):
                continue
            g = dict(zip(order, mt.groups()))
            try:
                s = g["m"].lower().rstrip(".")
                mon = int(s) if s.isdigit() else MONTHS.get(s, MONTHS.get(s[:3]))
                found.append(dt.date(int(g["y"]), mon, int(g.get("d", 15))))
                taken.append((mt.start(), mt.end()))
            except (ValueError, KeyError, TypeError):
                pass
    return found


def jparse(x):
    if isinstance(x, dict):
        return x
    try:
        return json.loads(re.sub(r"^```(?:json)?|```$", "", str(x).strip(), flags=re.M))
    except Exception:
        return None


def jsonl(path):
    if not os.path.exists(path):
        return None
    out = []
    for line in open(path):
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


cv = json.load(open("dataset/locomo10.json"))[N]["conversation"]
A, B = cv["speaker_a"], cv["speaker_b"]
uids = [f"{A}_{N}", f"{B}_{N}"]
other = {uids[0]: B, uids[1]: A}
own_name = {uids[0]: A, uids[1]: B}
session_dates = {d for k, v in cv.items() if k.endswith("_date_time") and cv.get(k[:-len("_date_time")]) for d in dates_in(v)}
print(f"Conversation {N}: {A} / {B}, {len(session_dates)} sessions\n")

qc = QdrantClient("localhost", port=6333)
R = {}
for label, folder, col, url, env in EXPS:
    r = R[label] = collections.OrderedDict()
    # ---- 1. memories in Qdrant
    mems = []
    if qc.collection_exists(col):
        for u in uids:
            flt = models.Filter(must=[models.FieldCondition(key="user_id", match=models.MatchValue(value=u))])
            off = None
            while True:
                pts, off = qc.scroll(col, scroll_filter=flt, limit=500, offset=off, with_payload=True)
                mems += [(u, p.payload.get("data", ""), p.payload.get("timestamp")) for p in pts]
                if off is None:
                    break
    dated = close = mid = far = rel = only_other = 0
    for u, t, ts in mems:
        ds, own = dates_in(t), dates_in(str(ts or ""))
        rel += bool(RELATIVE.search(t))
        low = t.lower()
        only_other += (other[u].lower() in low and own_name[u].lower() not in low)
        if ds:
            dated += 1
            if own:
                gap = min(abs((d - own[0]).days) for d in ds)
                close, mid, far = close + (gap <= 7), mid + (7 < gap <= 60), far + (gap > 60)
    r["memories stored"] = len(mems)
    r["  with an explicit date"] = dated
    r["    within 7 days of own session date"] = close
    r["    8-60 days away"] = mid
    r["    over 60 days away (invented?)"] = far
    r["  still with a relative word"] = rel
    r["  only about the OTHER speaker"] = only_other
    r["  average length (words)"] = round(sum(len(t.split()) for _, t, _ in mems) / max(1, len(mems)), 1)

    # ---- 1+2. LLM log: facts extracted, all update decisions (NONE included)
    llm = jsonl(os.path.join(folder, f"logs/llm_conv{N}.jsonl"))
    if llm is None:
        r["(LLM log)"] = "not found"
    else:
        calls = facts = empty = 0
        dec = collections.Counter()
        earlier_to_session = 0
        llm_err = 0
        for rec in llm:
            if rec.get("error"):
                llm_err += 1
                continue
            if rec.get("llm") != "memory":
                continue
            msgs = rec.get("messages") or []
            user = next((m.get("content", "") for m in msgs if m.get("role") == "user"), "")
            resp = jparse(rec.get("response"))
            if str(user).startswith("Input:"):
                calls += 1
                fs = (resp or {}).get("facts") or []
                facts += len(fs)
                empty += not fs
                # "last week"/"a month ago" in the input, and a fact dated exactly on the session date
                sd = dates_in(re.search(r"\[([^\]]+)\]", user).group(1)) if re.search(r"\[([^\]]+)\]", user) else []
                if sd and EARLIER.search(user):
                    earlier_to_session += any(sd[0] in dates_in(str(f)) for f in fs)
            elif isinstance(resp, dict) and isinstance(resp.get("memory"), list):
                for item in resp["memory"]:
                    dec[str(item.get("event", "?")).upper()] += 1
        r["fact-extraction calls"] = calls
        r["  facts extracted"] = facts
        r["  calls with no fact"] = empty
        if label == "Exp 5":
            r["  'last week/month ago' turned into the session date"] = earlier_to_session
        for e in ("ADD", "UPDATE", "DELETE", "NONE"):
            r[f"update decisions {e}"] = dec.get(e, 0)
        r["LLM calls that failed"] = llm_err

    # ---- 2+4+5. event logs: UPDATEs that changed a date, graph deletions, failed add() calls
    upd_date = add_err = g_del = 0
    for u in uids:
        ev = jsonl(os.path.join(folder, f"logs/events_{u}.jsonl")) or []
        for rec in ev:
            add_err += bool(rec.get("error"))
            for e in rec.get("memory_events") or []:
                if str(e.get("event")).upper() == "UPDATE" and e.get("previous_memory") is not None:
                    if set(dates_in(e.get("previous_memory"))) != set(dates_in(e.get("memory"))):
                        upd_date += 1
            g_del += sum(len(x) if isinstance(x, list) else 1 for x in (rec.get("graph_deleted") or []) if x)
    r["UPDATEs that changed or removed a date"] = upd_date
    r["graph relations deleted"] = g_del
    r["add() calls that failed"] = add_err

    # ---- 3. graph in Neo4j
    try:
        drv = GraphDatabase.driver(url, auth=(env.get("NEO4J_USERNAME"), env.get("NEO4J_PASSWORD")))
        with drv.session() as s:
            trip = [(x["s"], x["r"], x["t"]) for x in s.run(
                "MATCH (a)-[r]->(b) WHERE a.user_id IN $uids RETURN a.name AS s, type(r) AS r, b.name AS t", uids=uids)]
        drv.close()
        nd = lambda n: str(n).replace("_", " ")
        nodes = {n for a, _, b in trip for n in (a, b)}
        dnodes = {n for n in nodes if dates_in(nd(n))}
        sess_copy = {n for n in dnodes if dates_in(nd(n))[0] in session_dates}
        r["graph relations stored"] = len(trip)
        r["  date nodes"] = len(dnodes)
        r["    = a session date (copied from brackets?)"] = len(sess_copy)
        r["  relative-word nodes"] = len({n for n in nodes if RELATIVE.search(nd(n))})
        r["  'user_id:' person nodes"] = len({n for n in nodes if str(n).startswith("user_id:")})
        r["_examples"] = [f"{a} -{rr}-> {b}" for a, rr, b in trip if a in sess_copy or b in sess_copy][:5]
    except Exception as e:
        r["graph"] = f"not reachable ({type(e).__name__}) - is the Neo4j container running?"

keys = [k for k in R["Exp 5"] if not k.startswith("_")] + [k for k in R["Exp 4"] if k not in R["Exp 5"] and not k.startswith("_")]
print(f"{'':54} {'Exp 4':>10} {'Exp 5':>10}")
for k in keys:
    print(f"{k:54} {str(R['Exp 4'].get(k, '-')):>10} {str(R['Exp 5'].get(k, '-')):>10}")
for label in ("Exp 5",):
    ex = R[label].get("_examples") or []
    if ex:
        print(f"\n{label}: graph relations that use a session date as a node (examples)")
        for x in ex:
            print("   ", x)
print("\nRead it as: dates should move from 'over 60 days away' to 'within 7 days'; the other lines should stay close to Exp 4."
      "\nA line that moves a lot is a side effect to look at before the other 9 conversations run.")
