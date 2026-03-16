#!/usr/bin/env python3
"""
Session 2, Step 2.1: Soak test — poll 5 handles every 30 min, log results.
Run in background: nohup python3 soak_test.py &> soak_test.log &

Tracks: response code, item count, token validity, errors.
Stop: kill the process or Ctrl+C.
"""

import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

RSSHUB = "http://localhost:1200"
INTERVAL_MIN = 30
LOG_FILE = "soak_test_log.jsonl"

HANDLES = [
    "deepakshenoy",
    "KobeissiLetter",
    "michaelxpettis",
    "sanjeevsanyal",
    "contrarianEPS",
]

def fetch_one(handle):
    url = f"{RSSHUB}/twitter/user/{handle}"
    start = time.time()
    try:
        req = Request(url, headers={"User-Agent": "FinanceRadar-SoakTest/1.0"})
        resp = urlopen(req, timeout=60)
        elapsed = round(time.time() - start, 2)
        data = resp.read().decode("utf-8", errors="replace")
        root = ET.fromstring(data)
        items = root.findall(".//item")
        newest = None
        if items:
            d = items[0].find("pubDate")
            if d is not None and d.text:
                try:
                    newest = parsedate_to_datetime(d.text).isoformat()
                except:
                    pass
        return {"status": 200, "items": len(items), "time_s": elapsed, "newest": newest, "error": None}
    except HTTPError as e:
        elapsed = round(time.time() - start, 2)
        return {"status": e.code, "items": 0, "time_s": elapsed, "newest": None, "error": f"HTTP {e.code}"}
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        return {"status": 0, "items": 0, "time_s": elapsed, "newest": None, "error": str(e)[:100]}

def run_cycle():
    ts = datetime.now().isoformat()
    results = {}
    all_ok = True
    for handle in HANDLES:
        r = fetch_one(handle)
        results[handle] = r
        if r["status"] != 200:
            all_ok = False
        time.sleep(2)

    entry = {"timestamp": ts, "all_ok": all_ok, "results": results}

    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

    total_items = sum(r["items"] for r in results.values())
    errors = sum(1 for r in results.values() if r["status"] != 200)
    print(f"[{ts}] Items: {total_items} | Errors: {errors} | {'OK' if all_ok else 'ISSUES'}")
    return all_ok

def main():
    print(f"Soak test started. Polling {len(HANDLES)} handles every {INTERVAL_MIN} min.")
    print(f"Logging to: {LOG_FILE}")
    print(f"Stop with: kill {__import__('os').getpid()}\n")

    cycle = 0
    while True:
        cycle += 1
        print(f"--- Cycle {cycle} ---")
        run_cycle()
        print(f"    Next check in {INTERVAL_MIN} min...\n")
        time.sleep(INTERVAL_MIN * 60)

if __name__ == "__main__":
    main()
