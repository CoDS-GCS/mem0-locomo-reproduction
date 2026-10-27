"""Builders for the JSON the pages draw: Cytoscape elements + a details dict (what a click shows)."""
import ast
import re
from collections import defaultdict

from .exp import loose_json
from .util import rel_words, overlap, date_verdict, OVERLAP_MIN, parse_session_date
from . import analysis as AN


def clip(s, n=110):
    s = re.sub(r"\s+", " ", str(s if s is not None else "")).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


class G:
    """Tiny graph builder."""

    def __init__(self):
        self.el, self.details, self.ids = [], {}, set()

    def node(self, id, label, kind, detail=None, cls=""):
        if id in self.ids:
            return id
        self.ids.add(id)
        self.el.append({"data": {"id": id, "label": label, "kind": kind}, "classes": cls})
        if detail is not None:
            self.details[id] = detail
        return id

    def edge(self, a, b, label="", cls="", detail=None):
        eid = f"e:{a}>{b}"
        if eid in self.ids:
            return
        self.ids.add(eid)
        self.el.append({"data": {"id": eid, "source": a, "target": b, "label": label}, "classes": cls})
        if detail is not None:
            self.details[eid] = detail

    def out(self, **kw):
        return {"elements": self.el, "details": self.details, **kw}


def tpl_block(exp, key, logged_text):
    t = exp.templates.get(key) or {}
    txt = t.get("text")
    match = None
    if txt and logged_text:
        head = re.sub(r"\s+", " ", txt.strip())[:60]
        match = head in re.sub(r"\s+", " ", logged_text)
    return {"t": "kv", "label": "Template", "rows": [["file", t.get("file", "?")], ["name", t.get("name", "?")],
                                                       ["template found in source", "yes" if txt else "no (not readable)"],
                                                       ["logged prompt starts with this template", {True: "yes", False: "NO - differs", None: "n/a"}[match]]]}


# ======================================================================= P1
def dataset_conv(exp, c):
    conv = exp.conv(c)
    sessions = [{"i": i, "key": s["key"], "date": s["date"], "n": len(s["turns"]),
                 "rel": sum(1 for t in s["turns"] if t["rel"])} for i, s in enumerate(conv["sessions"])]
    return {"idx": c, "a": conv["a"], "b": conv["b"], "sessions": sessions, "questions": conv["qa"],
            "n_turns": sum(s["n"] for s in sessions)}


def dataset_session(exp, c, si):
    conv = exp.conv(c)
    s = conv["sessions"][si]
    return {"key": s["key"], "date": s["date"], "turns": s["turns"]}


# ======================================================================= P2
def session_batches(exp, c, user, si):
    out = []
    for b in exp.B.get((c, user), []):
        if b["si"] == si:
            fin = b["final"] or {}
            ev = [e.get("event") for e in (fin.get("memory_events") or [])]
            out.append({"bi": b["bi"], "seq": b["seq"], "status": b["status"], "turns": [exp.conv(c)["sessions"][si]["turns"][p]["dia"] for p in b["pos"]],
                        "add": ev.count("ADD"), "upd": ev.count("UPDATE"), "del": ev.count("DELETE"), "attempts": len(b["events"]) or len(b["groups"]),
                        "time": fin.get("time")})
    return out


def state_before(exp, user, seq):
    """memory id -> text for memories alive just before batch `seq` of this user (from the version chains)."""
    alive = {}
    for mid, ch in exp.chains.get(user, {}).items():
        last = None
        for v in ch:
            if v["seq"] < seq:
                last = v
        if last and last["event"] != "DELETE":
            alive[mid] = last["text"]
    return alive


def parse_existing(prompt_text):
    """From the update prompt: ({temp id: text}, [new facts]) ."""
    ex, facts = {}, []
    m = re.search(r"current content of my memory.*?```\s*(.*?)\s*```", prompt_text, re.S)
    if m:
        try:
            for d in ast.literal_eval(m.group(1)):
                ex[str(d.get("id"))] = d.get("text")
        except Exception:
            pass
    m2 = re.search(r"new retrieved facts are mentioned in the triple backticks.*?```\s*(.*?)\s*```", prompt_text, re.S)
    if m2:
        try:
            facts = list(ast.literal_eval(m2.group(1)))
        except Exception:
            pass
    return ex, facts


