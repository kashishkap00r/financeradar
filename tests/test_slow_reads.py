"""Tests for the Slow Reads homepage strip selection in aggregator.py."""

import sys
import os
import unittest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aggregator import select_slow_reads
from config import (SLOW_READS_MAX_PER_SOURCE, SLOW_READS_MAX_ITEMS, SLOW_READS_WINDOW_DAYS,
                    SLOW_READS_SOURCES)

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)


def art(source, days_ago, title=None, link=None, publisher=""):
    title = title or f"{source} post {days_ago}"
    return {
        "title": title,
        "link": link or f"https://example.com/{source}/{days_ago}/{title}".replace(" ", "-"),
        "source": source,
        "publisher": publisher,
        "date": NOW - timedelta(days=days_ago),
    }


class TestSelectSlowReads(unittest.TestCase):

    def test_strip_has_a_slot_for_every_source(self):
        # Otherwise a source's newest post can be crowded out by the others
        self.assertGreaterEqual(SLOW_READS_MAX_ITEMS, len(SLOW_READS_SOURCES))

    def test_keeps_posts_older_than_news_window(self):
        picked = select_slow_reads([art("The LEAP Blog", 6)], now=NOW)
        self.assertEqual(len(picked), 1)
        self.assertEqual(picked[0]["source"], "The LEAP Blog")

    def test_drops_posts_outside_window(self):
        picked = select_slow_reads([art("The LEAP Blog", SLOW_READS_WINDOW_DAYS + 1)], now=NOW)
        self.assertEqual(picked, [])

    def test_ignores_sources_not_in_list(self):
        # OWID Data Insights is daily — deliberately excluded even though OWID articles are in
        picked = select_slow_reads([art("Our World in Data — Data Insights", 1),
                                    art("Economic Times — Latest", 1)], now=NOW)
        self.assertEqual(picked, [])

    def test_caps_per_source(self):
        batch = [art("The India Forum", d) for d in range(1, 6)]
        picked = select_slow_reads(batch, now=NOW)
        self.assertEqual(len(picked), SLOW_READS_MAX_PER_SOURCE)
        # and keeps the newest ones
        self.assertEqual(picked[0]["title"], "The India Forum post 1")

    def test_sorted_newest_first_across_sources(self):
        picked = select_slow_reads([art("India Dispatch", 12), art("The LEAP Blog", 6),
                                    art("Ember Energy", 2)], now=NOW)
        self.assertEqual([p["source"] for p in picked],
                         ["Ember Energy", "The LEAP Blog", "India Dispatch"])

    def test_caps_total_items(self):
        sources = ["India Dispatch", "By the Numbers", "SOIC", "Ideas For India", "Ember Energy",
                   "The LEAP Blog", "Business Standard", "Market Bites", "Capital Quill",
                   "Our World in Data", "The Morning Context", "The India Forum"]
        many = [art(s, d) for s in sources for d in (1, 2)]
        self.assertEqual(len(select_slow_reads(many, now=NOW)), SLOW_READS_MAX_ITEMS)

    def test_slowest_source_not_crowded_out_by_frequent_ones(self):
        # 12 sources each with a fresh 2nd post would fill 20 slots on recency alone;
        # India Dispatch's single 25-day-old post must still get its slot.
        sources = ["By the Numbers", "SOIC", "Ideas For India", "Ember Energy",
                   "The LEAP Blog", "Business Standard", "Market Bites", "Capital Quill",
                   "Our World in Data", "The Morning Context", "The India Forum",
                   "SOIC Wisdom Board"]
        busy = [art(s, d) for s in sources for d in (1, 2)]
        picked = select_slow_reads(busy + [art("India Dispatch", 25)], now=NOW)
        self.assertIn("India Dispatch", [p["source"] for p in picked])
        self.assertEqual(picked[-1]["source"], "India Dispatch")  # still date-ordered

    def test_skips_titles_that_are_just_the_site_name(self):
        junk = art("Ideas For India", 1, title="ideasforindia", publisher="Ideas For India")
        real = art("Ideas For India", 2, title="Female leadership and CSR", publisher="Ideas For India")
        picked = select_slow_reads([junk, real], now=NOW)
        self.assertEqual([p["title"] for p in picked], ["Female leadership and CSR"])

    def test_skips_undated_and_duplicate_links(self):
        undated = art("The LEAP Blog", 1)
        undated["date"] = None
        a = art("India Dispatch", 3, link="https://example.com/same")
        b = art("India Dispatch", 4, link="https://example.com/same")
        picked = select_slow_reads([undated, a, b], now=NOW)
        self.assertEqual(len(picked), 1)

    def test_publisher_falls_back_to_source_and_date_is_iso(self):
        picked = select_slow_reads([art("Market Bites", 2)], now=NOW)
        self.assertEqual(picked[0]["publisher"], "Market Bites")
        self.assertTrue(picked[0]["date"].startswith("2026-09-27"))


if __name__ == "__main__":
    unittest.main()
