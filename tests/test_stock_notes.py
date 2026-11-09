"""Tests for broker stock notes: Moneycontrol + Business Standard fetchers,
broker-name cleanup, Indian-only filter, cross-source dedup, and the
AI-ranker exclusion (stock notes must never reach the homepage picks)."""

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from articles import IST_TZ
from reports_fetcher import fetch_bs_research, fetch_moneycontrol_ideas, scraper
from stock_notes import (
    STOCK_NOTE_KIND,
    canonical_broker,
    canonical_rating,
    clean_company,
    dedup_stock_notes,
)


def _ymd(days_ago):
    return (datetime.now(IST_TZ) - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _dmy(days_ago):
    return (datetime.now(IST_TZ) - timedelta(days=days_ago)).strftime("%d/%m/%Y")


MC_CFG = {
    "id": "moneycontrol-stock-ideas",
    "name": "Moneycontrol — Broker Research",
    "url": "https://www.moneycontrol.com/markets/stock-ideas/",
    "feed": "mcideas:stock-ideas",
    "category": "Reports",
    "region": "Indian",
    "publisher": "Moneycontrol",
    "kind": "stock_note",
    "max_items": 800,
    "max_age_days": 14,
}

BS_CFG = {
    "id": "business-standard-research",
    "name": "Business Standard — Research Reports",
    "url": "https://www.business-standard.com/markets/research-report",
    "feed": "bsresearch:reports",
    "category": "Reports",
    "region": "Indian",
    "publisher": "Business Standard",
    "kind": "stock_note",
    "max_items": 400,
    "max_age_days": 14,
}


def _mc_row(**over):
    row = {
        "organization": "Motilal Oswal",
        "entry_date": _ymd(0),
        "target_price_date": _ymd(2),
        "heading": "Buy ONGC; target of Rs 285: Motilal Oswal",
        "attachment": "https://images.moneycontrol.com/static-mcnews/2026/11/ONGC-moti.pdf",
        "target_price": "285",
        "recommended_price": 232,
        "stkname": "Oil and Natural Gas Corporation",
        "stockShortName": "ONGC",
        "recommend_flag": "BUY",
        "stock_data": {
            "current": {"recommend_flag": "B", "target_price": "285", "P_ORGANIZATION": "Motilal Oswal"},
            "previous": {"recommend_flag": "N", "target_price": 290, "P_ORGANIZATION": "Motilal Oswal"},
        },
    }
    row.update(over)
    return row


def _mc_payload(rows):
    return json.dumps({"success": 1, "data": rows}).encode("utf-8")


def _bs_page(rows):
    data = {"props": {"pageProps": {"response2": {"data": rows}}}}
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(data)
        + "</script></body></html>"
    ).encode("utf-8")


def _bs_row(**over):
    row = {
        "id": 21356,
        "brokertips_date": _dmy(1),
        "recommedation_date": _dmy(1),
        "broker_name": "Emkay",
        "action": "Buy",
        "price": 470,
        "target_price": 575,
        "pdf_path": "/_media/bs/data/market-reports/equity-brokertips/2026-11/1794.pdf",
        "company_name": "Honasa Consumer",
        "company_full_name": "Honasa Consumer Ltd",
    }
    row.update(over)
    return row


class TestBrokerNames(unittest.TestCase):
    def test_aliases_collapse_to_one_name(self):
        for raw in ("Prabhudas Liladhar", "Prabhudas Lilladhar", "Prabhudas Lilladher", "PL Capital"):
            self.assertEqual(canonical_broker(raw), "Prabhudas Lilladher", raw)
        for raw in ("Emkay", "Enkay", "Emkay Global", "Emkay Global Financial Services"):
            self.assertEqual(canonical_broker(raw), "Emkay Global", raw)
        for raw in ("Motilal Oswal", "Motilala Oswal", "Motilal Oswal Securities"):
            self.assertEqual(canonical_broker(raw), "Motilal Oswal", raw)
        self.assertEqual(canonical_broker("ICICIdirect.com"), "ICICI Securities")
        self.assertEqual(canonical_broker("Share Khan"), "Sharekhan")
        self.assertEqual(canonical_broker("Choice Institutional Equities"), "Choice Broking")

    def test_unknown_indian_broker_passes_through_trimmed(self):
        self.assertEqual(canonical_broker("  Networth Capital "), "Networth Capital")

    def test_foreign_brokers_and_non_brokers_are_dropped(self):
        for raw in ("Citi Research", "Jefferies", "Morgan Stanley", "CLSA", "Nomura", "Goldman Sachs", "Moneycontrol", "", None):
            self.assertIsNone(canonical_broker(raw), raw)

    def test_ratings(self):
        self.assertEqual(canonical_rating("BUY"), "Buy")
        self.assertEqual(canonical_rating("accumulate"), "Accumulate")
        self.assertEqual(canonical_rating("Initiating Coverage"), "Initiating coverage")
        self.assertIsNone(canonical_rating("-"))
        self.assertIsNone(canonical_rating(None))

    def test_clean_company(self):
        self.assertEqual(clean_company("Honasa Consumer Ltd"), "Honasa Consumer")
        self.assertEqual(clean_company("Deepak Nitrite Limited"), "Deepak Nitrite")
        self.assertEqual(clean_company("  Oil and Natural Gas Corporation "), "Oil and Natural Gas Corporation")


