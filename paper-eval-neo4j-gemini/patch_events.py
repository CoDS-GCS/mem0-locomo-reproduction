"""Exp 4: record every memory operation in a log the monitor can read. Run once, from
~/mem0-repro/paper-eval-neo4j-gemini:   python patch_events.py

What it changes in src/memzero/config.py (nothing else):
  get_memory() wraps the Memory object's add() so that, when EVENTS_LOG is set in .env, each call
  appends one JSON line to <EVENTS_LOG>_<user_id>.jsonl with: the time, user, session date, the 2 messages,
  the memory events Mem0 returned (ADD / UPDATE with the previous text / DELETE) and the graph relations
  added and deleted. A failed call is logged with its error and then raised exactly as before.
  It only writes this log: what Mem0 does, and every result, stays the same. Without EVENTS_LOG nothing happens.
Note: Mem0 1.0.11 does not return NONE decisions (facts it decided to leave alone), so they are not in the log.
"""
import pathlib
import sys

p = pathlib.Path("src/memzero/config.py")
s = p.read_text()
if "_with_event_log" in s:
    sys.exit("already patched - nothing changed")
OLD = "    return Memory.from_config(config)\n"
if s.count(OLD) != 1:
    sys.exit("STOP: 'return Memory.from_config(config)' not found exactly once - nothing changed")

ADD = '''

# ---- Event log for the monitor (added for Exp 4) -------------------------------
# Writes one JSON line per add() call to <EVENTS_LOG>_<user_id>.jsonl when EVENTS_LOG is set.
# Logging only: the call, its arguments and its result are passed through unchanged.
import json as _json
import threading as _threading
import time as _time

_event_lock = _threading.Lock()


def _with_event_log(mem):
    prefix = os.getenv("EVENTS_LOG")
    if not prefix:
        return mem
    orig_add = mem.add

    def _write(rec):
        try:
            name = str(rec.get("user_id") or "unknown").replace("/", "_")
            with _event_lock, open(f"{prefix}_{name}.jsonl", "a") as f:
                f.write(_json.dumps(rec, default=str) + "\\n")
        except Exception:
            pass  # the log must never break the experiment

    def add(messages, *args, **kwargs):
        rec = {"time": _time.strftime("%Y-%m-%d %H:%M:%S"), "user_id": kwargs.get("user_id"),
               "session_date": (kwargs.get("metadata") or {}).get("timestamp"), "messages": messages}
        t0 = _time.time()
        try:
            res = orig_add(messages, *args, **kwargs)
        except Exception as e:
            rec.update(seconds=round(_time.time() - t0, 2), error=f"{type(e).__name__}: {e}"[:500])
            _write(rec)
            raise
        rel = (res or {}).get("relations") or {}
        rec.update(seconds=round(_time.time() - t0, 2), memory_events=(res or {}).get("results"),
                   graph_added=rel.get("added_entities"), graph_deleted=rel.get("deleted_entities"))
        _write(rec)
        return res

    mem.add = add
    return mem
'''
s = s.replace(OLD, "    return _with_event_log(Memory.from_config(config))\n") + ADD
p.write_text(s)
print("patched OK")
