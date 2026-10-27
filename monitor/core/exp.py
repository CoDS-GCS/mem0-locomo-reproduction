"""Read-only index of one experiment folder. Nothing here ever writes inside the experiment folder."""
import ast
import glob
import json
import os
import re
import threading
import time
from collections import defaultdict
from pathlib import Path

from .srcs import load_templates
from .tail import Tail, read_line_at
from .util import rel_words, parse_session_date

SECRET = re.compile(r"PASSWORD|SECRET|TOKEN|KEY", re.I)
THREAD_RE = re.compile(r"ThreadPoolExecutor-(\d+)_(\d+)")
UID_RE = re.compile(r"use\s+\"?(?:user_id:\s*)?([^\s\"]+?)\"?\s+as the source entity", re.I)


def read_env(path):
    env = {}
    try:
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return env


def loose_json(s):
    """Parse a JSON object out of an LLM answer (plain, fenced, or surrounded by text)."""
    if isinstance(s, (dict, list)):
        return s
    if not isinstance(s, str):
        return None
    t = s.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t, strict=False)
    except Exception:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            try:
                return json.loads(m.group(0), strict=False)
            except Exception:
                return None
    return None


def fmt_t(ts):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else None


# =========================================================================== dataset
class Dataset:
    def __init__(self, path):
        self.path = Path(path)
        self.mtime = None
        self.convs = []

    def load(self):
        try:
            st = self.path.stat()
        except OSError:
            return False
        if self.mtime == st.st_mtime:
            return False
        data = json.loads(self.path.read_text())
        convs = []
        for idx, item in enumerate(data):
            cv = item["conversation"]
            a, b = cv["speaker_a"], cv["speaker_b"]
            sessions, dia = [], {}
            for key in cv.keys():
                if key in ("speaker_a", "speaker_b") or "date" in key or "timestamp" in key:
                    continue
                turns = []
                for p, ch in enumerate(cv[key]):
                    t = {"dia": ch.get("dia_id"), "speaker": ch["speaker"], "text": ch["text"], "rel": rel_words(ch["text"])}
                    turns.append(t)
                    dia[t["dia"]] = (len(sessions), p)
                sessions.append({"key": key, "date": cv.get(key + "_date_time", ""), "turns": turns})
            qa = [{"qi": i, "question": q.get("question", ""), "answer": str(q.get("answer", q.get("adversarial_answer", ""))),
                   "category": int(q.get("category", -1)), "evidence": q.get("evidence", [])} for i, q in enumerate(item["qa"])]
            c = {"idx": idx, "a": a, "b": b, "users": [f"{a}_{idx}", f"{b}_{idx}"], "sessions": sessions, "qa": qa, "dia": dia}
            c["batches"] = {u: self._batches(c, u) for u in c["users"]}
            convs.append(c)
        self.convs, self.mtime = convs, st.st_mtime
        return True

    @staticmethod
    def _batches(c, user, size=2):
        own = user.rsplit("_", 1)[0]
        out = []
        for si, s in enumerate(c["sessions"]):
            msgs = [("user" if t["speaker"] == own else "assistant", f"{t['speaker']}: {t['text']}") for t in s["turns"]]
            for bi, i in enumerate(range(0, len(msgs), size)):
                m = tuple(msgs[i:i + size])
                out.append({"c": c["idx"], "user": user, "seq": len(out), "si": si, "skey": s["key"], "bi": bi,
                            "pos": list(range(i, min(i + size, len(msgs)))), "date": s["date"], "msgs": m,
                            "ekey": (m, s["date"]), "gkey": m,
                            "events": [], "groups": [], "status": "pending"})
        return out


# =========================================================================== classify one LLM call
def classify(rec, extract_mark):
    msgs = rec.get("messages") or []
    llm, tools = rec.get("llm"), rec.get("tools") or []
    th = THREAD_RE.search(rec.get("thread", "") or "")
    L = {"time": rec.get("time"), "N": int(th.group(1)) if th else None, "br": int(th.group(2)) if th else None,
         "llm": llm, "seconds": rec.get("seconds"), "err": rec.get("error"), "kind": "other"}
    sys0 = msgs[0]["content"] if msgs and msgs[0].get("role") == "system" else ""
    last = msgs[-1]["content"] if msgs else ""
    resp = rec.get("response")
    if llm == "graph":
        t = tools[0] if tools else None
        L["kind"] = {"extract_entities": "entities", "establish_relationships": "relations", "delete_graph_memory": "delete"}.get(t, "graph_other")
        m = UID_RE.search(sys0)
        L["uid"] = m.group(1) if m else None
        calls = (resp or {}).get("tool_calls") if isinstance(resp, dict) else None
        calls = calls or []
        if L["kind"] == "entities":
            L["qtext"] = last
            L["out"] = [e.get("entity") for c in calls for e in (c.get("arguments") or {}).get("entities", [])]
        elif L["kind"] == "relations":
            L["out"] = [e for c in calls for e in (c.get("arguments") or {}).get("entities", [])]
        elif L["kind"] == "delete":
            L["out"] = [c.get("arguments") for c in calls]
    elif llm == "memory" and not tools:
        if sys0 and (extract_mark in sys0[:400] or "Generate personal memories" in sys0[:400]):
            L["kind"] = "extract"
            L["input"] = last.strip()
            j = loose_json(resp) if not rec.get("error") else None
            L["facts"] = [f for f in (j or {}).get("facts", []) if isinstance(f, str)] if isinstance(j, dict) else None
        elif "smart memory manager" in last[:300] or "retrieved facts" in last:
            L["kind"] = "update"
            j = loose_json(resp) if not rec.get("error") else None
            dec = []
            if isinstance(j, dict):
                for d in j.get("memory", []) or []:
                    if isinstance(d, dict):
                        dec.append({"id": str(d.get("id")), "text": d.get("text"), "event": d.get("event"), "old": d.get("old_memory")})
            L["decisions"] = dec if isinstance(j, dict) else None
    return L


