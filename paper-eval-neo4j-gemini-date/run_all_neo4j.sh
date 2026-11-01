#!/bin/bash
# Exp 4 overnight chain: conv 0 test -> sanity check -> all conversations -> search -> judge x10
cd ~/mem0-repro/paper-eval-neo4j-gemini-date || exit 1
source ~/mem0-repro/paper-eval-neo4j-gemini/.venv-neo/bin/activate || exit 1
set -a; source .env; set +a
mkdir -p logs results
L=logs/runner_n.log
stop() { echo "$(date '+%F %T') CHAIN STOPPED: $1" >> $L; exit 1; }
echo "$(date '+%F %T') CHAIN START" >> $L

# 1) conversation 0 alone, as a test
bash run_add_neo4j.sh 0
[ -f logs/n_done_0 ] || stop "conversation 0 did not finish"

# 2) sanity check: conversation 0 really has memories in Qdrant and entities in Neo4j
python - >> $L 2>&1 <<'PY' || stop "conversation 0 sanity check failed"
import json, os, sys
from neo4j import GraphDatabase
from qdrant_client import QdrantClient, models
cv = json.load(open("dataset/locomo10.json"))[0]["conversation"]
uids = [f"{cv['speaker_a']}_0", f"{cv['speaker_b']}_0"]
col = os.environ.get("QDRANT_COLLECTION", "locomo_gem_neo4j_date")
c = QdrantClient("localhost", port=6333)
ok = True
for u in uids:
    n = c.count(col, count_filter=models.Filter(must=[models.FieldCondition(
        key="user_id", match=models.MatchValue(value=u))]), exact=True).count
    print("sanity qdrant", u, n)
    ok = ok and n >= 50
drv = GraphDatabase.driver(os.environ["NEO4J_URL"], auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]))
with drv.session() as s:
    e = s.run("MATCH (n) WHERE n.user_id IN $uids RETURN count(n) AS c", uids=uids).single()["c"]
drv.close()
print("sanity neo4j entities", e)
ok = ok and e >= 50
sys.exit(0 if ok else 1)
PY

# 3) the other nine conversations (conv 0 is skipped because n_done_0 exists)
bash run_add_neo4j.sh
DONE=$(ls logs/n_done_* 2>/dev/null | wc -l)
[ "$DONE" -ge 10 ] || stop "only $DONE/10 conversations finished the add stage"

# 4) search + answers (resumes by itself)
bash run_search_neo4j.sh
[ -f results/mem0g_neo4j_search_BACKUP.json ] || stop "search did not reach 1986 answers"

# 5) judge, 10 runs
bash run_eval_neo4j.sh
echo "$(date '+%F %T') CHAIN END: $(ls results/mem0g_eval_run*.json 2>/dev/null | wc -l)/10 judge runs" >> $L
