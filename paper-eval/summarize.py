import json, sys, glob
import pandas as pd
names = {1: "Single hop", 2: "Temporal", 3: "Multi-hop", 4: "Open domain"}
paper = {1: 67.13, 2: 55.51, 3: 51.15, 4: 72.93, "overall": 66.88}
runs = []
for f in sorted(glob.glob(sys.argv[1])):
    d = json.load(open(f))
    df = pd.DataFrame([x for v in d.values() for x in v])
    df["category"] = df["category"].astype(int)
    r = {"overall": 100 * df.llm_score.mean()}
    for c, g in df.groupby("category"):
        r[c] = 100 * g.llm_score.mean()
    runs.append(r)
t = pd.DataFrame(runs)
print(f"J over {len(t)} judge runs (mean ± std)   vs paper")
for c in [1, 2, 3, 4]:
    print(f"  cat {c} {names[c]:12s} {t[c].mean():6.2f} ± {t[c].std():.2f}   paper {paper[c]}")
print(f"  Overall            {t['overall'].mean():6.2f} ± {t['overall'].std():.2f}   paper {paper['overall']}")
print(f"F1 = {100*df.f1_score.mean():.2f}   BLEU-1 = {100*df.bleu_score.mean():.2f}   (questions scored: {len(df)})")
print("\nJ per conversation (last run):")
d = json.load(open(sorted(glob.glob(sys.argv[1]))[-1]))
for k, v in d.items():
    print(f"  conv {k}: {100*sum(x['llm_score'] for x in v)/len(v):5.1f}  ({len(v)} questions)")
