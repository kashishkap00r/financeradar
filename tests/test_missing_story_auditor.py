"""Unit tests for missing_story_auditor status classification."""

import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from missing_story_auditor import classify_story_status, make_blocked_finding


class TestMissingStoryAuditor(unittest.TestCase):
    def test_classify_resolved_within_sla(self):
        now = datetime(2026, 2, 26, 18, 0, tzinfo=timezone.utc)
        source_item = {
            "tab": "news",
            "source_id": "feed-a",
            "source_name": "Feed A",
            "title": "Story A",
            "url": "https://example.com/a",
            "source_seen_at": "2026-02-26T10:00:00+00:00",
        }
        published = [
            {
                "tab": "news",
                "source_id": "feed-a",
                "title": "Story A",
                "url": "https://example.com/a",
                "published_at": "2026-02-26T12:00:00+00:00",
            }
        ]
        finding = classify_story_status(source_item, published, sla_hours=6, now_utc=now)
        self.assertIsNotNone(finding)
        self.assertEqual(finding["status"], "resolved")

    def test_classify_late_when_published_after_sla(self):
        now = datetime(2026, 2, 26, 20, 0, tzinfo=timezone.utc)
        source_item = {
            "tab": "reports",
            "source_id": "rep-a",
            "source_name": "Report A",
            "title": "Coverage note",
            "url": "https://example.com/r",
            "source_seen_at": "2026-02-26T10:00:00+00:00",
        }
        published = [
            {
                "tab": "reports",
                "source_id": "rep-a",
                "title": "Coverage note",
                "url": "https://example.com/r",
                "published_at": "2026-02-26T18:30:00+00:00",
            }
        ]
        finding = classify_story_status(source_item, published, sla_hours=6, now_utc=now)
        self.assertIsNotNone(finding)
        self.assertEqual(finding["status"], "late")
        self.assertEqual(finding["failure_stage"], "render")

    def test_classify_missing_when_unmatched_and_past_sla(self):
        now = datetime(2026, 2, 26, 20, 0, tzinfo=timezone.utc)
        source_item = {
            "tab": "youtube",
            "source_id": "yt-a",
            "source_name": "Channel A",
            "title": "Video A",
            "url": "https://youtube.com/watch?v=abc",
            "source_seen_at": "2026-02-26T10:00:00+00:00",
        }
        finding = classify_story_status(source_item, published_items=[], sla_hours=6, now_utc=now)
        self.assertIsNotNone(finding)
        self.assertEqual(finding["status"], "missing")
        self.assertEqual(finding["failure_stage"], "filter")

    def test_classify_returns_none_when_within_sla_and_unmatched(self):
        now = datetime(2026, 2, 26, 13, 0, tzinfo=timezone.utc)
        source_item = {
            "tab": "twitter",
            "source_id": "tw-a",
            "source_name": "Handle A",
            "title": "Tweet A",
            "url": "https://x.com/a/status/1",
            "source_seen_at": "2026-02-26T10:00:00+00:00",
        }
        finding = classify_story_status(source_item, published_items=[], sla_hours=6, now_utc=now)
        self.assertIsNone(finding)

    def test_make_blocked_finding(self):
        now = datetime(2026, 2, 26, 20, 0, tzinfo=timezone.utc)
        blocked = {
            "tab": "telegram",
            "source_id": "telegram:all",
            "source_name": "Telegram reports file",
            "source_url": "/tmp/telegram_reports.json",
            "error": "file not found",
        }
        finding = make_blocked_finding(blocked, now)
        self.assertEqual(finding["status"], "blocked")
        self.assertEqual(finding["failure_stage"], "fetch")
        self.assertIn("error", finding["evidence"])


if __name__ == "__main__":
    unittest.main()

