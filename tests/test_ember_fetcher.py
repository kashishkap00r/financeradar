"""Unit tests for the Ember insights fetcher."""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import reports_fetcher
from reports_fetcher import fetch_ember_cache


def _row(title, slug, days_ago, type_label, description="Excerpt."):
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "title": title,
        "link": f"https://ember-energy.org/latest-insights/{slug}",
        # WordPress returns naive local timestamps, not ISO with an offset.
        "date": dt.replace(tzinfo=None).isoformat(),
        "type": type_label,
        "description": description,
    }


ANALYSIS_CFG = {
    "id": "ember-analysis",
    "name": "Ember — Analysis",
    "url": "https://ember-energy.org/insights/#analysis",
    "feed": "ember:analysis",
    "category": "Reports",
    "region": "International",
    "publisher": "Ember",
}
COMMENTARY_CFG = {**ANALYSIS_CFG, "id": "ember-commentary", "name": "Ember — Commentary", "feed": "ember:commentary"}
POLICY_CFG = {**ANALYSIS_CFG, "id": "ember-policy-papers", "name": "Ember — Policy Papers", "feed": "ember:policy-papers"}


class TestEmberFetcher(unittest.TestCase):
    """Validate insight-type routing, freshness, and cache-absence handling."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.tmpdir, "ember_cache.json")
        patcher = patch.object(reports_fetcher, "_EMBER_CACHE_FILE", self.cache_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmpdir, True)

    def _write(self, items, generated_at=None):
        payload = {
            "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
            "items": items,
        }
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def test_routes_each_insight_type_to_its_own_feed(self):
        self._write([
            _row("Solar hits a quarter of EU power", "eu-solar", 3, "Analysis"),
            _row("A strategic reset on negative emissions", "reset", 5, "Commentary"),
            _row("From oil dependence to electric security", "oil-to-electric", 7, "Policy papers"),
        ])

        self.assertEqual([a["title"] for a in fetch_ember_cache(ANALYSIS_CFG)], ["Solar hits a quarter of EU power"])
        self.assertEqual([a["title"] for a in fetch_ember_cache(COMMENTARY_CFG)], ["A strategic reset on negative emissions"])
        self.assertEqual([a["title"] for a in fetch_ember_cache(POLICY_CFG)], ["From oil dependence to electric security"])

        first = fetch_ember_cache(ANALYSIS_CFG)[0]
        self.assertEqual(first["publisher"], "Ember")
        self.assertEqual(first["region"], "International")
        self.assertEqual(first["feed_id"], "ember-analysis")
        self.assertEqual(first["description"], "Excerpt.")
        self.assertIsNotNone(first["date"].tzinfo)

    def test_drops_items_past_the_30_day_window(self):
        self._write([
            _row("Fresh analysis", "fresh", 10, "Analysis"),
            _row("Ancient analysis", "ancient", 200, "Analysis"),
        ])

        self.assertEqual([a["title"] for a in fetch_ember_cache(ANALYSIS_CFG)], ["Fresh analysis"])

    def test_sorted_newest_first(self):
        self._write([
            _row("Older", "older", 20, "Analysis"),
            _row("Newest", "newest", 1, "Analysis"),
            _row("Middle", "middle", 10, "Analysis"),
        ])

        self.assertEqual([a["title"] for a in fetch_ember_cache(ANALYSIS_CFG)], ["Newest", "Middle", "Older"])

    def test_decodes_html_entities_in_titles(self):
        """WordPress returns rendered HTML, so curly quotes arrive as entities."""
        self._write([_row("UK&#8217;s largest emitter Drax", "drax", 2, "Analysis")])

        self.assertEqual(fetch_ember_cache(ANALYSIS_CFG)[0]["title"], "UK’s largest emitter Drax")

    def test_preexisting_news_feed_id_matches_nothing(self):
        """ember-energy-insights is the Google-RSS News feed; it must not pick up Reports items."""
        self._write([_row("Solar analysis", "solar", 2, "Analysis")])

        self.assertEqual(fetch_ember_cache({**ANALYSIS_CFG, "id": "ember-energy-insights"}), [])

    def test_missing_cache_returns_empty(self):
        self.assertEqual(fetch_ember_cache(ANALYSIS_CFG), [])

    def test_corrupt_cache_returns_empty(self):
        with open(self.cache_path, "w", encoding="utf-8") as f:
            f.write("{not json")

        self.assertEqual(fetch_ember_cache(ANALYSIS_CFG), [])

    def test_skips_rows_missing_title_or_link(self):
        self._write([
            {"title": "", "link": "https://ember-energy.org/latest-insights/x", "date": None, "type": "Analysis"},
            {"title": "No link", "link": "", "date": None, "type": "Analysis"},
            _row("Valid one", "valid", 1, "Analysis"),
        ])

        self.assertEqual([a["title"] for a in fetch_ember_cache(ANALYSIS_CFG)], ["Valid one"])

    def test_stale_cache_still_serves_items_within_window(self):
        """No TTL by design — the per-item date filter is what governs relevance."""
        old = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        self._write([_row("Still fresh", "fresh", 5, "Analysis")], generated_at=old)

        self.assertEqual([a["title"] for a in fetch_ember_cache(ANALYSIS_CFG)], ["Still fresh"])

    def test_registered_in_dispatcher(self):
        for field in ("ember:analysis", "ember:commentary", "ember:policy-papers"):
            self.assertIs(reports_fetcher.get_report_fetcher(field), fetch_ember_cache)


if __name__ == "__main__":
    unittest.main()
