"""Read-only access to the live stores. Qdrant: REST count/scroll only. Neo4j: READ sessions, LIMITed queries.
Results are cached for CACHE_S seconds so a page can never query more often than that. The Neo4j password is never returned."""
import json
import time
import urllib.request

CACHE_S = 25
_cache = {}


def _cached(key, fn):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_S:
        return hit[1]
    try:
        val = fn()
    except Exception as e:
        val = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    _cache[key] = (now, val)
    return val


def _qdrant_post(host, path, body, timeout=5):
    req = urllib.request.Request(f"http://{host}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def qdrant_user(exp, user, with_list=True):
    host = exp._env.get("QDRANT_HOST", "localhost") + ":" + exp._env.get("QDRANT_PORT", "6333")
    col = exp.collection
    flt = {"must": [{"key": "user_id", "match": {"value": user}}]}

    def run():
        out = {"collection": col}
        n = _qdrant_post(host, f"/collections/{col}/points/count", {"filter": flt, "exact": True})
        out["count"] = n["result"]["count"]
        if with_list:
            pts, off = [], None
            for _ in range(8):          # at most 8 x 256 points
                body = {"filter": flt, "limit": 256, "with_payload": True, "with_vector": False}
                if off is not None:
                    body["offset"] = off
                r = _qdrant_post(host, f"/collections/{col}/points/scroll", body)["result"]
                pts += r["points"]
                off = r.get("next_page_offset")
                if off is None:
                    break
            out["points"] = [{"id": p["id"], "memory": (p.get("payload") or {}).get("data"),
                              "created_at": (p.get("payload") or {}).get("created_at"), "updated_at": (p.get("payload") or {}).get("updated_at"),
                              "timestamp": (p.get("payload") or {}).get("timestamp")} for p in pts]
        return out
    return _cached(("q", col, user, with_list), run)


def neo4j_user(exp, user, node_cap=150, rel_cap=400):
    def run():
        from neo4j import GraphDatabase, READ_ACCESS, Query
        drv = GraphDatabase.driver(exp._env["NEO4J_URL"], auth=(exp._env["NEO4J_USERNAME"], exp._env["NEO4J_PASSWORD"]),
                                   connection_timeout=4, max_transaction_retry_time=2)
        try:
            with drv.session(default_access_mode=READ_ACCESS) as s:
                n = s.run(Query("MATCH (n) WHERE n.user_id = $u RETURN count(n) AS c", timeout=5), u=user).single()["c"]
                nodes = [{"name": r["name"], "labels": r["labels"]} for r in s.run(
                    Query("MATCH (n) WHERE n.user_id = $u RETURN n.name AS name, labels(n) AS labels LIMIT $cap", timeout=5), u=user, cap=node_cap)]
                rels = [{"source": r["a"], "relationship": r["t"], "target": r["b"]} for r in s.run(
                    Query("MATCH (a)-[r]->(b) WHERE a.user_id = $u AND b.user_id = $u RETURN a.name AS a, type(r) AS t, b.name AS b LIMIT $cap", timeout=5), u=user, cap=rel_cap)]
        finally:
            drv.close()
        return {"node_count": n, "nodes": nodes, "relationships": rels, "capped": n > node_cap}
    return _cached(("n", user), run)


def neo4j_has_nodes(exp, user, names):
    """Exact-name check of which entity names exist as nodes of this user (one query)."""
    names = sorted({n for n in names if n})[:20]

    def run():
        from neo4j import GraphDatabase, READ_ACCESS, Query
        drv = GraphDatabase.driver(exp._env["NEO4J_URL"], auth=(exp._env["NEO4J_USERNAME"], exp._env["NEO4J_PASSWORD"]), connection_timeout=4)
        try:
            with drv.session(default_access_mode=READ_ACCESS) as s:
                got = {r["name"] for r in s.run(Query("MATCH (n) WHERE n.user_id = $u AND n.name IN $names RETURN n.name AS name LIMIT 50", timeout=5), u=user, names=names)}
        finally:
            drv.close()
        return {"found": sorted(got)}
    return _cached(("nh", user, tuple(names)), run)
