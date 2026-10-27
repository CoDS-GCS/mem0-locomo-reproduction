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
    if is_graph:
        config["graph_store"] = {
            "provider": "kuzu",
            "config": {"db": os.getenv("KUZU_DB", "kuzu_db/locomo_mem0g.kuzu")},
        }
    return Memory.from_config(config)


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
