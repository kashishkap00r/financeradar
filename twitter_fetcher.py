"""
Dual-source Twitter/X ingestion pipeline.

Merges two independent sources:
  1. RSSHub (local) — freshest tweets, direct x.com links, rich content.
     Populated by running rsshub_local_fetch.py on your machine.
  2. Google RSS — zero-auth fallback, always available from GH Actions.

Falls back to a clean snapshot cache when both sources return nothing.
"""

import json
import os
import re
import tempfile
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from articles import IST_TZ, clean_twitter_title
from config import (
    FEED_THREAD_WORKERS,
    RSSHUB_CACHE_FILE,
    RSSHUB_CACHE_MAX_AGE_HOURS,
    TWITTER_CACHE_FILE,
    TWITTER_GOOGLE_MAX_ITEMS_PER_HANDLE,
    TWITTER_RESOLVE_WORKERS,
)
from feeds import fetch_feed
from twitter_signal import canonicalize_tweet_url, extract_tweet_parts, resolve_google_twitter_urls

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TWITTER_URL_CACHE_FILE = os.path.join(SCRIPT_DIR, "static", "twitter_url_cache.json")

X_PROFILE_HANDLE_RE = re.compile(r"^https?://(?:www\.)?x\.com/([^/?#]+)", re.IGNORECASE)
X_QUERY_HANDLE_RE = re.compile(r"(?:from:|site:x\.com/)([A-Za-z0-9_]+)", re.IGNORECASE)
RETWEET_PREFIX_RE = re.compile(r"^RT\s+@", re.IGNORECASE)


def _abs_path(path):
    if not path:
        return os.path.join(SCRIPT_DIR, TWITTER_CACHE_FILE)
    if os.path.isabs(path):
        return path
    return os.path.join(SCRIPT_DIR, path)


def _to_aware_datetime(dt):
    if not dt:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            return None
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _serialize_article(article):
    out = dict(article)
    dt = _to_aware_datetime(out.get("date"))
    out["date"] = dt.isoformat() if dt else None
    return out


def _deserialize_article(article):
    out = dict(article)
    out["date"] = _to_aware_datetime(out.get("date"))
    return out


