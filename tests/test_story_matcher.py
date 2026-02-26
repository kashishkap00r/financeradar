"""Tests for auditor.matcher matching primitives."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from auditor.matcher import canonicalize_url, find_best_match, normalize_title


class TestStoryMatcher(unittest.TestCase):
    def test_canonicalize_url_strips_tracking_and_fragment(self):
        raw = "https://example.com/path/?utm_source=x&b=2&a=1#section"
        canonical = canonicalize_url(raw)
        self.assertEqual(canonical, "https://example.com/path?a=1&b=2")

    def test_normalize_title(self):
        self.assertEqual(normalize_title("  \"Hello, World!\" "), "hello world")

    def test_find_best_match_by_url_same_source(self):
        source_item = {
            "tab": "news",
            "source_id": "feed-1",
            "title": "Sample title",
            "url": "https://example.com/post?utm_source=abc",
        }
        published = [
            {
                "tab": "news",
                "source_id": "feed-1",
                "title": "Another title",
                "url": "https://example.com/post",
            }
        ]
        match = find_best_match(source_item, published)
        self.assertIsNotNone(match)
        self.assertEqual(match["match_type"], "url_exact")
        self.assertFalse(match["cross_source"])

    def test_find_best_match_by_title_cross_source(self):
        source_item = {
            "tab": "reports",
            "source_id": "src-a",
            "title": "Global Inflation Forecast 2026",
            "url": "https://source-a.example/report-1",
        }
        published = [
            {
                "tab": "reports",
                "source_id": "src-b",
                "title": "Global inflation forecast 2026",
                "url": "https://source-b.example/report-xyz",
            }
        ]
        match = find_best_match(source_item, published)
        self.assertIsNotNone(match)
        self.assertEqual(match["match_type"], "title_exact")
        self.assertTrue(match["cross_source"])

    def test_find_best_match_respects_tab_boundary(self):
        source_item = {
            "tab": "youtube",
            "source_id": "yt-a",
            "title": "Macro Outlook",
            "url": "https://youtube.com/watch?v=123",
        }
        published = [
            {
                "tab": "news",
                "source_id": "yt-a",
                "title": "Macro Outlook",
                "url": "https://youtube.com/watch?v=123",
            }
        ]
        self.assertIsNone(find_best_match(source_item, published))


if __name__ == "__main__":
    unittest.main()

