"""Quick check of the Exp 4 setup: Gemini + Qdrant + Neo4j (costs a fraction of a cent).
Run from ~/mem0-repro/paper-eval-neo4j-gemini with .venv-neo active and .env loaded:
    python smoke_neo4j.py
"""
import os

os.environ["QDRANT_COLLECTION"] = "smoke_gem_neo4j"

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
print("Vertex AI:", os.getenv("GOOGLE_GENAI_USE_VERTEXAI"), "| project:", os.getenv("GOOGLE_CLOUD_PROJECT"),
      "| location:", os.getenv("GOOGLE_CLOUD_LOCATION"), "| model:", os.getenv("MODEL"))
print("Graph store:", os.getenv("GRAPH_STORE"), "| Neo4j:", os.getenv("NEO4J_URL"),
      "| extraction prompt:", os.getenv("EXTRACTION_PROMPT", "paper (not set)"))

client = genai.Client()
r = client.models.generate_content(model=os.getenv("MODEL"), contents="Reply with the single word OK.",
                                   config=types.GenerateContentConfig(temperature=0))
print("1. LLM answer:", (r.text or "").strip())

from neo4j import GraphDatabase
drv = GraphDatabase.driver(os.environ["NEO4J_URL"], auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]))
with drv.session() as s:
    v = s.run("CALL dbms.components() YIELD name, versions RETURN name, versions[0] AS v").single()
print("2. Neo4j server:", v["name"], v["v"])

from src.memzero.config import get_memory

m = get_memory(is_graph=True)
print("3. Mem0 graph class:", type(m.graph).__module__, "| paper prompt in use:", bool(m.config.custom_fact_extraction_prompt))
res = m.add([{"role": "user", "content": "Caroline: I adopted a dog named Max last week and I love hiking with him."}],
            user_id="smoke_test", metadata={"timestamp": "1:56 pm on 8 May, 2023"})
print("4. Add result:", res)
s = m.search("What is the name of Caroline's dog?", user_id="smoke_test", limit=5)
print("5. Search memories:", [x["memory"] for x in s.get("results", [])])
print("   Graph relations:", s.get("relations"))
with drv.session() as ses:
    n = ses.run("MATCH (n) WHERE n.user_id = 'smoke_test' RETURN count(n) AS c").single()["c"]
print("6. Neo4j nodes for smoke_test before cleanup:", n)

m.delete_all(user_id="smoke_test")
with drv.session() as ses:
    ses.run("MATCH (n) WHERE n.user_id = 'smoke_test' DETACH DELETE n").consume()
drv.close()
from qdrant_client import QdrantClient
QdrantClient("localhost", port=6333).delete_collection("smoke_gem_neo4j")
print("Smoke test finished. You should see: OK, a Neo4j 5 version, mem0.memory.graph_memory, "
      "paper prompt True, memories, relations and a node count above 0.")
