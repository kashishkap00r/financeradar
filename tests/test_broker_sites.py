"""Stock notes from brokers' own sites (PL, ICICI Direct, Kotak, SBI Securities,
Choice, Way2Wealth, Ventura) and how they dedup against the aggregators."""

import unittest
from datetime import datetime, timedelta
from unittest import mock

import reports_fetcher as rf
from articles import IST_TZ
from stock_notes import STOCK_NOTE_KIND, dedup_stock_notes, known_note_keys, merge_into_archive


def _note(broker, company, days_ago, via, target=None, headline="", link=None):
    return {"kind": STOCK_NOTE_KIND, "publisher": broker, "company": company, "target": target,
            "date": datetime(2026, 11, 10, tzinfo=IST_TZ) - timedelta(days=days_ago), "via": via,
            "headline": headline, "link": link or f"https://x/{broker}/{company}/{days_ago}/{via}"}


class TestTitleParsing(unittest.TestCase):
    def test_pl_titles(self):
        self.assertEqual(rf.split_pl_title(
            "Safari Industries (India) (SII IN) &#8211; Q2FY27 Result Update &#8211; Capacity expansion to drive growth &#8211; BUY"),
            ("Safari Industries (India)", "Capacity expansion to drive growth"))
        self.assertEqual(rf.split_pl_title("Ipca Laboratories (IPCA IN) – Q2FY27 Result Update – ‘ACCUMULATE’"),
                         ("Ipca Laboratories", ""))
        self.assertEqual(rf.split_pl_title("Bharti Airtel (BHARTI IN) – Tariff hikes on the way – BUY"),
                         ("Bharti Airtel", "Tariff hikes on the way"))
        self.assertEqual(rf.split_pl_title("India Strategy – Earnings season scorecard"), ("", ""))
        self.assertEqual(rf.split_pl_title("Titan Company (TTAN IN) – Q2FY27 Result Update – Strong growth outlook – Downgrade to ‘ACCUMULATE’"),
                         ("Titan Company", "Strong growth outlook"))

    def test_sbi_descriptions(self):
        self.assertEqual(rf.split_sbi_desc("Pick of the Day (Short Term Delivery Call)_ITC Hotels Ltd."),
                         ("ITC Hotels", "Pick of the Day (short-term delivery call)"))
        self.assertEqual(rf.split_sbi_desc("Pick of the week_NSE Ltd"), ("NSE", "Pick of the Week"))
        self.assertEqual(rf.split_sbi_desc("IPO Note-01-03-2023_Acme Ltd"), ("Acme", "IPO note"))
        self.assertEqual(rf.split_sbi_desc("Acme Solar Holdings Ltd IPO Note"), ("Acme Solar Holdings", "IPO note"))
        self.assertEqual(rf.split_sbi_desc("Weekly Report"), ("", ""))

    def test_choice_headline(self):
        self.assertEqual(rf.choice_headline("Core MarTech Growth Sustains; H2 Recovery in Focus\r\n\r\nRATEGAIN reported…"),
                         "Core MarTech Growth Sustains; H2 Recovery in Focus")
        long = ("Strong execution despite cost pressures; capacity expansion underpins growth: "
                "M&M delivered a solid Q2FY27, with consolidated revenue and PAT increasing sharply")
        self.assertEqual(rf.choice_headline(long),
                         "Strong execution despite cost pressures; capacity expansion underpins growth")
        self.assertEqual(rf.choice_headline(""), "")

    def test_way2wealth_captions(self):
        self.assertEqual(rf.split_w2w_caption("J K Cement Ltd. -  Result Update  –  09 November 2026"), ("J K Cement", "Result Update"))
        self.assertEqual(rf.split_w2w_caption("IDFC First Bank Ltd.-  Light House Update  – 29 October 2026"),
                         ("IDFC First Bank", "Light House Update"))
        self.assertEqual(rf.split_w2w_caption("National Stock Exchange of India Ltd. (NSE Ltd.) -  Result Update  – 09 November 2026")[0],
                         "National Stock Exchange of India")
        self.assertEqual(rf.split_w2w_caption("Diwali Picks - 2026 - 03 November 2026"), ("", ""))
        self.assertEqual(rf.split_w2w_caption("RBI Monetary Policy - Event Update - 07 October 2026"), ("", ""))

    def test_report_type_titles_for_brokers_without_headlines(self):
        self.assertEqual(rf.report_label("639159344546009946_ONGC Q4FY26 result update.pdf", "Result Update"), "Q4FY26 Result Update")
        self.assertEqual(rf.report_label("637777469508275819_Infosys Ltd - Q3FY22.pdf", "Result Update"), "Q3FY22 Result Update")
        self.assertEqual(rf.report_label("Aarti_Ind_One_Pager_Q2_FY_27_Result_Update_1d91911ca6.pdf", "Update"), "Q2FY27 Result Update")
        self.assertEqual(rf.report_label("ABB_One_Pager_Q2_CY_26_Update_56ac8d1eb7.pdf", "Update"), "Q2CY26 Update")
        self.assertEqual(rf.report_label("Light House Update", "Update"), "Light House Update")

    def test_icici_headline_is_the_line_after_the_date(self):
        page = ("x\nVenus Pipes and Tubes (VENPIP)\nCMP: ₹1,740\nTarget ₹ 2,340 (35%)\nBUY\nNovember 6, 2026\n"
                "Muted quarterly results , guides for strong H2’FY27\n…\n: Venus Pipes and Tubes (VPT), established in 2015")
        self.assertEqual(rf.icici_headline(page), "Muted quarterly results, guides for strong H2’FY27")
        self.assertEqual(rf.icici_headline("no date here\nat all"), "")

    def test_company_tidy_and_dates(self):
        self.assertEqual(rf._tidy_company("MAHINDRA & MAHINDRA LTD"), "Mahindra & Mahindra")
        self.assertEqual(rf._tidy_company("HDFC BANK LIMITED"), "HDFC Bank")
        self.assertEqual(rf._tidy_company("Aarti Industries (ARTO) "), "Aarti Industries")
        self.assertEqual(rf._first_date_in("Result Update | November 10, 2026 | CMP").date().isoformat(), "2026-11-10")
        self.assertEqual(rf._first_date_in("ABSL AMC One Pager Result Update 22 October 2026 5c08").date().isoformat(), "2026-10-22")
        self.assertIsNone(rf._first_date_in("Aarti Ind One Pager Q2 FY 27 Result Update"))

    def test_house_spelling_from_archive(self):
        spellings = rf.archive_spellings([
            {"company": "ICICI Bank", "via": "Moneycontrol"}, {"company": "ICICI Bank", "via": "Business Standard"},
            {"company": "Icici Bank", "via": "Moneycontrol"}, {"company": "CIPLA", "via": "Moneycontrol"},
            {"company": "Cipla", "via": ""}])
        self.assertEqual(spellings, {"icici bank": "ICICI Bank"})
        cfg = {"_known": set(), "_spellings": spellings}
        self.assertEqual(rf._house_spelling("Icici Bank", cfg), "ICICI Bank")
        self.assertEqual(rf._house_spelling("Somany Ceramics", cfg), "Somany Ceramics")


