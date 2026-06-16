"""
Fetcher for the Companies tab, sourced from Tipsheet (https://tipsheet.markets).

Tipsheet turns BSE/NSE filings into annotated notes tagged with a market-cap
tier. Its `search-index.json` endpoint is the only public source that exposes
the cap tier per filing, so that is what we consume here.

Mirrors the resilient live-fetch-with-cache-fallback pattern of paper_fetcher.py:
a successful fetch refreshes static/companies_cache.json; on failure or empty
response the caller loads the cache so a CI hiccup never blanks the tab.
"""

import json
import urllib.request
from datetime import datetime, timedelta

from articles import IST_TZ
from config import (
    COMPANIES_FETCH_TIMEOUT,
    COMPANIES_FRESHNESS_DAYS,
    COMPANIES_MAX_ITEMS,
    COMPANIES_SEARCH_INDEX_URL,
    COMPANIES_SITE_BASE,
    DEFAULT_USER_AGENT,
)

COMPANIES_FEED_ID = "tipsheet"
COMPANIES_SOURCE_LABEL = "Tipsheet"

# Canonical cap-tier labels as published by Tipsheet (used for filtering/UI).
CAP_TIERS = ["Mega cap", "Large cap", "Mid cap", "Small cap", "Micro cap", "Nano cap"]


def _parse_tipsheet_date(raw):
    """Parse Tipsheet's naive 'YYYY-MM-DD HH:MM:SS' timestamp as IST-aware."""
    if not raw:
        return None
    raw = str(raw).strip()
    # The `t` field is naive local (IST); `published`-style ISO may also appear.
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=IST_TZ)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=IST_TZ)
    except ValueError:
        return None


def _absolute_url(path):
    if not path:
        return ""
    path = str(path).strip()
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return COMPANIES_SITE_BASE + path


def _extract_items(payload):
    """search-index.json may be a bare array or wrapped in an object."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            return payload["items"]
        # Fall back to the first list value present.
        for value in payload.values():
            if isinstance(value, list):
                return value
    return []


def parse_companies(payload, now=None):
    """Map the search-index payload into normalized company-filing objects."""
    now = now or datetime.now(IST_TZ)
    cutoff = now - timedelta(days=COMPANIES_FRESHNESS_DAYS)

    companies = []
    seen_links = set()
    for item in _extract_items(payload):
        if not isinstance(item, dict):
            continue
        if item.get("s") != "filing":
            continue

        title = (item.get("h") or "").strip()
        link = _absolute_url(item.get("u"))
        if not title or not link:
            continue

        link_key = link.lower().rstrip("/")
        if link_key in seen_links:
            continue

        date_value = _parse_tipsheet_date(item.get("t"))
        if date_value is not None and date_value < cutoff:
            continue

        try:
            score = int(item.get("sc")) if item.get("sc") is not None else 0
        except (TypeError, ValueError):
            score = 0

        seen_links.add(link_key)
        companies.append(
            {
                "title": title,
                "link": link,
                "source": COMPANIES_SOURCE_LABEL,
                "source_url": link,
                "publisher": COMPANIES_SOURCE_LABEL,
                "description": "",
                "date": date_value,
                "time": date_value.strftime("%I:%M %p").lstrip("0") if date_value else "",
                "ticker": (item.get("sym") or "").strip(),
                "sector": (item.get("sec") or "").strip(),
                "cap": (item.get("cap") or "").strip(),
                "category": (item.get("cat") or "").strip(),
                "score": score,
                "feed_id": COMPANIES_FEED_ID,
            }
        )

    # Default order: most consequential first (score desc), newest as tiebreak.
    epoch_ist = datetime(1970, 1, 1, tzinfo=IST_TZ)
    companies.sort(
        key=lambda c: (
            -c.get("score", 0),
            -((c.get("date") or epoch_ist).timestamp()),
        )
    )
    return companies[:COMPANIES_MAX_ITEMS]


def fetch_companies(url=COMPANIES_SEARCH_INDEX_URL, timeout=COMPANIES_FETCH_TIMEOUT, now=None):
    """Fetch and parse Tipsheet filings. Returns a list (empty on failure)."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    return parse_companies(payload, now=now)


def save_companies_cache(cache_file, companies):
    """Persist companies to cache with ISO datetime serialization."""
    payload = {
        "generated_at": datetime.now(IST_TZ).isoformat(),
        "companies": [
            {**c, "date": c["date"].isoformat() if c.get("date") else None}
            for c in (companies or [])
        ],
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload["generated_at"]


def load_companies_cache(cache_file):
    """Load cached companies; returns (companies, generated_at)."""
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return [], ""

    if isinstance(payload, list):
        raw_items, generated_at = payload, ""
    else:
        raw_items = payload.get("companies", [])
        generated_at = payload.get("generated_at", "")

    companies = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        company = dict(item)
        date_raw = company.get("date")
        if date_raw:
            try:
                company["date"] = datetime.fromisoformat(date_raw)
            except ValueError:
                company["date"] = None
        else:
            company["date"] = None
        companies.append(company)
    return companies, generated_at


if __name__ == "__main__":
    from collections import Counter

    from config import COMPANIES_CACHE_FILE

    items = fetch_companies()
    print(f"Fetched {len(items)} company filings from Tipsheet")
    if items:
        caps = Counter(c.get("cap") or "?" for c in items)
        print("By cap tier:", dict(caps))
        save_companies_cache(COMPANIES_CACHE_FILE, items)
        print(f"Saved cache -> {COMPANIES_CACHE_FILE}")
