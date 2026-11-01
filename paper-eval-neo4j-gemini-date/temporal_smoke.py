"""Temporal smoke test for Exp 5, BEFORE the full run (costs a few cents: about 24 add() calls on Flash-Lite).
Run from the Exp 5 folder with the venv active:
    cd ~/mem0-repro/paper-eval-neo4j-gemini-date
    source ~/mem0-repro/paper-eval-neo4j-gemini/.venv-neo/bin/activate
    python temporal_smoke.py            (8 cases; or e.g. python temporal_smoke.py 12)

It picks LOCOMO temporal questions whose evidence turn uses a relative time ("yesterday", "last year",
"next month", "last Saturday", ...). For each, it sends the same 2-turn batch that add.py sends for that turn
(built by the real add.py code) to a fresh throwaway user, three ways:
  A  no date in the text                 = Exp 4
  B  date in front of every turn         = Exp 5 (the kit)
  C  B + one extra rule for the graph step, given through Mem0's own setting graph_store.custom_prompt
     (a possible fix for the graph; NOT used by the run unless we decide so)
and prints, next to the gold answer, the memories Mem0 stored and the graph relations it added, with flags:
  memories: has an explicit date or year? still has a relative word?
  graph:    a relative word used as a node (e.g. "yesterday")? a date used as a node?
Everything goes to a throwaway Qdrant collection and throwaway users in the Exp 5 Neo4j, all removed at the end.
"""
import datetime as dt
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path.cwd()
if HERE.name != "paper-eval-neo4j-gemini-date":
    sys.exit("STOP: run this from ~/mem0-repro/paper-eval-neo4j-gemini-date")
sys.path.insert(0, str(HERE))
N_CASES = int(sys.argv[1]) if len(sys.argv) > 1 else 8
COL = "smoke_temporal_exp5"
os.environ["QDRANT_COLLECTION"] = COL
os.environ["LLM_LOG"] = "logs/smoke/temporal_llm"
os.environ["EVENTS_LOG"] = "logs/smoke/temporal_events"
os.environ.pop("START_CONV", None)
pathlib.Path("logs/smoke").mkdir(parents=True, exist_ok=True)
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

GRAPH_RULE = ("Each message starts with its date in square brackets, e.g. [1:56 pm on 8 May, 2023]. Never use a relative "
              "time expression (yesterday, today, last week, last Saturday, last year, next month, ...) as an entity: "
              "replace it with the absolute date or period it refers to, computed from the date in brackets "
              "(e.g. 'yesterday' in a message dated 8 May 2023 becomes '7 May 2023'; 'last year' becomes '2022').")

RELATIVE = re.compile(r"\b(yesterday|today|tonight|tomorrow|last (?:week|weekend|month|year|night|friday|saturday|sunday|"
                      r"monday|tuesday|wednesday|thursday|summer|winter|spring|fall)|this (?:week|weekend|month|year|"
                      r"past week)|next (?:week|month|year|weekend|summer)|recently|(?:a few|two|three|\d+) (?:days|weeks|"
                      r"months|years) ago|(?:a|one) (?:week|month|year) ago)\b", re.I)
MON = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DATEISH = re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)? {MON}\b|\b{MON} \d{{1,2}}\b|\b{MON},? (?:19|20)\d\d\b|\b(?:19|20)\d\d\b", re.I)

# ---------------------------------------------------------------- pick the cases
data = json.load(open("dataset/locomo10.json"))
cases, per_word = [], {}
for ci, item in enumerate(data):
    cv = item["conversation"]
    for qa in item["qa"]:
        if str(qa.get("category")) != "2" or not qa.get("evidence"):
            continue
        m = re.match(r"D(\d+):(\d+)$", str(qa["evidence"][0]).strip())
        if not m:
            continue
        sess = f"session_{m.group(1)}"
        turns = cv.get(sess) or []
        idx = next((i for i, t in enumerate(turns) if t.get("dia_id") == qa["evidence"][0].strip()), None)
        if idx is None:
            continue
        rel = RELATIVE.search(turns[idx]["text"])
        if not rel:
            continue
        w = rel.group(0).lower()
        if per_word.get(w, 0) >= 2 or sum(x["ci"] == ci for x in cases) >= 2:  # varied words, several conversations
            continue
        per_word[w] = per_word.get(w, 0) + 1
        cases.append(dict(ci=ci, sess=sess, idx=idx, qa=qa, turn=turns[idx], word=w))
        if len(cases) >= N_CASES:
            break
    if len(cases) >= N_CASES:
        break

# ---------------------------------------------------------------- build the batches with the real add.py code
import src.memzero.add as addmod  # noqa: E402


class _Any:
    def __getattr__(self, n): return _Any()
    def __call__(self, *a, **k): return _Any()
    def __iter__(self): return iter(())


class _Stub:
    batch_size, is_graph, data = 2, True, None
    def __init__(self): self.sent = {}
    def add_memories_for_speaker(self, speaker, messages, timestamp, desc=""): self.sent[speaker] = (messages, timestamp)
    def __getattr__(self, n): return _Any()


