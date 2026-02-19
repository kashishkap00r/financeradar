#!/usr/bin/env python3
"""
WSW (Who Said What) Ranker — Generates 8 ranked debate clusters for the
Who Said What newsletter. Ingests 7-day rolling data from all sources
and calls AI to surface notable quotes with India relevance.
"""
import json
import urllib.request
import os
import ssl
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IST_TZ = timezone(timedelta(hours=5, minutes=30))
SSL_CONTEXT = ssl.create_default_context()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"

WSW_MODELS = {
    "gemini-2-5-flash": {
        "id": "gemini-2.0-flash",
        "name": "Gemini 2.0 Flash",
        "provider": "gemini"
    },
    "auto": {
        "id": "meta-llama/llama-3.3-70b-instruct:free",
        "name": "Auto (Best Free)",
        "provider": "openrouter"
    }
}

WSW_PROMPT = """You are the editor of "Who Said What" — an Indian finance newsletter surfacing notable quotes from business/finance figures.

Audience: informed Indians — investors, founders, policy thinkers.

INPUT: Numbered items from the last 7 days across news, Telegram, YouTube, Twitter.

TASK: Return exactly 8 debate clusters, each anchored by a quotable claim from a named person or institution.

PRIORITY: Named speakers with surprising/contrarian claims > institutional clashes > cross-border debates with India angle > structural macro claims.

HARD SKIPS: Price targets, earnings beats, routine filings, influencer fluff, crypto prices, brokerage order announcements.

DIVERSITY (CRITICAL — enforce before finalising):
Step 1: After picking your 8, list the REAL-WORLD SUBJECT of each (e.g. "AI", "oil prices", "aviation", "fintech"). The "theme" field label does NOT count — what matters is the actual subject.
Step 2: If any real-world subject appears more than twice, replace the excess with the next-best story on a DIFFERENT subject.
Step 3: Your final 8 MUST cover at least 5 different real-world subjects. AI/LLMs is ONE subject regardless of angle (policy, investment, safety, regulation). The India AI Summit counts as AI.
Subjects to draw from beyond AI: banking/credit, oil/commodities, trade/tariffs, geopolitics/defence, labour/jobs, real estate, equity markets, currencies, corporate M&A, agriculture, healthcare, infrastructure.

OUTPUT: Valid JSON array of exactly 8 objects. No markdown, no extra text.
Each object:
- rank: 1-8
- cluster_title: string (max 10 words, newsletter-ready)
- theme: one of "macro|policy|markets|trade|corporate|geopolitics|labour|tech"
- india_relevance: string (1 sentence)
- core_claim: string (1-2 sentences)
- quote_snippet: string (most quotable line, verbatim if possible)
- quote_speaker: string (name + role; "Unknown" if not identifiable)
- quote_source_type: one of "news|twitter|telegram|youtube|other"
- source_url_primary: string (URL or empty string)
- source_url_secondary: string (URL or empty string)
- counter_view: string (strongest opposing argument, 1 sentence)
- why_it_matters: string (1-2 sentences for the reader)
- confidence: one of "high|medium|low"

VALIDATION: Exactly 8 items, ranks 1-8 unique, at least 5 distinct topics covered.

## Source Items
{items}"""


def parse_dt(item):
    date_str = item.get("date", "")
    if not date_str:
        return datetime.min.replace(tzinfo=IST_TZ)
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST_TZ)
        return dt
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=IST_TZ)


