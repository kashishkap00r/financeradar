"""Tests for companies_fetcher.py (Market Tide announcements ingestion)."""

import unittest
from datetime import datetime, timedelta

from articles import IST_TZ
from companies_fetcher import (
    CAP_TIERS,
    RESERVED_FIELDS,
    _parse_markettide_date,
    cap_for_mcap,
    companies_cache_age_days,
    parse_companies,
)

NOW = datetime(2026, 9, 3, 18, 0, tzinfo=IST_TZ)


def _item(**over):
    base = {
        "id": "BSE-235bc2c3-50db-4e82-91aa-df104ed3771c",
        "exchange": "BSE",
        "company": "Bharti Airtel Ltd",
        "ticker": "532454",
        "category": "Company Update / Acquisition",
        "headline": "Disclosure under Regulation 30 of SEBI (LODR)",
        "time": "03 Sep, 11:59",
        "date": "2026-09-03",
        "score": 88,
        "tag": "Acquisition",
        "pdf_url": "https://www.bseindia.com/xml-data/corpfiling/AttachLive/x.pdf",
        "mcap": 1142012.0,
        "day": "2026-09-03",
    }
    base.update(over)
    return base


class TestCapBanding(unittest.TestCase):
    def test_thresholds_match_market_tides_own_bands(self):
        # The dashboard filters on "Above Rs 1 lakh cr", "Rs 50,000 cr - 1 lakh
        # cr", "Rs 10,000 - 50,000 cr", "Rs 1,000 - 10,000 cr", below that.
        self.assertEqual(cap_for_mcap(1_142_012), "Mega cap")
        self.assertEqual(cap_for_mcap(100_000), "Mega cap")
        self.assertEqual(cap_for_mcap(99_610), "Large cap")
        self.assertEqual(cap_for_mcap(50_000), "Large cap")
        self.assertEqual(cap_for_mcap(49_999), "Mid cap")
        self.assertEqual(cap_for_mcap(10_000), "Mid cap")
        self.assertEqual(cap_for_mcap(9_999), "Small cap")
        self.assertEqual(cap_for_mcap(1_000), "Small cap")
        self.assertEqual(cap_for_mcap(999), "Micro cap")
        self.assertEqual(cap_for_mcap(72.4), "Micro cap")

    def test_missing_or_bad_mcap_is_unbanded(self):
        for bad in (None, 0, -5, "", "abc", [1]):
            self.assertEqual(cap_for_mcap(bad), "")

    def test_every_band_label_is_a_declared_tier(self):
        for value in (500_000, 60_000, 20_000, 5_000, 100):
            self.assertIn(cap_for_mcap(value), CAP_TIERS)


class TestDateParsing(unittest.TestCase):
    def test_combines_date_and_display_time(self):
        dt = _parse_markettide_date("2026-09-03", "03 Sep, 11:59")
        self.assertEqual((dt.year, dt.month, dt.day, dt.hour, dt.minute),
                         (2026, 9, 3, 11, 59))
        self.assertIsNotNone(dt.tzinfo)

    def test_unreadable_time_keeps_the_date(self):
        """A filing with a junk time must not be dropped."""
        dt = _parse_markettide_date("2026-09-03", "sometime today")
        self.assertEqual((dt.year, dt.month, dt.day, dt.hour, dt.minute),
                         (2026, 9, 3, 0, 0))

    def test_out_of_range_time_falls_back_to_midnight(self):
        dt = _parse_markettide_date("2026-09-03", "03 Sep, 99:99")
        self.assertEqual((dt.hour, dt.minute), (0, 0))

    def test_missing_or_bad_date_is_none(self):
        self.assertIsNone(_parse_markettide_date(None, "03 Sep, 11:59"))
        self.assertIsNone(_parse_markettide_date("not-a-date", ""))


