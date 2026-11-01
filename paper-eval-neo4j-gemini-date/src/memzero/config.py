"""Mem0 config for the Gemini (Vertex AI) + Kuzu experiment.

Same custom instructions as the paper's add.py. Differences from our GPT-4o-mini runs:
  - LLM and embeddings: Gemini on Vertex AI (paid from Google Cloud trial credits)
  - Graph store (Mem0g): Kuzu, an embedded graph database (a folder on disk, no server)
  - mem0ai 1.0.11 (the last release that supports Kuzu)
"""
import os

from dotenv import load_dotenv

from mem0 import Memory

load_dotenv()

EMBED_DIMS = int(os.getenv("EMBED_DIMS", "768"))

# Same custom instructions as add.py, plus the JSON output format the open-source fact extractor expects
custom_fact_extraction_prompt = """
Generate personal memories that follow these guidelines:

1. Each memory should be self-contained with complete context, including:
   - The person's name, do not use "user" while creating memories
   - Personal details (career aspirations, hobbies, life circumstances)
   - Emotional states and reactions
   - Ongoing journeys or future plans
   - Specific dates when events occurred

2. Include meaningful personal narratives focusing on:
   - Identity and self-acceptance journeys
   - Family planning and parenting
   - Creative outlets and hobbies
   - Mental health and self-care activities
   - Career aspirations and education goals
   - Important life events and milestones

3. Make each memory rich with specific details rather than general statements
   - Include timeframes (exact dates when possible)
   - Name specific activities (e.g., "charity race for mental health" rather than just "exercise")
   - Include emotional context and personal growth elements

4. Extract memories only from user messages, not incorporating assistant responses

5. Format each memory as a paragraph with a clear narrative structure that captures the person's experience, challenges, and aspirations

Return the memories in JSON format with the key "facts": {"facts": ["...", "..."]}
"""


def get_memory(is_graph=False):
    collection = os.getenv("QDRANT_COLLECTION", "locomo_gem_kuzu" if is_graph else "locomo_gem")
    config = {
        "llm": {
            "provider": "gemini",
            "config": {"model": os.getenv("MODEL", "gemini-2.5-flash-lite"), "temperature": 0},
        },
        "embedder": {
            "provider": "gemini",
            "config": {"model": os.getenv("EMBED_MODEL", "gemini-embedding-001"), "embedding_dims": EMBED_DIMS},
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "host": "localhost",
                "port": 6333,
                "collection_name": collection,
                "embedding_model_dims": EMBED_DIMS,
            },
        },
        "version": "v1.1",
        "custom_fact_extraction_prompt": custom_fact_extraction_prompt,
    }
    if is_graph and os.getenv("GRAPH_STORE", "kuzu") == "neo4j":
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
    return _with_llm_log(_with_event_log(Memory.from_config(config)))


# ---- Gemini guard (added 2026-10-21) ----------------------------------------
# Gemini sometimes returns an entity, or one end of a relation, with an empty name.
# Vertex refuses to embed an empty string ("400 INVALID_ARGUMENT ... Empty instances"),
# so Mem0 failed the whole batch and add.py skipped it after 6 retries.
# These three wrappers drop only items whose name is empty (or only spaces/underscores)
# before they are embedded. Every non-empty entity, relation and fact goes through unchanged.
import re as _re
import mem0.memory.kuzu_memory as _kuzu_mem
import mem0.memory.main as _mem_main


def _not_empty(s):
    return isinstance(s, str) and _re.sub(r"[\s_]", "", s) != ""


_orig_nodes = _kuzu_mem.MemoryGraph._retrieve_nodes_from_data
def _nodes_without_empty(self, data, filters):
    return {k: v for k, v in _orig_nodes(self, data, filters).items() if _not_empty(k)}
_kuzu_mem.MemoryGraph._retrieve_nodes_from_data = _nodes_without_empty

_orig_rels = _kuzu_mem.MemoryGraph._remove_spaces_from_entities
def _rels_without_empty(self, entity_list):
    return [r for r in _orig_rels(self, entity_list)
            if _not_empty(r.get("source")) and _not_empty(r.get("destination"))]
_kuzu_mem.MemoryGraph._remove_spaces_from_entities = _rels_without_empty

