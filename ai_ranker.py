#!/usr/bin/env python3
"""
AI News Ranker - Calls AI providers to rank top stories.
Runs daily after aggregator.py to generate cached AI rankings.
"""
import json
import urllib.request
import urllib.error
import os
import ssl
import re
import sys
import tempfile
import time
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone

from config import (
    AI_RANKER_ARTICLE_WINDOW_HOURS,
    AI_RANKER_EXTENDED_WINDOW_DAYS,
    AI_RANKER_MAX_ARTICLES,
    AI_RANKER_TARGET_COUNT,
    AI_RANKER_OPENROUTER_TIMEOUT,
    AI_RANKER_GEMINI_TIMEOUT,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IST_TZ = timezone(timedelta(hours=5, minutes=30))
SSL_CONTEXT = ssl.create_default_context()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

MODELS = {
    "gemini-3-flash": {
        "id": "gemini-3-flash-preview",
        "name": "Gemini 3.0 Flash",
        "provider": "gemini"
    },
    "deepseek-v3": {
        "id": "deepseek/deepseek-v3.2",
        "name": "DeepSeek V3.2",
        "provider": "openrouter"
    }
}

SOURCE_TYPE_ORDER = ["news", "twitter", "telegram", "reports", "youtube"]
SOURCE_WINDOWS = {
    "news": timedelta(hours=AI_RANKER_ARTICLE_WINDOW_HOURS),
    "twitter": timedelta(hours=AI_RANKER_ARTICLE_WINDOW_HOURS),
    "telegram": timedelta(days=AI_RANKER_EXTENDED_WINDOW_DAYS),
    "reports": timedelta(days=AI_RANKER_EXTENDED_WINDOW_DAYS),
    "youtube": timedelta(days=AI_RANKER_EXTENDED_WINDOW_DAYS),
}


def build_ranking_prompt(headlines, available_source_types):
    source_list = ", ".join(st.upper() for st in available_source_types) or "NEWS"
    return f"""You are the editor of an Indian finance newsletter modeled on Zerodha's Daily Brief.
Audience: curious, informed Indians (long-term investors, founders, policy nerds).

INPUT
You will receive a list of FinanceRadar headlines.
- NEWS and TWITTER items are from the last {AI_RANKER_ARTICLE_WINDOW_HOURS} hours.
- TELEGRAM, REPORTS, and YOUTUBE items are from the last {AI_RANKER_EXTENDED_WINDOW_DAYS} days.
Each headline is formatted as: - Headline text [Source Name | SOURCE_TYPE]

TASK
Pick exactly {AI_RANKER_TARGET_COUNT} stories most relevant to Daily Brief.
Prioritize high-signal, India-relevant stories.

RANKING PRIORITY (highest to lowest)
1. Explanatory "why/how" journalism (mechanism over headline)
2. Structural company/sector narratives (business model shifts, M&A, governance failures; not earnings beats)
3. Commodity/supply-chain/trade stories with clear India impact (cause-effect chain, not pure price ticks)
4. Major policy analysis (implications, second-order effects; not announcement rewrites)
5. High-quality opinion/insider analysis with an original thesis from credible voices
6. Labour/employment/social-economy trends (gig economy, rural consumption, jobs transitions)

HARD SKIPS (never include)
- Earnings/quarterly results coverage
- Wire-style breaking updates with no analysis
- Routine regulatory filings
- Market noise (intraday moves, FII/DII flows, broker upgrades, stock tips)
- Crypto price movement stories
- Celebrity CEO personality fluff

INDIA LENS RULE
Global stories qualify only if they explicitly connect to Indian industry, policy, trade, consumers, jobs, or capital flows.
If India linkage is weak or implied, reject.

DIVERSITY RULE
No more than 4 selected stories from the same sector.
Ensure at least one story from each source type available in the input: {source_list}.

SOURCE QUALITY FILTER
Prefer primary reporting and strong analytical outlets.
De-prioritize republished wires, low-information rewrites, and unsourced hot takes.

SELECTION LOGIC
- Rank by editorial value, not recency alone.
- Prefer one strong explanatory piece over multiple repetitive updates.
- Remove duplicates/near-duplicates across sources.
- If fewer than {AI_RANKER_TARGET_COUNT} high-confidence stories exist, still return {AI_RANKER_TARGET_COUNT} by using medium-confidence picks that obey all hard-skip rules.

## Headlines
{headlines}

OUTPUT FORMAT (STRICT)
Return ONLY a JSON array of exactly {AI_RANKER_TARGET_COUNT} objects. No markdown, no commentary, no code blocks.

Each object must contain:
- rank: integer (1-{AI_RANKER_TARGET_COUNT})
- title: string (exact headline text as given, including the [Source Name | SOURCE_TYPE] tag)
- india_relevance: string (1 concise sentence)
- signal_type: one of ["mechanism", "structural-shift", "supply-chain", "policy-implication", "credible-opinion", "labour-trend"]
- why_it_matters: string (max 2 concise lines)
- confidence: one of ["high", "medium", "low"]

CRITICAL:
- Use the EXACT headline text from the input — do not paraphrase or modify it.
- Include the full [Source Name | SOURCE_TYPE] tag exactly as shown. This is required for story matching.
- When in doubt, pick the story that makes the reader say "I didn't know that" over "I already saw that."

VALIDATION BEFORE FINALIZING
- Exactly {AI_RANKER_TARGET_COUNT} items
- Ranks are unique and sequential 1..{AI_RANKER_TARGET_COUNT}
- No duplicate titles
- Every item has explicit India relevance
- Hard skips are excluded"""


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


def build_candidates_from_snapshot(snapshot_data, now=None, max_articles=AI_RANKER_MAX_ARTICLES):
    """Build AI ranking candidates from static/published_snapshot.json."""
    now = now or datetime.now(IST_TZ)
    candidates = []
    for source_type in SOURCE_TYPE_ORDER:
        entries = snapshot_data.get(source_type, [])
        if not isinstance(entries, list):
            continue
        cutoff = now - SOURCE_WINDOWS[source_type]
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
                "_parsed_date": parsed_date or datetime.min.replace(tzinfo=IST_TZ),
            })

    candidates.sort(key=lambda x: x.get("_parsed_date", datetime.min.replace(tzinfo=IST_TZ)), reverse=True)

    deduped = []
    seen = set()
    for item in candidates:
        key = item_identity(item.get("title", ""), item.get("url", ""), item.get("source_type", ""), item.get("source", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= max_articles:
            break

    for item in deduped:
        item.pop("_parsed_date", None)
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

    articles.sort(key=lambda x: x.get("_parsed_date", datetime.min.replace(tzinfo=IST_TZ)), reverse=True)
    trimmed = articles[:max_articles]
    for item in trimmed:
        item.pop("_parsed_date", None)
    return trimmed


def load_rank_candidates(max_articles=AI_RANKER_MAX_ARTICLES):
    """Load ranking candidates from snapshot; fallback to legacy articles file."""
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


def sanitize_headline(title):
    """Remove quotes and special chars that break JSON when AI echoes them back."""
    return title.replace('"', "'").replace('\n', ' ').replace('\r', ' ').strip()


def normalize_title(title):
    """Normalize a title for robust matching regardless of punctuation variations.
    Handles: em/en-dash → hyphen, smart quotes → straight, extra whitespace, case."""
    t = sanitize_headline(title)
    # Dashes: em-dash, en-dash, figure dash, minus → hyphen
    t = t.replace('\u2014', '-').replace('\u2013', '-').replace('\u2012', '-').replace('\u2212', '-')
    # Smart single quotes → apostrophe
    t = t.replace('\u2018', "'").replace('\u2019', "'").replace('\u02bc', "'")
    # Smart double quotes → straight double quote (already done by sanitize, but be safe)
    t = t.replace('\u201c', '"').replace('\u201d', '"')
    # Ellipsis → three dots
    t = t.replace('\u2026', '...')
    # Collapse multiple spaces
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
    """Ensure minimum 1 per available source_type and fill to target count."""
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
        match = next((item for item in rankings if normalize_source_type(item.get("source_type")) == source_type), None)
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


def parse_json_response(text):
    text = text.strip()
    # Remove markdown code blocks
    if "```" in text:
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if match:
            text = match.group(1).strip()
        else:
            text = text.replace("```json", "").replace("```", "").strip()
    # Extract JSON array
    if not text.startswith("["):
        start = text.find("[")
        if start != -1:
            end = text.rfind("]")
            if end > start:
                text = text[start:end+1]
    # Clean up common issues
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
            "messages": [{"role": "user", "content": prompt}]
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://financeradar.kashishkapoor.com",
            "X-Title": "FinanceRadar"
        }
    )
    with urllib.request.urlopen(request, timeout=AI_RANKER_OPENROUTER_TIMEOUT, context=SSL_CONTEXT) as response:
        result = json.loads(response.read().decode("utf-8"))
    return parse_json_response(result["choices"][0]["message"]["content"])