class TestParseCompanies(unittest.TestCase):
    def test_maps_payload_to_card_fields(self):
        out = parse_companies({"items": [_item()]}, now=NOW)
        self.assertEqual(len(out), 1)
        c = out[0]
        # Company leads; the boilerplate headline is the description.
        self.assertEqual(c["title"], "Bharti Airtel Ltd")
        self.assertEqual(c["description"], "Disclosure under Regulation 30 of SEBI (LODR)")
        self.assertEqual(c["cap"], "Mega cap")
        self.assertEqual(c["category"], "Acquisition")           # their tag
        self.assertEqual(c["sector"], "Company Update / Acquisition")  # filing type
        self.assertEqual(c["exchange"], "BSE")
        self.assertEqual(c["ticker"], "532454")
        self.assertEqual(c["score"], 88)
        self.assertEqual(c["source"], "Market Tide")

    def test_links_to_the_filing_pdf_not_the_quote_page(self):
        out = parse_companies({"items": [_item(page_url="https://nseindia.com/q")]}, now=NOW)
        self.assertTrue(out[0]["link"].endswith(".pdf"))

    def test_falls_back_to_page_url_when_no_pdf(self):
        out = parse_companies({"items": [_item(pdf_url="", page_url="https://nseindia.com/q")]},
                              now=NOW)
        self.assertEqual(out[0]["link"], "https://nseindia.com/q")

    def test_skips_items_missing_company_or_link(self):
        payload = {"items": [_item(company=""), _item(pdf_url="", page_url="")]}
        self.assertEqual(parse_companies(payload, now=NOW), [])

    def test_dedupes_on_id(self):
        payload = {"items": [_item(), _item(pdf_url="https://other.example/x.pdf")]}
        self.assertEqual(len(parse_companies(payload, now=NOW)), 1)

    def test_drops_filings_outside_the_freshness_window(self):
        old = (NOW - timedelta(days=90)).strftime("%Y-%m-%d")
        payload = {"items": [_item(id="OLD", date=old, day=old)]}
        self.assertEqual(parse_companies(payload, now=NOW), [])

    def test_sorts_by_score_then_recency(self):
        payload = {"items": [
            _item(id="A", company="Low", score=10),
            _item(id="B", company="High", score=90),
            _item(id="C", company="Mid", score=50),
        ]}
        self.assertEqual([c["title"] for c in parse_companies(payload, now=NOW)],
                         ["High", "Mid", "Low"])

    def test_tolerates_bare_array_and_bad_rows(self):
        self.assertEqual(len(parse_companies([_item(), "junk", None, 7], now=NOW)), 1)

    def test_non_numeric_score_and_mcap_do_not_raise(self):
        out = parse_companies({"items": [_item(score="high", mcap="big")]}, now=NOW)
        self.assertEqual(out[0]["score"], 0)
        self.assertEqual(out[0]["cap"], "")


class TestReservedFields(unittest.TestCase):
    def test_market_tides_own_prose_is_never_carried_through(self):
        """Their terms reserve summaries/scoring prose; we must not persist it."""
        payload = {"items": [_item(
            summary="Airtel is buying a stake in...",
            why_it_matters="This matters because...",
            impact="Positive",
            key_numbers="Rs 2,000 cr",
        )]}
        c = parse_companies(payload, now=NOW)[0]
        for field in RESERVED_FIELDS:
            self.assertNotIn(field, c, f"{field} must not reach the card payload")


class TestCacheAge(unittest.TestCase):
    def test_reports_age_of_newest_filing(self):
        items = [
            {"date": NOW - timedelta(days=9)},
            {"date": NOW - timedelta(days=2)},
        ]
        self.assertEqual(companies_cache_age_days(items, now=NOW), 2)

    def test_none_when_nothing_is_dated(self):
        self.assertIsNone(companies_cache_age_days([{"date": None}], now=NOW))
        self.assertIsNone(companies_cache_age_days([], now=NOW))

    def test_naive_datetimes_are_treated_as_ist(self):
        items = [{"date": (NOW - timedelta(days=1)).replace(tzinfo=None)}]
        self.assertEqual(companies_cache_age_days(items, now=NOW), 1)


if __name__ == "__main__":
    unittest.main()
