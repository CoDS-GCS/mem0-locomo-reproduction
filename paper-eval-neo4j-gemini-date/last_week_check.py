"""Exp 5: what exactly happens to "last week", "yesterday", "two months ago" ... ? Read-only.
Run from the Exp 5 folder, venv active:   python last_week_check.py 0

PART 1 - every extraction call of conversation N whose input contains such a phrase (from logs/llm_conv<N>.jsonl).
For each fact about that same event (it shares words with the sentence), it says what the extractor did:
  OK   resolved      the fact has a date EARLIER than the session date ("last week" -> around June 2)
  OK   told+kept     the fact has the session date AND keeps the phrase ("On June 9 she said that last week ...")
  OK   kept          no date but the phrase is kept (the answer step can compute it from the memory's timestamp)
  BAD  on session    the event itself is put ON the session date, phrase gone ("On June 9 she gave a talk")
  BAD  wrong date    a date that is after the session or more than a year before it (invented)
  BAD  lost          no date and no phrase: the time is gone
PART 2 - the LOCOMO temporal questions of conversation N whose evidence turn has such a phrase:
the gold answer, and the stored memory (Exp 4 and Exp 5) that best matches the evidence turn.
"""
import datetime as dt
import json
import os
import re
import sys

from qdrant_client import QdrantClient, models

