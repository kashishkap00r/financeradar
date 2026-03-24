#!/usr/bin/env python3
"""
AI News Ranker.

Builds source-separated AI rankings for the sidebar:
- News (25)
- Telegram (20)
- Reports (5)
- Twitter (5)
- YouTube (5)
"""
import json
import urllib.request
import os
import re
import sys
import tempfile
import time
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone

from config import (
    AI_RANKER_ARTICLE_WINDOW_HOURS,
    AI_RANKER_TWITTER_WINDOW_HOURS,
    AI_RANKER_EXTENDED_WINDOW_DAYS,
    AI_RANKER_MAX_ARTICLES,
    AI_RANKER_TARGET_COUNT,
    AI_RANKER_OPENROUTER_TIMEOUT,
    AI_RANKER_GEMINI_TIMEOUT,
    AI_RANKER_MAX_CLUSTERS,
    AI_RANKER_CLUSTER_TIMEOUT,
    SSL_CONTEXT,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IST_TZ = timezone(timedelta(hours=5, minutes=30))
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

MODELS = {
    "gemini-3-flash": {
        "id": "gemini-3-flash-preview",
        "name": "Gemini 3.0 Flash",
        "provider": "gemini",
    },
    "deepseek-v3": {
        "id": "deepseek/deepseek-v3.2",
        "name": "DeepSeek V3.2",
        "provider": "openrouter",
    },
}

# Backward-compatible ordering for helper functions/tests.
SOURCE_TYPE_ORDER = ["news", "twitter", "telegram", "reports", "youtube"]
# New sidebar bucket order.
BUCKET_ORDER = ["news", "telegram", "reports", "twitter", "youtube"]
BUCKET_TARGETS = {
    "news": AI_RANKER_TARGET_COUNT,
    "telegram": 20,
    "reports": 10,
    "twitter": 10,
    "youtube": 10,
}
SOURCE_WINDOWS = {
    "news": timedelta(hours=AI_RANKER_ARTICLE_WINDOW_HOURS),
    "twitter": timedelta(hours=AI_RANKER_TWITTER_WINDOW_HOURS),
    "telegram": timedelta(days=AI_RANKER_EXTENDED_WINDOW_DAYS),
    "reports": timedelta(days=AI_RANKER_EXTENDED_WINDOW_DAYS),
    "youtube": timedelta(days=AI_RANKER_EXTENDED_WINDOW_DAYS),
}


def build_ranking_prompt(headlines, source_type, target_count):
    window = SOURCE_WINDOWS[source_type]
    source_label = source_type.upper()
    if window < timedelta(days=2):
        window_label = f"last {int(window.total_seconds() // 3600)} hours"
    else:
        window_label = f"last {window.days} days"
    return f"""You are the editor of an Indian finance newsletter modeled on Zerodha's Daily Brief.
Audience: curious, informed Indians (long-term investors, founders, policy nerds).

INPUT
You will receive FinanceRadar {source_label} headlines from the {window_label}.
Each headline is formatted as: - Headline text [Source Name | SOURCE_TYPE]

TASK
Pick exactly {target_count} stories most relevant to Daily Brief.
Prioritize high-signal, India-relevant stories.

RANKING PRIORITY (highest to lowest)
1. Explanatory "why/how" journalism (mechanism over headline)
2. Structural company/sector narratives (business model shifts, M&A, governance failures; not earnings beats)
3. Commodity/supply-chain/trade stories with clear India impact (cause-effect chain, not pure price ticks)
4. Major policy analysis (implications, second-order effects; not announcement rewrites)
5. High-quality opinion/insider analysis with an original thesis from credible voices
6. Labour/employment/social-economy trends (gig economy, rural consumption, jobs transitions)

PRIMARY SOURCE RULE
When an official source (RBI, SEBI, PIB, ECB, FRED, MoSPI) publishes original content — press release, policy statement, data release, speech, bulletin — ALWAYS prefer it over media rewrites of the same announcement. The original is more authoritative.
If both an RBI press release and 3 newspaper rewrites appear, pick the RBI original.

HARD SKIPS (never include)
- Earnings/quarterly results coverage
- Wire-style breaking updates with no analysis
- Routine regulatory filings (exception: major policy announcements from RBI/SEBI/PIB)
- Market noise (intraday moves, FII/DII flows, broker upgrades, stock tips)
- Crypto price movement stories
- Celebrity CEO personality fluff

INDIA LENS RULE
Global stories qualify only if they explicitly connect to Indian industry, policy, trade, consumers, jobs, or capital flows.
If India linkage is weak or implied, reject.

SELECTION LOGIC
- Rank by editorial value, not recency alone.
- Prefer one strong explanatory piece over multiple repetitive updates.
- Remove duplicates/near-duplicates.
- If fewer than {target_count} high-confidence stories exist, still return {target_count} by using medium-confidence picks that obey all hard-skip rules.

## Headlines
{headlines}

OUTPUT FORMAT (STRICT)
Return ONLY a JSON array of exactly {target_count} objects. No markdown, no commentary, no code blocks.

Each object must contain:
- rank: integer (1-{target_count})
- title: string (exact headline text as given, including the [Source Name | SOURCE_TYPE] tag)
- india_relevance: string (1 concise sentence)
- signal_type: one of ["mechanism", "structural-shift", "supply-chain", "policy-implication", "credible-opinion", "labour-trend"]
- why_it_matters: string (max 2 concise lines)
- confidence: one of ["high", "medium", "low"]

CRITICAL:
- Use the EXACT headline text from the input — do not paraphrase or modify it.
- Include the full [Source Name | SOURCE_TYPE] tag exactly as shown. This is required for story matching.
- Do not return duplicate titles."""


def parse_item_date(date_str):
    """Parse an ISO date and normalize timezone; return None if parsing fails."""
    if not date_str:
        return None
    try:
        normalized = date_str.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST_TZ)
        return dt.astimezone(IST_TZ)
    except (ValueError, TypeError, AttributeError):
        return None


