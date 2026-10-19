"""Tests for AI ranker utility functions."""

import sys
import os
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_ranker import (
    parse_json_response,
    sanitize_headline,
    build_candidates_from_snapshot,
    build_candidates_for_source,
    enforce_source_coverage_and_size,
    enforce_bucket_size,
    resolve_cluster_indices,
    cluster_ranked_items,
    build_clustering_prompt,
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
                {"title": "Tweet stale", "url": "https://x/2", "publisher": "X", "published_at": (now - timedelta(hours=97)).isoformat()},
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

    def test_build_candidates_for_source_only_returns_requested_source(self):
        now = datetime(2026, 2, 26, 18, 0, tzinfo=timezone.utc)
        snapshot = {
            "news": [
                {"title": "News recent", "url": "https://a/1", "publisher": "A", "published_at": (now - timedelta(hours=2)).isoformat()},
                {"title": "News stale", "url": "https://a/2", "publisher": "A", "published_at": (now - timedelta(days=3)).isoformat()},
            ],
            "twitter": [
                {"title": "Tweet recent", "url": "https://x/1", "publisher": "X", "published_at": (now - timedelta(hours=1)).isoformat()},
            ],
        }
        news = build_candidates_for_source(snapshot, source_type="news", now=now, max_articles=20)
        self.assertEqual([item["title"] for item in news], ["News recent"])
        self.assertTrue(all(item["source_type"] == "news" for item in news))


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

    def test_enforce_bucket_size_keeps_single_source_and_fills(self):
        candidates = [
            {"title": "News A", "url": "https://n/1", "source": "N", "source_type": "news"},
            {"title": "News B", "url": "https://n/2", "source": "N", "source_type": "news"},
            {"title": "News C", "url": "https://n/3", "source": "N", "source_type": "news"},
        ]
        rankings = [
            {"rank": 1, "title": "News A", "url": "https://n/1", "source": "N", "source_type": "news"},
            {"rank": 2, "title": "Tweet Z", "url": "https://x/1", "source": "X", "source_type": "twitter"},
        ]
        final = enforce_bucket_size(rankings, candidates, source_type="news", target_count=3)
        self.assertEqual(len(final), 3)
        self.assertTrue(all(item["source_type"] == "news" for item in final))
        self.assertEqual([item["rank"] for item in final], [1, 2, 3])
        self.assertEqual({item["title"] for item in final}, {"News A", "News B", "News C"})


class _FakeHttpResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload.encode("utf-8")


class TestClusterResolution(unittest.TestCase):
    """Tests for cross-bucket story clustering."""

    def _make_items(self):
        return [
            {"title": "Iran strikes push crude past $95", "url": "https://et.com/1", "source": "ET", "source_type": "news", "why_it_matters": "Oil shock", "signal_type": "supply-chain"},
            {"title": "Shipping costs triple on Hormuz", "url": "https://ft.com/1", "source": "FT", "source_type": "news"},
            {"title": "CLSA: India crude exposure", "url": "https://t.me/1", "source": "CLSA", "source_type": "telegram"},
            {"title": "RBI holds rates steady", "url": "https://rbi.com/1", "source": "Mint", "source_type": "news"},
            {"title": "The Real Cost of Hormuz", "url": "https://yt.com/1", "source": "Rachana", "source_type": "youtube"},
        ]

    def test_valid_cluster_resolved(self):
        items = self._make_items()
        raw = [{
            "story_id": "iran-oil-tensions",
            "story_label": "Iran-Oil Tensions Roil Indian Energy",
            "lead_index": 1,
            "related": [
                {"index": 2, "angle": "insurance impact"},
                {"index": 3, "angle": "institutional analysis"},
                {"index": 5, "angle": "explainer video"},
            ]
        }]
        clusters = resolve_cluster_indices(raw, items)
        self.assertEqual(len(clusters), 1)
        c = clusters[0]
        self.assertEqual(c["story_id"], "iran-oil-tensions")
        self.assertEqual(c["lead"]["source"], "ET")
        self.assertEqual(c["lead"]["source_type"], "news")
        self.assertEqual(len(c["related"]), 3)
        source_types = {r["source_type"] for r in c["related"]}
        self.assertEqual(source_types, {"news", "telegram", "youtube"})

    def test_out_of_range_index_drops_cluster(self):
        items = self._make_items()
        raw = [{"story_id": "bad", "story_label": "Bad", "lead_index": 99, "related": [{"index": 1, "angle": "x"}]}]
        clusters = resolve_cluster_indices(raw, items)
        self.assertEqual(len(clusters), 0)

    def test_invalid_related_index_skipped(self):
        items = self._make_items()
        raw = [{
            "story_id": "partial",
            "story_label": "Partial",
            "lead_index": 1,
            "related": [
                {"index": 2, "angle": "ok"},
                {"index": 999, "angle": "bad"},
            ]
        }]
        clusters = resolve_cluster_indices(raw, items)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]["related"]), 1)

    def test_self_referencing_related_skipped(self):
        items = self._make_items()
        raw = [{
            "story_id": "self-ref",
            "story_label": "Self Ref",
            "lead_index": 1,
            "related": [
                {"index": 1, "angle": "self"},
                {"index": 2, "angle": "ok"},
            ]
        }]
        clusters = resolve_cluster_indices(raw, items)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]["related"]), 1)

    def test_empty_raw_returns_empty(self):
        items = self._make_items()
        self.assertEqual(resolve_cluster_indices([], items), [])

    def test_malformed_cluster_skipped(self):
        items = self._make_items()
        raw = ["not a dict", None, 42]
        self.assertEqual(resolve_cluster_indices(raw, items), [])

    def test_single_related_item_is_valid(self):
        """A cluster with lead + 1 related (2 total) is valid."""
        items = self._make_items()
        raw = [{"story_id": "min", "story_label": "Min", "lead_index": 4, "related": [{"index": 1, "angle": "related"}]}]
        clusters = resolve_cluster_indices(raw, items)
        self.assertEqual(len(clusters), 1)

    def test_story_summary_passed_through(self):
        """The one-line summary shown under each Big Story label survives resolution."""
        items = self._make_items()
        raw = [{
            "story_id": "iran-oil",
            "story_label": "Iran strikes push crude past $95",
            "story_summary": "  Crude jumped after the strikes; India pays more for every barrel.  ",
            "articles": [{"index": 1, "angle": "price move"}, {"index": 2, "angle": "shipping costs"}],
        }]
        clusters = resolve_cluster_indices(raw, items)
        self.assertEqual(clusters[0]["story_summary"], "Crude jumped after the strikes; India pays more for every barrel.")

    def test_story_summary_missing_is_empty(self):
        items = self._make_items()
        raw = [{"story_id": "x", "story_label": "X", "articles": [{"index": 1, "angle": "a"}, {"index": 2, "angle": "b"}]}]
        self.assertEqual(resolve_cluster_indices(raw, items)[0]["story_summary"], "")

    def test_story_summary_capped(self):
        items = self._make_items()
        raw = [{"story_id": "x", "story_label": "X", "story_summary": "word " * 100,
                "articles": [{"index": 1, "angle": "a"}, {"index": 2, "angle": "b"}]}]
        self.assertLessEqual(len(resolve_cluster_indices(raw, items)[0]["story_summary"]), 240)

    def test_lead_why_comes_from_the_lead_article(self):
        """The lead's why_it_matters must describe the lead itself, not the first candidate overall."""
        items = self._make_items()
        # Lead is item 4 (RBI, no why_it_matters); item 1 ("Oil shock") is only a related article.
        raw = [{"story_id": "rbi", "story_label": "RBI holds", "lead_index": 4, "related": [{"index": 3, "angle": "a"}]}]
        lead = resolve_cluster_indices(raw, items)[0]["lead"]
        self.assertEqual(lead["source"], "Mint")
        self.assertEqual(lead["why_it_matters"], "")
        self.assertEqual(lead["signal_type"], "")

    def test_lead_why_kept_when_lead_has_one(self):
        items = self._make_items()
        raw = [{"story_id": "oil", "story_label": "Oil", "lead_index": 1, "related": [{"index": 2, "angle": "a"}]}]
        lead = resolve_cluster_indices(raw, items)[0]["lead"]
        self.assertEqual(lead["why_it_matters"], "Oil shock")
        self.assertEqual(lead["signal_type"], "supply-chain")

    def test_clustering_prompt_asks_for_summary_and_sentence_case(self):
        prompt = build_clustering_prompt(self._make_items())
        self.assertIn("story_summary", prompt)
        self.assertIn("sentence case", prompt.lower())

    def test_cluster_ranked_items_returns_empty_on_failure(self):
        """cluster_ranked_items returns [] if API call fails."""
        items = self._make_items()
        model_config = {"name": "Test", "chain": ["test-model"]}
        with patch("ai_ranker.generate_json", side_effect=RuntimeError("API down")):
            result = cluster_ranked_items(items, model_config)
        self.assertEqual(result, [])

    def test_cluster_ranked_items_returns_empty_for_tiny_input(self):
        """Fewer than 2 items → no clustering attempted."""
        result = cluster_ranked_items([{"title": "Solo"}], {"name": "x", "chain": ["x"]})
        self.assertEqual(result, [])



