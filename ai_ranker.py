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
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IST_TZ = timezone(timedelta(hours=5, minutes=30))
SSL_CONTEXT = ssl.create_default_context()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

RANKING_PROMPT = """You are a senior financial news editor for an Indian audience tracking markets, economy, and business.

From these headlines (last 48 hours), select the TOP 20 most important stories. Rank by:
1. Market impact (stocks, forex, commodities)
2. Policy significance (RBI, govt, regulations)
3. Corporate news (major deals, earnings, scandals)
4. Economic indicators and data
5. Global events affecting India

Headlines:
{headlines}

Return ONLY a valid JSON array with exactly 20 items (no markdown, no explanation, no code blocks):
[
  {{"rank": 1, "title": "exact headline text from above", "reason": "10 words max why important"}},
  {{"rank": 2, "title": "exact headline text from above", "reason": "10 words max why important"}},
  ...continue to rank 20...
]

IMPORTANT: Use the EXACT headline text from the list above. Do not paraphrase or modify titles."""


def load_articles_48h(max_articles=150):
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
                text = text[start:end+1]
    text = text.replace("\n", " ")
    text = re.sub(r',\s*]', ']', text)
    text = re.sub(r',\s*}', '}', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if text.count('[') > text.count(']'):
            text = text + ']' * (text.count('[') - text.count(']'))
        if text.count('{') > text.count('}'):
            text = text + '}' * (text.count('{') - text.count('}'))
        return json.loads(text)


def call_openrouter(headlines):
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not set")
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps({
            "model": "nvidia/nemotron-nano-9b-v2:free",
            "messages": [{"role": "user", "content": RANKING_PROMPT.format(headlines=headlines)}]
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://financeradar.pages.dev",
            "X-Title": "FinanceRadar"
        }
    )
    with urllib.request.urlopen(request, timeout=120, context=SSL_CONTEXT) as response:
        result = json.loads(response.read().decode("utf-8"))
    return parse_json_response(result["choices"][0]["message"]["content"])


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
    headlines = "\n".join(f"- {a['title']}" for a in articles)
    title_to_article = {a["title"]: a for a in articles}

    providers = {"openrouter": ("OpenRouter (Nemotron)", call_openrouter)}
    results = {"generated_at": datetime.now(IST_TZ).isoformat(), "article_count": len(articles), "providers": {}}

    print(f"\nCalling AI provider...\n")
    for key, (name, fn) in providers.items():
        try:
            rankings = fn(headlines)
            if isinstance(rankings, dict):
                rankings = rankings.get("rankings", rankings.get("items", []))
            enriched = []
            for item in rankings[:20]:
                title = item.get("title", "")
                article = title_to_article.get(title)
                enriched.append({
                    "rank": item.get("rank", len(enriched) + 1),
                    "title": title,
                    "url": article["url"] if article else "",
                    "source": article["source"] if article else "",
                    "reason": item.get("reason", "")
                })
            results["providers"][key] = {"name": name, "status": "ok", "count": len(enriched), "rankings": enriched}
            print(f"  [OK] {name}: {len(enriched)} rankings")
        except Exception as e:
            results["providers"][key] = {"name": name, "status": "error", "error": str(e)[:200]}
            print(f"  [FAIL] {name}: {str(e)[:200]}")

    output_path = os.path.join(SCRIPT_DIR, "static", "ai_rankings.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {output_path}")
    print(f"\nSuccess: {sum(1 for p in results['providers'].values() if p['status'] == 'ok')}/{len(providers)} providers")
    print("=" * 50)


if __name__ == "__main__":
    main()
