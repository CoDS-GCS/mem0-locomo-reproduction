# Exp 5: session date shown to Mem0's extractors

Mem0g on LOCOMO with Gemini 2.5 Flash-Lite and Neo4j (mem0ai 1.0.11, authors' instructions).
One change against Exp 4 (`../paper-eval-neo4j-gemini`), in `src/memzero/add.py`: with `DATE_PREFIX=1`
each turn is sent as `[today is 8 May, 2023] Caroline: I went to ...` instead of `Caroline: I went to ...`.
The Mem0 library is not modified. Settings, rationale, wording test and notes: `../EXPERIMENTS.md`, section 5.

Result (J %, 10 judge runs, 1540 questions): overall 59.48 (Exp 4: 50.13), temporal 68.22 (Exp 4: 25.55).
Full tables: `results/exp5_tables.txt`.

## Separate from Exp 4
- Qdrant collection `locomo_gem_neo4j_date`
- Neo4j container `neo4j-date` (bolt 7689, browser 7476), started with `bash start_neo4j_date.sh`
- Environment: Exp 4's `.venv-neo`
- `.env` (not in the repository) sets `QDRANT_COLLECTION=locomo_gem_neo4j_date`, `NEO4J_URL=bolt://localhost:7689`, `DATE_PREFIX=1`

## Run
    bash start_neo4j_date.sh        # once; Qdrant must be running
    python smoke_exp5.py            # must end with SMOKE TEST PASSED
    bash run_all_neo4j.sh           # add, search, 10 judge runs; log in logs/runner_n.log
    python report_exp5.py | tee results/exp5_tables.txt

## Scripts added for Exp 5
- `patch_exp5.py`: the one-line change in `src/memzero/add.py`
- `switch_to_today.py`: switches the wording from `[1:56 pm on 8 May, 2023]` to `[today is 8 May, 2023]`
- `prefix_test.py`: compares date wordings on 58 temporal questions (chose "today is")
- `temporal_smoke.py`, `smoke_exp5.py`: smoke tests before the full run
- `date_check.py`, `last_week_check.py`, `side_effects.py`: read-only checks of one conversation against Exp 4
- `report_exp5.py`: result tables (Exp 5 vs Exp 4 vs paper)

## Not in the repository
- `dataset/locomo10.json`: download it from the LOCOMO repository (snap-research/locomo, file `data/locomo10.json`) into `dataset/`.
- `logs/` and `results/*.gz` (raw search output) stay local; `results/mem0g_eval_run*.json` and `results/exp5_tables.txt` are included.
- `.env` is not committed: create it from `env.example` and set `QDRANT_COLLECTION`, `NEO4J_URL` and `DATE_PREFIX=1` as listed above.
- `src/langmem.py`, `src/rag.py`, `src/openai/` and `src/zep/` are the authors' other baselines; they are not used, but `run_experiments.py` imports them, so they are kept.

`README.md` in this folder is the authors' original evaluation README, unchanged.