_orig_facts = _mem_main.normalize_facts
_mem_main.normalize_facts = lambda raw: [f for f in _orig_facts(raw) if _not_empty(f)]


# ---- Gemini guard, Neo4j part (added for Exp 4) -------------------------------
# Same idea as the guard above, for Mem0's Neo4j graph code (mem0.memory.graph_memory).
# Neo4j uses each relation name as a relationship TYPE in Cypher ([r:works_at]) without quotes,
# so a name with characters Cypher does not allow, or starting with a digit, breaks the whole batch.
# Such names are cleaned (bad characters -> "_", a leading digit gets "r_"); empty ones are dropped.
# Entity types are used as node labels: an empty type, or one with a backtick, becomes "entity".
def _cypher_rel(name):
    name = _re.sub(r"\W+", "_", name if isinstance(name, str) else "").strip("_")
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


# ---- Event log for the monitor (added for Exp 4) -------------------------------
# Writes one JSON line per add() call to <EVENTS_LOG>_<user_id>.jsonl when EVENTS_LOG is set.
# Logging only: the call, its arguments and its result are passed through unchanged.
import json as _json
import threading as _threading
import time as _time

_event_lock = _threading.Lock()


def _with_event_log(mem):
    prefix = os.getenv("EVENTS_LOG")
    if not prefix:
        return mem
    orig_add = mem.add

    def _write(rec):
        try:
            name = str(rec.get("user_id") or "unknown").replace("/", "_")
            with _event_lock, open(f"{prefix}_{name}.jsonl", "a") as f:
                f.write(_json.dumps(rec, default=str) + "\n")
        except Exception:
            pass  # the log must never break the experiment

    def add(messages, *args, **kwargs):
        rec = {"time": _time.strftime("%Y-%m-%d %H:%M:%S"), "user_id": kwargs.get("user_id"),
               "session_date": (kwargs.get("metadata") or {}).get("timestamp"), "messages": messages}
        t0 = _time.time()
        try:
            res = orig_add(messages, *args, **kwargs)
        except Exception as e:
            rec.update(seconds=round(_time.time() - t0, 2), error=f"{type(e).__name__}: {e}"[:500])
            _write(rec)
            raise
        rel = (res or {}).get("relations") or {}
        rec.update(seconds=round(_time.time() - t0, 2), memory_events=(res or {}).get("results"),
                   graph_added=rel.get("added_entities"), graph_deleted=rel.get("deleted_entities"))
        _write(rec)
        return res

    mem.add = add
    return mem


# ---- LLM call log for the monitor (added for Exp 4) ----------------------------
# Writes one JSON line per LLM call made by Mem0 to <LLM_LOG>_conv<N>.jsonl when LLM_LOG is set.
# Logging only: the call, its arguments and its answer are passed through unchanged.
def _with_llm_log(mem):
    prefix = os.getenv("LLM_LOG")
    if not prefix:
        return mem
    conv = os.getenv("START_CONV")
    path = f"{prefix}_conv{conv}.jsonl" if conv is not None else f"{prefix}_other.jsonl"

    def wrap(llm, role):
        if llm is None or getattr(llm, "_llm_logged", False):
            return
        orig = llm.generate_response

        def generate_response(*args, **kwargs):
            msgs = kwargs.get("messages", args[0] if args else None)
            tools = [t.get("function", {}).get("name") for t in (kwargs.get("tools") or []) if isinstance(t, dict)]
            rec = {"time": _time.strftime("%Y-%m-%d %H:%M:%S"), "thread": _threading.current_thread().name,
                   "llm": role, "tools": tools, "messages": msgs}
            t0 = _time.time()
            try:
                out = orig(*args, **kwargs)
                rec.update(seconds=round(_time.time() - t0, 2), response=out)
                return out
            except Exception as e:
                rec.update(seconds=round(_time.time() - t0, 2), error=f"{type(e).__name__}: {e}"[:500])
                raise
            finally:
                try:
                    with _event_lock, open(path, "a") as f:
                        f.write(_json.dumps(rec, default=str) + "\n")
                except Exception:
                    pass  # the log must never break the experiment

        llm.generate_response = generate_response
        llm._llm_logged = True

    wrap(getattr(mem, "llm", None), "memory")
    graph = getattr(mem, "graph", None)
    wrap(getattr(graph, "llm", None), "graph")
    return mem
