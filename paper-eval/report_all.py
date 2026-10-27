import argparse, glob, json
import numpy as np
import tiktoken

PAPER = {
    "mem0": {"cat": {"1": (38.72, 27.13, 67.13, 0.65), "2": (48.93, 40.51, 55.51, 0.34),
                     "3": (28.64, 21.58, 51.15, 0.31), "4": (47.65, 38.72, 72.93, 0.11)},
             "tokens": 1764, "search": (0.148, 0.200), "total": (0.708, 1.440), "J": (66.88, 0.15)},
    "mem0g": {"cat": {"1": (38.09, 26.03, 65.71, 0.45), "2": (51.55, 40.28, 58.13, 0.44),
                      "3": (24.32, 18.82, 47.19, 0.67), "4": (49.27, 40.30, 75.71, 0.21)},
              "tokens": 3616, "search": (0.476, 0.657), "total": (1.091, 2.590), "J": (68.44, 0.17)},
}
NAMES = {"1": "Single hop", "3": "Multi-hop", "4": "Open domain", "2": "Temporal"}
ORDER = ["1", "3", "4", "2"]

ap = argparse.ArgumentParser()
ap.add_argument("--system", choices=["mem0", "mem0g"], required=True)
a = ap.parse_args()
graph = a.system == "mem0g"
search_file = f"results/mem0_results_top_30_filter_False_graph_{graph}.json"
eval_files = [f for f in sorted(glob.glob(f"results/{a.system}_eval_run*.json")) if "BACKUP" not in f]
P = PAPER[a.system]

runs = [[r for v in json.load(open(f)).values() for r in v if str(r["category"]) in NAMES] for f in eval_files]
if not runs:
    raise SystemExit(f"no judge files found for {a.system}")
n_q = len(runs[0])
cat_rows = lambda rows, c: [r for r in rows if str(r["category"]) == c]
label = "Mem0g" if graph else "Mem0"

print(f"TABLE 1 - {label} on LOCOMO  ({len(runs)} judge runs, {n_q} questions, categories 1-4)")
print(f"{'Question type':14} {'n':>4} | {'F1':>6} {'paper':>6} | {'BLEU-1':>6} {'paper':>6} | {'J':>14} {'paper':>14}")
for c in ORDER:
    r0 = cat_rows(runs[0], c)
    f1 = 100 * np.mean([r["f1_score"] for r in r0]); b1 = 100 * np.mean([r["bleu_score"] for r in r0])
    js = [100 * np.mean([r["llm_score"] for r in cat_rows(run, c)]) for run in runs]
    pf, pb, pj, ps = P["cat"][c]
    print(f"{NAMES[c]:14} {len(r0):>4} | {f1:6.2f} {pf:6.2f} | {b1:6.2f} {pb:6.2f} | "
          f"{np.mean(js):6.2f} ± {np.std(js):4.2f}   {pj:6.2f} ± {ps:4.2f}")
overall = [100 * np.mean([r["llm_score"] for r in run]) for run in runs]
f1_all = 100 * np.mean([r["f1_score"] for r in runs[0]]); b1_all = 100 * np.mean([r["bleu_score"] for r in runs[0]])
print(f"{'Overall':14} {n_q:>4} | {f1_all:6.2f} {'':>6} | {b1_all:6.2f} {'':>6} | "
      f"{np.mean(overall):6.2f} ± {np.std(overall):4.2f}   {P['J'][0]:6.2f} ± {P['J'][1]:4.2f}")

enc = tiktoken.get_encoding("cl100k_base")
rows = [r for v in json.load(open(search_file)).values() for r in v if str(r["category"]) in NAMES]
tokens, search_t, total_t = [], [], []
for r in rows:
    text = "\n".join(f"{m['timestamp']}: {m['memory']}"
                     for m in (r["speaker_1_memories"] or []) + (r["speaker_2_memories"] or []))
    if graph:
        text += "\n" + json.dumps(r["speaker_1_graph_memories"], indent=4)
        text += "\n" + json.dumps(r["speaker_2_graph_memories"], indent=4)
    tokens.append(len(enc.encode(text)))
    s = r["speaker_1_memory_time"] + r["speaker_2_memory_time"]
    search_t.append(s); total_t.append(s + r["response_time"])
p = lambda x, q: float(np.percentile(x, q))
print(f"\nTABLE 2 - {label} ({len(rows)} questions)          ours      paper")
print(f"  Memory tokens per question (mean)   {np.mean(tokens):8.0f}   {P['tokens']:6d}")
print(f"  Search latency p50 (s)              {p(search_t, 50):8.3f}   {P['search'][0]:6.3f}")
print(f"  Search latency p95 (s)              {p(search_t, 95):8.3f}   {P['search'][1]:6.3f}")
print(f"  Total latency  p50 (s)              {p(total_t, 50):8.3f}   {P['total'][0]:6.3f}")
print(f"  Total latency  p95 (s)              {p(total_t, 95):8.3f}   {P['total'][1]:6.3f}")
print(f"  Overall J                       {np.mean(overall):6.2f} ± {np.std(overall):4.2f}   {P['J'][0]:.2f} ± {P['J'][1]:.2f}")
