"""Search results and judge runs. Parsed only when the file changed AND at most every 30 s (the files are big)."""
import glob
import json
import os
import re
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

SEARCH_NAME = "mem0_results_top_30_filter_False_graph_True.json"


class Results:
    def __init__(self, folder):
        self.dir = Path(folder)
        self.search_path = self.dir / "results" / SEARCH_NAME
        self._sig = None
        self._last_parse = 0
        self.rows = {}              # conv -> [row dict]
        self.n_answered = 0
        self.eval = {}              # K -> {"sig":..., "by_conv": {conv: [rows]}}
        self.eval_index = {}        # (conv, question, answer) -> [ {K: row} ... ] by occurrence
        self.version = 0
        self.lock = threading.Lock()
        self.search_mtime = None
        self.minutes = 30

    def refresh(self, force=False):
        changed = False
        now = time.time()
        try:
            st = os.stat(self.search_path)
            sig = (st.st_mtime, st.st_size)
        except OSError:
            sig = None
        if sig and sig != self._sig and (force or now - self._last_parse >= self.minutes):
            try:
                with open(self.search_path) as f:
                    raw = json.load(f)
                intern = {}

                def it(s):
                    return intern.setdefault(s, s)
                rows = {}
                for k, lst in raw.items():
                    out = []
                    for r in lst:
                        r = dict(r)
                        for key in ("speaker_1_memories", "speaker_2_memories"):
                            r[key] = [(it(m["memory"]), it(m.get("timestamp", "")), m.get("score")) for m in (r.get(key) or [])]
                        for key in ("speaker_1_graph_memories", "speaker_2_graph_memories"):
                            r[key] = [tuple(it(x) if isinstance(x, str) else x for x in (g.get("source"), g.get("relationship"), g.get("target"))) for g in (r.get(key) or [])] if r.get(key) is not None else None
                        out.append(r)
                    rows[int(k)] = out
                with self.lock:
                    self.rows = rows
                    self.n_answered = sum(len(v) for v in rows.values())
                    self._sig, self._last_parse, self.search_mtime = sig, now, st.st_mtime
                changed = True
                raw = None
            except Exception as e:  # half-written or replaced while reading: try again next round
                print("results: search file not readable now:", type(e).__name__, file=sys.stderr)
        # judge runs
        for p in sorted(glob.glob(str(self.dir / "results" / "mem0g_eval_run*.json"))):
            m = re.search(r"run(\d+)\.json$", p)
            if not m:
                continue
            K = int(m.group(1))
            try:
                st = os.stat(p)
            except OSError:
                continue
            sig = (st.st_mtime, st.st_size)
            if self.eval.get(K, {}).get("sig") == sig:
                continue
            try:
                d = json.load(open(p))
            except Exception:
                continue
            with self.lock:
                self.eval[K] = {"sig": sig, "by_conv": {int(k): v for k, v in d.items()}}
            changed = True
        if changed:
            idx = defaultdict(list)
            for K in sorted(self.eval):
                for c, lst in self.eval[K]["by_conv"].items():
                    seen = defaultdict(int)
                    for r in lst:
                        key = (c, r["question"], str(r["answer"]))
                        i = seen[key]
                        seen[key] += 1
                        while len(idx[key]) <= i:
                            idx[key].append({})
                        idx[key][i][K] = r
            with self.lock:
                self.eval_index = idx
                self.version += 1
        return changed

    # ------------------------------------------------------------------
    def row(self, c, qi):
        lst = self.rows.get(c) or []
        return lst[qi] if qi < len(lst) else None

    def verdicts(self, c, qi, qa):
        """-> {K: llm_score} plus f1/bleu for question qi of conv c (matched by question text + gold answer, k-th repeat)."""
        # occurrence number of this question among scored questions of the conversation (category 5 is not judged)
        occ = 0
        for q in qa[:qi]:
            if q["question"] == qa[qi]["question"] and q["answer"] == qa[qi]["answer"] and q["category"] != 5:
                occ += 1
        lst = self.eval_index.get((c, qa[qi]["question"], qa[qi]["answer"]), [])
        if occ >= len(lst):
            return {}, None
        per = lst[occ]
        any_row = next(iter(per.values()), None)
        return {K: r["llm_score"] for K, r in per.items()}, any_row

    def j_summary(self, qa_by_conv=None):
        """category and overall J over the judge runs that exist: mean, std (population, as report_all.py), n runs."""
        import statistics
        out = {"runs": sorted(self.eval), "cats": {}, "overall": None}
        if not self.eval:
            return out
        per_run_cat = defaultdict(dict)
        for K, e in self.eval.items():
            by = defaultdict(list)
            allr = []
            for c, lst in e["by_conv"].items():
                for r in lst:
                    if str(r["category"]) == "5":
                        continue
                    by[str(r["category"])].append(r["llm_score"])
                    allr.append(r["llm_score"])
            for cat, v in by.items():
                per_run_cat[cat][K] = 100 * sum(v) / len(v)
            per_run_cat["all"][K] = 100 * sum(allr) / len(allr) if allr else 0
        for cat, d in per_run_cat.items():
            vals = list(d.values())
            out["cats"][cat] = {"mean": statistics.fmean(vals), "std": statistics.pstdev(vals) if len(vals) > 1 else 0.0, "n_runs": len(vals)}
        out["overall"] = out["cats"].pop("all", None)
        return out
