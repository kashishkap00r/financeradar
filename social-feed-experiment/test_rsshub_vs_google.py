#!/usr/bin/env python3
"""
Session 1: Compare RSSHub vs Google News RSS for Twitter handles.
Run AFTER starting RSSHub locally: cd rsshub-test && npm run dev

Usage:
    python3 test_rsshub_vs_google.py
"""

import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import json
import time
import sys

# --- Config ---
RSSHUB_BASE = "http://localhost:1200"
GOOGLE_BASE = "https://news.google.com/rss/search"

HANDLES = [
    "deepakshenoy",
    "KobeissiLetter",
    "michaelxpettis",
    "sanjeevsanyal",
    "contrarianEPS",
]

RESULTS = []


def fetch_xml(url, source_name, timeout=30):
    """Fetch and parse RSS/XML from a URL."""
    try:
        req = Request(url, headers={"User-Agent": "FinanceRadar-Test/1.0"})
        start = time.time()
        resp = urlopen(req, timeout=timeout)
        elapsed = round(time.time() - start, 2)
        data = resp.read().decode("utf-8", errors="replace")
        return data, elapsed, resp.status
    except HTTPError as e:
        return None, 0, e.code
    except (URLError, Exception) as e:
        return None, 0, str(e)


def count_items(xml_str):
    """Count <item> or <entry> elements in RSS/Atom XML."""
    if not xml_str:
        return 0, [], None
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return 0, [], "XML parse error"

    # RSS 2.0
    items = root.findall(".//item")
    if not items:
        # Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//atom:entry", ns)

    titles = []
    dates = []
    for item in items:
        title_el = item.find("title")
        if title_el is None:
            title_el = item.find("{http://www.w3.org/2005/Atom}title")
        date_el = item.find("pubDate")
        if date_el is None:
            date_el = item.find("{http://www.w3.org/2005/Atom}published")

        t = (title_el.text or "")[:80] if title_el is not None else "(no title)"
        d = (date_el.text or "") if date_el is not None else "(no date)"
        titles.append(t)
        dates.append(d)

    return len(items), titles, dates


def check_content(titles):
    """Classify content: original tweets, retweets, replies."""
    rts = sum(1 for t in titles if t.strip().startswith("RT @"))
    replies = sum(1 for t in titles if t.strip().startswith("@"))
    originals = len(titles) - rts - replies
    return originals, rts, replies


def test_handle(handle):
    """Test one handle against both sources."""
    print(f"\n{'='*60}")
    print(f"  Testing: @{handle}")
    print(f"{'='*60}")

    # RSSHub
    rsshub_url = f"{RSSHUB_BASE}/twitter/user/{handle}"
    print(f"\n  [RSSHub] {rsshub_url}")
    rsshub_xml, rsshub_time, rsshub_status = fetch_xml(rsshub_url, "RSSHub")
    rsshub_count, rsshub_titles, rsshub_dates = count_items(rsshub_xml)
    rsshub_orig, rsshub_rts, rsshub_replies = check_content(rsshub_titles)
    print(f"    Status: {rsshub_status} | Items: {rsshub_count} | Time: {rsshub_time}s")
    print(f"    Originals: {rsshub_orig} | RTs: {rsshub_rts} | Replies: {rsshub_replies}")
    if rsshub_dates and rsshub_dates[0] != "(no date)":
        print(f"    Most recent: {rsshub_dates[0]}")
        print(f"    Oldest: {rsshub_dates[-1]}")

    # Google News RSS
    google_url = f"{GOOGLE_BASE}?q=site:x.com/{handle}/status&hl=en-IN&gl=IN&ceid=IN:en"
    print(f"\n  [Google] {google_url[:80]}...")
    google_xml, google_time, google_status = fetch_xml(google_url, "Google")
    google_count, google_titles, google_dates = count_items(google_xml)
    google_orig, google_rts, google_replies = check_content(google_titles)
    print(f"    Status: {google_status} | Items: {google_count} | Time: {google_time}s")
    print(f"    Originals: {google_orig} | RTs: {google_rts} | Replies: {google_replies}")
    if google_dates and google_dates[0] != "(no date)":
        print(f"    Most recent: {google_dates[0]}")
        print(f"    Oldest: {google_dates[-1]}")

    # Ratio
    if google_count > 0:
        ratio = round(rsshub_count / google_count, 1)
        print(f"\n  --> RSSHub/Google ratio: {ratio}x ({rsshub_count} vs {google_count})")
    else:
        ratio = "N/A"
        print(f"\n  --> Google returned 0 items, ratio: N/A")

    result = {
        "handle": handle,
        "rsshub_items": rsshub_count,
        "rsshub_originals": rsshub_orig,
        "rsshub_rts": rsshub_rts,
        "rsshub_replies": rsshub_replies,
        "rsshub_time_s": rsshub_time,
        "rsshub_status": rsshub_status,
        "google_items": google_count,
        "google_originals": google_orig,
        "google_rts": google_rts,
        "google_replies": google_replies,
        "google_time_s": google_time,
        "google_status": google_status,
        "ratio": ratio,
    }

    # Show first 3 RSSHub titles for verification
    if rsshub_titles:
        print(f"\n  [RSSHub sample titles]")
        for t in rsshub_titles[:3]:
            print(f"    - {t}")

    RESULTS.append(result)
    return result


def main():
    print("=" * 60)
    print("  RSSHub vs Google News RSS — Twitter Feed Comparison")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Check if RSSHub is running
    try:
        urlopen(f"{RSSHUB_BASE}/", timeout=5)
    except Exception:
        print("\n  ERROR: RSSHub not running at localhost:1200")
        print("  Start it first: cd rsshub-test && npm run dev")
        sys.exit(1)

    for handle in HANDLES:
        test_handle(handle)
        time.sleep(2)  # Be gentle

    # Summary
    print(f"\n\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    print(f"{'Handle':<20} {'RSSHub':>8} {'Google':>8} {'Ratio':>8}")
    print("-" * 48)
    for r in RESULTS:
        print(f"{r['handle']:<20} {r['rsshub_items']:>8} {r['google_items']:>8} {str(r['ratio']):>8}")

    # Success criteria
    passing = sum(1 for r in RESULTS if isinstance(r["ratio"], float) and r["ratio"] >= 3.0)
    total = len(RESULTS)
    print(f"\n  Handles where RSSHub >= 3x Google: {passing}/{total}")
    if passing >= 4:
        print("  SUCCESS: RSSHub meets the 3x threshold for >= 4 handles")
    else:
        print("  BELOW THRESHOLD: RSSHub did not meet 3x for >= 4 handles")

    # Save results
    out_path = "session1-comparison-results.json"
    with open(out_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": RESULTS,
            "passing_count": passing,
        }, f, indent=2)
    print(f"\n  Results saved to: {out_path}")


if __name__ == "__main__":
    main()
