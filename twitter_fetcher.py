"""
Dedicated Twitter/X ingestion pipeline.

Primary mode uses authenticated account-pool scraping (twscrape).
If auth fails for consecutive cycles, emergency mode uses Google RSS feeds.
On full failure, last known-good snapshot is served.
"""

import asyncio
import json
import os
import re
import tempfile
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from articles import IST_TZ, clean_twitter_title
from config import (
    FEED_THREAD_WORKERS,
    TWITTER_ACCOUNTS_ENV_VAR,
    TWITTER_AUTH_LOOKBACK_HOURS,
    TWITTER_AUTH_MAX_TWEETS_PER_HANDLE,
    TWITTER_CACHE_FILE,
    TWITTER_EMERGENCY_MAX_ITEMS_PER_HANDLE,
    TWITTER_FAILS_BEFORE_EMERGENCY,
    TWITTER_PRIMARY_MODE,
    TWITTER_RESOLVE_WORKERS,
)
from feeds import fetch_feed
from twitter_signal import canonicalize_tweet_url, extract_tweet_parts, resolve_google_twitter_urls

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TWITTER_URL_CACHE_FILE = os.path.join(SCRIPT_DIR, "static", "twitter_url_cache.json")
TWITTER_USER_CACHE_FILE = os.path.join(SCRIPT_DIR, "static", "twitter_user_cache.json")

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


