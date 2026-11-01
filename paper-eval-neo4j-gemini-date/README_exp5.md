# Exp 5: show the session date to Mem0's extractors

One change against Exp 4, in our evaluation code `src/memzero/add.py` (not in the Mem0 library):
each turn is sent as `[today is 8 May, 2023] Caroline: I went to ...` instead of `Caroline: I went to ...`.
Mem0 builds both extractor inputs (facts and graph) from the message text only, so now both see the date.
Everything else is Exp 4: mem0ai 1.0.11, authors' instructions, Gemini, Neo4j, top-30, 2 turns per add, 10 judge runs.

New folder `~/mem0-repro/paper-eval-neo4j-gemini-date`, new Qdrant collection `locomo_gem_neo4j_date`,
new Neo4j container `neo4j-date` (ports 7476 / 7689). Exp 4's folder, collection and container are not touched.

## Steps (type one block at a time, wait for it to finish)

1. Unzip the kit
   ```
   cd ~/mem0-repro
   unzip ~/Downloads/exp5_kit.zip
   ```
2. Setup (prints every change it makes)
   ```
   python3 ~/mem0-repro/exp5_kit/setup_exp5.py
   ```
3. Start the Exp 5 Neo4j (Qdrant must be running: `docker ps` shows it)
   ```
   bash ~/mem0-repro/paper-eval-neo4j-gemini-date/start_neo4j_date.sh
   ```
4. Smoke test (must end with `SMOKE TEST PASSED`)
   ```
   cd ~/mem0-repro/paper-eval-neo4j-gemini-date
   source ~/mem0-repro/paper-eval-neo4j-gemini/.venv-neo/bin/activate
   python smoke_exp5.py
   ```
5. Start the overnight run in tmux: first `tmux new -s exp5` alone, then inside it
   ```
   cd ~/mem0-repro/paper-eval-neo4j-gemini-date && bash run_all_neo4j.sh
   ```
   Leave tmux with `Ctrl+b` then `d`. Come back with `tmux attach -t exp5`.
6. Watch from any terminal
   ```
   tail -f ~/mem0-repro/paper-eval-neo4j-gemini-date/logs/runner_n.log
   ```
7. When conversation 0 is done (about 40 min, `ls ~/mem0-repro/paper-eval-neo4j-gemini-date/logs/n_done_*` shows `n_done_0`):
   ```
   cd ~/mem0-repro/paper-eval-neo4j-gemini-date
   source ~/mem0-repro/paper-eval-neo4j-gemini/.venv-neo/bin/activate
   python date_check.py 0
   ```
   and the monitor: `bash ~/mem0-repro/monitor/run.sh ~/mem0-repro/paper-eval-neo4j-gemini-date 8733`, open http://127.0.0.1:8733
8. Next morning (runner_n.log ends with `CHAIN END: 10/10 judge runs`)
   ```
   python report_exp5.py | tee results/exp5_tables.txt
   ```

## If something goes wrong
- Stop the run: `tmux attach -t exp5`, `Ctrl+c`, then `pkill -f run_experiments.py`
- A Google credentials error: `gcloud auth application-default login`, then start again
- Any `STOP:` or `FAIL` line: nothing more happens; check the message
