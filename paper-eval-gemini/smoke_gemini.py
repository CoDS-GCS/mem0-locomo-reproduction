"""Quick check of the whole Gemini + Qdrant + Kuzu setup (costs a fraction of a cent).
Run from paper-eval-gemini:  python smoke_gemini.py
"""
import os
import shutil

os.environ["QDRANT_COLLECTION"] = "smoke_gem"
os.environ["KUZU_DB"] = "kuzu_db/smoke.kuzu"

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
print("Vertex AI:", os.getenv("GOOGLE_GENAI_USE_VERTEXAI"), "| project:", os.getenv("GOOGLE_CLOUD_PROJECT"),
      "| location:", os.getenv("GOOGLE_CLOUD_LOCATION"), "| model:", os.getenv("MODEL"))

client = genai.Client()
r = client.models.generate_content(model=os.getenv("MODEL"), contents="Reply with the single word OK.",
                                   config=types.GenerateContentConfig(temperature=0))
print("1. LLM answer:", (r.text or "").strip())

e = client.models.embed_content(model=os.getenv("EMBED_MODEL", "gemini-embedding-001"), contents="hello",
                                config=types.EmbedContentConfig(output_dimensionality=int(os.getenv("EMBED_DIMS", "768"))))
print("2. Embedding size:", len(e.embeddings[0].values))

from src.memzero.config import get_memory

os.makedirs("kuzu_db", exist_ok=True)
m = get_memory(is_graph=True)
res = m.add([{"role": "user", "content": "Caroline: I adopted a dog named Max last week and I love hiking with him."}],
            user_id="smoke_test", metadata={"timestamp": "1:56 pm on 8 May, 2023"})
print("3. Add result:", res)
s = m.search("What is the name of Caroline's dog?", user_id="smoke_test", limit=5)
print("4. Search memories:", [x["memory"] for x in s.get("results", [])])
print("   Graph relations:", s.get("relations"))
m.delete_all(user_id="smoke_test")

from qdrant_client import QdrantClient
QdrantClient("localhost", port=6333).delete_collection("smoke_gem")
print("Smoke test finished. If you see an answer, 768, memories and relations above, the setup works.")
