"""Unit tests for the IEA and CSEP report fetchers."""

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import reports_fetcher
from reports_fetcher import fetch_csep, fetch_iea

IEA_CFG = {
    "id": "iea-reports",
    "name": "IEA — Reports",
    "url": "https://www.iea.org/analysis?type=report",
    "feed": "iea:reports",
    "category": "Reports",
    "region": "International",
    "publisher": "IEA",
}

CSEP_CFG = {
    "id": "csep-publications",
    "name": "CSEP — Publications",
    "url": "https://csep.org/publication/",
    "feed": "csep:publications",
    "category": "Reports",
    "region": "Indian",
    "publisher": "CSEP",
}


def _iea_card(title, slug, kind, date_str):
    return (
        f'<li class="m-card-listing-item m-card-listing-item--report" data-id="1">'
        f'<a class="m-card" href="/reports/{slug}">'
        f'<h2 class="f-title-7 m-card__title">{title}</h2>'
        f'<p class="m-card__type">{kind}   &mdash;   {date_str}</p>'
        f"</a></li>"
    )


def _iea_page(cards, with_nav=True):
    nav = (
        '<ul class="m-card-listing m-card-listing--nav">'
        + _iea_card("Nav Menu Report", "nav-only", "Fuel report", "01 January 2020")
        + "</ul>"
    ) if with_nav else ""
    return f"<html><body>{nav}<ul class='m-card-listing'>{''.join(cards)}</ul></body></html>"


