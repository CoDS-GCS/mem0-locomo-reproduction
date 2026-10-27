"""Exp 4: record every LLM call Mem0 makes (prompt in, answer out), so the monitor can show the exact
prompts and answers of each step. Run once, AFTER patch_events.py, from ~/mem0-repro/paper-eval-neo4j-gemini:
    python patch_llmlog.py

What it changes in src/memzero/config.py (nothing else):
  get_memory() also wraps generate_response() of Mem0's two LLM objects (the memory one and the graph one).
  When LLM_LOG is set in .env, each call appends one JSON line to <LLM_LOG>_conv<N>.jsonl (N = START_CONV,
  i.e. the conversation being added) or <LLM_LOG>_other.jsonl (search stage, smoke test) with: time, thread,
  which LLM object ("memory" or "graph"), the tool names offered, the full messages sent, the answer, seconds,
  or the error. Logging only: arguments and answers pass through unchanged. Without LLM_LOG nothing happens.
This is what shows the facts extracted, the ADD/UPDATE/DELETE/NONE decisions (including NONE) and the graph
steps. Expect roughly 150-250 MB of logs for the whole add stage.
"""
import pathlib
import sys

p = pathlib.Path("src/memzero/config.py")
s = p.read_text()
if "_with_llm_log" in s:
    sys.exit("already patched - nothing changed")
OLD = "    return _with_event_log(Memory.from_config(config))\n"
if s.count(OLD) != 1:
    sys.exit("STOP: run patch_events.py first (the event-log line was not found) - nothing changed")

ADD = '''

# ---- LLM call log for the monitor (added for Exp 4) ----------------------------
# Writes one JSON line per LLM call made by Mem0 to <LLM_LOG>_conv<N>.jsonl when LLM_LOG is set.
# Logging only: the call, its arguments and its answer are passed through unchanged.
def _with_llm_log(mem):
    prefix = os.getenv("LLM_LOG")
    if not prefix:
        return mem
    conv = os.getenv("START_CONV")
    path = f"{prefix}_conv{conv}.jsonl" if conv is not None else f"{prefix}_other.jsonl"

    def wrap(llm, role):
        if llm is None or getattr(llm, "_llm_logged", False):
            return
        orig = llm.generate_response

        def generate_response(*args, **kwargs):
            msgs = kwargs.get("messages", args[0] if args else None)
            tools = [t.get("function", {}).get("name") for t in (kwargs.get("tools") or []) if isinstance(t, dict)]
            rec = {"time": _time.strftime("%Y-%m-%d %H:%M:%S"), "thread": _threading.current_thread().name,
                   "llm": role, "tools": tools, "messages": msgs}
            t0 = _time.time()
            try:
                out = orig(*args, **kwargs)
                rec.update(seconds=round(_time.time() - t0, 2), response=out)
                return out
            except Exception as e:
                rec.update(seconds=round(_time.time() - t0, 2), error=f"{type(e).__name__}: {e}"[:500])
                raise
            finally:
                try:
                    with _event_lock, open(path, "a") as f:
                        f.write(_json.dumps(rec, default=str) + "\\n")
                except Exception:
                    pass  # the log must never break the experiment

        llm.generate_response = generate_response
        llm._llm_logged = True

    wrap(getattr(mem, "llm", None), "memory")
    graph = getattr(mem, "graph", None)
    wrap(getattr(graph, "llm", None), "graph")
    return mem
'''
s = s.replace(OLD, "    return _with_llm_log(_with_event_log(Memory.from_config(config)))\n") + ADD
p.write_text(s)
print("patched OK")