def msgs_to_input(msgs):
    return ("Input:\n" + "".join(f"{r}: {c}\n" for r, c in msgs)).strip()


# =========================================================================== the experiment
class Exp:
    def __init__(self, folder):
        self.dir = Path(folder).expanduser().resolve()
        self._env = read_env(self.dir / ".env")
        self.public_env = {k: v for k, v in self._env.items() if not SECRET.search(k) and not k.startswith("GOOGLE_CLOUD")}
        gs = self._env.get("GRAPH_STORE", "").lower()
        logs = self.dir / "logs"
        if gs in ("neo4j", "kuzu"):
            self.mode = gs
            self.mode_source = "GRAPH_STORE in .env"
        elif list(logs.glob("runner_n.log")) or list(logs.glob("events_*.jsonl")):
            self.mode, self.mode_source = "neo4j", "log names (GRAPH_STORE missing)"
        elif list(logs.glob("runner_k.log")) or list(logs.glob("addk_*.log")):
            self.mode, self.mode_source = "kuzu", "log names (GRAPH_STORE missing)"
        elif self._env.get("KUZU_DB"):
            self.mode, self.mode_source = "kuzu", "KUZU_DB in .env"
        else:
            self.mode, self.mode_source = "unknown", "nothing to detect from"
        self.sfx = "n" if self.mode == "neo4j" else "k"
        self.has_addlogs = self.mode == "neo4j"      # events + llm logs exist only for the Neo4j experiment
        self.collection = self._env.get("QDRANT_COLLECTION", "")
        self.lock = threading.RLock()
        self.ds = Dataset(self.dir / "dataset" / "locomo10.json")
        self.templates = load_templates(self.dir)
        self.extract_mark = (self.templates["extract"]["text"] or "").strip()[:40] or "Generate personal memories"
        self.version = 0
        # events
        self._etails, self.events = {}, defaultdict(list)
        # llm
        self._ltails, self.llm = {}, defaultdict(list)     # file -> [light recs]
        # derived
        self.B = {}            # (c,user) -> [batch]
        self.chains = {}       # user -> {mem_id: [versions]}
        self.search_groups = {}  # (uid, question) -> [light recs] from llm_other
        self.runner = {"lines": [], "stage": "unknown"}
        self._runner_sig = None
        self.addlog = {}       # conv -> progress dict
        self._addtails = {}
        self.results = None
        self.last_change = None
        self.last_refresh = None
        self.want_results = 0

    # ------------------------------------------------------------------ files
    def logs(self, pat):
        return sorted(p for p in glob.glob(str(self.dir / "logs" / pat)) if ".before_" not in p)

    def refresh(self):
        changed = False
        if self.ds.load():
            changed = True
        # events
        if self.has_addlogs:
            for p in self.logs("events_*.jsonl"):
                t = self._etails.setdefault(p, Tail(p))
                for off, ln, rec in t.read_new():
                    rec["_f"], rec["_off"], rec["_len"] = p, off, ln
                    self.events[rec.get("user_id") or Path(p).stem[7:]].append(rec)
                    changed = True
            for p in self.logs("llm_conv*.jsonl") + self.logs("llm_other.jsonl"):
                t = self._ltails.setdefault(p, Tail(p))
                lst = self.llm[p]

                def add(off, ln, rec, p=p, lst=lst):
                    L = classify(rec, self.extract_mark)
                    L["_f"], L["_off"], L["_len"] = p, off, ln
                    lst.append(L)
                before = len(lst)
                t.read_new(add)
                if len(lst) != before:
                    changed = True
        # runner log + add logs (small)
        self._read_runner()
        self._read_addlogs()
        # last change = newest mtime among logs and results
        mt = 0
        for pat in ("*",):
            for p in glob.glob(str(self.dir / "logs" / pat)):
                try:
                    mt = max(mt, os.stat(p).st_mtime)
                except OSError:
                    pass
        for p in glob.glob(str(self.dir / "results" / "*.json")):
            try:
                mt = max(mt, os.stat(p).st_mtime)
            except OSError:
                pass
        self.last_change = mt or None
        if changed:
            with self.lock:
                self._relink()
                self.version += 1
        self.last_refresh = time.time()

    # ------------------------------------------------------------------ runner / add logs
    def _read_runner(self):
        p = self.dir / "logs" / f"runner_{self.sfx}.log"
        try:
            st = p.stat()
        except OSError:
            return
        sig = (st.st_mtime, st.st_size)
        if sig == self._runner_sig:
            return
        self._runner_sig = sig
        lines = p.read_text(errors="replace").splitlines()
        stage, detail = "unknown", ""
        for ln in lines:
            if "CHAIN START" in ln:
                stage, detail = "add", "chain started"
            m = re.search(r"pass (\d+) conv (\d+) start", ln)
            if m:
                stage, detail = "add", f"pass {m.group(1)}, conversation {m.group(2)}"
            if "ADD DONE" in ln:
                stage, detail = "search", "add finished"
            m = re.search(r"search attempt (\d+), answered so far: (\d+)", ln)
            if m:
                stage, detail = "search", f"attempt {m.group(1)}, {m.group(2)} answers so far"
            if "SEARCH DONE" in ln:
                stage, detail = "judge", "search finished"
            m = re.search(r"judge run (\d+) done", ln)
            if m:
                stage, detail = "judge", f"{m.group(1)} of 10 judge runs done"
            if "CHAIN END" in ln:
                stage, detail = "finished", ln.split("CHAIN END:")[-1].strip()
            if "CHAIN STOPPED" in ln:
                stage, detail = "stopped", ln.split("CHAIN STOPPED:")[-1].strip()
        self.runner = {"lines": lines[-40:], "stage": stage, "detail": detail,
                       "conv_finished": {int(m.group(1)): ln for ln in lines for m in [re.search(r"conv (\d+) finished=", ln)] if m}}

    def _read_addlogs(self):
        for p in sorted(glob.glob(str(self.dir / "logs" / f"add{self.sfx}_*.log"))):
            m = re.search(r"_(\d+)\.log$", p)
            if not m:
                continue
            c = int(m.group(1))
            d = self.addlog.setdefault(c, {"skipped": [], "crashes": 0, "bar": {}, "off": 0})
            try:
                sz = os.stat(p).st_size
            except OSError:
                continue
            if sz < d["off"]:
                d.update({"skipped": [], "crashes": 0, "bar": {}, "off": 0})
            if sz == d["off"]:
                continue
            with open(p, "rb") as f:
                f.seek(d["off"])
                chunk = f.read(sz - d["off"]).decode("utf-8", "replace")
            d["off"] = sz
            for seg in re.split(r"[\r\n]+", chunk):
                if "SKIPPED BATCH" in seg:
                    d["skipped"].append(seg.strip()[:300])
                if "Exception in thread" in seg:
                    d["crashes"] += 1
                mm = re.match(r"(Adding Memories for Speaker [AB]):\s+(\d+)%\|.*?\|\s*(\d+)/(\d+)", seg.strip())
                if mm:
                    d["bar"][mm.group(1)[-1]] = {"pct": int(mm.group(2)), "done": int(mm.group(3)), "total": int(mm.group(4))}

    # ------------------------------------------------------------------ linking
    @staticmethod
    def _assign_runs(items, keyof, batches, field):
        """items chronological; consecutive items with equal key = attempts of one batch; run -> next unused batch with that key."""
        runs = []
        for it in items:
            k = keyof(it)
            if runs and runs[-1][0] == k:
                runs[-1][1].append(it)
            else:
                runs.append((k, [it]))
        idx = defaultdict(list)
        for i, b in enumerate(batches):
            idx[b[field]].append(i)
        used, last, orphans = set(), -1, []
        for k, its in runs:
            cands = [i for i in idx.get(k, []) if i not in used]
            if not cands:
                orphans.append(its)
                continue
            ge = [i for i in cands if i >= last]
            i = ge[0] if ge else cands[0]
            used.add(i)
            last = i
            yield batches[i], its
        for o in orphans:
            yield None, o

    def _groups_of(self, path):
        groups, order = {}, []
        for r in self.llm.get(path, []):
            N = r["N"]
            if N is None:
                continue
            g = groups.get(N)
            if g is not None and r["kind"] == "extract" and g.get("extract") is not None:
                g = None
            if g is None:
                g = {"N": N, "recs": [], "file": path}
                groups[N] = g
                order.append(g)
            g["recs"].append(r)
            g.setdefault(r["kind"], r) if r["kind"] in ("extract", "update", "entities", "relations", "delete") else None
        for g in order:
            g["t0"] = g["recs"][0]["time"]
            g["t1"] = g["recs"][-1]["time"]
            g["off0"] = g["recs"][0]["_off"]
            g["uid"] = next((r.get("uid") for r in g["recs"] if r.get("uid")), None)
        return order

    def _relink(self):
        B = {}
        for c in self.ds.convs:
            for u in c["users"]:
                # fresh copies so concurrent readers keep a consistent old snapshot
                bl = [dict(b, events=[], groups=[], status="pending") for b in c["batches"][u]]
                B[(c["idx"], u)] = bl
        # events -> batches
        for (c, u), bl in B.items():
            for b, its in self._assign_runs(self.events.get(u, []), lambda e: (tuple((m.get("role"), m.get("content")) for m in (e.get("messages") or [])), e.get("session_date")), bl, "ekey"):
                if b is not None:
                    b["events"] = its
        # llm groups (add stage) -> batches
        for path in [p for p in self.llm if re.search(r"llm_conv\d+\.jsonl$", p)]:
            c = int(re.search(r"llm_conv(\d+)\.jsonl$", path).group(1))
            conv = next((x for x in self.ds.convs if x["idx"] == c), None)
            if not conv:
                continue
            per_user = defaultdict(list)
            inp2users = defaultdict(set)
            for u in conv["users"]:
                for b in B[(c, u)]:
                    inp2users[msgs_to_input(b["msgs"])].add(u)
            for g in self._groups_of(path):
                inp = g["extract"]["input"] if g.get("extract") else None
                u = g["uid"] if g.get("uid") in conv["users"] else None
                if u is None and inp:
                    us = inp2users.get(inp, set())
                    u = next(iter(us)) if len(us) == 1 else None
                g["user"], g["inp"] = u, inp
                if u:
                    per_user[u].append(g)
            for u, gl in per_user.items():
                gl.sort(key=lambda g: g["off0"])
                bl = B[(c, u)]
                for b in bl:
                    b["ikey"] = msgs_to_input(b["msgs"])
                for b, its in self._assign_runs(gl, lambda g: g["inp"], bl, "ikey"):
                    if b is not None:
                        b["groups"] = its
        # status
        for (c, u), bl in B.items():
            act = [b["seq"] for b in bl if b["events"] or b["groups"]]
            top = max(act) if act else -1
            for b in bl:
                fin = next((e for e in reversed(b["events"]) if not e.get("error")), None)
                b["final"] = fin
                b["last_error"] = next((e.get("error") for e in reversed(b["events"]) if e.get("error")), None) if not fin else None
                if fin:
                    b["status"] = "ok"
                elif b["events"]:
                    b["status"] = "retrying" if b["seq"] == top else "skipped"
                elif b["groups"]:
                    b["status"] = "running" if b["seq"] == top else "incomplete"
                else:
                    b["status"] = "pending"
        # memory version chains from the (successful) events, in batch order
        chains = {}
        for (c, u), bl in B.items():
            ch = chains.setdefault(u, {})
            for b in bl:
                for ev in (b["final"] or {}).get("memory_events") or []:
                    mid, e = ev.get("id"), ev.get("event")
                    v = {"event": e, "text": ev.get("memory"), "prev": ev.get("previous_memory"), "c": c, "user": u,
                         "seq": b["seq"], "skey": b["skey"], "bi": b["bi"], "time": b["final"].get("time")}
                    lst = ch.setdefault(mid, [])
                    v["v"] = len(lst) + 1
                    lst.append(v)
        # search-stage entity calls
        sg = defaultdict(list)
        for path, recs in self.llm.items():
            if path.endswith("llm_other.jsonl"):
                for r in recs:
                    if r["kind"] == "entities" and r.get("uid"):
                        sg[(r["uid"], (r.get("qtext") or "").strip())].append(r)
        self.B, self.chains, self.search_groups = B, chains, sg

    # ------------------------------------------------------------------ helpers for API layers
    def conv(self, c):
        return next((x for x in self.ds.convs if x["idx"] == c), None)

    def raw(self, ref):
        """ref = '<file>@<offset>:<len>' -> the full logged record, only for files inside <folder>/logs."""
        try:
            f, rest = ref.rsplit("@", 1)
            off, ln = map(int, rest.split(":"))
        except Exception:
            return None
        p = (self.dir / "logs" / f).resolve()
        if p.parent != (self.dir / "logs").resolve() or not p.name.endswith(".jsonl") or ".before_" in p.name:
            return None
        return read_line_at(p, off, ln)

    @staticmethod
    def ref(L):
        return f"{Path(L['_f']).name}@{L['_off']}:{L['_len']}"
