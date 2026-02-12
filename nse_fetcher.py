#!/usr/bin/env python3
"""
NSE Bulk/Block Deals Fetcher
Fetches large deal data from NSE India and outputs to static/nse_deals.json.
Handles NSE's anti-scraping: cookie dance + proper headers.
"""

import json
import os
import urllib.request
import urllib.error
import http.cookiejar
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "static", "nse_deals.json")

IST_TZ = timezone(timedelta(hours=5, minutes=30))

# NSE requires a browser-like session: first hit homepage for cookies, then API
NSE_BASE = "https://www.nseindia.com"
NSE_API = "https://www.nseindia.com/api/snapshot-capital-market-largedeal"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def create_nse_session():
    """Create a urllib session with cookie handling for NSE."""
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    return opener, cookie_jar


def make_request(opener, url, ua_index=0):
    """Make a request with proper NSE headers."""
    ua = USER_AGENTS[ua_index % len(USER_AGENTS)]
    req = urllib.request.Request(url, headers={
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Referer": NSE_BASE + "/",
        "Connection": "keep-alive",
    })
    return opener.open(req, timeout=15)


def fetch_deals():
    """Fetch bulk/block deals from NSE API."""
    opener, _ = create_nse_session()

    # Step 1: Hit homepage to get cookies
    print("  Fetching NSE homepage for cookies...")
    for i in range(len(USER_AGENTS)):
        try:
            make_request(opener, NSE_BASE, i)
            print("  [OK] Got NSE cookies")
            break
        except Exception as e:
            if i == len(USER_AGENTS) - 1:
                print(f"  [FAIL] Could not get NSE cookies: {str(e)[:80]}")
                return None

    # Step 2: Fetch the deals API
    print("  Fetching deals API...")
    for i in range(len(USER_AGENTS)):
        try:
            resp = make_request(opener, NSE_API, i)
            content = resp.read()
            data = json.loads(content)
            print(f"  [OK] Got deals data")
            return data
        except urllib.error.HTTPError as e:
            print(f"  [RETRY] HTTP {e.code} with UA #{i}")
            if i == len(USER_AGENTS) - 1:
                print(f"  [FAIL] All UAs failed: HTTP {e.code}")
                return None
        except Exception as e:
            print(f"  [RETRY] Error with UA #{i}: {str(e)[:60]}")
            if i == len(USER_AGENTS) - 1:
                print(f"  [FAIL] All UAs failed: {str(e)[:80]}")
                return None

    return None


def parse_deals(raw_data):
    """Parse NSE deals data into a structured format."""
    if not raw_data:
        return []

    deals = []
    now = datetime.now(IST_TZ)
    cutoff = now - timedelta(hours=48)

    # NSE returns data under different keys depending on the API version
    deal_lists = []
    if isinstance(raw_data, dict):
        # Try common keys
        for key in ["BLOCK", "BULK", "block", "bulk", "data", "Data"]:
            if key in raw_data:
                items = raw_data[key]
                if isinstance(items, list):
                    for item in items:
                        item["_deal_type"] = key.upper().replace("DATA", "DEAL")
                    deal_lists.extend(items)

        # If no known keys, try to find any list
        if not deal_lists:
            for key, val in raw_data.items():
                if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                    for item in val:
                        item["_deal_type"] = key.upper()
                    deal_lists.extend(val)

    elif isinstance(raw_data, list):
        deal_lists = raw_data

    for item in deal_lists:
        try:
            deal = {
                "symbol": item.get("symbol", ""),
                "name": item.get("name", ""),
                "deal_type": item.get("_deal_type", "DEAL").replace("_DATA", "").replace("_DEALS", ""),
                "client": item.get("clientName", ""),
                "buy_sell": item.get("buySell", ""),
                "quantity": item.get("qty", 0),
                "price": item.get("watp", 0),
                "date": item.get("date", ""),
                "remarks": item.get("remarks", ""),
            }

            # Clean up values
            if isinstance(deal["quantity"], str):
                deal["quantity"] = deal["quantity"].replace(",", "")
                try:
                    deal["quantity"] = int(float(deal["quantity"]))
                except ValueError:
                    deal["quantity"] = 0

            if isinstance(deal["price"], str):
                deal["price"] = deal["price"].replace(",", "")
                try:
                    deal["price"] = float(deal["price"])
                except ValueError:
                    deal["price"] = 0

            # Calculate trade value
            try:
                deal["value_cr"] = round((deal["quantity"] * deal["price"]) / 10000000, 2)
            except (TypeError, ValueError):
                deal["value_cr"] = 0

            if deal["symbol"]:
                deals.append(deal)

        except Exception as e:
            print(f"  [WARN] Skipping deal entry: {str(e)[:50]}")
            continue

    # Sort by date (most recent first), then by value
    deals.sort(key=lambda d: (d.get("date", ""), d.get("value_cr", 0)), reverse=True)

    return deals


def main():
    print("=" * 50)
    print("NSE Bulk/Block Deals Fetcher")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    raw_data = fetch_deals()

    if raw_data is None:
        print("\n  [WARN] Could not fetch NSE deals — writing empty output")
        deals = []
    else:
        deals = parse_deals(raw_data)
        print(f"\n  Parsed {len(deals)} deals")

    output = {
        "generated_at": datetime.now(IST_TZ).isoformat(),
        "deals": deals,
        "warnings": [] if deals else ["Could not fetch NSE deals data"],
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"  Output: {OUTPUT_FILE}")
    print(f"  Total deals: {len(deals)}")
    print("\nDone!")
    print("=" * 50)


if __name__ == "__main__":
    main()
