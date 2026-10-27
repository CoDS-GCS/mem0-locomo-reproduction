"""P3 memory state, P4 search, P5 judge, P6 journey, P7 overview."""
import json
import time
from collections import defaultdict

from jinja2 import Template

from . import analysis as AN
from .util import overlap, OVERLAP_MIN, f1_detail, simple_tokenize, date_verdict, rel_words, parse_session_date
from .views import G, clip, parse_existing, state_before, tpl_block
from .exp import fmt_t


# ======================================================================= prompts
def answer_prompt(exp, c, row):
    conv = exp.conv(c)
    tpl = exp.templates["answer_graph"]["text"]
    if not tpl:
        return None
    u1, u2 = conv["users"]
    s1 = json.dumps([f"{ts}: {m}" for m, ts, _ in row["speaker_1_memories"]], indent=4)
    s2 = json.dumps([f"{ts}: {m}" for m, ts, _ in row["speaker_2_memories"]], indent=4)
    gm = lambda x: None if x is None else [{"source": a, "relationship": b, "target": t} for a, b, t in x]
    return Template(tpl).render(speaker_1_user_id=u1.split("_")[0], speaker_2_user_id=u2.split("_")[0], speaker_1_memories=s1, speaker_2_memories=s2,
                                speaker_1_graph_memories=json.dumps(gm(row["speaker_1_graph_memories"]), indent=4),
                                speaker_2_graph_memories=json.dumps(gm(row["speaker_2_graph_memories"]), indent=4), question=row["question"])


def marks_in(prompt, needles):
    out = []
    for text, cls in needles:
        n = json.dumps(text)[1:-1]
        i = prompt.find(n)
        if i >= 0 and n:
            out.append({"start": i, "end": i + len(n), "cls": cls})
    return sorted(out, key=lambda m: m["start"])


def judge_prompt(exp, q, response):
    tpl = exp.templates["judge"]["text"]
    return tpl.format(question=q["question"], gold_answer=q["answer"], generated_answer=response) if tpl else None


# ======================================================================= P4
def search_groups_for(exp, uid, question):
    return exp.search_groups.get((uid, question.strip()), [])


def evidence_memories(A, uidx):
    """texts of memories born from the evidence turns of this question in store uidx: {text: label}"""
    out = {}
    hints = {}
    for t in A["turns"]:
        P = t["paths"][uidx]
        if P.get("chosen"):
            ch = P["chosen"]["versions"]
            if ch and ch[-1]["event"] != "DELETE":
                out[ch[-1]["text"]] = f"born in batch {P['batch']['bi'] + 1} of {P['batch']['skey']}" + (" (rewritten later)" if len(ch) > 1 else "")
        if P.get("alt") and P["alt"]["overlap"] >= (OVERLAP_MIN if "batch" in P and P.get("chosen") is not None or P.get("stages", {}).get("created") else AN.TEXT_ONLY_MIN):
            hints.setdefault(P["alt"]["text"], "text resembles the evidence turn")
    return out, hints


