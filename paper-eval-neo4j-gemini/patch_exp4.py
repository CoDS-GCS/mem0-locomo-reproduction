"""Exp 4 patch for src/memzero/config.py. Run once, from ~/mem0-repro/paper-eval-neo4j-gemini:
    python patch_exp4.py
What it changes (nothing else):
  1. The graph store is chosen by GRAPH_STORE in .env: "kuzu" (default, exactly as in Exp 2) or "neo4j".
  2. The empty-name guard from Exp 2 is extended to Mem0's Neo4j graph code (mem0.memory.graph_memory).
     Neo4j also uses each relation name as a relationship TYPE in Cypher ([r:works_at]), so a name with
     characters Cypher does not allow (e.g. "a,b") or starting with a digit makes the whole batch fail.
     Such names are cleaned (bad characters -> "_", a leading digit gets "r_" in front); empty ones are dropped.
     An entity type that is empty or contains a backtick becomes "entity" (types are used as node labels).
"""
import pathlib
import sys

p = pathlib.Path("src/memzero/config.py")
s = p.read_text()
if "GRAPH_STORE" in s:
    sys.exit("already patched - nothing changed")

OLD = '''    if is_graph:
        config["graph_store"] = {
            "provider": "kuzu",
            "config": {"db": os.getenv("KUZU_DB", "kuzu_db/locomo_mem0g.kuzu")},
        }
'''
NEW = '''    if is_graph and os.getenv("GRAPH_STORE", "kuzu") == "neo4j":
        config["graph_store"] = {
            "provider": "neo4j",
            "config": {
                "url": os.environ["NEO4J_URL"],
                "username": os.environ["NEO4J_USERNAME"],
                "password": os.environ["NEO4J_PASSWORD"],
            },
        }
    elif is_graph:
        config["graph_store"] = {
            "provider": "kuzu",
            "config": {"db": os.getenv("KUZU_DB", "kuzu_db/locomo_mem0g.kuzu")},
        }
'''
GUARD = '''

# ---- Gemini guard, Neo4j part (added for Exp 4) -------------------------------
# Same idea as the guard above, for Mem0's Neo4j graph code (mem0.memory.graph_memory).
# Neo4j uses each relation name as a relationship TYPE in Cypher ([r:works_at]) without quotes,
# so a name with characters Cypher does not allow, or starting with a digit, breaks the whole batch.
# Such names are cleaned (bad characters -> "_", a leading digit gets "r_"); empty ones are dropped.
# Entity types are used as node labels: an empty type, or one with a backtick, becomes "entity".
def _cypher_rel(name):
    name = _re.sub(r"\\W+", "_", name if isinstance(name, str) else "").strip("_")
    return "r_" + name if name[:1].isdigit() else name


try:
    import mem0.memory.graph_memory as _neo_mem

    _orig_nodes_neo = _neo_mem.MemoryGraph._retrieve_nodes_from_data
    def _nodes_valid_neo(self, data, filters):
        out = {}
        for k, v in _orig_nodes_neo(self, data, filters).items():
            if _not_empty(k):
                out[k] = v if (isinstance(v, str) and v and "`" not in v) else "entity"
        return out
    _neo_mem.MemoryGraph._retrieve_nodes_from_data = _nodes_valid_neo

    _orig_rels_neo = _neo_mem.MemoryGraph._remove_spaces_from_entities
    def _rels_valid_neo(self, entity_list):
        out = []
        for r in _orig_rels_neo(self, entity_list):
            if not (_not_empty(r.get("source")) and _not_empty(r.get("destination"))):
                continue
            r["relationship"] = _cypher_rel(r.get("relationship"))
            if r["relationship"]:
                out.append(r)
        return out
    _neo_mem.MemoryGraph._remove_spaces_from_entities = _rels_valid_neo
except ImportError:  # langchain-neo4j not installed: this folder does not use Neo4j
    pass
'''

if s.count(OLD) != 1:
    sys.exit("STOP: the graph_store block in config.py is not the one expected - nothing changed")
if "Gemini guard" not in s or "def _not_empty" not in s or "import re as _re" not in s:
    sys.exit("STOP: the Gemini guard from Exp 2 is missing in config.py - nothing changed")
p.write_text(s.replace(OLD, NEW) + GUARD)
print("patched OK")
