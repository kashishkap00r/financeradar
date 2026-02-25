"""Tests for article processing utilities in articles.py."""

import sys
import os
import unittest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from articles import clean_html, titles_are_similar, group_similar_articles, normalize_title


class TestCleanHtml(unittest.TestCase):
    """Tests for clean_html()."""

    def test_strips_html_tags(self):
        result = clean_html("<p>Hello <b>world</b></p>")
        self.assertEqual(result, "Hello world")

    def test_decodes_html_entities(self):
        result = clean_html("AT&amp;T is &lt;big&gt;")
        self.assertEqual(result, "AT&T is <big>")

    def test_collapses_whitespace(self):
        result = clean_html("  hello   world  ")
        self.assertEqual(result, "hello world")

    def test_empty_string(self):
        self.assertEqual(clean_html(""), "")

    def test_none_input(self):
        self.assertEqual(clean_html(None), "")

    def test_truncates_long_text(self):
        long_text = "A" * 300
        result = clean_html(long_text)
        self.assertTrue(result.endswith("..."))
        self.assertLessEqual(len(result), 254)  # 250 + "..."


class TestTitlesSimilar(unittest.TestCase):
    """Tests for titles_are_similar()."""

    def test_identical_titles(self):
        self.assertTrue(titles_are_similar(
            "RBI cuts repo rate by 25 bps",
            "RBI cuts repo rate by 25 bps",
        ))

    def test_similar_titles_different_sources(self):
        self.assertTrue(titles_are_similar(
            "RBI cuts repo rate by 25 basis points to 6.25%",
            "RBI cuts repo rate by 25 bps to 6.25 percent",
        ))

    def test_dissimilar_titles(self):
        self.assertFalse(titles_are_similar(
            "RBI cuts repo rate by 25 bps",
            "Infosys reports strong Q3 earnings growth",
        ))

    def test_empty_titles(self):
        self.assertFalse(titles_are_similar("", ""))
        self.assertFalse(titles_are_similar("Some title", ""))

    def test_prefix_stripped(self):
        # "BREAKING:" prefix should be removed before comparison
        self.assertTrue(titles_are_similar(
            "BREAKING: Government announces new trade policy",
            "Government announces new trade policy",
        ))


class TestGroupSimilarArticles(unittest.TestCase):
    """Tests for group_similar_articles()."""

    def _make_article(self, title, source, date=None):
        if date is None:
            date = datetime(2026, 2, 23, tzinfo=timezone.utc)
        return {
            "title": title,
            "source": source,
            "source_url": f"https://{source.lower().replace(' ', '')}.com",
            "link": f"https://example.com/{title[:10].replace(' ', '-')}",
            "date": date,
        }

    def test_similar_articles_grouped(self):
        articles = [
            self._make_article("RBI cuts repo rate by 25 basis points", "ET"),
            self._make_article("RBI cuts repo rate by 25 bps to 6.25%", "Mint"),
        ]
        groups = group_similar_articles(articles)
        # Should be grouped into 1 group
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["all_articles"]), 2)

    def test_dissimilar_articles_not_grouped(self):
        articles = [
            self._make_article("RBI cuts repo rate by 25 bps", "ET"),
            self._make_article("Infosys reports strong Q3 earnings", "Mint"),
        ]
        groups = group_similar_articles(articles)
        self.assertEqual(len(groups), 2)

    def test_different_dates_not_grouped(self):
        # Articles from different days should NOT be grouped even if similar
        articles = [
            self._make_article(
                "RBI cuts repo rate by 25 bps", "ET",
                datetime(2026, 2, 23, tzinfo=timezone.utc),
            ),
            self._make_article(
                "RBI cuts repo rate by 25 bps", "Mint",
                datetime(2026, 2, 24, tzinfo=timezone.utc),
            ),
        ]
        groups = group_similar_articles(articles)
        self.assertEqual(len(groups), 2)

    def test_empty_list(self):
        groups = group_similar_articles([])
        self.assertEqual(groups, [])


if __name__ == "__main__":
    unittest.main()