def question_view(exp, res, c, qi, show_all=False):
    conv = exp.conv(c)
    q = conv["qa"][qi]
    row = res.row(c, qi)
    A = AN.analyze(exp, res, c, qi)
    g = G()
    verd = A["verdicts"]
    g.node("q", f"Question\n{q['question']}", "data", {"title": "Question", "subtitle": f"conversation {c}, question {qi}, category {q['category']}", "blocks": [
        {"t": "kv", "rows": [["gold answer", q["answer"]], ["category", f"{q['category']} ({ {1: 'single-hop', 2: 'temporal', 3: 'multi-hop', 4: 'open-domain', 5: 'adversarial'}.get(q['category'], '?')})"], ["evidence", ", ".join(q["evidence"])]]},
        {"t": "nav", "label": "Follow this question through all stages", "href": f"#/journey?qs={c}:{qi}"}]}, cls="data")
    if row is None:
        g.node("pending", "Search stage\nnot reached yet for this question", "mem", {"title": "Pending", "blocks": [{"t": "p", "v": "results/…graph_True.json has no row for this question yet."}]}, cls="pending")
        g.edge("q", "pending")
        return g.out(meta={"has_row": False, "question": q, "analysis": brief(A)})
    users = conv["users"]
    for s, (u, key, gk, tk) in enumerate([(users[0], "speaker_1_memories", "speaker_1_graph_memories", "speaker_1_memory_time"),
                                          (users[1], "speaker_2_memories", "speaker_2_graph_memories", "speaker_2_memory_time")]):
        mems = row[key]
        evm, hints = evidence_memories(A, s)
        sid = f"s{s}"
        top_items = []
        hit_ranks = []
        for i, (text, ts, sc) in enumerate(mems):
            tag = "evidence" if text in evm else ("hint" if text in hints else "")
            if tag:
                hit_ranks.append(i + 1)
            top_items.append(f"#{i + 1}  score {sc}  [{ts}]  {text}" + (f"   ◀ {evm.get(text) or hints.get(text)}" if tag else ""))
        g.node(f"{sid}:top", f"Top {len(mems)} from Qdrant\n{u}\nsearch {row[tk]:.2f} s" + (f"\nevidence at rank {', '.join(map(str, hit_ranks))}" if hit_ranks else ""), "mem",
               {"title": f"Top {len(mems)} memories of {u} (memory.search, limit=30)", "subtitle": f"search latency {row[tk]:.3f} s (memory + graph search together)",
                "blocks": [{"t": "list", "label": "Ranked memories (score, session date, text)", "items": top_items}]}, cls="mem")
        g.edge("q", f"{sid}:top", "embed + search")
        shown = 0
        for i, (text, ts, sc) in enumerate(mems):
            tag = "evidence" if text in evm else ("hint" if text in hints else "")
            if show_all or i < 5 or tag:
                nid = f"{sid}:m{i}"
                g.node(nid, f"#{i + 1} · {sc}\n{clip(text, 90)}", "mem", {"title": f"Rank {i + 1}, score {sc}", "subtitle": ts, "blocks": [{"t": "pre", "label": "memory", "v": text}] + (
                    [{"t": "p", "v": "◀ " + (evm.get(text) or hints.get(text))}] if tag else [])}, cls="mem rank" + (" evidence" if tag == "evidence" else " hint" if tag else ""))
                g.edge(f"{sid}:top", nid)
                g.edge(nid, "prompt")
                shown += 1
        if shown < len(mems):
            g.node(f"{sid}:more", f"… {len(mems) - shown} more\n(click Top node for the list)", "mem", {"title": "More memories", "blocks": [{"t": "p", "v": "Use 'show all 30' above the graph to draw every rank."}]}, cls="mem pending")
            g.edge(f"{sid}:top", f"{sid}:more")
            g.edge(f"{sid}:more", "prompt")
        if not hit_ranks:
            exp_text = next(iter(evm), None)
            lab = "Evidence memory\n" + (clip(exp_text, 100) if exp_text else ("no stored memory resembles the evidence turn" if exp.has_addlogs else "unknown: no add-stage logs in this run"))
            g.node(f"{sid}:ev", lab, "mem", {"title": "Evidence memory (expected)"}, cls="mem ghost")
            g.edge(f"{sid}:ev", f"{sid}:top", "evidence memory not retrieved", cls="loss")
        # graph branch
        calls = search_groups_for(exp, u, q["question"])
        call = calls[-1] if calls else None
        rels = row[gk] or []
        if call:
            g.node(f"{sid}:ent", f"Entity call on the question\n→ {len(call.get('out') or [])} entities", "llm", {"title": "Entity extraction on the question (search stage)", "subtitle": f"{call.get('seconds')} s · {call.get('time')}", "blocks": [
                {"t": "list", "label": "Entities", "items": [str(x) for x in call.get("out") or []]}, {"t": "llm", "ref": exp.ref(call), "label": "Full prompt and raw answer"}]}, cls="llm")
            names = call.get("out") or []
        else:
            g.node(f"{sid}:ent", "Entity call on the question\n" + ("(not in logs/llm_other.jsonl)" if exp.has_addlogs else "(not logged in this run)"), "llm", {"title": "Entity extraction on the question"}, cls="llm pending")
            names = []
        g.edge("q", f"{sid}:ent", "graph search")
        chk = ""
        if exp.mode == "neo4j" and names:
            from . import stores
            r = stores.neo4j_has_nodes(exp, u, [str(n).lower().replace(" ", "_") for n in names])
            chk = f"\nexact-name check: {len(r.get('found', []))} of {len(set(names))} exist" if "found" in r else ""
        g.node(f"{sid}:nodes", f"Matched Neo4j nodes\n(similarity match; not logged){chk}", "mem", {"title": "Matched Neo4j nodes", "blocks": [{"t": "p", "v": "Mem0 matches the entities to nodes by embedding similarity inside Neo4j. This step is not written to any log, so it cannot be shown. The exact-name check (if shown) only asks whether a node with the same normalised name exists."}]}, cls="mem pending")
        g.edge(f"{sid}:ent", f"{sid}:nodes")
        g.node(f"{sid}:rel", f"Relations kept (≤5, BM25)\n{len(rels)}", "mem", {"title": "Graph relations kept for the prompt", "blocks": [{"t": "list", "items": [f"{a} —{b}→ {t}" for a, b, t in rels]}]}, cls="mem")
        g.edge(f"{sid}:nodes", f"{sid}:rel", "BM25 top 5")
        g.edge(f"{sid}:rel", "prompt")
    prompt = answer_prompt(exp, c, row)
    needles = []
    for s in (0, 1):
        evm, hints = evidence_memories(A, s)
        needles += [(f"{ts}: {m}", "ev") for m, ts, _ in row["speaker_1_memories" if s == 0 else "speaker_2_memories"] if m in evm]
        needles += [(f"{ts}: {m}", "hint") for m, ts, _ in row["speaker_1_memories" if s == 0 else "speaker_2_memories"] if m in hints and m not in evm]
    g.node("prompt", f"Exact answer prompt\nANSWER_PROMPT_GRAPH\n{len(prompt or '')} characters", "llm", {"title": "The exact prompt the answer model receives", "subtitle": "rebuilt with jinja2 exactly as src/memzero/search.py does", "blocks": [
        tpl_block(exp, "answer_graph", prompt), {"t": "prompt", "text": prompt or "(template not readable)", "marks": marks_in(prompt or "", needles)},
        {"t": "p", "v": "Highlighted: memories born from the evidence turns (purple) or that look like them by text match (light)."}]}, cls="llm")
    resp = row["response"]
    jv = f"\njudge: {sum(verd.values())} of {len(verd)} runs CORRECT" if verd else ""
    g.node("resp", f"Model answer\n{clip(resp, 140)}\nanswer call {row['response_time']:.2f} s{jv}", "coral", {"title": "Model answer", "subtitle": f"answer latency {row['response_time']:.3f} s", "blocks": [
        {"t": "pre", "label": "response", "v": resp}, {"t": "nav", "label": "Open the judge page", "href": f"#/judge?conv={c}&q={qi}"}]},
           cls="coral" + (" correct" if verd and sum(verd.values()) * 2 >= len(verd) else " wrong" if verd else ""))
    g.edge("prompt", "resp", "Gemini answer call")
    g.node("gold", f"Gold answer\n{q['answer']}", "data", {"title": "Gold answer", "blocks": [{"t": "pre", "v": q["answer"]}]}, cls="data")
    g.edge("resp", "gold", "compared")
    return g.out(meta={"has_row": True, "question": q, "analysis": brief(A), "search_s": [row["speaker_1_memory_time"], row["speaker_2_memory_time"]], "answer_s": row["response_time"]})


