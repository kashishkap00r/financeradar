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
import time
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IST_TZ = timezone(timedelta(hours=5, minutes=30))
SSL_CONTEXT = ssl.create_default_context()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# Free models on OpenRouter - using auto-router + one specific model
MODELS = {
    "auto": {
        "id": "openrouter/free",
        "name": "Auto (Best Free)"
    },
    "nemotron": {
        "id": "nvidia/nemotron-3-nano-30b-a3b:free",
        "name": "Nemotron 3 Nano"
    }
}

RANKING_PROMPT = """You are the editor of a daily finance newsletter modelled on Zerodha's Daily Brief. Your readers are curious, informed Indians — long-term investors, founders, policy nerds — who open the newsletter for the "aha" stories they missed, not the headlines they already saw on Twitter.

Your job: pick the 20 best stories from the list below (last 48 hours).

## WHAT TO PICK — ranked by priority

### Priority 1 — Explanatory / "why-how" journalism (HIGHEST)
Stories that unpack the mechanism behind a headline. Think pieces titled "Why India's solar tariff flip matters for your power bill" or "How UPI's market-share cap could reshape fintech". If a headline promises to explain *why* something happened or *how* a system works, it almost certainly belongs.

### Priority 2 — Structural company / sector narratives
Deep dives into business-model shifts, industry restructurings, M&A that redraws boundaries, or governance blow-ups. Not "Company X beats estimates" but "Company X is quietly pivoting from Y to Z — here's what it means."

### Priority 3 — Commodity, supply-chain, and trade narratives with India impact
Oil, metals, agri-commodities, logistics bottlenecks, tariff wars — but only when the story explains the chain of cause-and-effect for Indian producers or consumers. Skip pure price tickers.

### Priority 4 — Major policy analysis (not announcements)
RBI, SEBI, government policy — but only when the piece analyses *implications*, not when it merely announces the gazette notification. Prefer "What RBI's new LCR norms mean for bank lending" over "RBI issues circular on LCR."

### Priority 5 — High-quality opinion / insider analysis
Columns, guest essays, or interviews that surface an original thesis — e.g., a former regulator explaining an under-reported risk, or a sector veteran connecting dots others miss.

### Priority 6 — Labour, employment, and social-economy trends
Stories on hiring/firing cycles, gig-economy regulation, skilling initiatives, rural consumption shifts — the human side of the economy that most market-focused feeds ignore.

## HARD SKIP — always exclude
- **All earnings / quarterly results** — even "record profit" or "revenue miss" headlines. No exceptions.
- **Wire-style breaking news** — one-line headlines that state a fact with no analysis ("Sensex rises 300 pts", "RBI keeps repo rate unchanged", "Company X appoints new CFO").
- **Routine regulatory filings** — board meeting notices, insider-trading disclosures, SEBI show-cause unless it's a major crackdown.
- **Market noise** — intraday moves, FII/DII daily flow tables, broker upgrades/downgrades, "top 5 stocks to buy" listicles.
- **Repetitive / duplicate coverage** — if five outlets report the same event, pick at most the one with the best explanatory angle.
- **Crypto price movements** and celebrity CEO fluff.

## DIVERSITY RULE — strictly enforced
No more than 2–3 stories from the same topic or sector. If you have four banking stories, keep only the two most insightful. Spread picks across sectors, themes, and story types.

## SCOPE
India lens only. A global story qualifies only if the piece explicitly connects it to Indian industry, policy, or consumers.

## Headlines
{headlines}

Return ONLY a valid JSON array with exactly 20 items (no markdown, no explanation, no code blocks):
[
  {{"rank": 1, "title": "exact headline text from above"}},
  {{"rank": 2, "title": "exact headline text from above"}},
  ...continue to rank 20...
]

IMPORTANT:
- Use the EXACT headline text from the list above — do not paraphrase or add anything.
- The headline may include a [Source Name] tag at the end. Include it exactly as shown so the match works.
- When in doubt, pick the story that makes the reader say "I didn't know that" over the one that makes them say "I already saw that."
- Quality over quantity: 20 genuinely interesting picks beat 30 padded ones."""


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

    # Sanitize headlines to avoid JSON parsing issues when AI echoes them back
    sanitized_to_article = {}
    for a in articles:
        sanitized = sanitize_headline(a['title'])
        sanitized_to_article[sanitized] = a

    headlines = "\n".join(f"- {sanitize_headline(a['title'])} [{a.get('source', '')}]" for a in articles)

    results = {"generated_at": datetime.now(IST_TZ).isoformat(), "article_count": len(articles), "providers": {}}

    print(f"\nCalling {len(MODELS)} AI models...\n")
    for key, model_config in MODELS.items():
        model_id = model_config["id"]
        model_name = model_config["name"]
        try:
            rankings = call_openrouter(headlines, model_id)
            if isinstance(rankings, dict):
                rankings = rankings.get("rankings", rankings.get("items", []))
            enriched = []
            for item in rankings[:20]:
                title = item.get("title", "").strip()
                # Strip echoed [Source] bracket suffix the AI may repeat
                title = re.sub(r'\s*\[.*?\]\s*$', '', title)
                # Look up using sanitized title
                article = sanitized_to_article.get(title)
                enriched.append({
                    "rank": item.get("rank", len(enriched) + 1),
                    "title": article["title"] if article else title,  # Use original title
                    "url": article["url"] if article else "",
                    "source": article["source"] if article else ""
                })
            results["providers"][key] = {"name": model_name, "status": "ok", "count": len(enriched), "rankings": enriched}
            print(f"  [OK] {model_name}: {len(enriched)} rankings")
        except Exception as e:
            results["providers"][key] = {"name": model_name, "status": "error", "error": str(e)[:200]}
            print(f"  [FAIL] {model_name}: {str(e)[:200]}")
        # Rate limit: wait 2 seconds between calls
        time.sleep(2)

    output_path = os.path.join(SCRIPT_DIR, "static", "ai_rankings.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {output_path}")
    print(f"\nSuccess: {sum(1 for p in results['providers'].values() if p['status'] == 'ok')}/{len(MODELS)} models")
    print("=" * 50)


if __name__ == "__main__":
    main()
