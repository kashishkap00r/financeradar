"""Tests for paper_fetcher.py."""

import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from articles import IST_TZ
from paper_fetcher import load_papers_cache, parse_paper_html, save_papers_cache


SAMPLE_HTML = """
<div class="paper-list" id="paper-list">
  <article class="paper" data-source="RBI" data-title="Working Paper" data-url="https://example.com/paper-a">
    <div class="paper-header">
      <a href="https://example.com/paper-a" class="paper-title">Working Paper</a>
    </div>
    <div class="paper-authors">Alice Author, Bob Author</div>
    <div class="paper-meta">
      <span class="tag tag-source">RBI</span>
      <span>2026-02-20</span>
    </div>
    <div class="paper-summary">A concise summary.</div>
  </article>
  <article class="paper" data-source="NIPFP" data-title="No Date Paper" data-url="https://example.com/paper-b">
    <div class="paper-header">
      <a href="https://example.com/paper-b" class="paper-title">No Date Paper</a>
    </div>
    <div class="paper-meta">
      <span class="tag tag-source">NIPFP</span>
    </div>
  </article>
</div>
"""


class TestPaperFetcher(unittest.TestCase):
    def test_parse_paper_html_extracts_expected_fields(self):
        fetched_at = datetime(2026, 2, 27, 8, 0, tzinfo=IST_TZ)
        papers = parse_paper_html(SAMPLE_HTML, fetched_at=fetched_at)
        self.assertEqual(len(papers), 2)

        first = next(p for p in papers if p["title"] == "Working Paper")
        self.assertEqual(first["link"], "https://example.com/paper-a")
        self.assertEqual(first["source"], "RBI")
        self.assertEqual(first["authors"], "Alice Author, Bob Author")
        self.assertEqual(first["description"], "A concise summary.")
        self.assertFalse(first["date_is_fallback"])
        self.assertEqual(first["date"].date().isoformat(), "2026-02-20")

    def test_parse_paper_html_falls_back_to_fetch_time_when_date_missing(self):
        fetched_at = datetime(2026, 2, 27, 8, 0, tzinfo=IST_TZ)
        papers = parse_paper_html(SAMPLE_HTML, fetched_at=fetched_at)
        second = next(p for p in papers if p["title"] == "No Date Paper")
        self.assertTrue(second["date_is_fallback"])
        self.assertEqual(second["date"], fetched_at)

    def test_cache_round_trip(self):
        fetched_at = datetime(2026, 2, 27, 8, 0, tzinfo=IST_TZ)
        papers = parse_paper_html(SAMPLE_HTML, fetched_at=fetched_at)

        with tempfile.TemporaryDirectory() as tmp:
            cache_file = os.path.join(tmp, "papers_cache.json")
            generated_at = save_papers_cache(cache_file, papers)
            cached_papers, cached_generated_at = load_papers_cache(cache_file)

        self.assertTrue(generated_at)
        self.assertEqual(cached_generated_at, generated_at)
        self.assertEqual(len(cached_papers), len(papers))
        self.assertIsNotNone(cached_papers[0].get("date"))


if __name__ == "__main__":
    unittest.main()