import contextlib, io  # noqa: E401,E402

for c in cases:
    cv = data[c["ci"]]["conversation"]
    item = {"conversation": {k: cv[k] for k in ("speaker_a", "speaker_b", c["sess"], c["sess"] + "_date_time")}}
    sid = f"{c['turn']['speaker']}_{c['ci']}"
    start = (c["idx"] // 2) * 2  # add.py sends 2 turns per add(): the batch that contains the evidence turn
    for flag in ("0", "1"):
        os.environ["DATE_PREFIX"] = flag
        st = _Stub()
        with contextlib.redirect_stdout(io.StringIO()):  # hide add.py's own "Messages added successfully"
            addmod.MemoryADD.process_conversation(st, item, c["ci"])
        msgs, ts = st.sent[sid]
        c["batch" + flag] = msgs[start:start + 2]
        c["ts"] = ts
os.environ["DATE_PREFIX"] = "1"

# ---------------------------------------------------------------- run them through Mem0
from neo4j import GraphDatabase  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402
from src.memzero.config import get_memory  # noqa: E402

m = get_memory(is_graph=True)
gcfg = m.graph.config.graph_store
uids = []
tot = {v: dict(mem=0, mem_date=0, mem_rel=0, g=0, g_rel=0, g_date=0) for v in "ABC"}
LABEL = {"A": "A no date (Exp 4)", "B": "B date shown (Exp 5)", "C": "C B + graph rule"}
print(f"{len(cases)} cases, each sent 3 ways (A, B, C). Gemini model: {os.getenv('MODEL')}\n")
for k, c in enumerate(cases, 1):
    q = c["qa"]
    print(f"[{k}/{len(cases)}] conv {c['ci']}, {c['sess']} ({c['ts']}), {c['turn']['speaker']}, {c['turn']['dia_id']}")
    print(f"  Q: {q['question']}   GOLD: {q['answer']}")
    print(f"  turn: \"{c['turn']['text'][:160]}\"")
    for v in "ABC":
        uid = f"{c['turn']['speaker']}_t{k}{v}"
        uids.append(uid)
        gcfg.custom_prompt = GRAPH_RULE if v == "C" else None
        try:
            res = m.add(c["batch0"] if v == "A" else c["batch1"], user_id=uid, metadata={"timestamp": c["ts"]})
        except Exception as e:
            print(f"  {LABEL[v]:22} ERROR {type(e).__name__}: {str(e)[:150]}")
            continue
        mems = [x.get("memory", "") for x in res.get("results", []) if x.get("event", "ADD") == "ADD"]
        rels = [r for grp in ((res.get("relations") or {}).get("added_entities") or []) for r in (grp or [])]
        nodes = {str(n) for r in rels for n in (r.get("source"), r.get("target") or r.get("destination")) if n}
        nd = lambda n: n.replace("_", " ")
        t = tot[v]
        t["mem"] += len(mems)
        t["mem_date"] += sum(bool(DATEISH.search(x)) for x in mems)
        t["mem_rel"] += sum(bool(RELATIVE.search(x)) for x in mems)
        t["g"] += len(rels)
        g_rel = [n for n in nodes if RELATIVE.search(nd(n))]
        g_date = [n for n in nodes if DATEISH.search(nd(n))]
        t["g_rel"] += len(g_rel)
        t["g_date"] += len(g_date)
        print(f"  {LABEL[v]}")
        for x in mems or ["(no memory stored)"]:
            flags = ("  [date]" if DATEISH.search(x) else "") + ("  [RELATIVE LEFT]" if RELATIVE.search(x) else "")
            print(f"      mem: {x[:200]}{flags}")
        for r in rels:
            print(f"      graph: {r.get('source')} -{r.get('relationship')}-> {r.get('target') or r.get('destination')}")
        if g_rel:
            print(f"      >> graph uses a relative word as a node: {g_rel}")
    gcfg.custom_prompt = None
    print()

# ---------------------------------------------------------------- summary + cleanup
print("SUMMARY over all cases")
print(f"{'':22} {'memories':>8} {'with date':>9} {'relative left':>13} {'graph rels':>10} {'rel-word nodes':>14} {'date nodes':>10}")
for v in "ABC":
    t = tot[v]
    print(f"{LABEL[v]:22} {t['mem']:8} {t['mem_date']:9} {t['mem_rel']:13} {t['g']:10} {t['g_rel']:14} {t['g_date']:10}")

drv = GraphDatabase.driver(os.environ["NEO4J_URL"], auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]))
with drv.session() as s:
    s.run("MATCH (n) WHERE n.user_id IN $uids DETACH DELETE n", uids=uids).consume()
drv.close()
QdrantClient("localhost", port=6333).delete_collection(COL)
print(f"\nCleanup done (throwaway users and collection {COL} removed). Full prompts/answers: "
      f"{HERE / 'logs/smoke/temporal_llm_other.jsonl'}")