N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
MONTHS = {m.lower(): i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                               "September", "October", "November", "December"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
MON = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
YEAR = r"((?:19|20)\d\d)"
PATTERNS = [(re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?(?: of)? {MON},? {YEAR}\b", re.I), ("d", "m", "y")),
            (re.compile(rf"\b{MON} (\d{{1,2}})(?:st|nd|rd|th)?,? {YEAR}\b", re.I), ("m", "d", "y")),
            (re.compile(rf"\b{YEAR}-(\d\d)-(\d\d)\b"), ("y", "m", "d")),
            (re.compile(rf"\b{MON},? {YEAR}\b", re.I), ("m", "y")),
            (re.compile(rf"\b(?:in|of|around|during) {YEAR}\b", re.I), ("y",))]
EARLIER = re.compile(r"\b(yesterday|the other day|last (?:week|weekend|month|year|night|summer|winter|spring|fall|monday|"
                     r"tuesday|wednesday|thursday|friday|saturday|sunday)|(?:a few|a couple of|two|three|four|five|\d+) "
                     r"(?:days|weeks|months|years) ago|(?:a|one) (?:week|month|year) ago)\b", re.I)
STOP = set("that this with from have been were they them their there what when which about would could should "
           "really just like also your into over some very much more than then here know think going said "
           "went last week weekend yesterday days month months year years night since spoke things happened great "
           "awesome today ago other couple".split())


def dates_in(text):
    found, taken = [], []
    for rx, order in PATTERNS:
        for mt in rx.finditer(text or ""):
            if any(a < mt.end() and mt.start() < b for a, b in taken):
                continue
            g = dict(zip(order, mt.groups()))
            try:
                if "m" in g:
                    s = g["m"].lower().rstrip(".")
                    mon = int(s) if s.isdigit() else MONTHS.get(s, MONTHS.get(s[:3]))
                else:
                    mon = 7
                found.append(dt.date(int(g["y"]), mon, int(g.get("d", 15 if "m" in g else 1))))
                taken.append((mt.start(), mt.end()))
            except (ValueError, KeyError, TypeError):
                pass
    return found


def classify(text, sess):
    """What a memory/fact says about the time of an event told on session date `sess` with 'last week' etc."""
    ds, kept = dates_in(text), bool(EARLIER.search(text or ""))
    if ds and sess:
        if any(d == sess for d in ds):
            return "OK   told+kept" if kept else "BAD  on session"
        if any(sess - dt.timedelta(days=400) <= d < sess for d in ds):
            return "OK   resolved"
        return "BAD  wrong date"
    return "OK   kept" if kept else "BAD  lost"


words = lambda t: {w for w in re.findall(r"[a-z]{4,}", (t or "").lower()) if w not in STOP}


def jparse(x):
    try:
        return x if isinstance(x, dict) else json.loads(re.sub(r"^```(?:json)?|```$", "", str(x).strip(), flags=re.M))
    except Exception:
        return None


# ---------------------------------------------------------------- PART 1
path = f"logs/llm_conv{N}.jsonl"
CLASSES = ("OK   resolved", "OK   told+kept", "OK   kept", "BAD  on session", "BAD  wrong date", "BAD  lost")
counts = {k: 0 for k in CLASSES}
examples = {k: [] for k in counts}
calls = 0
for line in open(path):
    rec = json.loads(line)
    if rec.get("llm") != "memory" or rec.get("error"):
        continue
    user = next((m.get("content", "") for m in rec.get("messages") or [] if m.get("role") == "user"), "")
    if not str(user).startswith("Input:"):
        continue
    facts = (jparse(rec.get("response")) or {}).get("facts") or []
    for turn in user.splitlines()[1:]:
        m = re.match(r"(?:user|assistant): \[([^\]]+)\] (.*)", turn)
        if not m or not EARLIER.search(m.group(2)):
            continue
        sess = (dates_in(m.group(1)) or [None])[0]
        sentence = next((s for s in re.split(r"(?<=[.!?])\s+", m.group(2)) if EARLIER.search(s)), m.group(2))
        phrase = EARLIER.search(sentence).group(0)
        key = words(sentence) - words(m.group(2).split(":")[0])
        related = [f for f in facts if len(words(str(f)) & key) >= 2]
        if not related:
            continue
        calls += 1
        for f in related:
            f = str(f)
            k = classify(f, sess)
            counts[k] += 1
            if len(examples[k]) < 6:
                examples[k].append((m.group(1), phrase, sentence, f))

print(f"PART 1 - conversation {N}: {calls} turns with a phrase like 'last week' / 'yesterday' / '2 months ago',")
print("and what the extractor wrote about that same event:\n")
tot = sum(counts.values())
for k, v in counts.items():
    print(f"  {k:16} {v:4}  ({100 * v / max(1, tot):4.1f}%)")
for k in ("BAD  on session", "BAD  wrong date", "BAD  lost", "OK   told+kept", "OK   resolved"):
    if examples[k]:
        print(f"\n  examples - {k.strip()}:")
        for sess, ph, sent, f in examples[k][:4]:
            print(f"    session {sess} | said: \"{sent[:120]}\"")
            print(f"      -> fact: {f[:170]}")

# ---------------------------------------------------------------- PART 2
data = json.load(open("dataset/locomo10.json"))[N]
cv = data["conversation"]
qc = QdrantClient("localhost", port=6333)


def memories(col, uid):
    if not qc.collection_exists(col):
        return []
    flt = models.Filter(must=[models.FieldCondition(key="user_id", match=models.MatchValue(value=uid))])
    out, off = [], None
    while True:
        pts, off = qc.scroll(col, scroll_filter=flt, limit=500, offset=off, with_payload=True)
        out += [(p.payload.get("timestamp"), p.payload.get("data", "")) for p in pts]
        if off is None:
            return out


print(f"\nPART 2 - temporal questions of conversation {N} whose evidence uses such a phrase "
      "(best-matching stored memory of the speaker who said it)")
cache = {}
summary = {lab: {k: 0 for k in CLASSES + ("no matching memory",)} for lab in ("Exp 4", "Exp 5")}
for qa in data["qa"]:
    if str(qa.get("category")) != "2" or not qa.get("evidence"):
        continue
    ev = str(qa["evidence"][0]).strip()
    mm = re.match(r"D(\d+):(\d+)$", ev)
    if not mm:
        continue
    turn = next((t for t in cv.get(f"session_{mm.group(1)}", []) if t.get("dia_id") == ev), None)
    if not turn or not EARLIER.search(turn["text"]):
        continue
    uid = f"{turn['speaker']}_{N}"
    sent = next((x for x in re.split(r"(?<=[.!?])\s+", turn["text"]) if EARLIER.search(x)), turn["text"])
    key = words(sent)
    sess = (dates_in(cv[f"session_{mm.group(1)}_date_time"]) or [None])[0]
    print(f"\n  Q: {qa['question']}   GOLD: {qa['answer']}")
    print(f"     said on {cv[f'session_{mm.group(1)}_date_time']}: \"{sent[:130]}\"")
    for label, col in (("Exp 4", "locomo_gem_neo4j"), ("Exp 5", "locomo_gem_neo4j_date")):
        if (col, uid) not in cache:
            cache[(col, uid)] = memories(col, uid)
        best = sorted(cache[(col, uid)], key=lambda m: -len(words(m[1]) & key))[:1]
        if not best or len(words(best[0][1]) & key) < 2:
            summary[label]["no matching memory"] += 1
            print(f"     {label}: (no matching memory)")
            continue
        ts, t = best[0]
        k = classify(t, sess)
        summary[label][k] += 1
        print(f"     {label} {k:16} {t[:160]}")

print("\nPART 2 summary (one memory per question):")
print(f"  {'':20} {'Exp 4':>6} {'Exp 5':>6}")
for k in summary["Exp 5"]:
    print(f"  {k:20} {summary['Exp 4'][k]:6} {summary['Exp 5'][k]:6}")
