"""Tests for the homepage "This Week" calendar (calendar_events.py):
Nifty 200 results from NSE's event calendar, market dates worked out by rule,
the hand-kept macro file, and the JSON / .ics the browser and calendar apps read."""

import json
import os
import tempfile
import unittest
from datetime import date, datetime

import calendar_events as ce


INDEX_CSV = (
    "Company Name,Industry,Symbol,Series,ISIN Code\n"
    "Tata Steel Ltd.,Metals & Mining,TATASTEEL,EQ,INE081A01020\n"
    "Hindustan Aeronautics Ltd.,Capital Goods,HAL,EQ,INE066F01020\n"
    "Page Industries Limited,Textiles,PAGEIND,EQ,INE761H01022\n"
)

NSE_EVENTS = [
    {"symbol": "HAL", "company": "Hindustan Aeronautics Limited", "purpose": "Financial Results",
     "bm_desc": "To consider and approve the financial results", "date": "12-Nov-2026"},
    {"symbol": "PAGEIND", "company": "Page Industries Limited", "purpose": "Financial Results/Dividend",
     "bm_desc": "results and dividend", "date": "12-Nov-2026"},
    {"symbol": "TATASTEEL", "company": "Tata Steel Limited", "purpose": "Fund Raising",
     "bm_desc": "fund raising", "date": "13-Nov-2026"},
    {"symbol": "ACE", "company": "Action Construction Equipment Limited", "purpose": "Financial Results",
     "bm_desc": "not in the index", "date": "12-Nov-2026"},
    {"symbol": "HAL", "company": "Hindustan Aeronautics Limited", "purpose": "Financial Results",
     "bm_desc": "bad date", "date": "sometime"},
]


class IndexTests(unittest.TestCase):
    def test_parse_index_csv_and_short_names(self):
        rows = ce.parse_index_csv(INDEX_CSV)
        self.assertEqual(rows["TATASTEEL"], "Tata Steel")
        self.assertEqual(rows["HAL"], "Hindustan Aeronautics")
        self.assertEqual(rows["PAGEIND"], "Page Industries")

    def test_short_company_name(self):
        self.assertEqual(ce.short_company_name("Mahindra & Mahindra Ltd."), "Mahindra & Mahindra")
        self.assertEqual(ce.short_company_name("Bharat Electronics Limited"), "Bharat Electronics")
        self.assertEqual(ce.short_company_name("  360 ONE WAM Ltd. "), "360 ONE WAM")

    def test_build_index_tiers(self):
        index = ce.build_index({
            50: {"TATASTEEL": "Tata Steel"},
            100: {"TATASTEEL": "Tata Steel", "HAL": "Hindustan Aeronautics"},
            200: {"TATASTEEL": "Tata Steel", "HAL": "Hindustan Aeronautics", "PAGEIND": "Page Industries"},
        })
        self.assertEqual(index["TATASTEEL"]["tier"], 1)
        self.assertEqual(index["HAL"]["tier"], 2)
        self.assertEqual(index["PAGEIND"]["tier"], 3)
        self.assertEqual(index["HAL"]["name"], "HAL")  # common name wins over the official one


class ResultsTests(unittest.TestCase):
    def setUp(self):
        self.index = {
            "TATASTEEL": {"name": "Tata Steel", "tier": 1},
            "HAL": {"name": "Hindustan Aeronautics", "tier": 2},
            "PAGEIND": {"name": "Page Industries", "tier": 3},
        }

    def test_only_index_members_with_financial_results(self):
        got = ce.parse_event_calendar(NSE_EVENTS, self.index)
        self.assertEqual(sorted((r["date"], r["symbol"]) for r in got),
                         [("2026-11-12", "HAL"), ("2026-11-12", "PAGEIND")])

    def test_merge_keeps_today_from_cache_and_trusts_fresh_for_the_future(self):
        today = date(2026, 11, 12)
        cached = [
            {"date": "2026-11-10", "symbol": "OLD"},        # too old, dropped
            {"date": "2026-11-12", "symbol": "TATASTEEL"},  # today: NSE no longer lists it, keep
            {"date": "2026-11-14", "symbol": "HAL"},        # rescheduled in fresh, dropped
            {"date": "2026-11-15", "symbol": "GONE"},       # future, missing from fresh: cancelled
        ]
        fresh = [{"date": "2026-11-18", "symbol": "HAL"}]
        got = ce.merge_results(cached, fresh, today, fetched_ok=True)
        self.assertEqual(got, [
            {"date": "2026-11-12", "symbol": "TATASTEEL"},
            {"date": "2026-11-18", "symbol": "HAL"},
        ])

    def test_merge_keeps_cache_when_fetch_failed(self):
        today = date(2026, 11, 12)
        cached = [{"date": "2026-11-10", "symbol": "OLD"}, {"date": "2026-11-15", "symbol": "HAL"}]
        got = ce.merge_results(cached, [], today, fetched_ok=False)
        self.assertEqual(got, [{"date": "2026-11-15", "symbol": "HAL"}])

    def test_merge_drops_todays_entry_when_company_moved_to_later(self):
        today = date(2026, 11, 12)
        cached = [{"date": "2026-11-12", "symbol": "HAL"}]
        fresh = [{"date": "2026-11-20", "symbol": "HAL"}]
        got = ce.merge_results(cached, fresh, today, fetched_ok=True)
        self.assertEqual(got, [{"date": "2026-11-20", "symbol": "HAL"}])


