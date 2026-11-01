# Mem0 / Mem0g on LOCOMO: reproduction

Reproduction of the LOCOMO results of the Mem0 paper (Chhikara et al. 2025, arXiv 2504.19413) with the authors' own evaluation code (Apache-2.0). The lab notebook is [`EXPERIMENTS.md`](EXPERIMENTS.md).

## Folders

| Folder | What it is | Environment |
|---|---|---|
| `paper-eval/` | **Exp 1** (1a Mem0, 1b Mem0g): GPT-4o-mini, mem0ai 0.1.93, Qdrant + Neo4j | `.venv312` |
| `paper-eval-gemini/` | **Exp 2**: Mem0g with Gemini 2.5 Flash-Lite (Vertex AI), mem0ai 1.0.11, Kuzu | `.venv-gem` |
| `paper-eval-neo4j-gemini/` | **Exp 4**: as Exp 2 but with Neo4j (second container) instead of Kuzu | `.venv-neo` |
| `paper-eval-neo4j-gemini-date/` | **Exp 5**: as Exp 4, with the session date shown to the extractor (`[today is <date>]` in front of every turn, `DATE_PREFIX=1`) | `.venv-neo` (Exp 4's) |
| `monitor/` | "Memory Journey": read-only web app to follow add / search / judge stages | own `requirements.txt` |
| `EXPERIMENTS.md` | lab notebook (settings, notes and known issues per experiment) | |
| `mem0-src/` | **not included**: clone of https://github.com/mem0ai/mem0.git at commit `d85fcda0378e3e2ba8772705b075049484bd8fa8` ("Formatting (#2750)", 2025-05-22) | |

Exp 3 (Mem0's built-in extraction prompt) is planned and has not been run yet; see `EXPERIMENTS.md`.

Each experiment folder holds `src/`, `metrics/`, `dataset/`, the runner scripts, patches, report scripts, `results/` (search outputs, 10 judge runs, result tables) and `logs/` (runner/add/search/eval logs, plus `events_*.jsonl` event logs for Exp 4). `requirements.txt` in each folder is a `pip freeze` of that experiment's environment.

## Results

LLM judge J (%), mean over 10 judge runs, 1540 scored questions (categories 1-4). "Paper" is the value printed in the paper. Copied from `results/*_tables*.txt` (`mem0_tables_v2.txt`, `mem0g_tables.txt`, `mem0g_kuzu_tables.txt`, `mem0g_neo4j_tables.txt`, `exp5_tables.txt`).

| Question type | n | 1a Mem0 (GPT) | Paper Mem0 | 1b Mem0g (GPT, Neo4j) | Paper Mem0g | 2 Mem0g (Gemini, Kuzu) | 4 Mem0g (Gemini, Neo4j) | 5 Mem0g (Gemini, Neo4j, date) |
|---|---|---|---|---|---|---|---|---|
| Single hop | 282 | 58.51 | 67.13 | 52.34 | 65.71 | 54.96 | 53.19 | 52.48 |
| Multi-hop | 96 | 41.88 | 51.15 | 44.79 | 47.19 | 34.38 | 30.21 | 28.12 |
| Open domain | 841 | 69.02 | 72.93 | 69.18 | 75.71 | 60.17 | 60.76 | 62.07 |
| Temporal | 321 | 18.54 | 55.51 | 18.63 | 58.13 | 24.92 | 25.55 | 68.22 |
| **Overall** | 1540 | **54.88** | 66.88 | **54.04** | 68.44 | **50.26** | **50.13** | **59.48** |

The Gemini judge gave identical scores in all 10 runs (± 0.00). F1, BLEU-1 and cost tables (tokens, latency) are in the `*_tables*.txt` files.

## How to run

Each experiment runs from its own folder with its own environment (`pip install -r requirements.txt`), a `.env` file and the Docker services it needs (Qdrant; Neo4j for Exp 1b and 4; Exp 2 uses embedded Kuzu).

1. **add** (store the conversations as memories): `bash run_add.sh` / `run_add_graph.sh` (Exp 1), `bash run_add_kuzu.sh` (Exp 2), `bash run_add_neo4j.sh` (Exp 4). Optional argument: one conversation number.
2. **search** (retrieve memories and answer the questions): `run_search_kuzu.sh`, `run_search_neo4j.sh`; Exp 1 uses `make run-mem0-search` / `make run-mem0-plus-search`.
3. **evaluate** (LLM judge, 10 runs): `run_eval_kuzu.sh`, `run_eval_neo4j.sh`; Exp 1 uses `python evals.py --input_file results/mem0_results_top_30_filter_False_graph_<False|True>.json --output_file results/<mem0|mem0g>_eval_run<k>.json` (needs `OPENAI_API_KEY` in the environment, e.g. `set -a; source .env; set +a`), repeated for k = 1..10.
4. **report** (result tables): `python report_all.py --system mem0` and `--system mem0g` (Exp 1; `report.py` is the earlier Mem0-only version), `report_kuzu.py` (Exp 2), `report_neo4j.py` (Exp 4), `report_exp5.py` (Exp 5).

Exp 5 is run like Exp 4 (`run_all_neo4j.sh`, `report_exp5.py`) from its own folder, with `DATE_PREFIX=1` in its `.env`; see `paper-eval-neo4j-gemini-date/README_exp5.md`.

`run_all_kuzu.sh` and `run_all_neo4j.sh` chain all four stages. The monitor starts with `monitor/run.sh [experiment-folder] [port]`.

## Not included

- `.env` files (API keys, passwords). Copy `env.example` to `.env` in each experiment folder and fill it in.
- The LLM call logs (`logs/llm_*`), the virtual environments, the Kuzu database, backups and abandoned-pass logs.
- `mem0-src/` (see above).
- Exp 5: `logs/`, `dataset/` and `results/*.gz` stay local (see `.gitignore`).
- The four search-result files over 50 MB (`results/mem0_results_top_30_*.json`) are committed gzipped as `.json.gz`; use `gunzip -k` to restore them.

## Dataset

The LOCOMO dataset (`dataset/locomo10.json`) is included for internal use in this private repository. Its license must be checked before the repository is ever made public.
