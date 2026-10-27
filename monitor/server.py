#!/usr/bin/env python3
"""Memory Journey: read-only monitor for a Mem0 LOCOMO experiment folder.

    python server.py ~/mem0-repro/paper-eval-neo4j-gemini            -> http://127.0.0.1:8731

Binds to 127.0.0.1 only. Never writes inside the experiment folder; never opens Kuzu files.
"""
import argparse
import logging
import sys
import threading
import time
import traceback
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

sys.path.insert(0, str(Path(__file__).parent))
from core.exp import Exp, fmt_t                      # noqa: E402
from core.results import Results                     # noqa: E402
from core import views, views2, overview, stores     # noqa: E402

HERE = Path(__file__).parent
app = Flask(__name__, static_folder=str(HERE / "static"), static_url_path="/static")
EXP: Exp = None
RES: Results = None
STATE = {"ready": False, "indexing_since": None, "last_error": None, "demand": 0.0}


def worker(period=15):
    first = True
    while True:
        try:
            t = time.time()
            EXP.refresh()
            if first or time.time() - STATE["demand"] < 180:
                RES.refresh(force=first)
            first = False
            STATE["ready"] = True
            STATE["last_error"] = None
        except Exception as e:
            STATE["last_error"] = f"{type(e).__name__}: {e}"
            traceback.print_exc()
        time.sleep(period)


def api(fn):
    def wrapper(*a, **kw):
        try:
            return jsonify(fn(*a, **kw))
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": f"{type(e).__name__}: {e}"}), 500
    wrapper.__name__ = fn.__name__
    return wrapper


def want_results():
    STATE["demand"] = time.time()


def qs_arg():
    out = []
    for part in (request.args.get("qs") or "").split(","):
        if ":" in part:
            a, b = part.split(":", 1)
            if a.isdigit() and b.isdigit():
                out.append((int(a), int(b)))
    return out[:12]


@app.get("/")
def index():
    return send_from_directory(HERE / "static", "index.html")


@app.get("/api/meta")
@api
def meta():
    want_results()
    return {"ready": STATE["ready"], "error": STATE["last_error"], "folder": str(EXP.dir), "name": EXP.dir.name, "mode": EXP.mode, "mode_source": EXP.mode_source,
            "has_addlogs": EXP.has_addlogs, "collection": EXP.collection, "model": EXP.public_env.get("MODEL"), "env": EXP.public_env,
            "convs": [{"idx": c["idx"], "a": c["a"], "b": c["b"], "sessions": len(c["sessions"]), "questions": len(c["qa"]),
                       "turns": sum(len(s["turns"]) for s in c["sessions"])} for c in EXP.ds.convs],
            "stage": EXP.runner.get("stage"), "version": EXP.version, "res_version": RES.version, "refreshed": fmt_t(EXP.last_refresh), "now": fmt_t(time.time()),
            "templates": {k: {"file": v["file"], "name": v["name"], "found": bool(v["text"])} for k, v in EXP.templates.items()}}


# ------------------------------------------------------------------ P1
@app.get("/api/dataset/conv/<int:c>")
@api
def ds_conv(c):
    return views.dataset_conv(EXP, c)


@app.get("/api/dataset/session/<int:c>/<int:si>")
@api
def ds_session(c, si):
    return views.dataset_session(EXP, c, si)


# ------------------------------------------------------------------ P2
@app.get("/api/add/session")
@api
def add_session():
    c, u, si = int(request.args["conv"]), request.args["user"], int(request.args["si"])
    return {"batches": views.session_batches(EXP, c, u, si)}


@app.get("/api/add/batch")
@api
def add_batch():
    return views.batch_view(EXP, int(request.args["conv"]), request.args["user"], int(request.args["si"]), int(request.args["bi"]))


@app.get("/api/add/live")
@api
def add_live():
    return {"newest": views.newest_batch(EXP), "version": EXP.version}


@app.get("/api/llm")
@api
def llm_raw():
    rec = EXP.raw(request.args.get("ref", ""))
    if rec is None:
        return {"error": "unknown reference"}
    return {"time": rec.get("time"), "thread": rec.get("thread"), "llm": rec.get("llm"), "tools": rec.get("tools"), "messages": rec.get("messages"),
            "response": rec.get("response"), "seconds": rec.get("seconds"), "error": rec.get("error")}


# ------------------------------------------------------------------ P3
@app.get("/api/memory/state")
@api
def mem_state():
    return views2.memory_state(EXP, int(request.args["conv"]), request.args["user"])


@app.get("/api/memory/replay")
@api
def mem_replay():
    return views2.replay(EXP, int(request.args["conv"]), request.args["user"])


@app.get("/api/memory/live")
@api
def mem_live():
    u = request.args["user"]
    q = stores.qdrant_user(EXP, u)
    n = stores.neo4j_user(EXP, u) if EXP.mode == "neo4j" else {"error": "Neo4j is only read in Neo4j mode (Kuzu files are never opened)"}
    st = views2.memory_state(EXP, int(request.args["conv"]), u) if EXP.has_addlogs else None
    return {"qdrant": q, "neo4j": n, "log_alive": st["alive"] if st else None}


# ------------------------------------------------------------------ P4 / P5 / P6
@app.get("/api/questions")
@api
def questions():
    want_results()
    c = int(request.args["conv"])
    conv = EXP.conv(c)
    out = []
    for q in conv["qa"]:
        verd, _ = RES.verdicts(c, q["qi"], conv["qa"])
        out.append({"qi": q["qi"], "question": q["question"], "answer": q["answer"], "category": q["category"], "evidence": q["evidence"],
                    "answered": RES.row(c, q["qi"]) is not None, "judged": len(verd), "correct": sum(verd.values()) if verd else None})
    return {"questions": out, "answered": len(RES.rows.get(c, []))}


@app.get("/api/question")
@api
def question():
    want_results()
    return views2.question_view(EXP, RES, int(request.args["conv"]), int(request.args["q"]), show_all=request.args.get("all") == "1")


@app.get("/api/judge")
@api
def judge():
    want_results()
    return views2.judge_view(EXP, RES, int(request.args["conv"]), int(request.args["q"]))


@app.get("/api/journey")
@api
def journey():
    want_results()
    return views2.journey_view(EXP, RES, qs_arg())


# ------------------------------------------------------------------ P7
@app.get("/api/overview")
@api
def ov():
    want_results()
    return overview.progress(EXP, RES)


@app.get("/api/funnel")
@api
def fun():
    want_results()
    return overview.funnel(EXP, RES)


@app.get("/api/funnel/list")
@api
def fun_list():
    return overview.funnel_list(EXP, RES, request.args.get("cat", "all"), int(request.args.get("step", 1)), request.args.get("mode", "drop"))


@app.get("/api/lens")
@api
def lens():
    want_results()
    return overview.lens(EXP, RES)


def main():
    global EXP, RES
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="experiment folder, e.g. ~/mem0-repro/paper-eval-neo4j-gemini")
    ap.add_argument("--port", type=int, default=8731)
    ap.add_argument("--period", type=int, default=15, help="seconds between incremental log reads")
    a = ap.parse_args()
    EXP = Exp(a.folder)
    RES = Results(EXP.dir)
    if not (EXP.dir / "dataset" / "locomo10.json").exists():
        sys.exit(f"{EXP.dir}/dataset/locomo10.json not found")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    threading.Thread(target=worker, args=(a.period,), daemon=True).start()
    print(f"Memory Journey on http://127.0.0.1:{a.port}  (folder {EXP.dir}, mode {EXP.mode}, read-only)", flush=True)
    app.run(host="127.0.0.1", port=a.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
