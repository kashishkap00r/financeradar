"""Unit tests for State Street insights report fetcher."""

import json
import unittest
from datetime import datetime
from unittest.mock import patch

from reports_fetcher import fetch_ssga_insights


class TestSsgaInsightsFetcher(unittest.TestCase):
    """Validate SSGA insights API parsing and mapping."""

    def setUp(self):
        self.feed_cfg = {
            "id": "ssga-insights",
            "name": "State Street — Insights",
            "url": "https://www.ssga.com/us/en/intermediary/insights",
            "feed": "ssga:insights",
            "category": "Reports",
            "region": "International",
            "publisher": "State Street",
        }
        self.today = datetime.now().strftime("%B %d, %Y")

    @patch("reports_fetcher._fetch_url")
    def test_parses_ssga_results_and_normalizes_fields(self, mock_fetch_url):
        payload = {
            "status": "success",
            "results": [
                {
                    "k": "State Street outlook for rates",
                    "l": "https://www.ssga.com/us/en/intermediary/insights/rates-outlook",
                    "d": "Subheading one",
                    "t": self.today,
                },
                {
                    "k": "Macro trends to watch",
                    "l": "/us/en/intermediary/insights/macro-trends",
                    "d": "Subheading two",
                    "t": self.today,
                },
            ],
        }
        mock_fetch_url.return_value = json.dumps(payload).encode("utf-8")

        articles = fetch_ssga_insights(self.feed_cfg)

        self.assertEqual(len(articles), 2)
        first = articles[0]
        self.assertEqual(first["title"], "State Street outlook for rates")
        self.assertEqual(first["link"], "https://www.ssga.com/us/en/intermediary/insights/rates-outlook")
        self.assertEqual(first["description"], "Subheading one")
        self.assertEqual(first["region"], "International")
        self.assertEqual(first["publisher"], "State Street")
        self.assertEqual(first["feed_id"], "ssga-insights")
        self.assertIsNotNone(first["date"])
        self.assertIsNotNone(first["date"].tzinfo)

        second = articles[1]
        self.assertEqual(second["link"], "https://www.ssga.com/us/en/intermediary/insights/macro-trends")

    @patch("reports_fetcher._fetch_url")
    def test_dedupes_by_normalized_url_and_skips_invalid_rows(self, mock_fetch_url):
        payload = {
            "status": "success",
            "results": [
                {
                    "k": "Duplicate A",
                    "l": "https://www.ssga.com/us/en/intermediary/insights/dup",
                    "d": "One",
                    "t": self.today,
                },
                {
                    "k": "Duplicate B",
                    "l": "https://www.ssga.com/us/en/intermediary/insights/dup/",
                    "d": "Two",
                    "t": self.today,
                },
                {"k": "", "l": "https://www.ssga.com/us/en/intermediary/insights/invalid", "d": "", "t": self.today},
                {"k": "No link", "l": "", "d": "", "t": self.today},
            ],
        }
        mock_fetch_url.return_value = json.dumps(payload).encode("utf-8")

        articles = fetch_ssga_insights(self.feed_cfg)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "Duplicate A")

    @patch("reports_fetcher._fetch_url")
    def test_invalid_json_returns_empty_list(self, mock_fetch_url):
        mock_fetch_url.return_value = b"not-json"

        articles = fetch_ssga_insights(self.feed_cfg)

        self.assertEqual(articles, [])


if __name__ == "__main__":
    unittest.main()
