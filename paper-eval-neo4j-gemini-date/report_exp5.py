"""Tables for Exp 5 (Exp 4 + session date shown to the extractors), next to Exp 4 and the paper.

Usage (from ~/mem0-repro/paper-eval-neo4j-gemini-date, venv active):
  python report_exp5.py | tee results/exp5_tables.txt

Reads results/mem0_results_top_30_filter_False_graph_True.json and results/mem0g_eval_run*.json of this folder.
Same rules as report_neo4j.py: categories 1-4 (1,540 questions); F1 and BLEU-1 from run 1; J = mean ± std over
the runs (std divides by the number of runs); memory tokens with tiktoken cl100k_base.
If Exp 4's judge file is there, it also counts per category the questions that changed between Exp 4 and Exp 5.
"""
import glob
import json
import os
import re

import numpy as np
import tiktoken

PAPER = {"1": (38.09, 26.03, 65.71, 0.45), "2": (51.55, 40.28, 58.13, 0.44),      # Mem0g, paper Table 1
         "3": (24.32, 18.82, 47.19, 0.67), "4": (49.27, 40.30, 75.71, 0.21)}
EXP4 = {"1": (31.08, 21.95, 53.19), "2": (27.78, 25.36, 25.55),                 # Gemini + Neo4j, no date
        "3": (14.67, 11.91, 30.21), "4": (37.40, 28.82, 60.76)}
T2 = {"Exp 4": {"tokens": 3786, "s50": 1.782, "s95": 2.664, "t50": 2.431, "t95": 3.767, "J": 50.13, "F1": 32.82, "B1": 25.79},
      "Paper": {"tokens": 3616, "s50": 0.476, "s95": 0.657, "t50": 1.091, "t95": 2.590, "J": 68.44}}
EXP4_RUN1 = os.path.expanduser("~/mem0-repro/paper-eval-neo4j-gemini/results/mem0g_eval_run1.json")

NAMES = {"1": "Single hop", "3": "Multi-hop", "4": "Open domain", "2": "Temporal"}
ORDER = ["1", "3", "4", "2"]
SEARCH = "results/mem0_results_top_30_filter_False_graph_True.json"

files = [f for f in glob.glob("results/mem0g_eval_run*.json") if re.search(r"run\d+\.json$", f)]
files.sort(key=lambda f: int(re.search(r"run(\d+)\.json$", f).group(1)))
if not files:
    raise SystemExit("no results/mem0g_eval_run*.json found - run this from ~/mem0-repro/paper-eval-neo4j-gemini-date")
runs = [[r for v in json.load(open(f)).values() for r in v if str(r["category"]) in NAMES] for f in files]
n_q = len(runs[0])
cat = lambda rows, c: [r for r in rows if str(r["category"]) == c]
pct = lambda rows, k: 100 * np.mean([r[k] for r in rows])

print("Exp 5: Mem0g on LOCOMO - Gemini 2.5 Flash-Lite + Neo4j (mem0ai 1.0.11, authors' instructions)")
print("       + session date written in front of every turn (DATE_PREFIX=1); everything else as Exp 4")
print(f"{len(files)} judge runs, {n_q} scored questions (categories 1-4)\n")
print("TABLE 1a - LLM judge J (%)")
print(f"{'Question type':14} {'n':>4}   {'Exp5 date':>14}   {'Exp4 no date':>12}   {'change':>7}   {'Paper':>14}")
for c in ORDER:
    js = [pct(cat(run, c), "llm_score") for run in runs]
    print(f"{NAMES[c]:14} {len(cat(runs[0], c)):>4}   {np.mean(js):6.2f} ± {np.std(js):4.2f}   {EXP4[c][2]:12.2f}   "
          f"{np.mean(js) - EXP4[c][2]:+7.2f}   {PAPER[c][2]:6.2f} ± {PAPER[c][3]:4.2f}")
overall = [pct(run, "llm_score") for run in runs]
print(f"{'Overall':14} {n_q:>4}   {np.mean(overall):6.2f} ± {np.std(overall):4.2f}   {T2['Exp 4']['J']:12.2f}   "
      f"{np.mean(overall) - T2['Exp 4']['J']:+7.2f}   {T2['Paper']['J']:6.2f} ± 0.17")
print("  J per run:", ", ".join(f"{x:.2f}" for x in overall))