def batch_view(exp, c, user, si, bi):
    conv = exp.conv(c)
    sess = conv["sessions"][si]
    b = next((x for x in exp.B[(c, user)] if x["si"] == si and x["bi"] == bi), None)
    if b is None:
        return {"error": "no such batch"}
    g = G()
    own = user.rsplit("_", 1)[0]
    turns = [sess["turns"][p] for p in b["pos"]]
    grp = b["groups"][-1] if b["groups"] else None
    fin = b["final"]
    status = b["status"]
    # ---- turns
    tl = "\n".join(f"{t['dia']}  {clip(t['speaker'] + ': ' + t['text'], 70)}" + ("  ⏱" if t["rel"] else "") for t in turns)
    notes = []
    if len(b["events"]) > 1 or len(b["groups"]) > 1:
        notes.append({"t": "p", "v": f"This batch took {max(len(b['events']), len(b['groups']))} attempt(s). Earlier errors: " + "; ".join(clip(e.get('error'), 160) for e in b["events"] if e.get("error"))})
    g.node("turns", tl, "data", {"title": f"Batch {bi + 1} of {sess['key']} — {user}", "subtitle": sess["date"], "blocks": [
        {"t": "kv", "rows": [["store (user id)", user], ["session date (metadata.timestamp)", sess["date"]], ["status", status]]},
        {"t": "list", "label": "Messages given to add() (role in this store)", "items": [f"{('user' if t['speaker'] == own else 'assistant')} · {t['dia']} · {t['speaker']}: {t['text']}" for t in turns]},
        {"t": "p", "v": "Relative time words in these turns: " + (", ".join(sorted({w for t in turns for w in t['rel']})) or "none")},
        {"t": "p", "v": "Note: metadata.timestamp is stored with the memory but is NOT part of any prompt the LLM sees (see the extraction prompt)."}] + notes},
           cls="data")
    pend = status in ("pending",)
    # ---- memory branch
    ex = grp.get("extract") if grp else None
    if ex is None:
        g.node("extract", "Extraction call\n(pending)" if pend else "Extraction call\n(no log for this batch)", "llm", {"title": "Extraction call", "blocks": [tpl_block(exp, "extract", None)]}, cls="llm pending")
    else:
        err = ex.get("err")
        facts = ex.get("facts")
        lab = f"Extraction call\nsystem prompt: custom_fact_extraction_prompt\n→ " + ("ERROR" if err else (f"{len(facts)} fact(s)" if facts is not None else "answer not parseable"))
        raw = exp.raw(exp.ref(ex)) or {}
        sys0 = (raw.get("messages") or [{}])[0].get("content", "")
        g.node("extract", lab, "llm", {"title": "Extraction call (memory branch, step 1)", "subtitle": f"{ex.get('seconds')} s · {ex.get('time')}", "blocks": [
            tpl_block(exp, "extract", sys0),
            {"t": "list", "label": "Facts out" if facts else "Facts out (none)", "items": facts or []},
            {"t": "llm", "ref": exp.ref(ex), "label": "Full prompt in and raw answer out"}] + ([{"t": "p", "v": "ERROR: " + str(err)}] if err else [])},
               cls="llm" + (" error" if err else ""))
    g.edge("turns", "extract", "2 messages")
    up = grp.get("update") if grp else None
    facts = (ex or {}).get("facts") or []
    if ex is not None and not facts and not (ex.get("err")):
        g.node("update", "Update call\nnot made: no facts were extracted", "llm", {"title": "Update call skipped", "blocks": [{"t": "p", "v": "Mem0 only calls the update LLM when the extraction produced at least one fact."}]}, cls="llm pending")
    elif up is None:
        g.node("update", "Update call\n(pending)" if (pend or ex is None) else "Update call\n(not logged)", "llm", {"title": "Update call"}, cls="llm pending")
    else:
        raw = exp.raw(exp.ref(up)) or {}
        ptxt = (raw.get("messages") or [{}])[-1].get("content", "")
        existing, nfacts = parse_existing(ptxt)
        alive = state_before(exp, user, b["seq"])
        t2id = {t: i for i, t in alive.items()}
        dec = up.get("decisions")
        cnt = defaultdict(int)
        for d in dec or []:
            cnt[d["event"]] += 1
        lab = f"Update call\n{len(existing)} existing memories given\n→ " + (", ".join(f"{k} {v}" for k, v in sorted(cnt.items())) if dec else ("ERROR" if up.get("err") else "answer not parseable"))
        rows = [[d["event"], d["id"], (t2id.get(existing.get(d["id"])) or t2id.get(d.get("text")) or "(new)"), d.get("text"), d.get("old") or ""] for d in dec or []]
        g.node("update", lab, "llm", {"title": "Update call (memory branch, step 3)", "subtitle": f"{up.get('seconds')} s · {up.get('time')}", "blocks": [
            tpl_block(exp, "update", ptxt),
            {"t": "list", "label": f"Existing memories the LLM was given ({len(existing)}; the 5 most similar per fact, from Qdrant)", "items": [f"[{k}] {v}" for k, v in existing.items()]},
            {"t": "list", "label": "New facts it was asked to place", "items": nfacts},
            {"t": "table", "label": "Decision per memory (NONE = left unchanged)", "head": ["event", "temp id", "real memory id", "text", "old text"], "rows": rows},
            {"t": "llm", "ref": exp.ref(up), "label": "Full prompt in and raw answer out"}] + ([{"t": "p", "v": "ERROR: " + str(up.get('err'))}] if up.get("err") else [])},
               cls="llm" + (" error" if up.get("err") else ""))
    g.edge("extract", "update", "facts")
    # memory outcome nodes
    evs = (fin or {}).get("memory_events") or []
    n_none = sum(1 for d in ((up or {}).get("decisions") or []) if d["event"] == "NONE")
    k = 0
    for ev in evs:
        e = ev.get("event")
        mid = ev.get("id")
        chain = exp.chains.get(user, {}).get(mid, [])
        v = next((x for x in chain if x["seq"] == b["seq"]), None)
        blocks = [{"t": "kv", "rows": [["memory id", mid], ["event", e], ["version", f"v{v['v']} of {len(chain)}" if v else "?"]]}]
        if e == "UPDATE":
            blocks.append({"t": "diff", "label": "before → after", "a": ev.get("previous_memory") or "", "b": ev.get("memory") or ""})
        else:
            blocks.append({"t": "pre", "label": "memory text", "v": ev.get("memory") or ""})
        dv = date_verdict(" ".join(t["text"] for t in turns), ev.get("memory") or "", sess["date"]) if any(t["rel"] for t in turns) and e != "DELETE" else None
        if dv and dv["label"] != "none":
            blocks.append({"t": "kv", "label": "Temporal check (heuristic, see About)", "rows": [["relative words in the turns", ", ".join(dv["words"])], ["dates written in memory", ", ".join(dv["mentions"]) or "none"],
                                                                                               ["expected from session date", "; ".join(dv.get("expected", [])) or "n/a"], ["verdict", dv["label"].replace("_", " ")]]})
        blocks.append({"t": "nav", "label": "Open this memory in the Memory page", "href": f"#/memory?conv={c}&user={user}&mem={mid}"})
        g.node(f"mem{k}", f"{e}\n{clip(ev.get('memory'), 150)}", "mem", {"title": f"Memory {e}", "blocks": blocks}, cls={"ADD": "mem add", "UPDATE": "mem upd", "DELETE": "mem del"}.get(e, "mem"))
        g.edge("update", f"mem{k}", e.lower())
        k += 1
    if not evs and up is not None and up.get("decisions") and status != "ok":
        for d in up["decisions"]:
            if d["event"] in ("ADD", "UPDATE", "DELETE"):
                g.node(f"mem{k}", f"{d['event']} (not confirmed yet)\n{clip(d.get('text'), 140)}", "mem", {"title": "Decision not yet confirmed by the add() result"}, cls="mem pending")
                g.edge("update", f"mem{k}", d["event"].lower())
                k += 1
    if n_none or (up is not None and not evs and status == "ok"):
        g.node("none", f"NONE ×{n_none}\nexisting memories left unchanged" if n_none else "no change\nnothing was added, updated or deleted", "mem", {"title": "Decisions NONE", "blocks": [{"t": "p", "v": "Mem0 1.0.11 does not return NONE decisions from add(); they are read from the update call's answer."}]}, cls="mem none")
        g.edge("update", "none", "NONE")
    if k == 0 and "none" not in g.ids:
        g.node("memnone", "Memory outcome\n(pending)" if status in ("pending", "running") else "Memory outcome\nnone", "mem", {"title": "Memory outcome"}, cls="mem pending")
        g.edge("update", "memnone")
    # ---- graph branch
    def gcall(key, nid, title, step, tkey):
        r = grp.get(key) if grp else None
        if r is None:
            g.node(nid, f"{title}\n(pending)" if (pend or grp is None) else f"{title}\n(not logged)", "llm", {"title": title}, cls="llm pending")
            return None
        raw = exp.raw(exp.ref(r)) or {}
        msgs = raw.get("messages") or []
        sysm = msgs[0]["content"] if msgs and msgs[0].get("role") == "system" else ""
        out = r.get("out")
        if key == "entities":
            lab, items = f"{title}\ntool extract_entities\n→ {len(out or [])} entities", [str(x) for x in (out or [])]
        elif key == "relations":
            lab, items = f"{title}\ntool establish_relationships\n→ {len(out or [])} relations", [f"{x.get('source')} —{x.get('relationship')}→ {x.get('destination')}" for x in (out or [])]
        else:
            lab, items = f"{title}\ntool delete_graph_memory\n→ {len(out or [])} deletion(s)", [f"{x.get('source')} —{x.get('relationship')}→ {x.get('destination')}" for x in (out or []) if isinstance(x, dict)]
        if r.get("err"):
            lab = f"{title}\n→ ERROR"
        blocks = [tpl_block(exp, tkey, sysm) if tkey in exp.templates and exp.templates[tkey].get("text") else
                  {"t": "kv", "label": "Template", "rows": [["file", exp.templates["entities"]["file"]], ["name", "EXTRACT_ENTITIES_TOOL + inline system prompt"]]},
                  {"t": "list", "label": "Answer (parsed)", "items": items}]
        if key == "delete" and msgs:
            blocks.insert(1, {"t": "pre", "label": "Existing relations found in Neo4j and given to this call (step 3 result)", "v": (msgs[-1]["content"].split("New Information")[0] if msgs else "")})
        blocks.append({"t": "llm", "ref": exp.ref(r), "label": "Full prompt in and raw answer out"})
        if r.get("err"):
            blocks.append({"t": "p", "v": "ERROR: " + str(r["err"])})
        g.node(nid, lab, "llm", {"title": f"{title} (graph branch, {step})", "subtitle": f"{r.get('seconds')} s · {r.get('time')}", "blocks": blocks}, cls="llm" + (" error" if r.get("err") else ""))
        return r
    gcall("entities", "ents", "Entity call", "step 1", "entities")
    gcall("relations", "rels", "Relation call", "step 2", "relations")
    gcall("delete", "gdel", "Delete-decision call", "step 4", "delete")
    g.edge("turns", "ents", "text")
    g.edge("ents", "rels", "entities")
    g.edge("rels", "gdel", "relations + existing")
    added = [r for lst in (fin or {}).get("graph_added") or [] for r in (lst or [])]
    deleted = [r for lst in (fin or {}).get("graph_deleted") or [] for r in (lst or [])]
    if fin:
        fmt = lambda r: f"{r.get('source')} —{r.get('relationship')}→ {r.get('target') or r.get('destination')}"
        g.node("gadd", f"Neo4j\n+ {len(added)} relation(s)" + ("\n" + clip("; ".join(fmt(r) for r in added[:3]), 120) if added else ""), "mem",
               {"title": "Relations added to Neo4j", "blocks": [{"t": "list", "items": [fmt(r) for r in added]}]}, cls="mem add")
        g.node("gdelete", f"Neo4j\n− {len(deleted)} relation(s)" + ("\n" + clip("; ".join(fmt(r) for r in deleted[:3]), 120) if deleted else ""), "mem",
               {"title": "Relations deleted from Neo4j", "blocks": [{"t": "list", "items": [fmt(r) for r in deleted]}]}, cls="mem del" if deleted else "mem none")
        g.edge("gdel", "gadd", "added")
        g.edge("gdel", "gdelete", "deleted")
    else:
        g.node("gadd", "Neo4j edges\n(pending)", "mem", {"title": "Neo4j edges"}, cls="mem pending")
        g.edge("gdel", "gadd")
    # errors on the batch as a whole
    if status in ("skipped", "retrying", "incomplete") or b["last_error"]:
        g.details["turns"]["blocks"].append({"t": "p", "v": f"BATCH {status.upper()}: {b['last_error'] or 'no successful add() result was logged'}"})
        g.el[0]["classes"] += " error"
    add_log = exp.addlog.get(c, {})
    sk = [s for s in add_log.get("skipped", []) if user in s]
    if sk:
        g.details["turns"]["blocks"].append({"t": "list", "label": "SKIPPED BATCH lines in the add log for this user", "items": sk[-5:]})
    meta = {"status": status, "seq": b["seq"], "total": len(exp.B[(c, user)]), "time": (fin or {}).get("time"), "seconds": (fin or {}).get("seconds")}
    return g.out(meta=meta)


def newest_batch(exp):
    best = None
    for (c, u), bl in exp.B.items():
        for b in bl:
            t = (b["final"] or {}).get("time") or (b["groups"][-1]["t1"] if b["groups"] else None)
            if t and (best is None or t > best[0]):
                best = (t, c, u, b["si"], b["bi"])
    return {"c": best[1], "user": best[2], "si": best[3], "bi": best[4], "time": best[0]} if best else None
