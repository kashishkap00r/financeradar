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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IST_TZ = timezone(timedelta(hours=5, minutes=30))
SSL_CONTEXT = ssl.create_default_context()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

MODELS = {
    "gemini-2-5-flash": {
        "id": "gemini-2.0-flash",
        "name": "Gemini 2.0 Flash",
        "provider": "gemini"
    },
    "auto": {
        "id": "openrouter/free",
        "name": "Auto (Best Free)",
        "provider": "openrouter"
    }
}

RANKING_PROMPT = """You are the editor of an Indian finance newsletter modeled on Zerodha's Daily Brief.
Audience: curious, informed Indians (long-term investors, founders, policy nerds).

INPUT
You will receive a list of news headlines from the last 48 hours.
Each headline is formatted as: - Headline text [Source Name]

TASK
Pick exactly 20 stories most relevant to Daily Brief.
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
No more than 3 selected stories from the same sector.

SOURCE QUALITY FILTER
Prefer primary reporting and strong analytical outlets.
De-prioritize republished wires, low-information rewrites, and unsourced hot takes.

SELECTION LOGIC
- Rank by editorial value, not recency alone.
- Prefer one strong explanatory piece over multiple repetitive updates.
- Remove duplicates/near-duplicates across sources.
- If fewer than 20 high-confidence stories exist, still return 20 by using medium-confidence picks that obey all hard-skip rules.

## Headlines
{headlines}

OUTPUT FORMAT (STRICT)
Return ONLY a JSON array of exactly 20 objects. No markdown, no commentary, no code blocks.

Each object must contain:
- rank: integer (1-20)
- title: string (exact headline text as given, including the [Source Name] tag)
- india_relevance: string (1 concise sentence)
- signal_type: one of ["mechanism", "structural-shift", "supply-chain", "policy-implication", "credible-opinion", "labour-trend"]
- why_it_matters: string (max 2 concise lines)
- confidence: one of ["high", "medium", "low"]

CRITICAL:
- Use the EXACT headline text from the input — do not paraphrase or modify it.
- Include the [Source Name] tag exactly as shown. This is required for the article match to work.
- When in doubt, pick the story that makes the reader say "I didn't know that" over "I already saw that."

VALIDATION BEFORE FINALIZING
- Exactly 20 items
- Ranks are unique and sequential 1..20
- No duplicate titles
- Every item has explicit India relevance
- Hard skips are excluded"""


def load_articles_48h(max_articles=200):
    articles_path = os.path.join(SCRIPT_DIR, "static", "articles.json")
    try:
        with open(articles_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: {articles_path} not found. Run aggregator.py first.")
        return []

    cutoff = datetime.now(IST_TZ) - timedelta(hours=48)
    articles = []
    for a in data["articles"]:
        if a["date"]:
            try:
                dt = datetime.fromisoformat(a["date"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=IST_TZ)
                if dt >= cutoff:
                    a["_parsed_date"] = dt
                    articles.append(a)
            except (ValueError, TypeError):
                articles.append(a)
        else:
            articles.append(a)
    articles.sort(key=lambda x: x.get("_parsed_date", datetime.min.replace(tzinfo=IST_TZ)), reverse=True)
    for a in articles:
        a.pop("_parsed_date", None)
    return articles[:max_articles]


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


def call_openrouter(headlines, model_id):
    """Call OpenRouter API with specified model."""
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not set")
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps({
            "model": model_id,
            "messages": [{"role": "user", "content": RANKING_PROMPT.format(headlines=headlines)}]
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://financeradar.kashishkapoor.com",
            "X-Title": "FinanceRadar"
        }
    )
    with urllib.request.urlopen(request, timeout=60, context=SSL_CONTEXT) as response:
        result = json.loads(response.read().decode("utf-8"))
    return parse_json_response(result["choices"][0]["message"]["content"])


def call_gemini(headlines, model_id):
    """Call Gemini API directly."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_id}:generateContent?key={GEMINI_API_KEY}"
    )
    body = {
        "contents": [{"parts": [{"text": RANKING_PROMPT.format(headlines=headlines)}]}],
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
    with urllib.request.urlopen(request, timeout=120, context=SSL_CONTEXT) as response:
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

    articles = load_articles_48h()
    if not articles:
        print("No articles found. Exiting.")
        return

    print(f"\nLoaded {len(articles)} articles from last 48 hours")

    # Build lookup dicts: exact-sanitized and normalized (for robust matching)
    sanitized_to_article = {}
    normalized_to_article = {}
    for a in articles:
        sanitized = sanitize_headline(a['title'])
        sanitized_to_article[sanitized] = a
        normalized_to_article[normalize_title(a['title'])] = a

    headlines = "\n".join(f"- {sanitize_headline(a['title'])} [{a.get('source', '')}]" for a in articles)

    results = {"generated_at": datetime.now(IST_TZ).isoformat(), "article_count": len(articles), "providers": {}}

    print(f"\nCalling {len(MODELS)} AI models...\n")
    for key, model_config in MODELS.items():
        model_id = model_config["id"]
        model_name = model_config["name"]
        try:
            if model_config.get("provider") == "gemini":
                rankings = call_gemini(headlines, model_id)
            else:
                rankings = call_openrouter(headlines, model_id)
            if isinstance(rankings, dict):
                rankings = rankings.get("rankings", rankings.get("items", []))
            enriched = []
            for item in rankings[:20]:
                title = item.get("title", "").strip()
                # Strip echoed [Source] bracket suffix the AI may repeat
                title = re.sub(r'\s*\[.*?\]\s*$', '', title)
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
                    "india_relevance": item.get("india_relevance", ""),
                    "signal_type": item.get("signal_type", ""),
                    "why_it_matters": item.get("why_it_matters", ""),
                    "confidence": item.get("confidence", ""),
                })
            empty_count = sum(1 for item in enriched if not item.get("title"))
            if empty_count > len(enriched) * 0.5:
                raise ValueError(f"AI returned {empty_count}/{len(enriched)} empty titles — response malformed, skipping")
            results["providers"][key] = {"name": model_name, "status": "ok", "count": len(enriched), "rankings": enriched}
            print(f"  [OK] {model_name}: {len(enriched)} rankings")
        except Exception as e:
            safe_err = re.sub(r'Bearer\s+\S+|key=[^&\s]+', '[REDACTED]', str(e))[:200]
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
