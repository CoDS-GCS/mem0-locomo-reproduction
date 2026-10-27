"""Text helpers: tokens, F1 (same tokenizer as metrics/utils.py), overlap, relative-time words, date checks."""
import re
from datetime import date, datetime, timedelta
import calendar

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTHS["sept"] = 9


def simple_tokenize(text):
    """Exactly metrics/utils.py simple_tokenize (used by the F1 score)."""
    return str(text).lower().replace(".", " ").replace(",", " ").replace("!", " ").replace("?", " ").split()


def f1_detail(pred, gold):
    p, g = set(simple_tokenize(pred)), set(simple_tokenize(gold))
    common = p & g
    if not p or not g:
        return {"f1": 0.0, "common": sorted(common), "pred_tokens": sorted(p), "gold_tokens": sorted(g)}
    pr, rc = len(common) / len(p), len(common) / len(g)
    f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
    return {"f1": f1, "precision": pr, "recall": rc, "common": sorted(common)}


STOP = set("""that this with have from they them their there were been will would could should about what when where which while your
very just like also some than then into over only more most much many such even still well really thing things been being does done make made
going gone came come know knew said says saying lot lots great good thanks thank yeah sure okay""".split())


def content_tokens(text):
    out = set()
    for w in re.findall(r"[a-z0-9']+", str(text).lower()):
        w = w.strip("'")
        if len(w) >= 4 and w not in STOP:
            out.add(w[:5])  # crude stem: first 5 letters
    return out


def strip_speaker(text):
    return re.sub(r"^[A-Z][\w ]{0,20}: ", "", str(text))


def overlap(turn_text, other_text):
    """Share of the turn's content words that also appear in other_text (0..1); None if the turn has no content words."""
    t = content_tokens(strip_speaker(turn_text))
    if not t:
        return None
    return len(t & content_tokens(other_text)) / len(t)


OVERLAP_MIN = 0.30

# ---------------------------------------------------------------- relative time words
_REL = [
    r"yesterday", r"tomorrow", r"tonight", r"last night", r"the other day", r"recently", r"earlier this \w+",
    r"last (?:week|weekend|month|year|summer|winter|spring|fall|autumn|monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
    r"next (?:week|weekend|month|year|summer|winter|spring|fall|autumn|monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
    r"this (?:week|weekend|month|year|morning|afternoon|evening)",
    r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|few|couple of|several) (?:days?|weeks?|months?|years?) ago",
    r"\bago\b", r"a while back", r"the (?:week|month|year) before",
]
REL_RE = re.compile("|".join(f"(?:{r})" for r in _REL), re.I)


def rel_words(text):
    return [m.group(0).lower().strip() for m in REL_RE.finditer(str(text))]


# ---------------------------------------------------------------- dates
SESSION_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(am|pm)\s+on\s+(\d{1,2})\s+(\w+),?\s+(\d{4})", re.I)


def parse_session_date(s):
    m = SESSION_RE.search(str(s))
    if not m:
        return None
    mon = MONTHS.get(m.group(5).lower())
    if not mon:
        return None
    try:
        return date(int(m.group(6)), mon, int(m.group(4)))
    except ValueError:
        return None


_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
_D1 = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MON})\.?,?\s+(\d{{4}})\b", re.I)       # 8 May 2023
_D2 = re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)                # May 8, 2023
_D3 = re.compile(rf"\b({_MON})\.?,?\s+(\d{{4}})\b", re.I)                                              # May 2023
_D4 = re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?!,?\s*\d{{4}})", re.I)              # May 8
_D5 = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MON})\b(?!\.?,?\s*\d{{4}})", re.I)     # 8 May
_D6 = re.compile(r"\b(19|20)\d\d\b")                                                                   # 2023


def _span(y, m=None, d=None):
    try:
        if d:
            x = date(y, m, d)
            return x, x
        if m:
            return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
        return date(y, 1, 1), date(y, 12, 31)
    except ValueError:
        return None


