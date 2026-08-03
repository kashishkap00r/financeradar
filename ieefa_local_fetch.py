#!/usr/bin/env python3
"""
Local IEEFA backfill using Playwright.

The pipeline reads IEEFA from static/ieefa_cache.json, which reports_fetcher.py
tops up hourly from ieefa.org/rss.xml. That firehose only carries the 10 newest
sitewide items (~3 days), so it fills the 30-day Reports window gradually.

This script fills the window immediately: ieefa.org/research-hub is behind a
Cloudflare JS challenge, so it needs a real browser. Run it once to seed the
cache, and any time you want to backfill after a gap.

IEEFA guards the hub with an *interactive* Cloudflare Turnstile ("Verify you
are human"), not the passive interstitial PIIE uses — so a headless run cannot
clear it. The browser opens visibly and waits for you to tick the box the first
time. Clearance is stored in a persistent Chrome profile, so later runs
normally sail straight through.

Usage:
    python3 ieefa_local_fetch.py                # fetch + merge into cache
    python3 ieefa_local_fetch.py --pages 5      # go deeper than the default 3
    python3 ieefa_local_fetch.py --push         # fetch + merge + git commit & push

Requires: playwright (pip install playwright && playwright install)
"""

import argparse
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(SCRIPT_DIR, "static", "ieefa_cache.json")

# Persisted outside the repo so the Cloudflare clearance cookie survives runs.
PROFILE_DIR = os.path.expanduser("~/.cache/financeradar-ieefa-profile")

# Keep in step with _IEEFA_CACHE_WINDOW_DAYS in reports_fetcher.py
CACHE_WINDOW_DAYS = 35

# The research hub's "Type" filter is a taxonomy facet: tid_1[6]=6 is Report,
# tid_1[583]=583 is Insights. Both map to one feed each in feeds.json.
IEEFA_SECTIONS = [
    {
        "id": "ieefa-reports",
        "name": "IEEFA — Reports",
        "url": "https://ieefa.org/research-hub?keys=&tid_1%5B6%5D=6",
    },
    {
        "id": "ieefa-insights",
        "name": "IEEFA — Insights",
        "url": "https://ieefa.org/research-hub?keys=&tid_1%5B583%5D=583",
    },
]

EXTRACT_CARDS_JS = """() => {
    const out = [];
    document.querySelectorAll('a.card').forEach(card => {
        const href = card.getAttribute('href') || '';
        const title = (card.querySelector('.card-title')?.textContent || '').trim();
        const date = (card.querySelector('.card-tags .tags')?.textContent || '').trim();
        const type = (card.querySelector('.type')?.textContent || '').trim();
        if (!href || !title) return;
        out.push({
            title: title.replace(/\\s+/g, ' '),
            link: href.startsWith('http') ? href : 'https://ieefa.org' + href,
            date_text: date,
            type: type,
        });
    });
    return out;
}"""


def parse_date(date_str):
    """Parse the research hub's 'August 03, 2026' card date."""
    date_str = (date_str or "").strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %Y"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _blocked(page):
    title = page.title()
    return "Just a moment" in title or "Cloudflare" in title


def wait_for_cloudflare(page, prompt_after=15, give_up_after=240):
    """Block until Cloudflare clears, prompting for a manual tick if it stalls.

    The challenge is an interactive Turnstile checkbox, so past `prompt_after`
    seconds we assume it needs a human and say so rather than silently spinning.
    """
    waited = 0
    prompted = False
    while waited < give_up_after:
        if not _blocked(page):
            return True
        if waited >= prompt_after and not prompted:
            print("\n  >> Cloudflare wants a human: tick 'Verify you are human' in the")
            print("     browser window. Clearance is saved, so this is usually one-time.\n")
            prompted = True
        page.wait_for_timeout(3000)
        waited += 3
    return False


def scrape_section(page, section, max_pages, cutoff):
    """Scrape one research-hub facet, paging until items fall outside the window."""
    results = []
    seen = set()

    for page_num in range(max_pages):
        url = f"{section['url']}&page={page_num}"
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        if not wait_for_cloudflare(page):
            print(f"  TIMEOUT: Cloudflare did not clear for {url}")
            break

        try:
            page.wait_for_selector("a.card", timeout=15000)
        except Exception:
            print(f"  No cards on page {page_num} (title: {page.title()})")
            break

        cards = page.evaluate(EXTRACT_CARDS_JS)
        if not cards:
            break

        stale_on_page = 0
        for card in cards:
            link = card["link"].strip()
            title = card["title"].strip()
            if not link or len(title) < 5 or link in seen:
                continue
            seen.add(link)

            dt = parse_date(card.get("date_text"))
            if dt and dt < cutoff:
                stale_on_page += 1
                continue

            results.append({
                "title": title,
                "link": link,
                "date": dt.isoformat() if dt else None,
                "type": card.get("type", "").strip(),
            })

        # Listings are newest-first, so a page that is mostly stale ends the walk.
        if stale_on_page > len(cards) / 2:
            break

    return results


def load_existing():
    """Load the current cache as {link: row}, so a backfill tops up rather than replaces."""
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    items = data.get("items", []) if isinstance(data, dict) else []
    return {i["link"]: i for i in items if isinstance(i, dict) and i.get("link")}


def main():
    parser = argparse.ArgumentParser(description="Backfill IEEFA reports via Playwright")
    parser.add_argument("--pages", type=int, default=3, help="max listing pages per section (default 3)")
    parser.add_argument("--push", action="store_true", help="git commit and push after saving")
    args = parser.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=CACHE_WINDOW_DAYS)
    by_link = load_existing()
    print(f"Cache holds {len(by_link)} items; scraping {len(IEEFA_SECTIONS)} IEEFA sections...")

    scraped = 0
    with sync_playwright() as p:
        # Real Chrome, and a persistent profile so the Turnstile clearance cookie
        # outlives the run. Headed is mandatory — the checkbox needs a click.
        os.makedirs(PROFILE_DIR, exist_ok=True)
        ctx = p.chromium.launch_persistent_context(PROFILE_DIR, headless=False, channel="chrome")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        for section in IEEFA_SECTIONS:
            items = scrape_section(page, section, args.pages, cutoff)
            for item in items:
                by_link[item["link"]] = item
            scraped += len(items)
            print(f"  {section['name']:<24s} {len(items)} items")

        ctx.close()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": {"source": "ieefa_playwright_backfill", "scraped": scraped},
        "items": sorted(by_link.values(), key=lambda i: i.get("date") or "", reverse=True),
    }

    # Temp file + rename: the pipeline reads this concurrently, so a reader
    # must never catch a half-written file.
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CACHE_PATH)

    print(f"\nScraped {scraped}, cache now holds {len(by_link)} items → static/ieefa_cache.json")

    if args.push:
        print("\nCommitting and pushing...")
        subprocess.run(["git", "add", CACHE_PATH], cwd=SCRIPT_DIR)
        subprocess.run(
            ["git", "commit", "-m", f"chore: backfill IEEFA cache ({len(by_link)} items)"],
            cwd=SCRIPT_DIR,
        )
        subprocess.run(["git", "push"], cwd=SCRIPT_DIR)
        print("Pushed to remote.")


if __name__ == "__main__":
    main()