class EntertainmentFilterTest(unittest.TestCase):
    def test_flags_entertainment_but_not_policy_usage(self):
        from ai_ranker import is_entertainment
        self.assertTrue(is_entertainment("Shots Fired At Actor Tiger Shroff"))
        self.assertTrue(is_entertainment("Bollywood box office collection day 3"))
        self.assertFalse(is_entertainment("Iran a state actor in Hormuz attacks"))
        self.assertFalse(is_entertainment("US called a bad actor on trade"))
        self.assertFalse(is_entertainment("RBI holds repo rate at 5.5%"))

    def test_drops_cluster_whose_summary_is_entertainment(self):
        from ai_ranker import filter_entertainment_clusters
        clusters = [
            {"story_label": "Bishnoi gang claims attack on Tiger Shroff",
             "story_summary": "Gunfire targeted actor Tiger Shroff's vehicle in Mumbai.",
             "lead": {"title": "Tiger Shroff firing: CM vows action"},
             "related": [{"title": "Police widen probe"}]},
            {"story_label": "Fairfax gets nod for IDBI Bank stake",
             "story_summary": "Cabinet cleared the ₹52,878 crore deal.",
             "lead": {"title": "Cabinet clears IDBI sale"},
             "related": [{"title": "IDBI shares jump"}]},
        ]
        kept = filter_entertainment_clusters(clusters)
        self.assertEqual([c["story_label"] for c in kept], ["Fairfax gets nod for IDBI Bank stake"])

    def test_drops_cluster_when_half_the_articles_are_entertainment(self):
        from ai_ranker import filter_entertainment_clusters
        cluster = {"story_label": "Mumbai shooting", "story_summary": "",
                   "lead": {"title": "Shooting in Juhu"},
                   "related": [{"title": "Actor safe after shots fired"}]}
        self.assertEqual(filter_entertainment_clusters([cluster]), [])

if __name__ == "__main__":
    unittest.main()
