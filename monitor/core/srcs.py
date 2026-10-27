"""Read prompt templates from source files WITHOUT importing them (importing would write __pycache__ into the experiment)."""
import ast
import glob
from pathlib import Path


def get_const(path, name):
    try:
        src = Path(path).read_text()
        tree = ast.parse(src)
    except Exception:
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except Exception:
                try:
                    ns = {}
                    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
                    return ns.get(name)
                except Exception:
                    return None
    return None


def find_mem0_dir(folder):
    for pat in (".venv*/lib/python*/site-packages/mem0",):
        for p in sorted(glob.glob(str(Path(folder) / pat))):
            if Path(p, "configs", "prompts.py").exists():
                return Path(p)
    return None


def load_templates(folder):
    """name -> {"file": relative label, "name": constant, "text": str|None}"""
    f = Path(folder)
    m0 = find_mem0_dir(f)
    spec = [
        ("extract", f / "src/memzero/config.py", "custom_fact_extraction_prompt", "src/memzero/config.py"),
        ("update", (m0 / "configs/prompts.py") if m0 else None, "DEFAULT_UPDATE_MEMORY_PROMPT", "mem0/configs/prompts.py (mem0ai 1.0.11)"),
        ("relations", (m0 / "graphs/utils.py") if m0 else None, "EXTRACT_RELATIONS_PROMPT", "mem0/graphs/utils.py (mem0ai 1.0.11)"),
        ("delete", (m0 / "graphs/utils.py") if m0 else None, "DELETE_RELATIONS_SYSTEM_PROMPT", "mem0/graphs/utils.py (mem0ai 1.0.11)"),
        ("answer_graph", f / "prompts.py", "ANSWER_PROMPT_GRAPH", "prompts.py"),
        ("answer", f / "prompts.py", "ANSWER_PROMPT", "prompts.py"),
        ("judge", f / "metrics/llm_judge.py", "ACCURACY_PROMPT", "metrics/llm_judge.py"),
    ]
    out = {}
    for key, path, const, label in spec:
        out[key] = {"file": label, "name": const, "text": get_const(path, const) if path and Path(path).exists() else None}
    # entity extraction: the system prompt is an f-string inside mem0's graph code; report the tool instead
    out["entities"] = {"file": "mem0/graphs/tools.py (tool extract_entities) + mem0/memory/graph_memory.py", "name": "EXTRACT_ENTITIES_TOOL", "text": None}
    return out
