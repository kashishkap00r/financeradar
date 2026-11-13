"""RBI Bulletin + speeches: clean RSS titles, and the From the Source wiring."""

import json
import os
import unittest

import config
import feeds

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TidyRbiTitlesTests(unittest.TestCase):
    def test_cleans_entities_footnotes_and_dangling_dash(self):
        rows = [
            {"title": "Economic Resilience: Where Does India Stand?<sup>[1]</sup>"},
            {"title": "RBI Podcast: From Paisa to Policy | Understanding CBDC - "},
            {"title": "Underwriting Auction for &#8377;34,000 crore"},
        ]
        self.assertEqual([r["title"] for r in feeds.tidy_rbi_titles(rows)], [
            "Economic Resilience: Where Does India Stand?",
            "RBI Podcast: From Paisa to Policy | Understanding CBDC",
            "Underwriting Auction for ₹34,000 crore",
        ])

    def test_drops_hindi_only_titles(self):
        rows = [{"title": "&#2327;&#2357;&#2352;&#2381;&#2344;&#2352; &#2325;&#2366; - RBI &#2325;&#2375; &#2337;&#2375;"},
                {"title": "Speech - RBI"}]
        self.assertEqual([r["title"] for r in feeds.tidy_rbi_titles(rows)], ["Speech - RBI"])


class WiringTests(unittest.TestCase):
    def test_long_life_sources_match_feed_names_and_frontend(self):
        names = {f["name"]: f for f in json.load(open(os.path.join(ROOT, "feeds.json"), encoding="utf-8"))}
        app = open(os.path.join(ROOT, "templates", "app.js"), encoding="utf-8").read()
        for name in config.RBI_LONG_LIFE_SOURCES:
            self.assertIn(name, names)
            self.assertEqual(names[name]["publisher"], "RBI")
            self.assertGreaterEqual(names[name].get("keep_days", 0), config.RBI_LONG_LIFE_DAYS)
            self.assertIn(f"'{name}': true", app)


if __name__ == "__main__":
    unittest.main()
