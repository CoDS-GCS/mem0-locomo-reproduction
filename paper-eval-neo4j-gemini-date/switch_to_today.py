"""Exp 5: switch the date wording from "[1:56 pm on 8 May, 2023] Caroline: ..." to "[today is 8 May, 2023] Caroline: ..."
(chosen with prefix_test.py on 58 cases from conversations 0-2, before the full run).
Run once from the Exp 5 folder:   python switch_to_today.py

What it changes (prints each change; stops without changing anything if a file looks unexpected):
  1. src/memzero/add.py  - the one date_prefix line (and its comment). DATE_PREFIX=0 still gives Exp 4's text exactly.
  2. smoke_exp5.py       - its checks expect the new wording.
  3. ~/mem0-repro/EXPERIMENTS.md - row 5 and a note on the pilot that chose the wording.
"""
import os
import pathlib
import sys

if pathlib.Path.cwd().name != "paper-eval-neo4j-gemini-date":
    sys.exit("STOP: run this from ~/mem0-repro/paper-eval-neo4j-gemini-date")

edits = {
    "src/memzero/add.py": [
        ('date_prefix = f"[{timestamp}] " if os.getenv("DATE_PREFIX", "0") == "1" else ""',
         'date_prefix = f"[today is {timestamp.split(\' on \', 1)[-1]}] " if os.getenv("DATE_PREFIX", "0") == "1" else ""'),
        ('# "[1:56 pm on 8 May, 2023] Caroline: ...", so Mem0\'s fact and graph extractors see it.',
         '# "[today is 8 May, 2023] Caroline: ...", so Mem0\'s fact and graph extractors see it.'),
    ],
    "smoke_exp5.py": [
        ('check(got1 == [f"[{ts}] {x}" for x in exp4_text], f"DATE_PREFIX=1: all {len(got1)} turns start with [{ts}]")',
         'pre = f"[today is {ts.split(\' on \', 1)[-1]}] "\n'
         'check(got1 == [pre + x for x in exp4_text], f"DATE_PREFIX=1: all {len(got1)} turns start with {pre.strip()}")'),
        ('check(ts in user_in, "the date is in the FACT-EXTRACTOR input. What Gemini received:")',
         'check(ts.split(" on ", 1)[-1] in user_in, "the date is in the FACT-EXTRACTOR input. What Gemini received:")'),
        ('check(any(ts in json.dumps(r["messages"]) for r in graph), "the date is in the GRAPH-EXTRACTOR input")',
         'check(any(ts.split(" on ", 1)[-1] in json.dumps(r["messages"]) for r in graph), "the date is in the GRAPH-EXTRACTOR input")'),
    ],
}

# check everything first, change nothing unless all edits fit
new = {}
for f, pairs in edits.items():
    s = pathlib.Path(f).read_text()
    if "today is" in s and f == "src/memzero/add.py":
        sys.exit("add.py already uses the 'today is' wording - nothing changed")
    for old, rep in pairs:
        if s.count(old) != 1:
            sys.exit(f"STOP: in {f} this line was found {s.count(old)} times (expected 1) - NOTHING changed:\n  {old}")
        s = s.replace(old, rep)
    if f.endswith(".py"):
        compile(s, f, "exec")
    new[f] = s
for f, s in new.items():
    pathlib.Path(f).write_text(s)
    print(f"changed {f}")
for i, l in enumerate(new["src/memzero/add.py"].splitlines(), 1):
    if "date_prefix =" in l:
        print(f"   add.py line {i}: {l.strip()}")

nb = pathlib.Path(os.path.expanduser("~/mem0-repro/EXPERIMENTS.md"))
if nb.exists():
    s = nb.read_text()
    s = s.replace("4: session date written in front of every turn (DATE_PREFIX=1)",
                  "4: session date shown in front of every turn as \"[today is <date>]\" (DATE_PREFIX=1)")
    NOTE = """- Wording of the date, chosen before the full run with `prefix_test.py`: Mem0's fact extractor (authors' instructions, called exactly as Mem0 calls it) on the 58 LOCOMO temporal questions of conversations 0-2 whose evidence says "yesterday", "last week", "last Friday", "two weeks ago", "last month" or "last year". Label of the best fact about the event (CORRECT = the date the phrase really means; KEPT = phrase kept, computable from the memory timestamp; SESSION = event put on the session day):

  | wording | CORRECT | KEPT | SESSION | WRONG | LOST | no fact |
  |---|---|---|---|---|---|---|
  | none (= Exp 4) | 0 | 29 | 0 | 13 | 5 | 11 |
  | `[1:56 pm on 8 May, 2023]` | 19 | 15 | 12 | 1 | 2 | 9 |
  | `[sent on 8 May, 2023 at 1:56 pm]` | 23 | 20 | 5 | 0 | 1 | 9 |
  | `[today is 8 May, 2023]` (chosen) | 35 | 9 | 3 | 2 | 0 | 9 |

  One run per wording; conversation 0 was first added with the `[1:56 pm on 8 May, 2023]` wording (pilot) and then redone with the chosen one. "today is" mirrors Mem0's own default extraction prompt ("Today's date is ..."), with the conversation's date instead of the computer's clock.
"""
    if "prefix_test.py" not in s and "\n### 5 " in s:
        head, tail = s.split("\n### 5 ", 1)
        nxt = tail.find("\n### ")
        sec, rest = (tail, "") if nxt < 0 else (tail[:nxt], tail[nxt:])
        s = head + "\n### 5 " + sec.rstrip("\n") + "\n" + NOTE + rest
    nb.write_text(s)
    print("updated ~/mem0-repro/EXPERIMENTS.md (row 5 + wording note)")
else:
    print("EXPERIMENTS.md not found - notebook not updated (check the setup)")
print("\nNext: python smoke_exp5.py   (must PASS with the new wording), then rm logs/n_done_0 and start the run.")