def _recent(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%d %B %Y")


class TestIeaFetcher(unittest.TestCase):
    """Validate IEA listing parsing, nav stripping, and challenge detection."""

    @patch("reports_fetcher._fetch_url")
    def test_parses_cards_and_splits_kind_from_date(self, mock_fetch):
        mock_fetch.return_value = _iea_page([
            _iea_card("Heat Pump Monitor 2026", "heat-pump-monitor-2026", "Technology report", _recent(3)),
        ]).encode("utf-8")

        articles = fetch_iea(IEA_CFG)

        self.assertEqual(len(articles), 1)
        a = articles[0]
        self.assertEqual(a["title"], "Heat Pump Monitor 2026")
        self.assertEqual(a["link"], "https://www.iea.org/reports/heat-pump-monitor-2026")
        self.assertEqual(a["description"], "Technology report")
        self.assertEqual(a["publisher"], "IEA")
        self.assertEqual(a["region"], "International")
        self.assertEqual(a["feed_id"], "iea-reports")
        self.assertIsNotNone(a["date"])
        self.assertIsNotNone(a["date"].tzinfo)

    @patch("reports_fetcher._fetch_url")
    def test_ignores_nav_menu_cards(self, mock_fetch):
        """The mega-menu reuses m-card markup and must not leak into results."""
        mock_fetch.return_value = _iea_page([
            _iea_card("Real Report", "real", "Fuel report", _recent(2)),
        ]).encode("utf-8")

        titles = [a["title"] for a in fetch_iea(IEA_CFG)]

        self.assertEqual(titles, ["Real Report"])
        self.assertNotIn("Nav Menu Report", titles)

    @patch("reports_fetcher._fetch_url")
    def test_dedupes_featured_block_repeats(self, mock_fetch):
        mock_fetch.return_value = _iea_page([
            _iea_card("Oil Market Report", "oil-market-report", "Fuel report", _recent(5)),
            _iea_card("Oil Market Report", "oil-market-report", "Fuel report", _recent(5)),
            _iea_card("Gas Market Report", "gas-market-report", "Fuel report", _recent(6)),
        ]).encode("utf-8")

        self.assertEqual(len(fetch_iea(IEA_CFG)), 2)

    @patch("reports_fetcher._fetch_url")
    def test_sorted_newest_first_despite_featured_ordering(self, mock_fetch):
        mock_fetch.return_value = _iea_page([
            _iea_card("Featured Older", "older", "Fuel report", _recent(20)),
            _iea_card("Newest", "newest", "Fuel report", _recent(1)),
            _iea_card("Middle", "middle", "Fuel report", _recent(10)),
        ]).encode("utf-8")

        self.assertEqual([a["title"] for a in fetch_iea(IEA_CFG)], ["Newest", "Middle", "Featured Older"])

    @patch("reports_fetcher._fetch_url")
    def test_cloudflare_challenge_fails_rather_than_returning_empty(self, mock_fetch):
        """A challenge must not be parsed as a legitimately empty listing."""
        mock_fetch.return_value = (
            b"<!DOCTYPE html><html><head><title>Just a moment...</title>"
            b'<script src="https://challenges.cloudflare.com/turnstile"></script></head></html>'
        )

        # @scraper swallows the raised error, but the empty result is what matters:
        # the aggregator then refills this feed from reports_cache.json.
        self.assertEqual(fetch_iea(IEA_CFG), [])

    @patch("reports_fetcher._fetch_url")
    def test_drops_stale_cards(self, mock_fetch):
        mock_fetch.return_value = _iea_page([
            _iea_card("Fresh", "fresh", "Fuel report", _recent(5)),
            _iea_card("Ancient", "ancient", "Fuel report", "12 November 2019"),
        ]).encode("utf-8")

        self.assertEqual([a["title"] for a in fetch_iea(IEA_CFG)], ["Fresh"])


class TestCsepFetcher(unittest.TestCase):
    """Validate CSEP multi-post-type REST aggregation."""

    def _post(self, title, slug, days_ago, excerpt="<p>Summary.</p>"):
        dt = datetime.now() - timedelta(days=days_ago)
        return {
            "title": {"rendered": title},
            "link": f"https://csep.org/reports/{slug}/",
            "date": dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "excerpt": {"rendered": excerpt},
        }

    @patch("reports_fetcher._fetch_url")
    def test_pools_every_post_type_into_one_source(self, mock_fetch):
        calls = []

        def fake(url, **kwargs):
            calls.append(url)
            if "/reports?" in url:
                return json.dumps([self._post("A Report", "a-report", 2)]).encode()
            if "/working-paper?" in url:
                return json.dumps([self._post("A Working Paper", "a-wp", 4)]).encode()
            return json.dumps([]).encode()

        mock_fetch.side_effect = fake
        articles = fetch_csep(CSEP_CFG)

        self.assertEqual([a["title"] for a in articles], ["A Report", "A Working Paper"])
        self.assertEqual(len(calls), len(reports_fetcher._CSEP_POST_TYPES))
        self.assertTrue(all(a["publisher"] == "CSEP" and a["region"] == "Indian" for a in articles))
        self.assertEqual(articles[0]["description"], "Summary.")

    @patch("reports_fetcher._fetch_url")
    def test_excludes_media_post_types(self, mock_fetch):
        """multimedia and interactives are tools, not reports."""
        mock_fetch.return_value = json.dumps([]).encode()
        fetch_csep(CSEP_CFG)

        queried = " ".join(c[0][0] for c in mock_fetch.call_args_list)
        self.assertNotIn("/multimedia?", queried)
        self.assertNotIn("/interactives?", queried)
        self.assertIn("/opinion-commentary?", queried)

    @patch("reports_fetcher._fetch_url")
    def test_one_failing_type_does_not_sink_the_feed(self, mock_fetch):
        def fake(url, **kwargs):
            if "/working-paper?" in url:
                raise Exception("HTTP Error 500")
            if "/reports?" in url:
                return json.dumps([self._post("Survivor", "survivor", 1)]).encode()
            return json.dumps([]).encode()

        mock_fetch.side_effect = fake

        self.assertEqual([a["title"] for a in fetch_csep(CSEP_CFG)], ["Survivor"])

    @patch("reports_fetcher._fetch_url")
    def test_sorted_newest_first_across_types(self, mock_fetch):
        def fake(url, **kwargs):
            if "/reports?" in url:
                return json.dumps([self._post("Older", "older", 20)]).encode()
            if "/policy-brief?" in url:
                return json.dumps([self._post("Newest", "newest", 1)]).encode()
            if "/discussion-note?" in url:
                return json.dumps([self._post("Middle", "middle", 9)]).encode()
            return json.dumps([]).encode()

        mock_fetch.side_effect = fake

        self.assertEqual([a["title"] for a in fetch_csep(CSEP_CFG)], ["Newest", "Middle", "Older"])

    @patch("reports_fetcher._fetch_url")
    def test_drops_stale_and_malformed_posts(self, mock_fetch):
        def fake(url, **kwargs):
            if "/reports?" in url:
                return json.dumps([
                    self._post("Fresh", "fresh", 3),
                    self._post("Stale", "stale", 400),
                    {"title": {"rendered": ""}, "link": "https://csep.org/x/", "date": None},
                    {"title": {"rendered": "No link"}, "link": "", "date": None},
                ]).encode()
            return json.dumps([]).encode()

        mock_fetch.side_effect = fake

        self.assertEqual([a["title"] for a in fetch_csep(CSEP_CFG)], ["Fresh"])

    @patch("reports_fetcher._fetch_url")
    def test_non_list_payload_is_ignored(self, mock_fetch):
        mock_fetch.return_value = json.dumps({"code": "rest_no_route"}).encode()

        self.assertEqual(fetch_csep(CSEP_CFG), [])


class TestDispatcherRegistration(unittest.TestCase):
    def test_registered(self):
        self.assertIs(reports_fetcher.get_report_fetcher("iea:reports"), fetch_iea)
        self.assertIs(reports_fetcher.get_report_fetcher("csep:publications"), fetch_csep)


if __name__ == "__main__":
    unittest.main()
