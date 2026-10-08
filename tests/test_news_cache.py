"""Tests for the rolling news cache (feeds with "keep_days" in feeds.json)."""

import sys
import os
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aggregator import merge_news_cache

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
FEEDS = [
    {"id": "thecore", "name": "The Core", "category": "News", "keep_days": 30},
    {"id": "et", "name": "ET", "category": "News"},
]


def art(feed_id, slug, days_ago):
    return {
        "title": slug.replace("-", " "),
        "link": f"https://example.com/{slug}",
        "source": "The Core" if feed_id == "thecore" else "ET",
        "feed_id": feed_id,
        "date": NOW - timedelta(days=days_ago),
    }


class TestMergeNewsCache(unittest.TestCase):

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.path)  # start with no cache file

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def run_merge(self, fresh):
        return merge_news_cache(list(fresh), FEEDS, self.path, now=NOW)

    def test_keeps_articles_that_left_the_live_feed(self):
        self.run_merge([art("thecore", "old-story", 3)])
        out = self.run_merge([art("thecore", "new-story", 0)])
        links = {a["link"] for a in out}
        self.assertIn("https://example.com/old-story", links)
        self.assertIn("https://example.com/new-story", links)

    def test_restored_dates_are_datetimes(self):
        self.run_merge([art("thecore", "old-story", 3)])
        out = self.run_merge([])
        self.assertEqual(len(out), 1)
        self.assertIsInstance(out[0]["date"], datetime)
        self.assertEqual(out[0]["date"], NOW - timedelta(days=3))

    def test_no_duplicates_when_story_still_live(self):
        self.run_merge([art("thecore", "story", 1)])
        out = self.run_merge([art("thecore", "story", 1)])
        self.assertEqual(len(out), 1)

    def test_prunes_past_keep_days(self):
        self.run_merge([art("thecore", "ancient", 31), art("thecore", "recent", 29)])
        with open(self.path) as f:
            cached = json.load(f)
        self.assertEqual([a["link"] for a in cached["thecore"]], ["https://example.com/recent"])

    def test_ignores_feeds_without_keep_days(self):
        self.run_merge([art("et", "et-story", 1)])
        out = self.run_merge([])
        self.assertEqual(out, [])

    def test_corrupt_cache_file_is_ignored(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        out = self.run_merge([art("thecore", "story", 0)])
        self.assertEqual(len(out), 1)

    def test_drops_cache_for_feeds_no_longer_configured(self):
        with open(self.path, "w") as f:
            json.dump({"removed-feed": [{"link": "x", "date": NOW.isoformat()}]}, f)
        self.run_merge([])
        with open(self.path) as f:
            self.assertNotIn("removed-feed", json.load(f))


if __name__ == "__main__":
    unittest.main()
