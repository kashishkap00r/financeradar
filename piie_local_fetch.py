#!/usr/bin/env python3
"""
Local PIIE scraper using Playwright.

PIIE is behind Cloudflare — requires a real browser to solve the challenge.
This script visits each PIIE section, extracts articles, and saves to a
cache file that the main pipeline reads.

Usage:
    python3 piie_local_fetch.py                # fetch + save
    python3 piie_local_fetch.py --push         # fetch + save + git commit & push

Requires: playwright (pip install playwright && playwright install)
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(SCRIPT_DIR, "static", "piie_cache.json")

PIIE_SECTIONS = [
    {
        "id": "piie-blogs",
        "name": "PIIE — Blogs",
        "url": "https://www.piie.com/blogs",
    },
    {
        "id": "piie-working-papers",
        "name": "PIIE — Working Papers",
        "url": "https://www.piie.com/publications/working-papers",
    },
    {
        "id": "piie-policy-briefs",
        "name": "PIIE — Policy Briefs",
        "url": "https://www.piie.com/publications/policy-briefs",
    },
    {
        "id": "piie-briefings",
        "name": "PIIE — Briefings",
        "url": "https://www.piie.com/publications/piie-briefings",
    },
    {
        "id": "piie-commentary",
        "name": "PIIE — Commentary",
        "url": "https://www.piie.com/research/commentary",
    },
]

DATE_PATTERNS = [
    r"(\w+ \d{1,2}, \d{4})",  # March 16, 2026
    r"(\w+ \d{4})",            # March 2026
]


def parse_date(date_str):
    """Parse PIIE date formats."""
    date_str = date_str.strip()
    for fmt in ["%B %d, %Y", "%B %Y"]:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def scrape_section(page, section):
    """Scrape one PIIE section using an existing Playwright page."""
    url = section["url"]
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    # Wait for Cloudflare challenge to resolve (look for title change)
    for _ in range(12):  # up to 60 seconds
        title = page.title()
        if "Just a moment" not in title and "Cloudflare" not in title:
            break
        page.wait_for_timeout(5000)

    # Extra settle time for JS rendering after Cloudflare clears
    page.wait_for_timeout(3000)

    # Now wait for article elements
    try:
        page.wait_for_selector("article", timeout=15000)
    except Exception:
        print(f"  TIMEOUT: Could not load {url} (title: {page.title()})")
        return []

    # Extract articles via JavaScript
    articles_data = page.evaluate("""() => {
        const articles = [];
        document.querySelectorAll('article').forEach(article => {
            const h2 = article.querySelector('h2');
            const link = h2 ? h2.querySelector('a') : null;
            const time = article.querySelector('time');
            const typeP = article.querySelector('p');

            if (!link) return;

            // Get the href - could be internal or external
            let href = link.getAttribute('href') || '';
            if (href.startsWith('/')) {
                href = 'https://www.piie.com' + href;
            }

            // Get title (strip "(link is external)" text)
            let title = link.textContent.trim()
                .replace(/\\(link is external\\)/g, '')
                .replace(/\\s+/g, ' ')
                .trim();

            const dateText = time ? time.textContent.trim() : '';
            const typeText = typeP ? typeP.textContent.trim() : '';

            articles.push({
                title: title,
                link: href,
                date_text: dateText,
                type: typeText,
            });
        });
        return articles;
    }""")

    results = []
    for item in articles_data:
        title = item.get("title", "").strip()
        link = item.get("link", "").strip()
        date_text = item.get("date_text", "")
        article_type = item.get("type", "")

        if not title or not link or len(title) < 5:
            continue

        dt = parse_date(date_text) if date_text else None

        results.append({
            "title": title,
            "link": link,
            "date": dt.isoformat() if dt else None,
            "source": "PIIE",
            "publisher": "PIIE",
            "category": "Reports",
            "region": "International",
            "feed_id": section["id"],
            "article_type": article_type,
        })

    return results


def main():
    parser = argparse.ArgumentParser(description="Fetch PIIE reports via Playwright")
    parser.add_argument("--push", action="store_true", help="Git commit and push after saving")
    args = parser.parse_args()

    print(f"Scraping {len(PIIE_SECTIONS)} PIIE sections with Playwright...")

    all_items = []
    with sync_playwright() as p:
        # Use installed Chrome (not Chromium) to bypass Cloudflare detection
        browser = p.chromium.launch(headless=False, channel="chrome")
        context = browser.new_context()
        page = context.new_page()

        for section in PIIE_SECTIONS:
            articles = scrape_section(page, section)
            all_items.extend(articles)
            print(f"  {section['name']:<30s} {len(articles)} articles")

        browser.close()

    # Save cache
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": {
            "source": "piie_playwright",
            "sections": len(PIIE_SECTIONS),
            "items_total": len(all_items),
        },
        "items": all_items,
    }

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)

    print(f"\nSaved {len(all_items)} items to static/piie_cache.json")

    if args.push:
        print("\nCommitting and pushing...")
        subprocess.run(["git", "add", CACHE_PATH], cwd=SCRIPT_DIR)
        subprocess.run(
            ["git", "commit", "-m", f"chore: update PIIE cache ({len(all_items)} items)"],
            cwd=SCRIPT_DIR,
        )
        subprocess.run(["git", "push"], cwd=SCRIPT_DIR)
        print("Pushed to remote.")


if __name__ == "__main__":
    main()
