"""Stock-notes archive (static/stock_notes.json) and PDF-headline filling."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from articles import IST_TZ
from stock_notes import (
    STOCK_NOTE_KIND,
    clean_headline,
    fill_headlines,
    load_archive,
    merge_into_archive,
    save_archive,
)


def _article(broker, company, target, days_ago, via, link, prev=None):
    """A fetched stock note, as reports_fetcher builds it."""
    return {
        "kind": STOCK_NOTE_KIND, "publisher": broker, "company": company, "target": target,
        "date": datetime.now(IST_TZ) - timedelta(days=days_ago), "via": via, "link": link,
        "prev_target": prev, "title": f"{company}: Buy",
    }


def _entry(link, days_ago=0, headline="", tries=0, company="Infosys", broker="Emkay Global", target=1300.0):
    return {
        "date": (datetime.now(IST_TZ) - timedelta(days=days_ago)).date().isoformat(),
        "broker": broker, "company": company, "headline": headline, "link": link,
        "via": "Moneycontrol", "target": target, "headline_tries": tries,
    }


class TestMerge(unittest.TestCase):
    def test_new_notes_are_added_in_archive_shape_newest_first(self):
        out = merge_into_archive([], [
            _article("Emkay Global", "Infosys", 1300.0, 3, "Moneycontrol", "https://mc/a.pdf"),
            _article("JM Financial", "Trent", 3000.0, 1, "Business Standard", "https://bs/b.pdf"),
        ])
        self.assertEqual([e["link"] for e in out], ["https://bs/b.pdf", "https://mc/a.pdf"])
        e = out[1]
        self.assertEqual(set(e), {"date", "broker", "company", "headline", "link", "via", "target", "headline_tries", "ts"})
        self.assertEqual(e["broker"], "Emkay Global")
        self.assertEqual(e["headline"], "")
        self.assertEqual(e["date"], (datetime.now(IST_TZ) - timedelta(days=3)).date().isoformat())

    def test_known_links_keep_their_headline(self):
        archive = [_entry("https://mc/a.pdf", headline="Deal wins drive the beat", tries=1)]
        out = merge_into_archive(archive, [_article("Emkay Global", "Infosys", 1300.0, 0, "Moneycontrol", "https://mc/a.pdf")])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["headline"], "Deal wins drive the beat")

    def test_cross_site_repeat_of_an_archived_call_is_not_added(self):
        archive = [_entry("https://mc/a.pdf", days_ago=2, headline="Deal wins drive the beat")]
        bs_copy = _article("Emkay Global", "Infosys Ltd", 1300.0, 0, "Business Standard", "https://bs/x.pdf")
        out = merge_into_archive(archive, [bs_copy])
        self.assertEqual([e["link"] for e in out], ["https://mc/a.pdf"])

    def test_mc_listing_wins_over_bs_copy_when_both_are_new(self):
        mc = _article("Motilal Oswal", "Jubilant Foodworks", 625.0, 2, "Moneycontrol", "https://mc/j.pdf", prev=600.0)
        bs = _article("Motilal Oswal", "Jubilant FoodWorks", 625.0, 0, "Business Standard", "https://bs/j.pdf")
        out = merge_into_archive([], [bs, mc])
        self.assertEqual([e["link"] for e in out], ["https://mc/j.pdf"])


class TestSaveLoad(unittest.TestCase):
    def test_round_trip_is_stable_one_note_per_line(self):
        items = [_entry("https://mc/b.pdf", 1), _entry("https://mc/a.pdf", 0, headline="Beat")]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "stock_notes.json")
            save_archive(path, items)
            first = open(path, encoding="utf-8").read()
            self.assertEqual(len(first.strip().splitlines()), 4)  # [ + 2 notes + ]
            self.assertEqual(json.loads(first)[0]["link"], "https://mc/a.pdf")  # newest first
            save_archive(path, load_archive(path))
            self.assertEqual(open(path, encoding="utf-8").read(), first)

    def test_missing_or_broken_file_loads_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load_archive(os.path.join(d, "nope.json")), [])
            bad = os.path.join(d, "bad.json")
            open(bad, "w").write("{oops")
            self.assertEqual(load_archive(bad), [])


class TestCleanHeadline(unittest.TestCase):
    def test_cleanup(self):
        self.assertEqual(clean_headline('  "Production drag  persists"  ', "ONGC"), "Production drag persists")
        self.assertEqual(clean_headline("Infosys", "Infosys"), "")
        self.assertEqual(clean_headline("", "Infosys"), "")
        self.assertEqual(clean_headline("x" * 300, "Infosys"), "")


class TestFillHeadlines(unittest.TestCase):
    def test_fills_newest_first_and_counts_tries(self):
        items = [
            _entry("https://mc/old.pdf", days_ago=5),
            _entry("https://mc/new.pdf", days_ago=0, company="Trent"),
            _entry("https://mc/done.pdf", days_ago=1, headline="Already there"),
            _entry("https://mc/gaveup.pdf", days_ago=0, tries=2),
            _entry("https://mc/broken.pdf", days_ago=0),
        ]
        texts = {"https://mc/new.pdf": "Trent page one", "https://mc/old.pdf": "Infosys page one"}

        def fake_text(link):
            if link not in texts:
                raise OSError("404")
            return texts[link]

        asked = []

        def fake_ask(batch):
            asked.append([b["link"] for b in batch])
            return {b["link"]: ("Zudio keeps compounding" if b["company"] == "Trent" else "") for b in batch}

        filled = fill_headlines(items, limit=10, pdf_text=fake_text, ask_model=fake_ask, workers=2, batch_size=8)
        by = {e["link"]: e for e in items}
        self.assertEqual(filled, 1)
        self.assertEqual(by["https://mc/new.pdf"]["headline"], "Zudio keeps compounding")
        self.assertEqual(by["https://mc/old.pdf"]["headline"], "")
        self.assertEqual(by["https://mc/old.pdf"]["headline_tries"], 1)      # model found none
        self.assertEqual(by["https://mc/broken.pdf"]["headline_tries"], 1)   # download failed
        self.assertEqual(by["https://mc/gaveup.pdf"]["headline_tries"], 2)   # not retried
        self.assertEqual(by["https://mc/done.pdf"]["headline"], "Already there")
        self.assertEqual(asked, [["https://mc/new.pdf", "https://mc/old.pdf"]])  # newest first, one batch

    def test_limit_and_model_failure_leave_items_retryable(self):
        items = [_entry(f"https://mc/{i}.pdf", days_ago=i) for i in range(5)]

        def boom(batch):
            raise RuntimeError("All Gemini models failed")

        filled = fill_headlines(items, limit=2, pdf_text=lambda link: "text", ask_model=boom, workers=1)
        self.assertEqual(filled, 0)
        # A model outage is not the PDF's fault: no try is burned.
        self.assertEqual([e["headline_tries"] for e in items], [0, 0, 0, 0, 0])


if __name__ == "__main__":
    unittest.main()


class TestBrokerSiteReports(unittest.TestCase):
    """Axis Direct, Baroda eTrade, HDFC Securities: report titles, no company field."""

    def _report(self, title, publisher, link):
        return {"kind": STOCK_NOTE_KIND, "publisher": publisher, "title": title, "link": link,
                "date": datetime.now(IST_TZ), "via": ""}

    def test_titles_map_to_company_and_headline(self):
        out = merge_into_archive([], [
            self._report("Honasa Consumer: Healthy Q2 delivery, execution continues to aid. Maintain BUY",
                         "HDFC Securities", "https://hdfc/1.pdf"),
            self._report("Result Update:Britannia Inds.", "Axis Direct", "https://axis/2.pdf"),
            self._report("First Light | ACC, Equitas Small Finance Bank, Hero Motocorp", "Baroda eTrade", "https://bob/3.pdf"),
            self._report("HSIE Results Daily: ONGC, LG Electronics India", "HDFC Securities", "https://hdfc/4.pdf"),
        ])
        by = {e["link"]: e for e in out}
        self.assertEqual((by["https://hdfc/1.pdf"]["company"], by["https://hdfc/1.pdf"]["headline"]),
                         ("Honasa Consumer", "Healthy Q2 delivery, execution continues to aid. Maintain BUY"))
        # Axis gives the company only; the PDF headline is filled later
        self.assertEqual((by["https://axis/2.pdf"]["company"], by["https://axis/2.pdf"]["headline"]), ("Britannia Inds.", ""))
        # Multi-stock dailies keep their own title as the headline
        self.assertEqual((by["https://bob/3.pdf"]["company"], by["https://bob/3.pdf"]["headline"]),
                         ("", "First Light | ACC, Equitas Small Finance Bank, Hero Motocorp"))
        self.assertEqual((by["https://hdfc/4.pdf"]["company"], by["https://hdfc/4.pdf"]["headline"]),
                         ("", "HSIE Results Daily: ONGC, LG Electronics India"))
        self.assertEqual(by["https://axis/2.pdf"]["broker"], "Axis Direct")

    def test_report_items_carry_kind_from_feed(self):
        from reports_fetcher import _make_article
        cfg = {"name": "Axis Direct — Research", "url": "https://axis", "id": "axis-direct-research",
               "publisher": "Axis Direct", "kind": "stock_note"}
        self.assertEqual(_make_article("t", "https://x", None, "", cfg)["kind"], STOCK_NOTE_KIND)
        self.assertEqual(_make_article("t", "https://x", None, "", {"name": "n", "url": "u"})["kind"], "")


class TestHomeSelection(unittest.TestCase):
    def test_newest_single_company_notes_as_cards(self):
        from stock_notes import select_home_notes
        entries = [
            _entry("https://a", 0, headline="Beat on all fronts", company="Honasa Consumer"),
            _entry("https://b", 0, headline="First Light | ACC, Hero", company=""),   # multi-stock daily
            _entry("https://c", 1, company="Trent"),                                   # headline not read yet
            _entry("https://d", 2, headline="Old one", company="ITC"),
        ]
        got = select_home_notes(entries, limit=2)
        self.assertEqual([g["link"] for g in got], ["https://a", "https://c"])
        self.assertEqual(got[0]["title"], "Honasa Consumer — Beat on all fronts")
        self.assertEqual(got[1]["title"], "Trent")
        self.assertEqual(got[0]["publisher"], "Emkay Global")
        self.assertTrue(got[0]["date"].endswith("T00:00:00+05:30"))


class TestHeadlineMinDate(unittest.TestCase):
    def test_min_date_leaves_older_notes_alone(self):
        items = [_entry("https://new", days_ago=1), _entry("https://old", days_ago=60)]
        asked = []
        fill_headlines(items, limit=10, min_date=(datetime.now(IST_TZ) - timedelta(days=30)).date().isoformat(),
                       pdf_text=lambda link: "page", ask_model=lambda b: (asked.extend(x["link"] for x in b) or {x["link"]: "A headline" for x in b}))
        self.assertEqual(asked, ["https://new"])
        self.assertEqual([e["headline"] for e in items], ["A headline", ""])


class TestHistoryFloorAndBrowserChunks(unittest.TestCase):
    def test_notes_older_than_five_years_are_dropped(self):
        from datetime import date
        from stock_notes import min_note_date
        self.assertEqual(min_note_date(date(2026, 11, 11)), "2021-11-11")
        self.assertEqual(min_note_date(date(2028, 2, 29)), "2023-02-28")
        too_old = (datetime.now(IST_TZ) - timedelta(days=5 * 366)).date().isoformat()
        old = {"date": too_old, "broker": "Way2Wealth", "company": "Cipla", "headline": "", "link": "https://w/old.pdf",
               "via": "", "target": None, "headline_tries": 0}
        art = _article("Emkay Global", "Infosys", 1300.0, 0, "Moneycontrol", "https://mc/a.pdf")
        ancient = {**art, "link": "https://w/2016.pdf", "date": datetime(2016, 5, 1, tzinfo=IST_TZ)}
        out = merge_into_archive([old], [art, ancient])
        self.assertEqual([e["link"] for e in out], ["https://mc/a.pdf"])

    def test_chunks_recent_first_then_one_file_per_year(self):
        from stock_notes import write_note_chunks
        entries = [_entry(f"https://n/{i}", days_ago=i * 200, company=f"Co{i}", broker=b)
                   for i, b in enumerate(["Emkay Global", "Way2Wealth", "Emkay Global", "Ventura Securities"])]
        with tempfile.TemporaryDirectory() as d:
            written = write_note_chunks(entries, out_dir=d, recent=2)
            recent = json.load(open(os.path.join(d, "recent.json")))
            self.assertEqual([n["link"] for n in recent["notes"]], ["https://n/0", "https://n/1"])
            self.assertEqual(set(recent["notes"][0]), {"date", "broker", "company", "headline", "link", "via"})
            self.assertEqual(recent["brokers"], ["Emkay Global", "Ventura Securities", "Way2Wealth"])
            years = recent["years"]
            self.assertEqual(years, sorted(years, reverse=True))
            self.assertEqual(sum(len(json.load(open(os.path.join(d, f"{y}.json")))) for y in years), 4)
            self.assertIn("recent.json", written)
            self.assertEqual(write_note_chunks(entries, out_dir=d, recent=2), [])  # unchanged → nothing rewritten


class TestLatestFirst(unittest.TestCase):
    def test_note_time_from_source_link_or_first_seen(self):
        from stock_notes import note_time
        self.assertEqual(note_time("https://images.moneycontrol.com/x/2026/11/20261109080824_Mphasis.pdf"), "2026-11-09T08:08")
        self.assertEqual(note_time("https://www.hdfcsec.com/hsl.docs/Dabur - Q2FY27 - HSIE-202611050746138922064.pdf"), "2026-11-05T07:46")
        self.assertEqual(note_time("https://ventura1.com/q/639298433316872389_HCC Result Update Q2FY27.pdf")[:10], "2026-11-09")
        self.assertEqual(note_time("https://pl/x.pdf", datetime(2026, 11, 11, 10, 52, tzinfo=IST_TZ)), "2026-11-11T10:52")
        seen = datetime(2026, 11, 11, 14, 5, tzinfo=IST_TZ)
        self.assertEqual(note_time("https://w2w/RR1.pdf", datetime(2026, 11, 9, tzinfo=IST_TZ), now=seen), "2026-11-11T14:05")

    def test_day_then_company_so_one_stocks_notes_sit_together(self):
        from stock_notes import sort_notes
        notes = [
            {"date": "2026-11-11", "broker": "Ventura Securities", "company": "Titan Company", "link": "1", "ts": "2026-11-11T16:00"},
            {"date": "2026-11-11", "broker": "Prabhudas Lilladher", "company": "Mahindra & Mahindra", "link": "2", "ts": "2026-11-11T09:30"},
            {"date": "2026-11-11", "broker": "HDFC Securities", "company": "", "link": "3", "headline": "HSIE Results Daily: …"},
            {"date": "2026-11-11", "broker": "Choice Broking", "company": "Mahindra and Mahindra Ltd", "link": "4", "ts": "2026-11-11T12:00"},
            {"date": "2026-11-11", "broker": "Way2Wealth", "company": "Astral", "link": "5"},
            {"date": "2026-11-11", "broker": "Kotak Securities", "company": "Mahindra & Mahindra", "link": "6"},
            {"date": "2026-11-12", "broker": "Zed", "company": "Zomato", "link": "7"},
        ]
        # 12 Nov first; then 11 Nov: Astral, the three M&M notes (latest first, untimed last), Titan, the daily
        self.assertEqual([n["link"] for n in sort_notes(notes)], ["7", "5", "4", "2", "6", "1", "3"])

class TestRuleHeadlines(unittest.TestCase):
    """Page-1 layout rules (no AI) for ICICI Securities and Motilal Oswal."""

    def test_icici_securities_headline_follows_company_and_sector(self):
        from stock_notes import rule_headline
        lines = [(17.5, 18, "BUY (Maintain)"), (9, 60, "11 November 2026"),
                 (9, 70, "India | Equity Research | Results Update"), (17.5, 100, "Motilal Oswal Financial Services"),
                 (9, 120, "Exchanges"), (15.1, 149, "Excess inventory likely to weigh on rest of FY26; Downgrade to HOLD"),
                 (9, 170, "Voltas’ Q1FY26 performance was weighed down by softer summer product sales"),
                 (9, 180, "body"), (9, 190, "body"), (9, 200, "body")]
        self.assertEqual(rule_headline("ICICI Securities", lines, "Voltas"),
                         "Excess inventory likely to weigh on rest of FY26; Downgrade to HOLD")

    def test_motilal_takes_largest_line_that_is_not_a_name_or_price(self):
        from stock_notes import rule_headline
        lines = [(26.0, 58, "Fujiyama Power Systems"), (14.0, 98, "TP: INR500 (+40%)"),
                 (14.0, 118, "Strong volume-led growth supported by"), (14.0, 134, "channel expansion"),
                 (11.0, 300, "Investors are advised to refer through important disclosures")]
        self.assertEqual(rule_headline("Motilal Oswal", lines, "Fujiyama Power Systems"),
                         "Strong volume-led growth supported by channel expansion")
        self.assertEqual(rule_headline("Emkay Global", lines, "X"), "")  # no rule → no guess

    def test_fill_only_touches_rule_brokers(self):
        from stock_notes import rule_headlines
        items = [_entry("https://mc/mo.pdf", broker="Motilal Oswal", company="Aarti Industries"),
                 _entry("https://mc/em.pdf", broker="Emkay Global")]
        page = [(26.0, 73, "Aarti Industries"), (24.0, 717, "Fuel additives lead; core chemistry gains momentum")]
        fill_headlines(items, limit=10, pdf_text=lambda link: page, ask_model=rule_headlines,
                       brokers=("ICICI Securities", "Motilal Oswal"))
        self.assertEqual([e["headline"] for e in items], ["Fuel additives lead; core chemistry gains momentum", ""])
        self.assertEqual(items[1]["headline_tries"], 0)
