# Exp 1a / 1b: Mem0 and Mem0g on GPT-4o-mini (closest public release to the paper)

Reproduces the paper's Mem0 (1a) and Mem0g (1b) runs with the authors' own evaluation code, the open-source `mem0ai` 0.1.93 release (April 2025, the version closest in time to the paper), GPT-4o-mini and Qdrant + Neo4j in Docker.

## Setup vs the paper

| Parameter | This experiment (1a / 1b) | Paper |
|---|---|---|
| Mem0 version | `mem0ai==0.1.93` (`requirements.txt`) | hosted platform (`EXPERIMENTS.md`) |
| LLM | GPT-4o-mini, temperature 0 (`src/memzero/config.py`) | GPT-4o-mini (`EXPERIMENTS.md`) |
| Embedding model / dims | OpenAI `text-embedding-3-small`, dims not set in config, i.e. the provider default (`src/memzero/config.py`) | not stated |
| Vector store | Qdrant, collections `locomo_mem0` / `locomo_mem0g` (`src/memzero/config.py`) | not stated |
| Graph store | none (1a) / Neo4j (1b) (`src/memzero/config.py`) | none (Mem0) / Neo4j (Mem0g) (`EXPERIMENTS.md`) |
| Extraction instructions | authors' `custom_instructions` in `src/memzero/add.py`, reused as `custom_fact_extraction_prompt` in `src/memzero/config.py`, plus one line asking for the JSON format the library expects | authors' instructions, via the hosted platform; the paper itself prints no extraction prompt (`EXPERIMENTS.md`) |
| Top-k | 30 memories per speaker, `--top_k` default in `run_experiments.py` / `src/memzero/search.py` | not stated |
| Batch size | 2 turns per `add()` call, `batch_size=2` in `src/memzero/add.py` | not stated |
| Judge model | GPT-4o-mini, `metrics/llm_judge.py` (authors' own evaluation code) | not stated |
| Judge runs | 10 (`results/mem0_eval_run1..10.json`, `results/mem0g_eval_run1..10.json`) | not stated |
| Session date shown to extractor | No — only passed as `metadata={"timestamp": ...}` in `add_memories_for_speaker` (`src/memzero/add.py`); the extractor never sees it (`EXPERIMENTS.md`, note on temporal collapse) | not stated |

## Results

LLM judge J (%), F1 and BLEU-1, mean over 10 judge runs, 1540 scored questions (categories 1-4). Source: `results/mem0_tables_v2.txt` (Mem0, 1a) and `results/mem0g_tables.txt` (Mem0g, 1b).

### 1a — Mem0 (`results/mem0_tables_v2.txt`)

| Question type | n | F1 | paper F1 | BLEU-1 | paper BLEU-1 | J | paper J |
|---|---|---|---|---|---|---|---|
| Single hop | 282 | 33.44 | 38.72 | 24.01 | 27.13 | 58.51 ± 0.57 | 67.13 ± 0.65 |
| Multi-hop | 96 | 22.98 | 28.64 | 17.24 | 21.58 | 41.88 ± 0.42 | 51.15 ± 0.31 |
| Open domain | 841 | 41.30 | 47.65 | 33.40 | 38.72 | 69.02 ± 0.19 | 72.93 ± 0.11 |
| Temporal | 321 | 28.69 | 48.93 | 27.91 | 40.51 | 18.54 ± 0.16 | 55.51 ± 0.34 |
| **Overall** | 1540 | 36.09 | — | 29.53 | — | **54.88 ± 0.13** | 66.88 ± 0.15 |

Cost (ours / paper): memory tokens per question 5473 / 1764; search latency p50 0.532 s / 0.148 s, p95 0.701 s / 0.200 s; total latency p50 1.346 s / 0.708 s, p95 2.547 s / 1.440 s.

### 1b — Mem0g (`results/mem0g_tables.txt`)

| Question type | n | F1 | paper F1 | BLEU-1 | paper BLEU-1 | J | paper J |
|---|---|---|---|---|---|---|---|
| Single hop | 282 | 31.13 | 38.09 | 22.25 | 26.03 | 52.34 ± 0.43 | 65.71 ± 0.45 |
| Multi-hop | 96 | 22.57 | 24.32 | 17.52 | 18.82 | 44.79 ± 0.00 | 47.19 ± 0.67 |
| Open domain | 841 | 39.55 | 49.27 | 31.42 | 40.30 | 69.18 ± 0.17 | 75.71 ± 0.21 |
| Temporal | 321 | 28.43 | 51.55 | 27.99 | 40.28 | 18.63 ± 0.12 | 58.13 ± 0.44 |
| **Overall** | 1540 | 34.63 | — | 28.16 | — | **54.04 ± 0.14** | 68.44 ± 0.17 |

Cost (ours / paper): memory tokens per question 5762 / 3616; search latency p50 4.410 s / 0.476 s, p95 6.927 s / 0.657 s; total latency p50 5.242 s / 1.091 s, p95 7.848 s / 2.590 s.

## How to run

Environment: `source ../.venv312/bin/activate`, then `pip install -r requirements.txt`. Copy `env.example` to `.env` and fill in `OPENAI_API_KEY`, `MODEL`, `NEO4J_PASSWORD` (names only, see `env.example`).

Services: Qdrant on `localhost:6333`; Neo4j on `bolt://localhost:7687` for the graph (1b) runs.

1. **Add** (store conversations as memories):
   - `bash run_add.sh` (Mem0, 1a) — wraps `python run_experiments.py --technique_type mem0 --method add`, one conversation per process, crash-safe, three passes.
   - `bash run_add_graph.sh` (Mem0g, 1b) — same idea with `--is_graph`.
2. **Search** (retrieve memories, answer questions):
   - `make run-mem0-search` → `python run_experiments.py --technique_type mem0 --method search --output_folder results/ --top_k 30`
   - `make run-mem0-plus-search` → same with `--is_graph`
3. **Evaluate** (LLM judge, repeat for k = 1..10):
   - `set -a; source .env; set +a` (needs `OPENAI_API_KEY` in the environment)
   - `python evals.py --input_file results/mem0_results_top_30_filter_False_graph_False.json --output_file results/mem0_eval_run<k>.json` (Mem0)
   - `python evals.py --input_file results/mem0_results_top_30_filter_False_graph_True.json --output_file results/mem0g_eval_run<k>.json` (Mem0g)
4. **Scores** (result tables): `python report_all.py --system mem0` and `python report_all.py --system mem0g` (`report.py` is the earlier Mem0-only version).

## Credits

Code adapted from the `evaluation/` folder of [mem0ai/mem0](https://github.com/mem0ai/mem0) (Apache-2.0).