def date_mentions(text, default_year=None):
    """Explicit dates written in text -> list of (label, lo, hi)."""
    t = str(text)
    out, used = [], []

    def take(rx, build):
        for m in rx.finditer(t):
            if any(a < m.end() and m.start() < b for a, b in used):
                continue
            sp = build(m)
            if sp:
                used.append((m.start(), m.end()))
                out.append((m.group(0), sp[0], sp[1]))
    take(_D1, lambda m: _span(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))))
    take(_D2, lambda m: _span(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))))
    take(_D3, lambda m: _span(int(m.group(2)), MONTHS[m.group(1).lower()]))
    if default_year:
        take(_D4, lambda m: _span(default_year, MONTHS[m.group(1).lower()], int(m.group(2))))
        take(_D5, lambda m: _span(default_year, MONTHS[m.group(2).lower()], int(m.group(1))))
    take(_D6, lambda m: _span(int(m.group(0))))
    return out


def _month_shift(d, k):
    y, m = d.year, d.month + k
    while m < 1:
        y, m = y - 1, m + 12
    while m > 12:
        y, m = y + 1, m - 12
    return y, m


NUMS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "few": 3, "couple of": 2, "several": 4}


def expected_range(word, sd):
    """What dates a relative word can mean when written on session date sd. Returns (lo, hi) or None (cannot resolve)."""
    w = word.lower()
    if w in ("yesterday",):
        return sd - timedelta(1), sd - timedelta(1)
    if w in ("tomorrow",):
        return sd + timedelta(1), sd + timedelta(1)
    if w in ("tonight", "this morning", "this afternoon", "this evening"):
        return sd, sd
    if w in ("last night",):
        return sd - timedelta(1), sd
    if w in ("the other day", "recently"):
        return sd - timedelta(14), sd
    if w in ("last week", "last weekend"):
        return sd - timedelta(14), sd - timedelta(1)
    if re.match(r"last (monday|tuesday|wednesday|thursday|friday|saturday|sunday)$", w):
        return sd - timedelta(7), sd - timedelta(1)
    if w == "last month":
        y, m = _month_shift(sd, -1)
        return _span(y, m)
    if w == "last year":
        return _span(sd.year - 1)
    if w == "next week":
        return sd + timedelta(1), sd + timedelta(14)
    if w == "next month":
        y, m = _month_shift(sd, 1)
        return _span(y, m)
    if w == "next year":
        return _span(sd.year + 1)
    if w in ("this week", "this weekend"):
        return sd - timedelta(6), sd + timedelta(6)
    if w == "this month":
        return _span(sd.year, sd.month)
    if w == "this year":
        return _span(sd.year)
    m = re.match(r"(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|few|couple of|several) (day|week|month|year)s? ago$", w)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else NUMS.get(m.group(1), 1)
        u = m.group(2)
        if u == "day":
            return sd - timedelta(n + 1), sd - timedelta(max(n - 1, 0))
        if u == "week":
            return sd - timedelta(7 * n + 7), sd - timedelta(max(7 * n - 7, 0))
        if u == "month":
            y1, m1 = _month_shift(sd, -n - 1)
            y2, m2 = _month_shift(sd, -n + 1) if n > 1 else (sd.year, sd.month)
            return _span(y1, m1)[0], _span(y2, m2)[1]
        return _span(sd.year - n - 1)[0], _span(sd.year - n + 1)[1] if n > 1 else sd
    return None


def date_verdict(turn_text, memory_text, session_date_str):
    """Temporal lens for one (evidence turn, memory) pair. Only meaningful if the turn has a relative time word.
    Returns {"label": none|kept_word|dropped|correct|invented|unverified, "words": [...], "mentions": [...], "expected": ...}."""
    words = rel_words(turn_text)
    if not words:
        return {"label": "none", "words": []}
    sd = parse_session_date(session_date_str)
    ment = date_mentions(memory_text, sd.year if sd else None)
    kept = any(w in str(memory_text).lower() for w in words)
    res = {"words": words, "mentions": [m[0] for m in ment], "kept_word": kept}
    exp = [(w, expected_range(w, sd)) for w in words] if sd else []
    exp = [(w, r) for w, r in exp if r]
    res["expected"] = [f"{w}: {r[0].isoformat()}" + (f" .. {r[1].isoformat()}" if r[1] != r[0] else "") for w, r in exp]
    if ment:
        if not exp:
            res["label"] = "unverified"
        elif any(lo <= r[1] and r[0] <= hi for _, lo, hi in ment for _, r in exp):
            res["label"] = "correct"
        else:
            res["label"] = "invented"
    else:
        res["label"] = "kept_word" if kept else "dropped"
    return res


def evidence_ids(ev):
    out = []
    for e in ev or []:
        out += re.findall(r"D\d+:\d+", str(e))
    return out
