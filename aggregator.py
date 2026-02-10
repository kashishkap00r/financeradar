#!/usr/bin/env python3
"""
RSS News Aggregator
Fetches news from multiple RSS feeds and generates a static HTML website.
"""

import json
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import escape, unescape
import re
import ssl
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

# Get script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FEEDS_FILE = os.path.join(SCRIPT_DIR, "feeds.json")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "index.html")

# Create SSL context that doesn't verify certificates (some feeds have issues)
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

# IST timezone for consistent display
IST_TZ = timezone(timedelta(hours=5, minutes=30))

# =============================================================================
# CONTENT FILTERS - Patterns to filter out irrelevant/routine content
# =============================================================================

# Title patterns to filter (case-insensitive regex)
FILTER_TITLE_PATTERNS = [
    # Market price movements (routine daily updates)
    r"sensex (closes|ends|opens|gains|loses|falls|rises|at)",
    r"nifty (closes|ends|opens|gains|loses|falls|rises|at)",
    r"sensex.{0,10}nifty.*(close|end|open|gain|lose|fall|rise)",
    r"market (closes|ends|opens) (at|flat|higher|lower)",
    r"gold.*(rate|price).*(today|january|february|march|april|may|june|july|august|september|october|november|december)",
    r"silver.*(rate|price).*(today|january|february|march|april|may|june|july|august|september|october|november|december)",
    r"crude oil price today",
    r"petrol.*(price|rate).*today",
    r"diesel.*(price|rate).*today",
    r"dollar.*rupee.*(today|rate)",
    r"rupee (opens|closes|ends) at",
    r"forex rate today",
    r"currency rate today",

    # RBI routine operations
    r"money market operations as on",
    r"auction of.*treasury bills",
    r"auction of.*government securities",
    r"auction of state government securities",
    r"weekly statistical supplement",
    r"lending and deposit rates of scheduled commercial banks",
    r"directions under section 35a",
    r"auction result",

    # Live tickers
    r"live updates.*sensex",
    r"live updates.*nifty",
    r"stock market live",
    r"market live updates",
    r"trading live",

    # IPO routine
    r"ipo.*(gmp|grey market|gray market)",
    r"ipo subscription.*(status|day \d|times|x subscribed|\dx)",

    # MF/SIP routine
    r"best.*(mutual fund|mf|sip)",
    r"top \d+.*(mutual fund|fund|sip)",
    r"sip.*(contribution|inflow|record)",
    r"mutual fund.*(buy|invest|best)",

    # Holidays
    r"bank.*(holiday|closed|shut)",
    r"market.*(holiday|closed|shut)",
    r"trading holiday",
    r"banks closed",

    # Roundups
    r"week ahead.*market",
    r"markets this week",
    r"monthly roundup",
    r"weekly roundup",
    r"week in review",

    # Crypto prices
    r"bitcoin (falls|rises|drops|surges|crashes|slips|at \$)",
    r"ethereum (falls|rises|drops|surges|crashes|slips|at \$)",
    r"crypto.*(price|market update|today)",
    r"cryptocurrency.*(price|market update|today)",

    # Stock tips
    r"stock tip",
    r"intraday tip",
    r"\bbuy or sell\b",
    r"multibagger",
    r"stocks to buy",

    # Quarterly results roundups (routine lists)
    r"q[1-4]\s*results?\s*today",
    r"q[1-4]\s*results?\s*live",
    r"q[1-4]\s*earnings?\s*today",
    r"q[1-4]\s*earnings?\s*live",
    r"results?\s*today\s*live",
    r"earnings?\s*today\s*live",

    # Stocks to watch (routine daily lists)
    r"stocks?\s*to\s*watch\s*today",
    r"stocks?\s*to\s*watch\s*on",
    r"shares?\s*to\s*watch\s*today",
    r"stocks?\s*in\s*focus\s*today",
    r"stocks?\s*in\s*news\s*today",

    # Market opening predictions
    r"(flat|flattish|positive|negative|cautious|muted|weak|strong|higher|lower)\s*opening\s*(seen|expected|likely)",
    r"opening\s*(seen|expected)\s*(for|on)\s*(sensex|nifty|market)",

    # Stock Market Today/Highlights (daily roundups)
    r"stock\s*market\s*today",
    r"stock\s*market\s*highlights",
    r"market\s*highlights.*(sensex|nifty)",

    # Sensex/Nifty with big movement verbs
    r"sensex\s*(surges?|zooms?|jumps?|soars?|rallies?|tanks?|plunges?|crashes?|tumbles?|slumps?|skyrockets?)",
    r"nifty\s*(surges?|zooms?|jumps?|soars?|rallies?|tanks?|plunges?|crashes?|tumbles?|slumps?|skyrockets?)",

    # Point/percentage movements
    r"(sensex|nifty).{0,30}(up|down|adds?|sheds?|gains?|loses?)\s*\d+\s*(pts|points?|%)",

    # Prediction articles
    r"(sensex|nifty)\s*prediction",
    r"what\s*to\s*expect.*stock\s*market",
    r"what\s*to\s*expect.*(sensex|nifty)",

    # Top gainers/losers
    r"top\s*gainers",
    r"top\s*losers",
    r"gainers.{0,20}losers",

    # Technical analysis jargon
    r"(support|resistance).{0,15}(support|resistance)?\s*levels?",

    # Closing/Opening Bell
    r"closing\s*bell",
    r"opening\s*bell",

    # "Sensex today" / "Nifty today" patterns
    r"(sensex|nifty)\s*today\s*:",
    r"(sensex|nifty)\s*\d+.{0,10}(sensex|nifty)\s*today",
]

# URL patterns to filter (case-insensitive, substring match)
FILTER_URL_PATTERNS = [
    "/pr-release/",
    "/brandhub/",
    "/press-release/",
    "prnewswire.com",
    "businesswire.com",
    "/cartoon",
    "/cartoons",
    "/video",
    "/videos",
    "/podcast",
    "/travel",
    "/sports",
    "/weather",
    "/review",
    "/reviews",
    "/infographic",
    "/fashion",
    "/entertainment",
    "downtoearth.org.in/food",
]

# Compile regex patterns for performance
COMPILED_TITLE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in FILTER_TITLE_PATTERNS]

def should_filter_article(article):
    """Check if an article should be filtered out."""
    title = article.get("title", "").lower()
    link = article.get("link", "").lower()

    # Check URL patterns
    for pattern in FILTER_URL_PATTERNS:
        if pattern.lower() in link:
            return True

    # Check title patterns
    for pattern in COMPILED_TITLE_PATTERNS:
        if pattern.search(title):
            return True

    return False


# =============================================================================
# DUPLICATE HEADLINE GROUPING - Functions for similarity detection
# =============================================================================

