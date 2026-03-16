#!/usr/bin/env python3
"""
Session 2, Step 2.2: Scale test — fetch all 49 Twitter handles via RSSHub.
Measures: status, item count, response time, errors, rate limiting.
"""

import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import os

RSSHUB = "http://localhost:1200"
FEEDS_JSON = os.path.expanduser("~/vibecoding projects/financeradar/feeds.json")

def load_handles():
    with open(FEEDS_JSON) as f:
        feeds = json.load(f)
    handles = []
    for feed in feeds:
        if feed.get("category") == "Twitter":
            url = feed.get("url", "")
            if "x.com/" in url:
                handle = url.split("x.com/")[-1].strip("/")
                handles.append(handle)
    return handles

def fetch_one(handle):
    url = f"{RSSHUB}/twitter/user/{handle}"
    start = time.time()
    try:
        req = Request(url, headers={"User-Agent": "FinanceRadar-ScaleTest/1.0"})
        resp = urlopen(req, timeout=60)
        elapsed = round(time.time() - start, 2)
        data = resp.read().decode("utf-8", errors="replace")

        root = ET.fromstring(data)
        items = root.findall(".//item")

        newest_age = None
        if items:
            date_el = items[0].find("pubDate")
            if date_el is not None and date_el.text:
                try:
                    dt = parsedate_to_datetime(date_el.text)
                    newest_age = round((datetime.now(timezone.utc) - dt).total_seconds() / 3600, 1)
                except:
                    pass

        rts = sum(1 for i in items if (i.find("title").text or "").startswith("RT "))

        return {
            "handle": handle,
            "status": 200,
            "items": len(items),
            "rts": rts,
            "originals": len(items) - rts,
            "time_s": elapsed,
            "newest_age_h": newest_age,
            "error": None,
        }
    except HTTPError as e:
        elapsed = round(time.time() - start, 2)
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:200]
        except:
            pass
        return {
            "handle": handle,
            "status": e.code,
            "items": 0,
            "rts": 0,
            "originals": 0,
            "time_s": elapsed,
            "newest_age_h": None,
            "error": f"HTTP {e.code}: {body[:100]}",
        }
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        return {
            "handle": handle,
            "status": 0,
            "items": 0,
            "rts": 0,
            "originals": 0,
            "time_s": elapsed,
            "newest_age_h": None,
            "error": str(e)[:100],
        }

def main():
    handles = load_handles()
    print(f"{'='*70}")
    print(f"  RSSHub Scale Test — {len(handles)} handles")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    # Sequential to avoid overwhelming RSSHub/Twitter
    results = []
    rate_limited = 0
    errors = 0
    total_items = 0
    total_start = time.time()

    for i, handle in enumerate(handles):
        r = fetch_one(handle)
        results.append(r)

        status_icon = "OK" if r["status"] == 200 else f"ERR({r['status']})"
        age_str = f"{r['newest_age_h']}h" if r['newest_age_h'] is not None else "N/A"
        print(f"  [{i+1:2d}/49] @{handle:<22s} {status_icon:<8s} {r['items']:>3d} items  {r['time_s']:>5.1f}s  newest: {age_str}")

        if r["status"] == 429:
            rate_limited += 1
        if r["error"]:
            errors += 1
        total_items += r["items"]

        # Small delay between requests
        time.sleep(1)

    total_time = round(time.time() - total_start, 1)

    # Summary
    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    success = sum(1 for r in results if r["status"] == 200)
    print(f"  Total handles:      {len(handles)}")
    print(f"  Successful (200):   {success}")
    print(f"  Rate limited (429): {rate_limited}")
    print(f"  Other errors:       {errors - rate_limited}")
    print(f"  Total items:        {total_items}")
    print(f"  Avg items/handle:   {total_items/max(success,1):.1f}")
    print(f"  Total time:         {total_time}s")
    print(f"  Avg time/handle:    {total_time/len(handles):.1f}s")

    # Distribution
    times = [r["time_s"] for r in results if r["status"] == 200]
    if times:
        print(f"\n  Response times:")
        print(f"    Min:    {min(times):.1f}s")
        print(f"    Max:    {max(times):.1f}s")
        print(f"    Median: {sorted(times)[len(times)//2]:.1f}s")

    # Failures detail
    failed = [r for r in results if r["status"] != 200]
    if failed:
        print(f"\n  Failed handles:")
        for r in failed:
            print(f"    @{r['handle']}: {r['error']}")

    # Freshness
    ages = [r["newest_age_h"] for r in results if r["newest_age_h"] is not None]
    if ages:
        print(f"\n  Freshness (newest tweet age):")
        print(f"    < 1 hour:   {sum(1 for a in ages if a < 1)}")
        print(f"    1-6 hours:  {sum(1 for a in ages if 1 <= a < 6)}")
        print(f"    6-24 hours: {sum(1 for a in ages if 6 <= a < 24)}")
        print(f"    1-7 days:   {sum(1 for a in ages if 24 <= a < 168)}")
        print(f"    > 7 days:   {sum(1 for a in ages if a >= 168)}")

    # Save
    out = {
        "timestamp": datetime.now().isoformat(),
        "total_handles": len(handles),
        "success": success,
        "rate_limited": rate_limited,
        "errors": errors,
        "total_items": total_items,
        "total_time_s": total_time,
        "results": results,
    }
    with open("session2-scale-results.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n  Saved to session2-scale-results.json")


if __name__ == "__main__":
    main()
