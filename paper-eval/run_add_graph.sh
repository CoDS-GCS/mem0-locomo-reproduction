#!/bin/bash
cd ~/mem0-repro/paper-eval
set -a; source .env; set +a
mkdir -p logs
CONVS="${@:-0 1 2 3 4 5 6 7 8 9}"

clean() {
  python - "$1" <<'EOF'
import sys, json
from qdrant_client import QdrantClient, models
N = int(sys.argv[1]); c = QdrantClient("localhost", port=6333)
cv = json.load(open("dataset/locomo10.json"))[N]["conversation"]
for spk in (cv["speaker_a"], cv["speaker_b"]):
    uid = f"{spk}_{N}"
    if c.collection_exists("locomo_mem0g"):
        c.delete("locomo_mem0g", points_selector=models.FilterSelector(filter=models.Filter(
            must=[models.FieldCondition(key="user_id", match=models.MatchValue(value=uid))])))
    print(uid, file=open(f"logs/g_uids_{N}", "a"))
EOF
  while read uid; do
    docker exec neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (n {user_id: '$uid'}) DETACH DELETE n"
  done < logs/g_uids_$1; rm -f logs/g_uids_$1
}

for pass in 1 2 3; do
  for N in $CONVS; do
    [ -f logs/g_done_$N ] && continue
    echo "$(date +%T) pass $pass conv $N start" >> logs/runner_g.log
    clean $N
    START_CONV=$N END_CONV=$N python run_experiments.py --technique_type mem0 --method add --is_graph > logs/addg_$N.log 2>&1 &
    PID=$!
    while kill -0 $PID 2>/dev/null; do
      grep -q "Messages added successfully\|Processing conversations: 100%" logs/addg_$N.log && { kill -9 $PID; break; }
      AGE=$(( $(date +%s) - $(stat -c %Y logs/addg_$N.log) ))
      [ $AGE -gt 1200 ] && { echo "conv $N stale, killed" >> logs/runner_g.log; kill -9 $PID; break; }
      sleep 20
    done
    FIN=0; grep -q "Messages added successfully\|Processing conversations: 100%" logs/addg_$N.log && FIN=1
    CRASH=$(grep -c "Exception in thread" logs/addg_$N.log)
    SKIP=$(grep -c "Error in new_memories_with_actions\|Invalid JSON" logs/addg_$N.log)
    echo "$(date +%T) conv $N finished=$FIN crashes=$CRASH skipped=$SKIP" >> logs/runner_g.log
    [ $FIN -eq 1 ] && [ $CRASH -eq 0 ] && touch logs/g_done_$N
  done
done
echo "$(date +%T) DONE: $(ls logs/g_done_* 2>/dev/null | wc -l)/10" >> logs/runner_g.log
