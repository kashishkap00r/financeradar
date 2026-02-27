"""
Twitter signal processing pipeline.

Builds two tweet lanes:
- Full Stream: cleaned broad feed
- High Signal: tighter top 25 (24h, no retweets), AI-ranked with fallback
"""

import json
import os
import re
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from articles import IST_TZ, clean_twitter_title
from config import (
    AI_RANKER_GEMINI_TIMEOUT,
    AI_RANKER_OPENROUTER_TIMEOUT,
)

SSL_CONTEXT = ssl.create_default_context()
GOOGLE_NEWS_ARTICLE_RE = re.compile(r"^https?://news\.google\.com/rss/articles/([A-Za-z0-9_-]+)")
TWEET_URL_RE = re.compile(
    r"^https?://(?:www\.|m\.|mobile\.)?(?:x|twitter)\.com/([^/]+)/status/(\d+)",
    re.IGNORECASE,
)
TRAILING_MEDIA_SEGMENT_RE = re.compile(r"/(?:photo|video)/\d+$", re.IGNORECASE)
HTML_ATTR_RE = {
    "id": re.compile(r'data-n-a-id="([^"]+)"'),
    "ts": re.compile(r'data-n-a-ts="([^"]+)"'),
    "sg": re.compile(r'data-n-a-sg="([^"]+)"'),
}
NOISE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\blive\b",
        r"\bmarket snapshot\b",
        r"\bclosing bell\b",
        r"\bopening bell\b",
        r"\btop gainers?\b",
        r"\btop losers?\b",
        r"\bstocks?\s+in\s+focus\b",
        r"\bbuy or sell\b",
        r"\btarget price\b",
    )
]
ANALYSIS_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bwhy\b",
        r"\bhow\b",
        r"\banalysis\b",
        r"\bexplained\b",
        r"\boutlook\b",
        r"\bpolicy\b",
        r"\bstrategy\b",
        r"\brisk\b",
        r"\binsight\b",
        r"\breport\b",
        r"\bthesis\b",
    )
]


def canonicalize_tweet_url(url):
    """Normalize tweet URL to stable x.com form for dedupe and thread handling."""
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception:
        return url.strip()

    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host in ("mobile.twitter.com", "m.twitter.com", "twitter.com"):
        host = "x.com"

    path = (parsed.path or "").rstrip("/")
    path = TRAILING_MEDIA_SEGMENT_RE.sub("", path)
    if host == "x.com":
        return f"https://x.com{path}"
    if host:
        return f"https://{host}{path}"
    return url.strip()


def extract_tweet_parts(url):
    """Return (handle, tweet_id) from a canonical tweet URL."""
    match = TWEET_URL_RE.match(url or "")
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def _canonical_google_key(url):
    """Stable cache key for Google RSS article links."""
    token_match = GOOGLE_NEWS_ARTICLE_RE.match(url or "")
    if token_match:
        return f"google:{token_match.group(1)}"
    return (url or "").strip()


def _fetch_google_decode_params(article_url, timeout=12):
    """Fetch Google RSS article page and extract id/ts/signature attributes."""
    req = urllib.request.Request(
        article_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT) as response:
        html = response.read().decode("utf-8", errors="ignore")

    found = {}
    for key, regex in HTML_ATTR_RE.items():
        match = regex.search(html)
        if match:
            found[key] = match.group(1).strip()
    if not found.get("id") or not found.get("ts") or not found.get("sg"):
        return None
    return found


def _resolve_google_article_via_batchexecute(article_id, ts, signature, timeout=12):
    """Resolve Google RSS article id to direct link via batch execute endpoint."""
    payload = [
        "garturlreq",
        [
            [
                "en-US",
                "US",
                ["FINANCE_TOP_INDICES", "WEB_TEST_1_0_0"],
                None,
                None,
                1,
                1,
                "US:en",
                None,
                180,
                None,
                None,
                None,
                None,
                None,
                0,
                None,
                None,
                [1608992183, 723341000],
            ],
            "en-US",
            "US",
            1,
            [2, 3, 4, 8],
            1,
            0,
            "655000234",
            0,
            0,
            None,
            0,
        ],
        article_id,
        int(ts),
        signature,
    ]
    outer = [[["Fbv4je", json.dumps(payload, separators=(",", ":")), None, "generic"]]]
    body = "f.req=" + urllib.parse.quote(json.dumps(outer, separators=(",", ":")))
    req = urllib.request.Request(
        "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je",
        data=body.encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        },
    )
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT) as response:
        raw = response.read().decode("utf-8", errors="ignore")

    for line in raw.splitlines():
        if not line.strip().startswith("[["):
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not parsed or not isinstance(parsed, list):
            continue
        slot = parsed[0]
        if len(slot) < 3:
            continue
        try:
            inner = json.loads(slot[2])
        except Exception:
            continue
        if isinstance(inner, list) and len(inner) >= 2 and inner[0] == "garturlres":
            resolved = (inner[1] or "").strip()
            if resolved:
                return resolved
    return ""


