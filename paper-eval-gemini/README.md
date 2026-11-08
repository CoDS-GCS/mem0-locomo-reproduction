# Exp 2: Mem0g with Gemini 2.5 Flash-Lite and Kuzu

Mem0g on LOCOMO with the LLM, embeddings and graph store swapped out: Gemini 2.5 Flash-Lite (Vertex AI) instead of GPT-4o-mini, and Kuzu (embedded graph) instead of Neo4j, on `mem0ai` 1.0.11. Changed vs Exp 1b: LLM, embeddings, graph store, mem0 version (`EXPERIMENTS.md`).

## Setup vs the paper

| Parameter | This experiment (Exp 2) | Paper |
|---|---|---|
| Mem0 version | `mem0ai==1.0.11` (`requirements.txt`) | hosted platform (`EXPERIMENTS.md`) |
| LLM | Gemini 2.5 Flash-Lite via Vertex AI, temperature 0 (`src/memzero/config.py`, env `MODEL`) | GPT-4o-mini (`EXPERIMENTS.md`) |
| Embedding model / dims | `gemini-embedding-001`, 768 dims (`src/memzero/config.py`, env `EMBED_MODEL`/`EMBED_DIMS`) | not stated |
| Vector store | Qdrant, collection `locomo_gem_kuzu` (`src/memzero/config.py`, env `QDRANT_COLLECTION`) | not stated |
| Graph store | Kuzu, embedded db at `kuzu_db/locomo_mem0g.kuzu` (`src/memzero/config.py`, env `KUZU_DB`) | Neo4j (`EXPERIMENTS.md`) |
| Extraction instructions | authors' instructions, same as Exp 1, reused as `custom_fact_extraction_prompt` (`src/memzero/config.py`) | authors' instructions, via the hosted platform; the paper itself prints no extraction prompt (`EXPERIMENTS.md`) |
| Top-k | 30 memories per speaker, `--top_k` default in `run_experiments.py` / `src/memzero/search.py` | not stated |
| Batch size | 2 turns per `add()` call, `batch_size=2` in `src/memzero/add.py` | not stated |
| Judge model | Gemini 2.5 Flash-Lite, `JUDGE_MODEL` env, default `MODEL` (`metrics/llm_judge.py`) | not stated |
| Judge runs | 10 (`results/mem0g_eval_run1..10.json`) | not stated |
| Session date shown to extractor | No — only passed as metadata, same `add.py` logic as Exp 1 | not stated |

## Results

Source: `results/mem0g_kuzu_tables.txt` (10 judge runs, 1540 scored questions, categories 1-4).

| Question type | n | F1 | BLEU-1 | J | paper J |
|---|---|---|---|---|---|
| Single hop | 282 | 30.99 | 21.30 | 54.96 ± 0.00 | 65.71 ± 0.45 |
| Multi-hop | 96 | 16.46 | 12.45 | 34.38 ± 0.00 | 47.19 ± 0.67 |
| Open domain | 841 | 37.82 | 28.79 | 60.17 ± 0.00 | 75.71 ± 0.21 |
| Temporal | 321 | 26.28 | 23.45 | 24.92 ± 0.00 | 58.13 ± 0.44 |
| **Overall** | 1540 | 32.83 | 25.29 | **50.26 ± 0.00** | 68.44 ± 0.17 |

The Gemini judge gave identical scores in all 10 runs (± 0.00); per-run values: 50.26 × 10 (`results/mem0g_kuzu_tables.txt`).

Cost (ours / paper): memory tokens per question 3776 / 3616; search latency p50 2.182 s / 0.476 s, p95 3.946 s / 0.657 s; total latency p50 2.918 s / 1.091 s, p95 6.071 s / 2.590 s.

## How to run

Environment: `source .venv-gem/bin/activate`, then `pip install -r requirements.txt`. Copy `env.example` to `.env` and fill in `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` (names only; also sets `GOOGLE_GENAI_USE_VERTEXAI`, `MODEL`, `JUDGE_MODEL`, `EMBED_MODEL`, `EMBED_DIMS`, `QDRANT_COLLECTION`, `KUZU_DB`, `MEM0_TELEMETRY`).

Services: Qdrant on `localhost:6333`. Kuzu is an embedded (on-disk) graph store — no separate container.

1. **Add**: `bash run_add_kuzu.sh` (all conversations) or `bash run_add_kuzu.sh 0` (one conversation) — wraps `python run_experiments.py --technique_type mem0 --method add --is_graph`, crash-safe, three passes.
2. **Search**: `bash run_search_kuzu.sh` — wraps `python run_experiments.py --technique_type mem0 --method search --is_graph`, retries until all 1,986 questions are answered, then backs up to `results/mem0g_kuzu_search_BACKUP.json`.
3. **Evaluate**: `bash run_eval_kuzu.sh` — runs `python evals.py --input_file results/mem0_results_top_30_filter_False_graph_True.json --output_file results/mem0g_eval_run<k>.json` for k = 1..10, resuming from whichever runs already exist.
4. **Scores**: `python report_kuzu.py`.

`run_all_kuzu.sh` chains all of the above (conversation-0 test, a Qdrant/Kuzu sanity check, the remaining conversations, search, then the 10 judge runs).

## Credits

Code adapted from the `evaluation/` folder of [mem0ai/mem0](https://github.com/mem0ai/mem0) (Apache-2.0).