class TestDedupWithDirectSites(unittest.TestCase):
    def test_direct_link_replaces_middleman_and_keeps_its_headline(self):
        mc = _note("Prabhudas Lilladher", "Safari Industries", 1, "Moneycontrol", 2400.0, "Read from the PDF")
        pl = _note("Prabhudas Lilladher", "Safari Industries (India)", 0, "")
        out = dedup_stock_notes([mc, pl])
        self.assertEqual([o["link"] for o in out], [pl["link"]])
        self.assertEqual(out[0]["headline"], "Read from the PDF")

    def test_targetless_match_needs_the_second_word(self):
        mc = _note("Kotak Securities", "Mahindra Lifespace", 0, "Moneycontrol", 600.0)
        direct = _note("Kotak Securities", "Mahindra Logistics", 0, "")
        self.assertEqual(len(dedup_stock_notes([mc, direct])), 2)
        short = _note("Kotak Securities", "Aarti Ind", 1, "")
        full = _note("Kotak Securities", "Aarti Industries", 0, "Business Standard", 450.0)
        self.assertEqual(len(dedup_stock_notes([full, short])), 1)

    def test_two_direct_reports_on_one_stock_both_stay(self):
        a = _note("HDFC Securities", "Dabur India", 1, "", headline="New leadership needs to anchor growth")
        b = _note("HDFC Securities", "Dabur India", 0, "", headline="Clear strategic roadmap")
        self.assertEqual(len(dedup_stock_notes([a, b])), 2)

    def test_different_targets_are_different_calls_even_with_a_direct_copy(self):
        a = _note("ICICI Securities", "Titan Company", 0, "", 5800.0)
        b = _note("ICICI Securities", "Titan Company", 1, "Moneycontrol", 4200.0)
        self.assertEqual(len(dedup_stock_notes([a, b])), 2)

    def test_archive_merge_swaps_in_direct_link_and_records_its_page(self):
        archive = [{"date": "2026-11-09", "broker": "Prabhudas Lilladher", "company": "Safari Industries",
                    "headline": "Claude read this", "link": "https://mc/safari.pdf", "via": "Moneycontrol",
                    "target": 2400.0, "headline_tries": 1}]
        art = rf._direct_note({"name": "PL", "url": "https://www.plindia.com/pl-research/", "publisher": "Prabhudas Lilladher",
                               "kind": STOCK_NOTE_KIND}, company="Safari Industries (India)", headline="",
                              dt=datetime(2026, 11, 11, 10, tzinfo=IST_TZ), pdf="https://plindia.com/ResReport/SII.pdf",
                              page="https://www.plindia.com/pl-research/safari/")
        out = merge_into_archive(archive, [art])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["link"], "https://plindia.com/ResReport/SII.pdf")
        self.assertEqual(out[0]["via"], "")
        self.assertEqual(out[0]["headline"], "Claude read this")
        self.assertEqual(out[0]["page"], "https://www.plindia.com/pl-research/safari/")
        self.assertIn("https://www.plindia.com/pl-research/safari/", known_note_keys(out))


