# Lab notebook: reproducing Mem0 / Mem0g on LOCOMO

Paper: Chhikara et al. 2025, "Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory", arXiv 2504.19413.
Evaluation code: the authors' own (`evaluation/` folder of the mem0 repository; original copy kept in `mem0-src/`).
Data: LOCOMO, 10 conversations, 1,986 questions; categories 1-4 scored (1,540), category 5 (adversarial) excluded as in the paper.

Rule: a finished experiment is frozen. New ideas become new experiments, each changing one thing at a time.

## Overview

| Exp | Date | Folder | System | LLM (memory, answers, judge) | Graph | mem0ai | Extraction prompt | Changed vs | Overall J | Temporal J |
|---|---|---|---|---|---|---|---|---|---|---|
| paper | 2025 | - | Mem0 | GPT-4o-mini | - | hosted platform | authors' instructions (via platform) | - | 66.88 ± 0.15 | 55.51 |
| paper | 2025 | - | Mem0g | GPT-4o-mini | Neo4j | hosted platform | authors' instructions (via platform) | - | 68.44 ± 0.17 | 58.13 |
| 1a | mid-Oct 2026 | paper-eval | Mem0 | GPT-4o-mini | - | 0.1.93 | authors' instructions | paper | 54.88 ± 0.13 | 18.54 |
| 1b | mid-Oct 2026 | paper-eval | Mem0g | GPT-4o-mini | Neo4j | 0.1.93 | authors' instructions | paper | 54.04 ± 0.14 | 18.63 |
| 2 | 21 Oct 2026 | paper-eval-gemini | Mem0g | Gemini 2.5 Flash-Lite | Kuzu | 1.0.11 | authors' instructions | 1b: LLM, embeddings, graph store, mem0 version | 50.26 ± 0.00 | 24.92 |
| 4 | 21-22 Oct 2026 | paper-eval-neo4j-gemini | Mem0g | Gemini 2.5 Flash-Lite | Neo4j | 1.0.11 | authors' instructions | 2: graph store only | 50.13 ± 0.00 | 25.55 |
| 5 | | paper-eval-gemini | Mem0g | Gemini 2.5 Flash-Lite | Kuzu | 1.0.11 | authors' instructions + session date shown | 2: date shown to the extractor | | |
| 3 (optional) | | | Mem0g | Gemini 2.5 Flash-Lite | Kuzu | 1.0.11 | Mem0's built-in user prompt (+ authors' instructions?) | 2: prompt | | |

± is the standard deviation over 10 judge runs, dividing by 10.

## Shared settings (all our runs)

- Top-30 memories retrieved per speaker (60 per question), 2 turns per `add()` call, session date stored as metadata.
- The authors' answer prompt (`prompts.py`, ANSWER_PROMPT_GRAPH for Mem0g) and judge prompt (`metrics/llm_judge.py`, ACCURACY_PROMPT), word for word.
- 10 judge runs; F1 and BLEU-1 from run 1.
- "Authors' instructions" = `custom_instructions` in the authors' `src/memzero/add.py`, used word for word as `custom_fact_extraction_prompt`, plus one line asking for the JSON format the open-source library expects. The paper itself prints no extraction prompt.

## Notes per experiment

### 1a / 1b (paper-eval, venv ~/mem0-repro/.venv312)
- Closest public release to the paper (April 2025). Qdrant + Neo4j in Docker.
- `delete_all` in 0.1.93 removes only 100 memories, so each conversation was cleaned explicitly.
- Mem0g: the graph step sometimes got a relation with a missing field (KeyError); such batches were skipped after 3 retries. Conversations 2 and 8 were wiped by a runner bug and redone.
- Temporal collapse: the extractor never sees the session date, yet the instructions ask for exact dates, so it invents them (57% of memories carry a year, 31% of those wrong).

### 2 (paper-eval-gemini, venv .venv-gem)
- Gemini through Vertex AI (Google Cloud credits), `gemini-embedding-001` with 768 dims, Kuzu 0.11.3 embedded graph.
- Gemini sometimes returns empty entity names; Vertex rejects empty text ("400 Empty instances"). Fixed with the empty-name guard at the bottom of `src/memzero/config.py` (drops empty names only).
- After the fix: 0 skipped batches, 9 batches with malformed LLM output (skipped by Mem0 itself), conversation 1 stalled once and was rebuilt.
- The Gemini judge gave identical scores in all 10 runs (± 0.00).
- Add 5.5 h, search about 3 h, judge about 1.5 h.

### 4 (paper-eval-neo4j-gemini, venv .venv-neo)
- Exp 2's code with one change: Neo4j (second container `neo4j-gem`, ports 7475/7688) instead of Kuzu, selected by GRAPH_STORE=neo4j.
- Guard extended to Mem0's Neo4j code: relation names Cypher cannot use as a relationship type are cleaned, empty ones dropped.
- Known library difference: Mem0 1.0.11's Neo4j search returns at most 5 relations per speaker (n=5 hard-coded); its Kuzu search passes the limit (30).
- Event log (logging only, no effect on results): with EVENTS_LOG=logs/events, every add() call is written to logs/events_<user>.jsonl (messages, ADD/UPDATE/DELETE events, graph relations added/deleted, errors). NONE decisions are not returned by Mem0 1.0.11, so they are not logged.
- LLM call log (logging only, no effect on results): with LLM_LOG=logs/llm, every prompt Mem0 sends and every answer it gets back is written to logs/llm_conv<N>.jsonl (search stage: logs/llm_other.jsonl). This shows the facts extracted, all ADD/UPDATE/DELETE/NONE decisions and the graph steps.
- Result (J per category, from `results/mem0g_neo4j_tables.txt`): single hop 53.19, multi-hop 30.21, open domain 60.76, temporal 25.55, overall 50.13 ± 0.00.
