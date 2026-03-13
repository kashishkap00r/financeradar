#!/usr/bin/env python3
"""
LinkedIn Daily Brief Generator.

Reads FinanceRadar's AI rankings and generates 3-5 LinkedIn post
topic suggestions with hooks, data points, and angles.

Usage:
    GEMINI_API_KEY="..." python3 linkedin_brief.py
    GEMINI_API_KEY="..." python3 linkedin_brief.py --date 2026-03-14
    GEMINI_API_KEY="..." python3 linkedin_brief.py --no-ai   # skip Gemini, raw clustering only
"""
import json
import os
import ssl
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IST_TZ = timezone(timedelta(hours=5, minutes=30))
SSL_CONTEXT = ssl.create_default_context()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-3-flash-preview"
GEMINI_TIMEOUT = 120

RANKINGS_PATH = os.path.join(SCRIPT_DIR, "static", "ai_rankings.json")
BRIEFS_DIR = os.path.join(SCRIPT_DIR, "linkedin_briefs")

# ── Gemini API (same pattern as ai_ranker.py) ───────────────────────


def call_gemini(prompt):
    """Call Gemini API and return parsed JSON response."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 8192,
            "response_mime_type": "application/json",
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=GEMINI_TIMEOUT, context=SSL_CONTEXT) as response:
        result = json.loads(response.read().decode("utf-8"))

    candidates = result.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    if not text.strip():
        raise RuntimeError("Gemini returned empty response")
    return json.loads(text)


# ── Load rankings ───────────────────────────────────────────────────


def load_rankings():
    """Load AI rankings and flatten all buckets into a single list."""
    with open(RANKINGS_PATH, "r") as f:
        data = json.load(f)

    # Use the first available provider's rankings
    providers = data.get("providers", {})
    if not providers:
        print("ERROR: No providers found in ai_rankings.json")
        sys.exit(1)

    provider_key = next(iter(providers))
    provider = providers[provider_key]
    buckets = provider.get("buckets", {})

    articles = []
    for bucket_name, items in buckets.items():
        for item in items:
            item["bucket"] = bucket_name
            articles.append(item)

    generated_at = data.get("generated_at", "unknown")
    return articles, generated_at


# ── Build the brief prompt ──────────────────────────────────────────


BRIEF_PROMPT_TEMPLATE = """You are a LinkedIn content strategist for Kashish, an Indian finance professional at Zerodha with ~35K followers.

His style: analytical, data-driven, conversational, occasionally satirical. Writes substantive business/finance takes — NOT "5 tips" or motivational content.

He follows Jayant Mundhra's LinkedIn format:
- Provocative opening hook (stat, contrarian claim, or curiosity gap)
- Data-heavy body with specific numbers
- A "non-obvious angle" that most people miss
- Clear personal take/thesis
- Short, punchy paragraphs with ".." section breaks

TASK:
From the ranked articles below, identify exactly {count} distinct LinkedIn post opportunities.

For each, cluster 1-3 related articles into a single post theme. DO NOT suggest a post for every article — find the THEMES.

Good themes:
- A sector shift that connects 2-3 seemingly unrelated stories
- A policy change with second-order effects nobody is discussing
- A contrarian take on a viral headline
- A structural business change that reveals how an industry works
- India vs global comparison that reveals something surprising

ARTICLES:
{articles}

OUTPUT FORMAT (STRICT):
Return ONLY a JSON array of exactly {count} objects. No markdown, no commentary.

