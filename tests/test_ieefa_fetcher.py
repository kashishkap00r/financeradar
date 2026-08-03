"""Unit tests for the IEEFA reports/insights fetcher."""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import patch

import reports_fetcher
from reports_fetcher import fetch_ieefa


def _item(title, slug, days_ago, type_label, typed=True):
    """Build one <item> block shaped like ieefa.org/rss.xml."""
    pub = format_datetime(datetime.now(timezone.utc) - timedelta(days=days_ago))
    # The real feed HTML-escapes the description and wraps the resource type in
    # a bare <div>, preceded by an empty one and followed by topic/region groups.
    type_div = f"&lt;div&gt;{type_label}&lt;/div&gt;" if typed else ""
    return f"""<item>
  <title>{title}</title>
  <link>https://ieefa.org/resources/{slug}</link>
  <description>&lt;span&gt;{title}&lt;/span&gt;
&lt;span&gt;&lt;time datetime="2026-08-01T10:00:00+01:00"&gt;Sat, 08/01/2026 - 10:00&lt;/time&gt;&lt;/span&gt;
&lt;div&gt;&lt;/div&gt;
{type_div}
&lt;div&gt;&lt;div&gt;Coal&lt;/div&gt;&lt;div&gt;Energy Policy&lt;/div&gt;&lt;/div&gt;
</description>
  <pubDate>{pub}</pubDate>
</item>"""


def _rss(*items):
    return "<?xml version='1.0' encoding='utf-8'?><rss><channel>" + "".join(items) + "</channel></rss>"


REPORTS_CFG = {
    "id": "ieefa-reports",
    "name": "IEEFA — Reports",
    "url": "https://ieefa.org/research-hub?keys=&tid_1%5B6%5D=6",
    "feed": "ieefa:reports",
    "category": "Reports",
    "region": "International",
    "publisher": "IEEFA",
}

INSIGHTS_CFG = {**REPORTS_CFG, "id": "ieefa-insights", "name": "IEEFA — Insights", "feed": "ieefa:insights"}