def normalize_title(title):
    """Normalize title for comparison (lowercase, remove prefixes, clean)."""
    if not title:
        return ""

    # Convert to lowercase
    normalized = title.lower()

    # Remove common prefixes like "BREAKING:", "EXCLUSIVE:", "UPDATE:", etc.
    prefixes = [
        r'^breaking:\s*', r'^exclusive:\s*', r'^update:\s*', r'^urgent:\s*',
        r'^just in:\s*', r'^live:\s*', r'^watch:\s*', r'^video:\s*',
        r'^opinion:\s*', r'^analysis:\s*', r'^explained:\s*',
    ]
    for prefix in prefixes:
        normalized = re.sub(prefix, '', normalized, flags=re.IGNORECASE)

    # Remove punctuation and extra whitespace
    normalized = re.sub(r'[^\w\s]', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    return normalized


def titles_are_similar(title1, title2, threshold=0.75):
    """Check similarity using difflib.SequenceMatcher."""
    norm1 = normalize_title(title1)
    norm2 = normalize_title(title2)

    if not norm1 or not norm2:
        return False

    # Quick check: if titles are identical after normalization
    if norm1 == norm2:
        return True

    # Use SequenceMatcher for fuzzy matching
    ratio = SequenceMatcher(None, norm1, norm2).ratio()
    return ratio >= threshold


def get_title_signature(title):
    """Get a set of significant words from title for quick comparison."""
    normalized = normalize_title(title)
    words = set(normalized.split())
    # Filter out very short words and common words
    significant = {w for w in words if len(w) >= 4}
    return significant


def group_similar_articles(articles):
    """
    Group articles with similar titles.
    Returns list of article groups, each containing:
    - primary: Main article to display (first encountered)
    - related_sources: List of {name, url, link} from other sources
    - all_articles: All articles in the group

    Optimized: Only compare articles from the same date and uses word overlap
    as a quick filter before expensive SequenceMatcher comparison.
    """
    # Group articles by date first to reduce comparisons
    from collections import defaultdict

    articles_by_date = defaultdict(list)
    for i, article in enumerate(articles):
        date_key = ""
        if article.get("date"):
            try:
                date_key = article["date"].strftime("%Y-%m-%d")
            except:
                pass
        articles_by_date[date_key].append((i, article))

    groups = []
    used = set()

    # Pre-compute title signatures for all articles
    signatures = {}
    for i, article in enumerate(articles):
        signatures[i] = get_title_signature(article["title"])

    for date_key, date_articles in articles_by_date.items():
        for idx, (i, article) in enumerate(date_articles):
            if i in used:
                continue

            # Start a new group with this article
            group = {
                "primary": article,
                "related_sources": [],
                "all_articles": [article],
            }
            used.add(i)

            sig_i = signatures[i]

            # Only compare with other articles from the same date
            for j, other in date_articles[idx + 1:]:
                if j in used:
                    continue

                # Quick filter: check word overlap first
                sig_j = signatures[j]
                if sig_i and sig_j:
                    overlap = len(sig_i & sig_j)
                    min_len = min(len(sig_i), len(sig_j))
                    if min_len > 0 and overlap / min_len < 0.5:
                        # Not enough word overlap, skip expensive comparison
                        continue

                if titles_are_similar(article["title"], other["title"]):
                    # Don't add duplicates from the same source
                    if other["source"] != article["source"]:
                        group["related_sources"].append({
                            "name": other["source"],
                            "url": other["source_url"],
                            "link": other["link"],
                        })
                    group["all_articles"].append(other)
                    used.add(j)

            groups.append(group)

    return groups


def load_feeds():
    """Load feed configurations from JSON file."""
    try:
        with open(FEEDS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: {FEEDS_FILE} not found!")
        return []
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {FEEDS_FILE}: {e}")
        return []


def parse_date(date_str, source_name=None):
    """Try to parse various date formats from RSS feeds."""
    if not date_str:
        return None

    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S",  # RBI format (no timezone)
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%d %b %Y %H:%M:%S %z",
        "%d %b, %Y %z",  # SEBI format (02 Feb, 2026 +0530)
        "%d %b %Y %z",   # SEBI format without comma
    ]

    # Clean up common timezone issues
    date_str = date_str.strip()
    date_str = re.sub(r'\s+', ' ', date_str)
    date_str = date_str.replace("GMT", "+0000").replace("UTC", "+0000")
    date_str = date_str.replace("IST", "+0530").replace("EDT", "-0400").replace("EST", "-0500")

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                # RBI feeds are typically in IST but omit timezone
                if source_name and "RBI" in source_name:
                    dt = dt.replace(tzinfo=IST_TZ)
            return dt
        except ValueError:
            continue

    return None


def fetch_feed(feed_config):
    """Fetch and parse a single RSS feed."""
    feed_url = feed_config["feed"]
    feed_name = feed_config["name"]
    source_url = feed_config["url"]

    articles = []

    try:
        content = None

        # Try urllib first
        try:
            req = urllib.request.Request(
                feed_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9"
                }
            )
            with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as response:
                content = response.read()
        except urllib.error.HTTPError as e:
            if e.code == 403:
                # Fallback to curl with different User-Agents
                for ua in ["FeedFetcher/1.0", "Mozilla/5.0 (compatible; RSS Reader)"]:
                    result = subprocess.run(
                        ["curl", "-sL", "-A", ua, feed_url],
                        capture_output=True,
                        timeout=20
                    )
                    if result.returncode == 0 and result.stdout and result.stdout.strip().startswith(b'<'):
                        content = result.stdout
                        break
                if not content:
                    raise e
            else:
                raise e

        if not content:
            raise Exception("No content received")

        # Parse XML
        root = ET.fromstring(content)

        # Handle RSS 2.0 format
        items = root.findall(".//item")

        # Handle Atom format
        if not items:
            # Try Atom namespace
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            items = root.findall(".//atom:entry", ns)

            for item in items:
                title = item.find("atom:title", ns)
                link = item.find("atom:link", ns)

                # Fix deprecation: use explicit None checks instead of 'or'
                pub_date = item.find("atom:published", ns)
                if pub_date is None:
                    pub_date = item.find("atom:updated", ns)

                summary = item.find("atom:summary", ns)
                if summary is None:
                    summary = item.find("atom:content", ns)

                link_href = link.get("href") if link is not None else ""

                articles.append({
                    "title": title.text if title is not None and title.text else "No title",
                    "link": link_href,
                    "date": parse_date(pub_date.text if pub_date is not None else "", feed_name),
                    "description": summary.text[:300] if summary is not None and summary.text else "",
                    "source": feed_name,
                    "source_url": source_url,
                    "category": feed_config.get("category", "News"),
                    "publisher": feed_config.get("publisher", "")
                })
        else:
            # RSS 2.0 format
            for item in items:
                title = item.find("title")
                link = item.find("link")
                pub_date = item.find("pubDate")
                description = item.find("description")

                articles.append({
                    "title": title.text if title is not None and title.text else "No title",
                    "link": link.text if link is not None and link.text else "",
                    "date": parse_date(pub_date.text if pub_date is not None else "", feed_name),
                    "description": description.text[:300] if description is not None and description.text else "",
                    "source": feed_name,
                    "source_url": source_url,
                    "category": feed_config.get("category", "News"),
                    "publisher": feed_config.get("publisher", "")
                })

        print(f"  [OK] {feed_name}: {len(articles)} articles")

    except Exception as e:
        print(f"  [FAIL] {feed_name}: {str(e)[:50]}")

    return articles


def clean_html(text):
    """Remove HTML tags and clean up text."""
    if not text:
        return ""
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '', text)
    # Decode HTML entities (handles &nbsp;, &amp;, &lt;, etc.)
    clean = unescape(clean)
    # Remove extra whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean[:250] + "..." if len(clean) > 250 else clean


def get_sort_timestamp(article):
    """Get a comparable timestamp for sorting, handling timezone differences."""
    dt = article["date"]
    if dt is None:
        return 0  # Put at the end

    try:
        # timestamp() handles both aware and naive datetimes
        return dt.timestamp()
    except (OSError, OverflowError, ValueError):
        return 0


def to_local_datetime(dt):
    """Convert a datetime to IST for display."""
    if dt is None:
        return None

    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # Convert to IST via timestamp
        return datetime.fromtimestamp(dt.timestamp(), IST_TZ)
    except (OSError, OverflowError, ValueError):
        return dt