print("\nTABLE 1b - F1 / BLEU-1 (%)")
print(f"{'Question type':14}   {'Exp5 date':>13}   {'Exp4 no date':>13}   {'Paper':>13}")
for c in ORDER:
    r0 = cat(runs[0], c)
    print(f"{NAMES[c]:14}   {pct(r0, 'f1_score'):5.2f} / {pct(r0, 'bleu_score'):5.2f}   "
          f"{EXP4[c][0]:5.2f} / {EXP4[c][1]:5.2f}   {PAPER[c][0]:5.2f} / {PAPER[c][1]:5.2f}")
print(f"{'Overall':14}   {pct(runs[0], 'f1_score'):5.2f} / {pct(runs[0], 'bleu_score'):5.2f}   "
      f"{T2['Exp 4']['F1']:5.2f} / {T2['Exp 4']['B1']:5.2f}")

enc = tiktoken.get_encoding("cl100k_base")
all_rows = [r for v in json.load(open(SEARCH)).values() for r in v]
rows = [r for r in all_rows if str(r["category"]) in NAMES]
tokens, s_t, t_t = [], [], []
for r in rows:
    text = "\n".join(f"{m['timestamp']}: {m['memory']}"
                     for m in (r["speaker_1_memories"] or []) + (r["speaker_2_memories"] or []))
    text += "\n" + json.dumps(r["speaker_1_graph_memories"], indent=4)
    text += "\n" + json.dumps(r["speaker_2_graph_memories"], indent=4)
    tokens.append(len(enc.encode(text)))
    s = r["speaker_1_memory_time"] + r["speaker_2_memory_time"]
    s_t.append(s)
    t_t.append(s + r["response_time"])
q = lambda x, p: float(np.percentile(x, p))
ours = {"tokens": np.mean(tokens), "s50": q(s_t, 50), "s95": q(s_t, 95), "t50": q(t_t, 50), "t95": q(t_t, 95)}
print(f"\nTABLE 2 - cost ({len(rows)} questions)")
print(f"{'':32} {'Exp5 date':>10}   {'Exp4 no date':>12}   {'Paper':>7}")
for k, label, fmt in [("tokens", "Memory tokens per question", "{:.0f}"),
                      ("s50", "Search latency p50 (s)", "{:.3f}"), ("s95", "Search latency p95 (s)", "{:.3f}"),
                      ("t50", "Total latency  p50 (s)", "{:.3f}"), ("t95", "Total latency  p95 (s)", "{:.3f}")]:
    print(f"{label:32} {fmt.format(ours[k]):>10}   {fmt.format(T2['Exp 4'][k]):>12}   {fmt.format(T2['Paper'][k]):>7}")

if os.path.exists(EXP4_RUN1):
    e4 = json.load(open(EXP4_RUN1))
    e5 = json.load(open(files[0]))
    flips = {c: [0, 0, 0] for c in ORDER}  # wrong->right, right->wrong, compared
    for k, v5 in e5.items():
        for i, r in enumerate(v5):
            c = str(r["category"])
            if c not in NAMES or k not in e4 or i >= len(e4[k]) or e4[k][i]["question"] != r["question"]:
                continue
            a, b = int(e4[k][i]["llm_score"]), int(r["llm_score"])
            flips[c][0] += (a == 0 and b == 1)
            flips[c][1] += (a == 1 and b == 0)
            flips[c][2] += 1
    print("\nTABLE 3 - questions that changed, Exp 4 -> Exp 5 (judge run 1)")
    print(f"{'Question type':14} {'compared':>8}   {'wrong->right':>12}   {'right->wrong':>12}   {'net':>5}")
    for c in ORDER:
        w, r_, n = flips[c]
        print(f"{NAMES[c]:14} {n:8}   {w:12}   {r_:12}   {w - r_:+5}")
else:
    print(f"\n(Exp 4 judge file not found at {EXP4_RUN1}: per-question comparison skipped)")

empty = sum(1 for r in all_rows if not str(r.get("response", "")).strip())
with_rel = sum(1 for r in all_rows if (r["speaker_1_graph_memories"] or r["speaker_2_graph_memories"]))
n_mem = [len(r["speaker_1_memories"] or []) + len(r["speaker_2_memories"] or []) for r in all_rows]
print(f"\nCHECKS (all {len(all_rows)} questions)")
print(f"  empty answers: {empty}")
print(f"  questions with graph relations: {with_rel} of {len(all_rows)}")
print(f"  memories per question (both speakers): mean {np.mean(n_mem):.1f}, max {max(n_mem)}")
