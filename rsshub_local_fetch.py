#!/usr/bin/env python3
"""
Local RSSHub Twitter fetcher.

Run this on your machine (where RSSHub is running on localhost:1200)
to fetch fresh tweets and save them as a cache file that the main
pipeline merges with Google RSS results.

Usage:
    python3 rsshub_local_fetch.py                # fetch + save
    python3 rsshub_local_fetch.py --push         # fetch + save + git commit & push

Requires: RSSHub running locally (npm run dev in rsshub-test/)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import RSSHUB_BASE_URL, RSSHUB_CACHE_FILE

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FEEDS_JSON = os.path.join(SCRIPT_DIR, "feeds.json")
CACHE_PATH = os.path.join(SCRIPT_DIR, RSSHUB_CACHE_FILE)

RETWEET_RE = re.compile(r"^RT\s+", re.IGNORECASE)
X_STATUS_RE = re.compile(r"https?://(?:x|twitter)\.com/([^/]+)/status/(\d+)")


def load_twitter_handles():
    """Read Twitter handles from feeds.json."""
    with open(FEEDS_JSON, "r", encoding="utf-8") as f:
        feeds = json.load(f)
    handles = []
    for feed in feeds:
        if feed.get("category") != "Twitter":
            continue
        url = feed.get("url", "")
        if "x.com/" in url:
            handle = url.split("x.com/")[-1].strip("/")
            publisher = feed.get("publisher", feed.get("name", handle))
            handles.append({"handle": handle, "publisher": publisher, "id": feed.get("id", "")})
    return handles


def fetch_rsshub_feed(handle, base_url=RSSHUB_BASE_URL, timeout=60):
    """Fetch one handle from RSSHub, return list of article dicts."""
    url = f"{base_url}/twitter/user/{handle}"
    try:
        req = Request(url, headers={"User-Agent": "FinanceRadar-RSSHub/1.0"})
        resp = urlopen(req, timeout=timeout)
        data = resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, Exception) as e:
        return [], str(e)

    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return [], "XML parse error"

    items = root.findall(".//item")
    articles = []
    for item in items:
        title = (item.find("title").text or "").strip() if item.find("title") is not None else ""
        link = (item.find("link").text or "").strip() if item.find("link") is not None else ""
        pub_date = (item.find("pubDate").text or "").strip() if item.find("pubDate") is not None else ""
        author = (item.find("author").text or "").strip() if item.find("author") is not None else ""
        desc = (item.find("description").text or "").strip() if item.find("description") is not None else ""

        # Parse date
        dt = None
        if pub_date:
            try:
                dt = parsedate_to_datetime(pub_date)
            except Exception:
                pass

        # Extract tweet_id from link
        tweet_id = ""
        m = X_STATUS_RE.search(link)
        if m:
            tweet_id = m.group(2)

        if not tweet_id or not link:
            continue

        articles.append({
            "title": title,
            "link": link,
            "date": dt.isoformat() if dt else None,
            "tweet_id": tweet_id,
            "source": author or handle,
            "publisher": "",  # filled by caller
            "source_mode": "rsshub",
            "is_retweet": bool(RETWEET_RE.match(title)),
            "is_reply": title.startswith("@"),
            "description_html": desc,
        })

    return articles, None


def main():
    parser = argparse.ArgumentParser(description="Fetch Twitter via local RSSHub")
    parser.add_argument("--push", action="store_true", help="Git commit and push after saving")
    parser.add_argument("--base-url", default=RSSHUB_BASE_URL, help="RSSHub base URL")
    args = parser.parse_args()

    # Check RSSHub is running
    try:
        urlopen(f"{args.base_url}/healthz", timeout=5)
    except Exception:
        print(f"ERROR: RSSHub not reachable at {args.base_url}")
        print("Start it first: cd rsshub-test && npm run dev")
        sys.exit(1)

    handles = load_twitter_handles()
    print(f"Fetching {len(handles)} handles from RSSHub at {args.base_url}")

    all_items = []
    ok = 0
    empty = 0
    errors = 0

    for i, h in enumerate(handles):
        articles, err = fetch_rsshub_feed(h["handle"], base_url=args.base_url)
        if err:
            errors += 1
            print(f"  [{i+1:2d}/{len(handles)}] @{h['handle']:<22s} ERROR: {err[:60]}")
        elif not articles:
            empty += 1
            print(f"  [{i+1:2d}/{len(handles)}] @{h['handle']:<22s} 0 items (empty/rate-limited)")
        else:
            ok += 1
            for a in articles:
                a["publisher"] = h["publisher"]
            all_items.extend(articles)
            print(f"  [{i+1:2d}/{len(handles)}] @{h['handle']:<22s} {len(articles)} items")

        time.sleep(1)  # stay under rate limit

    # Save cache
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": {
            "source": "rsshub_local",
            "base_url": args.base_url,
            "handles_total": len(handles),
            "handles_ok": ok,
            "handles_empty": empty,
            "handles_error": errors,
            "items_total": len(all_items),
        },
        "items": all_items,
    }

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)

    print(f"\nSaved {len(all_items)} items to {RSSHUB_CACHE_FILE}")
    print(f"  OK: {ok} | Empty: {empty} | Errors: {errors}")

    if args.push:
        print("\nCommitting and pushing...")
        subprocess.run(["git", "add", CACHE_PATH], cwd=SCRIPT_DIR)
        subprocess.run(
            ["git", "commit", "-m", f"chore: update RSSHub twitter cache ({len(all_items)} items)"],
            cwd=SCRIPT_DIR,
        )
        subprocess.run(["git", "push"], cwd=SCRIPT_DIR)
        print("Pushed to remote.")


if __name__ == "__main__":
    main()
