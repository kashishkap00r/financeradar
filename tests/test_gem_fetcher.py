"""Unit tests for the Global Energy Monitor reports scraper."""

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from reports_fetcher import fetch_gem, _gem_parse_cards, _gem_month_start


GEM_CFG = {
    "id": "gem-reports",
    "name": "Global Energy Monitor — Reports",
    "url": "https://globalenergymonitor.org/reports-and-briefings/",
    "feed": "gem:reports",
    "category": "Reports",
    "region": "International",
    "publisher": "Global Energy Monitor",
}


def _card(slug, title, date_text, type_tag="Report", topic="Energy transition"):
    return f'''<a href="/research/{slug}" class="card  w-inline-block">
  <div class="tag-row">
    <div class="tag">
            {type_tag}
      </div>
    <div class="tag">
            {topic}
      </div>
  </div>
  <div class="card-title"><strong>
<span>{title}</span>
</strong></div>
  <div class="card-date">{date_text}</div>
  <div class="more-pop"><div>Read Report</div></div>
</a>'''


def _ajax(cards):
    """Drupal views AJAX responses are a list of command objects."""
    return json.dumps([
        {"command": "settings", "settings": {}},
        {"command": "insert", "data": '<div class="card-row">' + "".join(cards) + "</div>"},
    ]).encode("utf-8")


def _rss(entries):
    items = "".join(
        f"<item><title>{t}</title>"
        f"<link>https://globalenergymonitor.org/research/{s}</link>"
        f"<pubDate>{d}</pubDate></item>"
        for s, t, d in entries
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{items}</channel></rss>'.encode("utf-8")


class TestGemMonthStart(unittest.TestCase):
    def test_resolves_month_only_text_to_first_of_month_utc(self):
        dt = _gem_month_start("September 2026")
        self.assertEqual((dt.year, dt.month, dt.day), (2026, 9, 1))
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_handles_abbreviated_and_padded_month_text(self):
        self.assertEqual(_gem_month_start("  Aug 2026 ").month, 8)

    def test_returns_none_for_unparseable_text(self):
        self.assertIsNone(_gem_month_start(""))
        self.assertIsNone(_gem_month_start("Coming soon"))


class TestGemCardParsing(unittest.TestCase):
    def test_extracts_title_link_date_and_topic(self):
        html = '<div class="card-row">' + _card(
            "wind-and-solar-potential-mediterranean",
            "Wind and solar potential in the Mediterranean",
            "September 2026",
        ) + "</div>"
        cards = _gem_parse_cards(html)

        self.assertEqual(len(cards), 1)
        c = cards[0]
        self.assertEqual(c["slug"], "wind-and-solar-potential-mediterranean")
        self.assertEqual(c["title"], "Wind and solar potential in the Mediterranean")
        self.assertEqual(c["date_text"], "September 2026")
        self.assertEqual(c["topics"], ["Energy transition"])

    def test_skips_cards_not_tagged_as_a_report(self):
        """Guards against view_args silently selecting a different listing."""
        html = (
            _card("a-report", "A real report", "September 2026", type_tag="Report")
            + _card("a-job", "Open position", "September 2026", type_tag="Career")
        )
        cards = _gem_parse_cards(html)
        self.assertEqual([c["slug"] for c in cards], ["a-report"])

    def test_accepts_briefing_as_a_report_type(self):
        html = _card("a-briefing", "A briefing", "September 2026", type_tag="Briefing")
        self.assertEqual(len(_gem_parse_cards(html)), 1)


class TestGemFetcher(unittest.TestCase):
    def setUp(self):
        now = datetime.now(timezone.utc)
        self.this_month = now.strftime("%B %Y")

    def test_maps_cards_onto_report_articles(self):
        with patch("reports_fetcher._fetch_url",
                   return_value=_ajax([_card("slug-one", "Report one", self.this_month)])), \
             patch("reports_fetcher._fetch_url_bytes", return_value=_rss([])):
            articles = fetch_gem(GEM_CFG)

        self.assertEqual(len(articles), 1)
        a = articles[0]
        self.assertEqual(a["title"], "Report one")
        self.assertEqual(a["link"], "https://globalenergymonitor.org/research/slug-one")
        self.assertEqual(a["category"], "Reports")
        self.assertEqual(a["region"], "International")
        self.assertEqual(a["publisher"], "Global Energy Monitor")
        self.assertEqual(a["description"], "Energy transition")
        self.assertEqual(a["date"].day, 1)

    def test_rss_supplies_an_exact_date_when_it_covers_the_report(self):
        now = datetime.now(timezone.utc)
        exact = now.replace(day=9, hour=23, minute=0, second=0, microsecond=0)
        with patch("reports_fetcher._fetch_url",
                   return_value=_ajax([_card("slug-one", "Report one", self.this_month)])), \
             patch("reports_fetcher._fetch_url_bytes",
                   return_value=_rss([("slug-one", "Report one",
                                       exact.strftime("%a, %d %b %Y %H:%M:%S +0000"))])):
            articles = fetch_gem(GEM_CFG)

        # Exact day 9 from RSS, not the day-1 approximation from the card.
        self.assertEqual(articles[0]["date"].day, 9)

    def test_posts_the_expected_views_arguments(self):
        with patch("reports_fetcher._fetch_url", return_value=_ajax([])) as mock_fetch, \
             patch("reports_fetcher._fetch_url_bytes", return_value=_rss([])):
            fetch_gem(GEM_CFG)

        url = mock_fetch.call_args[0][0]
        body = mock_fetch.call_args.kwargs["data"].decode()
        self.assertIn("/views/ajax", url)
        self.assertIn("view_name=resource_listing", body)
        self.assertIn("view_display_id=block_2", body)

    def test_survives_rss_failure_and_still_returns_cards(self):
        """RSS only refines dates; losing it must not lose the listing."""
        with patch("reports_fetcher._fetch_url",
                   return_value=_ajax([_card("slug-one", "Report one", self.this_month)])), \
             patch("reports_fetcher._fetch_url_bytes", side_effect=Exception("rss down")):
            articles = fetch_gem(GEM_CFG)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["date"].day, 1)

    def test_returns_empty_when_listing_fails(self):
        with patch("reports_fetcher._fetch_url", side_effect=Exception("views down")), \
             patch("reports_fetcher._fetch_url_bytes", return_value=_rss([])):
            self.assertEqual(fetch_gem(GEM_CFG), [])

    def test_drops_reports_older_than_the_freshness_window(self):
        old = (datetime.now(timezone.utc) - timedelta(days=200)).strftime("%B %Y")
        with patch("reports_fetcher._fetch_url",
                   return_value=_ajax([_card("old-one", "Ancient report", old)])), \
             patch("reports_fetcher._fetch_url_bytes", return_value=_rss([])):
            self.assertEqual(fetch_gem(GEM_CFG), [])


if __name__ == "__main__":
    unittest.main()
