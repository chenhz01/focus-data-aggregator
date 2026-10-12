#!/usr/bin/env python3
"""Self test for focus-data-aggregator. Run: python self_test.py
Last line: SUMMARY: PASS n/n"""

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import focus_data_aggregator as fda

PASS = 0
FAIL = 0
FAILED = []


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILED.append(name)


def rec(date="2026-10-10", start="09:00", end="10:30", task="writing",
        interruptions=None, **extra):
    r = {"date": date, "start": start, "end": end, "task": task}
    if interruptions is not None:
        r["interruptions"] = interruptions
    r.update(extra)
    return r


def run_cli(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = fda.main(argv)
    return code, buf.getvalue()


# ---------- functional: schema validation ----------
check("valid_record_no_errors", fda.validate_record(rec()) == [])
check("missing_date", any("date" in e for e in fda.validate_record(rec(date=""))))
check("missing_start", any("start" in e for e in fda.validate_record(rec(start=""))))
check("missing_end", any("end" in e for e in fda.validate_record(rec(end=""))))
check("missing_task", any("task" in e for e in fda.validate_record(rec(task=""))))
check("bad_date_format", any("invalid date" in e for e in fda.validate_record(rec(date="2026/10/10"))))
check("bad_date_value", any("invalid date" in e for e in fda.validate_record(rec(date="2026-13-40"))))
check("bad_start_format", any("invalid start" in e for e in fda.validate_record(rec(start="9am"))))
check("bad_end_format", any("invalid end" in e for e in fda.validate_record(rec(end="9999"))))
check("end_before_start", any("end must be after start" in e for e in fda.validate_record(rec(start="10:00", end="09:00"))))
check("end_equals_start_invalid", fda.validate_record(rec(start="09:00", end="09:00")) != [])
check("non_dict_record", fda.validate_record("nope") == ["record must be a JSON object"])
check("interruptions_not_list", any("must be a list" in e for e in fda.validate_record(rec(interruptions="x"))))
check("interruption_missing_cause", any("missing cause" in e for e in fda.validate_record(rec(interruptions=[{"time": "09:10"}]))))
check("interruption_bad_time", any("bad time" in e for e in fda.validate_record(rec(interruptions=[{"time": "25:99", "cause": "call"}]))))
check("interruption_bad_category", any("category" in e for e in fda.validate_record(rec(interruptions=[{"time": "09:10", "cause": "call", "category": "alien"}]))))
check("interruption_not_dict", any("must be an object" in e for e in fda.validate_record(rec(interruptions=["knock"]))))
check("valid_with_interruptions", fda.validate_record(rec(interruptions=[{"time": "09:30", "cause": "phone call"}])) == [])
check("focus_minutes_fallback", fda.session_minutes({"start": "x", "end": "y", "focus_minutes": 45}) == 45.0)

# ---------- functional: categorization ----------
check("cat_declared_wins", fda.categorize("anything", "self") == "self")
check("cat_call_external", fda.categorize("phone call from boss") == "external")
check("cat_meeting_external", fda.categorize("impromptu meeting") == "external")
check("cat_slack_tech", fda.categorize("Slack notification") == "tech")
check("cat_email_tech", fda.categorize("EMAIL arrived") == "tech")
check("cat_wifi_tech", fda.categorize("wifi dropped") == "tech")
check("cat_distracted_self", fda.categorize("got distracted") == "self")
check("cat_procrastination_self", fda.categorize("procrastinating again") == "self")
check("cat_unknown", fda.categorize("mystery event") == "unknown")
check("cat_empty", fda.categorize("") == "unknown")
check("cat_none", fda.categorize(None) == "unknown")
check("cat_chinese", fda.categorize("接到电话") == "external")

# ---------- functional: aggregation ----------
r1 = rec("2026-10-10", "09:00", "10:00", "a", interruptions=[{"time": "09:30", "cause": "call"}])
r2 = rec("2026-10-10", "11:00", "12:00", "b", interruptions=[{"time": "11:10", "cause": "slack ping"}, {"time": "11:40", "cause": "distraction"}])
r3 = rec("2026-10-12", "09:00", "10:00", "c")
d = fda.aggregate_daily([r1, r2, r3])
check("agg_days_sorted", list(d.keys()) == ["2026-10-10", "2026-10-12"])
check("agg_focus_minutes", d["2026-10-10"]["focus_minutes"] == 120.0)
check("agg_sessions", d["2026-10-10"]["sessions"] == 2 and d["2026-10-12"]["sessions"] == 1)
check("agg_interruptions", d["2026-10-10"]["interruptions"] == 3)
check("agg_by_cat_external", d["2026-10-10"]["by_category"]["external"] == 1)
check("agg_by_cat_tech", d["2026-10-10"]["by_category"]["tech"] == 1)
check("agg_by_cat_self", d["2026-10-10"]["by_category"]["self"] == 1)
check("agg_score_clean_day", d["2026-10-12"]["focus_score"] == 1.0)
check("agg_score_noisy_day", d["2026-10-10"]["focus_score"] == round(120 / 135, 3))
w = fda.aggregate_weekly([r1, r2, r3])
check("weekly_two_buckets", list(w.keys()) == ["2026-W41", "2026-W42"])
check("weekly_totals", w["2026-W41"]["focus_minutes"] == 120.0 and w["2026-W41"]["sessions"] == 2
      and w["2026-W42"]["focus_minutes"] == 60.0 and w["2026-W42"]["sessions"] == 1)
w2 = fda.aggregate_weekly([rec("2026-01-01"), rec("2026-01-05")])
check("weekly_year_boundary_two_buckets", list(w2.keys()) == ["2026-W01", "2026-W02"])
dm = fda.aggregate_daily([rec("2026-10-10", start="09:00", end="bad", focus_minutes=30)])
check("fallback_focus_minutes", dm["2026-10-10"]["focus_minutes"] == 30.0)
d0 = fda.aggregate_daily([])
check("empty_daily", d0 == {})
w0 = fda.aggregate_weekly([])
check("empty_weekly", w0 == {})
dz = fda.aggregate_daily([rec()])
check("zero_interruptions_keys", dz["2026-10-10"]["by_category"] == {"external": 0, "self": 0, "tech": 0, "unknown": 0})

tmp = tempfile.mkdtemp()
jsonl = os.path.join(tmp, "log.jsonl")
with open(jsonl, "w", encoding="utf-8") as f:
    f.write(json.dumps(rec()) + "\n\n")
    f.write(json.dumps(rec(date="2026-10-11", start="14:00", end="15:00", task="review")) + "\n")
code, out = run_cli(["--log", jsonl, "--agg", "day", "--json"])
r = json.loads(out)
check("cli_jsonl_day", code == 0 and r["valid_records"] == 2 and r["total_records"] == 2)
check("cli_two_days", len(r["aggregates"]) == 2)
jarr = os.path.join(tmp, "log.json")
with open(jarr, "w", encoding="utf-8") as f:
    json.dump([rec(), rec(date="2026-10-11", start="14:00", end="15:00", task="review")], f)
code, out = run_cli(["--log", jarr, "--agg", "week", "--json"])
r = json.loads(out)
check("cli_array_week", code == 0 and list(r["aggregates"].keys()) == ["2026-W41"])
code, out = run_cli(["--log", jsonl, "--agg", "day"])
check("cli_human_mode", code == 0 and "focus=" in out and "2026-10-10" in out)

# ---------- exception paths ----------
check("bad_hhmm_none", fda._parse_hhmm("nope") is None)
check("bad_hhmm_range", fda._parse_hhmm("24:00") is None)
check("bad_hhmm_short", fda._parse_hhmm("9:0") is None)
check("good_hhmm", fda._parse_hhmm("09:07") is not None)
check("bad_weekkey", fda._week_key("not-a-date") == "?")
check("bad_weekkey_empty", fda._week_key("") == "?")
badlog = os.path.join(tmp, "bad.jsonl")
with open(badlog, "w", encoding="utf-8") as f:
    f.write('{"date": "2026-10-10", "start": "09:00", "end": "10:00", "task": "a"}\n{corrupted line}\n')
code, out = run_cli(["--log", badlog])
check("cli_corrupt_line_exit2", code == 2)
code, out = run_cli(["--log", os.path.join(tmp, "missing.jsonl")])
check("cli_missing_log_exit2", code == 2)
notarray = os.path.join(tmp, "obj.json")
with open(notarray, "w", encoding="utf-8") as f:
    f.write('{"date": "2026-10-10"}')
code, out = run_cli(["--log", notarray, "--json"])
r = json.loads(out)
check("cli_object_treated_as_one_record", code == 0 and r["total_records"] == 1 and r["valid_records"] == 0)
agg_bad = fda.aggregate_daily([{"date": "oops", "start": "09:00", "end": "10:00", "task": "x"}])
check("agg_bad_date_grouped_as_q", "?" not in agg_bad and "oops" in agg_bad)
check("session_minutes_bad_times", fda.session_minutes({"start": "x", "end": "y"}) == 0.0)
check("session_minutes_negative_fm_ignored", fda.session_minutes({"start": "x", "end": "y", "focus_minutes": -5}) == 0.0)
empty_log = os.path.join(tmp, "empty.jsonl")
with open(empty_log, "w", encoding="utf-8") as f:
    f.write("")
code, out = run_cli(["--log", empty_log, "--json"])
r = json.loads(out)
check("cli_empty_log", code == 0 and r["total_records"] == 0)

# ---------- extreme edge cases ----------
check("edge_unicode_task", fda.validate_record(rec(task="写论文 ✍️ 说明")) == [])
u = rec(date="2026-10-10", task="写论文", interruptions=[{"time": "09:10", "cause": "微信通知"}])
d = fda.aggregate_daily([u])
check("edge_unicode_interruption_tech", d["2026-10-10"]["by_category"]["tech"] == 1)
long_task = "t" * 100000
check("edge_very_long_task", fda.validate_record(rec(task=long_task)) == [])
many = [rec(date="2026-10-%02d" % ((i % 10) + 1), start="%02d:00" % (i % 12), end="%02d:30" % (i % 12), task="s%d" % i,
            interruptions=[{"time": "%02d:10" % (i % 12), "cause": "call", "category": "external"}]) for i in range(200)]
d = fda.aggregate_daily(many)
check("edge_many_records", len(d) == 10 and sum(v["sessions"] for v in d.values()) == 200)
check("edge_many_records_score_bounds", all(0.0 <= v["focus_score"] <= 1.0 for v in d.values()))
deep = rec(interruptions=[{"time": "09:%02d" % i, "cause": "c%d" % i} for i in range(10, 60)])
d = fda.aggregate_daily([deep])
check("edge_many_interruptions", d["2026-10-10"]["interruptions"] == 50)
d = fda.aggregate_daily([rec(start="23:30", end="23:59")])
check("edge_late_night_session", d["2026-10-10"]["focus_minutes"] == 29.0)
d = fda.aggregate_daily([rec(start="00:00", end="00:01")])
check("edge_midnight_one_minute", d["2026-10-10"]["focus_minutes"] == 1.0)
check("edge_leap_day_valid", fda.validate_record(rec(date="2024-02-29")) == [])
d = fda.aggregate_daily([rec(start="09:00", end="10:00", interruptions=[])])
check("edge_empty_interruption_list", d["2026-10-10"]["interruptions"] == 0)
code, out = run_cli(["--log", jsonl, "--agg", "day", "--json"])
r = json.loads(out)
check("edge_cli_deterministic", r["aggregates"]["2026-10-10"]["focus_minutes"] == 90.0)

print()
if FAILED:
    print("FAILED CASES:", ", ".join(FAILED))
print("SUMMARY: PASS %d/%d" % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
