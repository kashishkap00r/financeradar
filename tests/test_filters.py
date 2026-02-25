"""Tests for content filtering in filters.py."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from filters import should_filter_article


class TestShouldFilterArticle(unittest.TestCase):
    """Tests for should_filter_article()."""

    def test_filters_quarterly_results(self):
        article = {"title": "Stock XYZ: Q3 Results Today Live", "link": ""}
        self.assertTrue(should_filter_article(article))

    def test_filters_penny_stocks(self):
        article = {"title": "Top 5 penny stocks to buy this week", "link": ""}
        self.assertTrue(should_filter_article(article))

    def test_filters_sensex_movement(self):
        article = {"title": "Sensex surges 500 points amid rally", "link": ""}
        self.assertTrue(should_filter_article(article))

    def test_filters_stock_tips(self):
        article = {"title": "Buy or sell: best intraday tips for today", "link": ""}
        self.assertTrue(should_filter_article(article))

    def test_passes_legitimate_policy_article(self):
        article = {
            "title": "RBI announces new monetary policy framework",
            "link": "https://example.com/rbi-policy",
        }
        self.assertFalse(should_filter_article(article))

    def test_passes_economic_analysis(self):
        article = {
            "title": "India GDP growth slows to 6.1% in Q3 on weak manufacturing",
            "link": "https://example.com/gdp",
        }
        self.assertFalse(should_filter_article(article))

    def test_filters_url_pattern_press_release(self):
        article = {
            "title": "Some company announcement",
            "link": "https://example.com/pr-release/12345",
        }
        self.assertTrue(should_filter_article(article))

    def test_filters_url_pattern_personal_finance(self):
        article = {
            "title": "How to save more money",
            "link": "https://example.com/personal-finance/savings-tips",
        }
        self.assertTrue(should_filter_article(article))

    def test_empty_title_does_not_crash(self):
        article = {"title": "", "link": ""}
        # Should not raise; result can be True or False
        result = should_filter_article(article)
        self.assertIsInstance(result, bool)

    def test_missing_title_key_does_not_crash(self):
        article = {"link": ""}
        result = should_filter_article(article)
        self.assertIsInstance(result, bool)

    def test_missing_link_key_does_not_crash(self):
        article = {"title": "Some title"}
        result = should_filter_article(article)
        self.assertIsInstance(result, bool)


if __name__ == "__main__":
    unittest.main()
