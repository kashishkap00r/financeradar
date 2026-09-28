"""Unit tests for the Apollo (apollo.com/insights-news) fetcher."""

import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from articles import IST_TZ
from reports_fetcher import fetch_apollo, fetch_apollo_media, get_report_fetcher


def _recent(days_ago=1):
    """Apollo's display format, e.g. 'September 27, 2026'."""
    return (datetime.now(IST_TZ) - timedelta(days=days_ago)).strftime("%B %d, %Y")


INSIGHTS_CFG = {
    "id": "apollo-insights",
    "name": "Apollo — Insights",
    "url": "https://www.apollo.com/insights-news/insights",
    "feed": "apollo:insights",
    "category": "Reports",
    "region": "International",
    "publisher": "Apollo",
}

DAILY_SPARK_CFG = {
    "id": "apollo-daily-spark",
    "name": "Apollo Daily Spark",
    "url": "https://www.apollo.com/insights-news/insights/daily-spark",
    "feed": "apollo:daily-spark",
    "category": "News",
    "publisher": "Apollo",
}


MEDIA_CFG = {
    "id": "apollo-media",
    "name": "Apollo — Podcasts & Videos",
    "url": "https://www.apollo.com/insights-news/insights",
    "feed": "apollo:media",
    "category": "Videos",
    "publisher": "Apollo",
    "youtube_bucket": "Educational/Explainers",
}


def _insight(title, fmt, days_ago=1, path=None, description="Summary.", image=None):
    return {
        "featuredImage": image or f"/content/dam/apolloaem/images/insights/2026/{fmt}.png",
        "title": title,
        "format": f"apollo:format/{fmt}",
        "releaseDate": _recent(days_ago),
        "contentPath": path or f"/insights-news/insights/2026/09/{title.lower().replace(' ', '-')}",
        "description": description,
        "eyebrow": "Credit | Market Insight",
        "author": "Torsten Slok",
        "maxCount": "231",
    }


def _spark_card(title, slug, days_ago=1, eyebrow="Macroeconomic Indicators &amp; Trends"):
    """Mirrors the server-rendered markup on the Daily Spark listing page."""
    return f"""
    <div class="blog-detail">
      <div class="blog-detail-info">
        <span class="blog-detail-info-eyebrow-text">{eyebrow}</span>
        <p class="blog-detail-info-date">{_recent(days_ago)}</p>
        <h2 class="blog-detail-info-title-heading">
          <a class="blog-detail-info-title" href="/insights-news/insights/daily-spark/{slug}">{title}</a>
        </h2>
        <div class="blog-detail-info-separator"></div>
      </div>
    </div>"""


def _spark_page(*cards):
    return (
        '<html><body><div id="total-results" data-totalCount="633"></div>'
        '<div class="blog-results-container" data-blogsPerPage="10">'
        + "".join(cards)
        + "</div></body></html>"
    ).encode("utf-8")


class TestApolloInsights(unittest.TestCase):
    """The Reports-side feed, backed by the site's own insight.json servlet."""

    def _run(self, payload):
        with patch("reports_fetcher._fetch_url") as mock_fetch:
            mock_fetch.return_value = json.dumps(payload).encode("utf-8")
            articles = fetch_apollo(INSIGHTS_CFG)
        return articles, mock_fetch

    def test_keeps_whitepapers_and_articles_only(self):
        payload = [
            _insight("Midyear Credit Outlook", "whitepaper"),
            _insight("Industrial Comeback", "article"),
            _insight("The Allocation Episode", "podcast"),
            _insight("What Makes Apollo Apollo", "video"),
        ]
        articles, _ = self._run(payload)
        self.assertEqual(
            sorted(a["title"] for a in articles),
            ["Industrial Comeback", "Midyear Credit Outlook"],
        )

    def test_maps_reports_fields(self):
        articles, _ = self._run([
            _insight(
                "Midyear Credit Outlook", "whitepaper",
                path="/insights-news/insights/2026/08/2026-midyear-credit-outlook",
                description="Adoption, financing and investing in the AI era.",
            ),
        ])
        self.assertEqual(len(articles), 1)
        art = articles[0]
        self.assertEqual(
            art["link"],
            "https://www.apollo.com/insights-news/insights/2026/08/2026-midyear-credit-outlook",
        )
        self.assertEqual(art["description"], "Adoption, financing and investing in the AI era.")
        self.assertEqual(art["category"], "Reports")
        self.assertEqual(art["region"], "International")
        self.assertEqual(art["publisher"], "Apollo")
        self.assertEqual(art["feed_id"], "apollo-insights")
        self.assertEqual(art["date"].date(), (datetime.now(IST_TZ) - timedelta(days=1)).date())

    def test_requests_first_page_one_based(self):
        """pageOffset is 1-based; pageOffset=0 makes the AEM servlet answer 500."""
        _, mock_fetch = self._run([])
        requested = mock_fetch.call_args[0][0]
        self.assertIn("/api/int.insight.json", requested)
        self.assertIn("pageOffset=1&", requested)

    def test_drops_stale_items(self):
        articles, _ = self._run([
            _insight("Fresh Paper", "whitepaper", days_ago=2),
            _insight("Old Paper", "whitepaper", days_ago=90),
        ])
        self.assertEqual([a["title"] for a in articles], ["Fresh Paper"])

    def test_unexpected_shape_returns_empty_not_crash(self):
        articles, _ = self._run({"error": "changed"})
        self.assertEqual(articles, [])


