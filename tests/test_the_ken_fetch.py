"""Unit tests for The Ken fallback extraction helpers."""

import unittest

from feeds import (
    _dedupe_articles,
    _extract_the_ken_html_articles,
    _normalize_the_ken_title,
)


class TestTheKenHelpers(unittest.TestCase):
    """Validate The Ken parsing helpers independent of network calls."""

    def _feed_cfg(self):
        return {
            "id": "the-ken",
            "name": "The Ken",
            "url": "https://the-ken.com",
            "feed": "https://the-ken.com/feed/",
            "category": "News",
            "publisher": "The Ken",
        }

    def test_normalize_title_suffix(self):
        self.assertEqual(
            _normalize_the_ken_title("The power of co-investment - The Ken"),
            "The power of co-investment",
        )
        self.assertEqual(
            _normalize_the_ken_title("The dark side of AI"),
            "The dark side of AI",
        )

    def test_extracts_story_from_jsonld(self):
        html = """
        <html><body>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "itemListElement": [
            {
              "@type": "ListItem",
              "url": "https://the-ken.com/story/power-of-co-investment/",
              "name": "The power of co-investment",
              "datePublished": "2026-02-26T08:00:00+0000",
              "description": "Private equity themes"
            },
            {
              "@type": "ListItem",
              "url": "https://the-ken.com/about/",
              "name": "About"
            }
          ]
        }
        </script>
        </body></html>
        """
        articles = _extract_the_ken_html_articles(html.encode("utf-8"), self._feed_cfg())
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "The power of co-investment")
        self.assertEqual(articles[0]["link"], "https://the-ken.com/story/power-of-co-investment/")
        self.assertIsNotNone(articles[0]["date"])

    def test_extracts_story_from_article_card(self):
        html = """
        <html><body>
          <article>
            <a href="/story/dark-side-ai/">
              <h2>The dark side of AI: prompt injection attacks</h2>
            </a>
            <time datetime="2026-02-25T07:00:00+0000">25 Feb 2026</time>
            <p>Active equities</p>
          </article>
        </body></html>
        """
        articles = _extract_the_ken_html_articles(html.encode("utf-8"), self._feed_cfg())
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "The dark side of AI: prompt injection attacks")
        self.assertEqual(articles[0]["link"], "https://the-ken.com/story/dark-side-ai/")
        self.assertIsNotNone(articles[0]["date"])

    def test_dedupe_articles_uses_normalized_link(self):
        articles = [
            {"title": "A", "link": "https://the-ken.com/story/a/"},
            {"title": "A copy", "link": "https://the-ken.com/story/a"},
            {"title": "B - The Ken", "link": "https://the-ken.com/story/b/"},
        ]
        deduped = _dedupe_articles(articles)
        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[1]["title"], "B")


if __name__ == "__main__":
    unittest.main()