def brief(A):
    return {"reason": A.get("reason"), "reason_text": A.get("reason_text"), "issues": A.get("issues", []), "level": A.get("level"), "correct": A.get("correct"), "n_runs": A.get("n_runs")}


# ======================================================================= P5
def judge_view(exp, res, c, qi):
    conv = exp.conv(c)
    q = conv["qa"][qi]
    row = res.row(c, qi)
    verd, erow = res.verdicts(c, qi, conv["qa"])
    out = {"question": q, "has_row": row is not None, "verdicts": {str(k): v for k, v in sorted(verd.items())}, "n_runs": len(verd)}
    if erow is None and row is None:
        out["pending"] = True
        return out
    response = (erow or row)["response"]
    out["response"] = response
    out["prompt"] = judge_prompt(exp, q, response)
    out["template"] = {"file": exp.templates["judge"]["file"], "name": exp.templates["judge"]["name"]}
    if erow:
        out["f1"], out["bleu1"] = erow["f1_score"], erow["bleu_score"]
        d = f1_detail(response, q["answer"])
        common = set(d["common"])
        out["pred_tokens"] = [[t, t in common] for t in simple_tokenize(response)]
        out["gold_tokens"] = [[t, t in common] for t in simple_tokenize(q["answer"])]
        out["precision"], out["recall"] = d.get("precision"), d.get("recall")
    out["j"] = res.j_summary()
    out["category"] = q["category"]
    return out


