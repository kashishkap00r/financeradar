"""Tests for report fetch timeout/retry overrides and report identity fields."""

import unittest
from unittest.mock import patch
import urllib.error

from config import (
    SCRAPER_FETCH_TIMEOUT,
    SCRAPER_RETRY_ATTEMPTS,
    SCRAPER_TIMEOUT_OVERRIDES,
)
from reports_fetcher import _fetch_url, _make_article


class TestReportFetcherOverrides(unittest.TestCase):
    """Verify source-specific fetch behavior for report scrapers."""

    @patch("reports_fetcher.time.sleep", return_value=None)
    @patch("reports_fetcher.urllib.request.urlopen")
    def test_baroda_uses_fail_fast_timeout_and_zero_retries(self, mock_urlopen, _mock_sleep):
        mock_urlopen.side_effect = urllib.error.URLError("timed out")

        with self.assertRaises(urllib.error.URLError):
            _fetch_url(
                "https://www.barodaetrade.com/research-Details/STR",
                feed_config={"id": "baroda-etrade-str"},
            )

        self.assertEqual(len(mock_urlopen.call_args_list), 1)
        self.assertEqual(
            mock_urlopen.call_args_list[0].kwargs.get("timeout"),
            SCRAPER_TIMEOUT_OVERRIDES["baroda-etrade-str"],
        )

    @patch("reports_fetcher.time.sleep", return_value=None)
    @patch("reports_fetcher.urllib.request.urlopen")
    def test_default_sources_keep_standard_timeout_and_retries(self, mock_urlopen, _mock_sleep):
        mock_urlopen.side_effect = urllib.error.URLError("timed out")

        with self.assertRaises(urllib.error.URLError):
            _fetch_url(
                "https://example.com/reports",
                feed_config={"id": "some-other-source"},
            )

        self.assertEqual(len(mock_urlopen.call_args_list), SCRAPER_RETRY_ATTEMPTS + 1)
        self.assertEqual(
            mock_urlopen.call_args_list[0].kwargs.get("timeout"),
            SCRAPER_FETCH_TIMEOUT,
        )

    def test_make_article_includes_feed_id(self):
        feed_cfg = {
            "id": "baroda-etrade-str",
            "name": "Baroda eTrade — STR",
            "url": "https://www.barodaetrade.com/research-Details/STR",
            "category": "Reports",
            "publisher": "Baroda eTrade",
            "region": "Indian",
        }
        article = _make_article(
            "Sample",
            "https://example.com/sample.pdf",
            None,
            "desc",
            feed_cfg,
        )
        self.assertEqual(article.get("feed_id"), "baroda-etrade-str")


if __name__ == "__main__":
    unittest.main()