def export_articles_json(article_groups):
    """Export articles to JSON for AI ranker to consume."""
    articles = []
    for group in article_groups:
        article = group["primary"]
        articles.append({
            "title": article["title"],
            "url": article["link"],
            "source": article["source"],
            "date": article["date"].isoformat() if article["date"] else None,
            "category": article.get("category", "News"),
            "has_related": len(group["related_sources"]) > 0
        })
    output_path = os.path.join(SCRIPT_DIR, "static", "articles.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(IST_TZ).isoformat(), "articles": articles}, f, indent=2)
    print(f"Exported {len(articles)} articles to {output_path}")


def generate_html(article_groups):
    """Generate the static HTML website."""

    # Sort groups by date of primary article (newest first)
    def get_group_timestamp(group):
        return get_sort_timestamp(group["primary"])

    groups_with_date = [g for g in article_groups if g["primary"]["date"]]
    groups_without_date = [g for g in article_groups if not g["primary"]["date"]]

    groups_with_date.sort(key=get_group_timestamp, reverse=True)
    all_sorted_groups = groups_with_date + groups_without_date

    # Apply per-feed cap (max 50 articles per feed)
    MAX_PER_FEED = 50
    source_counts = {}
    capped_groups = []

    for group in all_sorted_groups:
        source = group["primary"]["source"]
        count = source_counts.get(source, 0)
        if count < MAX_PER_FEED:
            capped_groups.append(group)
            source_counts[source] = count + 1

    # Re-sort after capping
    capped_groups.sort(key=get_group_timestamp, reverse=True)
    sorted_groups = capped_groups

    # Extract flat list of primary articles for counting
    sorted_articles = [g["primary"] for g in sorted_groups]

    # Group by date
    now_ist = datetime.now(IST_TZ)
    today = now_ist.date()
    yesterday = today - timedelta(days=1)
    today_iso = today.isoformat()

    # Get unique sources for filter dropdown
    sources = sorted(set(a['source'] for a in sorted_articles))

    # Count in-focus articles (covered by multiple sources)
    in_focus_count = sum(1 for g in sorted_groups if g["related_sources"])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FinanceRadar</title>
    <link rel="icon" href="static/favicon.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700;900&family=Source+Sans+Pro:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #ffffff;
            --bg-secondary: #f8f9fa;
            --bg-hover: #f1f3f5;
            --text-primary: #1a1a2e;
            --text-secondary: #4a4a68;
            --text-muted: #8a8aa3;
            --accent: #e14b4b;
            --accent-hover: #c73b3b;
            --border: #e2e4e9;
            --border-light: #d0d3da;
            --card-shadow: 0 1px 3px rgba(0,0,0,0.06);
            --danger: #dc3545;
        }}
        [data-theme="light"] {{
            --bg-primary: #ffffff;
            --bg-secondary: #f8f9fa;
            --bg-hover: #f1f3f5;
            --text-primary: #1a1a2e;
            --text-secondary: #4a4a68;
            --text-muted: #8a8aa3;
            --accent: #e14b4b;
            --accent-hover: #c73b3b;
            --border: #e2e4e9;
            --border-light: #d0d3da;
            --card-shadow: 0 1px 3px rgba(0,0,0,0.06);
            --danger: #dc3545;
        }}
        [data-theme="dark"] {{
            --bg-primary: #0f1419;
            --bg-secondary: #161b22;
            --bg-hover: #1c2430;
            --text-primary: #e6edf3;
            --text-secondary: #b0bac5;
            --text-muted: #7d8590;
            --accent: #e14b4b;
            --accent-hover: #ff6b6b;
            --border: #2a3140;
            --border-light: #363f50;
            --card-shadow: 0 1px 3px rgba(0,0,0,0.2);
            --danger: #ff6b6b;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        *:focus-visible {{
            outline: 2px solid var(--accent);
            outline-offset: 2px;
        }}

        html {{
            scroll-behavior: smooth;
        }}

        body {{
            font-family: 'Source Sans Pro', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            font-size: 16px;
        }}

        /* Sticky Header */
        .top-bar {{
            position: sticky;
            top: 0;
            background: var(--bg-primary);
            border-bottom: 1px solid var(--border);
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            padding: 12px 16px;
            z-index: 100;
        }}

        .top-bar-inner {{
            max-width: 900px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .brand {{
            display: flex;
            align-items: center;
            gap: 10px;
            white-space: nowrap;
        }}
        .logo {{
            font-family: 'Merriweather', Georgia, serif;
            font-weight: 700;
            font-size: 1.1em;
            letter-spacing: -0.5px;
            color: var(--text-primary);
            padding-bottom: 2px;
            border-bottom: 3px solid var(--accent);
        }}

        .search-box {{
            flex: 1;
            position: relative;
        }}

        #search {{
            width: 100%;
            height: 36px;
            padding: 0 12px 0 34px;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 14px;
            transition: border-color 0.2s;
        }}

        #search:focus {{
            outline: none;
            border-color: var(--accent);
        }}

        .search-icon {{
            position: absolute;
            left: 10px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
            font-size: 14px;
        }}

        .theme-toggle {{
            padding: 0;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-primary);
            cursor: pointer;
            transition: border-color 0.2s, background 0.2s;
            line-height: 0;
            position: relative;
            z-index: 2;
            pointer-events: auto;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 32px;
        }}
        .theme-toggle:hover {{
            border-color: var(--border-light);
            background: var(--bg-hover);
        }}
        .theme-toggle svg {{
            width: 16px;
            height: 16px;
            stroke: currentColor;
            fill: none;
            stroke-width: 2;
            stroke-linecap: round;
            stroke-linejoin: round;
        }}
        .theme-toggle .icon-sun {{
            display: none;
        }}
        .theme-toggle[data-theme="dark"] .icon-moon {{
            display: none;
        }}
        .theme-toggle[data-theme="dark"] .icon-sun {{
            display: inline;
        }}

        /* Main Content */
        .container {{
            max-width: 900px;
            margin: 0 auto;
            padding: 16px;
        }}

        /* Filter Card */
        .filter-card {{
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 14px 18px;
            margin-bottom: 12px;
            box-shadow: var(--card-shadow);
        }}

        /* Stats Bar */
        .stats-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0 0 8px 0;
        }}

        .stats {{
            display: flex;
            gap: 20px;
            font-size: 13px;
            color: var(--text-secondary);
        }}

        .stats span {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        /* In Focus Row */
        .in-focus-row {{
            padding: 8px 0 0 0;
            display: flex;
            justify-content: center;
        }}

        /* In Focus Button with Pulsing Dot */
        .in-focus-btn {{
            display: inline-flex;
            align-items: center;
            gap: 10px;
            padding: 8px 20px;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 20px;
            color: var(--text-secondary);
            font-size: 13px;
            font-family: inherit;
            cursor: pointer;
            transition: all 0.15s;
        }}
        .in-focus-btn:hover {{
            border-color: var(--accent);
            color: var(--text-primary);
        }}
        .in-focus-btn.active {{
            background: var(--accent);
            border-color: var(--accent);
            color: #fff;
        }}
        .in-focus-btn.active .pulse-dot {{
            background: #fff;
            box-shadow: 0 0 0 0 rgba(255, 255, 255, 0.4);
        }}

        /* Pulsing Dot */
        .pulse-dot {{
            width: 10px;
            height: 10px;
            background: var(--accent);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }}

        @keyframes pulse {{
            0% {{
                box-shadow: 0 0 0 0 rgba(225, 75, 75, 0.6);
            }}
            70% {{
                box-shadow: 0 0 0 10px rgba(225, 75, 75, 0);
            }}
            100% {{
                box-shadow: 0 0 0 0 rgba(225, 75, 75, 0);
            }}
        }}

        .update-time {{
            font-size: 13px;
            color: var(--text-muted);
        }}

        /* Category Links */
        .category-links {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 0;
            font-size: 13px;
            flex-wrap: wrap;
        }}
        .filter-label {{
            color: var(--text-muted);
            margin-right: 4px;
        }}
        .category-link {{
            color: var(--text-secondary);
            text-decoration: none;
            padding-bottom: 2px;
            transition: color 0.15s;
        }}
        .category-link:hover {{
            color: var(--text-primary);
        }}
        .category-link.active {{
            color: var(--text-primary);
            border-bottom: 2px solid var(--accent);
        }}
        .category-sep {{
            color: var(--text-muted);
        }}

        /* Pagination */
        .pagination {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: center;
            gap: 4px;
            padding: 12px 0;
            width: 100%;
        }}
        .pagination.bottom {{
            margin-top: 20px;
            border-top: 1px solid var(--border);
        }}
        .page-numbers {{
            display: flex;
            align-items: center;
            gap: 4px;
        }}
        .page-btn {{
            padding: 6px 12px;
            border: none;
            background: transparent;
            color: var(--text-muted);
            font-size: 13px;
            font-family: inherit;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.15s;
        }}
        .page-btn:hover {{
            background: var(--bg-hover);
            color: var(--text-primary);
        }}
        .page-btn:disabled {{
            opacity: 0.4;
            cursor: default;
        }}
        .page-btn:disabled:hover {{
            background: transparent;
            color: var(--text-muted);
        }}
        .page-btn.active {{
            background: var(--accent);
            color: #fff;
            font-weight: 500;
        }}
        .page-btn.active:hover {{
            background: var(--accent-hover);
            color: #fff;
        }}
        .page-btn.nav {{
            color: var(--text-secondary);
            font-weight: 500;
        }}
        .page-btn.nav:hover {{
            color: var(--text-primary);
        }}
        .page-btn.nav.prev {{
            margin-right: 8px;
        }}
        .page-btn.nav.next {{
            margin-left: 8px;
        }}
        .page-ellipsis {{
            padding: 6px 4px;
            color: var(--text-muted);
            font-size: 13px;
        }}

        /* Date Headers */
        .date-header {{
            position: sticky;
            top: 53px;
            background: var(--bg-primary);
            padding: 16px 0 12px 0;
            margin-top: 24px;
            font-family: 'Source Sans Pro', sans-serif;
            font-size: 13px;
            font-weight: 700;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 1px;
            z-index: 50;
        }}

        .date-header:first-child {{
            margin-top: 0;
        }}

        /* Article List */
        .article {{
            padding: 16px 20px;
            margin-bottom: 12px;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: var(--bg-secondary);
            transition: box-shadow 0.2s ease, border-color 0.2s ease, transform 0.15s ease;
        }}
        .article:hover {{
            box-shadow: var(--card-shadow);
            border-color: var(--border-light);
            transform: translateY(-1px);
        }}

        .article-title {{
            font-family: 'Merriweather', Georgia, serif;
            font-size: 17px;
            font-weight: 700;
            line-height: 1.45;
            margin-bottom: 6px;
        }}

        .article-title a {{
            color: var(--text-primary);
            text-decoration: none;
            transition: color 0.15s;
        }}

        .article-title a:hover {{
            color: var(--accent);
        }}

        .article-title a:visited {{
            color: var(--text-secondary);
        }}

        .article-meta {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
            color: var(--text-muted);
        }}

        .source-tag {{
            color: var(--text-secondary);
            text-decoration: none;
            transition: color 0.15s;
            border-bottom: 2px solid var(--accent);
            padding-bottom: 1px;
        }}

        .source-tag:hover {{
            color: var(--accent);
        }}

        .meta-dot {{
            color: var(--text-muted);
        }}

        .article-time {{
            color: var(--text-muted);
        }}

        .article-description {{
            margin-top: 8px;
            font-size: 14.5px;
            color: var(--text-secondary);
            line-height: 1.55;
        }}

        /* Footer */
        footer {{
            margin-top: 48px;
            padding: 28px 0;
            border-top: 1px solid var(--border);
            text-align: center;
            font-size: 13px;
            color: var(--text-muted);
        }}
        footer a {{
            color: var(--text-muted);
            text-decoration: none;
            border-bottom: 2px solid var(--accent);
            padding-bottom: 1px;
        }}
        footer a:hover {{
            color: var(--accent);
        }}

        /* Bookmark Button (per article) */
        .bookmark-btn {{
            background: none;
            border: none;
            cursor: pointer;
            padding: 10px;
            color: var(--text-muted);
            transition: color 0.15s, transform 0.15s;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            touch-action: manipulation;
            -webkit-tap-highlight-color: transparent;
        }}
        .bookmark-btn:hover {{
            color: var(--accent);
            transform: scale(1.1);
        }}
        .bookmark-btn.bookmarked {{
            color: var(--accent);
        }}
        .bookmark-btn svg {{
            width: 16px;
            height: 16px;
            stroke: currentColor;
            stroke-width: 2;
            fill: none;
            pointer-events: none;
        }}
        .bookmark-btn.bookmarked svg {{
            fill: currentColor;
        }}

        /* Bookmarks Header Button */
        .bookmarks-toggle {{
            position: relative;
            padding: 0;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-primary);
            cursor: pointer;
            transition: border-color 0.2s, background 0.2s;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 32px;
        }}
        .bookmarks-toggle:hover {{
            border-color: var(--border-light);
            background: var(--bg-hover);
        }}
        .bookmarks-toggle svg {{
            width: 16px;
            height: 16px;
            stroke: currentColor;
            fill: none;
            stroke-width: 2;
        }}
        .bookmarks-toggle.has-bookmarks svg {{
            fill: var(--accent);
            stroke: var(--accent);
        }}
        .bookmark-count {{
            position: absolute;
            top: -6px;
            right: -6px;
            background: var(--accent);
            color: #fff;
            font-size: 10px;
            font-weight: 600;
            min-width: 16px;
            height: 16px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0 4px;
        }}
        .bookmark-count.hidden {{
            display: none;
        }}

        /* AI Toggle Button */
        .ai-toggle {{
            position: relative;
            padding: 0;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-primary);
            cursor: pointer;
            transition: border-color 0.2s, background 0.2s;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 32px;
        }}
        .ai-toggle:hover {{
            border-color: var(--border-light);
            background: var(--bg-hover);
        }}

        /* Bookmarks Sidebar */
        .sidebar-overlay {{
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.5);
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.3s, visibility 0.3s;
            z-index: 200;
        }}
        .sidebar-overlay.open {{
            opacity: 1;
            visibility: visible;
        }}
        .bookmarks-sidebar {{
            position: fixed;
            top: 0;
            right: 0;
            width: 400px;
            max-width: 90vw;
            height: 100vh;
            background: var(--bg-primary);
            border-left: 1px solid var(--border);
            transform: translateX(100%);
            transition: transform 0.3s ease;
            z-index: 201;
            display: flex;
            flex-direction: column;
        }}
        .sidebar-overlay.open .bookmarks-sidebar {{
            transform: translateX(0);
        }}
        .sidebar-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px 20px;
            border-bottom: 1px solid var(--border);
            flex-shrink: 0;
        }}
        .sidebar-title {{
            font-family: 'Merriweather', Georgia, serif;
            font-size: 16px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .sidebar-close {{
            background: none;
            border: none;
            cursor: pointer;
            color: var(--text-muted);
            padding: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: color 0.15s;
        }}
        .sidebar-close:hover {{
            color: var(--text-primary);
        }}
        .sidebar-close svg {{
            width: 20px;
            height: 20px;
            stroke: currentColor;
            stroke-width: 2;
        }}
        .sidebar-content {{
            flex: 1;
            overflow-y: auto;
            padding: 12px 0;
        }}
        .sidebar-empty {{
            padding: 40px 20px;
            text-align: center;
            color: var(--text-muted);
            font-size: 14px;
        }}
        .sidebar-article {{
            padding: 12px 20px;
            border-bottom: 1px solid var(--border);
            transition: background 0.15s;
        }}
        .sidebar-article:hover {{
            background: var(--bg-hover);
        }}
        .sidebar-article-title {{
            font-family: 'Merriweather', Georgia, serif;
            font-size: 14px;
            font-weight: 500;
            line-height: 1.4;
            margin-bottom: 6px;
        }}
        .sidebar-article-title a {{
            color: var(--text-primary);
            text-decoration: none;
        }}
        .sidebar-article-title a:hover {{
            color: var(--accent);
        }}
        .sidebar-article-meta {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
            color: var(--text-muted);
        }}
        .sidebar-article-source {{
            color: var(--text-secondary);
        }}
        .sidebar-remove {{
            background: none;
            border: none;
            cursor: pointer;
            color: var(--text-muted);
            padding: 2px;
            transition: color 0.15s;
        }}
        .sidebar-remove:hover {{
            color: var(--accent);
        }}
        .sidebar-footer {{
            padding: 12px 20px;
            border-top: 1px solid var(--border);
            display: flex;
            gap: 8px;
            flex-shrink: 0;
        }}
        .sidebar-btn {{
            flex: 1;
            padding: 8px 12px;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-secondary);
            font-size: 12px;
            cursor: pointer;
            transition: all 0.15s;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }}
        .sidebar-btn:hover {{
            background: var(--bg-hover);
            border-color: var(--border-light);
            color: var(--text-primary);
        }}
        .sidebar-btn.danger:hover {{
            border-color: var(--danger);
            color: var(--danger);
        }}
        .sidebar-btn.copied {{
            border-color: #22c55e;
            color: #22c55e;
        }}

        /* AI Sidebar */
        .ai-sidebar {{
            position: fixed;
            top: 0;
            right: 0;
            width: 400px;
            max-width: 90vw;
            height: 100vh;
            background: var(--bg-primary);
            border-left: 1px solid var(--border);
            transform: translateX(100%);
            transition: transform 0.3s ease;
            z-index: 201;
            display: flex;
            flex-direction: column;
        }}
        .sidebar-overlay.open .ai-sidebar {{
            transform: translateX(0);
        }}
        .ai-provider-select {{
            padding: 12px 20px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .ai-provider-select label {{
            font-size: 13px;
            color: var(--text-secondary);
        }}
        .ai-provider-select select {{
            flex: 1;
            padding: 6px 10px;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text-primary);
            font-family: inherit;
            font-size: 13px;
        }}
        .ai-rank-item {{
            display: flex;
            gap: 12px;
            padding: 10px 20px;
            border-bottom: 1px solid var(--border);
            align-items: flex-start;
        }}
        .ai-rank-item:hover {{
            background: var(--bg-hover);
        }}
        .rank-num {{
            font-weight: 600;
            color: var(--accent);
            min-width: 20px;
            font-size: 13px;
        }}
        .rank-content {{
            flex: 1;
            min-width: 0;
        }}
        .rank-content a {{
            display: block;
            font-family: 'Merriweather', Georgia, serif;
            color: var(--text-primary);
            text-decoration: none;
            font-size: 13px;
            line-height: 1.4;
        }}
        .rank-content a:hover {{
            color: var(--accent);
        }}
        .rank-source {{
            display: block;
            font-size: 10px;
            color: var(--text-muted);
            margin-top: 2px;
            opacity: 0.7;
        }}
        .ai-updated-time {{
            font-size: 11px;
            color: var(--text-muted);
        }}
        .ai-error {{
            padding: 40px 20px;
            text-align: center;
        }}
        .ai-error-title {{
            color: var(--danger);
            font-weight: 600;
            margin-bottom: 8px;
        }}
        .ai-bookmark-btn {{
            background: none;
            border: none;
            cursor: pointer;
            color: var(--text-muted);
            padding: 12px;
            margin: -8px -8px -8px 0;
            flex-shrink: 0;
            touch-action: manipulation;
            -webkit-tap-highlight-color: transparent;
            position: relative;
            z-index: 1;
        }}
        .ai-bookmark-btn:hover {{
            color: var(--accent);
        }}
        .ai-bookmark-btn.bookmarked {{
            color: var(--accent);
        }}
        .ai-bookmark-btn svg {{
            width: 16px;
            height: 16px;
            stroke: currentColor;
            fill: none;
            stroke-width: 2;
            pointer-events: none;
        }}
        .ai-bookmark-btn.bookmarked svg {{
            fill: var(--accent);
        }}

        /* Back to Top */
        .back-to-top {{
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 40px;
            height: 40px;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 10px;
            box-shadow: var(--card-shadow);
            color: var(--text-secondary);
            font-size: 18px;
            cursor: pointer;
            opacity: 0;
            visibility: hidden;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .back-to-top.visible {{
            opacity: 1;
            visibility: visible;
        }}

        .back-to-top:hover {{
            background: var(--bg-hover);
            border-color: var(--border-light);
            color: var(--text-primary);
        }}

        /* Keyboard hint */
        .keyboard-hint {{
            position: fixed;
            bottom: 24px;
            left: 24px;
            font-size: 12px;
            color: var(--text-muted);
            background: var(--bg-secondary);
            padding: 8px 12px;
            border-radius: 8px;
            border: 1px solid var(--border);
            opacity: 0.7;
        }}

        .keyboard-hint kbd {{
            background: var(--bg-hover);
            padding: 2px 6px;
            border-radius: 3px;
            font-family: inherit;
            margin: 0 2px;
        }}

        /* Hidden */
        .hidden {{
            display: none !important;
        }}
        .paged-hidden {{
            display: none !important;
        }}

        /* Also Covered By */
        .also-covered {{
            margin-top: 6px;
            font-size: 12px;
            color: var(--text-muted);
        }}
        .also-covered a {{
            color: var(--text-secondary);
            text-decoration: none;
            transition: color 0.15s;
        }}
        .also-covered a:hover {{
            color: var(--accent);
        }}

        /* Source Count Badge */
        .source-badge {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 2px 8px;
            background: var(--accent);
            color: #fff;
            font-size: 11px;
            font-weight: 500;
            border-radius: 10px;
            margin-left: 8px;
        }}

        /* Publisher text links */
        .publisher-links {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 0;
            font-size: 13px;
            flex-wrap: wrap;
        }}
        .publisher-label {{
            color: var(--text-muted);
            margin-right: 4px;
        }}
        .publisher-link {{
            color: var(--text-secondary);
            text-decoration: none;
            padding-bottom: 2px;
            transition: color 0.15s;
        }}
        .publisher-link:hover {{
            color: var(--text-primary);
        }}
        .publisher-link.active {{
            color: var(--text-primary);
            border-bottom: 2px solid var(--accent);
        }}
        .publisher-sep {{
            color: var(--text-muted);
        }}

        /* Responsive */
        @media (max-width: 640px) {{
            .top-bar-inner {{
                flex-wrap: wrap;
            }}

            .brand {{
                width: 100%;
                margin-bottom: 8px;
            }}

            .search-box {{
                flex: 1;
            }}

            #source-filter {{
                min-width: 120px;
            }}

            .article {{
                padding: 14px 16px;
                margin-bottom: 10px;
                border-radius: 8px;
            }}

            .article:hover {{
                transform: none;
                box-shadow: none;
                border-color: var(--border);
            }}

            .keyboard-hint {{
                display: none;
            }}

            /* Mobile bookmarks sidebar fix */
            .bookmarks-sidebar {{
                height: 100%;
                height: 100dvh;
                max-height: -webkit-fill-available;
            }}

            .sidebar-content {{
                flex: 1;
                min-height: 0;
                overflow-y: auto;
                -webkit-overflow-scrolling: touch;
            }}

            .sidebar-footer {{
                padding: 16px 20px;
                padding-bottom: max(16px, env(safe-area-inset-bottom));
                background: var(--bg-primary);
                position: sticky;
                bottom: 0;
            }}
        }}
    </style>
