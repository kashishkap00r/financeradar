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
    filing_subtitle,
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


class TestFilingSubtitle(unittest.TestCase):
    """The card title is the company, so the subtitle must say what happened.

    Exchange filings bury the substance behind stock phrasing — these are the
    real shapes from /api/announcements, not invented ones.
    """

    def test_strips_has_informed_the_exchange_lead_in(self):
        self.assertEqual(
            filing_subtitle(
                "Astron Paper & Board Mill Limited has informed the Exchange about "
                "Corporate Insolvency Resolution Process",
                "Astron Paper & Board Mill Ltd", "Nclt"),
            "Corporate Insolvency Resolution Process")

    def test_handles_had_as_well_as_has(self):
        out = filing_subtitle(
            "Foo Limited had informed the Exchange regarding change in directorate",
            "Foo Limited", "Change In Management")
        self.assertEqual(out, "Change in directorate")

    def test_tames_all_caps_filings(self):
        out = filing_subtitle(
            "MILLWORKS TECHNOLOGIES LIMITED HAS INFORMED THE EXCHANGE REGARDING "
            "THE ACQUISITION OF VIDWAN AERONAUTICS PRIVATE LIMITED",
            "Millworks Technologies Ltd", "Acquisition")
        self.assertNotEqual(out, out.upper())
        self.assertIn("acquisition of vidwan", out.lower())

    def test_keeps_acronyms_readable_when_lowercasing(self):
        out = filing_subtitle("UPDATE ON SEBI AND NCLT PROCEEDINGS FOR THE COMPANY",
                              "Foo Ltd", "Legal/Reg")
        self.assertIn("SEBI", out)
        self.assertIn("NCLT", out)

    def test_rewrites_clarification_queries_rather_than_dropping_the_verb(self):
        out = filing_subtitle(
            "The Exchange has sought clarification from Marsons Limited for the "
            "quarter ended 30-Jun-2026 with respect to Regulation 33 of the SEBI "
            "(LODR) Regulations, 2015",
            "Marsons Limited", "Results")
        self.assertTrue(out.lower().startswith("exchange sought clarification"), out)
        self.assertIn("30-Jun-2026", out)

    def test_strips_submitted_to_the_exchange_and_stranded_auxiliary(self):
        out = filing_subtitle(
            "SBI Capital Markets Ltd has submitted to the Exchange a copy of "
            "Post offer advertisement",
            "SBI Capital Markets Ltd", "Open Offer")
        self.assertEqual(out, "Post offer advertisement")

    def test_keeps_substance_after_a_regulation_30_prefix(self):
        out = filing_subtitle(
            "Disclosure under Regulation 30 of SEBI (Listing Obligations and "
            "Disclosure Requirements) Regulations, 2015 - Intimation of "
            "Participation in Alpha Ideas Conference",
            "Exato Technologies Ltd", "Investor Meet")
        self.assertIn("Participation in Alpha Ideas", out)
        self.assertNotIn("Regulation 30", out)

    def test_falls_back_to_category_for_a_bare_citation(self):
        for headline in (
            "Pursuant to Regulation 30 read with Schedule III of the SEBI (LODR) "
            "Regulations, 2015",
            "Regulation 30",
            "As enclosed.",
            "'update'",
            "",
        ):
            self.assertEqual(filing_subtitle(headline, "Foo Ltd", "Board Meeting"),
                             "Board Meeting", headline)

    def test_never_returns_a_wordless_subtitle(self):
        """Cutting a citation at an interior comma once left just '2015'."""
        out = filing_subtitle("Pursuant to Regulation 30 of SEBI LODR Regulations, 2015",
                              "Foo Ltd", "Dividend")
        self.assertGreaterEqual(sum(1 for ch in out if ch.isalpha()), 3)

    def test_passes_through_an_already_informative_headline(self):
        for headline in ("Record Date for Dividend Distribution",
                         "Acquisition of additional stake in Step-Down Subsidiary",
                         "Company Received a Show Cause Notice"):
            self.assertEqual(filing_subtitle(headline, "Foo Ltd", "Other"), headline)

    def test_does_not_restate_the_company_name(self):
        out = filing_subtitle("Nila Spaces Limited has informed the Exchange regarding "
                              "allotment of equity shares",
                              "Nila Spaces Limited", "Pref")
        self.assertNotIn("nila spaces", out.lower())

    def test_long_citation_chain_does_not_hang(self):
        """A nested quantifier here used to backtrack catastrophically."""
        headline = "Regulation 30 read with schedule iii read with clause 5 " * 8
        filing_subtitle(headline, "Foo Ltd", "Other")  # must simply return

    def test_extracts_the_press_release_title_as_the_gist(self):
        """A press release's substance is its title, not the dateline."""
        self.assertEqual(
            filing_subtitle('A press release dated September 03, 2026, titled '
                            '"Prestige Group Expands Into Chennai"',
                            "Prestige Estates Projects Limited", "Press Release"),
            "Prestige Group Expands Into Chennai")

    def test_press_release_dateline_may_contain_several_commas(self):
        out = filing_subtitle('A press release dated August 29, 2026, titled '
                              '"Foo wins a contract"', "Bar Ltd", "Press Release")
        self.assertEqual(out, "Foo wins a contract")

    def test_bare_press_release_headline_falls_back(self):
        self.assertEqual(filing_subtitle("Press Release", "Foo Ltd", "Press Release"),
                         "Press Release")

    def test_disclosure_under_reg_30_is_a_citation_not_a_subtitle(self):
        for headline in ("Disclosure under reg 30", "Intimation under Regulation 30",
                         "Disclosure under Regulation 10(7) in respect of acquisition"):
            self.assertEqual(filing_subtitle(headline, "Foo Ltd", "Acquisition"),
                             "Acquisition", headline)

    def test_strips_a_stranded_year_from_a_cut_citation(self):
        out = filing_subtitle("2015, we are enclosing herewith a Press Release titled "
                              "'Tata Motors launches Harrier EV'",
                              "Tata Motors Passenger Vehicles Ltd", "Press Release")
        self.assertEqual(out, "Tata Motors launches Harrier EV")

    def test_subtitle_reaches_the_parsed_payload(self):
        out = parse_companies({"items": [_item(
            headline="Bharti Airtel Ltd has informed the Exchange about "
                     "acquisition of spectrum",
        )]}, now=NOW)
        self.assertEqual(out[0]["subtitle"], "Acquisition of spectrum")
        self.assertEqual(out[0]["title"], "Bharti Airtel Ltd")


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
