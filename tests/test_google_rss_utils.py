"""Unit tests for Google RSS helper behavior."""

import os
import sys
import base64
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from feeds import (
    _normalize_google_source_suffix,
    _extract_google_article_token,
    _decode_google_article_token,
    _best_effort_resolve_google_link,
    _post_process_google_rss_articles,
)


class TestGoogleRssHelpers(unittest.TestCase):
    """Validate title/link normalization for Google RSS feeds."""

    def test_normalize_google_source_suffix_wsj(self):
        self.assertEqual(
            _normalize_google_source_suffix("A big business move - WSJ", "WSJ"),
            "A big business move",
        )

    def test_normalize_google_source_suffix_economist(self):
        self.assertEqual(
            _normalize_google_source_suffix("Global markets cool off - The Economist", "The Economist"),
            "Global markets cool off",
        )

    def test_extract_google_article_token(self):
        link = "https://news.google.com/rss/articles/CBMiABCdef_123?oc=5&hl=en-IN"
        self.assertEqual(_extract_google_article_token(link), "CBMiABCdef_123")

    def test_decode_google_article_token_best_effort(self):
        payload = b"\x08meta https://www.wsj.com/economy/story-123?a=1 \x1f extra"
        token = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        self.assertEqual(
            _decode_google_article_token(token),
            "https://www.wsj.com/economy/story-123?a=1",
        )

    def test_resolve_google_link_from_query_param(self):
        link = "https://news.google.com/rss/articles/ABC?q=https%3A%2F%2Fwww.wsj.com%2Fworld%2Findia%2Fstory"
        self.assertEqual(
            _best_effort_resolve_google_link(link),
            "https://www.wsj.com/world/india/story",
        )

    def test_resolve_google_link_from_description_anchor(self):
        link = "https://news.google.com/rss/articles/ABC?oc=5"
        desc = '<a href="https://www.economist.com/business/2026/02/26/example-story">Business - The Economist</a>'
        self.assertEqual(
            _best_effort_resolve_google_link(link, description=desc),
            "https://www.economist.com/business/2026/02/26/example-story",
        )

    def test_post_process_google_rss_articles(self):
        articles = [{
            "title": "India Seizes Tankers - WSJ",
            "link": "https://news.google.com/rss/articles/ABC?q=https%3A%2F%2Fwww.wsj.com%2Fworld%2Findia%2Fstory",
            "description": "",
            "guid": "",
        }]
        stats = _post_process_google_rss_articles(
            articles,
            {"publisher": "WSJ", "feed": "https://news.google.com/rss/search?q=site:wsj.com/world/india"},
        )
        self.assertEqual(articles[0]["title"], "India Seizes Tankers")
        self.assertEqual(articles[0]["link"], "https://www.wsj.com/world/india/story")
        self.assertEqual(stats, {"attempted": 1, "resolved": 1})


if __name__ == "__main__":
    unittest.main()