_PL_LISTING = """
<a href="https://www.plindia.com/pl-research/known-one/" class="report-card-link"><h3>Ipca Laboratories (IPCA IN) &#8211; Q2FY27 Result Update &#8211; BUY</h3></a>
<a href="https://www.plindia.com/pl-research/new-one/" class="report-card-link"><h3>Safari Industries (India) (SII IN) &#8211; Q2FY27 Result Update &#8211; Capacity expansion &#8211; BUY</h3></a>
<a href="https://www.plindia.com/pl-research/strategy/" class="report-card-link"><h3>India Strategy &#8211; Scorecard</h3></a>
"""
_PL_REPORT = """{"datePublished":"2026-11-11T05:22:50+00:00"} <div class="research-cta">
<a class="btn" href="http://plindia.com/ResReport/SII-6-11-26-PL.pdf">Download Full Report</a></div>
<div class="other-reports"><a href="https://plindia.com/ResReport/IPCA-6-11-26-PL.pdf">x</a></div>"""


class TestFetchers(unittest.TestCase):
    def test_pl_skips_archived_pages_and_non_company_reports(self):
        fetched = []

        def fake_fetch(url, **kw):
            fetched.append(url)
            if url.endswith("/page/2/"):
                raise rf.urllib.error.HTTPError(url, 404, "nf", {}, None)
            return (_PL_REPORT if "new-one" in url else _PL_LISTING).encode()

        cfg = {"name": "PL", "url": "https://www.plindia.com/pl-research/", "publisher": "Prabhudas Lilladher",
               "kind": STOCK_NOTE_KIND, "max_age_days": 3650,
               "_known": {"https://www.plindia.com/pl-research/known-one/"}}
        with mock.patch.object(rf, "_fetch_url", side_effect=fake_fetch):
            out = rf.fetch_plindia(cfg)
        self.assertEqual(fetched, ["https://www.plindia.com/pl-research/",
                                   "https://www.plindia.com/pl-research/new-one/",
                                   "https://www.plindia.com/pl-research/page/2/"])
        self.assertEqual(len(out), 1)
        a = out[0]
        self.assertEqual((a["company"], a["headline"], a["via"]), ("Safari Industries (India)", "Capacity expansion", ""))
        self.assertEqual(a["link"], "https://plindia.com/ResReport/SII-6-11-26-PL.pdf")  # the report's own PDF, https
        self.assertEqual(a["page"], "https://www.plindia.com/pl-research/new-one/")
        self.assertEqual(a["date"].date().isoformat(), "2026-11-11")

    def test_icici_reads_target_and_date_and_skips_known(self):
        page = """
        <label>Target Price</label> <snap class="label_value"><span class="icon-rupee"></span>5,800.00</snap>
        <a href="https://mailcontent.icicidirect.com/mailcontent/idirect_titan_q2fy27.pdf" target="_blank" onclick="trackCustomEventVPV_researchEquity('investing_ideas_Titan Company Ltd', 'view_report')"> View Report </a>
        <label>Target Price</label> <snap class="label_value"><span class="icon-rupee"></span>1,000.00</snap>
        <a href="https://mailcontent.icicidirect.com/mailcontent/idirect_astral_q2fy27.pdf" target="_blank" onclick="trackCustomEventVPV_researchEquity('investing_ideas_Astral Ltd', 'view_report')"> View Report </a>
        """
        today = datetime.now(IST_TZ).strftime("%d %B %Y")
        cfg = {"name": "ICICI", "url": "https://www.icicidirect.com/research/equity", "publisher": "ICICI Securities",
               "kind": STOCK_NOTE_KIND, "_known": {"https://mailcontent.icicidirect.com/mailcontent/idirect_astral_q2fy27.pdf"}}
        with mock.patch.object(rf, "_fetch_url", return_value=page.encode()), \
                mock.patch.object(rf, "pdf_first_page_text", return_value=f"Titan Company\n{today}\nResult Update") as pdf:
            out = rf.fetch_icicidirect(cfg)
        self.assertEqual([(a["company"], a["target"]) for a in out], [("Titan Company", 5800.0)])
        self.assertEqual(pdf.call_count, 1)
        self.assertEqual(out[0]["publisher"], "ICICI Securities")


