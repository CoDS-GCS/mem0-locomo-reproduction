import os

from dotenv import load_dotenv

from mem0 import Memory

load_dotenv()


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
    config = {
        "llm": {
            "provider": "openai",
            "config": {"model": "gpt-4o-mini", "temperature": 0},
        },
        "embedder": {
            "provider": "openai",
            "config": {"model": "text-embedding-3-small"},
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "host": "localhost",
                "port": 6333,
                "collection_name": "locomo_mem0g" if is_graph else "locomo_mem0",
            },
        },
        "version": "v1.1",
        "custom_fact_extraction_prompt": custom_fact_extraction_prompt,
    }
    if is_graph:
        config["graph_store"] = {
            "provider": "neo4j",
            "config": {
                "url": "bolt://localhost:7687",
                "username": "neo4j",
                "password": os.getenv("NEO4J_PASSWORD"),
            },
        }
    return Memory.from_config(config)