def resolve_google_twitter_urls(articles, cache_file, logger=None, max_workers=8):
    """Resolve Google News tweet links to direct x.com URLs with persistent cache."""
    stats = {"attempted": 0, "resolved": 0, "cache_hits": 0, "failed": 0}
    if not articles:
        return articles, stats

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)
        if not isinstance(cache, dict):
            cache = {}
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}

    def _resolve_single(url):
        key = _canonical_google_key(url)
        if key in cache:
            cached = canonicalize_tweet_url(cache.get(key, ""))
            _, tweet_id = extract_tweet_parts(cached)
            if cached and not tweet_id:
                cached = ""
                cache[key] = ""
            return url, cached, True
        try:
            params = _fetch_google_decode_params(url)
            if not params:
                cache[key] = ""
                return url, "", False
            resolved = _resolve_google_article_via_batchexecute(
                params["id"], params["ts"], params["sg"]
            )
            resolved = canonicalize_tweet_url(resolved or "")
            _, tweet_id = extract_tweet_parts(resolved)
            if not tweet_id:
                resolved = ""
            cache[key] = resolved
            return url, resolved, False
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            cache[key] = ""
            return url, "", False
        except Exception:
            cache[key] = ""
            return url, "", False

    targets = []
    for item in articles:
        link = (item.get("link") or "").strip()
        if GOOGLE_NEWS_ARTICLE_RE.match(link):
            targets.append(link)
    unique_targets = sorted(set(targets))
    stats["attempted"] = len(unique_targets)

    if unique_targets:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_resolve_single, url): url for url in unique_targets}
            results = {}
            for future in as_completed(futures):
                original_url, resolved_url, from_cache = future.result()
                if from_cache:
                    stats["cache_hits"] += 1
                if resolved_url:
                    stats["resolved"] += 1
                else:
                    stats["failed"] += 1
                results[original_url] = resolved_url

        for item in articles:
            link = (item.get("link") or "").strip()
            if link in results and results[link]:
                item["link"] = canonicalize_tweet_url(results[link])

    # Persist cache atomically.
    try:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(cache_file), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        os.replace(tmp, cache_file)
    except Exception as exc:
        if logger:
            logger.warn("Twitter URL cache", f"could not write: {exc}")

    return articles, stats


def _parse_item_date(value):
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST_TZ)
    return dt.astimezone(IST_TZ)


def _title_similarity_key(title):
    cleaned = clean_twitter_title(title or "")
    cleaned = cleaned.lower().strip()
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = re.sub(r"@[a-z0-9_]+", " ", cleaned)
    cleaned = re.sub(r"#[a-z0-9_]+", " ", cleaned)
    cleaned = re.sub(r"\b\d+/\d+\b", " ", cleaned)
    cleaned = re.sub(r"\b\d+\b", " ", cleaned)
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _thread_signature(title):
    key = _title_similarity_key(title)
    words = key.split()
    return " ".join(words[:12])


def _is_retweet_title(title):
    return bool(re.match(r"^rt\s+@", (title or "").strip(), flags=re.IGNORECASE))


def _is_quote_style(title):
    stripped = (title or "").strip()
    return stripped.startswith(("“", "”", "\""))


def _is_reply_like(title):
    return (title or "").strip().startswith("@")


def _article_identity(item):
    url = (item.get("link") or "").strip()
    if url:
        return f"url::{url.lower()}"
    title = _title_similarity_key(item.get("title", ""))
    source = (item.get("publisher") or item.get("source") or "").lower()
    return f"title::{source}|{title}"