class MarketDateTests(unittest.TestCase):
    def test_monthly_expiry_is_last_tuesday(self):
        self.assertEqual(ce.monthly_expiry(2026, 12, {}), date(2026, 12, 29))

    def test_monthly_expiry_moves_back_over_a_holiday(self):
        # 24 Nov 2026 (last Tuesday) is Guru Nanak Jayanti: expiry moves to Monday 23 Nov.
        holidays = {"2026-11-24": "Guru Nanak Jayanti"}
        self.assertEqual(ce.monthly_expiry(2026, 11, holidays), date(2026, 11, 23))

    def test_results_deadlines(self):
        events = ce.results_deadline_events(date(2026, 11, 1), date(2027, 6, 30))
        got = [(e["date"], e["name"]) for e in events]
        self.assertIn(("2026-11-14", "Last day for September-quarter results"), got)
        self.assertIn(("2027-02-14", "Last day for December-quarter results"), got)
        self.assertIn(("2027-05-30", "Last day for March-quarter results"), got)

    def test_forex_reserves_every_friday(self):
        events = ce.forex_reserve_events(date(2026, 11, 11), date(2026, 11, 30))
        self.assertEqual([e["date"] for e in events], ["2026-11-13", "2026-11-20", "2026-11-27"])

    def test_holiday_events_skip_weekends(self):
        holidays = {"2026-11-08": "Diwali Laxmi Pujan", "2026-11-24": "Guru Nanak Jayanti"}
        events = ce.holiday_events(holidays, date(2026, 11, 1), date(2026, 11, 30))
        self.assertEqual([(e["date"], e["name"]) for e in events], [("2026-11-24", "Markets shut: Guru Nanak Jayanti")])

    def test_parse_holidays(self):
        data = {"CM": [{"tradingDate": "24-Nov-2026", "description": "Prakash Gurpurb Sri Guru Nanak Dev"},
                       {"tradingDate": "junk", "description": "x"}]}
        self.assertEqual(ce.parse_holidays(data), {"2026-11-24": "Prakash Gurpurb Sri Guru Nanak Dev"})


class BuildTests(unittest.TestCase):
    def test_build_days_orders_events_and_results(self):
        index = {
            "TATASTEEL": {"name": "Tata Steel", "tier": 1},
            "HAL": {"name": "Hindustan Aeronautics", "tier": 2},
            "ABB": {"name": "ABB India", "tier": 3},
        }
        events = [
            {"date": "2026-11-12", "time": "19:00", "name": "US CPI, October", "kind": "global"},
            {"date": "2026-11-12", "time": "16:00", "name": "CPI inflation, October", "kind": "india", "big": True},
            {"date": "2026-11-12", "time": None, "name": "Untimed thing", "kind": "policy"},
            {"date": "2026-12-30", "time": None, "name": "Outside window", "kind": "india"},
        ]
        results = [
            {"date": "2026-11-12", "symbol": "ABB"},
            {"date": "2026-11-12", "symbol": "TATASTEEL"},
            {"date": "2026-11-12", "symbol": "HAL"},
            {"date": "2026-11-13", "symbol": "MISSING"},  # dropped from the index since: skipped
        ]
        days = ce.build_days(events, results, index, date(2026, 11, 11), date(2026, 11, 20))
        self.assertEqual([d["date"] for d in days], ["2026-11-12"])
        self.assertEqual([e["name"] for e in days[0]["events"]],
                         ["CPI inflation, October", "US CPI, October", "Untimed thing"])
        self.assertEqual(days[0]["results"], ["Tata Steel", "Hindustan Aeronautics", "ABB India"])

    def test_load_macro_events_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "macro.json")
            with open(path, "w") as f:
                json.dump({"events": [
                    {"date": "2026-11-12", "time": "16:00", "name": "CPI inflation, October", "short": "CPI",
                     "kind": "india", "big": True, "source": "MoSPI", "confirmed": True},
                    {"date": "bad", "name": "Broken"},
                    {"date": "2026-11-13", "name": "Odd kind", "kind": "weird"},
                    {"date": "2026-11-14", "time": "25:00", "name": "Bad time", "kind": "india"},
                ]}, f)
            got = ce.load_macro_events(path)
        self.assertEqual([e["name"] for e in got], ["CPI inflation, October", "Bad time"])
        self.assertIsNone(got[1]["time"])

    def test_ics_has_timed_and_all_day_events(self):
        days = [{"date": "2026-11-12", "events": [
            {"name": "CPI inflation, October", "time": "16:00", "kind": "india", "source": "MoSPI", "big": True},
            {"name": "Last day for September-quarter results", "time": None, "kind": "market"},
        ], "results": ["Tata Steel", "Hindustan Aeronautics"]}]
        ics = ce.build_ics(days, datetime(2026, 11, 11, 6, 0))
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertIn("DTSTART:20261112T103000Z", ics)  # 4 pm IST
        self.assertIn("DTSTART;VALUE=DATE:20261112", ics)
        self.assertIn("SUMMARY:Results: Tata Steel\\, Hindustan Aeronautics", ics)
        self.assertTrue(ics.endswith("END:VCALENDAR\r\n"))
        for line in ics.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75)


if __name__ == "__main__":
    unittest.main()
