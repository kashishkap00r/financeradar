"""Tests for date parsing functions across modules."""

import sys
import os
import unittest
from datetime import datetime, timezone, timedelta

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from reports_fetcher import _parse_date_flexible
from feeds import parse_date


class TestParseDateFlexible(unittest.TestCase):
    """Tests for _parse_date_flexible() in reports_fetcher.py."""

    def test_month_first_abbreviated(self):
        result = _parse_date_flexible("Feb 23, 2026")
        self.assertIsNotNone(result)
        self.assertEqual(result.month, 2)
        self.assertEqual(result.day, 23)
        self.assertEqual(result.year, 2026)

    def test_month_first_full(self):
        result = _parse_date_flexible("February 23, 2026")
        self.assertIsNotNone(result)
        self.assertEqual(result.month, 2)
        self.assertEqual(result.day, 23)

    def test_day_first(self):
        result = _parse_date_flexible("23 Feb 2026")
        self.assertIsNotNone(result)
        self.assertEqual(result.day, 23)
        self.assertEqual(result.month, 2)

    def test_dd_mm_yyyy_slash(self):
        result = _parse_date_flexible("23/02/2026")
        self.assertIsNotNone(result)
        self.assertEqual(result.day, 23)
        self.assertEqual(result.month, 2)

    def test_iso_date(self):
        result = _parse_date_flexible("2026-02-23")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 2)
        self.assertEqual(result.day, 23)

    def test_iso_datetime(self):
        result = _parse_date_flexible("2026-02-23T14:30:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)

    def test_empty_string_returns_none(self):
        self.assertIsNone(_parse_date_flexible(""))

    def test_none_returns_none(self):
        self.assertIsNone(_parse_date_flexible(None))

    def test_garbage_returns_none(self):
        self.assertIsNone(_parse_date_flexible("not a date"))

    def test_all_parsed_dates_are_timezone_aware(self):
        cases = [
            "Feb 23, 2026",
            "February 23, 2026",
            "23 Feb 2026",
            "23/02/2026",
            "2026-02-23",
            "2026-02-23T14:30:00",
        ]
        for date_str in cases:
            with self.subTest(date_str=date_str):
                result = _parse_date_flexible(date_str)
                self.assertIsNotNone(result, f"Failed to parse: {date_str}")
                self.assertIsNotNone(
                    result.tzinfo,
                    f"Parsed date has no tzinfo: {date_str} -> {result}",
                )


class TestParseDate(unittest.TestCase):
    """Tests for parse_date() in feeds.py."""

    def test_rss_format(self):
        result = parse_date("Mon, 23 Feb 2026 14:30:00 +0530")
        self.assertIsNotNone(result)
        self.assertEqual(result.day, 23)
        self.assertEqual(result.month, 2)
        self.assertEqual(result.year, 2026)

    def test_atom_iso_utc(self):
        result = parse_date("2026-02-23T14:30:00Z")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)

    def test_iso_with_offset(self):
        result = parse_date("2026-02-23T14:30:00+05:30")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)

    def test_empty_string_returns_none(self):
        self.assertIsNone(parse_date(""))

    def test_none_returns_none(self):
        self.assertIsNone(parse_date(None))


if __name__ == "__main__":
    unittest.main()