def load_sources_7d():
    """Load items from all source files, filtered to last 7 days."""
    now = datetime.now(IST_TZ)
    cutoff = now - timedelta(days=7)
    items = []
    counts = {"news": 0, "twitter": 0, "telegram": 0, "youtube": 0}

    # --- News + Twitter (articles.json) ---
    articles_path = os.path.join(SCRIPT_DIR, "static", "articles.json")
    try:
        with open(articles_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for a in data.get("articles", []):
            if parse_dt(a) < cutoff:
                continue
            cat = a.get("category", "News")
            source_type = "twitter" if cat == "Twitter" else "news"
            items.append({
                "source_type": source_type,
                "title": a.get("title", ""),
                "speaker": a.get("source", ""),
                "url": a.get("url", ""),
                "date": a.get("date", ""),
            })
            counts[source_type] += 1
    except FileNotFoundError:
        print(f"WARNING: {articles_path} not found — skipping news/twitter")
    except Exception as e:
        print(f"WARNING: Error loading articles.json: {e}")

    # --- Telegram (telegram_reports.json) ---
    tg_path = os.path.join(SCRIPT_DIR, "static", "telegram_reports.json")
    try:
        with open(tg_path, "r", encoding="utf-8") as f:
            tg_data = json.load(f)
        for r in tg_data.get("reports", []):
            text = r.get("text", "").strip()
            if not text:
                continue
            if parse_dt(r) < cutoff:
                continue
            items.append({
                "source_type": "telegram",
                "title": text[:100].replace("\n", " "),
                "speaker": r.get("channel", ""),
                "url": r.get("url", ""),
                "date": r.get("date", ""),
            })
            counts["telegram"] += 1
    except FileNotFoundError:
        print(f"WARNING: {tg_path} not found — skipping telegram")
    except Exception as e:
        print(f"WARNING: Error loading telegram_reports.json: {e}")

    # --- YouTube (youtube_cache.json) ---
    yt_path = os.path.join(SCRIPT_DIR, "static", "youtube_cache.json")
    try:
        with open(yt_path, "r", encoding="utf-8") as f:
            yt_cache = json.load(f)
        for feed_id, videos in yt_cache.items():
            if not isinstance(videos, list):
                continue
            for v in videos:
                if parse_dt(v) < cutoff:
                    continue
                items.append({
                    "source_type": "youtube",
                    "title": v.get("title", ""),
                    "speaker": v.get("source", v.get("publisher", "")),
                    "url": v.get("link", v.get("url", "")),
                    "date": v.get("date", ""),
                })
                counts["youtube"] += 1
    except FileNotFoundError:
        print(f"WARNING: {yt_path} not found — skipping youtube")
    except Exception as e:
        print(f"WARNING: Error loading youtube_cache.json: {e}")

    total = sum(counts.values())
    print(
        f"Loaded {total} items "
        f"(news: {counts['news']}, telegram: {counts['telegram']}, "
        f"youtube: {counts['youtube']}, twitter: {counts['twitter']})"
    )
    return items, total


_AI_KEYWORDS = re.compile(
    r'\b(artificial intelligence|ai summit|ai safety|large language|llm|chatgpt|gemini|openai'
    r'|deepseek|anthropic|mistral|generative ai|gen ai|ai investment|ai policy|ai regulation'
    r'|ai governance|india ai|global ai|ai hub|ai infrastructure|ai compute|gpu)\b',
    re.IGNORECASE
)

def build_input_text(items):
    """Cap per source type AND per topic (AI capped at 20%), sort newest-first."""
    CAPS = {"news": 50, "telegram": 30, "youtube": 15, "twitter": 15}
    buckets = {k: [] for k in CAPS}
    for item in sorted(items, key=parse_dt, reverse=True):
        st = item["source_type"]
        if st in buckets and len(buckets[st]) < CAPS[st]:
            buckets[st].append(item)

    selected = buckets["news"] + buckets["telegram"] + buckets["youtube"] + buckets["twitter"]
    total_target = len(selected)
    ai_cap = 4  # hard cap: max 4 AI items so output can have at most 2 AI clusters

    final, ai_count = [], 0
    for item in selected:
        is_ai = bool(_AI_KEYWORDS.search(item["title"]))
        if is_ai:
            if ai_count < ai_cap:
                final.append(item)
                ai_count += 1
        else:
            final.append(item)

    lines = []
    for i, item in enumerate(final, 1):
        lines.append(
            f"{i}. [{item['source_type'].upper()}] {item['speaker']}: {item['title'][:120]} | {item['url']}"
        )
    print(f"  AI items: {ai_count}/{len(final)} (capped at {ai_cap})")
    return "\n".join(lines)


def parse_json_response(text):
    text = text.strip()
    if not text:
        raise ValueError("Empty response from model")
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
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Attempt recovery from truncated JSON: close any open string/object/array
        recovered = text
        # Count open vs closed braces
        opens = recovered.count('{') - recovered.count('}')
        arr_opens = recovered.count('[') - recovered.count(']')
        # If mid-string, close it
        if recovered.count('"') % 2 == 1:
            recovered += '"'
        recovered += '}' * max(0, opens) + ']' * max(0, arr_opens)
        recovered = re.sub(r',\s*}', '}', recovered)
        recovered = re.sub(r',\s*]', ']', recovered)
        return json.loads(recovered)


def call_openrouter(input_text, model_id):
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not set")
    prompt = WSW_PROMPT.format(items=input_text)
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
    with urllib.request.urlopen(request, timeout=90, context=SSL_CONTEXT) as response:
        result = json.loads(response.read().decode("utf-8"))
    return parse_json_response(result["choices"][0]["message"]["content"])


def call_gemini(input_text):
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    body = {
        "contents": [{"parts": [{"text": WSW_PROMPT.format(items=input_text)}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 8192}
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=90, context=SSL_CONTEXT) as response:
        result = json.loads(response.read().decode("utf-8"))
    text = result["candidates"][0]["content"]["parts"][0]["text"]
    return parse_json_response(text)


def main():
    print("=" * 50)
    print("WSW (Who Said What) Ranker")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    items, total = load_sources_7d()
    if not items:
        print("No items found. Exiting.")
        return

    input_text = build_input_text(items)
    print(f"Input: {len(input_text)} chars, {input_text.count(chr(10))+1} lines")

    results = {
        "generated_at": datetime.now(IST_TZ).isoformat(),
        "item_count": total,
        "providers": {}
    }

    print(f"\nCalling {len(WSW_MODELS)} AI models...\n")
    for key, model_config in WSW_MODELS.items():
        model_name = model_config["name"]
        model_id = model_config["id"]
        clusters = None
        for attempt in range(2):
            try:
                print(f"\nCalling {model_name} (attempt {attempt+1})...")
                if model_config["provider"] == "gemini":
                    clusters = call_gemini(input_text)
                else:
                    clusters = call_openrouter(input_text, model_id)
                if isinstance(clusters, dict):
                    clusters = clusters.get("clusters", clusters.get("items", []))
                if clusters:
                    print(f"  [OK] Got {len(clusters)} clusters")
                    break
                print("  [EMPTY] No clusters returned, retrying...")
                time.sleep(3)
            except Exception as e:
                safe_err = re.sub(r'Bearer\s+\S+|key=[^&\s]+', '[REDACTED]', str(e))[:200]
                print(f"  [FAIL] attempt {attempt+1}: {safe_err}")
                time.sleep(3)
        if clusters:
            for i, c in enumerate(clusters[:8], 1):
                c["rank"] = i
            n = len(clusters[:8])
            if n < 8:
                print(f"  WARNING: Only {n}/8 clusters (recovery may have truncated output)")
            results["providers"][key] = {
                "name": model_name, "status": "ok",
                "count": n, "clusters": clusters[:8]
            }
        else:
            results["providers"][key] = {
                "name": model_name, "status": "error",
                "error": "No clusters returned after retries"
            }
            print(f"  [FAIL] {model_name}: no clusters returned")
        time.sleep(2)

    if not any(p["status"] == "ok" for p in results["providers"].values()):
        print("\nAll models failed. Exiting.")
        sys.exit(1)

    output_path = os.path.join(SCRIPT_DIR, "static", "wsw_clusters.json")
    tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(output_path), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, output_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    ok = sum(1 for p in results["providers"].values() if p["status"] == "ok")
    print(f"\nSaved to {output_path}")
    print(f"Success: {ok}/{len(WSW_MODELS)} models")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
