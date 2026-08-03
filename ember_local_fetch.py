#!/usr/bin/env python3
"""
Local Ember scraper using Playwright.

ember-energy.org puts everything behind a Cloudflare challenge — robots.txt,
/feed/ and the WordPress REST API included — so there is no endpoint the
GitHub Actions pipeline can reach. This script clears the challenge in a real
browser, then reads the site's own REST API (far cleaner than scraping the
DOM) and writes static/ember_cache.json for reports_fetcher.py to consume.

Because CI can never refresh this, the cache goes stale if the script stops
being run. That is safe rather than silently wrong: every item carries a date
and the 30-day Reports window filters on it, so a neglected cache empties
itself instead of serving old reports. The pipeline warns past 7 days.

Usage:
    python3 ember_local_fetch.py                # fetch + save
    python3 ember_local_fetch.py --per-type 60  # pull deeper history
    python3 ember_local_fetch.py --push         # fetch + save + git commit & push

Requires: playwright (pip install playwright && playwright install)
"""

import argparse
import html
import json
import os
import re
import subprocess
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(SCRIPT_DIR, "static", "ember_cache.json")
PROFILE_DIR = os.path.expanduser("~/.cache/financeradar-ember-profile")

INSIGHTS_URL = "https://ember-energy.org/insights/#all"

# `insight_type` taxonomy term ids, from /wp-json/wp/v2/insight_type.
# Labels must match _EMBER_FEED_TYPES in reports_fetcher.py.
INSIGHT_TYPES = {
    376: "Analysis",
    23: "Commentary",
    24: "Policy papers",
}

# Pulls each type straight from the REST API inside the cleared browser session.
FETCH_JS = """async ({types, perType}) => {
    const out = [];
    for (const [tid, label] of Object.entries(types)) {
        const url = `/wp-json/wp/v2/insight_page?insight_type=${tid}`
            + `&orderby=date&order=desc&per_page=${perType}`
            + `&_fields=id,title,link,date,excerpt`;
        const res = await fetch(url, {credentials: 'include'});
        if (!res.ok) { out.push({__error: res.status, label}); continue; }
        for (const p of await res.json()) {
            out.push({
                title: (p.title && p.title.rendered) || '',
                link: p.link || '',
                date: p.date || null,
                type: label,
                description: ((p.excerpt && p.excerpt.rendered) || '')
                    .replace(/<[^>]+>/g, '').replace(/\\s+/g, ' ').trim().slice(0, 300),
            });
        }
    }
    return out;
}"""


def clean(text):
    """Strip tags and decode entities — WP returns rendered HTML."""
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def wait_for_cloudflare(page, prompt_after=15, give_up_after=240):
    """Block until Cloudflare clears, asking for a manual tick if it stalls."""
    waited = 0
    prompted = False
    while waited < give_up_after:
        title = page.title()
        if "Just a moment" not in title and "Cloudflare" not in title:
            return True
        if waited >= prompt_after and not prompted:
            print("\n  >> Cloudflare wants a human: tick 'Verify you are human' in the")
            print("     browser window. Clearance is saved, so this is usually one-time.\n")
            prompted = True
        page.wait_for_timeout(3000)
        waited += 3
    return False


def main():
    parser = argparse.ArgumentParser(description="Fetch Ember insights via Playwright")
    parser.add_argument("--per-type", type=int, default=40, help="items per insight type (default 40)")
    parser.add_argument("--push", action="store_true", help="git commit and push after saving")
    args = parser.parse_args()

    print(f"Fetching {len(INSIGHT_TYPES)} Ember insight types (up to {args.per_type} each)...")

    with sync_playwright() as p:
        # Real Chrome plus a persistent profile, so the clearance cookie survives.
        os.makedirs(PROFILE_DIR, exist_ok=True)
        ctx = p.chromium.launch_persistent_context(PROFILE_DIR, headless=False, channel="chrome")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(INSIGHTS_URL, wait_until="domcontentloaded", timeout=60000)

        if not wait_for_cloudflare(page):
            print("  FAILED: Cloudflare never cleared; cache left untouched.")
            ctx.close()
            return 1

        raw = page.evaluate(FETCH_JS, {"types": {str(k): v for k, v in INSIGHT_TYPES.items()},
                                       "perType": args.per_type})
        ctx.close()

    items, errors = [], []
    seen = set()
    for row in raw:
        if row.get("__error"):
            errors.append(f"{row.get('label')}: HTTP {row['__error']}")
            continue
        title, link = clean(row.get("title")), (row.get("link") or "").strip()
        if not title or not link or link in seen:
            continue
        seen.add(link)
        items.append({
            "title": title,
            "link": link,
            "date": row.get("date"),
            "type": row.get("type", ""),
            "description": clean(row.get("description")),
        })

    for err in errors:
        print(f"  [WARN] {err}")
    if not items:
        print("  FAILED: no items returned; cache left untouched.")
        return 1

    by_type = {}
    for i in items:
        by_type[i["type"]] = by_type.get(i["type"], 0) + 1
    for label in INSIGHT_TYPES.values():
        print(f"  {label:<16s} {by_type.get(label, 0)} items")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": {"source": "ember_wp_rest", "items_total": len(items)},
        "items": sorted(items, key=lambda i: i.get("date") or "", reverse=True),
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

    print(f"\nSaved {len(items)} items to static/ember_cache.json")

    if args.push:
        print("\nCommitting and pushing...")
        subprocess.run(["git", "add", CACHE_PATH], cwd=SCRIPT_DIR)
        subprocess.run(["git", "commit", "-m", f"chore: update Ember cache ({len(items)} items)"], cwd=SCRIPT_DIR)
        subprocess.run(["git", "push"], cwd=SCRIPT_DIR)
        print("Pushed to remote.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
