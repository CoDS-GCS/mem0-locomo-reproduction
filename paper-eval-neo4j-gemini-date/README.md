# Exp 5: session date shown to Mem0's extractors

Exp 4's code (Mem0g, Gemini 2.5 Flash-Lite, Neo4j) with one change, in `src/memzero/add.py`: with `DATE_PREFIX=1` each turn is sent as `[today is 8 May, 2023] Caroline: I went to ...` instead of `Caroline: I went to ...`, so the session date reaches Mem0's fact and graph extractors. The Mem0 library itself is not modified. Changed vs Exp 4: session date shown in front of every turn (`EXPERIMENTS.md`).

## Setup vs the paper

| Parameter | This experiment (Exp 5) | Paper |
|---|---|---|
| Mem0 version | `mem0ai==1.0.11` (`requirements.txt`) | hosted platform (`EXPERIMENTS.md`) |
| LLM | Gemini 2.5 Flash-Lite via Vertex AI, temperature 0 (`src/memzero/config.py`, env `MODEL`) | GPT-4o-mini (`EXPERIMENTS.md`) |
| Embedding model / dims | `gemini-embedding-001`, 768 dims (`src/memzero/config.py`, env `EMBED_MODEL`/`EMBED_DIMS`) | not stated |
| Vector store | Qdrant, collection `locomo_gem_neo4j_date` (`env.example`, env `QDRANT_COLLECTION`) | not stated |
| Graph store | Neo4j, `GRAPH_STORE=neo4j`, `NEO4J_URL=bolt://localhost:7689` (`env.example`) | Neo4j (`EXPERIMENTS.md`) |
| Extraction instructions | authors' instructions, unchanged from Exp 4, reused as `custom_fact_extraction_prompt` (`src/memzero/config.py`) | authors' instructions, via the hosted platform; the paper itself prints no extraction prompt (`EXPERIMENTS.md`) |
| Top-k | 30 memories per speaker, `--top_k` default in `run_experiments.py` / `src/memzero/search.py` | not stated |
| Batch size | 2 turns per `add()` call, `batch_size=2` in `src/memzero/add.py` | not stated |
| Judge model | Gemini 2.5 Flash-Lite, `JUDGE_MODEL` env, default `MODEL` (`metrics/llm_judge.py`) | not stated |
| Judge runs | 10 (`results/mem0g_eval_run1..10.json`) | not stated |
| Session date shown to extractor | **Yes** — `DATE_PREFIX=1` (`env.example`); each turn prefixed `[today is <session date>]` in `src/memzero/add.py` (wording chosen by `prefix_test.py`, see `EXPERIMENTS.md` section 5) | not stated |

## Results

Source: `results/exp5_tables.txt` (10 judge runs, 1540 scored questions, categories 1-4; "Exp4 no date" columns are Exp 4's numbers for comparison).

| Question type | n | F1 | BLEU-1 | J (Exp 5) | J (Exp 4, no date) | J change | paper J |
|---|---|---|---|---|---|---|---|
| Single hop | 282 | 30.84 | 21.87 | 52.48 ± 0.00 | 53.19 | -0.71 | 65.71 ± 0.45 |
| Multi-hop | 96 | 11.63 | 9.40 | 28.12 ± 0.00 | 30.21 | -2.09 | 47.19 ± 0.67 |
| Open domain | 841 | 39.48 | 30.03 | 62.07 ± 0.00 | 60.76 | +1.31 | 75.71 ± 0.21 |
| Temporal | 321 | 51.63 | 43.28 | 68.22 ± 0.00 | 25.55 | +42.67 | 58.13 ± 0.44 |
| **Overall** | 1540 | 38.69 | 30.01 | **59.48 ± 0.00** | 50.13 | +9.35 | 68.44 ± 0.17 |

The Gemini judge gave identical scores in all 10 runs (± 0.00); per-run values: 59.48 × 10 (`results/exp5_tables.txt`).

Cost (ours / Exp 4 / paper): memory tokens per question 3998 / 3786 / 3616; search latency p50 1.730 s / 1.782 s / 0.476 s, p95 2.637 s / 2.664 s / 0.657 s; total latency p50 2.369 s / 2.431 s / 1.091 s, p95 4.063 s / 3.767 s / 2.590 s.

Questions that changed between Exp 4 and Exp 5 (judge run 1, `results/exp5_tables.txt`): single-hop 34 wrong→right / 36 right→wrong (net -2); multi-hop 7/9 (net -2); open domain 127/116 (net +11); temporal 153/16 (net +137).

## How to run

Environment: Exp 4's venv, `source ~/mem0-repro/paper-eval-neo4j-gemini/.venv-neo/bin/activate`, then `pip install -r requirements.txt`. Copy `env.example` to `.env` and fill in `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `NEO4J_PASSWORD` (names only; also sets `MODEL`, `JUDGE_MODEL`, `EMBED_MODEL`, `EMBED_DIMS`, `QDRANT_COLLECTION`, `MEM0_TELEMETRY`, `GRAPH_STORE`, `NEO4J_URL`, `NEO4J_USERNAME`, `EXTRACTION_PROMPT`, `DATE_PREFIX`, `EVENTS_LOG`, `LLM_LOG` — see `env.example`).

Services: Qdrant on `localhost:6333` (already running, shared with the other experiments); a dedicated Neo4j container for this experiment, started once with `bash start_neo4j_date.sh` (clones Exp 4's `neo4j-gem` image/settings onto a new container/ports/volume, not touching `neo4j-gem` itself).

1. **Smoke test** (checks the date-prefix code path before spending API calls): `python smoke_exp5.py` — must end with `SMOKE TEST PASSED`.
2. **Add**: `bash run_all_neo4j.sh` runs the full add → search → judge chain (`bash run_add_neo4j.sh [N]` alone also works, one conversation per process, crash-safe, three passes); progress logged to `logs/runner_n.log`.
3. **Search**: included in `run_all_neo4j.sh` (`bash run_search_neo4j.sh` alone), wraps `python run_experiments.py --technique_type mem0 --method search --is_graph`, retries until all 1,986 questions are answered.
4. **Evaluate**: included in `run_all_neo4j.sh` (`bash run_eval_neo4j.sh` alone), runs `python evals.py --input_file results/mem0_results_top_30_filter_False_graph_True.json --output_file results/mem0g_eval_run<k>.json` for k = 1..10.
5. **Scores**: `python report_exp5.py | tee results/exp5_tables.txt`.

### Scripts specific to this experiment
- `patch_exp5.py` — applies the one-line `DATE_PREFIX` change to `src/memzero/add.py`.
- `switch_to_today.py` — switches the date wording from `[1:56 pm on 8 May, 2023]` to `[today is 8 May, 2023]`.
- `prefix_test.py` — compares date wordings on 58 temporal questions (chose "today is"); `temporal_smoke.py`, `smoke_exp5.py` — pre-run smoke tests.
- `date_check.py`, `last_week_check.py`, `side_effects.py` — read-only checks of one conversation against Exp 4.
- `report_exp5.py` — result tables (Exp 5 vs Exp 4 vs paper).

Full rationale, the wording test results and held-out checks: `../EXPERIMENTS.md`, section 5.

## Credits

Code adapted from the `evaluation/` folder of [mem0ai/mem0](https://github.com/mem0ai/mem0) (Apache-2.0).