</head>
<body>
    <div class="top-bar">
        <div class="top-bar-inner">
            <div class="brand">
                <div class="logo">FinanceRadar</div>
            </div>
            <div class="search-box">
                <span class="search-icon">&#128269;</span>
                <input type="text" id="search" placeholder="Search articles..." oninput="filterArticles()">
            </div>
            <button id="ai-toggle" class="ai-toggle" type="button" aria-label="AI Picks" title="AI Picks" onclick="openAiSidebar()">
                <span style="font-size: 16px;">🤖</span>
            </button>
            <button id="bookmarks-toggle" class="bookmarks-toggle" type="button" aria-label="View bookmarks" title="View bookmarks">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>
                </svg>
                <span id="bookmark-count" class="bookmark-count hidden">0</span>
            </button>
            <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Toggle theme" title="Toggle theme">
                <svg class="icon-moon feather feather-moon" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
                </svg>
                <svg class="icon-sun feather feather-sun" viewBox="0 0 24 24" aria-hidden="true">
                    <circle cx="12" cy="12" r="5"></circle>
                    <line x1="12" y1="1" x2="12" y2="3"></line>
                    <line x1="12" y1="21" x2="12" y2="23"></line>
                    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
                    <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
                    <line x1="1" y1="12" x2="3" y2="12"></line>
                    <line x1="21" y1="12" x2="23" y2="12"></line>
                    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
                    <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
                </svg>
            </button>
        </div>
    </div>

    <!-- Bookmarks Sidebar -->
    <div id="sidebar-overlay" class="sidebar-overlay">
        <div class="bookmarks-sidebar">
            <div class="sidebar-header">
                <div class="sidebar-title">
                    <svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" fill="none" stroke-width="2">
                        <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>
                    </svg>
                    Bookmarks
                </div>
                <button class="sidebar-close" onclick="closeSidebar()" aria-label="Close sidebar">
                    <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                </button>
            </div>
            <div id="sidebar-content" class="sidebar-content">
                <div class="sidebar-empty">No bookmarks yet.<br>Click the bookmark icon on articles to save them.</div>
            </div>
            <div class="sidebar-footer">
                <button class="sidebar-btn copy-btn" onclick="copyBookmarks()">
                    <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" fill="none" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                    </svg>
                    <span>Copy All</span>
                </button>
                <button class="sidebar-btn danger" onclick="clearAllBookmarks()">Clear All</button>
            </div>
        </div>
    </div>

    <!-- AI Rankings Sidebar -->
    <div id="ai-sidebar-overlay" class="sidebar-overlay">
        <div class="ai-sidebar">
            <div class="sidebar-header">
                <div class="sidebar-title"><span style="font-size: 18px;">🤖</span> AI Picks</div>
                <button class="sidebar-close" onclick="closeAiSidebar()" aria-label="Close sidebar">
                    <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                </button>
            </div>
            <div class="ai-provider-select">
                <label for="ai-provider">Model:</label>
                <select id="ai-provider" onchange="switchAiProvider()">
                    <option value="">Loading...</option>
                </select>
            </div>
            <div id="ai-rankings-content" class="sidebar-content">
                <div class="sidebar-empty">Loading AI rankings...</div>
            </div>
            <div class="sidebar-footer">
                <span id="ai-updated" class="ai-updated-time">Updated: --</span>
            </div>
        </div>
    </div>

    <div class="container">
        <div class="filter-card">
            <div class="stats-bar">
                <div class="stats">
                    <span><strong>{len(sorted_articles)}</strong> articles</span>
                    <span><strong>{len(sources)}</strong> sources</span>
                </div>
                <span class="update-time" id="update-time" data-time="{now_ist.isoformat()}">Updated {now_ist.strftime("%b %d, %I:%M %p")} IST</span>
            </div>

            <div class="category-links" id="category-tabs">
                <span class="filter-label">Category:</span>
                <a href="#" class="category-link" data-category="news" onclick="toggleCategory('news'); return false;">News</a>
                <span class="category-sep">·</span>
                <a href="#" class="category-link" data-category="institutions" onclick="toggleCategory('institutions'); return false;">Institutions</a>
                <span class="category-sep">·</span>
                <a href="#" class="category-link" data-category="ideas" onclick="toggleCategory('ideas'); return false;">Ideas</a>
            </div>

            <div class="publisher-links">
                <span class="publisher-label">Publisher:</span>
                <a href="#" class="publisher-link" data-publisher="ET" onclick="togglePublisher('ET'); return false;">ET</a>
                <span class="publisher-sep">·</span>
                <a href="#" class="publisher-link" data-publisher="The Hindu" onclick="togglePublisher('The Hindu'); return false;">The Hindu</a>
                <span class="publisher-sep">·</span>
                <a href="#" class="publisher-link" data-publisher="BusinessLine" onclick="togglePublisher('BusinessLine'); return false;">BusinessLine</a>
                <span class="publisher-sep">·</span>
                <a href="#" class="publisher-link" data-publisher="BS" onclick="togglePublisher('BS'); return false;">BS</a>
                <span class="publisher-sep">·</span>
                <a href="#" class="publisher-link" data-publisher="Mint" onclick="togglePublisher('Mint'); return false;">Mint</a>
                <span class="publisher-sep">·</span>
                <a href="#" class="publisher-link" data-publisher="Global" onclick="togglePublisher('Global'); return false;">Global</a>
            </div>

            <div class="in-focus-row">
                <button class="in-focus-btn" id="in-focus-toggle" onclick="toggleInFocus()">
                    <span class="pulse-dot"></span>
                    In Focus: <strong>{in_focus_count}</strong> stories covered by multiple sources
                </button>
            </div>
        </div>

        <div id="pagination-top" class="pagination" aria-label="Pagination"></div>

        <div id="articles">
