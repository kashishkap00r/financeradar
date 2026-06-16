"""Tests for companies_fetcher.py (Tipsheet search-index ingestion)."""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from articles import IST_TZ
from companies_fetcher import (
    load_companies_cache,
    parse_companies,
    save_companies_cache,
)


def _item(**kw):
    base = {
        "s": "filing",
        "u": "/wipro-launches-ai-hub-108928/",
        "h": "Wipro launches Claude AI hub",
        "sym": "WIPRO",
        "sec": "IT - Software",
        "cap": "Mega cap",
        "cat": "Other",
        "sc": 6,
        "t": "2026-06-16 15:46:22",
    }
    base.update(kw)
    return base


class TestCompaniesFetcher(unittest.TestCase):
    def setUp(self):
        # Fixed "now" so freshness math is deterministic.
        self.now = datetime(2026, 6, 16, 18, 0, 0, tzinfo=IST_TZ)

    def test_maps_core_fields_and_absolute_url(self):
        items = parse_companies({"items": [_item()]}, now=self.now)
        self.assertEqual(len(items), 1)
        c = items[0]
        self.assertEqual(c["title"], "Wipro launches Claude AI hub")
        self.assertEqual(c["link"], "https://tipsheet.markets/wipro-launches-ai-hub-108928/")
        self.assertEqual(c["source_url"], c["link"])
        self.assertEqual(c["ticker"], "WIPRO")
        self.assertEqual(c["sector"], "IT - Software")
        self.assertEqual(c["cap"], "Mega cap")
        self.assertEqual(c["category"], "Other")
        self.assertEqual(c["score"], 6)
        self.assertEqual(c["source"], "Tipsheet")

    def test_parses_naive_ist_timestamp(self):
        items = parse_companies([_item()], now=self.now)
        dt = items[0]["date"]
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, IST_TZ)
        self.assertEqual(dt.strftime("%Y-%m-%d %H:%M"), "2026-06-16 15:46")

    def test_drops_non_filing_records(self):
        payload = [_item(), _item(s="article", u="/some-blog/", h="A blog post")]
        items = parse_companies(payload, now=self.now)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["ticker"], "WIPRO")

    def test_drops_stale_filings_beyond_freshness_window(self):
        old_t = (self.now - timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S")
        payload = [_item(), _item(u="/old-100000/", h="Old filing", sym="OLD", t=old_t)]
        items = parse_companies(payload, now=self.now)
        syms = {c["ticker"] for c in items}
        self.assertIn("WIPRO", syms)
        self.assertNotIn("OLD", syms)

    def test_dedups_by_link(self):
        payload = [_item(), _item(h="Wipro launches Claude AI hub (dup)")]
        items = parse_companies(payload, now=self.now)
        self.assertEqual(len(items), 1)

    def test_default_sort_is_score_desc_then_date(self):
        payload = [
            _item(u="/a-1/", h="A", sym="A", sc=5, t="2026-06-16 09:00:00"),
            _item(u="/b-2/", h="B", sym="B", sc=9, t="2026-06-10 09:00:00"),
            _item(u="/c-3/", h="C", sym="C", sc=9, t="2026-06-15 09:00:00"),
        ]
        items = parse_companies(payload, now=self.now)
        self.assertEqual([c["ticker"] for c in items], ["C", "B", "A"])

    def test_handles_wrapped_and_bare_payloads(self):
        bare = parse_companies([_item()], now=self.now)
        wrapped = parse_companies({"items": [_item()]}, now=self.now)
        self.assertEqual(len(bare), 1)
        self.assertEqual(len(wrapped), 1)

    def test_cache_round_trip(self):
        items = parse_companies([_item()], now=self.now)
        with tempfile.TemporaryDirectory() as tmp:
            cache_file = os.path.join(tmp, "companies_cache.json")
            generated_at = save_companies_cache(cache_file, items)
            cached, cached_generated_at = load_companies_cache(cache_file)
        self.assertTrue(generated_at)
        self.assertEqual(cached_generated_at, generated_at)
        self.assertEqual(len(cached), 1)
        self.assertEqual(cached[0]["cap"], "Mega cap")
        self.assertIsNotNone(cached[0]["date"])

    def test_missing_cache_returns_empty(self):
        companies, generated_at = load_companies_cache("/nonexistent/path/x.json")
        self.assertEqual(companies, [])
        self.assertEqual(generated_at, "")


if __name__ == "__main__":
    unittest.main()
