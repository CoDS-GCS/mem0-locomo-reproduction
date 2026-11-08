# Exp 4: Mem0g with Gemini 2.5 Flash-Lite and Neo4j

Exp 2's code with one change: Neo4j (a second container) instead of Kuzu as the graph store, selected by `GRAPH_STORE=neo4j`. Changed vs Exp 2: graph store only (`EXPERIMENTS.md`).

## Setup vs the paper

| Parameter | This experiment (Exp 4) | Paper |
|---|---|---|
| Mem0 version | `mem0ai==1.0.11` (`requirements.txt`) | hosted platform (`EXPERIMENTS.md`) |
| LLM | Gemini 2.5 Flash-Lite via Vertex AI, temperature 0 (`src/memzero/config.py`, env `MODEL`) | GPT-4o-mini (`EXPERIMENTS.md`) |
| Embedding model / dims | `gemini-embedding-001`, 768 dims (`src/memzero/config.py`, env `EMBED_MODEL`/`EMBED_DIMS`) | not stated |
| Vector store | Qdrant, collection from env `QDRANT_COLLECTION` (default `locomo_gem_kuzu` in code, actually set to `locomo_gem_neo4j` for this experiment per `run_add_neo4j.sh`) (`src/memzero/config.py`) | not stated |
| Graph store | Neo4j, selected by env `GRAPH_STORE=neo4j`; connection from env `NEO4J_URL`/`NEO4J_USERNAME`/`NEO4J_PASSWORD` (`src/memzero/config.py`) | Neo4j (`EXPERIMENTS.md`) |
| Extraction instructions | authors' instructions, same as Exp 1/2, reused as `custom_fact_extraction_prompt` (`src/memzero/config.py`) | authors' instructions, via the hosted platform; the paper itself prints no extraction prompt (`EXPERIMENTS.md`) |
| Top-k | 30 memories per speaker, `--top_k` default in `run_experiments.py` / `src/memzero/search.py` | not stated |
| Batch size | 2 turns per `add()` call, `batch_size=2` in `src/memzero/add.py` | not stated |
| Judge model | Gemini 2.5 Flash-Lite, `JUDGE_MODEL` env, default `MODEL` (`metrics/llm_judge.py`) | not stated |
| Judge runs | 10 (`results/mem0g_eval_run1..10.json`) | not stated |
| Session date shown to extractor | No — only passed as metadata, same `add.py` logic as Exp 1/2 (changed in Exp 5) | not stated |

Note: `env.example` in this folder lists only the Exp 2 (Kuzu) variables; `GRAPH_STORE`, `NEO4J_URL`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` are read from the environment by `src/memzero/config.py` and `run_add_neo4j.sh` but are not listed there (names only, no values shown here).

## Results

Source: `results/mem0g_neo4j_tables.txt` (10 judge runs, 1540 scored questions, categories 1-4).

| Question type | n | F1 | BLEU-1 | J | paper J |
|---|---|---|---|---|---|
| Single hop | 282 | 31.08 | 21.95 | 53.19 ± 0.00 | 65.71 ± 0.45 |
| Multi-hop | 96 | 14.67 | 11.91 | 30.21 ± 0.00 | 47.19 ± 0.67 |
| Open domain | 841 | 37.40 | 28.82 | 60.76 ± 0.00 | 75.71 ± 0.21 |
| Temporal | 321 | 27.78 | 25.36 | 25.55 ± 0.00 | 58.13 ± 0.44 |
| **Overall** | 1540 | 32.82 | 25.79 | **50.13 ± 0.00** | 68.44 ± 0.17 |

The Gemini judge gave identical scores in all 10 runs (± 0.00); per-run values: 50.13 × 10 (`results/mem0g_neo4j_tables.txt`).

Cost (ours / paper): memory tokens per question 3786 / 3616; search latency p50 1.782 s / 0.476 s, p95 2.664 s / 0.657 s; total latency p50 2.431 s / 1.091 s, p95 3.767 s / 2.590 s.

## How to run

Environment: `source .venv-neo/bin/activate`, then `pip install -r requirements.txt`. Copy `env.example` to `.env` and fill in `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` (names only), plus (not in `env.example`, see note above) `GRAPH_STORE=neo4j`, `NEO4J_URL`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `QDRANT_COLLECTION`. Optional logging: `EVENTS_LOG`, `LLM_LOG` (names only; see `src/memzero/config.py`).

Services: Qdrant on `localhost:6333`; a Neo4j container reachable at `NEO4J_URL` (this experiment's own container, separate from Exp 1b's; see `EXPERIMENTS.md` section 4 for the container details) must already be running — this folder's scripts do not start it.

1. **Add**: `bash run_add_neo4j.sh` (all conversations) or `bash run_add_neo4j.sh 0` (one conversation) — wraps `python run_experiments.py --technique_type mem0 --method add --is_graph`, crash-safe, three passes; cleans the corresponding Qdrant points and Neo4j nodes before (re)building a conversation.
2. **Search**: `bash run_search_neo4j.sh` — wraps `python run_experiments.py --technique_type mem0 --method search --is_graph`, retries until all 1,986 questions are answered, then backs up to `results/mem0g_neo4j_search_BACKUP.json`.
3. **Evaluate**: `bash run_eval_neo4j.sh` — runs `python evals.py --input_file results/mem0_results_top_30_filter_False_graph_True.json --output_file results/mem0g_eval_run<k>.json` for k = 1..10, resuming from whichever runs already exist.
4. **Scores**: `python report_neo4j.py`.

`run_all_neo4j.sh` chains all of the above (conversation-0 test, a Qdrant/Neo4j sanity check, the remaining conversations, search, then the 10 judge runs).

## Credits

Code adapted from the `evaluation/` folder of [mem0ai/mem0](https://github.com/mem0ai/mem0) (Apache-2.0).
