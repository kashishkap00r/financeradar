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
    is_listing_page_title,
)


class TestGoogleRssHelpers(unittest.TestCase):
    """Validate title/link normalization for Google RSS feeds."""

    def test_normalize_google_source_suffix_wsj(self):
        self.assertEqual(
            _normalize_google_source_suffix("A big business move - WSJ", "WSJ"),
            "A big business move",
        )

    def test_normalize_google_source_suffix_fred(self):
        # The FRED Blog moved under fred.stlouisfed.org; Google suffixes the bank's name
        self.assertEqual(
            _normalize_google_source_suffix(
                "Updates to MSA maps in FRED - Federal Reserve Bank of St. Louis", "FRED"
            ),
            "Updates to MSA maps in FRED",
        )
        self.assertEqual(
            _normalize_google_source_suffix("Four possible reasons for being unemployed - FRED Blog", "FRED"),
            "Four possible reasons for being unemployed",
        )

    def test_normalize_google_source_suffix_domain(self):
        self.assertEqual(
            _normalize_google_source_suffix(
                "The electro-fortification of Britain - ember-energy.org",
                "Ember",
                "https://ember-energy.org/",
            ),
            "The electro-fortification of Britain",
        )

    def test_normalize_google_source_suffix_economist(self):
        self.assertEqual(
            _normalize_google_source_suffix("Global markets cool off - The Economist", "The Economist"),
            "Global markets cool off",
        )

    def test_normalize_google_source_suffix_full_site_title(self):
        self.assertEqual(
            _normalize_google_source_suffix(
                "What Is Space Superiority? - CSIS | Center for Strategic and International Studies",
                "CSIS",
            ),
            "What Is Space Superiority?",
        )

    def test_normalize_google_source_suffix_keeps_pipe_in_headline(self):
        # A pipe that isn't right after the publisher suffix is part of the headline.
        self.assertEqual(
            _normalize_google_source_suffix("States Weekly | Sept 30 - CSIS", "CSIS"),
            "States Weekly | Sept 30",
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

    def test_listing_page_titles(self):
        # Google's site: search also indexes The Morning Context's tag/company pages
        self.assertTrue(is_listing_page_title(
            "Tag | westside%20stores | The Morning Context | Business And Tech In India"))
        self.assertTrue(is_listing_page_title("Company | The Morning Context | Business And Tech In India"))
        self.assertTrue(is_listing_page_title("Category | Business"))
        self.assertFalse(is_listing_page_title("Westside wants to be the next Zudio. Can it?"))
        self.assertFalse(is_listing_page_title("Tagore's India and the market"))
        self.assertFalse(is_listing_page_title(""))

    def test_post_process_drops_listing_pages(self):
        articles = [
            {"title": "Tag | scale%20ai | The Morning Context | Business And Tech In India - The Morning Context",
             "link": "https://news.google.com/rss/articles/TAG", "description": "", "guid": ""},
            {"title": "Pixxel’s patriotism test - The Morning Context",
             "link": "https://news.google.com/rss/articles/REAL", "description": "", "guid": ""},
        ]
        _post_process_google_rss_articles(
            articles, {"publisher": "The Morning Context", "url": "https://themorningcontext.com"}
        )
        self.assertEqual([a["title"] for a in articles], ["Pixxel’s patriotism test"])


if __name__ == "__main__":
    unittest.main()
