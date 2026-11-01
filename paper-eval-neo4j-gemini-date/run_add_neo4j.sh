#!/bin/bash
# Exp 4, stage 1 (add): Mem0g with Neo4j + Gemini, one conversation per process, crash-safe.
# Same logic as run_add_kuzu.sh; only the folder, venv, log names and the graph cleanup differ.
# Usage:  ./run_add_neo4j.sh          (all conversations)
#         ./run_add_neo4j.sh 0        (only conversation 0)
cd ~/mem0-repro/paper-eval-neo4j-gemini-date || exit 1
source ~/mem0-repro/paper-eval-neo4j-gemini/.venv-neo/bin/activate || { echo "venv .venv-neo missing"; exit 1; }
set -a; source .env; set +a
mkdir -p logs
CONVS="${@:-0 1 2 3 4 5 6 7 8 9}"
COL="${QDRANT_COLLECTION:-locomo_gem_neo4j_date}"

clean() {  # remove conversation $1 from Qdrant and Neo4j before (re)building it
  COL="$COL" python - "$1" <<'PY'
import json, os, sys
from neo4j import GraphDatabase
from qdrant_client import QdrantClient, models
N = int(sys.argv[1])
cv = json.load(open("dataset/locomo10.json"))[N]["conversation"]
uids = [f"{cv['speaker_a']}_{N}", f"{cv['speaker_b']}_{N}"]
col = os.environ["COL"]
c = QdrantClient("localhost", port=6333)
if c.collection_exists(col):
    for u in uids:
        c.delete(col, points_selector=models.FilterSelector(filter=models.Filter(
            must=[models.FieldCondition(key="user_id", match=models.MatchValue(value=u))])))
drv = GraphDatabase.driver(os.environ["NEO4J_URL"], auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]))
with drv.session() as s:
    s.run("MATCH (n) WHERE n.user_id IN $uids DETACH DELETE n", uids=uids).consume()
drv.close()
import time  # keep the logs of an earlier (failed) pass apart from the new one
stamp = time.strftime('%Y%m%d_%H%M%S')
prefix = os.getenv("EVENTS_LOG")
if prefix:
    for u in uids:
        f = f"{prefix}_{u}.jsonl"
        if os.path.exists(f):
            os.rename(f, f"{prefix}_{u}.before_{stamp}.jsonl")
llm_prefix = os.getenv("LLM_LOG")
if llm_prefix and os.path.exists(f"{llm_prefix}_conv{N}.jsonl"):
    os.rename(f"{llm_prefix}_conv{N}.jsonl", f"{llm_prefix}_conv{N}.before_{stamp}.jsonl")
print("cleaned", uids)
PY
}

for pass in 1 2 3; do
  for N in $CONVS; do
    [ -f logs/n_done_$N ] && continue
    echo "$(date '+%F %T') pass $pass conv $N start" >> logs/runner_n.log
    clean $N >> logs/runner_n.log 2>&1
    START_CONV=$N END_CONV=$N python run_experiments.py --technique_type mem0 --method add --is_graph > logs/addn_$N.log 2>&1 &
    PID=$!
    while kill -0 $PID 2>/dev/null; do
      sleep 20
      if grep -q "Messages added successfully" logs/addn_$N.log; then sleep 30; kill -9 $PID 2>/dev/null; break; fi
      AGE=$(( $(date +%s) - $(stat -c %Y logs/addn_$N.log) ))
      if [ $AGE -gt 1800 ]; then echo "conv $N: no progress for 30 min, killed" >> logs/runner_n.log; kill -9 $PID; break; fi
    done
    wait $PID 2>/dev/null
    FIN=0; grep -q "Messages added successfully" logs/addn_$N.log && FIN=1
    CRASH=$(grep -c "Exception in thread" logs/addn_$N.log)
    SKIP=$(grep -c "SKIPPED BATCH" logs/addn_$N.log)
    BAD=$(grep -c "Error in new_memories_with_actions\|Invalid JSON\|Error in new_retrieved_facts" logs/addn_$N.log)
    echo "$(date '+%F %T') conv $N finished=$FIN crashes=$CRASH skipped_after_retries=$SKIP llm_format_errors=$BAD" >> logs/runner_n.log
    [ $FIN -eq 1 ] && [ $CRASH -eq 0 ] && touch logs/n_done_$N
  done
done
echo "$(date '+%F %T') ADD DONE: $(ls logs/n_done_* 2>/dev/null | wc -l)/10" >> logs/runner_n.log
