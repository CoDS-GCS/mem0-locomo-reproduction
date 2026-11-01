"""Exp 5 patch for src/memzero/add.py: show the session date to Mem0's extractors.

setup_exp5.py runs this for you on the Exp 5 copy. To run it by hand (only in the Exp 5 folder):
    cd ~/mem0-repro/paper-eval-neo4j-gemini-date && python3 patch_exp5.py

What it changes (nothing else, and nothing in the Mem0 library):
  1. one new line right after  timestamp = conversation[date_time_key] :
         date_prefix = f"[{timestamp}] " if os.getenv("DATE_PREFIX", "0") == "1" else ""
  2. the 4 lines that build the message text, e.g.
         f"{speaker_a}: {chat['text']}"   ->   f"{date_prefix}{speaker_a}: {chat['text']}"
So with DATE_PREFIX=1 a turn is sent as
         "[1:56 pm on 8 May, 2023] Caroline: I went to a LGBTQ support group yesterday ..."
and with DATE_PREFIX unset or 0 the text is exactly what Exp 4 sent ("Caroline: I went ...").

Why this reaches the extractors: Mem0 1.0.11 builds the fact-extractor input only from the message
text (parse_messages, mem0/memory/main.py lines 513-517) and the graph input only from the message
text (main.py line 714). The metadata timestamp is stored, but never shown to either of them.
"""
import pathlib
import re
import sys

A_OLD = "f\"{speaker_a}: {chat['text']}\""
B_OLD = "f\"{speaker_b}: {chat['text']}\""
A_NEW = "f\"{date_prefix}{speaker_a}: {chat['text']}\""
B_NEW = "f\"{date_prefix}{speaker_b}: {chat['text']}\""
ANCHOR = "timestamp = conversation[date_time_key]"


def patch(path="src/memzero/add.py", dry_run=False):
    """Returns 'patched', 'already patched' or raises SystemExit (file untouched) if add.py looks different."""
    p = pathlib.Path(path)
    s = p.read_text()
    if "DATE_PREFIX" in s:
        return "already patched"
    problems = []
    if s.count(A_OLD) != 2:
        problems.append(f"speaker_a message text found {s.count(A_OLD)} times (expected 2)")
    if s.count(B_OLD) != 2:
        problems.append(f"speaker_b message text found {s.count(B_OLD)} times (expected 2)")
    lines = s.split("\n")
    idx = [i for i, l in enumerate(lines) if l.strip() == ANCHOR]
    if len(idx) != 1:
        problems.append(f"line '{ANCHOR}' found {len(idx)} times (expected 1)")
    if not re.search(r"^import os\s*$", s, re.M):
        problems.append("'import os' not found")
    if problems:
        raise SystemExit("STOP: add.py does not look like the one we expected - NOTHING was changed.\n  - "
                         + "\n  - ".join(problems) + f"\nCheck this message and the file {p}.")
    i = idx[0]
    ind = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
    lines[i + 1:i + 1] = [
        ind + "# Exp 5: with DATE_PREFIX=1 every turn starts with its session date, e.g.",
        ind + "# \"[1:56 pm on 8 May, 2023] Caroline: ...\", so Mem0's fact and graph extractors see it.",
        ind + "date_prefix = f\"[{timestamp}] \" if os.getenv(\"DATE_PREFIX\", \"0\") == \"1\" else \"\"",
    ]
    s2 = "\n".join(lines).replace(A_OLD, A_NEW).replace(B_OLD, B_NEW)
    compile(s2, str(p), "exec")  # must still be valid Python
    if not dry_run:
        p.write_text(s2)
    return "patched"


if __name__ == "__main__":
    if pathlib.Path.cwd().name != "paper-eval-neo4j-gemini-date":
        sys.exit("STOP: run this only inside ~/mem0-repro/paper-eval-neo4j-gemini-date (Exp 4 stays untouched)")
    print("add.py:", patch())
