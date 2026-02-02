#!/usr/bin/env python3
"""
RSS News Aggregator
Fetches news from multiple RSS feeds and generates a static HTML website.
"""

import json
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from html import escape, unescape
import re
import ssl
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# Get script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FEEDS_FILE = os.path.join(SCRIPT_DIR, "feeds.json")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "index.html")

# Create SSL context that doesn't verify certificates (some feeds have issues)
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

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


def parse_date(date_str):
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
    ]

    # Clean up common timezone issues
    date_str = date_str.strip()
    date_str = re.sub(r'\s+', ' ', date_str)
    date_str = date_str.replace("GMT", "+0000").replace("UTC", "+0000")
    date_str = date_str.replace("IST", "+0530").replace("EDT", "-0400").replace("EST", "-0500")

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
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
        req = urllib.request.Request(
            feed_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

        with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as response:
            content = response.read()

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
                    "date": parse_date(pub_date.text if pub_date is not None else ""),
                    "description": summary.text[:300] if summary is not None and summary.text else "",
                    "source": feed_name,
                    "source_url": source_url
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
                    "date": parse_date(pub_date.text if pub_date is not None else ""),
                    "description": description.text[:300] if description is not None and description.text else "",
                    "source": feed_name,
                    "source_url": source_url
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
    """Convert a datetime to local time for display."""
    if dt is None:
        return None

    try:
        # Convert to local datetime via timestamp
        return datetime.fromtimestamp(dt.timestamp())
    except (OSError, OverflowError, ValueError):
        return dt


def generate_html(articles):
    """Generate the static HTML website."""

    # Sort by date (newest first), put articles without dates at the end
    articles_with_date = [a for a in articles if a["date"]]
    articles_without_date = [a for a in articles if not a["date"]]

    # Sort using timestamps to handle timezone differences correctly
    articles_with_date.sort(key=get_sort_timestamp, reverse=True)
    all_sorted = articles_with_date + articles_without_date

    # Apply per-feed cap (max 50 articles per feed)
    MAX_PER_FEED = 50
    source_counts = {}
    capped_articles = []

    for article in all_sorted:
        source = article["source"]
        count = source_counts.get(source, 0)
        if count < MAX_PER_FEED:
            capped_articles.append(article)
            source_counts[source] = count + 1

    # Re-sort after capping to ensure proper chronological order for date headers
    capped_articles.sort(key=get_sort_timestamp, reverse=True)
    sorted_articles = capped_articles

    # Group by date
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    today_iso = today.isoformat()

    # Get unique sources for filter dropdown
    sources = sorted(set(a['source'] for a in sorted_articles))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>News Feed</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&display=swap');
        :root {{
            --bg-primary: #ffffff;
            --bg-secondary: #ffffff;
            --bg-hover: #faf7f5;
            --text-primary: #1f1f1f;
            --text-secondary: #4b4b4b;
            --text-muted: #7a7a7a;
            --accent: #e14b4b;
            --accent-hover: #c73b3b;
            --border: #e7e7e7;
            --border-light: #e0e0e0;
            --card-shadow: none;
        }}
        [data-theme="light"] {{
            --bg-primary: #ffffff;
            --bg-secondary: #ffffff;
            --bg-hover: #faf7f5;
            --text-primary: #1f1f1f;
            --text-secondary: #4b4b4b;
            --text-muted: #7a7a7a;
            --accent: #e14b4b;
            --accent-hover: #c73b3b;
            --border: #e7e7e7;
            --border-light: #e0e0e0;
            --card-shadow: none;
        }}
        [data-theme="dark"] {{
            --bg-primary: #0f0f0f;
            --bg-secondary: #141414;
            --bg-hover: #1b1b1b;
            --text-primary: #e8e8e8;
            --text-secondary: #bdbdbd;
            --text-muted: #9a9a9a;
            --accent: #e14b4b;
            --accent-hover: #ff6b6b;
            --border: #262626;
            --border-light: #2f2f2f;
            --card-shadow: none;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        html {{
            scroll-behavior: smooth;
        }}

        body {{
            font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            font-size: 15px;
        }}

        /* Sticky Header */
        .top-bar {{
            position: sticky;
            top: 0;
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border);
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
            font-weight: 600;
            font-size: 1.05em;
            color: var(--text-primary);
            padding-bottom: 2px;
            border-bottom: 2px solid var(--accent);
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
            border-radius: 6px;
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

        #source-filter {{
            height: 36px;
            padding: 0 12px;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text-primary);
            font-size: 14px;
            cursor: pointer;
            min-width: 150px;
        }}

        #source-filter:focus {{
            outline: none;
            border-color: var(--accent);
        }}
        .theme-toggle {{
            padding: 0;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 6px;
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
            max-width: 860px;
            margin: 0 auto;
            padding: 16px;
        }}

        /* Stats Bar */
        .stats-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 0;
            margin-bottom: 8px;
            border-bottom: 1px solid var(--border);
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

        .update-time {{
            font-size: 13px;
            color: var(--text-muted);
        }}

        /* Pagination */
        .pagination {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            padding: 12px 0 4px 0;
            border-bottom: 1px solid var(--border);
            width: 100%;
        }}
        .pagination.bottom {{
            border-top: 1px solid var(--border);
            border-bottom: none;
            margin-top: 20px;
            padding: 12px 0 0 0;
        }}
        .page-btn {{
            padding: 6px 10px;
            border: 1px solid var(--border);
            background: var(--bg-secondary);
            color: var(--text-secondary);
            font-size: 13px;
            border-radius: 6px;
            cursor: pointer;
        }}
        .page-btn.active {{
            border-color: var(--accent);
            color: var(--text-primary);
        }}
        .page-btn:hover {{
            border-color: var(--border-light);
            background: var(--bg-hover);
        }}
        .page-ellipsis {{
            padding: 6px 8px;
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
            font-size: 13px;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid var(--border);
            z-index: 50;
        }}

        .date-header:first-child {{
            margin-top: 0;
        }}

        /* Article List */
        .article {{
            padding: 14px 0;
            border-bottom: 1px solid var(--border);
        }}
        .article:hover {{
            background: var(--bg-hover);
        }}

        .article-title {{
            font-size: 16px;
            font-weight: 600;
            line-height: 1.4;
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
            font-size: 14px;
            color: var(--text-secondary);
            line-height: 1.5;
        }}

        /* Footer */
        footer {{
            margin-top: 40px;
            padding: 24px 0;
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

        /* Back to Top */
        .back-to-top {{
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 40px;
            height: 40px;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
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
            border-radius: 6px;
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

            .article:hover {{
                transform: none;
                box-shadow: none;
            }}

            .keyboard-hint {{
                display: none;
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
            <select id="source-filter" onchange="filterBySource()">
                <option value="">All Sources ({len(sources)})</option>
                {"".join(f'<option value="{escape(s.lower())}">{escape(s[:40])}</option>' for s in sources)}
            </select>
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

    <div class="container">
        <div class="stats-bar">
            <div class="stats">
                <span><strong>{len(sorted_articles)}</strong> articles</span>
                <span><strong>{len(sources)}</strong> sources</span>
            </div>
            <div class="update-time">Updated {datetime.now().strftime("%b %d, %I:%M %p")}</div>
        </div>

        <div id="pagination-top" class="pagination" aria-label="Pagination"></div>

        <div id="articles">
"""

    current_date = None

    for article in sorted_articles:
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

        html += f"""            <article class="article" data-source="{source.lower()}" data-date="{article_date_iso}">
                <h3 class="article-title"><a href="{link}" target="_blank" rel="noopener">{title}</a></h3>
                <div class="article-meta">
                    <a href="{source_url}" target="_blank" class="source-tag" title="{source}">{source_display}</a>
                    {f'<span class="meta-dot">·</span><span class="article-time">{time_str}</span>' if time_str else ''}
                </div>
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

        // Search filter
        function filterArticles() {
            const query = document.getElementById('search').value.toLowerCase();
            const sourceFilter = document.getElementById('source-filter').value.toLowerCase();
            const articles = document.querySelectorAll('.article');
            const dateHeaders = document.querySelectorAll('.date-header');

            articles.forEach(article => {
                const text = article.textContent.toLowerCase();
                const source = article.dataset.source || '';
                const matchesSearch = !query || text.includes(query);
                const matchesSource = !sourceFilter || source.includes(sourceFilter);
                article.classList.toggle('hidden', !(matchesSearch && matchesSource));
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

        function filterBySource() {
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
                        applyPagination();
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
                container.appendChild(makeBtn('Prev', Math.max(1, currentPage - 1), false, currentPage === 1));

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

                container.appendChild(makeBtn('Next', Math.min(totalPages, currentPage + 1), false, currentPage === totalPages));
            };

            build(top);
            build(bottom);
        }

        function applyPagination() {
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
            document.getElementById('articles').scrollIntoView({ behavior: 'smooth', block: 'start' });
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
    </script>
</body>
</html>
""".replace("{source_count}", str(len(sources)))

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

    generate_html(filtered_articles)

    print("\nDone!")
    print("=" * 50)


if __name__ == "__main__":
    main()
