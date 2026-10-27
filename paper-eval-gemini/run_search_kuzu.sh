#!/bin/bash
# Stage 2 (search + answer). Resumes automatically after any crash until all 1,986 questions are answered.
cd ~/mem0-repro/paper-eval-gemini || exit 1
source .venv-gem/bin/activate || { echo "venv .venv-gem missing"; exit 1; }
set -a; source .env; set +a
mkdir -p logs results
OUT=results/mem0_results_top_30_filter_False_graph_True.json
count() { python -c "import json;d=json.load(open('$OUT'));print(sum(len(v) for v in d.values()))" 2>/dev/null || echo 0; }

for attempt in $(seq 1 30); do
  echo "$(date '+%F %T') search attempt $attempt, answered so far: $(count)" >> logs/runner_k.log
  python run_experiments.py --technique_type mem0 --method search --is_graph >> logs/search_k.log 2>&1
  N=$(count)
  if [ "$N" -ge 1986 ]; then
    cp "$OUT" results/mem0g_kuzu_search_BACKUP.json
    echo "$(date '+%F %T') SEARCH DONE: $N answers, backup saved" >> logs/runner_k.log
    exit 0
  fi
  echo "$(date '+%F %T') stopped at $N answers, resuming in 2 min" >> logs/runner_k.log
  sleep 120
done
echo "$(date '+%F %T') search gave up after 30 attempts" >> logs/runner_k.log