# ======================================================================= P6
def edge_text(r):
    return f"{r.get('source')} {r.get('relationship')} {r.get('target') or r.get('destination')}".replace("_", " ")


def edge_fates(exp, c, user, seq, added):
    """for each added relation: the first later batch that deleted it (dict) or None"""
    key = lambda r: (r.get("source"), r.get("relationship"), r.get("target") or r.get("destination"))
    want = {key(r): None for r in added}
    for b in exp.B.get((c, user), []):
        if b["seq"] <= seq or not b["final"]:
            continue
        for lst in b["final"].get("graph_deleted") or []:
            for r in lst or []:
                k = key(r)
                if k in want and want[k] is None:
                    want[k] = {"seq": b["seq"], "skey": b["skey"], "bi": b["bi"]}
        if all(want.values()):
            break
    return [want[key(r)] for r in added]


def journey_view(exp, res, qids):
    g = G()
    summary = []
    for c, qi in qids:
        conv = exp.conv(c)
        if conv is None or qi >= len(conv["qa"]):
            continue
        A = AN.analyze(exp, res, c, qi)
        q = A["q"]
        row = res.row(c, qi)
        qn = f"q:{c}:{qi}"
        g.node(qn, f"Question {c}:{qi}\n{clip(q['question'], 90)}\ncategory {q['category']}", "data", {"title": "Question", "subtitle": f"conversation {c}, question {qi}", "blocks": [
            {"t": "kv", "rows": [["gold answer", q["answer"]], ["category", str(q["category"])], ["evidence", ", ".join(q["evidence"])], ["temporal question (date checks apply)", "yes" if A["temporal"] else "no"]]},
            {"t": "nav", "label": "Search stage page", "href": f"#/question?conv={c}&q={qi}"}, {"t": "nav", "label": "Judge page", "href": f"#/judge?conv={c}&q={qi}"}]}, cls="data")
        loss = {"reason": A["reason"], "text": A["reason_text"], "issues": A.get("issues", [])}
        first_loss_edge = None   # (src, dst)
        tg = A["turns"]
        # which turn / user carries the first loss
        lt, lu = A.get("loss_turn"), A.get("loss_user")
        prompt_id, gold_id, ans_id, judge_id = f"p:{c}:{qi}", f"gold:{c}:{qi}", f"a:{c}:{qi}", f"j:{c}:{qi}"
        for t in tg:
            dia = t["dia"]
            conv_turn = None
            for P in t["paths"]:
                if P.get("turn_text") is not None:
                    conv_turn = P
                    break
            tid = f"t:{c}:{dia}"
            if conv_turn:
                tr = rel_words(conv_turn["turn_text"])
                g.node(tid, f"Evidence {dia}\n{conv_turn['session_date']}" + (" ⏱" if tr else "") + f"\n{clip(conv_turn['turn_text'], 80)}", "data", {"title": f"Evidence turn {dia}", "subtitle": conv_turn["session_date"], "blocks": [
                    {"t": "pre", "label": "text", "v": conv_turn["turn_text"]}, {"t": "p", "v": "Relative time words: " + (", ".join(tr) or "none")},
                    {"t": "nav", "label": "Open in the dataset page", "href": f"#/dataset?conv={c}&dia={dia}"}]}, cls="data")
            else:
                g.node(tid, f"Evidence {dia}\n(not found in dataset)", "data", {"title": "Evidence turn missing"}, cls="data ghost")
            g.edge(qn, tid, "evidence")
            for P in t["paths"]:
                u = P["user"]
                uidx = P["uidx"]
                is_main = t["dia"] == lt and u == lu
                prev = tid
                # ---- add stage nodes
                if exp.has_addlogs and P.get("batch"):
                    b = next((x for x in exp.B[(c, u)] if x["seq"] == P["batch"]["seq"]), None)
                    xid = f"x:{c}:{u}:{P['batch']['seq']}"
                    facts = P.get("facts") or []
                    bestf = max(facts, key=lambda f: f[1] or 0)[0] if facts else None
                    st = P["batch"]["status"]
                    g.node(xid, f"Batch {P['batch']['bi'] + 1} · {u}\n" + (f"{len(facts)} fact(s): {clip(bestf, 70)}" if facts else ("no facts extracted" if st == "ok" else f"batch {st}")), "llm", {"title": f"Extraction in batch {P['batch']['bi'] + 1} of {P['batch']['skey']} ({u})", "blocks": [
                        {"t": "list", "label": "Facts out (overlap with the evidence turn)", "items": [f"{f}   [overlap {o:.2f}]" if o is not None else f for f, o in facts]},
                        {"t": "nav", "label": "Open this batch pipeline", "href": f"#/add?conv={c}&user={u}&si={b['si'] if b else 0}&bi={b['bi'] if b else 0}"}]}, cls="llm" + (" pending" if st != "ok" else ""))
                    g.edge(tid, xid, "2-turn batch")
                    prev = xid
                    ch = (P.get("chosen") or {}).get("versions") or []
                    vids = []
                    for v in ch:
                        vid = f"m:{u}:{(P['chosen']['id'])}:v{v['v']}"
                        dv = date_verdict(P["turn_text"], v["text"] or "", P["session_date"]) if v["event"] != "DELETE" else None
                        g.node(vid, f"v{v['v']} {v['event']}\n{clip(v['text'], 100)}", "mem", {"title": f"Memory version v{v['v']} ({v['event']})", "subtitle": f"{u} · batch {v['bi'] + 1} of {v['skey']}", "blocks": [
                            {"t": "diff", "label": "before → after", "a": v["prev"] or "", "b": v["text"] or ""} if v["event"] == "UPDATE" else {"t": "pre", "label": "memory text", "v": v["text"] or ""},
                            {"t": "kv", "label": "Temporal check (heuristic)", "rows": [["relative words in the evidence turn", ", ".join(dv["words"]) or "none"], ["dates written in memory", ", ".join(dv["mentions"]) or "none"], ["expected", "; ".join(dv.get("expected", [])) or "n/a"], ["verdict", dv["label"].replace("_", " ")]]} if dv and dv["label"] != "none" else {"t": "p", "v": "No relative time word in the evidence turn: no date check."},
                            {"t": "nav", "label": "Open in the Memory page", "href": f"#/memory?conv={c}&user={u}&mem={P['chosen']['id']}"}]},
                                cls="mem " + {"ADD": "add", "UPDATE": "upd", "DELETE": "del"}.get(v["event"], ""))
                        vids.append((v, vid))
                    for i in range(1, len(vids)):
                        g.edge(vids[i - 1][1], vids[i][1], vids[i][0]["event"].lower())
                    if vids:
                        bv = next((vid for v, vid in vids if v["v"] == P["chosen"]["birth_v"]), vids[0][1])
                        g.edge(xid, bv, "memory created")
                        lastv = vids[-1][1]
                        prev = lastv
                        if is_main and A["reason"] in ("date_invented", "date_dropped"):
                            first_loss_edge = (xid, bv)
                        if is_main and A["reason"] in ("overwritten", "deleted") and P.get("lost_v"):
                            lv = next((vid for v, vid in vids if v["v"] == P["lost_v"]), None)
                            pv = next((vid for v, vid in vids if v["v"] == P["lost_v"] - 1), None)
                            if lv and pv:
                                first_loss_edge = (pv, lv)
                    else:
                        gh = f"ghost:{c}:{u}:{P['batch']['seq']}"
                        g.node(gh, "no memory\n" + ("created" if st == "ok" else "yet"), "mem", {"title": "No memory"}, cls="mem ghost")
                        g.edge(xid, gh, "update call")
                        prev = gh
                        if is_main and A["reason"] in ("no_fact", "none_decision"):
                            first_loss_edge = (xid, gh)
                    # graph edges added in this batch
                    if b and b["final"]:
                        added = [r for lst in b["final"].get("graph_added") or [] for r in (lst or [])]
                        fates = edge_fates(exp, c, u, b["seq"], added)
                        gid = f"ge:{c}:{u}:{b['seq']}"
                        ndel = sum(1 for f in fates if f)
                        rel_i = [i for i, r in enumerate(added) if (overlap(P["turn_text"], edge_text(r)) or 0) >= 0.2]
                        items = [f"{'◀ ' if i in rel_i else ''}{edge_text(r)}" + (f"   — DELETED in batch {fates[i]['bi'] + 1} of {fates[i]['skey']}" if fates[i] else "   — still in the graph (as far as the logs show)") for i, r in enumerate(added)]
                        rel_del = [i for i in rel_i if fates[i]]
                        g.node(gid, f"Neo4j edges added: {len(added)}" + (f"\n{ndel} deleted by later batches" if ndel else "") + (f"\n◀ relevant edge deleted in batch {fates[rel_del[0]]['bi'] + 1}" if rel_del else ""), "mem",
                               {"title": "Graph relations added in this batch, and their fate", "blocks": [{"t": "list", "label": "◀ = shares words with the evidence turn", "items": items},
                                                                                                          {"t": "p", "v": "Deletions are read from the later batches' graph_deleted lists in events_*.jsonl (the delete-decision call)."}]}, cls="mem " + ("del" if rel_del else "add"))
                        g.edge(xid, gid, "graph branch")
                elif not exp.has_addlogs:
                    nid = f"noadd:{c}"
                    g.node(nid, "Add stage\nnot logged in this run", "mem", {"title": "No add-stage logs", "blocks": [{"t": "p", "v": "This (Kuzu) run has no events or LLM logs, so the steps between the evidence turn and the retrieved memories cannot be shown."}]}, cls="mem ghost")
                    g.edge(tid, nid)
                    prev = nid
                # ---- retrieval node
                rid = f"r:{c}:{qi}:{u}"
                if row is None:
                    g.node(rid, f"Retrieval · {u}\n(search stage not reached)", "mem", {"title": "Pending"}, cls="mem pending")
                else:
                    mems = row["speaker_1_memories" if uidx == 0 else "speaker_2_memories"]
                    rk, sc = P.get("rank"), P.get("score")
                    alt = P.get("alt")
                    if rk:
                        lab = f"Retrieval · {u}\nrank {rk} of {len(mems)}, score {sc}"
                    elif alt and not exp.has_addlogs:
                        lab = f"Retrieval · {u}\nrank {alt['rank']}, score {alt['score']} (text match)"
                    elif P.get("final_rank"):
                        lab = f"Retrieval · {u}\nrank {P['final_rank']}, score {P['final_score']}\nbut this memory was rewritten: it no longer holds the evidence"
                    else:
                        lab = f"Retrieval · {u}\nnot retrieved (not in top {len(mems)})"
                    g.node(rid, lab, "mem", {"title": f"Top {len(mems)} of {u}", "blocks": [{"t": "list", "label": "Ranked memories", "items": [f"#{i + 1}  {s}  [{ts}]  {m}" for i, (m, ts, s) in enumerate(mems)]}]}, cls="mem" + ("" if (rk or P.get("final_rank") or (alt and not exp.has_addlogs)) else " ghost"))
                    if is_main and A["reason"] == "not_retrieved":
                        first_loss_edge = (prev, rid)
                g.edge(prev, rid, "search" if row is not None else "")
                g.edge(rid, prompt_id)
        # ---- prompt, answer, judge
        if row is None:
            for nid, lab in ((prompt_id, "Exact answer prompt\n(pending)"), (ans_id, "Model answer\n(pending)"), (judge_id, "Judge\n(pending)")):
                g.node(nid, lab, "llm" if nid == prompt_id else "coral", {"title": "Pending"}, cls=("llm" if nid == prompt_id else "coral") + " pending")
        else:
            prompt = answer_prompt(exp, c, row)
            evt = []
            for s in (0, 1):
                evm, hints = evidence_memories(A, s)
                key = "speaker_1_memories" if s == 0 else "speaker_2_memories"
                evt += [(f"{ts}: {m}", "ev") for m, ts, _ in row[key] if m in evm or m in hints]
            g.node(prompt_id, f"Exact answer prompt\n{len(prompt or '')} chars · top 30 + ≤5 relations ×2", "llm", {"title": "Exact answer prompt", "blocks": [{"t": "prompt", "text": prompt or "", "marks": marks_in(prompt or "", evt)}]}, cls="llm")
            g.node(ans_id, f"Model answer\n{clip(row['response'], 100)}", "coral", {"title": "Model answer", "subtitle": f"{row['response_time']:.2f} s", "blocks": [{"t": "pre", "v": row["response"]}]}, cls="coral")
            g.edge(prompt_id, ans_id, "answer call")
            verd = A["verdicts"]
            if verd:
                ok = sum(verd.values())
                g.node(judge_id, f"Judge verdict\n{ok} of {len(verd)} runs CORRECT", "coral", {"title": "Judge", "blocks": [{"t": "kv", "rows": [[f"run {k}", "CORRECT" if v else "WRONG"] for k, v in sorted(verd.items())]}, {"t": "nav", "label": "Judge page", "href": f"#/judge?conv={c}&q={qi}"}]}, cls="coral " + ("correct" if ok * 2 >= len(verd) else "wrong"))
            else:
                g.node(judge_id, "Judge verdict\n(pending)", "coral", {"title": "Pending"}, cls="coral pending")
            g.edge(ans_id, judge_id, "judged")
            if A["reason"] == "wrong":
                first_loss_edge = (prompt_id, ans_id)
        g.node(gold_id, f"Gold answer\n{q['answer']}", "data", {"title": "Gold answer", "blocks": [{"t": "pre", "v": q["answer"]}]}, cls="data")
        g.edge(gold_id, judge_id, "compare")
        if first_loss_edge:
            a, b2 = first_loss_edge
            eid = f"e:{a}>{b2}"
            for e in g.el:
                if e["data"].get("id") == eid:
                    e["classes"] = (e["classes"] + " loss").strip()
                    e["data"]["label"] = A["reason_text"]
        summary.append({"c": c, "qi": qi, "question": q["question"], "gold": q["answer"], "category": q["category"], "reason": A["reason"], "reason_text": A["reason_text"],
                        "issues": [AN.REASONS[i] for i in A.get("issues", [])], "level": A["level"], "correct": A["correct"], "answered_ok_despite_loss": A.get("answered_ok_despite_loss"), "n_runs": A["n_runs"],
                        "pending": (not A["has_row"])})
    return g.out(summary=summary)


