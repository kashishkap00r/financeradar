"""Tests for Google-only Twitter ingestion orchestration and cleaners."""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import twitter_fetcher


class TwitterFetcherTests(unittest.TestCase):
    def _feed(self):
        return {
            "id": "x-javier-blas",
            "name": "Javier Blas (X)",
            "url": "https://x.com/JavierBlas",
            "feed": "https://news.google.com/rss/search?q=site:x.com/JavierBlas/status&hl=en-IN&gl=IN&ceid=IN:en",
            "category": "Twitter",
            "publisher": "Javier Blas",
        }

    def test_normalize_keeps_retweets_and_drops_replies(self):
        now = datetime.now(timezone.utc)
        raw_items = [
            {
                "title": "RT @alpha: Important callout",
                "link": "https://x.com/alpha/status/123",
                "date": now,
                "tweet_id": "123",
                "is_retweet": True,
                "is_reply": False,
            },
            {
                "title": "@beta Thanks for the thread",
                "link": "https://x.com/alpha/status/124",
                "date": now,
                "tweet_id": "124",
                "is_retweet": False,
                "is_reply": True,
            },
            {
                "title": "Wrapper link should be removed",
                "link": "https://news.google.com/rss/articles/token",
                "date": now,
                "tweet_id": "",
                "is_retweet": False,
                "is_reply": False,
            },
        ]

        cleaned = twitter_fetcher.normalize_and_filter_tweets(
            raw_items, allow_retweets=True, allow_replies=False
        )
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0]["tweet_id"], "123")
        self.assertTrue(cleaned[0]["is_retweet"])

    @patch.object(twitter_fetcher, "save_twitter_snapshot")
    @patch.object(twitter_fetcher, "fetch_twitter_google")
    @patch.object(twitter_fetcher, "load_twitter_snapshot")
    def test_orchestrator_uses_google_when_available(
        self,
        snapshot_mock,
        google_mock,
        save_snapshot_mock,
    ):
        now = datetime.now(timezone.utc)
        snapshot_mock.return_value = {"meta": {}, "items": []}
        google_mock.return_value = (
            [
                {
                    "title": "Fresh tweet",
                    "link": "https://x.com/JavierBlas/status/2020",
                    "date": now,
                    "tweet_id": "2020",
                    "is_retweet": False,
                    "is_reply": False,
                    "category": "Twitter",
                }
            ],
            {"feeds_ok": 1},
        )

        items, meta = twitter_fetcher.fetch_twitter_articles([self._feed()])
        self.assertEqual(meta["source_mode"], "google")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["tweet_id"], "2020")
        google_mock.assert_called_once()
        save_snapshot_mock.assert_called_once()

    @patch.object(twitter_fetcher, "fetch_twitter_google")
    @patch.object(twitter_fetcher, "load_twitter_snapshot")
    def test_orchestrator_uses_snapshot_when_google_empty(
        self,
        snapshot_mock,
        google_mock,
    ):
        now = datetime.now(timezone.utc)
        snapshot_mock.return_value = {
            "meta": {},
            "items": [
                {
                    "title": "Cached tweet",
                    "link": "https://x.com/JavierBlas/status/1010",
                    "date": now.isoformat(),
                    "tweet_id": "1010",
                    "is_retweet": False,
                    "is_reply": False,
                    "category": "Twitter",
                }
            ],
        }
        google_mock.return_value = ([], {"feeds_ok": 0})

        items, meta = twitter_fetcher.fetch_twitter_articles([self._feed()])
        self.assertEqual(meta["source_mode"], "snapshot")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["tweet_id"], "1010")
        self.assertIn("google_empty_using_snapshot", meta["warning"])

    @patch.object(twitter_fetcher, "load_twitter_snapshot")
    def test_orchestrator_uses_snapshot_when_no_handles(self, snapshot_mock):
        now = datetime.now(timezone.utc)
        snapshot_mock.return_value = {
            "meta": {},
            "items": [
                {
                    "title": "Cached tweet",
                    "link": "https://x.com/JavierBlas/status/1111",
                    "date": now.isoformat(),
                    "tweet_id": "1111",
                    "is_retweet": False,
                    "is_reply": False,
                    "category": "Twitter",
                }
            ],
        }

        items, meta = twitter_fetcher.fetch_twitter_articles([])
        self.assertEqual(meta["source_mode"], "snapshot")
        self.assertEqual(items[0]["tweet_id"], "1111")
        self.assertIn("no_twitter_handles_configured", meta["warning"])


if __name__ == "__main__":
    unittest.main()
