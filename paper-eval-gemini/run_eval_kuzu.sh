#!/bin/bash
# Stage 3 (judge x10). A run's file only appears when that run is complete; finished runs are skipped on restart.
cd ~/mem0-repro/paper-eval-gemini || exit 1
source .venv-gem/bin/activate || { echo "venv .venv-gem missing"; exit 1; }
set -a; source .env; set +a
IN=results/mem0_results_top_30_filter_False_graph_True.json
for k in $(seq 1 10); do
  OUTK=results/mem0g_eval_run$k.json
  [ -s "$OUTK" ] && { echo "run $k already done"; continue; }
  for attempt in 1 2 3; do
    if python evals.py --input_file $IN --output_file $OUTK.tmp --max_workers 3 > logs/evalk_$k.log 2>&1; then
      mv $OUTK.tmp $OUTK; echo "$(date '+%F %T') judge run $k done" | tee -a logs/runner_k.log; break
    fi
    echo "$(date '+%F %T') judge run $k failed (attempt $attempt), retrying in 2 min" | tee -a logs/runner_k.log
    sleep 120
  done
done
