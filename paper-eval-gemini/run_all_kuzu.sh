#!/bin/bash
# Overnight chain: conv 0 test -> sanity check -> all conversations -> search -> judge x10
# Calls the three runners unchanged. Stops (and writes why) if a stage did not finish.
cd ~/mem0-repro/paper-eval-gemini || exit 1
source .venv-gem/bin/activate || exit 1
set -a; source .env; set +a
mkdir -p logs results
L=logs/runner_k.log
stop() { echo "$(date '+%F %T') CHAIN STOPPED: $1" >> $L; exit 1; }
echo "$(date '+%F %T') CHAIN START" >> $L

# 1) conversation 0 alone, as a test
bash run_add_kuzu.sh 0
[ -f logs/k_done_0 ] || stop "conversation 0 did not finish"

# 2) sanity check: conversation 0 really has memories in Qdrant and entities in Kuzu
python - >> $L 2>&1 <<'PY' || stop "conversation 0 sanity check failed"
import json, os, sys, kuzu
from qdrant_client import QdrantClient, models
cv = json.load(open("dataset/locomo10.json"))[0]["conversation"]
uids = [f"{cv['speaker_a']}_0", f"{cv['speaker_b']}_0"]
col = os.environ.get("QDRANT_COLLECTION", "locomo_gem_kuzu")
c = QdrantClient("localhost", port=6333)
ok = True
for u in uids:
    n = c.count(col, count_filter=models.Filter(must=[models.FieldCondition(
        key="user_id", match=models.MatchValue(value=u))]), exact=True).count
    print("sanity qdrant", u, n)
    ok = ok and n >= 50
conn = kuzu.Connection(kuzu.Database(os.environ.get("KUZU_DB", "kuzu_db/locomo_mem0g.kuzu")))
e = conn.execute("MATCH (n:Entity) RETURN count(n)").get_next()[0]
print("sanity kuzu entities", e)
ok = ok and e >= 50
sys.exit(0 if ok else 1)
PY

# 3) the other nine conversations (conv 0 is skipped because k_done_0 exists)
bash run_add_kuzu.sh
DONE=$(ls logs/k_done_* 2>/dev/null | wc -l)
[ "$DONE" -ge 10 ] || stop "only $DONE/10 conversations finished the add stage"

# 4) search + answers (resumes by itself)
bash run_search_kuzu.sh
[ -f results/mem0g_kuzu_search_BACKUP.json ] || stop "search did not reach 1986 answers"

# 5) judge, 10 runs
bash run_eval_kuzu.sh
echo "$(date '+%F %T') CHAIN END: $(ls results/mem0g_eval_run*.json 2>/dev/null | wc -l)/10 judge runs" >> $L