"""

    current_date = None

    for group in sorted_groups:
        article = group["primary"]
        related_sources = group["related_sources"]

        # Convert to local time for display
        local_dt = to_local_datetime(article["date"])

        # Add date header if new date
        if local_dt:
            article_date = local_dt.date()
            if article_date != current_date:
                current_date = article_date
                if article_date == today:
                    date_label = "Today"
                elif article_date == yesterday:
                    date_label = "Yesterday"
                else:
                    date_label = article_date.strftime("%A, %B %d")
                html += f'            <h2 class="date-header">{date_label}</h2>\n'

        title = escape(clean_html(article["title"]))
        link = escape(article["link"])
        source = escape(article["source"])
        source_url = escape(article["source_url"])
        description = escape(clean_html(article["description"]))
        time_str = local_dt.strftime("%I:%M %p").lstrip("0") if local_dt else ""
        article_date_iso = local_dt.date().isoformat() if local_dt else ""

        # Truncate long source names for display
        source_display = source[:35] + "..." if len(source) > 35 else source

        # Build "Also covered by" HTML and source badge if there are related sources
        also_covered_html = ""
        source_badge_html = ""
        is_in_focus = "true" if related_sources else "false"
        if related_sources:
            total_sources = len(related_sources) + 1  # +1 for the primary source
            source_badge_html = f'<span class="source-badge">{total_sources} sources</span>'
            source_links = []
            for rs in related_sources[:5]:  # Limit to 5 additional sources
                rs_name = escape(rs["name"])
                rs_link = escape(rs["link"])
                # Truncate source name for display
                rs_display = rs_name[:25] + "..." if len(rs_name) > 25 else rs_name
                source_links.append(f'<a href="{rs_link}" target="_blank" rel="noopener" title="{rs_name}">{rs_display}</a>')
            also_covered_html = f'\n                <div class="also-covered">Also covered by: {", ".join(source_links)}</div>'

        category = escape(article.get("category", "News").lower())
        publisher = escape(article.get("publisher", ""))
        html += f"""            <article class="article" data-source="{source.lower()}" data-date="{article_date_iso}" data-url="{link}" data-title="{title}" data-category="{category}" data-in-focus="{is_in_focus}" data-publisher="{publisher}">
                <h3 class="article-title"><a href="{link}" target="_blank" rel="noopener">{title}</a>{source_badge_html}</h3>
                <div class="article-meta">
                    <a href="{source_url}" target="_blank" class="source-tag" title="{source}">{source_display}</a>
                    {f'<span class="meta-dot">·</span><span class="article-time">{time_str}</span>' if time_str else ''}
                    <span class="meta-dot">·</span>
                    <button class="bookmark-btn" onclick="toggleBookmark(this)" aria-label="Bookmark article" title="Bookmark">
                        <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                    </button>
                </div>{also_covered_html}
            </article>
