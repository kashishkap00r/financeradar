"""Tests for dropping exact-link duplicates (one story reached via two feeds)."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aggregator import dedupe_by_link


class TestDedupeByLink(unittest.TestCase):

    def test_co_written_issue_kept_once(self):
        link = "https://www.bloomberg.com/news/newsletters/2026-10-21/jio-ipo"
        arts = [{"link": link, "source": "Bloomberg — Markets Daily India"},
                {"link": link, "source": "Bloomberg — Markets Daily India"},
                {"link": "https://example.com/other", "source": "Other"}]
        self.assertEqual([a["link"] for a in dedupe_by_link(arts)], [link, "https://example.com/other"])

    def test_items_without_links_are_kept(self):
        arts = [{"link": "", "title": "a"}, {"link": "", "title": "b"}, {"title": "c"}]
        self.assertEqual(len(dedupe_by_link(arts)), 3)


if __name__ == "__main__":
    unittest.main()