class TestMoneycontrolFetcher(unittest.TestCase):
    def test_maps_row_to_stock_note(self):
        with patch("reports_fetcher._fetch_url", return_value=_mc_payload([_mc_row()])):
            arts = fetch_moneycontrol_ideas(MC_CFG)
        self.assertEqual(len(arts), 1)
        a = arts[0]
        self.assertEqual(a["kind"], STOCK_NOTE_KIND)
        self.assertEqual(a["publisher"], "Motilal Oswal")
        self.assertEqual(a["via"], "Moneycontrol")
        self.assertEqual(a["region"], "Indian")
        self.assertEqual(a["company"], "Oil and Natural Gas Corporation")
        self.assertEqual(a["rating"], "Buy")
        self.assertEqual(a["target"], 285.0)
        self.assertEqual(a["reco_price"], 232.0)
        self.assertEqual(a["prev_target"], 290.0)
        self.assertEqual(a["prev_rating"], "Hold")
        self.assertEqual(a["link"], "https://images.moneycontrol.com/static-mcnews/2026/11/ONGC-moti.pdf")
        self.assertEqual(a["title"], "Oil and Natural Gas Corporation: Buy, target ₹285")
        # Report date (target_price_date), not Moneycontrol's posting date
        self.assertEqual(a["date"].date().isoformat(), _ymd(2))
        self.assertEqual(a["feed_id"], "moneycontrol-stock-ideas")

    def test_report_date_after_posting_date_is_a_typo(self):
        # Seen live 9 Nov 2026: posted 2 Nov, "target_price_date" 11 Nov.
        row = _mc_row(entry_date=_ymd(7), target_price_date=(datetime.now(IST_TZ) + timedelta(days=2)).strftime("%Y-%m-%d"))
        with patch("reports_fetcher._fetch_url", return_value=_mc_payload([row])):
            a = fetch_moneycontrol_ideas(MC_CFG)[0]
        self.assertEqual(a["date"].date().isoformat(), _ymd(7))

    def test_previous_call_from_another_broker_is_ignored(self):
        row = _mc_row()
        row["stock_data"]["previous"]["P_ORGANIZATION"] = "ICICI Securities"
        with patch("reports_fetcher._fetch_url", return_value=_mc_payload([row])):
            a = fetch_moneycontrol_ideas(MC_CFG)[0]
        self.assertIsNone(a.get("prev_target"))
        self.assertIsNone(a.get("prev_rating"))

    def test_drops_moneycontrol_own_picks_rows_without_pdf_and_old_rows(self):
        rows = [
            _mc_row(organization="Moneycontrol"),
            _mc_row(attachment=""),
            _mc_row(target_price_date=_ymd(20), entry_date=_ymd(19)),
            _mc_row(organization="ICICI Securities", stkname="Trent Limited"),
        ]
        with patch("reports_fetcher._fetch_url", return_value=_mc_payload(rows)):
            arts = fetch_moneycontrol_ideas(MC_CFG)
        self.assertEqual([a["company"] for a in arts], ["Trent"])

    def test_pages_until_rows_are_older_than_window(self):
        fresh = [_mc_row(stkname=f"Fresh {i}") for i in range(3)]
        old = [_mc_row(stkname=f"Old {i}", target_price_date=_ymd(30), entry_date=_ymd(30)) for i in range(3)]
        pages = [_mc_payload(fresh), _mc_payload(old), _mc_payload(fresh)]
        with patch("reports_fetcher._MC_IDEAS_PAGE_SIZE", 3), \
                patch("reports_fetcher._fetch_url", side_effect=pages) as m:
            arts = fetch_moneycontrol_ideas(MC_CFG)
        self.assertEqual(m.call_count, 2)  # full pages, but stopped after the all-old one
        self.assertEqual(len(arts), 3)

    def test_short_page_is_the_last_page(self):
        with patch("reports_fetcher._fetch_url", return_value=_mc_payload([_mc_row()])) as m:
            fetch_moneycontrol_ideas(MC_CFG)
        self.assertEqual(m.call_count, 1)

    def test_bad_target_does_not_crash(self):
        with patch("reports_fetcher._fetch_url", return_value=_mc_payload([_mc_row(target_price="NA")])):
            a = fetch_moneycontrol_ideas(MC_CFG)[0]
        self.assertIsNone(a["target"])
        self.assertEqual(a["title"], "Oil and Natural Gas Corporation: Buy")


