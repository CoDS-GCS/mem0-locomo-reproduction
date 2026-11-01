"""Exp 5 smoke test (costs a fraction of a cent: one add() call = about 5 Gemini calls).
Run from the Exp 5 folder with Exp 4's venv active:
    cd ~/mem0-repro/paper-eval-neo4j-gemini-date
    source ~/mem0-repro/paper-eval-neo4j-gemini/.venv-neo/bin/activate
    python smoke_exp5.py

1. settings: right folder, DATE_PREFIX=1, the Exp 5 collection and Neo4j; Exp 4's are not used
2. dry run of the REAL add.py code on session 1 of conversation 0 (no database, no LLM):
   with DATE_PREFIX=0 the text must be exactly Exp 4's, with DATE_PREFIX=1 it must start with the date
3. one real add() of the batch add.py sends with turn D1:3 ("I went to a LGBTQ support group yesterday")
   into a throwaway user; the LLM log must show the date in the fact-extractor AND graph-extractor input
4. removes the throwaway user and collection; the LLM log stays in logs/smoke/ for you to read
"""
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path.cwd()
if HERE.name != "paper-eval-neo4j-gemini-date":
    sys.exit("STOP: run this from ~/mem0-repro/paper-eval-neo4j-gemini-date")
sys.path.insert(0, str(HERE))  # import src/ from this folder, never from Exp 4's
from dotenv import dotenv_values, load_dotenv  # noqa: E402

env = dotenv_values(".env")
ok = True


def check(cond, msg):
    global ok
    print(("   OK    " if cond else "   FAIL  ") + msg)
    ok = ok and bool(cond)


print("1. settings (.env of this folder)")
check(env.get("DATE_PREFIX") == "1", f"DATE_PREFIX={env.get('DATE_PREFIX')}")
check(env.get("QDRANT_COLLECTION") == "locomo_gem_neo4j_date", f"QDRANT_COLLECTION={env.get('QDRANT_COLLECTION')}")
check(str(env.get("NEO4J_URL", "")).endswith(":7689"), f"NEO4J_URL={env.get('NEO4J_URL')} (Exp 4 uses :7688)")
check(env.get("GRAPH_STORE") == "neo4j", f"GRAPH_STORE={env.get('GRAPH_STORE')}")
check(env.get("EXTRACTION_PROMPT", "paper") == "paper", f"EXTRACTION_PROMPT={env.get('EXTRACTION_PROMPT', 'paper (not set)')}")
check(env.get("MODEL"), f"MODEL={env.get('MODEL')}")

# everything this test writes goes to a throwaway collection / log, never to the Exp 5 or Exp 4 data
os.environ["QDRANT_COLLECTION"] = "smoke_gem_neo4j_date"
os.environ["LLM_LOG"] = "logs/smoke/llm"
os.environ["EVENTS_LOG"] = "logs/smoke/events"
os.environ.pop("START_CONV", None)
pathlib.Path("logs/smoke").mkdir(parents=True, exist_ok=True)
LOG = pathlib.Path("logs/smoke/llm_other.jsonl")
if LOG.exists():
    LOG.unlink()
load_dotenv()  # does not override the values set above

from qdrant_client import QdrantClient  # noqa: E402

qc = QdrantClient("localhost", port=6333)
exp4_before = qc.count("locomo_gem_neo4j", exact=True).count if qc.collection_exists("locomo_gem_neo4j") else None
print(f"   Exp 4 collection locomo_gem_neo4j: {exp4_before} memories (read only)")

print("\n2. dry run of the real add.py message code (session 1 of conversation 0)")
import src.memzero.add as addmod  # noqa: E402

check(pathlib.Path(addmod.__file__).resolve().is_relative_to(HERE), f"add.py used: {addmod.__file__}")
cv = json.load(open("dataset/locomo10.json"))[0]["conversation"]
ts = cv["session_1_date_time"]
item = {"conversation": {k: cv[k] for k in ("speaker_a", "speaker_b", "session_1", "session_1_date_time")}}


class _Any:  # stands in for the Mem0 client during the dry run: every call does nothing
    def __getattr__(self, n): return _Any()
    def __call__(self, *a, **k): return _Any()
    def __iter__(self): return iter(())


class _Stub:
    batch_size, is_graph, data = 2, True, None

    def __init__(self): self.sent = {}
    def add_memories_for_speaker(self, speaker, messages, timestamp, desc=""): self.sent[speaker] = (messages, timestamp)
    def add_memory(self, user_id, message, metadata, *a, **k): self.sent.setdefault(user_id, ([], metadata))[0].extend(message)
    def __getattr__(self, n): return _Any()