"""

    html += """        </div>

        <div id="pagination-bottom" class="pagination bottom" aria-label="Pagination"></div>

        <footer>
            Aggregated from {source_count} sources · Built with Python · Made by <a href="https://kashishkapoor.com/" target="_blank" rel="noopener">Kashish Kapoor</a> · Built for <a href="https://thedailybrief.zerodha.com/" target="_blank" rel="noopener">The Daily Brief by Zerodha</a>
        </footer>
    </div>

    <button class="back-to-top" onclick="window.scrollTo({top:0,behavior:'smooth'})" title="Back to top">↑</button>

    <div class="keyboard-hint">
        <kbd>J</kbd> <kbd>K</kbd> navigate · <kbd>/</kbd> search
    </div>

    <script>
        // Theme toggle (persisted)
        const safeStorage = {
            get(key) {
                try { return localStorage.getItem(key); } catch (e) { return null; }
            },
            set(key, value) {
                try { localStorage.setItem(key, value); } catch (e) { /* no-op */ }
            }
        };
        const setTheme = (theme) => {
            document.documentElement.setAttribute('data-theme', theme);
            document.body.setAttribute('data-theme', theme);
            safeStorage.set('theme', theme);
            const btn = document.getElementById('theme-toggle');
            btn.setAttribute('data-theme', theme);
            btn.setAttribute('aria-pressed', theme === 'light' ? 'false' : 'true');
        };
        function toggleTheme() {
            const current = document.documentElement.getAttribute('data-theme') || 'dark';
            setTheme(current === 'light' ? 'dark' : 'light');
        }
        const initTheme = () => {
            const saved = safeStorage.get('theme');
            const theme = saved || 'light';
            setTheme(theme);
        };
        initTheme();
        document.getElementById('theme-toggle').addEventListener('click', toggleTheme);

        // Search, category, publisher, and In Focus filter
        let currentCategory = '';
        let currentPublisher = '';
        let inFocusOnly = false;

        function filterArticles() {
            const query = document.getElementById('search').value.toLowerCase();
            const articles = document.querySelectorAll('.article');
            const dateHeaders = document.querySelectorAll('.date-header');

            articles.forEach(article => {
                const text = article.textContent.toLowerCase();
                const category = article.dataset.category || '';
                const publisher = article.dataset.publisher || '';
                const isInFocus = article.dataset.inFocus === 'true';
                const matchesSearch = !query || text.includes(query);
                const matchesCategory = !currentCategory || category === currentCategory;
                const matchesPublisher = !currentPublisher || publisher === currentPublisher;
                const matchesInFocus = !inFocusOnly || isInFocus;
                article.classList.toggle('hidden', !(matchesSearch && matchesCategory && matchesPublisher && matchesInFocus));
            });

            // Hide empty date headers
            dateHeaders.forEach(header => {
                let next = header.nextElementSibling;
                let hasVisible = false;
                while (next && !next.classList.contains('date-header')) {
                    if (next.classList.contains('article') && !next.classList.contains('hidden')) {
                        hasVisible = true;
                        break;
                    }
                    next = next.nextElementSibling;
                }
                header.classList.toggle('hidden', !hasVisible);
            });

            setPageToToday();
            applyPagination();
        }

        // Toggle category (click again to deselect)
        function toggleCategory(category) {
            if (currentCategory === category) {
                currentCategory = ''; // deselect = show all
            } else {
                currentCategory = category;
            }

            // Update active state
            document.querySelectorAll('.category-link').forEach(link => {
                link.classList.toggle('active', link.dataset.category === currentCategory);
            });

            filterArticles();
        }

        // Toggle publisher (click again to deselect)
        function togglePublisher(publisher) {
            if (currentPublisher === publisher) {
                currentPublisher = ''; // deselect = show all
            } else {
                currentPublisher = publisher;
            }

            // Update active state
            document.querySelectorAll('.publisher-link').forEach(link => {
                link.classList.toggle('active', link.dataset.publisher === currentPublisher);
            });

            filterArticles();
        }

        function toggleInFocus() {
            inFocusOnly = !inFocusOnly;
            document.getElementById('in-focus-toggle').classList.toggle('active', inFocusOnly);
            filterArticles();
        }

        // Pagination
        const PAGE_SIZE = 20;
        let currentPage = 1;
        const TODAY_ISO = "{today_iso}";

        function getFilteredArticles() {
            return [...document.querySelectorAll('.article:not(.hidden)')];
        }

        function renderPagination(totalPages) {
            const top = document.getElementById('pagination-top');
            const bottom = document.getElementById('pagination-bottom');
            top.innerHTML = '';
            bottom.innerHTML = '';

            if (totalPages <= 1) {
                return;
            }
            const makeBtn = (label, page, isActive = false, isDisabled = false) => {
                const btn = document.createElement('button');
                btn.className = 'page-btn' + (isActive ? ' active' : '');
                btn.textContent = label;
                if (isDisabled) {
                    btn.disabled = true;
                } else {
                    btn.addEventListener('click', () => {
                        currentPage = page;
                        applyPagination(true);
                    });
                }
                return btn;
            };
            const makeEllipsis = () => {
                const span = document.createElement('span');
                span.className = 'page-ellipsis';
                span.textContent = '…';
                return span;
            };
            const windowSize = 7;
            const half = Math.floor(windowSize / 2);
            let start = Math.max(1, currentPage - half);
            let end = Math.min(totalPages, currentPage + half);

            if (end - start + 1 < windowSize) {
                if (start === 1) {
                    end = Math.min(totalPages, start + windowSize - 1);
                } else if (end === totalPages) {
                    start = Math.max(1, end - windowSize + 1);
                }
            }

            const build = (container) => {
                const prevBtn = makeBtn('← Prev', Math.max(1, currentPage - 1), false, currentPage === 1);
                prevBtn.classList.add('nav', 'prev');
                container.appendChild(prevBtn);

                if (start > 1) {
                    container.appendChild(makeBtn('1', 1, currentPage === 1));
                    if (start > 2) {
                        container.appendChild(makeEllipsis());
                    }
                }

                for (let i = start; i <= end; i++) {
                    container.appendChild(makeBtn(String(i), i, i === currentPage));
                }

                if (end < totalPages) {
                    if (end < totalPages - 1) {
                        container.appendChild(makeEllipsis());
                    }
                    container.appendChild(makeBtn(String(totalPages), totalPages, currentPage === totalPages));
                }

                const nextBtn = makeBtn('Next →', Math.min(totalPages, currentPage + 1), false, currentPage === totalPages);
                nextBtn.classList.add('nav', 'next');
                container.appendChild(nextBtn);
            };

            build(top);
            build(bottom);
        }

        function applyPagination(shouldScroll = false) {
            const articles = getFilteredArticles();
            const totalPages = Math.max(1, Math.ceil(articles.length / PAGE_SIZE));
            if (currentPage > totalPages) {
                currentPage = totalPages;
            }

            // Reset pagination visibility
            document.querySelectorAll('.article').forEach(a => a.classList.remove('paged-hidden'));

            const start = (currentPage - 1) * PAGE_SIZE;
            const end = start + PAGE_SIZE;
            articles.forEach((article, idx) => {
                if (idx < start || idx >= end) {
                    article.classList.add('paged-hidden');
                }
            });

            // Hide empty date headers after paging
            const dateHeaders = document.querySelectorAll('.date-header');
            dateHeaders.forEach(header => {
                let next = header.nextElementSibling;
                let hasVisible = false;
                while (next && !next.classList.contains('date-header')) {
                    if (next.classList.contains('article') && !next.classList.contains('hidden') && !next.classList.contains('paged-hidden')) {
                        hasVisible = true;
                        break;
                    }
                    next = next.nextElementSibling;
                }
                header.classList.toggle('hidden', !hasVisible);
            });

            renderPagination(totalPages);
            if (shouldScroll) {
                window.scrollTo(0, 0);
            }
        }

        function setPageToToday() {
            const articles = getFilteredArticles();
            if (!TODAY_ISO) {
                currentPage = 1;
                return;
            }
            const idx = articles.findIndex(a => (a.dataset.date || '') === TODAY_ISO);
            if (idx >= 0) {
                currentPage = Math.floor(idx / PAGE_SIZE) + 1;
            } else {
                currentPage = 1;
            }
        }

        // Back to top button
        window.addEventListener('scroll', () => {
            const btn = document.querySelector('.back-to-top');
            btn.classList.toggle('visible', window.scrollY > 500);
        });

        // Keyboard navigation
        let currentArticle = -1;
        const getVisibleArticles = () => [...document.querySelectorAll('.article:not(.hidden):not(.paged-hidden)')];

        document.addEventListener('keydown', (e) => {
            // Don't interfere with typing in search
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') {
                if (e.key === 'Escape') {
                    e.target.blur();
                }
                return;
            }

            const articles = getVisibleArticles();

            if (e.key === 'j' || e.key === 'ArrowDown') {
                e.preventDefault();
                currentArticle = Math.min(currentArticle + 1, articles.length - 1);
                articles[currentArticle]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                articles[currentArticle]?.querySelector('a')?.focus();
            } else if (e.key === 'k' || e.key === 'ArrowUp') {
                e.preventDefault();
                currentArticle = Math.max(currentArticle - 1, 0);
                articles[currentArticle]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                articles[currentArticle]?.querySelector('a')?.focus();
            } else if (e.key === '/') {
                e.preventDefault();
                document.getElementById('search').focus();
            } else if (e.key === 'Escape') {
                document.getElementById('search').value = '';
                document.getElementById('source-filter').value = '';
                filterArticles();
            }
        });

        // Initial pagination
        setPageToToday();
        applyPagination();

        // ==================== BOOKMARKS ====================
        const BOOKMARKS_KEY = 'financeradar_bookmarks';

        function getBookmarks() {
            try {
                const data = localStorage.getItem(BOOKMARKS_KEY);
                return data ? JSON.parse(data) : [];
            } catch (e) {
                return [];
            }
        }

        function saveBookmarks(bookmarks) {
            try {
                localStorage.setItem(BOOKMARKS_KEY, JSON.stringify(bookmarks));
            } catch (e) { /* no-op */ }
        }

        function isBookmarked(url) {
            return getBookmarks().some(b => b.url === url);
        }

        function toggleBookmark(btn) {
            const article = btn.closest('.article');
            const url = article.dataset.url;
            const title = article.dataset.title;
            const source = article.querySelector('.source-tag')?.textContent || '';

            let bookmarks = getBookmarks();
            const idx = bookmarks.findIndex(b => b.url === url);

            if (idx >= 0) {
                bookmarks.splice(idx, 1);
                btn.classList.remove('bookmarked');
            } else {
                bookmarks.unshift({ url, title, source, addedAt: Date.now() });
                btn.classList.add('bookmarked');
            }

            saveBookmarks(bookmarks);
            updateBookmarkCount();
            renderSidebarContent();
        }

        function updateBookmarkCount() {
            const count = getBookmarks().length;
            const badge = document.getElementById('bookmark-count');
            const toggle = document.getElementById('bookmarks-toggle');

            badge.textContent = count;
            badge.classList.toggle('hidden', count === 0);
            toggle.classList.toggle('has-bookmarks', count > 0);
        }

        function initBookmarkButtons() {
            document.querySelectorAll('.article').forEach(article => {
                const url = article.dataset.url;
                const btn = article.querySelector('.bookmark-btn');
                if (btn && isBookmarked(url)) {
                    btn.classList.add('bookmarked');
                }
            });
            updateBookmarkCount();
        }

        function openSidebar() {
            document.getElementById('sidebar-overlay').classList.add('open');
            document.body.style.overflow = 'hidden';
            renderSidebarContent();
        }

        function closeSidebar() {
            document.getElementById('sidebar-overlay').classList.remove('open');
            document.body.style.overflow = '';
        }

        function renderSidebarContent() {
            const container = document.getElementById('sidebar-content');
            const bookmarks = getBookmarks();

            if (bookmarks.length === 0) {
                container.innerHTML = '<div class="sidebar-empty">No bookmarks yet.<br>Click the bookmark icon on articles to save them.</div>';
                return;
            }

            container.innerHTML = bookmarks.map(b => `
                <div class="sidebar-article" data-url="${escapeHtml(b.url)}">
                    <div class="sidebar-article-title">
                        <a href="${escapeHtml(b.url)}" target="_blank" rel="noopener">${escapeHtml(b.title)}</a>
                    </div>
                    <div class="sidebar-article-meta">
                        <span class="sidebar-article-source">${escapeHtml(b.source)}</span>
                        <button class="sidebar-remove" onclick="removeBookmark('${escapeForAttr(b.url)}')" title="Remove bookmark">✕</button>
                    </div>
                </div>
            `).join('');
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text || '';
            return div.innerHTML;
        }

        function escapeForAttr(text) {
            return escapeHtml(text).replace(/'/g, '&#39;');
        }

        function removeBookmark(url) {
            let bookmarks = getBookmarks();
            bookmarks = bookmarks.filter(b => b.url !== url);
            saveBookmarks(bookmarks);

            // Update main list button
            const article = document.querySelector(`.article[data-url="${CSS.escape(url)}"]`);
            if (article) {
                const btn = article.querySelector('.bookmark-btn');
                if (btn) btn.classList.remove('bookmarked');
            }

            updateBookmarkCount();
            renderSidebarContent();
        }

        function copyBookmarks() {
            const bookmarks = getBookmarks();
            if (bookmarks.length === 0) {
                return;
            }

            const text = bookmarks.map(b => b.title + '\\n' + b.url).join('\\n\\n');

            navigator.clipboard.writeText(text).then(() => {
                const btn = document.querySelector('.copy-btn');
                const span = btn.querySelector('span');
                const originalText = span.textContent;

                btn.classList.add('copied');
                span.textContent = 'Copied!';

                setTimeout(() => {
                    btn.classList.remove('copied');
                    span.textContent = originalText;
                }, 2000);
            }).catch(() => {
                // Fallback for older browsers
                const textarea = document.createElement('textarea');
                textarea.value = text;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
            });
        }

        function clearAllBookmarks() {
            if (!confirm('Are you sure you want to clear all bookmarks?')) return;
            saveBookmarks([]);
            document.querySelectorAll('.bookmark-btn.bookmarked').forEach(btn => {
                btn.classList.remove('bookmarked');
            });
            updateBookmarkCount();
            renderSidebarContent();
        }

        // Sidebar toggle
        document.getElementById('bookmarks-toggle').addEventListener('click', openSidebar);
        document.getElementById('sidebar-overlay').addEventListener('click', (e) => {
            if (e.target.id === 'sidebar-overlay') closeSidebar();
        });

        // Close sidebar with Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && document.getElementById('sidebar-overlay').classList.contains('open')) {
                closeSidebar();
            }
        });

        // Initialize bookmarks
        initBookmarkButtons();

        // ==================== AI RANKINGS SIDEBAR ====================
        let aiRankings = null;
        let currentAiProvider = 'nemotron';

        async function loadAiRankings() {
            try {
                const res = await fetch('static/ai_rankings.json');
                if (!res.ok) throw new Error('Rankings not found');
                aiRankings = await res.json();
                populateProviderDropdown();
                renderAiRankings();
            } catch (e) {
                document.getElementById('ai-rankings-content').innerHTML =
                    '<div class="ai-error"><div class="ai-error-title">AI Rankings Unavailable</div><div>Run ai_ranker.py to generate rankings</div></div>';
            }
        }

        function populateProviderDropdown() {
            const select = document.getElementById('ai-provider');
            select.innerHTML = '';
            if (!aiRankings || !aiRankings.providers) return;
            const providers = Object.entries(aiRankings.providers);
            providers.forEach(([key, p]) => {
                const opt = document.createElement('option');
                opt.value = key;
                opt.textContent = p.name + (p.status !== 'ok' ? ' (unavailable)' : '');
                if (key === currentAiProvider) opt.selected = true;
                select.appendChild(opt);
            });
            // If current provider not in list, select first available
            if (!aiRankings.providers[currentAiProvider]) {
                const firstOk = providers.find(([k, p]) => p.status === 'ok');
                if (firstOk) {
                    currentAiProvider = firstOk[0];
                    select.value = currentAiProvider;
                }
            }
        }

        function switchAiProvider() {
            currentAiProvider = document.getElementById('ai-provider').value;
            renderAiRankings();
        }

        function renderAiRankings() {
            if (!aiRankings || !aiRankings.providers) return;
            const provider = aiRankings.providers[currentAiProvider];
            const container = document.getElementById('ai-rankings-content');
            if (!provider) {
                container.innerHTML = '<div class="ai-error">Provider not available</div>';
                return;
            }
            if (provider.status !== 'ok') {
                container.innerHTML = `<div class="ai-error"><div class="ai-error-title">AI Rankings Temporarily Unavailable</div><div style="margin-top:8px;font-size:12px;color:var(--text-muted)">Rankings will refresh on next scheduled run.</div></div>`;
                return;
            }
            container.innerHTML = provider.rankings.map((r, i) => `
                <div class="ai-rank-item">
                    <span class="rank-num">${i + 1}</span>
                    <div class="rank-content">
                        <a href="${escapeHtml(r.url || '#')}" target="_blank" rel="noopener">${escapeHtml(r.title)}</a>
                        <span class="rank-source">${escapeHtml(r.source)}</span>
                    </div>
                    <button class="ai-bookmark-btn ${isBookmarked(r.url) ? 'bookmarked' : ''}"
                            data-url="${escapeForAttr(r.url)}" data-title="${escapeForAttr(r.title)}" data-source="${escapeForAttr(r.source)}" title="Bookmark">
                        <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                    </button>
                </div>
            `).join('');
            const date = new Date(aiRankings.generated_at);
            document.getElementById('ai-updated').textContent = `Updated: ${date.toLocaleDateString()} ${date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}`;
        }

        function isBookmarked(url) {
            if (!url) return false;
            return getBookmarks().some(b => b.url === url);
        }

        function toggleAiBookmark(btn, url, title, source) {
            if (!url) return;
            let bookmarks = getBookmarks();
            const exists = bookmarks.some(b => b.url === url);
            if (exists) {
                bookmarks = bookmarks.filter(b => b.url !== url);
                btn.classList.remove('bookmarked');
            } else {
                bookmarks.push({ url, title, source, date: new Date().toISOString() });
                btn.classList.add('bookmarked');
            }
            saveBookmarks(bookmarks);
            updateBookmarkCount();
            const article = document.querySelector(`.article[data-url="${CSS.escape(url)}"]`);
            if (article) {
                const mainBtn = article.querySelector('.bookmark-btn');
                if (mainBtn) mainBtn.classList.toggle('bookmarked', !exists);
            }
        }

        function openAiSidebar() {
            document.getElementById('ai-sidebar-overlay').classList.add('open');
            document.body.style.overflow = 'hidden';
        }

        function closeAiSidebar() {
            document.getElementById('ai-sidebar-overlay').classList.remove('open');
            document.body.style.overflow = '';
        }

        document.getElementById('ai-sidebar-overlay').addEventListener('click', (e) => {
            if (e.target.id === 'ai-sidebar-overlay') closeAiSidebar();
        });

        // Event delegation for AI sidebar bookmark buttons (mobile fix)
        document.getElementById('ai-rankings-content').addEventListener('click', (e) => {
            const btn = e.target.closest('.ai-bookmark-btn');
            if (btn) {
                e.preventDefault();
                e.stopPropagation();
                const url = btn.getAttribute('data-url');
                const title = btn.getAttribute('data-title');
                const source = btn.getAttribute('data-source');
                if (url) toggleAiBookmark(btn, url, title, source);
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && document.getElementById('ai-sidebar-overlay').classList.contains('open')) {
                closeAiSidebar();
            }
        });

        loadAiRankings();

        // Update relative time
        function updateRelativeTime() {
            const el = document.getElementById('update-time');
            if (!el) return;
            const time = new Date(el.dataset.time);
            const now = new Date();
            const diff = Math.floor((now - time) / 1000);
            let text;
            if (diff < 60) text = 'Updated just now';
            else if (diff < 3600) text = `Updated ${Math.floor(diff / 60)} min ago`;
            else if (diff < 86400) text = `Updated ${Math.floor(diff / 3600)} hr ago`;
            else text = `Updated ${Math.floor(diff / 86400)} day ago`;
            el.textContent = text;
        }
        updateRelativeTime();
        setInterval(updateRelativeTime, 60000);

        // Ensure page starts at top on load
        window.addEventListener('load', () => {
            window.scrollTo(0, 0);
        });
    </script>
