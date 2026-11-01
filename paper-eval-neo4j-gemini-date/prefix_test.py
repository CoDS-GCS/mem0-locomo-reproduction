"""Which way of writing the date in front of each turn makes Gemini resolve "last week", "yesterday" ... best?
Calls ONLY Mem0's fact extractor, exactly as Mem0 1.0.11 calls it (same system prompt = authors' instructions,
same "Input:" text, same JSON mode). Nothing is stored. About 4 x 60 small Flash-Lite calls (a few cents), ~5 min.
Run from the Exp 5 folder, venv active:
    python prefix_test.py            (conversations 0 1 2)
    python prefix_test.py 0 1 2 3    (more conversations)

Cases: every LOCOMO temporal question whose evidence turn says "yesterday", "last week", "last Friday",
"two days ago", "last month", "last year" ... ; the batch is the one add.py sends for that turn.
Variants of the text Gemini receives:
  V0  Caroline: I went to a support group yesterday                     (= Exp 4, no date)
  V1  [1:56 pm on 8 May, 2023] Caroline: ...                           (= Exp 5 as run on conversation 0)
  V2  [sent on 8 May, 2023 at 1:56 pm] Caroline: ...
  V3  [today is 8 May, 2023] Caroline: ...
For the facts about that event it computes the date the phrase really means (e.g. "last Friday" said on Saturday
15 July 2023 -> Friday 14 July) and labels each:
  CORRECT    the fact has the right date (or right month/year for "last month"/"last year")
  KEPT       no conflicting date, the phrase is kept ("last week", "the previous Friday" ...): the answer step can
             still compute it from the memory's timestamp
  SESSION    the event is put ON the session day ("On July 15, 2023, Caroline attended ...")  <- the problem
  WRONG      another wrong date
  LOST       no date and no phrase
  NO FACT    no fact about that event
"""
import contextlib
import datetime as dt
import io
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path.cwd()
if HERE.name != "paper-eval-neo4j-gemini-date":
    sys.exit("STOP: run this from ~/mem0-repro/paper-eval-neo4j-gemini-date")
sys.path.insert(0, str(HERE))
CONVS = [int(x) for x in sys.argv[1:]] or [0, 1, 2]
os.environ["QDRANT_COLLECTION"] = "smoke_prefix_test"
os.environ["LLM_LOG"] = "logs/smoke/prefix_llm"
os.environ["EVENTS_LOG"] = "logs/smoke/prefix_events"
os.environ.pop("START_CONV", None)
pathlib.Path("logs/smoke").mkdir(parents=True, exist_ok=True)
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

