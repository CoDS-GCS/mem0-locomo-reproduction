"""LLM judge on Gemini (Vertex AI). The prompt is the paper's, unchanged; only the model call differs."""
import json
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

from mem0.memory.utils import extract_json

load_dotenv()
client = genai.Client()  # Vertex AI via GOOGLE_GENAI_USE_VERTEXAI / GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION
JUDGE_MODEL = os.getenv("JUDGE_MODEL", os.getenv("MODEL", "gemini-2.5-flash-lite"))

ACCURACY_PROMPT = """
Your task is to label an answer to a question as ’CORRECT’ or ’WRONG’. You will be given the following data:
    (1) a question (posed by one user to another user), 
    (2) a ’gold’ (ground truth) answer, 
    (3) a generated answer
which you will score as CORRECT/WRONG.

The point of the question is to ask about something one user should know about the other user based on their prior conversations.
The gold answer will usually be a concise and short answer that includes the referenced topic, for example:
Question: Do you remember what I got the last time I went to Hawaii?
Gold answer: A shell necklace
The generated answer might be much longer, but you should be generous with your grading - as long as it touches on the same topic as the gold answer, it should be counted as CORRECT. 

For time related questions, the gold answer will be a specific date, month, year, etc. The generated answer might be much longer or use relative time references (like "last Tuesday" or "next month"), but you should be generous with your grading - as long as it refers to the same date or time period as the gold answer, it should be counted as CORRECT. Even if the format differs (e.g., "May 7th" vs "7 May"), consider it CORRECT if it's the same date.

Now it's time for the real question:
Question: {question}
Gold answer: {gold_answer}
Generated answer: {generated_answer}

First, provide a short (one sentence) explanation of your reasoning, then finish with CORRECT or WRONG. 
Do NOT include both CORRECT and WRONG in your response, or it will break the evaluation script.

Just return the label CORRECT or WRONG in a json format with the key as "label".
"""


def evaluate_llm_judge(question, gold_answer, generated_answer, tries=8):
    """Return 1 if the judge says CORRECT, else 0. Retries with backoff on rate limits or network errors."""
    prompt = ACCURACY_PROMPT.format(question=question, gold_answer=gold_answer, generated_answer=generated_answer)
    for attempt in range(tries):
        try:
            response = client.models.generate_content(
                model=JUDGE_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json"),
            )
            label = json.loads(extract_json(response.text or ""))["label"]
            return 1 if label == "CORRECT" else 0
        except Exception as e:
            if attempt == tries - 1:
                raise
            wait = min(120, 2 ** (attempt + 1))
            print(f"[judge retry] {type(e).__name__}: {str(e)[:100]} -> sleeping {wait}s", flush=True)
            time.sleep(wait)
