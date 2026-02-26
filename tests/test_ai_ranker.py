"""Tests for AI ranker utility functions."""

import sys
import os
import json
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_ranker import (
    parse_json_response,
    sanitize_headline,
    build_candidates_from_snapshot,
    enforce_source_coverage_and_size,
)


class TestParseJsonResponse(unittest.TestCase):
    """Tests for parse_json_response()."""

    def test_valid_json_array(self):
        result = parse_json_response('[{"rank": 1}]')
        self.assertEqual(result, [{"rank": 1}])

    def test_json_in_markdown_code_block(self):
        text = '```json\n[{"rank": 1}]\n```'
        result = parse_json_response(text)
        self.assertEqual(result, [{"rank": 1}])

    def test_json_in_bare_code_block(self):
        text = '```\n[{"rank": 1}]\n```'
        result = parse_json_response(text)
        self.assertEqual(result, [{"rank": 1}])

    def test_trailing_comma_cleaned(self):
        text = '[{"rank": 1},]'
        result = parse_json_response(text)
        self.assertEqual(result, [{"rank": 1}])

    def test_trailing_comma_in_object(self):
        text = '[{"rank": 1, "title": "test",}]'
        result = parse_json_response(text)
        self.assertEqual(result, [{"rank": 1, "title": "test"}])

    def test_prefix_text_before_array(self):
        text = 'Here are the rankings:\n[{"rank": 1}]'
        result = parse_json_response(text)
        self.assertEqual(result, [{"rank": 1}])

    def test_empty_string_raises(self):
        with self.assertRaises((json.JSONDecodeError, ValueError)):
            parse_json_response("")

    def test_no_json_raises(self):
        with self.assertRaises((json.JSONDecodeError, ValueError)):
            parse_json_response("no json here at all")


class TestSanitizeHeadline(unittest.TestCase):
    """Tests for sanitize_headline()."""

    def test_double_quotes_replaced(self):
        result = sanitize_headline('He said "hello" to them')
        self.assertNotIn('"', result)
        self.assertIn("'", result)

    def test_newlines_replaced(self):
        result = sanitize_headline("Line one\nLine two\rLine three")
        self.assertNotIn("\n", result)
        self.assertNotIn("\r", result)

    def test_whitespace_stripped(self):
        result = sanitize_headline("  hello world  ")
        self.assertEqual(result, "hello world")

    def test_empty_string(self):
        result = sanitize_headline("")
        self.assertEqual(result, "")


class TestCandidateLoading(unittest.TestCase):
    """Tests for snapshot candidate loading and source windows."""

    def test_build_candidates_from_snapshot_respects_hybrid_windows(self):
        now = datetime(2026, 2, 26, 18, 0, tzinfo=timezone.utc)
        snapshot = {
            "news": [
                {"title": "News recent", "url": "https://a/1", "publisher": "A", "published_at": (now - timedelta(hours=2)).isoformat()},
                {"title": "News stale", "url": "https://a/2", "publisher": "A", "published_at": (now - timedelta(days=3)).isoformat()},
            ],
            "twitter": [
                {"title": "Tweet recent", "url": "https://x/1", "publisher": "X", "published_at": (now - timedelta(hours=47)).isoformat()},
                {"title": "Tweet stale", "url": "https://x/2", "publisher": "X", "published_at": (now - timedelta(hours=49)).isoformat()},
            ],
            "telegram": [
                {"title": "Telegram no date", "url": "https://t/1", "publisher": "TG"},
            ],
            "reports": [
                {"title": "Report recent", "url": "https://r/1", "publisher": "R", "published_at": (now - timedelta(days=6)).isoformat()},
                {"title": "Report stale", "url": "https://r/2", "publisher": "R", "published_at": (now - timedelta(days=8)).isoformat()},
            ],
            "youtube": [
                {"title": "Video recent", "url": "https://y/1", "publisher": "Y", "published_at": (now - timedelta(days=1)).isoformat()},
            ],
        }

        candidates = build_candidates_from_snapshot(snapshot, now=now, max_articles=50)
        titles = {c["title"] for c in candidates}
        self.assertIn("News recent", titles)
        self.assertIn("Tweet recent", titles)
        self.assertIn("Telegram no date", titles)
        self.assertIn("Report recent", titles)
        self.assertIn("Video recent", titles)
        self.assertNotIn("News stale", titles)
        self.assertNotIn("Tweet stale", titles)
        self.assertNotIn("Report stale", titles)


class TestCoverageEnforcement(unittest.TestCase):
    """Tests source-coverage and fill logic."""

    def test_enforces_minimum_one_per_source(self):
        candidates = [
            {"title": "N1", "url": "https://n/1", "source": "N", "source_type": "news"},
            {"title": "T1", "url": "https://x/1", "source": "X", "source_type": "twitter"},
            {"title": "G1", "url": "https://tg/1", "source": "G", "source_type": "telegram"},
            {"title": "R1", "url": "https://r/1", "source": "R", "source_type": "reports"},
            {"title": "Y1", "url": "https://y/1", "source": "Y", "source_type": "youtube"},
        ]
        rankings = [
            {"rank": 1, "title": "N1", "url": "https://n/1", "source": "N", "source_type": "news"},
            {"rank": 2, "title": "N2", "url": "https://n/2", "source": "N", "source_type": "news"},
        ]

        final = enforce_source_coverage_and_size(rankings, candidates, target_count=5)
        source_types = {item["source_type"] for item in final}
        self.assertEqual(len(final), 5)
        self.assertEqual(source_types, {"news", "twitter", "telegram", "reports", "youtube"})
        self.assertEqual([item["rank"] for item in final], [1, 2, 3, 4, 5])

    def test_fills_to_target_count(self):
        candidates = [
            {"title": "N1", "url": "https://n/1", "source": "N", "source_type": "news"},
            {"title": "N2", "url": "https://n/2", "source": "N", "source_type": "news"},
            {"title": "T1", "url": "https://x/1", "source": "X", "source_type": "twitter"},
        ]
        rankings = [
            {"rank": 1, "title": "N1", "url": "https://n/1", "source": "N", "source_type": "news"},
        ]

        final = enforce_source_coverage_and_size(rankings, candidates, target_count=3)
        self.assertEqual(len(final), 3)
        self.assertEqual([item["rank"] for item in final], [1, 2, 3])
        self.assertEqual({item["title"] for item in final}, {"N1", "N2", "T1"})


if __name__ == "__main__":
    unittest.main()
