"""Unit tests for optional RSS proxy fallback in fetch_feed."""

import os
import socket
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from unittest.mock import patch

import feeds


class FeedProxyFallbackTests(unittest.TestCase):
    def _news_feed(self):
        return {
            "id": "news-sample",
            "name": "News Sample",
            "url": "https://example.com",
            "feed": "https://example.com/feed.xml",
            "category": "News",
            "publisher": "Example",
        }

    def _video_feed(self):
        return {
            "id": "video-sample",
            "name": "Video Sample",
            "url": "https://youtube.com/@example",
            "feed": "https://www.youtube.com/feeds/videos.xml?channel_id=ABC123",
            "category": "Videos",
            "publisher": "Example",
        }

    def _article(self):
        return [
            {
                "title": "Recovered article",
                "link": "https://example.com/post-1",
                "date": None,
                "description": "",
                "source": "News Sample",
                "source_url": "https://example.com",
                "category": "News",
                "publisher": "Example",
                "feed_id": "news-sample",
            }
        ]

    @patch.dict(os.environ, {"RSS_PROXY_URL": "https://rss-proxy.test/api/fetch-rss"}, clear=False)
    @patch.object(feeds, "_parse_feed_content")
    @patch.object(feeds, "_fetch_url_bytes")
    def test_proxy_recovers_parse_error(self, fetch_mock, parse_mock):
        fetch_mock.side_effect = [b"<bad-xml>", b"<rss></rss>"]
        parse_mock.side_effect = [ET.ParseError("not well-formed"), self._article()]

        items = feeds.fetch_feed(self._news_feed())

        self.assertEqual(len(items), 1)
        self.assertEqual(fetch_mock.call_count, 2)
        second_url = fetch_mock.call_args_list[1].args[0]
        self.assertIn("https://rss-proxy.test/api/fetch-rss?url=", second_url)
        self.assertIn("https%3A%2F%2Fexample.com%2Ffeed.xml", second_url)

    @patch.dict(os.environ, {"RSS_PROXY_URL": "https://rss-proxy.test/api/fetch-rss"}, clear=False)
    @patch.object(feeds, "_parse_feed_content")
    @patch.object(feeds, "_fetch_url_bytes")
    def test_proxy_not_used_for_http_404(self, fetch_mock, parse_mock):
        url = self._news_feed()["feed"]
        fetch_mock.side_effect = urllib.error.HTTPError(url, 404, "Not Found", None, None)

        items = feeds.fetch_feed(self._news_feed())

        self.assertEqual(items, [])
        self.assertEqual(fetch_mock.call_count, 1)
        parse_mock.assert_not_called()

    @patch.dict(os.environ, {"RSS_PROXY_URL": "https://rss-proxy.test/api/fetch-rss"}, clear=False)
    @patch.object(feeds, "_parse_feed_content")
    @patch.object(feeds, "_fetch_url_bytes")
    def test_proxy_not_used_for_videos(self, fetch_mock, parse_mock):
        fetch_mock.return_value = b"<bad-xml>"
        parse_mock.side_effect = ET.ParseError("not well-formed")

        items = feeds.fetch_feed(self._video_feed())

        self.assertEqual(items, [])
        self.assertEqual(fetch_mock.call_count, 1)

    @patch.dict(os.environ, {"RSS_PROXY_URL": ""}, clear=False)
    @patch.object(feeds, "_parse_feed_content")
    @patch.object(feeds, "_fetch_url_bytes")
    def test_proxy_not_used_when_env_unset(self, fetch_mock, parse_mock):
        fetch_mock.return_value = b"<bad-xml>"
        parse_mock.side_effect = ET.ParseError("not well-formed")

        items = feeds.fetch_feed(self._news_feed())

        self.assertEqual(items, [])
        self.assertEqual(fetch_mock.call_count, 1)

    @patch.dict(os.environ, {"RSS_PROXY_URL": "https://rss-proxy.test/api/fetch-rss"}, clear=False)
    @patch.object(feeds, "_parse_feed_content")
    @patch.object(feeds, "_fetch_url_bytes")
    def test_proxy_recovers_url_timeout(self, fetch_mock, parse_mock):
        fetch_mock.side_effect = [
            urllib.error.URLError(socket.timeout("timed out")),
            b"<rss></rss>",
        ]
        parse_mock.return_value = self._article()

        items = feeds.fetch_feed(self._news_feed())

        self.assertEqual(len(items), 1)
        self.assertEqual(fetch_mock.call_count, 2)
        self.assertEqual(parse_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
