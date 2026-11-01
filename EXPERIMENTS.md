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
| 5 | 29 Oct 2026 | paper-eval-neo4j-gemini-date | Mem0g | Gemini 2.5 Flash-Lite | Neo4j | 1.0.11 | authors' instructions | 4: session date shown in front of every turn as "[today is <date>]" (DATE_PREFIX=1) | 59.48 ± 0.00 | 68.22 |
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

### 5 (paper-eval-neo4j-gemini-date, uses Exp 4's venv .venv-neo)
- Exp 4's folder copied without logs/ and results/. One change, in `src/memzero/add.py`: with DATE_PREFIX=1 each turn is sent as "[<session date>] Name: text" instead of "Name: text" (e.g. "[1:56 pm on 8 May, 2023] Caroline: I went to a LGBTQ support group yesterday ..."). The rest of `src/` is identical to Exp 4 (checked with a file comparison at setup).
- Why: Mem0 1.0.11 builds the fact-extractor input only from the message text (`parse_messages`, mem0/memory/main.py lines 513-517) and the graph-extractor input only from the message text (main.py line 714). The session date was passed only as metadata, so neither extractor ever saw it, while the authors' instructions ask for exact dates. The update step (ADD/UPDATE/DELETE/NONE) sees only the extracted facts, so it gets the date through them.
- Storage kept apart from Exp 4: Qdrant collection `locomo_gem_neo4j_date`; third Neo4j container `neo4j-date` (ports 7476/7689), same image and settings as `neo4j-gem`.
- Unchanged: mem0ai 1.0.11, the authors' instructions, Mem0's update prompt, the empty-name guard, event and LLM logs, search, answer and judge prompts, models, top-30, 2 turns per add(), 10 judge runs.
- Smoke test (`smoke_exp5.py`) checked that the real add.py code builds Exp 4's exact text with DATE_PREFIX=0 and the dated text with 1, and that the date appears in both extractor inputs in the LLM log.
- Wording of the date, chosen before the full run with `prefix_test.py`: Mem0's fact extractor (authors' instructions, called exactly as Mem0 calls it) on the 58 LOCOMO temporal questions of conversations 0-2 whose evidence says "yesterday", "last week", "last Friday", "two weeks ago", "last month" or "last year". Label of the best fact about the event (CORRECT = the date the phrase really means; KEPT = phrase kept, computable from the memory timestamp; SESSION = event put on the session day):

  | wording | CORRECT | KEPT | SESSION | WRONG | LOST | no fact |
  |---|---|---|---|---|---|---|
  | none (= Exp 4) | 0 | 29 | 0 | 13 | 5 | 11 |
  | `[1:56 pm on 8 May, 2023]` | 19 | 15 | 12 | 1 | 2 | 9 |
  | `[sent on 8 May, 2023 at 1:56 pm]` | 23 | 20 | 5 | 0 | 1 | 9 |
  | `[today is 8 May, 2023]` (chosen) | 35 | 9 | 3 | 2 | 0 | 9 |

  One run per wording; conversation 0 was first added with the `[1:56 pm on 8 May, 2023]` wording (pilot) and then redone with the chosen one. "today is" mirrors Mem0's own default extraction prompt ("Today's date is ..."), with the conversation's date instead of the computer's clock.

- Results (30 Oct 2026): overall J 59.48 ± 0.00 (Exp 4: 50.13); single-hop 52.48, multi-hop 28.12, open-domain 62.07, temporal 68.22 (Exp 4: 53.19, 30.21, 60.76, 25.55). F1/BLEU-1 temporal 51.63/43.28 (Exp 4: 27.78/25.36; paper 51.55/40.28); overall 38.69/30.01. Memory tokens 3,998; search 1.730/2.637 s, total 2.369/4.063 s (p50/p95). Judge run 1, Exp 4 -> Exp 5: temporal +153/-16; single-hop +34/-36, multi-hop +7/-9, open-domain +127/-116.
- Held-out check (wording chosen on conversations 0-2): temporal J on conversations 3-9 28.1 -> 66.7 (0-2: 18.9 -> 72.2); other categories within about ±4 points in both groups.
- Conversation 0 with the final wording: 292 of 337 memories carry an explicit date (Exp 4: 61 of 316); dates more than 60 days from the memory's own session 35 -> 5. Of 63 facts about events told with a relative expression: 38 correct date, 17 phrase kept or told-date, 6 event on the session day, 2 lost or wrong (last_week_check.py). Graph: 2 date nodes copied from the prefix.
- Graph-rule check (temporal_smoke.py, 8 cases, before the run): a date rule for the graph step via graph_store.custom_prompt gave no benefit (no relative-word graph nodes either way) and split person nodes more often ("user_id:" form in 5 of 8 cases vs 2 of 8), so it was not used.
- Run: conversation 0 stalled once (network) and was rebuilt; no batch skipped after retries; 16 batches with malformed LLM output skipped by Mem0 (10 in conversation 2). Add 22:25-03:07, search 1 h 50 min, judge about 1 h.
- Repository: logs/, dataset/ and results/*.gz stay local (see .gitignore).
