"""Unit tests for Twitter feed source fallback behavior."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import feeds


class TwitterFeedFallbackTests(unittest.TestCase):
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
        self.assertEqual(
            feeds._extract_x_handle(self._feed_cfg()),
            "JavierBlas",
        )

    def test_canonicalize_nitter_tweet_url(self):
        self.assertEqual(
            feeds._canonicalize_nitter_tweet_url(
                "https://nitter.net/JavierBlas/status/2028439174404006243#m"
            ),
            "https://x.com/JavierBlas/status/2028439174404006243",
        )

    def test_fetch_feed_uses_nitter_when_google_empty(self):
        nitter_article = self._article(
            "Fresh update",
            "https://nitter.net/JavierBlas/status/2028439174404006243#m",
            datetime.now(timezone.utc),
        )
        with patch.object(feeds, "NITTER_INSTANCES", ["https://nitter.net"]), \
             patch.object(feeds, "_fetch_url_bytes", side_effect=[b"<xml/>", b"<xml/>"]) as fetch_mock, \
             patch.object(feeds, "_parse_feed_content", side_effect=[[], [nitter_article]]) as parse_mock, \
             patch.object(feeds, "_post_process_google_rss_articles", return_value={"attempted": 0, "resolved": 0}):
            items = feeds.fetch_feed(self._feed_cfg())

        self.assertEqual(fetch_mock.call_count, 2)
        self.assertEqual(parse_mock.call_count, 2)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["link"], "https://x.com/JavierBlas/status/2028439174404006243")

    def test_fetch_feed_uses_nitter_when_google_stale(self):
        stale_google = self._article(
            "Older tweet - x.com",
            "https://news.google.com/rss/articles/old-token",
            datetime.now(timezone.utc) - timedelta(hours=20),
        )
        fresh_nitter = self._article(
            "Fresh tweet",
            "https://nitter.net/JavierBlas/status/2028439174404006243#m",
            datetime.now(timezone.utc),
        )
        with patch.object(feeds, "NITTER_INSTANCES", ["https://nitter.net"]), \
             patch.object(feeds, "_fetch_url_bytes", side_effect=[b"<xml/>", b"<xml/>"]) as fetch_mock, \
             patch.object(feeds, "_parse_feed_content", side_effect=[[stale_google], [fresh_nitter]]), \
             patch.object(feeds, "_post_process_google_rss_articles", return_value={"attempted": 0, "resolved": 0}):
            items = feeds.fetch_feed(self._feed_cfg())

        self.assertEqual(fetch_mock.call_count, 2)
        self.assertEqual(len(items), 2)
        self.assertTrue(any(item["title"] == "Fresh tweet" for item in items))

    def test_fetch_feed_skips_nitter_when_google_is_fresh(self):
        fresh_google = self._article(
            "Recent tweet - x.com",
            "https://news.google.com/rss/articles/fresh-token",
            datetime.now(timezone.utc) - timedelta(hours=1),
        )
        with patch.object(feeds, "NITTER_INSTANCES", ["https://nitter.net"]), \
             patch.object(feeds, "_fetch_url_bytes", return_value=b"<xml/>") as fetch_mock, \
             patch.object(feeds, "_parse_feed_content", return_value=[fresh_google]), \
             patch.object(feeds, "_post_process_google_rss_articles", return_value={"attempted": 0, "resolved": 0}):
            items = feeds.fetch_feed(self._feed_cfg())

        self.assertEqual(fetch_mock.call_count, 1)
        self.assertEqual(len(items), 1)


if __name__ == "__main__":
    unittest.main()