def call_gemini(prompt, model_id):
    """Call Gemini API directly."""
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
            "response_mime_type": "application/json"
        }
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=AI_RANKER_GEMINI_TIMEOUT, context=SSL_CONTEXT) as response:
        result = json.loads(response.read().decode("utf-8"))
    candidate = result["candidates"][0]
    finish_reason = candidate.get("finishReason", "UNKNOWN")
    if finish_reason not in ("STOP", "MAX_TOKENS"):
        print(f"    [WARN] Gemini finishReason={finish_reason}")
    if finish_reason == "MAX_TOKENS":
        print(f"    [WARN] Gemini hit token limit — response may be truncated")
    text = candidate["content"]["parts"][0]["text"]
    return parse_json_response(text)


def main():
    print("=" * 50)
    print("AI News Ranker")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    articles = load_rank_candidates()
    if not articles:
        print("No ranking candidates found. Exiting.")
        return

    source_counts = {source_type: 0 for source_type in SOURCE_TYPE_ORDER}
    for article in articles:
        source_type = normalize_source_type(article.get("source_type"))
        if source_type in source_counts:
            source_counts[source_type] += 1
    source_summary = ", ".join(f"{k}={v}" for k, v in source_counts.items() if v > 0)
    print(f"\nLoaded {len(articles)} ranking candidates ({source_summary or 'none'})")

    # Build lookup dicts: exact-sanitized and normalized (for robust matching)
    sanitized_to_article = {}
    normalized_to_article = {}
    for a in articles:
        sanitized = sanitize_headline(a['title'])
        sanitized_to_article.setdefault(sanitized, a)
        normalized_to_article.setdefault(normalize_title(a['title']), a)

    headlines = "\n".join(
        f"- {sanitize_headline(a['title'])} [{a.get('source', '')} | {normalize_source_type(a.get('source_type', 'news')).upper()}]"
        for a in articles
    )
    available_source_types = [
        source_type for source_type in SOURCE_TYPE_ORDER
        if any(normalize_source_type(item.get("source_type")) == source_type for item in articles)
    ]
    prompt = build_ranking_prompt(headlines, available_source_types)

    results = {"generated_at": datetime.now(IST_TZ).isoformat(), "article_count": len(articles), "providers": {}}

    print(f"\nCalling {len(MODELS)} AI models...\n")
    for key, model_config in MODELS.items():
        model_id = model_config["id"]
        model_name = model_config["name"]
        try:
            if model_config.get("provider") == "gemini":
                rankings = call_gemini(prompt, model_id)
            else:
                rankings = call_openrouter(prompt, model_id)
            if isinstance(rankings, dict):
                rankings = rankings.get("rankings", rankings.get("items", []))
            if not isinstance(rankings, list):
                raise ValueError(f"AI returned {type(rankings).__name__} instead of list")
            enriched = []
            for item in rankings[:AI_RANKER_TARGET_COUNT]:
                original_title = item.get("title", "").strip()
                tagged_source_type = extract_source_type_from_tag(original_title)
                # Strip echoed [Source | SourceType] suffix the AI may repeat
                title = re.sub(r'\s*\[.*?\]\s*$', '', original_title)
                # 1) Exact match on sanitized title
                article = sanitized_to_article.get(sanitize_headline(title))
                # 2) Exact match on normalized title (handles dash/quote variants)
                if not article:
                    article = normalized_to_article.get(normalize_title(title))
                # 3) Fuzzy fallback (threshold 0.72) against normalized keys
                if not article:
                    article = fuzzy_match_article(title, normalized_to_article)
                enriched.append({
                    "rank": item.get("rank", len(enriched) + 1),
                    "title": article["title"] if article else title,  # Use original title
                    "url": article["url"] if article else "",
                    "source": article["source"] if article else "",
                    "source_type": normalize_source_type(article.get("source_type", "")) if article else tagged_source_type,
                    "india_relevance": item.get("india_relevance", ""),
                    "signal_type": item.get("signal_type", ""),
                    "why_it_matters": item.get("why_it_matters", ""),
                    "confidence": item.get("confidence", ""),
                })
            enriched = enforce_source_coverage_and_size(enriched, articles, target_count=AI_RANKER_TARGET_COUNT)
            empty_count = sum(1 for item in enriched if not item.get("title"))
            if empty_count > len(enriched) * 0.5:
                raise ValueError(f"AI returned {empty_count}/{len(enriched)} empty titles — response malformed, skipping")
            results["providers"][key] = {"name": model_name, "status": "ok", "count": len(enriched), "rankings": enriched}
            print(f"  [OK] {model_name}: {len(enriched)} rankings")
        except Exception as e:
            safe_err = re.sub(r'AIza\S{20,}|sk-or-\S{20,}|Bearer\s+\S+|key[=:]\s*["\']?\S{10,}', '[REDACTED]', str(e))[:200]
            results["providers"][key] = {"name": model_name, "status": "error", "error": safe_err}
            print(f"  [FAIL] {model_name}: {safe_err}")
        # Rate limit: wait 2 seconds between calls
        time.sleep(2)

    output_path = os.path.join(SCRIPT_DIR, "static", "ai_rankings.json")
    tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(output_path), suffix='.tmp')
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        os.replace(tmp_path, output_path)
    except Exception:
        os.unlink(tmp_path)
        raise
    print(f"\nSaved to {output_path}")
    print(f"\nSuccess: {sum(1 for p in results['providers'].values() if p['status'] == 'ok')}/{len(MODELS)} models")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
