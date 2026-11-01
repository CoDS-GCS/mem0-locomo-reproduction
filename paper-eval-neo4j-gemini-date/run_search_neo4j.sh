#!/bin/bash
# Exp 4, stage 2 (search + answer). Same as run_search_kuzu.sh; only folder, venv and log names differ.
cd ~/mem0-repro/paper-eval-neo4j-gemini-date || exit 1
source ~/mem0-repro/paper-eval-neo4j-gemini/.venv-neo/bin/activate || { echo "venv .venv-neo missing"; exit 1; }
set -a; source .env; set +a
mkdir -p logs results
OUT=results/mem0_results_top_30_filter_False_graph_True.json
count() { python -c "import json;d=json.load(open('$OUT'));print(sum(len(v) for v in d.values()))" 2>/dev/null || echo 0; }

for attempt in $(seq 1 30); do
  echo "$(date '+%F %T') search attempt $attempt, answered so far: $(count)" >> logs/runner_n.log
  python run_experiments.py --technique_type mem0 --method search --is_graph >> logs/search_n.log 2>&1
  N=$(count)
  if [ "$N" -ge 1986 ]; then
    cp "$OUT" results/mem0g_neo4j_search_BACKUP.json
    echo "$(date '+%F %T') SEARCH DONE: $N answers, backup saved" >> logs/runner_n.log
    exit 0
  fi
  echo "$(date '+%F %T') stopped at $N answers, resuming in 2 min" >> logs/runner_n.log
  sleep 120
done
echo "$(date '+%F %T') search gave up after 30 attempts" >> logs/runner_n.log
