"""Unit tests for the CREA (energyandcleanair.org) WordPress fetcher."""

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from reports_fetcher import fetch_crea


def _recent_gmt(days_ago=1):
    """WordPress date_gmt format: naive ISO, always UTC."""
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S")


PUBLICATIONS_CFG = {
    "id": "crea-publications",
    "name": "CREA — Publications",
    "url": "https://energyandcleanair.org/publications/",
    "feed": "crea:publications",
    "category": "Reports",
    "region": "International",
    "publisher": "CREA",
}

NEWS_CFG = {
    "id": "crea-news",
    "name": "CREA",
    "url": "https://energyandcleanair.org/news/",
    "feed": "crea:news",
    "category": "News",
    "publisher": "CREA",
}


class TestCreaPublications(unittest.TestCase):
    """The Reports-side feed, backed by the `publication` custom post type."""

    def test_parses_publications_and_maps_reports_fields(self):
        payload = [
            {
                "date_gmt": _recent_gmt(2),
                "link": "https://energyandcleanair.org/publication/delhi-so2-sources/",
                "title": {"rendered": "Exempted but emitting: Delhi&#8217;s SO2 sources"},
                "excerpt": {"rendered": "<p>Plants operate <b>without</b> control tech.</p>\n"},
            },
        ]
        with patch("reports_fetcher._fetch_url") as mock_fetch:
            mock_fetch.return_value = json.dumps(payload).encode("utf-8")
            articles = fetch_crea(PUBLICATIONS_CFG)

        self.assertEqual(len(articles), 1)
        art = articles[0]
        self.assertEqual(art["title"], "Exempted but emitting: Delhi’s SO2 sources")
        self.assertEqual(art["link"], "https://energyandcleanair.org/publication/delhi-so2-sources/")
        self.assertEqual(art["description"], "Plants operate without control tech.")
        self.assertEqual(art["category"], "Reports")
        self.assertEqual(art["region"], "International")
        self.assertEqual(art["publisher"], "CREA")
        self.assertEqual(art["feed_id"], "crea-publications")
        self.assertIsNotNone(art["date"])
        self.assertEqual(art["date"].tzinfo, timezone.utc)

    def test_requests_publication_endpoint_in_english_only(self):
        with patch("reports_fetcher._fetch_url") as mock_fetch:
            mock_fetch.return_value = b"[]"
            fetch_crea(PUBLICATIONS_CFG)

        requested = mock_fetch.call_args[0][0]
        self.assertIn("/wp/v2/publication", requested)
        # Polylang: without lang=en the endpoint interleaves zh/ua translations.
        self.assertIn("lang=en", requested)

    def test_publications_do_not_fall_back_to_google(self):
        """Reports have reports_cache.json as their safety net; Google News
        does not index the /publication/ post type reliably."""
        with patch("reports_fetcher._fetch_url", side_effect=Exception("boom")), \
                patch("reports_fetcher._fetch_crea_google_fallback") as mock_google:
            articles = fetch_crea(PUBLICATIONS_CFG)

        self.assertEqual(articles, [])
        mock_google.assert_not_called()

    def test_drops_items_missing_title_or_link(self):
        payload = [
            {"date_gmt": _recent_gmt(), "link": "", "title": {"rendered": "No link"}},
            {"date_gmt": _recent_gmt(), "link": "https://x.test/a/", "title": {"rendered": "  "}},
        ]
        with patch("reports_fetcher._fetch_url") as mock_fetch:
            mock_fetch.return_value = json.dumps(payload).encode("utf-8")
            self.assertEqual(fetch_crea(PUBLICATIONS_CFG), [])


class TestCreaNews(unittest.TestCase):
    """The News-side feed, backed by regular posts, with a Google RSS fallback."""

    def test_parses_posts_and_maps_news_category(self):
        payload = [
            {
                "date_gmt": _recent_gmt(1),
                "link": "https://energyandcleanair.org/analysis-india-power-emissions/",
                "title": {"rendered": "Analysis: India&#8217;s power-sector emissions flat"},
                "excerpt": {"rendered": "<p>Clean energy surge.</p>"},
            },
        ]
        with patch("reports_fetcher._fetch_url") as mock_fetch:
            mock_fetch.return_value = json.dumps(payload).encode("utf-8")
            articles = fetch_crea(NEWS_CFG)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["category"], "News")
        self.assertEqual(articles[0]["publisher"], "CREA")
        self.assertEqual(articles[0]["title"], "Analysis: India’s power-sector emissions flat")

    def test_requests_posts_endpoint_in_english_only(self):
        # The fallback must be stubbed too: an empty REST response triggers it,
        # and an unpatched _fetch_url_bytes would hit Google News for real.
        with patch("reports_fetcher._fetch_url") as mock_fetch, \
                patch("reports_fetcher._fetch_crea_google_fallback", return_value=[]):
            mock_fetch.return_value = b"[]"
            fetch_crea(NEWS_CFG)

        requested = mock_fetch.call_args[0][0]
        self.assertIn("/wp/v2/posts", requested)
        self.assertIn("lang=en", requested)

    def test_falls_back_to_google_rss_when_rest_api_errors(self):
        rss = _google_rss_bytes()
        with patch("reports_fetcher._fetch_url", side_effect=Exception("cloudflare 403")), \
                patch("reports_fetcher._fetch_url_bytes", return_value=rss) as mock_bytes:
            articles = fetch_crea(NEWS_CFG)

        self.assertTrue(mock_bytes.called)
        self.assertIn("news.google.com/rss/search", mock_bytes.call_args[0][0])
        self.assertEqual(len(articles), 1)
        # Google appends " - CREA" to every title; it must be stripped.
        self.assertEqual(articles[0]["title"], "China coal permits rebound")
        self.assertEqual(articles[0]["category"], "News")
        self.assertEqual(articles[0]["publisher"], "CREA")

    def test_falls_back_to_google_rss_when_rest_api_returns_nothing(self):
        with patch("reports_fetcher._fetch_url", return_value=b"[]"), \
                patch("reports_fetcher._fetch_url_bytes", return_value=_google_rss_bytes()):
            articles = fetch_crea(NEWS_CFG)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "China coal permits rebound")

    def test_fallback_strips_domain_suffix_google_uses_for_some_items(self):
        """Google labels roughly half of CREA's items by domain, not by name."""
        with patch("reports_fetcher._fetch_url", side_effect=Exception("down")), \
                patch("reports_fetcher._fetch_url_bytes",
                      return_value=_google_rss_bytes(title="Indonesia air quality tracker - energyandcleanair.org")):
            articles = fetch_crea(NEWS_CFG)

        self.assertEqual(articles[0]["title"], "Indonesia air quality tracker")

    def test_returns_empty_when_both_routes_fail(self):
        with patch("reports_fetcher._fetch_url", side_effect=Exception("rest down")), \
                patch("reports_fetcher._fetch_url_bytes", side_effect=Exception("google down")):
            self.assertEqual(fetch_crea(NEWS_CFG), [])


def _google_rss_bytes(title="China coal permits rebound - CREA"):
    pub_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    return f"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>site:energyandcleanair.org - Google News</title>
  <item>
    <title>{title}</title>
    <link>https://energyandcleanair.org/china-coal-permits-rebound/</link>
    <guid>https://energyandcleanair.org/china-coal-permits-rebound/</guid>
    <pubDate>{pub_date}</pubDate>
    <description>Snippet</description>
  </item>
</channel></rss>""".encode("utf-8")


if __name__ == "__main__":
    unittest.main()
