"""Tests for collapsing one story that arrives twice under different links.

Google News lists some Morning Context stories under two URLs, ~12 hours apart,
each behind its own opaque news.google.com link, so dedupe_by_link misses them.
"""

import sys
import os
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aggregator import dedupe_same_title

T0 = datetime(2026, 10, 21, 7, 0, tzinfo=timezone.utc)


def art(title, link, hours, source="The Morning Context"):
    return {"title": title, "link": link, "source": source, "date": T0 + timedelta(hours=hours)}


class TestDedupeSameTitle(unittest.TestCase):

    def test_same_story_twice_keeps_earliest(self):
        out = dedupe_same_title([
            art("The hidden cost of India’s derivatives obsession", "https://g/late", 12),
            art("The hidden cost of India’s derivatives obsession", "https://g/early", 0),
        ])
        self.assertEqual([a["link"] for a in out], ["https://g/early"])

    def test_weekly_series_with_same_title_kept(self):
        out = dedupe_same_title([art("The Gulf Report", "https://g/a", 0),
                                 art("The Gulf Report", "https://g/b", 24 * 7)])
        self.assertEqual(len(out), 2)

    def test_different_sources_kept(self):
        out = dedupe_same_title([art("Markets wrap", "https://a", 0, "ET"),
                                 art("Markets wrap", "https://b", 1, "Mint")])
        self.assertEqual(len(out), 2)

    def test_undated_and_untitled_items_kept(self):
        out = dedupe_same_title([{"title": "", "link": "x", "source": "S"},
                                 {"title": "", "link": "y", "source": "S"},
                                 {"title": "A", "link": "z", "source": "S", "date": None}])
        self.assertEqual(len(out), 3)


if __name__ == "__main__":
    unittest.main()