class TestIeefaFetcher(unittest.TestCase):
    """Validate resource-type routing, accumulation, and failure handling."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.tmpdir, "ieefa_cache.json")
        patcher = patch.object(reports_fetcher, "_IEEFA_CACHE_FILE", self.cache_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        # The refresh memo is process-global; each test starts from a clean slate.
        reports_fetcher._ieefa_refreshed = False
        self.addCleanup(setattr, reports_fetcher, "_ieefa_refreshed", False)

    def _write_cache(self, items):
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "items": items}, f)

    @patch("reports_fetcher._fetch_url")
    def test_routes_each_resource_type_to_its_own_feed(self, mock_fetch):
        mock_fetch.return_value = _rss(
            _item("Coking coal methane report", "coking-coal", 2, "Report"),
            _item("Oil chokepoint blockage", "chokepoint", 1, "Insights"),
            _item("NSW submission", "nsw-submission", 1, "Testimony | Submission"),
            _item("Methane briefing", "methane-brief", 3, "Briefing Note"),
        ).encode("utf-8")

        reports = fetch_ieefa(REPORTS_CFG)
        self.assertEqual([a["title"] for a in reports], ["Coking coal methane report"])

        reports_fetcher._ieefa_refreshed = False
        insights = fetch_ieefa(INSIGHTS_CFG)
        self.assertEqual([a["title"] for a in insights], ["Oil chokepoint blockage"])

        first = reports[0]
        self.assertEqual(first["link"], "https://ieefa.org/resources/coking-coal")
        self.assertEqual(first["publisher"], "IEEFA")
        self.assertEqual(first["region"], "International")
        self.assertEqual(first["feed_id"], "ieefa-reports")
        self.assertIsNotNone(first["date"])
        self.assertIsNotNone(first["date"].tzinfo)

    @patch("reports_fetcher._fetch_url")
    def test_skips_items_with_no_resource_type(self, mock_fetch):
        """Press releases under /articles/ carry no type div and must not leak in."""
        mock_fetch.return_value = _rss(
            _item("Untyped press release", "press-release", 1, "", typed=False),
            _item("Real report", "real-report", 1, "Report"),
        ).encode("utf-8")

        self.assertEqual([a["title"] for a in fetch_ieefa(REPORTS_CFG)], ["Real report"])

    @patch("reports_fetcher._fetch_url")
    def test_accumulates_across_runs(self, mock_fetch):
        """The 10-item firehose must add to the cache, not replace it."""
        mock_fetch.return_value = _rss(_item("Older report", "older", 8, "Report")).encode("utf-8")
        self.assertEqual(len(fetch_ieefa(REPORTS_CFG)), 1)

        # Next run: the older item has rotated out of the sitewide feed.
        reports_fetcher._ieefa_refreshed = False
        mock_fetch.return_value = _rss(_item("Newer report", "newer", 1, "Report")).encode("utf-8")
        titles = [a["title"] for a in fetch_ieefa(REPORTS_CFG)]

        self.assertEqual(titles, ["Newer report", "Older report"])

    @patch("reports_fetcher._fetch_url")
    def test_prunes_items_past_the_cache_window(self, mock_fetch):
        stale = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        self._write_cache([
            {"title": "Ancient report", "link": "https://ieefa.org/resources/ancient", "date": stale, "type": "Report"},
        ])
        mock_fetch.return_value = _rss(_item("Fresh report", "fresh", 1, "Report")).encode("utf-8")

        self.assertEqual([a["title"] for a in fetch_ieefa(REPORTS_CFG)], ["Fresh report"])

        with open(self.cache_path, encoding="utf-8") as f:
            cached_links = [i["link"] for i in json.load(f)["items"]]
        self.assertNotIn("https://ieefa.org/resources/ancient", cached_links)

    @patch("reports_fetcher._fetch_url")
    def test_network_failure_serves_cache(self, mock_fetch):
        recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        self._write_cache([
            {"title": "Cached report", "link": "https://ieefa.org/resources/cached", "date": recent, "type": "Report"},
        ])
        mock_fetch.side_effect = Exception("403 Forbidden")

        self.assertEqual([a["title"] for a in fetch_ieefa(REPORTS_CFG)], ["Cached report"])

    @patch("reports_fetcher._fetch_url")
    def test_second_feed_reuses_the_single_network_call(self, mock_fetch):
        mock_fetch.return_value = _rss(
            _item("A report", "a-report", 1, "Report"),
            _item("An insight", "an-insight", 1, "Insights"),
        ).encode("utf-8")

        self.assertEqual(len(fetch_ieefa(REPORTS_CFG)), 1)
        self.assertEqual(len(fetch_ieefa(INSIGHTS_CFG)), 1)
        self.assertEqual(mock_fetch.call_count, 1)

    @patch("reports_fetcher._fetch_url")
    def test_unknown_feed_id_returns_nothing(self, mock_fetch):
        """An unmapped IEEFA feed must not fall through to the whole firehose."""
        mock_fetch.return_value = _rss(_item("A report", "a-report", 1, "Report")).encode("utf-8")

        self.assertEqual(fetch_ieefa({**REPORTS_CFG, "id": "ieefa-slides"}), [])
        mock_fetch.assert_not_called()

    @patch("reports_fetcher._fetch_url")
    def test_unreadable_cache_does_not_clobber_accumulation(self, mock_fetch):
        """A transient bad read must not replace months of history with one RSS window.

        Regression: the local rsshub systemd timer's git operations raced an
        aggregator run, the load came back empty, and the refresh wrote back
        only the 8 items then in the firehose — destroying the accumulation.
        """
        recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        self._write_cache([
            {"title": f"Accumulated {i}", "link": f"https://ieefa.org/resources/acc-{i}",
             "date": recent, "type": "Report"}
            for i in range(20)
        ])
        mock_fetch.return_value = _rss(_item("Only fresh one", "fresh", 1, "Report")).encode("utf-8")

        with patch.object(reports_fetcher, "_ieefa_load_cache", return_value={}):
            fetch_ieefa(REPORTS_CFG)

        with open(self.cache_path, encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)["items"]), 20)

    @patch("reports_fetcher._fetch_url")
    def test_empty_cache_file_still_gets_written(self, mock_fetch):
        """The guard must not block the legitimate first write."""
        mock_fetch.return_value = _rss(_item("First report", "first", 1, "Report")).encode("utf-8")

        self.assertEqual(len(fetch_ieefa(REPORTS_CFG)), 1)
        with open(self.cache_path, encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)["items"]), 1)

    @patch("reports_fetcher._fetch_url")
    def test_write_is_atomic_and_leaves_no_temp_file(self, mock_fetch):
        mock_fetch.return_value = _rss(_item("A report", "a-report", 1, "Report")).encode("utf-8")

        fetch_ieefa(REPORTS_CFG)

        self.assertFalse(os.path.exists(self.cache_path + ".tmp"))
        self.assertTrue(os.path.exists(self.cache_path))

    def test_atomic_write_cleans_up_after_an_unserializable_payload(self):
        """A cache write must never raise, nor strand a partial .tmp file."""
        target = os.path.join(self.tmpdir, "nested", "out.json")

        ok = reports_fetcher._atomic_write_json(target, {"bad": datetime.now()}, "test")

        self.assertFalse(ok)
        self.assertFalse(os.path.exists(target + ".tmp"))
        self.assertFalse(os.path.exists(target))

        # And a subsequent good write still succeeds into the same location.
        self.assertTrue(reports_fetcher._atomic_write_json(target, {"good": 1}, "test"))
        with open(target, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"good": 1})

    def test_registered_in_dispatcher(self):
        self.assertIs(reports_fetcher.get_report_fetcher("ieefa:reports"), fetch_ieefa)
        self.assertIs(reports_fetcher.get_report_fetcher("ieefa:insights"), fetch_ieefa)


if __name__ == "__main__":
    unittest.main()