def _load_json_file(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json_file(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="twitter-cache-", suffix=".json", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def load_twitter_snapshot(cache_file=None):
    """Load last-known good Twitter snapshot."""
    path = _abs_path(cache_file or TWITTER_CACHE_FILE)
    data = _load_json_file(path, {})
    if not isinstance(data, dict):
        return {"meta": {}, "items": []}
    items = [_deserialize_article(x) for x in data.get("items", []) if isinstance(x, dict)]
    meta = data.get("meta", {}) if isinstance(data.get("meta", {}), dict) else {}
    return {"meta": meta, "items": items}


def save_twitter_snapshot(payload, cache_file=None):
    """Persist clean Twitter payload for fallback usage."""
    path = _abs_path(cache_file or TWITTER_CACHE_FILE)
    safe_payload = {
        "generated_at": datetime.now(IST_TZ).isoformat(),
        "meta": payload.get("meta", {}),
        "items": [_serialize_article(x) for x in payload.get("items", [])],
    }
    _write_json_file(path, safe_payload)


def _extract_handle(feed_config):
    profile_url = (feed_config.get("url") or "").strip()
    match = X_PROFILE_HANDLE_RE.match(profile_url)
    if match:
        return match.group(1).strip()

    feed_url = (feed_config.get("feed") or "").strip()
    parsed = urllib.parse.urlparse(feed_url)
    query = (urllib.parse.parse_qs(parsed.query).get("q") or [""])[0]
    query_match = X_QUERY_HANDLE_RE.search(query)
    return query_match.group(1).strip() if query_match else ""


def _build_fetch_meta(source_mode, google_stats=None, rsshub_stats=None, warning=""):
    return {
        "source_mode": source_mode,
        "google_stats": google_stats or {},
        "rsshub_stats": rsshub_stats or {},
        "warning": warning,
        "generated_at": datetime.now(IST_TZ).isoformat(),
    }


def load_rsshub_cache(cache_file=None, max_age_hours=RSSHUB_CACHE_MAX_AGE_HOURS):
    """Load locally-generated RSSHub cache if fresh enough."""
    path = os.path.join(SCRIPT_DIR, cache_file or RSSHUB_CACHE_FILE)
    data = _load_json_file(path, {})
    if not isinstance(data, dict) or not data.get("items"):
        return [], {"status": "missing"}

    generated = data.get("generated_at", "")
    try:
        gen_dt = datetime.fromisoformat(generated)
        if gen_dt.tzinfo is None:
            gen_dt = gen_dt.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - gen_dt).total_seconds() / 3600
    except Exception:
        age_hours = 999

    if age_hours > max_age_hours:
        return [], {"status": "stale", "age_hours": round(age_hours, 1)}

    items = []
    for raw in data.get("items", []):
        if not isinstance(raw, dict):
            continue
        article = dict(raw)
        article["date"] = _to_aware_datetime(article.get("date"))
        article["category"] = "Twitter"
        article["source_mode"] = "rsshub"
        article["image"] = article.get("image", "")
        article["is_retweet"] = article.get("is_retweet", False)
        article["is_quote"] = article.get("is_quote", False)
        article["is_reply"] = article.get("is_reply", False)
        items.append(article)

    meta = data.get("meta", {})
    return items, {
        "status": "loaded",
        "age_hours": round(age_hours, 1),
        "items": len(items),
        "handles_ok": meta.get("handles_ok", 0),
    }


def normalize_and_filter_tweets(raw_items, allow_retweets=True, allow_replies=False):
    """Apply strict quality rules and dedupe Twitter item stream."""
    normalized = []
    seen = set()
    for item in raw_items:
        article = dict(item)
        article["title"] = clean_twitter_title(article.get("title", "")).strip()
        article["link"] = canonicalize_tweet_url(article.get("link", ""))
        article["date"] = _to_aware_datetime(article.get("date"))

        _, tweet_id = extract_tweet_parts(article.get("link", ""))
        article["tweet_id"] = (article.get("tweet_id") or tweet_id or "").strip()
        if not article["tweet_id"]:
            continue
        if not article["link"].startswith("https://x.com/"):
            continue
        if "/status/" not in article["link"]:
            continue

        if not article.get("title"):
            continue

        if article.get("is_reply") and not allow_replies:
            continue
        if article.get("is_retweet") and not allow_retweets:
            continue

        dedupe_key = article["tweet_id"]
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(article)

    normalized.sort(
        key=lambda item: (_to_aware_datetime(item.get("date")) or datetime(1970, 1, 1, tzinfo=timezone.utc)),
        reverse=True,
    )
    return normalized


def fetch_twitter_google(twitter_feeds, logger=None):
    """Fetch tweets from Google RSS feeds."""
    stats = {
        "feeds_total": len(twitter_feeds),
        "feeds_ok": 0,
        "feeds_failed": 0,
        "items_raw": 0,
        "resolve_attempted": 0,
        "resolve_resolved": 0,
        "resolve_cache_hits": 0,
    }
    items = []
    if not twitter_feeds:
        return [], stats

    worker_count = max(1, min(FEED_THREAD_WORKERS, len(twitter_feeds)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(fetch_feed, feed): feed for feed in twitter_feeds}
        for future in as_completed(futures):
            try:
                articles = future.result() or []
            except Exception:
                articles = []
            if not articles:
                stats["feeds_failed"] += 1
                continue

            stats["feeds_ok"] += 1
            for article in articles[:TWITTER_GOOGLE_MAX_ITEMS_PER_HANDLE]:
                row = dict(article)
                row["source_mode"] = "google"
                row["is_retweet"] = bool(RETWEET_PREFIX_RE.match(row.get("title", "").strip()))
                row["is_reply"] = row.get("title", "").strip().startswith("@")
                items.append(row)
            stats["items_raw"] += min(len(articles), TWITTER_GOOGLE_MAX_ITEMS_PER_HANDLE)

    items, resolve_stats = resolve_google_twitter_urls(
        items,
        TWITTER_URL_CACHE_FILE,
        logger=logger,
        max_workers=TWITTER_RESOLVE_WORKERS,
    )
    stats["resolve_attempted"] = resolve_stats.get("attempted", 0)
    stats["resolve_resolved"] = resolve_stats.get("resolved", 0)
    stats["resolve_cache_hits"] = resolve_stats.get("cache_hits", 0)
    return items, stats


def fetch_twitter_articles(twitter_feeds, logger=None):
    """Dual-source Twitter ingestion: RSSHub cache + Google RSS + snapshot fallback."""
    feeds = [f for f in twitter_feeds if (f.get("category") or "") == "Twitter"]
    handles = sorted({h.lower() for h in (_extract_handle(feed) for feed in feeds) if h})

    snapshot = load_twitter_snapshot()
    if not handles:
        cached = normalize_and_filter_tweets(snapshot.get("items", []), allow_retweets=True, allow_replies=False)
        meta = _build_fetch_meta(source_mode="snapshot", warning="no_twitter_handles_configured")
        return cached, meta

    # --- Source 1: RSSHub local cache (populated by rsshub_local_fetch.py) ---
    rsshub_items, rsshub_stats = load_rsshub_cache()
    if logger and rsshub_stats.get("status") == "loaded":
        logger.info(f"RSSHub cache: {rsshub_stats['items']} items, {rsshub_stats['age_hours']}h old")
    elif logger:
        logger.info(f"RSSHub cache: {rsshub_stats.get('status', 'unavailable')}")

    # --- Source 2: Google RSS (always runs as fallback) ---
    google_items, google_stats = fetch_twitter_google(feeds, logger=logger)

    # --- Merge: combine both sources, deduplicate by tweet_id ---
    # RSSHub items get priority (fresher, direct links, richer content)
    merged = []
    seen_ids = set()

    for item in rsshub_items:
        tid = (item.get("tweet_id") or "").strip()
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            merged.append(item)

    for item in google_items:
        tid = (item.get("tweet_id") or "").strip()
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            merged.append(item)

    cleaned = normalize_and_filter_tweets(merged, allow_retweets=True, allow_replies=False)

    # --- Source tracking ---
    rsshub_count = sum(1 for c in cleaned if c.get("source_mode") == "rsshub")
    google_count = sum(1 for c in cleaned if c.get("source_mode") == "google")

    if cleaned:
        source_mode = "rsshub+google" if rsshub_count and google_count else (
            "rsshub" if rsshub_count else "google"
        )
        meta = _build_fetch_meta(
            source_mode=source_mode,
            google_stats=google_stats,
            rsshub_stats=rsshub_stats,
        )
        # Log source distribution
        if logger:
            logger.info(f"Twitter sources: rsshub={rsshub_count}, google={google_count}, total={len(cleaned)}")
            if rsshub_stats.get("status") == "loaded" and rsshub_count == 0:
                logger.warning("RSSHub cache was loaded but 0 items survived merge — may be stale or all duplicates")

        save_twitter_snapshot({"meta": meta, "items": cleaned})
        return cleaned, meta

    # --- Fallback: snapshot cache ---
    cached = normalize_and_filter_tweets(snapshot.get("items", []), allow_retweets=True, allow_replies=False)
    meta = _build_fetch_meta(
        source_mode="snapshot",
        google_stats=google_stats,
        rsshub_stats=rsshub_stats,
        warning="all_sources_empty_using_snapshot",
    )
    return cached, meta