MONTHS = {m.lower(): i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                               "September", "October", "November", "December"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
MON = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
YEAR = r"((?:19|20)\d\d)"
# (regex, groups, granularity)
PATTERNS = [(re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*[-–]\s*\d{{1,2}}(?:st|nd|rd|th)?)?(?: of)? {MON},? {YEAR}\b", re.I), ("d", "m", "y"), "day"),
            (re.compile(rf"\b{MON} (\d{{1,2}})(?:st|nd|rd|th)?(?:\s*[-–]\s*\d{{1,2}}(?:st|nd|rd|th)?)?,? {YEAR}\b", re.I), ("m", "d", "y"), "day"),
            (re.compile(rf"\b{YEAR}-(\d\d)-(\d\d)\b"), ("y", "m", "d"), "day"),
            (re.compile(rf"\b{MON},? {YEAR}\b", re.I), ("m", "y"), "month"),
            (re.compile(rf"\b(?:in|of|around|during|since|from) {YEAR}\b", re.I), ("y",), "year")]
WD = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
NUM = {"a": 1, "one": 1, "a couple of": 2, "couple of": 2, "two": 2, "three": 3, "four": 4, "five": 5, "a few": 3, "few": 3}
PHRASE = re.compile(r"\b(yesterday|last night|the other day|last (?:week|weekend|month|year|summer|winter|spring|fall|"
                    + "|".join(WD) + r")|(a couple of|a few|a|one|two|three|four|five|\d+) (day|week|month|year)s? ago)\b", re.I)
KEPT = re.compile(r"\b(yesterday|last night|the other day|last (?:week|weekend|month|year|" + "|".join(WD) + r")|"
                  r"(?:the )?previous (?:day|night|week|weekend|month|year|" + "|".join(WD) + r")|the (?:day|week|weekend|"
                  r"month|year|night) before|(?:a|one|two|three|four|five|\d+|a few|a couple of) (?:days?|weeks?|months?|"
                  r"years?) (?:ago|earlier|before)|prior week)\b", re.I)
STOP = set("that this with from have been were they them their there what when which about would could should really just "
           "like also your into over some very much more than then here know think going said went last week weekend "
           "yesterday days month months year years night since spoke things happened great awesome today ago other couple".split())
words = lambda t: {w for w in re.findall(r"[a-z]{4,}", (t or "").lower()) if w not in STOP}


def dates_in(text):
    out, taken = [], []
    for rx, order, gran in PATTERNS:
        for mt in rx.finditer(text or ""):
            if any(a < mt.end() and mt.start() < b for a, b in taken):
                continue
            g = dict(zip(order, mt.groups()))
            try:
                mon = 1
                if "m" in g:
                    s = g["m"].lower().rstrip(".")
                    mon = int(s) if s.isdigit() else MONTHS.get(s, MONTHS.get(s[:3]))
                out.append((dt.date(int(g["y"]), mon, int(g.get("d", 1))), gran))
                taken.append((mt.start(), mt.end()))
            except (ValueError, KeyError, TypeError):
                pass
    return out


def expected(phrase, s):
    """(lo, hi, granularity) of the date the phrase means, said on day s."""
    p = phrase.lower()
    if p in ("yesterday", "last night"):
        d = s - dt.timedelta(days=1)
        return d, d, "day"
    if p == "the other day":
        return s - dt.timedelta(days=7), s - dt.timedelta(days=1), "day"
    m = re.match(r"last (\w+)$", p)
    if m:
        w = m.group(1)
        if w in WD:
            back = (s.weekday() - WD.index(w)) % 7 or 7
            d = s - dt.timedelta(days=back)
            return d, d, "day"
        if w == "week":
            return s - dt.timedelta(days=13), s - dt.timedelta(days=3), "day"
        if w == "weekend":  # the Saturday-Sunday just before the day it was said
            sun = s - dt.timedelta(days=(s.weekday() - 6) % 7 or 7)
            return sun - dt.timedelta(days=1), sun, "day"
        if w == "month":
            first = s.replace(day=1)
            prev = first - dt.timedelta(days=1)
            return prev.replace(day=1), prev, "month"
        if w == "year":
            return dt.date(s.year - 1, 1, 1), dt.date(s.year - 1, 12, 31), "year"
        return dt.date(s.year - 1, 1, 1), s, "year"  # last summer/winter...
    m = re.match(r"(a couple of|a few|a|one|two|three|four|five|\d+) (day|week|month|year)s? ago", p)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else NUM[m.group(1)]
        u = m.group(2)
        if u == "day":
            d = s - dt.timedelta(days=n)
            return d - dt.timedelta(days=1 if n > 2 else 0), d, "day"
        if u == "week":
            return s - dt.timedelta(days=7 * n + 4), s - dt.timedelta(days=7 * n - 4), "day"
        if u == "month":
            y, mo = s.year, s.month - n
            while mo <= 0:
                y, mo = y - 1, mo + 12
            return dt.date(y, mo, 1), dt.date(y, mo, 28), "month"
        return dt.date(s.year - n, 1, 1), dt.date(s.year - n, 12, 31), "year"
    return None


def label(fact, phrase, sess):
    lo, hi, gran = expected(phrase, sess)
    ds = dates_in(fact)
    for d, g in ds:
        if gran == "year" and d.year == lo.year:
            return "CORRECT"
        if gran == "month" and (d.year, d.month) in {(lo.year, lo.month), (hi.year, hi.month)}:
            return "CORRECT"
        if gran == "day" and g == "day" and lo <= d <= hi:
            return "CORRECT"
    if KEPT.search(fact):
        return "KEPT"
    if any(d == sess and g == "day" for d, g in ds):
        return "SESSION"
    if ds:
        return "WRONG"
    return "LOST"


# ---------------------------------------------------------------- cases + batches built by the real add.py code
data = json.load(open("dataset/locomo10.json"))
import src.memzero.add as addmod  # noqa: E402


class _Any:
    def __getattr__(self, n): return _Any()
    def __call__(self, *a, **k): return _Any()
    def __iter__(self): return iter(())


class _Stub:
    batch_size, is_graph, data = 2, True, None
    def __init__(self): self.sent = {}
    def add_memories_for_speaker(self, speaker, messages, timestamp, desc=""): self.sent[speaker] = (messages, timestamp)
    def __getattr__(self, n): return _Any()


cases = []
for ci in CONVS:
    cv = data[ci]["conversation"]
    for qa in data[ci]["qa"]:
        if str(qa.get("category")) != "2" or not qa.get("evidence"):
            continue
        ev = str(qa["evidence"][0]).strip()
        mm = re.match(r"D(\d+):(\d+)$", ev)
        if not mm:
            continue
        sess_key = f"session_{mm.group(1)}"
        turns = cv.get(sess_key) or []
        idx = next((i for i, t in enumerate(turns) if t.get("dia_id") == ev), None)
        if idx is None:
            continue
        ph = PHRASE.search(turns[idx]["text"])
        if not ph:
            continue
        sess_date = next((d for d, g in dates_in(cv[sess_key + "_date_time"]) if g == "day"), None)
        if not sess_date or expected(ph.group(0), sess_date) is None:
            continue
        item = {"conversation": {k: cv[k] for k in ("speaker_a", "speaker_b", sess_key, sess_key + "_date_time")}}
        sid = f"{turns[idx]['speaker']}_{ci}"
        os.environ["DATE_PREFIX"] = "0"
        st = _Stub()
        with contextlib.redirect_stdout(io.StringIO()):
            addmod.MemoryADD.process_conversation(st, item, ci)
        start = (idx // 2) * 2
        sentence = next((x for x in re.split(r"(?<=[.!?])\s+", turns[idx]["text"]) if PHRASE.search(x)), turns[idx]["text"])
        cases.append(dict(ci=ci, q=qa["question"], gold=qa["answer"], phrase=ph.group(0), sess=sess_date,
                          ts=cv[sess_key + "_date_time"], batch=st.sent[sid][0][start:start + 2], sentence=sentence))
os.environ["DATE_PREFIX"] = "1"

ts_split = lambda ts: (re.match(r"(.+?) on (.+)", ts).groups() if re.match(r"(.+?) on (.+)", ts) else ("", ts))
VARIANTS = {
    "V0 no date (Exp 4)": lambda ts: "",
    "V1 [time on date]": lambda ts: f"[{ts}] ",
    "V2 [sent on date at time]": lambda ts: f"[sent on {ts_split(ts)[1]} at {ts_split(ts)[0]}] ",
    "V3 [today is date]": lambda ts: f"[today is {ts_split(ts)[1]}] ",
}

# ---------------------------------------------------------------- the extractor call, exactly as Mem0 makes it
from mem0.memory.utils import ensure_json_instruction, parse_messages, remove_code_blocks  # noqa: E402
from src.memzero.config import get_memory  # noqa: E402

m = get_memory(is_graph=False)
SYSTEM = m.config.custom_fact_extraction_prompt
if not SYSTEM:
    sys.exit("STOP: the authors' instructions are not set as custom_fact_extraction_prompt - check EXTRACTION_PROMPT in .env")


def extract(batch):
    sp, up = ensure_json_instruction(SYSTEM, f"Input:\n{parse_messages(batch)}")
    r = m.llm.generate_response(messages=[{"role": "system", "content": sp}, {"role": "user", "content": up}],
                                response_format={"type": "json_object"})
    try:
        return json.loads(remove_code_blocks(r), strict=False).get("facts") or []
    except Exception:
        return []


CLASSES = ["CORRECT", "KEPT", "SESSION", "WRONG", "LOST", "NO FACT"]
tot = {v: {c: 0 for c in CLASSES} for v in VARIANTS}
print(f"{len(cases)} cases from conversations {CONVS}\n")
for k, c in enumerate(cases, 1):
    lo, hi, gran = expected(c["phrase"], c["sess"])
    want = lo.strftime("%d %b %Y") if lo == hi else (f"{lo:%b %Y}" if gran == "month" else
                                                     (str(lo.year) if gran == "year" else f"{lo:%d %b}-{hi:%d %b %Y}"))
    print(f"[{k}/{len(cases)}] {c['q']}  GOLD: {c['gold']}")
    print(f"   said on {c['ts']}: \"{c['sentence'][:110]}\"  -> '{c['phrase']}' means {want}")
    key = words(c["sentence"])
    for v, fmt in VARIANTS.items():
        batch = [{"role": x["role"], "content": fmt(c["ts"]) + x["content"]} for x in c["batch"]]
        facts = [str(f) for f in extract(batch)]
        rel = [f for f in facts if len(words(f) & key) >= 2]
        if not rel:
            lab, shown = "NO FACT", ""
        else:
            labs = [label(f, c["phrase"], c["sess"]) for f in rel]
            lab = min(labs, key=CLASSES.index)  # best fact about the event
            shown = rel[labs.index(lab)]
        tot[v][lab] += 1
        print(f"   {v:26} {lab:8} {shown[:120]}")
    print()

print("SUMMARY (best fact about the event, per case)")
print(f"{'':28}" + "".join(f"{c:>9}" for c in CLASSES))
for v in VARIANTS:
    print(f"{v:28}" + "".join(f"{tot[v][c]:9}" for c in CLASSES))
print("\nGood = CORRECT + KEPT high, SESSION + WRONG + LOST low.")
from qdrant_client import QdrantClient  # noqa: E402

QdrantClient("localhost", port=6333).delete_collection("smoke_prefix_test")
