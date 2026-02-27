import unittest

from feeds import DEFAULT_YOUTUBE_BUCKET, _normalize_video_feed_buckets


class VideoFeedBucketTests(unittest.TestCase):
    def test_keeps_valid_bucket(self):
        feeds = [{
            "id": "yt-valid",
            "category": "Videos",
            "youtube_bucket": "Traditional Media",
        }]
        normalized = _normalize_video_feed_buckets(feeds)
        self.assertEqual(normalized[0]["youtube_bucket"], "Traditional Media")

    def test_defaults_missing_and_invalid_buckets(self):
        feeds = [
            {"id": "yt-missing", "category": "Videos"},
            {"id": "yt-invalid", "category": "Videos", "youtube_bucket": "Unknown"},
            {"id": "news", "category": "News"},
        ]
        normalized = _normalize_video_feed_buckets(feeds)
        self.assertEqual(normalized[0]["youtube_bucket"], DEFAULT_YOUTUBE_BUCKET)
        self.assertEqual(normalized[1]["youtube_bucket"], DEFAULT_YOUTUBE_BUCKET)
        self.assertNotIn("youtube_bucket", normalized[2])


if __name__ == "__main__":
    unittest.main()
