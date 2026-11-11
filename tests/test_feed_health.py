"""Quiet-feeds tracking (feed_health.py)."""

import unittest
from datetime import datetime, timedelta

from articles import IST_TZ
from feed_health import quiet_feeds, record_run, record_stock_notes, report_markdown

NOW = datetime(2026, 11, 12, 10, 0, tzinfo=IST_TZ)


def _feeds():
    return [
        {"id": "daily", "name": "Daily News", "category": "News"},
        {"id": "monthly", "name": "Monthly Reports", "category": "Reports"},
        {"id": "slow", "name": "Slow Blog", "category": "News", "quiet_days": 120},
        {"id": "tw", "name": "Some Handle", "category": "Twitter"},
        {"id": "kotak", "name": "Kotak", "category": "Reports", "kind": "stock_note", "publisher": "Kotak Securities", "feed": "kotaksec:x"},
    ]


class TestFeedHealth(unittest.TestCase):
    def test_newest_date_only_moves_forward(self):
        data = {}
        record_run(data, {"daily": ([{"date": NOW - timedelta(days=2)}], "")}, now=NOW)
        record_run(data, {"daily": ([], "HTTP 403")}, now=NOW)  # a failed run doesn't erase what we know
        e = data["feeds"]["daily"]
        self.assertEqual((e["newest"], e["last_count"], e["last_error"]), ("2026-11-10", 0, "HTTP 403"))

    def test_quiet_uses_category_limits_and_overrides(self):
        data = {"tracking_since": "2026-11-01", "feeds": {
            "daily": {"newest": "2026-10-25"}, "monthly": {"newest": "2026-10-25"}, "slow": {"newest": "2026-08-01"}}}
        quiet = quiet_feeds(_feeds(), data, now=NOW)
        self.assertEqual([(f["id"], d) for f, d, _ in quiet], [("daily", 18)])  # Reports get 30 days, slow has 120; Twitter skipped

    def test_never_seen_is_quiet_only_after_the_limit(self):
        data = {"tracking_since": "2026-11-10", "feeds": {}}
        self.assertEqual(quiet_feeds([_feeds()[0]], data, now=NOW), [])
        data["tracking_since"] = "2026-10-01"
        self.assertEqual([(f["id"], d) for f, d, _ in quiet_feeds([_feeds()[0]], data, now=NOW)], [("daily", None)])

    def test_stock_note_feeds_use_the_archive(self):
        data = {}
        archive = [{"broker": "Kotak Securities", "via": "", "date": "2026-11-09"},
                   {"broker": "Kotak Securities", "via": "Moneycontrol", "date": "2026-11-11"}]  # middleman copies don't count
        record_stock_notes(data, _feeds(), archive)
        self.assertEqual(data["feeds"]["kotak"]["newest"], "2026-11-09")

    def test_report_text(self):
        self.assertIn("All feeds", report_markdown([], {}))
        data = {"feeds": {"daily": {"newest": "2026-10-25", "last_error": "HTTP 403 | blocked"}}}
        text = report_markdown([(_feeds()[0], 18, 10)], data)
        self.assertIn("| Daily News | News | 2026-10-25 | 18 days | 10 days | HTTP 403 / blocked |", text)


if __name__ == "__main__":
    unittest.main()