Each object:
- "theme": string (2-5 word theme label)
- "bucket_type": one of ["hot_take", "explainer", "deep_dive", "myth_buster", "sector_analysis"]
- "hook": string (the opening 1-2 lines for the LinkedIn post — provocative, specific, scroll-stopping)
- "key_data_points": array of 3-4 strings (specific numbers/facts to cite)
- "non_obvious_angle": string (the insight most people will miss — this is the core of the post)
- "your_take_prompt": string (a question to Kashish like "What's your stance on X?" to help him write the take section)
- "source_articles": array of objects with "title" and "url" fields
- "estimated_strength": one of ["strong", "medium"] (how likely this is to resonate)"""


def build_brief_prompt(articles, count=5):
    """Build the Gemini prompt from ranked articles."""
    lines = []
    for i, a in enumerate(articles, 1):
        parts = [
            f"{i}. [{a.get('bucket', '?').upper()}] {a['title']}",
            f"   Source: {a.get('source', 'Unknown')}",
            f"   Signal: {a.get('signal_type', 'unknown')}",
            f"   Why it matters: {a.get('why_it_matters', 'N/A')}",
            f"   India relevance: {a.get('india_relevance', 'N/A')}",
        ]
        lines.append("\n".join(parts))

    articles_text = "\n\n".join(lines)
    return BRIEF_PROMPT_TEMPLATE.format(count=count, articles=articles_text)


# ── Fallback: no-AI brief (just group by signal_type) ──────────────


def build_simple_brief(articles):
    """Group articles by signal_type without AI. Returns list of theme dicts."""
    groups = {}
    for a in articles:
        key = a.get("signal_type", "other")
        groups.setdefault(key, []).append(a)

    themes = []
    for signal_type, items in sorted(groups.items(), key=lambda x: -len(x[1])):
        top = items[:3]
        themes.append({
            "theme": signal_type.replace("-", " ").title(),
            "bucket_type": "explainer",
            "hook": f"[Write a hook about: {top[0]['title']}]",
            "key_data_points": [a.get("why_it_matters", a["title"]) for a in top],
            "non_obvious_angle": "[Find the non-obvious connection between these stories]",
            "your_take_prompt": f"What's your stance on {signal_type.replace('-', ' ')}?",
            "source_articles": [{"title": a["title"], "url": a.get("url", "")} for a in top],
            "estimated_strength": "medium",
        })
        if len(themes) >= 5:
            break
    return themes


# ── Format output ───────────────────────────────────────────────────


BUCKET_EMOJI = {
    "hot_take": "🔥",
    "explainer": "📊",
    "deep_dive": "🔍",
    "myth_buster": "💥",
    "sector_analysis": "📈",
}


def format_brief_markdown(themes, generated_at, date_str):
    """Format themes into a readable markdown brief."""
    lines = [
        f"# LinkedIn Brief — {date_str}",
        f"_Generated from FinanceRadar rankings ({generated_at})_\n",
    ]

    for i, t in enumerate(themes, 1):
        emoji = BUCKET_EMOJI.get(t.get("bucket_type", ""), "🎯")
        strength = t.get("estimated_strength", "medium")
        strength_tag = "⭐ STRONG" if strength == "strong" else "○ medium"

        lines.append(f"---\n")
        lines.append(f"## {emoji} Topic {i}: {t['theme']}  [{strength_tag}]")
        lines.append(f"**Type:** {t.get('bucket_type', 'unknown').replace('_', ' ').title()}\n")

        lines.append(f"**Suggested hook:**")
        lines.append(f"> {t['hook']}\n")

        lines.append(f"**Key data points:**")
        for dp in t.get("key_data_points", []):
            lines.append(f"- {dp}")
        lines.append("")

        lines.append(f"**Non-obvious angle:**")
        lines.append(f"> {t.get('non_obvious_angle', 'N/A')}\n")

        lines.append(f"**Your take prompt:** _{t.get('your_take_prompt', '')}_\n")

        lines.append(f"**Sources:**")
        for src in t.get("source_articles", []):
            title = src.get("title", "Untitled")
            url = src.get("url", "")
            if url:
                lines.append(f"- [{title}]({url})")
            else:
                lines.append(f"- {title}")
        lines.append("")

    lines.append("---")
    lines.append("_Pick one topic. Run `python3 linkedin_post.py <topic_number>` to scaffold your post._")
    return "\n".join(lines)


def format_brief_terminal(themes, date_str):
    """Format themes for terminal output with colors."""
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    RESET = "\033[0m"

    lines = [
        f"\n{BOLD}{'═' * 60}{RESET}",
        f"{BOLD}  LinkedIn Brief — {date_str}{RESET}",
        f"{BOLD}{'═' * 60}{RESET}\n",
    ]

    for i, t in enumerate(themes, 1):
        emoji = BUCKET_EMOJI.get(t.get("bucket_type", ""), "🎯")
        strength = t.get("estimated_strength", "medium")
        strength_color = GREEN if strength == "strong" else YELLOW

        lines.append(f"  {BOLD}{emoji} Topic {i}: {t['theme']}{RESET}  {strength_color}[{strength}]{RESET}")
        lines.append(f"  {DIM}Type: {t.get('bucket_type', '').replace('_', ' ').title()}{RESET}")
        lines.append(f"  {CYAN}Hook:{RESET} {t['hook']}")
        lines.append(f"  {CYAN}Angle:{RESET} {t.get('non_obvious_angle', 'N/A')}")
        lines.append(f"  {DIM}Sources: {', '.join(s.get('title', '')[:50] for s in t.get('source_articles', []))}{RESET}")
        lines.append(f"  {YELLOW}Take prompt:{RESET} {t.get('your_take_prompt', '')}")
        lines.append(f"  {'─' * 56}")
        lines.append("")

    lines.append(f"  {DIM}→ Pick a topic and run: python3 linkedin_post.py <number>{RESET}\n")
    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate LinkedIn topic briefs from FinanceRadar")
    parser.add_argument("--date", default=None, help="Date for the brief (YYYY-MM-DD)")
    parser.add_argument("--no-ai", action="store_true", help="Skip Gemini, use simple clustering")
    parser.add_argument("--count", type=int, default=5, help="Number of topics to generate")
    args = parser.parse_args()

    date_str = args.date or datetime.now(IST_TZ).strftime("%Y-%m-%d")

    # Load rankings
    articles, generated_at = load_rankings()
    if not articles:
        print("ERROR: No articles found in rankings")
        sys.exit(1)

    print(f"Loaded {len(articles)} ranked articles from {generated_at}")

    # Generate themes
    if args.no_ai:
        print("Using simple clustering (--no-ai mode)")
        themes = build_simple_brief(articles)
    else:
        print(f"Calling Gemini ({GEMINI_MODEL}) for topic clustering...")
        prompt = build_brief_prompt(articles, count=args.count)
        try:
            themes = call_gemini(prompt)
        except Exception as e:
            print(f"WARNING: Gemini call failed ({e}), falling back to simple clustering")
            themes = build_simple_brief(articles)

    if not themes:
        print("ERROR: No themes generated")
        sys.exit(1)

    # Save to file
    os.makedirs(BRIEFS_DIR, exist_ok=True)
    brief_path = os.path.join(BRIEFS_DIR, f"{date_str}.md")
    md_content = format_brief_markdown(themes, generated_at, date_str)
    with open(brief_path, "w") as f:
        f.write(md_content)

    # Also save raw JSON for linkedin_post.py to consume
    json_path = os.path.join(BRIEFS_DIR, f"{date_str}.json")
    with open(json_path, "w") as f:
        json.dump({"date": date_str, "generated_at": generated_at, "themes": themes}, f, indent=2)

    # Print to terminal
    print(format_brief_terminal(themes, date_str))
    print(f"Saved: {brief_path}")
    print(f"Saved: {json_path}")


if __name__ == "__main__":
    main()
