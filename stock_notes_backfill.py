"""One-off (re-runnable) backfill for Reports → Stock notes.

    python3 stock_notes_backfill.py                 # full history + headlines
    python3 stock_notes_backfill.py --headlines-only --limit 2000
    python3 stock_notes_backfill.py --no-headlines  # history only (no Gemini key needed)
    python3 stock_notes_backfill.py --no-headlines --direct                 # brokers' own sites, all history
    python3 stock_notes_backfill.py --no-headlines --direct ventura-research  # just one

1. Pages through every note Moneycontrol still lists (back to Jan 2024)
   and Business Standard's whole list (back to Nov 2024), and merges them
   into static/stock_notes.json. The hourly run only fetches 14 days.
2. Fills PDF headlines, newest first, saving after every chunk — stop it
   any time and re-run to resume. Needs GEMINI_API_KEY and pdftotext.

Downloads one PDF per note (~600 KB each, ~6 GB for the full history);
nothing is kept on disk.
"""

import argparse
import json
import os
import shutil
import sys
import time

from reports_fetcher import fetch_bs_research, fetch_moneycontrol_ideas, get_report_fetcher
from stock_notes import ARCHIVE_FILE, fill_headlines, load_archive, merge_into_archive, save_archive, write_note_chunks

HERE = os.path.dirname(os.path.abspath(__file__))


def _feed(feed_id):
    with open(os.path.join(HERE, "feeds.json"), encoding="utf-8") as f:
        return next(x for x in json.load(f) if x["id"] == feed_id)


from datetime import date
from stock_notes import min_note_date
# Back to the start of the rolling window (5 years) and no further.
EVERYTHING = {"max_age_days": (date.today() - date.fromisoformat(min_note_date())).days + 1, "max_items": 100000}

# Brokers' own sites: how deep each one's history goes (pages / per-report lookups).
DIRECT_HISTORY = {
    "plindia-research": {"max_pages": 120, "max_lookups": 10000, "polite": 0.3},  # ~2.6k reports, one page each
    "icicidirect-ideas": {},                                                       # only the latest ~15 are listed
    "kotak-opportune": {"max_lookups": 300, "polite": 0.2},
    "sbisec-research": {},                                                         # the API returns everything
    "choice-research": {"max_pages": 20},
    "way2wealth-research": {"max_pages": 150, "polite": 0.3},
    "ventura-research": {"max_pages": 300, "polite": 0.3},
    "idbi-capital-research": {"max_pages": 200, "polite": 0.3},
    "mncl-research": {"max_lookups": 1000, "polite": 0.2},  # one PDF page-1 read per note
    "nirmal-bang-research": {"max_pages": 700, "polite": 0.3},
}


def fetch_history():
    mc = fetch_moneycontrol_ideas({**_feed("moneycontrol-stock-ideas"), **EVERYTHING, "max_pages": 200})
    bs = fetch_bs_research({**_feed("business-standard-research"), **EVERYTHING})
    return mc + bs


def fetch_direct_history(only=None):
    out = []
    for feed_id, extra in DIRECT_HISTORY.items():
        if only and feed_id not in only:
            continue
        feed = _feed(feed_id)
        out += get_report_fetcher(feed["feed"])({**feed, **EVERYTHING, **extra})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--headlines-only", action="store_true", help="skip the history fetch")
    ap.add_argument("--no-headlines", action="store_true", help="only fetch the history")
    ap.add_argument("--limit", type=int, default=100000, help="max headlines to try this run")
    ap.add_argument("--workers", type=int, default=6, help="parallel PDF downloads / Gemini calls")
    ap.add_argument("--direct", nargs="*", metavar="FEED_ID",
                    help="fetch brokers' own sites instead of Moneycontrol/BS (all, or the feed ids given)")
    args = ap.parse_args()

    archive = load_archive(ARCHIVE_FILE)
    print(f"archive: {len(archive)} notes")
    if not args.headlines_only:
        before = len(archive)
        fetched = fetch_direct_history(args.direct) if args.direct is not None else fetch_history()
        archive = merge_into_archive(archive, fetched)
        save_archive(ARCHIVE_FILE, archive)
        write_note_chunks(archive)
        print(f"history merged: {len(archive)} notes (+{len(archive) - before})")

    if args.no_headlines:
        return
    if not os.environ.get("GEMINI_API_KEY") or not shutil.which("pdftotext"):
        sys.exit("headlines need GEMINI_API_KEY and pdftotext (poppler-utils)")

    started = time.monotonic()
    chunk = args.workers * 8 * 5  # save roughly every 5 rounds
    total_filled = 0
    remaining = args.limit
    while remaining > 0:
        filled_before = sum(1 for e in archive if e.get("headline"))
        n = fill_headlines(archive, limit=min(chunk, remaining), workers=args.workers, batch_size=8)
        save_archive(ARCHIVE_FILE, archive)
        total_filled += n
        pending = sum(1 for e in archive if not e.get("headline") and e.get("headline_tries", 0) < 2)
        done = filled_before + n
        mins = (time.monotonic() - started) / 60
        print(f"  {done}/{len(archive)} have headlines · {pending} pending · {mins:.1f} min", flush=True)
        remaining -= chunk
        if pending == 0:
            break
    print(f"done: {total_filled} headlines filled this run")


if __name__ == "__main__":
    main()
