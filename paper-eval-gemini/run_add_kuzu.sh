#!/bin/bash
# Stage 1 (add) for Mem0g with Kuzu + Gemini, one conversation per process, crash-safe.
# Usage:  ./run_add_kuzu.sh          (all conversations)
#         ./run_add_kuzu.sh 0        (only conversation 0, for a test)
cd ~/mem0-repro/paper-eval-gemini || exit 1
source .venv-gem/bin/activate || { echo "venv .venv-gem missing"; exit 1; }
set -a; source .env; set +a
mkdir -p logs kuzu_db
CONVS="${@:-0 1 2 3 4 5 6 7 8 9}"
COL="${QDRANT_COLLECTION:-locomo_gem_kuzu}"

clean() {  # remove conversation $1 from Qdrant and Kuzu before (re)building it
  COL="$COL" python - "$1" <<'EOF'
import json, os, sys
import kuzu
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
path = os.getenv("KUZU_DB", "kuzu_db/locomo_mem0g.kuzu")
if os.path.exists(path):
    conn = kuzu.Connection(kuzu.Database(path))
    for u in uids:
        try:
            conn.execute("MATCH (n:Entity) WHERE n.user_id = $u DETACH DELETE n", {"u": u})
        except RuntimeError as e:
            print("kuzu note:", e)
print("cleaned", uids)
EOF
}

for pass in 1 2 3; do
  for N in $CONVS; do
    [ -f logs/k_done_$N ] && continue
    echo "$(date '+%F %T') pass $pass conv $N start" >> logs/runner_k.log
    clean $N >> logs/runner_k.log 2>&1
    START_CONV=$N END_CONV=$N python run_experiments.py --technique_type mem0 --method add --is_graph > logs/addk_$N.log 2>&1 &
    PID=$!
    while kill -0 $PID 2>/dev/null; do
      sleep 20
      if grep -q "Messages added successfully" logs/addk_$N.log; then sleep 30; kill -9 $PID 2>/dev/null; break; fi
      AGE=$(( $(date +%s) - $(stat -c %Y logs/addk_$N.log) ))
      if [ $AGE -gt 1800 ]; then echo "conv $N: no progress for 30 min, killed" >> logs/runner_k.log; kill -9 $PID; break; fi
    done
    wait $PID 2>/dev/null
    FIN=0; grep -q "Messages added successfully" logs/addk_$N.log && FIN=1
    CRASH=$(grep -c "Exception in thread" logs/addk_$N.log)
    SKIP=$(grep -c "SKIPPED BATCH" logs/addk_$N.log)
    BAD=$(grep -c "Error in new_memories_with_actions\|Invalid JSON\|Error in new_retrieved_facts" logs/addk_$N.log)
    echo "$(date '+%F %T') conv $N finished=$FIN crashes=$CRASH skipped_after_retries=$SKIP llm_format_errors=$BAD" >> logs/runner_k.log
    [ $FIN -eq 1 ] && [ $CRASH -eq 0 ] && touch logs/k_done_$N
  done
done
echo "$(date '+%F %T') ADD DONE: $(ls logs/k_done_* 2>/dev/null | wc -l)/10" >> logs/runner_k.log
