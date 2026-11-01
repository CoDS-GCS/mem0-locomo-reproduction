"""Exp 5 vs Exp 4: which dates did the memories of one conversation get? Read-only (changes nothing).
Run from the Exp 5 folder with the venv active, after that conversation has finished the add stage:
    python date_check.py 0                      (conversation 0)
    python date_check.py 0 "support group"      (also list the memories that contain these words)

For each experiment it reads the memories of the two speakers from Qdrant and counts:
  - memories with an explicit date (e.g. "7 May 2023", "May 7, 2023", "May 2023", "2023-05-07")
  - of those, how far the date is from the session date the memory is stored with (Qdrant "timestamp"):
      within 7 days  -> fits "yesterday / last week / today" in that session
      8-60 days      -> unclear
      over 60 days   -> most likely invented (like Exp 4's "October 25, 2023" for the 8 May 2023 session),
                        or a memory that an UPDATE moved to a later session, or "last year" / future plans
  - memories that still contain a relative time word ("yesterday", "last week", ...)
This is a rough check to see whether showing the date helps, not a score. The score comes from the judge.
"""
import datetime as dt
import json
import re
import sys

from qdrant_client import QdrantClient, models

N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
GREP = sys.argv[2] if len(sys.argv) > 2 else ("support group" if N == 0 else None)
COLS = [("Exp 4 (no date shown)", "locomo_gem_neo4j"), ("Exp 5 (date shown)", "locomo_gem_neo4j_date")]

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
     "November", "December"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
MON = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
YEAR = r"((?:19|20)\d\d)"
PATTERNS = [  # (regex, which groups are day / month / year)
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?(?: of)? {MON},? {YEAR}\b", re.I), ("d", "m", "y")),
    (re.compile(rf"\b{MON} (\d{{1,2}})(?:st|nd|rd|th)?,? {YEAR}\b", re.I), ("m", "d", "y")),
    (re.compile(rf"\b{YEAR}-(\d\d)-(\d\d)\b"), ("y", "m", "d")),
    (re.compile(rf"\b{MON},? {YEAR}\b", re.I), ("m", "y")),
]
RELATIVE = re.compile(r"\b(yesterday|today|tonight|tomorrow|last (?:week|weekend|month|year|night|friday|saturday|"
                      r"sunday|monday|tuesday|wednesday|thursday)|this (?:week|weekend|month|year)|next (?:week|month|"
                      r"year)|recently|a few (?:days|weeks) ago|(?:\w+ )?(?:days|weeks|months|years) ago)\b", re.I)


def dates_in(text):
    found, taken = [], []
    for rx, order in PATTERNS:
        for mt in rx.finditer(text):
            if any(a < mt.end() and mt.start() < b for a, b in taken):
                continue  # already covered by a more specific pattern
            g = dict(zip(order, mt.groups()))
            try:
                s = g["m"].lower().rstrip(".")
                mon = int(s) if s.isdigit() else MONTHS.get(s, MONTHS.get(s[:3]))
                found.append(dt.date(int(g["y"]), mon, int(g.get("d", 15))))
                taken.append((mt.start(), mt.end()))
            except (ValueError, KeyError, TypeError):
                pass
    return found


cv = json.load(open("dataset/locomo10.json"))[N]["conversation"]
uids = [f"{cv['speaker_a']}_{N}", f"{cv['speaker_b']}_{N}"]
sessions = sorted(d for k, v in cv.items() if k.endswith("_date_time") and cv.get(k[:-len("_date_time")])
                  for d in dates_in(v))
print(f"Conversation {N}: {uids[0]} / {uids[1]}, {len(sessions)} sessions from {sessions[0]:%d %b %Y} to {sessions[-1]:%d %b %Y}\n")

qc = QdrantClient("localhost", port=6333)
for label, col in COLS:
    if not qc.collection_exists(col):
        print(f"{label}: collection {col} not found - skipped\n")
        continue
    mems = []
    for u in uids:
        flt = models.Filter(must=[models.FieldCondition(key="user_id", match=models.MatchValue(value=u))])
        off = None
        while True:
            pts, off = qc.scroll(col, scroll_filter=flt, limit=500, offset=off, with_payload=True)
            mems += [(u, p.payload.get("data", ""), p.payload.get("timestamp")) for p in pts]
            if off is None:
                break
    dated = [(u, t, ts, dates_in(t)) for u, t, ts in mems if dates_in(t)]
    close = mid = far = 0
    far_ex = []
    for u, t, ts, ds in dated:
        own = dates_in(str(ts or ""))
        if not own:
            continue
        gap = min(abs((d - own[0]).days) for d in ds)
        if gap <= 7:
            close += 1
        elif gap <= 60:
            mid += 1
        else:
            far += 1
            far_ex.append((ts, t))
    rel = [t for u, t, ts in mems if RELATIVE.search(t)]
    pc = lambda a, b: f"{100 * a / b:4.1f}%" if b else "  -  "
    print(f"{label}  [{col}]")
    print(f"  memories                                       {len(mems):5}")
    print(f"  with an explicit date                          {len(dated):5}  ({pc(len(dated), len(mems))} of memories)")
    print(f"    within 7 days of its own session date        {close:5}  ({pc(close, len(dated))} of dated)")
    print(f"    8-60 days away                               {mid:5}  ({pc(mid, len(dated))} of dated)")
    print(f"    over 60 days away (invented?)                {far:5}  ({pc(far, len(dated))} of dated)")
    print(f"  still with a relative word (yesterday...)      {len(rel):5}  ({pc(len(rel), len(mems))} of memories)")
    for ts, t in far_ex[:3]:
        print(f"    over-60-days example [session {ts}]: {t[:140]}")
    if GREP:
        hits = [(u, t, ts) for u, t, ts in mems if GREP.lower() in t.lower()]
        print(f"  memories containing '{GREP}': {len(hits)}")
        for u, t, ts in hits[:6]:
            print(f"    [{u} | stored with session date: {ts}] {t[:200]}")
    print()
if N == 0:
    print("Gold answer for 'When did Caroline go to the LGBTQ support group?': 7 May 2023 (session 1 is 8 May 2023)")
