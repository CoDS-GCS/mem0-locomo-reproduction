"""Tables for Exp 4 (Mem0g, Gemini 2.5 Flash-Lite + Neo4j, mem0ai 1.0.11), next to Exp 2, Exp 1 and the paper.

Usage (from ~/mem0-repro/paper-eval-neo4j-gemini, with .venv-neo active):
  python report_neo4j.py | tee results/mem0g_neo4j_tables.txt

Reads results/mem0_results_top_30_filter_False_graph_True.json and results/mem0g_eval_run*.json.
Only categories 1-4 are scored (1,540 questions), as in the paper.
F1 and BLEU-1 come from run 1; J is mean ± std over the runs (std divides by the number of runs, like
report_kuzu.py and report_all.py). Memory tokens use tiktoken cl100k_base, as for the other runs.
"""
import glob, json, re
import numpy as np
import tiktoken

# Mem0g rows: (F1, BLEU-1, J); paper also has J std
PAPER = {"1": (38.09, 26.03, 65.71, 0.45), "2": (51.55, 40.28, 58.13, 0.44),
         "3": (24.32, 18.82, 47.19, 0.67), "4": (49.27, 40.30, 75.71, 0.21)}
EXP2 = {"1": (30.99, 21.30, 54.96), "2": (26.28, 23.45, 24.92),      # Gemini + Kuzu, mem0ai 1.0.11
        "3": (16.46, 12.45, 34.38), "4": (37.82, 28.79, 60.17)}
EXP1 = {"1": (31.13, 22.25, 52.34), "2": (28.43, 27.99, 18.63),      # GPT-4o-mini + Neo4j, mem0ai 0.1.93
        "3": (22.57, 17.52, 44.79), "4": (39.55, 31.42, 69.18)}
T2 = {"Exp 2": {"tokens": 3776, "s50": 2.182, "s95": 3.946, "t50": 2.918, "t95": 6.071, "J": 50.26},
      "Exp 1": {"tokens": 5762, "s50": 4.410, "s95": 6.927, "t50": 5.242, "t95": 7.848, "J": 54.04},
      "Paper": {"tokens": 3616, "s50": 0.476, "s95": 0.657, "t50": 1.091, "t95": 2.590, "J": 68.44}}

NAMES = {"1": "Single hop", "3": "Multi-hop", "4": "Open domain", "2": "Temporal"}
ORDER = ["1", "3", "4", "2"]
SEARCH = "results/mem0_results_top_30_filter_False_graph_True.json"

files = [f for f in glob.glob("results/mem0g_eval_run*.json") if re.search(r"run\d+\.json$", f)]
files.sort(key=lambda f: int(re.search(r"run(\d+)\.json$", f).group(1)))
if not files:
    raise SystemExit("no results/mem0g_eval_run*.json found - run this from ~/mem0-repro/paper-eval-neo4j-gemini")
runs = [[r for v in json.load(open(f)).values() for r in v if str(r["category"]) in NAMES] for f in files]
n_q = len(runs[0])
cat = lambda rows, c: [r for r in rows if str(r["category"]) == c]
pct = lambda rows, k: 100 * np.mean([r[k] for r in rows])

print("Exp 4: Mem0g on LOCOMO - Gemini 2.5 Flash-Lite + Neo4j (mem0ai 1.0.11, authors' instructions)")
print(f"{len(files)} judge runs, {n_q} scored questions (categories 1-4)\n")
print("TABLE 1a - LLM judge J (%)")
print(f"{'Question type':14} {'n':>4}   {'Exp4 Neo4j':>14}   {'Exp2 Kuzu':>9}   {'Exp1 GPT':>8}   {'Paper':>14}")
for c in ORDER:
    js = [pct(cat(run, c), "llm_score") for run in runs]
    print(f"{NAMES[c]:14} {len(cat(runs[0], c)):>4}   {np.mean(js):6.2f} ± {np.std(js):4.2f}   "
          f"{EXP2[c][2]:9.2f}   {EXP1[c][2]:8.2f}   {PAPER[c][2]:6.2f} ± {PAPER[c][3]:4.2f}")
overall = [pct(run, "llm_score") for run in runs]
print(f"{'Overall':14} {n_q:>4}   {np.mean(overall):6.2f} ± {np.std(overall):4.2f}   "
      f"{T2['Exp 2']['J']:9.2f}   {T2['Exp 1']['J']:8.2f}   {T2['Paper']['J']:6.2f} ± 0.17")
print("  J per run:", ", ".join(f"{x:.2f}" for x in overall))

print("\nTABLE 1b - F1 / BLEU-1 (%)")
print(f"{'Question type':14}   {'Exp4 Neo4j':>13}   {'Exp2 Kuzu':>13}   {'Exp1 GPT':>13}   {'Paper':>13}")
for c in ORDER:
    r0 = cat(runs[0], c)
    print(f"{NAMES[c]:14}   {pct(r0, 'f1_score'):5.2f} / {pct(r0, 'bleu_score'):5.2f}   "
          f"{EXP2[c][0]:5.2f} / {EXP2[c][1]:5.2f}   {EXP1[c][0]:5.2f} / {EXP1[c][1]:5.2f}   "
          f"{PAPER[c][0]:5.2f} / {PAPER[c][1]:5.2f}")
print(f"{'Overall':14}   {pct(runs[0], 'f1_score'):5.2f} / {pct(runs[0], 'bleu_score'):5.2f}")

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
print(f"{'':32} {'Exp4 Neo4j':>10}   {'Exp2 Kuzu':>9}   {'Exp1 GPT':>8}   {'Paper':>7}")
for k, label, fmt in [("tokens", "Memory tokens per question", "{:.0f}"),
                      ("s50", "Search latency p50 (s)", "{:.3f}"), ("s95", "Search latency p95 (s)", "{:.3f}"),
                      ("t50", "Total latency  p50 (s)", "{:.3f}"), ("t95", "Total latency  p95 (s)", "{:.3f}")]:
    print(f"{label:32} {fmt.format(ours[k]):>10}   {fmt.format(T2['Exp 2'][k]):>9}   "
          f"{fmt.format(T2['Exp 1'][k]):>8}   {fmt.format(T2['Paper'][k]):>7}")

empty = sum(1 for r in all_rows if not str(r.get("response", "")).strip())
with_rel = sum(1 for r in all_rows if (r["speaker_1_graph_memories"] or r["speaker_2_graph_memories"]))
n_rel = [len(r["speaker_1_graph_memories"] or []) + len(r["speaker_2_graph_memories"] or []) for r in all_rows]
n_mem = [len(r["speaker_1_memories"] or []) + len(r["speaker_2_memories"] or []) for r in all_rows]
print(f"\nCHECKS (all {len(all_rows)} questions)")
print(f"  empty answers: {empty}")
print(f"  questions with graph relations: {with_rel} of {len(all_rows)}")
print(f"  memories per question (both speakers): mean {np.mean(n_mem):.1f}, max {max(n_mem)}")
print(f"  relations per question (both speakers): mean {np.mean(n_rel):.1f}, max {max(n_rel)}")
