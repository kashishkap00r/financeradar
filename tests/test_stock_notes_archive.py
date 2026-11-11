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
        self.assertEqual(set(e), {"date", "broker", "company", "headline", "link", "via", "target", "headline_tries"})
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
    def test_notes_before_2020_are_dropped(self):
        from stock_notes import MIN_NOTE_DATE
        old = {"date": "2019-12-31", "broker": "Way2Wealth", "company": "Cipla", "headline": "", "link": "https://w/old.pdf",
               "via": "", "target": None, "headline_tries": 0}
        art = _article("Emkay Global", "Infosys", 1300.0, 0, "Moneycontrol", "https://mc/a.pdf")
        ancient = {**art, "link": "https://w/2016.pdf", "date": datetime(2016, 5, 1, tzinfo=IST_TZ)}
        out = merge_into_archive([old], [art, ancient])
        self.assertEqual([e["link"] for e in out], ["https://mc/a.pdf"])
        self.assertEqual(MIN_NOTE_DATE, "2020-01-01")

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