def normalize_source_type(value):
    st = (value or "").strip().lower()
    return st if st in SOURCE_WINDOWS else ""


def item_identity(title, url="", source_type="", source=""):
    if url:
        return f"url::{url.strip().lower()}"
    return f"title::{normalize_title(title)}|{normalize_source_type(source_type)}|{(source or '').strip().lower()}"


def build_candidates_for_source(snapshot_data, source_type, now=None, max_articles=AI_RANKER_MAX_ARTICLES):
    """Build ranking candidates for a single source type from published snapshot."""
    now = now or datetime.now(IST_TZ)
    entries = snapshot_data.get(source_type, [])
    if not isinstance(entries, list):
        return []

    cutoff = now - SOURCE_WINDOWS[source_type]
    candidates = []
    for item in entries:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        source = (item.get("publisher") or item.get("source_name") or source_type.title()).strip()
        url = (item.get("url") or "").strip()
        date_str = item.get("published_at") or item.get("date") or ""
        parsed_date = parse_item_date(date_str)
        if parsed_date and parsed_date < cutoff:
            continue
        candidates.append({
            "title": title,
            "url": url,
            "source": source,
            "date": date_str,
            "source_type": source_type,
            "source_tier": item.get("source_tier", ""),
            "_parsed_date": parsed_date or datetime.min.replace(tzinfo=IST_TZ),
        })

    candidates.sort(
        key=lambda x: x.get("_parsed_date", datetime.min.replace(tzinfo=IST_TZ)),
        reverse=True,
    )

    deduped = []
    seen = set()
    for item in candidates:
        key = item_identity(
            item.get("title", ""),
            item.get("url", ""),
            item.get("source_type", ""),
            item.get("source", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= max_articles:
            break

    for item in deduped:
        item.pop("_parsed_date", None)
    return deduped


def build_candidates_from_snapshot(snapshot_data, now=None, max_articles=AI_RANKER_MAX_ARTICLES):
    """Backward-compatible helper: build a mixed candidate list across all source types."""
    all_candidates = []
    for source_type in SOURCE_TYPE_ORDER:
        all_candidates.extend(
            build_candidates_for_source(
                snapshot_data,
                source_type=source_type,
                now=now,
                max_articles=max_articles,
            )
        )

    all_candidates.sort(
        key=lambda x: parse_item_date(x.get("date", "")) or datetime.min.replace(tzinfo=IST_TZ),
        reverse=True,
    )
    deduped = []
    seen = set()
    for item in all_candidates:
        key = item_identity(
            item.get("title", ""),
            item.get("url", ""),
            item.get("source_type", ""),
            item.get("source", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= max_articles:
            break
    return deduped


def load_legacy_articles_48h(max_articles=AI_RANKER_MAX_ARTICLES):
    """Fallback loader using static/articles.json (news + twitter only)."""
    articles_path = os.path.join(SCRIPT_DIR, "static", "articles.json")
    try:
        with open(articles_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: {articles_path} not found. Run aggregator.py first.")
        return []

    cutoff = datetime.now(IST_TZ) - timedelta(hours=AI_RANKER_ARTICLE_WINDOW_HOURS)
    articles = []
    for a in data.get("articles", []):
        date_str = a.get("date")
        parsed_date = parse_item_date(date_str)
        if parsed_date and parsed_date < cutoff:
            continue
        category = (a.get("category") or "").strip().lower()
        source_type = "twitter" if category == "twitter" else "news"
        articles.append({
            "title": a.get("title", ""),
            "url": a.get("url", ""),
            "source": a.get("source", ""),
            "date": date_str or "",
            "source_type": source_type,
            "_parsed_date": parsed_date or datetime.min.replace(tzinfo=IST_TZ),
        })

    articles.sort(
        key=lambda x: x.get("_parsed_date", datetime.min.replace(tzinfo=IST_TZ)),
        reverse=True,
    )
    trimmed = articles[:max_articles]
    for item in trimmed:
        item.pop("_parsed_date", None)
    return trimmed


def load_rank_candidates(max_articles=AI_RANKER_MAX_ARTICLES):
    """Backward-compatible helper: load mixed candidate list."""
    snapshot_path = os.path.join(SCRIPT_DIR, "static", "published_snapshot.json")
    try:
        with open(snapshot_path, "r", encoding="utf-8") as f:
            snapshot_data = json.load(f)
        candidates = build_candidates_from_snapshot(snapshot_data, max_articles=max_articles)
        if candidates:
            return candidates
        print(f"WARNING: {snapshot_path} has no candidates in window, falling back to articles.json")
    except FileNotFoundError:
        print(f"WARNING: {snapshot_path} not found, falling back to articles.json")
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: Could not read {snapshot_path}: {e}. Falling back to articles.json")
    return load_legacy_articles_48h(max_articles=max_articles)


def load_rank_candidates_by_bucket(max_articles=AI_RANKER_MAX_ARTICLES):
    """Load bucketed ranking candidates from snapshot; fallback to legacy for news/twitter."""
    buckets = {source_type: [] for source_type in BUCKET_ORDER}
    snapshot_path = os.path.join(SCRIPT_DIR, "static", "published_snapshot.json")

    try:
        with open(snapshot_path, "r", encoding="utf-8") as f:
            snapshot_data = json.load(f)
        for source_type in BUCKET_ORDER:
            buckets[source_type] = build_candidates_for_source(
                snapshot_data,
                source_type=source_type,
                max_articles=max_articles,
            )
        if any(buckets.values()):
            return buckets
        print(f"WARNING: {snapshot_path} has no candidates in any source bucket, falling back to articles.json")
    except FileNotFoundError:
        print(f"WARNING: {snapshot_path} not found, falling back to articles.json")
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: Could not read {snapshot_path}: {e}. Falling back to articles.json")

    legacy = load_legacy_articles_48h(max_articles=max_articles)
    for item in legacy:
        source_type = normalize_source_type(item.get("source_type"))
        if source_type in buckets:
            buckets[source_type].append(item)
    return buckets


def sanitize_headline(title):
    """Remove quotes and special chars that break JSON when AI echoes them back."""
    return title.replace('"', "'").replace('\n', ' ').replace('\r', ' ').strip()


def normalize_title(title):
    """Normalize title text for robust matching across quote/dash variants."""
    t = sanitize_headline(title)
    t = t.replace('\u2014', '-').replace('\u2013', '-').replace('\u2012', '-').replace('\u2212', '-')
    t = t.replace('\u2018', "'").replace('\u2019', "'").replace('\u02bc', "'")
    t = t.replace('\u201c', '"').replace('\u201d', '"')
    t = t.replace('\u2026', '...')
    t = re.sub(r'\s+', ' ', t).strip()
    return t.lower()


def fuzzy_match_article(title, normalized_to_article, threshold=0.72):
    """Fuzzy match a title against known articles when exact match fails."""
    best_match = None
    best_ratio = 0
    title_norm = normalize_title(title)
    for norm_key, article in normalized_to_article.items():
        ratio = SequenceMatcher(None, title_norm, norm_key).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = article
    if best_ratio >= threshold:
        return best_match
    return None


def extract_source_type_from_tag(tagged_title):
    match = re.search(r'\[([^\]]+)\]\s*$', tagged_title or "")
    if not match:
        return ""
    payload = match.group(1)
    if "|" not in payload:
        return ""
    source_type = payload.split("|")[-1].strip().lower()
    return normalize_source_type(source_type)


def candidate_to_ranking_item(candidate):
    return {
        "rank": 0,
        "title": candidate.get("title", ""),
        "url": candidate.get("url", ""),
        "source": candidate.get("source", ""),
        "source_type": normalize_source_type(candidate.get("source_type", "")),
        "india_relevance": "",
        "signal_type": "",
        "why_it_matters": "",
        "confidence": "low",
    }


def enforce_source_coverage_and_size(rankings, candidates, target_count=AI_RANKER_TARGET_COUNT):
    """Backward-compatible helper used by tests."""
    required_types = [
        source_type
        for source_type in SOURCE_TYPE_ORDER
        if any(normalize_source_type(c.get("source_type")) == source_type for c in candidates)
    ]

    selected = []
    seen = set()

    def add_item(item):
        key = item_identity(
            item.get("title", ""),
            item.get("url", ""),
            item.get("source_type", ""),
            item.get("source", ""),
        )
        if key in seen:
            return False
        seen.add(key)
        selected.append(item)
        return True

    for source_type in required_types:
        match = next(
            (item for item in rankings if normalize_source_type(item.get("source_type")) == source_type),
            None,
        )
        if match and add_item(match):
            continue
        fallback = next(
            (
                candidate_to_ranking_item(candidate)
                for candidate in candidates
                if normalize_source_type(candidate.get("source_type")) == source_type
            ),
            None,
        )
        if fallback:
            add_item(fallback)

    for item in rankings:
        if len(selected) >= target_count:
            break
        add_item(item)

    for candidate in candidates:
        if len(selected) >= target_count:
            break
        add_item(candidate_to_ranking_item(candidate))

    selected = selected[:target_count]
    for idx, item in enumerate(selected, start=1):
        item["rank"] = idx
    return selected


def enforce_bucket_size(rankings, candidates, source_type, target_count):
    """Keep ranking list source-pure, deduped, and filled up to target count."""
    selected = []
    seen = set()

    def add_item(item):
        st = normalize_source_type(item.get("source_type")) or source_type
        if st != source_type:
            return False
        key = item_identity(item.get("title", ""), item.get("url", ""), st, item.get("source", ""))
        if key in seen:
            return False
        title = (item.get("title") or "").strip()
        if not title:
            return False
        payload = dict(item)
        payload["source_type"] = source_type
        seen.add(key)
        selected.append(payload)
        return True

    for item in rankings:
        if len(selected) >= target_count:
            break
        add_item(item)

    for candidate in candidates:
        if len(selected) >= target_count:
            break
        add_item(candidate_to_ranking_item(candidate))

    selected = selected[:target_count]
    for idx, item in enumerate(selected, start=1):
        item["rank"] = idx
    return selected


def parse_json_response(text):
    text = text.strip()
    if "```" in text:
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if match:
            text = match.group(1).strip()
        else:
            text = text.replace("```json", "").replace("```", "").strip()
    if not text.startswith("["):
        start = text.find("[")
        if start != -1:
            end = text.rfind("]")
            if end > start:
                text = text[start:end + 1]
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r',\s*]', ']', text)
    text = re.sub(r',\s*}', '}', text)
    return json.loads(text)


def call_openrouter(prompt, model_id):
    """Call OpenRouter API with specified model."""
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not set")
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps({
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://financeradar.kashishkapoor.com",
            "X-Title": "FinanceRadar",
        },
    )
    with urllib.request.urlopen(request, timeout=AI_RANKER_OPENROUTER_TIMEOUT, context=SSL_CONTEXT) as response:
        result = json.loads(response.read().decode("utf-8"))
    return parse_json_response(result["choices"][0]["message"]["content"])


def call_gemini(prompt, model_id):
    """Call Gemini API directly with guardrails for empty/blocked responses."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_id}:generateContent?key={GEMINI_API_KEY}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 8192,
            "response_mime_type": "application/json",
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=AI_RANKER_GEMINI_TIMEOUT, context=SSL_CONTEXT) as response:
        result = json.loads(response.read().decode("utf-8"))

    candidates = result.get("candidates") or []
    if not candidates:
        prompt_feedback = result.get("promptFeedback") or {}
        block_reason = prompt_feedback.get("blockReason", "no-candidates")
        raise ValueError(f"Gemini returned no candidates ({block_reason})")

    candidate = candidates[0]
    finish_reason = candidate.get("finishReason", "UNKNOWN")
    if finish_reason not in ("STOP", "MAX_TOKENS"):
        print(f"    [WARN] Gemini finishReason={finish_reason}")
    if finish_reason == "MAX_TOKENS":
        print("    [WARN] Gemini hit token limit — response may be truncated")

    parts = (candidate.get("content") or {}).get("parts") or []
    text = " ".join(part.get("text", "") for part in parts if isinstance(part, dict) and part.get("text"))
    if not text.strip():
        raise ValueError(f"Gemini returned empty text (finishReason={finish_reason})")
    return parse_json_response(text)


def normalize_ai_response(rankings):
    if isinstance(rankings, dict):
        rankings = rankings.get("rankings", rankings.get("items", []))
    if not isinstance(rankings, list):
        raise ValueError(f"AI returned {type(rankings).__name__} instead of list")
    return rankings


def build_headlines_payload(candidates):
    return "\n".join(
        f"- {sanitize_headline(item.get('title', ''))} "
        f"[{item.get('source', '')} | {normalize_source_type(item.get('source_type', 'news')).upper()}]"
        for item in candidates
    )


def enrich_bucket_rankings(rankings, candidates, source_type, target_count):
    sanitized_to_article = {}
    normalized_to_article = {}
    for item in candidates:
        sanitized = sanitize_headline(item.get("title", ""))
        sanitized_to_article.setdefault(sanitized, item)
        normalized_to_article.setdefault(normalize_title(item.get("title", "")), item)

    enriched = []
    for item in rankings[: max(target_count * 2, target_count)]:
        if not isinstance(item, dict):
            continue
        original_title = str(item.get("title", "")).strip()
        tagged_source_type = extract_source_type_from_tag(original_title)
        title = re.sub(r'\s*\[.*?\]\s*$', '', original_title).strip()
        if not title:
            continue

        article = sanitized_to_article.get(sanitize_headline(title))
        if not article:
            article = normalized_to_article.get(normalize_title(title))
        if not article:
            article = fuzzy_match_article(title, normalized_to_article)

        enriched.append({
            "rank": item.get("rank", len(enriched) + 1),
            "title": article["title"] if article else title,
            "url": article["url"] if article else "",
            "source": article["source"] if article else "",
            "source_type": normalize_source_type(article.get("source_type", "")) if article else (tagged_source_type or source_type),
            "source_tier": article.get("source_tier", "") if article else "",
            "india_relevance": item.get("india_relevance", ""),
            "signal_type": item.get("signal_type", ""),
            "why_it_matters": item.get("why_it_matters", ""),
            "confidence": item.get("confidence", ""),
        })

    final = enforce_bucket_size(enriched, candidates, source_type=source_type, target_count=target_count)
    empty_count = sum(1 for entry in final if not entry.get("title"))
    if final and empty_count > len(final) * 0.5:
        raise ValueError(f"AI returned {empty_count}/{len(final)} empty titles")
    return final


def sanitize_error(err):
    return re.sub(
        r'AIza\S{20,}|sk-or-\S{20,}|Bearer\s+\S+|key[=:]\s*["\']?\S{10,}',
        '[REDACTED]',
        err,
    )[:200]


def call_provider(model_config, prompt):
    if model_config.get("provider") == "gemini":
        return call_gemini(prompt, model_config["id"])
    return call_openrouter(prompt, model_config["id"])


def build_clustering_prompt(items, max_clusters=AI_RANKER_MAX_CLUSTERS):
    """Build the LLM prompt for cross-bucket story clustering.

    For large item lists (>50), uses titles-only mode to save tokens.
    For smaller lists, includes why_it_matters context when available.
    """
    titles_only = len(items) > 50
    lines = []
    for i, item in enumerate(items):
        headline = sanitize_headline(item.get("title", ""))
        src = item.get("source", "")
        stype = item.get("source_type", "news").upper()
        official_tag = " [OFFICIAL]" if item.get("source_tier") == "official" else ""
        line = f"{i+1}. {headline} [{src} | {stype}]{official_tag}"
        if not titles_only:
            wim = (item.get("why_it_matters") or "").strip()
            if wim:
                line += f" — {wim[:120]}"
        lines.append(line)
    numbered = "\n".join(lines)
    return f"""You are the editor of an Indian finance newsletter. You've already ranked these articles.

Now identify CLUSTERS: groups of 2+ articles covering the SAME underlying story or event, regardless of source type (news, Telegram reports, YouTube videos, tweets, research reports).

CLUSTERING RULES:
- Only cluster if articles cover the SAME specific event or development — not merely the same broad sector or topic.
  - YES: Three articles about RBI's March 2026 rate cut → same event
  - NO: Two unrelated banking articles (HDFC results + SBI NPA) → same sector, different stories
- CRITICAL: Do NOT include multiple articles that report the same facts. If ET, Mint, and Bloomberg all say "Fed holds rates steady", pick the ONE best version. Only include an article if it adds a genuinely NEW fact, number, angle, or format (e.g. a YouTube explainer, a research report with data, a tweet with insider context).
- Cross-type clusters are valuable: a YouTube explainer + a Telegram research note + a news report on the same event is a great cluster. Prefer diversity of source types over quantity.
- Minimum 2, maximum {max_clusters} clusters. Prefer fewer, tighter clusters over many loose ones. If no natural clusters exist, return empty array.
- Return clusters in ORDER OF IMPORTANCE — the biggest, most impactful story first.
- When a cluster includes an [OFFICIAL] source article (RBI, SEBI, PIB, ECB, etc.), prefer it as the FIRST article in the articles array — it's the primary source.

STORY LABEL — this is the editorial headline readers see. Make it:
- Sharp, specific, and informative — a reader should understand the story from the label alone
- Written like a newsletter section title, not a generic news headline
- BAD: "West Asia Conflict Triggers Massive Surge in Indian Oil Costs" (vague, wordy)
- GOOD: "Hormuz Blockade Chokes India's Oil & LPG Supply Lines" (specific, punchy)
- BAD: "India Struggles with Widening Jobs Gap for Educated Youth" (generic)
- GOOD: "Graduate Unemployment Hits Record Despite India's GDP Growth" (tells you the tension)

ANGLE — this is a 3-6 word tag shown next to each article. It must tell the reader what THIS article adds that others in the cluster don't.
- BAD angles: "news report on topic", "analysis of sector", "overview of situation" (these say nothing)
- GOOD angles: "1.7M tonnes stranded", "Iraq's Turkey workaround", "50-60% price forecast", "CRISIL curtailment data"
- The angle should make a reader think "oh, I should read this one too" — it's a reason to click, not a category label.

## Items
{numbered}

OUTPUT: Valid JSON array only. No markdown, no commentary.
Each object:
- story_id: string (kebab-case, 3-5 words)
- story_label: string (max 10 words, sharp editorial headline)
- articles: array of objects (2+ items), each with:
  - index: integer (1-based index from Items list)
  - angle: string (what THIS article uniquely adds, 3-6 words)"""


def resolve_cluster_indices(raw_clusters, items):
    """Resolve 1-based indices from LLM output to actual article data.

    Supports two formats:
    - New: flat "articles" array with index + angle for every item
    - Legacy: "lead_index" + "related" array

    Returns list of fully resolved clusters, silently dropping any cluster
    with invalid index references or fewer than 2 total articles.
    """
    resolved = []
    for cluster in raw_clusters:
        if not isinstance(cluster, dict):
            continue

        # Collect raw article references (support both formats)
        raw_articles = cluster.get("articles", [])
        if not isinstance(raw_articles, list) or not raw_articles:
            # Legacy format: lead_index + related
            lead_idx = cluster.get("lead_index")
            if not isinstance(lead_idx, int) or lead_idx < 1 or lead_idx > len(items):
                continue
            raw_articles = [{"index": lead_idx, "angle": ""}]
            for rel in (cluster.get("related") or []):
                if isinstance(rel, dict):
                    raw_articles.append(rel)

        # Resolve all articles
        articles = []
        seen_urls = set()
        for entry in raw_articles:
            if not isinstance(entry, dict):
                continue
            idx = entry.get("index")
            if not isinstance(idx, int) or idx < 1 or idx > len(items):
                continue
            art_item = items[idx - 1]
            art_url = (art_item.get("url") or "").lower()
            if art_url and art_url in seen_urls:
                continue
            seen_urls.add(art_url)
            articles.append({
                "title": art_item.get("title", ""),
                "url": art_item.get("url", ""),
                "source": art_item.get("source", ""),
                "source_type": normalize_source_type(art_item.get("source_type", "")),
                "source_tier": art_item.get("source_tier", ""),
                "angle": str(entry.get("angle", ""))[:60],
            })

        if len(articles) < 2:
            continue

        # Prefer official source as cluster lead
        official_idx = next(
            (i for i, a in enumerate(articles) if a.get("source_tier") == "official"),
            0,
        )
        if official_idx > 0:
            articles.insert(0, articles.pop(official_idx))

        # For backward compatibility, first article is "lead", rest are "related"
        lead = dict(articles[0])
        lead["why_it_matters"] = items[0].get("why_it_matters", "") if articles else ""
        lead["signal_type"] = items[0].get("signal_type", "") if articles else ""

        resolved.append({
            "story_id": str(cluster.get("story_id", ""))[:50],
            "story_label": str(cluster.get("story_label", ""))[:100],
            "lead": lead,
            "related": articles[1:],
        })
    return resolved


import re as _re

# Patterns for market-movement noise — these add no signal in clusters
_CLUSTER_NOISE_PATTERNS = [
    _re.compile(r"sensex\s*(closes?|ends?|opens?|gains?|loses?|falls?|rises?|at\b|surges?|zooms?|jumps?|soars?|rallies?|tanks?|plunges?|crashes?|tumbles?|slumps?|bleeds?|sheds?|down|up|today)", _re.I),
    _re.compile(r"nifty\s*(closes?|ends?|opens?|gains?|loses?|falls?|rises?|at\b|surges?|zooms?|jumps?|soars?|rallies?|tanks?|plunges?|crashes?|tumbles?|slumps?|bleeds?|prediction|today|may\s*fall|below)", _re.I),
    _re.compile(r"\b(stock|share)\s*market\s*(crash|tumbl|fall|drop|plunge|tank|bleed|sink)", _re.I),
    _re.compile(r"\bmarkets?\s*(tumbl|crash|plunge|tank|bleed|sink)", _re.I),
    _re.compile(r"\b(asian|global|indian)\s*(stocks?|markets?)\s*(to\s*)?(fall|drop|tumbl|plunge|crash|sink|slide)", _re.I),
    _re.compile(r"\bFPI\w*\s*(dump|sell|pull|withdraw|outflow)", _re.I),
]


def _is_market_noise(title):
    """Check if a title is primarily about market index movements."""
    t = title or ""
    return any(p.search(t) for p in _CLUSTER_NOISE_PATTERNS)


def filter_cluster_noise(clusters):
    """Remove market-movement noise from clusters.

    - Drop entire clusters whose label is about market indices
    - Strip individual noise articles from within clusters
    - Drop clusters that fall below 2 articles after stripping
    """
    filtered = []
    for cluster in clusters:
        # Skip entire cluster if the story_label is about market movements
        label = cluster.get("story_label", "")
        if _is_market_noise(label):
            continue

        # Strip noise articles from within the cluster
        lead = cluster.get("lead", {})
        related = cluster.get("related", [])
        all_arts = [lead] + related
        clean = [a for a in all_arts if not _is_market_noise(a.get("title", ""))]

        if len(clean) < 2:
            continue

        cluster["lead"] = clean[0]
        cluster["related"] = clean[1:]
        filtered.append(cluster)
    return filtered


_STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did will would "
    "shall should may might can could of in on at to for with by from as into "
    "and or but not no nor so yet if then than that this these those it its "
    "about after all also am among any both each every how i me my our ours "
    "says said report reports india indian market markets stock stocks news "
    "via rt the new".split()
)


def _title_words(title):
    """Extract significant words from a title for similarity comparison."""
    import re
    words = re.sub(r"[^\w\s]", " ", title.lower()).split()
    return set(w for w in words if w not in _STOP_WORDS and len(w) > 1)


def dedup_cluster_articles(clusters):
    """Remove near-duplicate articles within each cluster.

    Uses Jaccard similarity on significant title words.
    - Same source_type: 0.4 threshold (stricter — wire rewrites use different words)
    - Different source_type: 0.6 threshold (cross-type dupes are rarer)
    Clusters that shrink below 2 articles are removed entirely.
    """
    deduped = []
    for cluster in clusters:
        all_arts = [cluster.get("lead", {})] + cluster.get("related", [])
        keep = []
        kept_word_sets = []
        kept_types = []
        for art in all_arts:
            words = _title_words(art.get("title", ""))
            stype = art.get("source_type", "")
            if not words:
                keep.append(art)
                kept_word_sets.append(words)
                kept_types.append(stype)
                continue

            is_dup = False
            for i, kw in enumerate(kept_word_sets):
                if not kw:
                    continue
                intersection = words & kw
                union = words | kw
                similarity = len(intersection) / len(union) if union else 0
                # Stricter threshold for same source type (wire rewrites)
                threshold = 0.4 if stype == kept_types[i] else 0.6
                if similarity >= threshold:
                    is_dup = True
                    break

            if not is_dup:
                keep.append(art)
                kept_word_sets.append(words)
                kept_types.append(stype)

        if len(keep) < 2:
            continue

        cluster["lead"] = keep[0]
        cluster["related"] = keep[1:]
        deduped.append(cluster)
    return deduped


def enrich_clusters_from_rankings(clusters, ranked_buckets):
    """Attach why_it_matters and signal_type from ranked items to cluster articles.

    Cluster articles come from the full candidate pool and may lack ranking
    metadata.  This matches by URL against ranked items to fill in the gaps.
    """
    # Build URL → ranked-item lookup across all buckets
    ranked_by_url = {}
    for items in ranked_buckets.values():
        for item in items:
            url = (item.get("url") or "").lower().strip()
            if url:
                ranked_by_url[url] = item

    for cluster in clusters:
        for art in [cluster.get("lead", {})] + cluster.get("related", []):
            url = (art.get("url") or "").lower().strip()
            ranked = ranked_by_url.get(url)
            if ranked:
                if not art.get("why_it_matters"):
                    art["why_it_matters"] = ranked.get("why_it_matters", "")
                if not art.get("signal_type"):
                    art["signal_type"] = ranked.get("signal_type", "")
                if not art.get("source_tier"):
                    art["source_tier"] = ranked.get("source_tier", "")
    return clusters


def cluster_ranked_items(all_items, model_config, max_clusters=AI_RANKER_MAX_CLUSTERS):
    """Post-ranking step: cluster items across all buckets by underlying story.

    Accepts the full candidate pool (titles-only mode for large sets).
    Returns list of resolved cluster dicts. On any failure, returns empty list
    so that per-bucket rankings are unaffected.
    """
    if not all_items or len(all_items) < 2:
        return []

    prompt = build_clustering_prompt(all_items, max_clusters=max_clusters)

    try:
        if model_config.get("provider") == "gemini":
            raw = call_gemini(prompt, model_config["id"])
        else:
            raw = call_openrouter(prompt, model_config["id"])

        if isinstance(raw, dict):
            raw = raw.get("clusters", raw.get("items", []))
        if not isinstance(raw, list):
            print("    [WARN] Clustering returned non-list, skipping")
            return []

        clusters = resolve_cluster_indices(raw, all_items)
        clusters = dedup_cluster_articles(clusters)
        clusters = filter_cluster_noise(clusters)
        return clusters[:max_clusters]

    except Exception as err:
        safe_err = sanitize_error(str(err))
        print(f"  [WARN] Clustering failed ({safe_err}), continuing without clusters")
        return []


def main():
    print("=" * 50)
    print("AI News Ranker")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    candidates_by_bucket = load_rank_candidates_by_bucket()
    available_buckets = [bucket for bucket in BUCKET_ORDER if candidates_by_bucket.get(bucket)]
    total_candidates = sum(len(items) for items in candidates_by_bucket.values())

    if not total_candidates:
        print("No ranking candidates found. Exiting.")
        return

    source_summary = ", ".join(f"{bucket}={len(candidates_by_bucket[bucket])}" for bucket in BUCKET_ORDER)
    print(f"\nLoaded {total_candidates} ranking candidates ({source_summary})")

    results = {
        "generated_at": datetime.now(IST_TZ).isoformat(),
        "article_count": total_candidates,
        "bucket_counts": BUCKET_TARGETS,
        "providers": {},
    }

    print(f"\nCalling {len(MODELS)} AI models...\n")
    for key, model_config in MODELS.items():
        model_name = model_config["name"]
        provider_buckets = {}
        provider_errors = {}
        provider_count = 0
        print(f"[{model_name}]")

        for source_type in BUCKET_ORDER:
            candidates = candidates_by_bucket.get(source_type, [])
            target = min(BUCKET_TARGETS[source_type], len(candidates))

            if target <= 0:
                provider_errors[source_type] = "No candidates available"
                print(f"  [SKIP] {source_type}: no candidates")
                continue

            headlines = build_headlines_payload(candidates)
            prompt = build_ranking_prompt(headlines, source_type=source_type, target_count=target)

            try:
                rankings = call_provider(model_config, prompt)
                rankings = normalize_ai_response(rankings)
                enriched = enrich_bucket_rankings(
                    rankings,
                    candidates=candidates,
                    source_type=source_type,
                    target_count=target,
                )
                if not enriched:
                    raise ValueError("No rankings after enrichment")

                provider_buckets[source_type] = enriched
                provider_count += len(enriched)
                print(f"  [OK] {source_type}: {len(enriched)}")
            except Exception as err:
                safe_err = sanitize_error(str(err))
                provider_errors[source_type] = safe_err
                print(f"  [FAIL] {source_type}: {safe_err}")

            # Small delay between API calls to avoid provider bursts.
            time.sleep(1)

        if provider_buckets:
            # Cross-bucket clustering: run on ALL candidates for wider pattern detection
            all_candidates = []
            for bucket in BUCKET_ORDER:
                all_candidates.extend(candidates_by_bucket.get(bucket, []))
            # Pre-filter market-movement noise from clustering input
            all_candidates = [c for c in all_candidates if not _is_market_noise(c.get("title", ""))]

            clusters = cluster_ranked_items(all_candidates, model_config, max_clusters=7)
            # Enrich cluster articles with metadata from ranked items
            clusters = enrich_clusters_from_rankings(clusters, provider_buckets)
            n_items = sum(1 + len(c.get("related", [])) for c in clusters)
            if clusters:
                print(f"  [OK] clusters: {len(clusters)} stories ({n_items} articles from {len(all_candidates)} candidates)")
            else:
                print(f"  [OK] clusters: none found")

            status = "ok" if len(provider_buckets) == len(available_buckets) else "partial"
            payload = {
                "name": model_name,
                "status": status,
                "count": provider_count,
                "available_buckets": [b for b in BUCKET_ORDER if b in provider_buckets],
                "bucket_counts": {b: len(provider_buckets.get(b, [])) for b in BUCKET_ORDER},
                "buckets": provider_buckets,
                "clusters": clusters,
            }
            # Backward compatibility for older frontend versions.
            if provider_buckets.get("news"):
                payload["rankings"] = provider_buckets["news"]
            if provider_errors:
                payload["errors"] = provider_errors
            results["providers"][key] = payload
        else:
            results["providers"][key] = {
                "name": model_name,
                "status": "error",
                "error": "No bucket rankings available",
                "errors": provider_errors,
            }

    output_path = os.path.join(SCRIPT_DIR, "static", "ai_rankings.json")
    tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(output_path), suffix='.tmp')
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        os.replace(tmp_path, output_path)
    except Exception:
        os.unlink(tmp_path)
        raise

    success_count = sum(
        1 for p in results["providers"].values() if p.get("status") in ("ok", "partial")
    )
    print(f"\nSaved to {output_path}")
    print(f"\nSuccess: {success_count}/{len(MODELS)} models")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