class TestRoundTwoBrokers(unittest.TestCase):
    def test_idbi_titles(self):
        self.assertEqual(rf.split_idbi_title("India Shelter Finance (INDIASHL): Q2FY27 Result Review"),
                         ("India Shelter Finance", "Q2FY27 Result Review"))
        self.assertEqual(rf.split_idbi_title("TECHNICAL PICK: CDSL"), ("", ""))
        self.assertEqual(rf.split_idbi_title("Strategy Capital Market - November 2026"), ("", ""))

    def test_mncl_page_one(self):
        page = ("Company Update\nINDIA l Institutional Research l Capital Goods l 3 November 2026\n"
                "Grindwell Norton (GNO) l BUY l TP: Rs 2,412 l Upside: 25%\n"
                "Ceramics Drives Growth; Abrasives Remain Resilient\nWe maintain our BUY rating on Grindwell Norton")
        dt, head = rf.mncl_page_one(page)
        self.assertEqual(dt.date().isoformat(), "2026-11-03")
        self.assertEqual(head, "Ceramics Drives Growth; Abrasives Remain Resilient")
        self.assertEqual(rf.mncl_page_one("scanned cover"), (None, ""))
        self.assertEqual(rf._tidy_company("J .G. Chemicals Ltd."), "J.G. Chemicals")

    def test_nirmal_bang_titles(self):
        self.assertEqual(rf.split_nb_title(
            "Fine Organic Industries (FINEORG) - BUY - Chemicals | 2QFY27 Result Update - Expansion plans to fructify from FY29 - 09 November 2026"),
            ("Fine Organic Industries", "Expansion plans to fructify from FY29"))
        self.assertEqual(rf.split_nb_title(
            "Gland Pharma (GLAND) - Pharmaceuticals | 2QFY27 Result update - CDMO engine firing, Cenexi still the swing factor; maintain HOLD - 09 November 2026"),
            ("Gland Pharma", "CDMO engine firing, Cenexi still the swing factor"))
        self.assertEqual(rf.split_nb_title("Linc Ltd. - BUY -  Stationery | 2QFY27 Result Update - Market-share Gains Take Priority - 08 November 2026"),
                         ("Linc", "Market-share Gains Take Priority"))
        self.assertEqual(rf.split_nb_title("Fortnightly Macro Tracker - India Economy | Update - Economic activity mixed - 10 Nov"), ("", ""))
        self.assertEqual(rf.split_nb_title("India Morning Roundup - 9 November 2026"), ("", ""))
        self.assertEqual(rf.split_nb_title("Gujarat State Petronet Ltd (GUJS)- Oil & Gas | 4QFY24 Result Update- Still awaiting clarity on what lies ahead"),
                         ("Gujarat State Petronet", "Still awaiting clarity on what lies ahead"))
        company, head = rf.split_nb_title("PVRINOX Ltd. (PVRINOX)- Film Exhibition | 2QFY26 Result Preview- A strong end to 1H with momentum to continue")
        self.assertEqual((company.lower(), head), ("pvrinox", "A strong end to 1H with momentum to continue"))
        self.assertEqual(rf.split_nb_title("Tiles Sector- 2QFY26 Result Preview- Q2FY26: Weak start"), ("", ""))
        self.assertEqual(rf.split_nb_title("Power Mech Projects- 4QFY23 Result Update- Strong quarter; Targeting order inflow of Rs100bn for FY24"),
                         ("Power Mech Projects", "Strong quarter; Targeting order inflow of Rs100bn for FY24"))
        self.assertEqual(rf.split_nb_title("Berger Paints India Ltd.- 3QFY21 Result Update- Strong broad-based performance; Maintain Sell"),
                         ("Berger Paints India", "Strong broad-based performance"))
        self.assertEqual(rf.split_nb_title("4QFY23/FY23 GDP Growth Review- Economy Update- 4QFY23 GDP at 6.1%"), ("", ""))
        self.assertEqual(rf.split_nb_title("India Morning Roundup-3 July 2023"), ("", ""))
        self.assertEqual(rf.split_nb_title("HCL Technologies (HCLT) - IT | 1QFY27 Result Update - 14 July 2026"),
                         ("HCL Technologies", "Q1FY27 Result Update"))
        self.assertEqual(rf.split_nb_title("State Bank of India (SBIN) - Banks | 1QFY27 Result Update - Broad-based performance; margins back on track. BUY. - 08 August 2026")[1],
                         "Broad-based performance; margins back on track")

    def test_mncl_certificate_is_bundled(self):
        self.assertTrue(rf.os.path.exists(rf._MNCL_CA))


