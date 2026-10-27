import json, glob
import numpy as np, pandas as pd, tiktoken

SEARCH = "results/mem0_results_top_30_filter_False_graph_False.json"
EVALS = sorted(glob.glob("results/mem0_eval_run*.json"))
names = {1: "Single hop", 3: "Multi-hop", 4: "Open domain", 2: "Temporal"}
paper = {1: (38.72, 27.13, "67.13 ± 0.65"), 3: (28.64, 21.58, "51.15 ± 0.31"),
         4: (47.65, 38.72, "72.93 ± 0.11"), 2: (48.93, 40.51, "55.51 ± 0.34")}
sd = lambda v: np.std(v, ddof=1) if len(v) > 1 else 0.0

runs = []
for f in EVALS:
    d = json.load(open(f))
    df = pd.DataFrame([x for v in d.values() for x in v])
    df["category"] = df["category"].astype(int)
    runs.append(df)
base = runs[0]
print(f"TABLE 1 - Mem0 on LOCOMO  ({len(EVALS)} judge runs, {len(base)} questions, categories 1-4)")
print(f"{'Question type':13s}{'n':>5s} | {'F1':>6s} {'paper':>6s} | {'BLEU-1':>6s} {'paper':>6s} | {'J':>14s} {'paper':>14s}")
for c in [1, 3, 4, 2]:
    g = base[base.category == c]
    J = [100 * r[r.category == c].llm_score.mean() for r in runs]
    pf, pb, pj = paper[c]
    print(f"{names[c]:13s}{len(g):5d} | {100*g.f1_score.mean():6.2f} {pf:6.2f} | "
          f"{100*g.bleu_score.mean():6.2f} {pb:6.2f} | {np.mean(J):6.2f} ± {sd(J):.2f}  {pj:>14s}")
Jall = [100 * r.llm_score.mean() for r in runs]

s = json.load(open(SEARCH))
items = [x for v in s.values() for x in v if int(x["category"]) != 5]
enc = tiktoken.get_encoding("cl100k_base")
search = np.array([x["speaker_1_memory_time"] + x["speaker_2_memory_time"] for x in items])
total = search + np.array([x["response_time"] for x in items])
tokens = [len(enc.encode("\n".join(f"{m['timestamp']}: {m['memory']}"
          for m in x["speaker_1_memories"] + x["speaker_2_memories"]))) for x in items]
p = lambda a, q: np.percentile(a, q)
print(f"\nTABLE 2 - Mem0 ({len(items)} questions)           ours      paper")
print(f"  Memory tokens per question (mean)   {np.mean(tokens):8.0f}   1764")
print(f"  Search latency p50 (s)              {p(search,50):8.3f}   0.148")
print(f"  Search latency p95 (s)              {p(search,95):8.3f}   0.200")
print(f"  Total latency  p50 (s)              {p(total,50):8.3f}   0.708")
print(f"  Total latency  p95 (s)              {p(total,95):8.3f}   1.440")
print(f"  Overall J                           {np.mean(Jall):5.2f} ± {sd(Jall):.2f}   66.88 ± 0.15")