# ======================================================================= P3
def memory_state(exp, c, user):
    chains = exp.chains.get(user, {})
    sess_date = {(b["seq"]): b["date"] for b in exp.B.get((c, user), [])}
    mems = []
    for mid, ch in chains.items():
        alive = ch[-1]["event"] != "DELETE"
        mems.append({"id": mid, "alive": alive, "text": ch[-1]["text"], "born": sess_date.get(ch[0]["seq"]), "updated": sess_date.get(ch[-1]["seq"]),
                     "versions": [{"v": v["v"], "event": v["event"], "text": v["text"], "prev": v["prev"], "seq": v["seq"], "skey": v["skey"], "bi": v["bi"], "date": sess_date.get(v["seq"]), "time": v["time"]} for v in ch]})
    mems.sort(key=lambda m: m["versions"][0]["seq"])
    alive_n = sum(1 for m in mems if m["alive"])
    return {"user": user, "memories": mems, "alive": alive_n, "total": len(mems)}


def replay(exp, c, user):
    steps = []
    for b in exp.B.get((c, user), []):
        fin = b["final"]
        if not fin:
            continue
        steps.append({"seq": b["seq"], "skey": b["skey"], "bi": b["bi"], "date": b["date"], "time": fin.get("time"),
                      "mem": [[e.get("id"), e.get("event"), e.get("memory"), e.get("previous_memory")] for e in fin.get("memory_events") or []],
                      "gadd": [[r.get("source"), r.get("relationship"), r.get("target") or r.get("destination")] for lst in fin.get("graph_added") or [] for r in (lst or [])],
                      "gdel": [[r.get("source"), r.get("relationship"), r.get("target") or r.get("destination")] for lst in fin.get("graph_deleted") or [] for r in (lst or [])]})
    return {"user": user, "steps": steps, "total_batches": len(exp.B.get((c, user), []))}
