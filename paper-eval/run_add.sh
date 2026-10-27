#!/bin/bash
cd ~/mem0-repro/paper-eval
source ../.venv312/bin/activate
set -a; source .env; set +a
mkdir -p logs

clean() { python - "$1" <<'EOF'
import sys, json
from qdrant_client import QdrantClient, models
i = int(sys.argv[1]); conv = json.load(open("dataset/locomo10.json"))[i]["conversation"]
c = QdrantClient("localhost", port=6333)
for spk in (conv["speaker_a"], conv["speaker_b"]):
    uid = f"{spk}_{i}"
    try:
        c.delete("locomo_mem0", points_selector=models.FilterSelector(filter=models.Filter(
            must=[models.FieldCondition(key="user_id", match=models.MatchValue(value=uid))])))
        print("cleaned", uid)
    except Exception:
        print("nothing to clean for", uid)
EOF
}

for pass in 1 2 3; do
  echo "===== pass $pass  $(date +%H:%M) ====="
  for N in 0 1 2 3 4 5 6 7 8 9; do
    [ -f logs/done_$N ] && continue
    clean $N
    START_CONV=$N python run_experiments.py --technique_type mem0 --method add > logs/add_$N.log 2>&1 &
    PID=$!
    while kill -0 $PID 2>/dev/null; do
      if grep -q "Messages added successfully" logs/add_$N.log; then sleep 5; kill -9 $PID; break; fi
      if [ $(( $(date +%s) - $(stat -c %Y logs/add_$N.log) )) -gt 900 ]; then
        echo "conv $N: no progress for 15 min - stopping it"; kill -9 $PID; break; fi
      sleep 20
    done
    ok=$(grep -c "Messages added successfully" logs/add_$N.log)
    crashes=$(grep -c "Exception in thread" logs/add_$N.log)
    skipped=$(grep -c "Error in new_memories_with_actions" logs/add_$N.log)
    echo "$(date +%H:%M)  conv $N: finished=$ok crashed_threads=$crashes skipped_batches=$skipped"
    if [ "$ok" -ge 1 ] && [ "$crashes" -eq 0 ]; then touch logs/done_$N
    else echo "  -> conv $N will be retried in the next pass"; sleep 60; fi
  done
done
echo "ALL DONE: $(ls logs/done_* | wc -l)/10 conversations loaded"
