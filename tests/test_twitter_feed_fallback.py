"""Unit tests for Twitter feed fetch behavior without Nitter fallback."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import feeds


class TwitterFeedFetchTests(unittest.TestCase):
    def _feed_cfg(self):
        return {
            "id": "x-javier-blas",
            "name": "Javier Blas (X)",
            "url": "https://x.com/JavierBlas",
            "feed": "https://news.google.com/rss/search?q=site:x.com/JavierBlas/status&hl=en-IN&gl=IN&ceid=IN:en",
            "category": "Twitter",
            "publisher": "Javier Blas",
        }

    def _article(self, title, link, dt):
        return {
            "title": title,
            "link": link,
            "date": dt,
            "description": "",
            "source": "Javier Blas (X)",
            "source_url": "https://x.com/JavierBlas",
            "category": "Twitter",
            "publisher": "Javier Blas",
            "feed_id": "x-javier-blas",
        }

    def test_extract_x_handle_from_profile_url(self):
        self.assertEqual(feeds._extract_x_handle(self._feed_cfg()), "JavierBlas")

    def test_fetch_feed_calls_single_source_when_google_empty(self):
        with patch.object(feeds, "_fetch_url_bytes", return_value=b"<xml/>") as fetch_mock, \
             patch.object(feeds, "_parse_feed_content", return_value=[]) as parse_mock, \
             patch.object(feeds, "_post_process_google_rss_articles", return_value={"attempted": 0, "resolved": 0}):
            items = feeds.fetch_feed(self._feed_cfg())

        self.assertEqual(fetch_mock.call_count, 1)
        self.assertEqual(parse_mock.call_count, 1)
        self.assertEqual(items, [])

    def test_fetch_feed_keeps_stale_google_results_without_secondary_fetch(self):
        stale_google = self._article(
            "Older tweet - x.com",
            "https://news.google.com/rss/articles/old-token",
            datetime.now(timezone.utc) - timedelta(hours=20),
        )
        with patch.object(feeds, "_fetch_url_bytes", return_value=b"<xml/>") as fetch_mock, \
             patch.object(feeds, "_parse_feed_content", return_value=[stale_google]), \
             patch.object(feeds, "_post_process_google_rss_articles", return_value={"attempted": 0, "resolved": 0}):
            items = feeds.fetch_feed(self._feed_cfg())

        self.assertEqual(fetch_mock.call_count, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Older tweet - x.com")

    def test_fetch_feed_keeps_fresh_google_results(self):
        fresh_google = self._article(
            "Recent tweet - x.com",
            "https://news.google.com/rss/articles/fresh-token",
            datetime.now(timezone.utc) - timedelta(hours=1),
        )
        with patch.object(feeds, "_fetch_url_bytes", return_value=b"<xml/>") as fetch_mock, \
             patch.object(feeds, "_parse_feed_content", return_value=[fresh_google]), \
             patch.object(feeds, "_post_process_google_rss_articles", return_value={"attempted": 0, "resolved": 0}):
            items = feeds.fetch_feed(self._feed_cfg())

        self.assertEqual(fetch_mock.call_count, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Recent tweet - x.com")


if __name__ == "__main__":
    unittest.main()