class TestApolloDailySpark(unittest.TestCase):
    """The News-side feed, parsed from the server-rendered listing page."""

    def _run(self, page_bytes):
        with patch("reports_fetcher._fetch_url") as mock_fetch:
            mock_fetch.return_value = page_bytes
            return fetch_apollo(DAILY_SPARK_CFG)

    def test_parses_cards_and_maps_news_fields(self):
        articles = self._run(_spark_page(
            _spark_card("Is an Agentic Bank Run Coming?", "is-an-agentic-bank-run-coming", 1),
            _spark_card("Higher for Longer Hits the Lowest Rated", "higher-for-longer-hits-the-lowest-rated", 2,
                        eyebrow="Credit &amp; Fixed Income"),
        ))
        self.assertEqual(len(articles), 2)
        art = articles[0]
        self.assertEqual(art["title"], "Is an Agentic Bank Run Coming?")
        self.assertEqual(
            art["link"],
            "https://www.apollo.com/insights-news/insights/daily-spark/is-an-agentic-bank-run-coming",
        )
        # The category eyebrow is the only descriptive text on the card.
        self.assertEqual(art["description"], "Macroeconomic Indicators & Trends")
        self.assertEqual(articles[1]["description"], "Credit & Fixed Income")
        self.assertEqual(art["category"], "News")
        self.assertEqual(art["publisher"], "Apollo")
        self.assertEqual(art["feed_id"], "apollo-daily-spark")

    def test_sorted_newest_first(self):
        articles = self._run(_spark_page(
            _spark_card("Older", "older", 3),
            _spark_card("Newer", "newer", 1),
        ))
        self.assertEqual([a["title"] for a in articles], ["Newer", "Older"])

    def test_changed_layout_returns_empty_not_crash(self):
        self.assertEqual(self._run(b"<html><body><p>Redesigned</p></body></html>"), [])


class TestApolloMedia(unittest.TestCase):
    """The Videos-side feed: podcasts and videos from the same servlet."""

    def _run(self, payload):
        with patch("reports_fetcher._fetch_url") as mock_fetch:
            mock_fetch.return_value = json.dumps(payload).encode("utf-8")
            return fetch_apollo_media(MEDIA_CFG)

    def test_keeps_podcasts_and_videos_only(self):
        articles = self._run([
            _insight("The Allocation Episode", "podcast"),
            _insight("Empowering Retirees", "video"),
            _insight("Midyear Credit Outlook", "whitepaper"),
            _insight("Industrial Comeback", "article"),
        ])
        self.assertEqual(
            sorted(a["title"] for a in articles),
            ["Empowering Retirees", "The Allocation Episode"],
        )

    def test_maps_video_card_fields(self):
        articles = self._run([
            _insight("Empowering Retirees", "video",
                     path="/insights-news/insights/2026/08/empowering-retirees",
                     image="/content/dam/apolloaem/images/insights/2026/retirees.png"),
        ])
        art = articles[0]
        self.assertEqual(art["link"], "https://www.apollo.com/insights-news/insights/2026/08/empowering-retirees")
        self.assertEqual(
            art["thumbnail"],
            "https://www.apollo.com/content/dam/apolloaem/images/insights/2026/retirees.png",
        )
        self.assertEqual(art["category"], "Videos")
        self.assertEqual(art["publisher"], "Apollo")
        # The YouTube tab filters on this; the RSS path copies it from the feed too.
        self.assertEqual(art["youtube_bucket"], "Educational/Explainers")

    def test_old_items_kept_like_a_youtube_channel(self):
        """No 30-day Reports window: the tab shows a channel's latest items."""
        articles = self._run([_insight("Old Podcast", "podcast", days_ago=75)])
        self.assertEqual([a["title"] for a in articles], ["Old Podcast"])

    def test_capped_at_latest_fifteen_newest_first(self):
        articles = self._run([_insight(f"Ep {i}", "podcast", days_ago=i) for i in range(1, 21)])
        self.assertEqual(len(articles), 15)
        self.assertEqual(articles[0]["title"], "Ep 1")

    def test_missing_image_leaves_thumbnail_empty(self):
        item = _insight("No Art", "video")
        item["featuredImage"] = ""
        self.assertEqual(self._run([item])[0]["thumbnail"], "")

    def test_fetch_failure_returns_empty_not_crash(self):
        with patch("reports_fetcher._fetch_url", side_effect=Exception("HTTP Error 500")):
            self.assertEqual(fetch_apollo_media(MEDIA_CFG), [])

    def test_dispatcher_routes_media_before_generic_prefix(self):
        """REPORT_FETCHERS matches by startswith in order; 'apollo:' must not win."""
        self.assertIs(get_report_fetcher("apollo:media"), fetch_apollo_media)
        self.assertIs(get_report_fetcher("apollo:insights"), fetch_apollo)


class TestApolloUnknownSuffix(unittest.TestCase):
    def test_unknown_suffix_fails_softly(self):
        cfg = dict(INSIGHTS_CFG, feed="apollo:nonsense")
        with patch("reports_fetcher._fetch_url") as mock_fetch:
            self.assertEqual(fetch_apollo(cfg), [])
        mock_fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