sent = {}
print("   (add.py itself prints 'Messages added successfully' twice here: nothing is sent anywhere in this dry run)")
for flag in ("0", "1"):
    os.environ["DATE_PREFIX"] = flag
    st = _Stub()
    addmod.MemoryADD.process_conversation(st, item, 0)
    sent[flag] = st.sent
a_id = f"{cv['speaker_a']}_0"
exp4_text = [f"{t['speaker']}: {t['text']}" for t in cv["session_1"]]
got0 = [m["content"] for m in sent["0"].get(a_id, ([], None))[0]]
got1 = [m["content"] for m in sent["1"].get(a_id, ([], None))[0]]
check(got0 == exp4_text, f"DATE_PREFIX=0: all {len(got0)} turns identical to Exp 4's text")
pre = f"[today is {ts.split(' on ', 1)[-1]}] "
check(got1 == [pre + x for x in exp4_text], f"DATE_PREFIX=1: all {len(got1)} turns start with {pre.strip()}")
check(all(v[1] == ts or v[1] == {"timestamp": ts} for v in sent["1"].values()), "metadata timestamp unchanged")
for x in got1[:4]:
    print("         ", x[:110])
os.environ["DATE_PREFIX"] = "1"

print("\n3. one real add() of the batch with turn D1:3 (throwaway user smoke_exp5)")
from neo4j import GraphDatabase  # noqa: E402
from src.memzero.config import get_memory  # noqa: E402

drv = GraphDatabase.driver(os.environ["NEO4J_URL"], auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]))
with drv.session() as s:
    v = s.run("CALL dbms.components() YIELD name, versions RETURN name, versions[0] AS v").single()
print(f"   Neo4j at {os.environ['NEO4J_URL']}: {v['name']} {v['v']}")
m = get_memory(is_graph=True)
check(bool(m.config.custom_fact_extraction_prompt), "authors' instructions in use as the extraction prompt")
batch = sent["1"][a_id][0][2:4]  # add.py sends 2 turns per add(): this is the 2nd batch, turns D1:3 + D1:4
res = m.add(batch, user_id="smoke_exp5", metadata={"timestamp": ts})
recs = [json.loads(l) for l in LOG.read_text().splitlines()] if LOG.exists() else []
ext = [r for r in recs if r["llm"] == "memory" and any(x.get("role") == "user" and str(x.get("content", "")).startswith("Input:")
                                                      for x in r["messages"] or [])]
graph = [r for r in recs if r["llm"] == "graph"]
check(len(recs) > 0, f"LLM log written: {LOG} ({len(recs)} calls: {len(ext)} fact extraction, {len(graph)} graph)")
if ext:
    user_in = [x["content"] for x in ext[0]["messages"] if x["role"] == "user"][0]
    check(ts.split(" on ", 1)[-1] in user_in, "the date is in the FACT-EXTRACTOR input. What Gemini received:")
    for line in user_in.strip().splitlines():
        print("         ", line[:130])
    print("   facts Gemini extracted:")
    try:
        facts = json.loads(re.sub(r"^```(?:json)?|```$", "", str(ext[0]["response"]).strip(), flags=re.M))["facts"]
    except Exception:
        facts = [str(ext[0]["response"])[:300]]
    for f in facts:
        print("          -", f)
    joined = " ".join(map(str, facts))
    if re.search(r"\b7(th)? May|May 7", joined):
        print("   -> 'yesterday' was turned into 7 May 2023 (the gold answer)")
    elif re.search(r"8(th)? May|May 8", joined):
        print("   -> the session date (8 May) was written, 'yesterday' not resolved - we will count this in date_check.py")
    else:
        print("   -> no May 2023 date in the facts this time - look at the full run with date_check.py")
else:
    check(False, "no fact-extraction call found in the LLM log")
check(any(ts.split(" on ", 1)[-1] in json.dumps(r["messages"]) for r in graph), "the date is in the GRAPH-EXTRACTOR input")
print("   memories stored:", [x.get("memory") for x in res.get("results", [])])
print("   graph relations added:", (res.get("relations") or {}).get("added_entities") if isinstance(res.get("relations"), dict) else res.get("relations"))

print("\n4. cleanup of the throwaway user")
m.delete_all(user_id="smoke_exp5")
with drv.session() as s:
    s.run("MATCH (n) WHERE n.user_id = 'smoke_exp5' DETACH DELETE n").consume()
drv.close()
qc.delete_collection("smoke_gem_neo4j_date")
exp4_after = qc.count("locomo_gem_neo4j", exact=True).count if qc.collection_exists("locomo_gem_neo4j") else None
check(exp4_after == exp4_before, f"Exp 4 collection unchanged: {exp4_before} -> {exp4_after} memories")
print(f"   full prompts and answers of this test: {HERE / LOG}")
print("\nSMOKE TEST PASSED - you can start the run." if ok else "\nSMOKE TEST FAILED - do not start the run; check the FAIL lines.")