</body>
</html>
""".replace("{source_count}", str(len(sources))).replace("{in_focus_count}", str(in_focus_count))

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\nGenerated: {OUTPUT_FILE}")
        print(f"Total articles: {len(sorted_articles)}")
    except IOError as e:
        print(f"\nERROR: Could not write to {OUTPUT_FILE}: {e}")


def main():
    print("=" * 50)
    print("RSS News Aggregator")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    feeds = load_feeds()
    if not feeds:
        print("\nNo feeds to fetch. Check your feeds.json file.")
        return

    print(f"\nFetching {len(feeds)} feeds...\n")

    all_articles = []

    # Fetch feeds in parallel (10 at a time)
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_feed, feed): feed for feed in feeds}

        for future in as_completed(futures):
            articles = future.result()
            all_articles.extend(articles)

    print(f"\nTotal articles collected: {len(all_articles)}")

    # Remove duplicates based on URL only (not title - to preserve source diversity)
    seen_urls = set()
    unique_articles = []

    for article in all_articles:
        # Skip articles with no URL
        if not article["link"] or not article["link"].strip():
            continue

        # Normalize URL for comparison
        url = article["link"].lower().strip().rstrip('/')
        url = url.replace('http://', 'https://')

        # Skip if we've seen this exact URL before (within this run)
        if url in seen_urls:
            continue

        seen_urls.add(url)
        unique_articles.append(article)

    print(f"After removing duplicates: {len(unique_articles)}")

    # Apply content filters to remove irrelevant/routine articles
    filtered_articles = []
    filtered_count = 0

    for article in unique_articles:
        if should_filter_article(article):
            filtered_count += 1
        else:
            filtered_articles.append(article)

    print(f"After content filtering: {len(filtered_articles)} ({filtered_count} filtered out)")

    # Filter out articles older than 10 days
    now = datetime.now(IST_TZ)
    cutoff_date = now - timedelta(days=10)
    recent_articles = []
    old_count = 0

    for article in filtered_articles:
        article_date = article.get("date")
        if article_date is None:
            # Keep articles without dates (will be sorted to end)
            recent_articles.append(article)
        else:
            # Ensure timezone-aware comparison
            if article_date.tzinfo is None:
                article_date = article_date.replace(tzinfo=IST_TZ)
            if article_date >= cutoff_date:
                recent_articles.append(article)
            else:
                old_count += 1

    filtered_articles = recent_articles
    print(f"After removing old articles (>10 days): {len(filtered_articles)} ({old_count} removed)")

    # Group similar articles by headline
    article_groups = group_similar_articles(filtered_articles)
    grouped_count = len(filtered_articles) - len(article_groups)
    print(f"After grouping similar headlines: {len(article_groups)} groups ({grouped_count} articles merged)")

    generate_html(article_groups)
    export_articles_json(article_groups)

    print("\nDone!")
    print("=" * 50)


if __name__ == "__main__":
    main()