def _cluster_thread_bursts(items):
    """Collapse tweet bursts from same source into single representative items."""
    clusters = []
    for item in items:
        source = (item.get("publisher") or item.get("source") or "").strip()
        date = item.get("_parsed_date")
        signature = item.get("_thread_signature") or ""
        sim_key = item.get("_sim_key") or ""
        attached = False

        for cluster in clusters:
            if cluster["source"] != source:
                continue
            if not date or not cluster["date"]:
                continue
            if abs((cluster["date"] - date).total_seconds()) > 18 * 3600:
                continue
            if signature and cluster["signature"] and signature == cluster["signature"]:
                cluster["items"].append(item)
                attached = True
                break
            ratio = SequenceMatcher(None, sim_key, cluster["sim_key"]).ratio() if sim_key and cluster["sim_key"] else 0
            if ratio >= 0.76:
                cluster["items"].append(item)
                attached = True
                break

        if not attached:
            clusters.append({
                "source": source,
                "signature": signature,
                "sim_key": sim_key,
                "date": date,
                "items": [item],
            })

    representatives = []
    for cluster in clusters:
        # Representatives are the newest items (input is newest-first, so first item wins).
        rep = dict(cluster["items"][0])
        rep["thread_collapsed_count"] = max(0, len(cluster["items"]) - 1)
        rep["is_thread_cluster"] = len(cluster["items"]) > 1
        representatives.append(rep)
    return representatives


def _score_tweet(item, now):
    title = (item.get("title") or "").strip()
    lower = title.lower()
    dt = item.get("_parsed_date")
    hours_old = 999.0
    if dt:
        hours_old = max(0.0, (now - dt).total_seconds() / 3600.0)

    score = 0.0
    score += max(0.0, 42.0 - hours_old) * 1.6
    score += min(len(lower), 280) / 35.0
    if item.get("is_quote"):
        score += 0.8
    if item.get("thread_collapsed_count", 0) > 0:
        score += 1.0

    analysis_hits = sum(1 for rx in ANALYSIS_PATTERNS if rx.search(lower))
    noise_hits = sum(1 for rx in NOISE_PATTERNS if rx.search(lower))
    score += 2.2 * analysis_hits
    score -= 3.0 * noise_hits

    if item.get("is_reply_like"):
        score -= 3.0
    if _is_retweet_title(title):
        score -= 4.0

    return score


def _fallback_high_signal(candidates, now, target_count=25):
    scored = []
    for item in candidates:
        enriched = dict(item)
        enriched["_score"] = _score_tweet(item, now)
        scored.append(enriched)
    scored.sort(
        key=lambda x: (
            x.get("_score", 0.0),
            x.get("_parsed_date") or datetime.min.replace(tzinfo=IST_TZ),
        ),
        reverse=True,
    )
    return [dict(item) for item in scored[:target_count]]


def _parse_json_response(text):
    text = (text or "").strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()
        else:
            text = text.replace("```json", "").replace("```", "").strip()
    if not text.startswith("["):
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    text = re.sub(r",\s*\]", "]", text)
    text = re.sub(r",\s*\}", "}", text)
    return json.loads(text)