class TestSectorReports(unittest.TestCase):
    def test_nirmal_bang_sector_titles(self):
        self.assertEqual(rf.nb_sector_title("Cement Channel Check – Oct ’26 - Sector Update - Cement Prices Recover - 29 October 2026"),
                         "Cement Channel Check – Oct ’26 - Sector Update - Cement Prices Recover")
        self.assertTrue(rf.nb_sector_title("RBI Sectoral Deployment - Banking | Sector Update - Robust broad-based credit momentum"))
        self.assertTrue(rf.nb_sector_title("India Capex Pipeline - India Economy | Thematic - A New Private Sector-Led Investment Cycle"))
        self.assertTrue(rf.nb_sector_title("Fortnightly Macro Tracker - India Economy | Update - Economic activity mixed"))
        for noise in ("India Morning Roundup - 9 November 2026", "NBIE AI Powered Insights- 11 Nov 2026",
                      "Fine Organic Industries (FINEORG) - BUY - Chemicals | 2QFY27 Result Update - Expansion plans"):
            self.assertEqual(rf.nb_sector_title(noise), "", noise)
        # a single-stock note with "Sector" in it stays a stock note
        self.assertEqual(rf.split_nb_title("Bata India Ltd. (BIL) - Retail Sector | 2QFY27 Result Update - ASP-led recovery")[0], "Bata India")

    def test_sbi_thematic_split(self):
        self.assertEqual(rf.split_sbi_thematic("Carysil Ltd._2QFY27 Result Update"), ("stock", "Carysil", "Q2FY27 Result Update"))
        self.assertEqual(rf.split_sbi_thematic("JTL Industries Ltd-IC"), ("stock", "JTL Industries", "Initiating Coverage"))
        self.assertEqual(rf.split_sbi_thematic("Manorama Industries Ltd_Plant Visit Note"), ("stock", "Manorama Industries", "Plant Visit Note"))
        self.assertEqual(rf.split_sbi_thematic("SBICAP Securities - Metal Pulse Nov'26"), ("sector", "Metal Pulse Nov'26"))
        self.assertEqual(rf.split_sbi_thematic("Thematic Report_Rockstars of 1QFY27 Result")[0], "sector")
        self.assertEqual(rf.split_sbi_thematic("Macro Trends_Monthly Economic Report_Oct'26"),
                         ("sector", "Macro Trends – Monthly Economic Report – Oct'26"))
        self.assertEqual(rf.split_sbi_thematic("RBI MPC Meeting Oct'26")[0], "sector")
        self.assertEqual(rf.split_sbi_thematic("SBI Securities Diwali Muhurat Picks_2026"), ("skip",))


