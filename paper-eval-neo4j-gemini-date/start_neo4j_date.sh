#!/bin/bash
# Exp 5: start a third Neo4j container, neo4j-date, for the Exp 5 graph
#   ports: 7689 (bolt, used by Mem0) and 7476 (browser)
# It uses the same image and the same settings (password included) as Exp 4's neo4j-gem;
# only the name, the ports and the data volume (neo4j_date_data) differ. neo4j-gem and its data are not touched.
# Run once:   bash ~/mem0-repro/paper-eval-neo4j-gemini-date/start_neo4j_date.sh
# Later (e.g. after a reboot) the same command just starts it again.
cd ~/mem0-repro/paper-eval-neo4j-gemini-date || exit 1
NAME=neo4j-date
SINCE=$(date +%s)
if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "container $NAME already exists - starting it"
  docker start "$NAME" >/dev/null || exit 1
else
  docker inspect neo4j-gem >/dev/null 2>&1 || { echo "STOP: Exp 4's container neo4j-gem not found - check the setup"; exit 1; }
  IMAGE=$(docker inspect -f '{{.Config.Image}}' neo4j-gem)
  ENVF=$(mktemp); chmod 600 "$ENVF"
  # the NEO4J_* settings that were given to neo4j-gem (not the image's own built-in variables)
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' neo4j-gem | grep '^NEO4J' \
    | grep -v '^NEO4J_\(HOME\|SHA256\|TARBALL\|EDITION\|VERSION\)=' > "$ENVF"
  if ! grep -q '^NEO4J_AUTH=' "$ENVF"; then  # neo4j-gem had no NEO4J_AUTH: use the user/password from .env
    U=$(grep '^NEO4J_USERNAME=' .env | head -1 | cut -d= -f2- | tr -d "\"'")
    P=$(grep '^NEO4J_PASSWORD=' .env | head -1 | cut -d= -f2- | tr -d "\"'")
    echo "NEO4J_AUTH=${U:-neo4j}/$P" >> "$ENVF"
  fi
  echo "image: $IMAGE | settings copied from neo4j-gem: $(cut -d= -f1 "$ENVF" | tr '\n' ' ')(values not shown)"
  docker run -d --name "$NAME" -p 7476:7474 -p 7689:7687 -v neo4j_date_data:/data --env-file "$ENVF" "$IMAGE" >/dev/null
  RC=$?
  rm -f "$ENVF"
  [ $RC -eq 0 ] || { echo "STOP: docker run failed (see the message above) - check the setup"; exit 1; }
fi
echo -n "waiting for Neo4j to start "
for i in $(seq 1 60); do
  if docker logs --since "$SINCE" "$NAME" 2>&1 | grep -q "Started\."; then
    echo " ready: bolt://localhost:7689  (browser: http://localhost:7476)"
    docker ps --filter "name=neo4j" --format '   {{.Names}}  {{.Status}}  {{.Ports}}'
    exit 0
  fi
  echo -n "."; sleep 3
done
echo; echo "STOP: Neo4j did not say 'Started.' within 3 minutes. Check:  docker logs --tail 30 $NAME"; exit 1