def _call_gemini_rank(prompt):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-3-flash-preview:generateContent?key={api_key}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4096,
            "response_mime_type": "application/json",
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=AI_RANKER_GEMINI_TIMEOUT, context=SSL_CONTEXT) as response:
        result = json.loads(response.read().decode("utf-8"))
    text = result["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_json_response(text)


def _call_openrouter_rank(prompt):
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps({
            "model": "deepseek/deepseek-v3.2",
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://financeradar.kashishkapoor.com",
            "X-Title": "FinanceRadar Twitter Signal",
        },
    )
    with urllib.request.urlopen(req, timeout=AI_RANKER_OPENROUTER_TIMEOUT, context=SSL_CONTEXT) as response:
        result = json.loads(response.read().decode("utf-8"))
    return _parse_json_response(result["choices"][0]["message"]["content"])


def _ai_rank_high_signal(seed_items, target_count=25):
    if not seed_items:
        return []
    prompt_lines = []
    for idx, item in enumerate(seed_items, start=1):
        title = (item.get("title") or "").replace("\n", " ").strip()
        source = item.get("publisher") or item.get("source") or "Unknown"
        prompt_lines.append(f'{idx}. "{title}" [{source}]')
    prompt = f"""You are selecting high-signal finance tweets for an informed investor audience in India.

Input:
{chr(10).join(prompt_lines)}

Task:
- Pick exactly {target_count} strongest items.
- Prefer explanatory, thesis-driven, policy/market-structure, and non-obvious insights.
- Avoid repetitive chatter, routine market snapshots, and promotional fluff.

Output format:
Return ONLY a JSON array of objects with keys:
- id: integer (the input row number)
- confidence: one of ["high","medium","low"]
No markdown, no commentary.
"""
    ranked = None
    try:
        ranked = _call_gemini_rank(prompt)
    except Exception:
        try:
            ranked = _call_openrouter_rank(prompt)
        except Exception:
            return []
    if not isinstance(ranked, list):
        return []
    picked = []
    seen = set()
    for obj in ranked:
        if not isinstance(obj, dict):
            continue
        try:
            idx = int(obj.get("id"))
        except (TypeError, ValueError):
            continue
        if idx < 1 or idx > len(seed_items) or idx in seen:
            continue
        seen.add(idx)
        item = dict(seed_items[idx - 1])
        item["rank_confidence"] = (obj.get("confidence") or "").strip().lower()
        picked.append(item)
        if len(picked) >= target_count:
            break
    return picked


def build_twitter_lanes(twitter_articles, now=None, target_count=25, high_window_hours=24):
    """Build cleaned Full Stream + High Signal tweet lanes."""
    now = now or datetime.now(IST_TZ)
    prepared = []
    seen = set()
    for raw in twitter_articles:
        title = clean_twitter_title(raw.get("title", "")).strip()
        if not title:
            continue
        item = dict(raw)
        item["title"] = title
        item["link"] = canonicalize_tweet_url(item.get("link", ""))
        handle, tweet_id = extract_tweet_parts(item.get("link", ""))
        item["tweet_handle"] = handle
        item["tweet_id"] = tweet_id
        item["is_retweet"] = _is_retweet_title(title)
        item["is_quote"] = _is_quote_style(title)
        item["is_reply_like"] = _is_reply_like(title)
        item["_sim_key"] = _title_similarity_key(title)
        item["_thread_signature"] = _thread_signature(title)
        item["_parsed_date"] = _parse_item_date(item.get("date"))

        ident = _article_identity(item)
        if ident in seen:
            continue
        seen.add(ident)
        prepared.append(item)

    prepared.sort(
        key=lambda x: x.get("_parsed_date") or datetime.min.replace(tzinfo=IST_TZ),
        reverse=True,
    )

    full_stream = _cluster_thread_bursts(prepared)
    full_stream.sort(
        key=lambda x: x.get("_parsed_date") or datetime.min.replace(tzinfo=IST_TZ),
        reverse=True,
    )

    cutoff = now - timedelta(hours=high_window_hours)
    high_candidates = []
    for item in full_stream:
        dt = item.get("_parsed_date")
        if not dt or dt < cutoff:
            continue
        if item.get("is_retweet"):
            continue
        high_candidates.append(item)

    # Seed with deterministic ordering, then AI-rank top band.
    fallback_seed = _fallback_high_signal(high_candidates, now, target_count=max(target_count * 5, 120))
    ai_ranked = _ai_rank_high_signal(fallback_seed[:120], target_count=target_count)
    if ai_ranked:
        high_signal = ai_ranked
        ranking_mode = "ai"
    else:
        high_signal = _fallback_high_signal(high_candidates, now, target_count=target_count)
        ranking_mode = "fallback"

    # Fill short AI output from fallback list.
    if len(high_signal) < target_count:
        used_keys = set(_article_identity(x) for x in high_signal)
        for item in fallback_seed:
            key = _article_identity(item)
            if key in used_keys:
                continue
            high_signal.append(dict(item))
            used_keys.add(key)
            if len(high_signal) >= target_count:
                break

    def _strip_internal_fields(item):
        out = dict(item)
        out.pop("_sim_key", None)
        out.pop("_thread_signature", None)
        out.pop("_parsed_date", None)
        return out

    full_stream = [_strip_internal_fields(item) for item in full_stream]
    high_signal = [_strip_internal_fields(item) for item in high_signal[:target_count]]

    stats = {
        "input_count": len(twitter_articles),
        "prepared_count": len(prepared),
        "full_stream_count": len(full_stream),
        "high_candidates_count": len(high_candidates),
        "high_signal_count": len(high_signal),
        "ranking_mode": ranking_mode,
    }
    return full_stream, high_signal, stats