class TestHdfcAxisSectorSplit(unittest.TestCase):
    def test_hdfc(self):
        for t in ("IT Sector: PERM freeze: another blow, minimal impact", "NBFCs: Growth uptick, diminishing growth arbitrage",
                  "Healthcare Services: Supreme court slams drug markups", "Bharat Barometer (Sep’26)",
                  "Chemicals (Q2FY27 Results Preview): Cost pressures will outpace realization gains", "Capex Tracker: Q2FY27"):
            self.assertTrue(rf.is_hdfc_sector(t), t)
        for t in ("Dabur India: Clear strategic roadmap, execution key to rerating. Maintain ADD",
                  "HSIE Results Daily: Go Digit General Insurance, Data Patterns", "Bikaji Foods International: H2 uplift key"):
            self.assertFalse(rf.is_hdfc_sector(t), t)

    def test_axis(self):
        self.assertEqual(rf.classify_axis("Sector Update: BFSI - Insurance"), "sector")
        self.assertEqual(rf.classify_axis("Automobile - Q2FY27E: Result Preview"), "sector")
        self.assertEqual(rf.classify_axis("Auto Monthly Sales Volume - October 2026"), "sector")
        self.assertEqual(rf.classify_axis("Event Update:RBI Monetary Policy - October 2026"), "sector")
        self.assertEqual(rf.classify_axis("Result Update:Britannia Inds."), "stock")
        self.assertEqual(rf.classify_axis("Daily Fundamental View:November 11, 2026"), "stock")
        self.assertEqual(rf.classify_axis("High Conviction Ideas:Cement"), "skip")
        self.assertEqual(rf.classify_axis("Axis Top Picks for the month of November 2026"), "skip")

    def test_feed_decides_which_half(self):
        self.assertTrue(rf._wants_sector({"feed": "axis:sector"}))
        self.assertFalse(rf._wants_sector({"feed": "axis:research"}))


if __name__ == "__main__":
    unittest.main()
