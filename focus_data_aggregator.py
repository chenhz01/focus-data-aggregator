#!/usr/bin/env python3
"""focus-data-aggregator: validate focus-session records against a schema,
aggregate daily/weekly focus minutes, and classify interruption causes.
Pure standard library."""

import argparse
import json
import sys
from datetime import date, time

VALID_CATEGORIES = {"self", "external", "tech", "unknown"}

CATEGORY_KEYWORDS = [
    ("external", ["call", "phone", "meeting", "colleague", "boss", "manager",
                  "client", "visitor", "knock", "visitor", "person", "collegue", "同事", "电话", "会议"]),
    ("tech", ["notification", "alert", "slack", "email", "message", "ping",
              "internet", "wifi", "crash", "bug", "update", "通知", "邮件"]),
    ("self", ["distract", "procrastinat", "urge", "snack", "water", "tired",
              "wander", "break", "phone-check", "走神", "拖延", "分心"]),
]


def _parse_hhmm(s):
    if not isinstance(s, str) or len(s) != 5 or s[2] != ":":
        return None
    try:
        return time(int(s[:2]), int(s[3:]))
    except ValueError:
        return None


def _parse_date(s):
    try:
        y, m, d = (int(x) for x in s.split("-"))
        return date(y, m, d)
    except Exception:
        return None


def validate_record(rec):
    """Return list of error strings for one session record."""
    errs = []
    if not isinstance(rec, dict):
        return ["record must be a JSON object"]
    for k in ("date", "start", "end", "task"):
        v = rec.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            errs.append("missing field: %s" % k)
    if rec.get("date") and not _parse_date(rec["date"]):
        errs.append("invalid date: %r (want YYYY-MM-DD)" % rec.get("date"))
    st, en = _parse_hhmm(rec.get("start", "")), _parse_hhmm(rec.get("end", ""))
    if rec.get("start") and st is None:
        errs.append("invalid start time: %r (want HH:MM)" % rec.get("start"))
    if rec.get("end") and en is None:
        errs.append("invalid end time: %r (want HH:MM)" % rec.get("end"))
    if st is not None and en is not None and en <= st:
        errs.append("end must be after start")
    its = rec.get("interruptions", [])
    if not isinstance(its, list):
        errs.append("'interruptions' must be a list")
        its = []
    for i, it in enumerate(its):
        if not isinstance(it, dict):
            errs.append("interruption[%d] must be an object" % i)
            continue
        if not it.get("cause") or not str(it.get("cause")).strip():
            errs.append("interruption[%d]: missing cause" % i)
        if it.get("time") and _parse_hhmm(it["time"]) is None:
            errs.append("interruption[%d]: bad time %r" % (i, it.get("time")))
        if "category" in it and it["category"] not in VALID_CATEGORIES:
            errs.append("interruption[%d]: category must be one of %s" % (i, ",".join(sorted(VALID_CATEGORIES))))
    return errs


def categorize(cause, declared=None):
    """Declared category wins; else keyword match; else 'unknown'."""
    if declared in VALID_CATEGORIES:
        return declared
    c = str(cause or "").lower()
    for cat, kws in CATEGORY_KEYWORDS:
        for kw in kws:
            if kw.lower() in c:
                return cat
    return "unknown"


def session_minutes(rec):
    st, en = _parse_hhmm(rec.get("start", "")), _parse_hhmm(rec.get("end", ""))
    if st is None or en is None or en <= st:
        fm = rec.get("focus_minutes")
        if isinstance(fm, (int, float)) and fm >= 0:
            return float(fm)
        return 0.0
    return (en.hour * 60 + en.minute) - (st.hour * 60 + st.minute)


def _agg(records):
    focus = 0.0
    sessions = 0
    by_cat = {c: 0 for c in sorted(VALID_CATEGORIES)}
    for r in records:
        focus += session_minutes(r)
        sessions += 1
        for it in r.get("interruptions", []) or []:
            if isinstance(it, dict):
                cat = categorize(it.get("cause"), it.get("category"))
                by_cat[cat] = by_cat.get(cat, 0) + 1
    interr = sum(by_cat.values())
    score = round(focus / (focus + 5.0 * interr), 3) if (focus + interr) > 0 else 0.0
    return {
        "sessions": sessions,
        "focus_minutes": round(focus, 1),
        "interruptions": interr,
        "by_category": by_cat,
        "focus_score": score,
    }


def aggregate_daily(records):
    """Group by date; returns {date: aggregate} sorted ascending."""
    groups = {}
    for r in records:
        groups.setdefault(r.get("date", "?"), []).append(r)
    return {d: _agg(groups[d]) for d in sorted(groups)}


def _week_key(datestr):
    d = _parse_date(datestr)
    if not d:
        return "?"
    iso = d.isocalendar()
    return "%04d-W%02d" % (iso[0], iso[1])


def aggregate_weekly(records):
    groups = {}
    for r in records:
        groups.setdefault(_week_key(r.get("date", "")), []).append(r)
    return {w: _agg(groups[w]) for w in sorted(groups)}


def load_log(path):
    """Load a JSONL or JSON-array file. Raises ValueError/OSError on failure."""
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    text = raw.strip()
    if not text:
        return []
    if text.startswith("["):
        data = json.loads(raw)
    else:
        data = []
        for ln, line in enumerate(raw.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError("line %d: %s" % (ln, exc))
    if not isinstance(data, list):
        raise ValueError("log must be a JSON array or JSONL")
    return data


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="focus-data-aggregator",
        description="Validate focus-session records, aggregate day/week, classify interruption causes.",
    )
    p.add_argument("--log", required=True, help="session log (JSONL or JSON array)")
    p.add_argument("--agg", choices=["day", "week"], default="day")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args(argv)

    try:
        records = load_log(args.log)
    except Exception as exc:
        print("error: cannot load log: %s" % exc, file=sys.stderr)
        return 2

    invalid = []
    clean = []
    for i, r in enumerate(records):
        errs = validate_record(r)
        if errs:
            invalid.append({"index": i, "errors": errs})
        else:
            clean.append(r)

    agg = aggregate_daily(clean) if args.agg == "day" else aggregate_weekly(clean)
    if args.json:
        print(json.dumps({"aggregates": agg, "invalid_records": invalid,
                          "valid_records": len(clean), "total_records": len(records)},
                         ensure_ascii=False, indent=2))
    else:
        for k in agg:
            a = agg[k]
            print("%s  focus=%5.1fmin  sessions=%d  interruptions=%d  score=%.3f" %
                  (k, a["focus_minutes"], a["sessions"], a["interruptions"], a["focus_score"]))
        if invalid:
            print("invalid records: %d (run with --json for details)" % len(invalid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