def _tweet_attr(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _tweet_to_article(tweet, feed_cfg, source_mode):
    user = _tweet_attr(tweet, "user")
    username = (_tweet_attr(user, "username", "") or "").strip() or _extract_handle(feed_cfg)
    tweet_id = str(_tweet_attr(tweet, "id_str", "") or _tweet_attr(tweet, "id", "") or "").strip()
    link = canonicalize_tweet_url(_tweet_attr(tweet, "url", ""))
    if not link and username and tweet_id.isdigit():
        link = f"https://x.com/{username}/status/{tweet_id}"
    link = canonicalize_tweet_url(link)

    _, extracted_id = extract_tweet_parts(link)
    if not tweet_id:
        tweet_id = extracted_id

    raw_title = (_tweet_attr(tweet, "rawContent", "") or "").strip()
    title = clean_twitter_title(raw_title).strip() if raw_title else ""

    is_reply = _tweet_attr(tweet, "inReplyToTweetId") is not None
    is_retweet = _tweet_attr(tweet, "retweetedTweet") is not None or bool(RETWEET_PREFIX_RE.match(raw_title))

    return {
        "title": title or raw_title or "Untitled tweet",
        "link": link,
        "date": _to_aware_datetime(_tweet_attr(tweet, "date")),
        "description": (title or raw_title)[:300],
        "source": feed_cfg.get("name", f"{username} (X)"),
        "source_url": feed_cfg.get("url", f"https://x.com/{username}"),
        "category": "Twitter",
        "publisher": feed_cfg.get("publisher", username),
        "feed_id": feed_cfg.get("id", ""),
        "tweet_id": tweet_id,
        "is_reply": is_reply,
        "is_retweet": is_retweet,
        "source_mode": source_mode,
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


def _parse_accounts_cfg(accounts_cfg):
    parsed = []
    for row in accounts_cfg or []:
        if not isinstance(row, dict):
            continue
        username = str(row.get("username") or "").strip()
        if not username:
            continue
        if row.get("active") is False:
            continue

        cookies = row.get("cookies") or row.get("cookie") or row.get("cookie_string")
        if isinstance(cookies, dict):
            cookies = json.dumps(cookies, separators=(",", ":"))
        elif cookies is not None:
            cookies = str(cookies)

        parsed.append(
            {
                "username": username,
                "password": str(row.get("password") or "x"),
                "email": str(row.get("email") or f"{username}@example.com"),
                "email_password": str(row.get("email_password") or "x"),
                "proxy": (str(row.get("proxy")).strip() if row.get("proxy") else None),
                "cookies": cookies,
                "mfa_code": (str(row.get("mfa_code")).strip() if row.get("mfa_code") else None),
            }
        )
    return parsed


def _load_accounts_from_env():
    raw = os.getenv(TWITTER_ACCOUNTS_ENV_VAR, "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = payload.get("accounts", [])
    if not isinstance(payload, list):
        return []
    return _parse_accounts_cfg(payload)


def _load_user_cache():
    data = _load_json_file(TWITTER_USER_CACHE_FILE, {})
    return {str(k).lower(): int(v) for k, v in data.items() if str(v).isdigit()}


def _save_user_cache(cache):
    _write_json_file(TWITTER_USER_CACHE_FILE, cache)


async def _fetch_twitter_auth_async(handles, since_dt, accounts_cfg, feed_by_handle):
    from twscrape import API, gather

    fd, db_path = tempfile.mkstemp(prefix="financeradar-twscrape-", suffix=".db")
    os.close(fd)
    user_cache = _load_user_cache()
    stats = {
        "handles_total": len(handles),
        "handles_ok": 0,
        "handles_failed": 0,
        "tweets_raw": 0,
        "tweets_after_lookback": 0,
        "accounts_active": 0,
        "error": "",
    }
    items = []

    try:
        api = API(db_path)

        for row in accounts_cfg:
            await api.pool.add_account(
                row["username"],
                row["password"],
                row["email"],
                row["email_password"],
                proxy=row.get("proxy"),
                cookies=row.get("cookies"),
                mfa_code=row.get("mfa_code"),
            )

        all_accounts = await api.pool.get_all()
        to_login = [a.username for a in all_accounts if not a.active]
        if to_login:
            await api.pool.login_all(to_login)

        all_accounts = await api.pool.get_all()
        stats["accounts_active"] = len([a for a in all_accounts if a.active])
        if stats["accounts_active"] == 0:
            stats["error"] = "no_active_accounts"
            return [], stats

        for handle in handles:
            key = handle.lower()
            feed_cfg = feed_by_handle.get(key, {})
            user_id = user_cache.get(key)

            if not user_id:
                try:
                    user = await api.user_by_login(handle)
                except Exception:
                    user = None
                if not user or not _tweet_attr(user, "id"):
                    stats["handles_failed"] += 1
                    continue
                user_id = int(_tweet_attr(user, "id"))
                user_cache[key] = user_id

            tweets = None
            try:
                tweets = await gather(
                    api.user_tweets_and_replies(user_id, limit=TWITTER_AUTH_MAX_TWEETS_PER_HANDLE)
                )
            except Exception:
                # Retry once with refreshed user id.
                try:
                    user = await api.user_by_login(handle)
                    if user and _tweet_attr(user, "id"):
                        user_id = int(_tweet_attr(user, "id"))
                        user_cache[key] = user_id
                        tweets = await gather(
                            api.user_tweets_and_replies(user_id, limit=TWITTER_AUTH_MAX_TWEETS_PER_HANDLE)
                        )
                except Exception:
                    tweets = None

            if tweets is None:
                stats["handles_failed"] += 1
                continue

            stats["handles_ok"] += 1
            stats["tweets_raw"] += len(tweets)
            for tw in tweets:
                article = _tweet_to_article(tw, feed_cfg, source_mode="auth")
                dt = _to_aware_datetime(article.get("date"))
                if since_dt and dt and dt < since_dt:
                    continue
                stats["tweets_after_lookback"] += 1
                items.append(article)

        _save_user_cache(user_cache)
        return items, stats
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


def _run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def fetch_twitter_auth(handles, since_dt, accounts_cfg, feed_by_handle=None):
    """Fetch tweets via authenticated account pool."""
    feed_by_handle = feed_by_handle or {}
    if not accounts_cfg:
        return [], {"error": "missing_accounts", "handles_total": len(handles)}
    try:
        return _run_async(_fetch_twitter_auth_async(handles, since_dt, accounts_cfg, feed_by_handle))
    except ImportError:
        return [], {"error": "twscrape_not_installed", "handles_total": len(handles)}
    except Exception as exc:
        return [], {"error": f"auth_fetch_failed:{type(exc).__name__}", "handles_total": len(handles)}


def fetch_twitter_google_emergency(twitter_feeds, logger=None):
    """Fetch tweets from Google RSS feeds for emergency mode."""
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
            feed_cfg = futures[future]
            try:
                articles = future.result() or []
            except Exception:
                articles = []
            if not articles:
                stats["feeds_failed"] += 1
                continue

            stats["feeds_ok"] += 1
            for article in articles[:TWITTER_EMERGENCY_MAX_ITEMS_PER_HANDLE]:
                row = dict(article)
                row["source_mode"] = "google_emergency"
                row["is_retweet"] = bool(RETWEET_PREFIX_RE.match(row.get("title", "").strip()))
                # Google feed doesn't expose reliable reply metadata.
                row["is_reply"] = row.get("title", "").strip().startswith("@")
                items.append(row)
            stats["items_raw"] += min(len(articles), TWITTER_EMERGENCY_MAX_ITEMS_PER_HANDLE)

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


def _build_fetch_meta(
    source_mode,
    consecutive_auth_failures,
    auth_stats=None,
    emergency_stats=None,
    warning="",
):
    return {
        "source_mode": source_mode,
        "consecutive_auth_failures": max(0, int(consecutive_auth_failures or 0)),
        "auth_stats": auth_stats or {},
        "emergency_stats": emergency_stats or {},
        "warning": warning,
        "generated_at": datetime.now(IST_TZ).isoformat(),
    }


def fetch_twitter_articles(twitter_feeds, logger=None):
    """Run full Twitter ingestion orchestration."""
    feeds = [f for f in twitter_feeds if (f.get("category") or "") == "Twitter"]
    feed_by_handle = {}
    for feed in feeds:
        handle = _extract_handle(feed)
        if handle:
            feed_by_handle[handle.lower()] = feed
    handles = sorted(feed_by_handle.keys())

    snapshot = load_twitter_snapshot()
    previous_failures = int(snapshot.get("meta", {}).get("consecutive_auth_failures") or 0)

    if not handles:
        meta = _build_fetch_meta(
            source_mode="snapshot",
            consecutive_auth_failures=previous_failures,
            warning="no_twitter_handles_configured",
        )
        return snapshot.get("items", []), meta

    if TWITTER_PRIMARY_MODE == "google_only":
        emergency_items, emergency_stats = fetch_twitter_google_emergency(feeds, logger=logger)
        cleaned = normalize_and_filter_tweets(emergency_items, allow_retweets=True, allow_replies=False)
        if cleaned:
            meta = _build_fetch_meta(
                source_mode="google_emergency",
                consecutive_auth_failures=previous_failures,
                emergency_stats=emergency_stats,
            )
            save_twitter_snapshot({"meta": meta, "items": cleaned})
            return cleaned, meta

        cached = normalize_and_filter_tweets(snapshot.get("items", []), allow_retweets=True, allow_replies=False)
        meta = _build_fetch_meta(
            source_mode="snapshot",
            consecutive_auth_failures=previous_failures,
            emergency_stats=emergency_stats,
            warning="google_only_mode_empty_using_snapshot",
        )
        return cached, meta

    since_dt = datetime.now(timezone.utc) - timedelta(hours=TWITTER_AUTH_LOOKBACK_HOURS)
    accounts_cfg = _load_accounts_from_env()
    auth_items, auth_stats = fetch_twitter_auth(
        handles=handles,
        since_dt=since_dt,
        accounts_cfg=accounts_cfg,
        feed_by_handle=feed_by_handle,
    )
    cleaned_auth = normalize_and_filter_tweets(auth_items, allow_retweets=True, allow_replies=False)
    if cleaned_auth:
        meta = _build_fetch_meta(
            source_mode="auth",
            consecutive_auth_failures=0,
            auth_stats=auth_stats,
        )
        save_twitter_snapshot({"meta": meta, "items": cleaned_auth})
        return cleaned_auth, meta

    failures_now = previous_failures + 1
    if failures_now >= TWITTER_FAILS_BEFORE_EMERGENCY:
        emergency_items, emergency_stats = fetch_twitter_google_emergency(feeds, logger=logger)
        cleaned_emergency = normalize_and_filter_tweets(
            emergency_items,
            allow_retweets=True,
            allow_replies=False,
        )
        if cleaned_emergency:
            meta = _build_fetch_meta(
                source_mode="google_emergency",
                consecutive_auth_failures=failures_now,
                auth_stats=auth_stats,
                emergency_stats=emergency_stats,
            )
            save_twitter_snapshot({"meta": meta, "items": cleaned_emergency})
            return cleaned_emergency, meta

        cached = normalize_and_filter_tweets(snapshot.get("items", []), allow_retweets=True, allow_replies=False)
        meta = _build_fetch_meta(
            source_mode="snapshot",
            consecutive_auth_failures=failures_now,
            auth_stats=auth_stats,
            emergency_stats=emergency_stats,
            warning="auth_and_emergency_empty_using_snapshot",
        )
        return cached, meta

    cached = normalize_and_filter_tweets(snapshot.get("items", []), allow_retweets=True, allow_replies=False)
    meta = _build_fetch_meta(
        source_mode="snapshot",
        consecutive_auth_failures=failures_now,
        auth_stats=auth_stats,
        warning="auth_empty_waiting_for_emergency_threshold_using_snapshot",
    )
    return cached, meta