class TestBusinessStandardFetcher(unittest.TestCase):
    def test_parses_next_data(self):
        rows = [
            _bs_row(),
            _bs_row(broker_name="Citi Research", company_full_name="Infosys Ltd"),
            _bs_row(broker_name="JM Financial", recommedation_date=_dmy(25), company_full_name="Old Co Ltd"),
            _bs_row(broker_name="Elara Capital", pdf_path="", company_full_name="No Pdf Ltd"),
        ]
        with patch("reports_fetcher._fetch_url", return_value=_bs_page(rows)):
            arts = fetch_bs_research(BS_CFG)
        self.assertEqual(len(arts), 1)
        a = arts[0]
        self.assertEqual(a["publisher"], "Emkay Global")
        self.assertEqual(a["via"], "Business Standard")
        self.assertEqual(a["company"], "Honasa Consumer")
        self.assertEqual(a["rating"], "Buy")
        self.assertEqual(a["target"], 575.0)
        self.assertEqual(a["reco_price"], 470.0)
        self.assertEqual(a["link"], "https://bsmedia.business-standard.com/_media/bs/data/market-reports/equity-brokertips/2026-11/1794.pdf")
        self.assertEqual(a["date"].date().isoformat(), _ymd(1))
        self.assertEqual(a["kind"], STOCK_NOTE_KIND)


class TestDedup(unittest.TestCase):
    def _note(self, broker, company, target, days_ago, via, prev=None, link=None):
        return {
            "kind": STOCK_NOTE_KIND, "publisher": broker, "company": company, "target": target,
            "date": datetime.now(IST_TZ) - timedelta(days=days_ago), "via": via,
            "prev_target": prev, "link": link or f"https://x/{via}/{company}/{target}",
        }

    def test_same_call_on_both_sites_is_kept_once_preferring_richer_row(self):
        mc = self._note("Motilal Oswal", "Jubilant Foodworks", 625.0, 2, "Moneycontrol", prev=600.0)
        bs = self._note("Motilal Oswal", "Jubilant FoodWorks", 625.0, 0, "Business Standard")
        out = dedup_stock_notes([bs, mc])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["via"], "Moneycontrol")

    def test_different_target_or_far_apart_dates_are_separate_calls(self):
        a = self._note("JM Financial", "Bharti Airtel", 2410.0, 0, "Business Standard")
        b = self._note("JM Financial", "Bharti Airtel", 2300.0, 0, "Moneycontrol")
        c = self._note("JM Financial", "Bharti Airtel", 2410.0, 10, "Moneycontrol")
        self.assertEqual(len(dedup_stock_notes([a, b, c])), 3)

    def test_other_reports_pass_through_untouched_and_in_order(self):
        r1 = {"title": "Ecowrap", "link": "https://sbi/1"}
        note = self._note("Emkay Global", "Infosys", 1300.0, 0, "Moneycontrol")
        r2 = {"title": "CareEdge", "link": "https://care/2"}
        self.assertEqual(dedup_stock_notes([r1, note, r2]), [r1, note, r2])


class TestScraperLimits(unittest.TestCase):
    def test_feed_level_max_items_and_age(self):
        now = datetime.now(timezone.utc)

        @scraper
        def fake(cfg):
            return [{"date": now - timedelta(days=d)} for d in range(40)]

        self.assertEqual(len(fake({"name": "default"})), 30)  # SCRAPER_MAX_ARTICLES default
        self.assertEqual(len(fake({"name": "aged", "max_items": 100, "max_age_days": 14})), 14)  # days 0–13


class TestRankerExcludesStockNotes(unittest.TestCase):
    def test_stock_notes_never_become_ranking_candidates(self):
        from ai_ranker import build_candidates_for_source

        now = datetime.now(IST_TZ)
        snapshot = {"reports": [
            {"title": "ONGC: Buy, target ₹285", "url": "https://mc/1.pdf", "publisher": "Motilal Oswal",
             "published_at": now.isoformat(), "kind": "stock_note", "source_id": "moneycontrol-stock-ideas"},
            {"title": "Ecowrap: GST", "url": "https://sbi/2", "publisher": "SBI",
             "published_at": now.isoformat(), "source_id": "sbi-research"},
        ]}
        got = build_candidates_for_source(snapshot, "reports", now=now)
        self.assertEqual([c["title"] for c in got], ["Ecowrap: GST"])


if __name__ == "__main__":
    unittest.main()
