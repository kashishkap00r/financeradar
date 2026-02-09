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

# Free models available on OpenRouter
MODELS = {
    "nemotron": {
        "id": "nvidia/llama-3.1-nemotron-nano-8b-v1:free",
        "name": "Nemotron Nano"
    },
    "gemini": {
        "id": "google/gemini-2.0-flash-thinking-exp:free",
        "name": "Gemini 2.0 Flash"
    },
    "llama": {
        "id": "meta-llama/llama-4-scout:free",
        "name": "Llama 4 Scout"
    },
    "mistral": {
        "id": "mistralai/mistral-small-3.1-24b-instruct:free",
        "name": "Mistral Small 3.1"
    }
}

RANKING_PROMPT = """You are a senior research analyst at a financial media company (like Zerodha's Daily Brief) curating stories for an Indian audience interested in markets, business, and economic policy.

Your readers are NOT day traders. They are long-term investors, policy watchers, and business professionals who want to understand structural shifts, not daily noise.

From these headlines (last 48 hours), select the TOP 20 most important stories.

## PRIORITIZE stories about:

### 1. Policy & Regulatory Changes (HIGH PRIORITY)
- RBI monetary policy, banking regulations, NBFC rules
- SEBI market structure changes, F&O rules, disclosure norms
- Government policy: PLI schemes, tariffs, FDI rules, labor laws
- Sector-specific regulation: telecom, pharma, energy, fintech
- Tax policy changes affecting businesses or investors

### 2. Structural Business & Corporate News (HIGH PRIORITY)
- Business model shifts, pivots, or existential challenges
- M&A deals that reshape industry structure
- IPO filings with detailed business model insights
- Corporate governance issues, frauds, whistleblower reports
- Companies entering/exiting major business lines

### 3. Macro & Fiscal Developments (HIGH PRIORITY)
- GDP data, inflation prints, employment numbers
- Budget announcements, fiscal deficit concerns
- Government borrowing, bond yields, liquidity conditions
- State-level fiscal stress or reforms
- Current account, forex reserves, trade balance

### 4. Infrastructure & Industrial Policy (MEDIUM-HIGH)
- Energy transition: renewables, coal phase-down, grid modernization
- Manufacturing: electronics, semiconductors, defense, auto
- Logistics: ports, railways, highways, warehousing
- Critical minerals, mining policy, resource nationalism

### 5. Commodities & Supply Chains (MEDIUM-HIGH)
- Global commodity price shifts with India impact
- Supply chain disruptions affecting Indian industries
- Agricultural commodities, MSP, food inflation
- Oil, gas, metals with structural (not daily) significance

### 6. Geopolitics Affecting India (MEDIUM)
- Trade deals, tariff negotiations (US, EU, UK)
- China+1 shifts benefiting/hurting India
- Global events affecting FII flows or trade
- Sanctions, export controls on tech/commodities

### 7. Banking & Financial Sector (MEDIUM)
- Bank results revealing NPA trends or credit growth shifts
- NBFC stress, liquidity issues, or regulatory action
- Insurance, AMC, or fintech structural changes
- Credit cycle indicators

## DEPRIORITIZE or IGNORE:
- Daily stock price movements ("Sensex up 200 points")
- Routine quarterly results without structural insight
- Short-term FII/DII flow data
- Broker upgrades/downgrades
- Crypto price movements
- Celebrity CEO statements without substance
- "Top 5 stocks to buy" type content
- Market volatility without underlying cause

## RANKING CRITERIA (in order):
1. Structural importance: Does this change how an industry/market works?
2. Policy signal: Does this indicate government/regulator direction?
3. Investment relevance: Does this affect long-term capital allocation?
4. Explanatory value: Does this help understand WHY something is happening?
5. Timeliness: Is this genuinely new information?

Headlines:
{headlines}

Return ONLY a valid JSON array with exactly 20 items (no markdown, no explanation, no code blocks):
[
  {{"rank": 1, "title": "exact headline text from above", "reason": "15 words max explaining structural importance"}},
  {{"rank": 2, "title": "exact headline text from above", "reason": "15 words max explaining structural importance"}},
  ...continue to rank 20...
]

IMPORTANT:
- Use the EXACT headline text from the list above. Do not paraphrase.
- Prefer depth over breadth - one major policy change beats five routine updates.
- If a story explains WHY something is happening, rank it higher than one that just reports WHAT happened."""


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

    # Sanitize headlines to avoid JSON parsing issues when AI echoes them back
    sanitized_to_article = {}
    for a in articles:
        sanitized = sanitize_headline(a['title'])
        sanitized_to_article[sanitized] = a

    headlines = "\n".join(f"- {sanitize_headline(a['title'])}" for a in articles)

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
                # Look up using sanitized title
                article = sanitized_to_article.get(title)
                enriched.append({
                    "rank": item.get("rank", len(enriched) + 1),
                    "title": article["title"] if article else title,  # Use original title
                    "url": article["url"] if article else "",
                    "source": article["source"] if article else "",
                    "reason": item.get("reason", "")
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
