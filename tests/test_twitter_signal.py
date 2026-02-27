import unittest
from datetime import datetime, timedelta

from articles import IST_TZ
from twitter_signal import build_twitter_lanes, canonicalize_tweet_url, extract_tweet_parts


class TwitterSignalTests(unittest.TestCase):
    def test_canonicalize_tweet_url(self):
        url = "https://twitter.com/WSJ/status/123456789/photo/1?ref_src=abc"
        self.assertEqual(
            canonicalize_tweet_url(url),
            "https://x.com/WSJ/status/123456789",
        )

    def test_extract_tweet_parts(self):
        handle, tweet_id = extract_tweet_parts("https://x.com/alpha/status/987654321")
        self.assertEqual(handle, "alpha")
        self.assertEqual(tweet_id, "987654321")

    def test_build_twitter_lanes_excludes_retweets_and_collapses_threads(self):
        now = datetime.now(IST_TZ)
        items = [
            {
                "title": "RT @alpha: Market check-in for today",
                "link": "https://x.com/alpha/status/1",
                "date": now - timedelta(hours=1),
                "source": "Alpha",
                "publisher": "Alpha",
            },
            {
                "title": "Thread: Why PSU bank credit costs are falling in FY26",
                "link": "https://x.com/beta/status/2",
                "date": now - timedelta(hours=2),
                "source": "Beta",
                "publisher": "Beta",
            },
            {
                "title": "Thread: Why PSU bank credit costs are falling in FY26 (part 2)",
                "link": "https://x.com/beta/status/3",
                "date": now - timedelta(hours=2, minutes=10),
                "source": "Beta",
                "publisher": "Beta",
            },
            {
                "title": "Policy note: export logistics and margin impact",
                "link": "https://x.com/gamma/status/4",
                "date": now - timedelta(hours=3),
                "source": "Gamma",
                "publisher": "Gamma",
            },
        ]

        full_stream, high_signal, stats = build_twitter_lanes(
            items,
            now=now,
            target_count=3,
            high_window_hours=24,
        )

        self.assertEqual(stats["ranking_mode"], "fallback")
        self.assertTrue(any(item.get("thread_collapsed_count", 0) > 0 for item in full_stream))
        self.assertTrue(all(not item.get("is_retweet") for item in high_signal))
        self.assertEqual(len(high_signal), 2)


if __name__ == "__main__":
    unittest.main()
