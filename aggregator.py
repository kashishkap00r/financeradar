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
import sys
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

# Filters extracted to filters.py for independent editing and testing
from filters import should_filter_article



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
            except (AttributeError, ValueError, TypeError):
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
                if date_str.endswith('Z') or date_str.endswith('z'):
                    dt = dt.replace(tzinfo=timezone.utc)
                elif source_name and "RBI" in source_name:
                    dt = dt.replace(tzinfo=IST_TZ)
            return dt
        except ValueError:
            continue

    if date_str:
        print(f"  [WARN] Unparseable date ({source_name}): {date_str[:60]}")
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

                article_data = {
                    "title": title.text if title is not None and title.text else "No title",
                    "link": link_href,
                    "date": parse_date(pub_date.text if pub_date is not None else "", feed_name),
                    "description": summary.text[:300] if summary is not None and summary.text else "",
                    "source": feed_name,
                    "source_url": source_url,
                    "category": feed_config.get("category", "News"),
                    "publisher": feed_config.get("publisher", "")
                }

                # YouTube-specific: extract video ID and thumbnail
                yt_vid = item.find("{http://www.youtube.com/xml/schemas/2015}videoId")
                if yt_vid is not None and yt_vid.text:
                    article_data["video_id"] = yt_vid.text
                    media_group = item.find("{http://search.yahoo.com/mrss/}group")
                    thumb = ""
                    if media_group is not None:
                        thumb_el = media_group.find("{http://search.yahoo.com/mrss/}thumbnail")
                        if thumb_el is not None:
                            thumb = thumb_el.get("url", "")
                    article_data["thumbnail"] = thumb or f"https://i.ytimg.com/vi/{yt_vid.text}/mqdefault.jpg"

                articles.append(article_data)
        else:
            # RSS 2.0 format
            MEDIA_NS = "{http://search.yahoo.com/mrss/}"
            for item in items:
                title = item.find("title")
                link = item.find("link")
                pub_date = item.find("pubDate")
                description = item.find("description")

                # Extract image from media:thumbnail, media:content, or enclosure
                image_url = ""
                thumb = item.find(f"{MEDIA_NS}thumbnail")
                if thumb is not None:
                    image_url = thumb.get("url", "")
                if not image_url:
                    content = item.find(f"{MEDIA_NS}content")
                    if content is not None and content.get("medium", "") == "image":
                        image_url = content.get("url", "")
                if not image_url:
                    enclosure = item.find("enclosure")
                    if enclosure is not None and enclosure.get("type", "").startswith("image/"):
                        image_url = enclosure.get("url", "")

                articles.append({
                    "title": title.text if title is not None and title.text else "No title",
                    "link": link.text if link is not None and link.text else "",
                    "date": parse_date(pub_date.text if pub_date is not None else "", feed_name),
                    "description": description.text[:300] if description is not None and description.text else "",
                    "source": feed_name,
                    "source_url": source_url,
                    "category": feed_config.get("category", "News"),
                    "publisher": feed_config.get("publisher", ""),
                    "image": image_url
                })

        print(f"  [OK] {feed_name}: {len(articles)} articles")

    except Exception as e:
        print(f"  [FAIL] {feed_name}: {str(e)[:50]}")

    return articles


def fetch_careratings(feed_config):
    """Fetch articles from CareRatings industry research JSON API."""
    feed_name = feed_config["name"]
    source_url = feed_config["url"]
    articles = []

    try:
        page_id = int(feed_config["feed"].split(":")[1])
        section_id = 5037 if page_id == 23 else 5034
        year = datetime.now().year
        api_url = f"https://www.careratings.com/insightspagedata?PageId={page_id}&SectionId={section_id}&YearID={year}&MonthID=0"

        req = urllib.request.Request(api_url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json"
        })
        with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as response:
            data = json.loads(response.read())

        for item in data.get("data", []):
            title = item.get("Title", "").strip()
            pdf = item.get("PDf", "")
            if not title or not pdf:
                continue
            link = f"https://www.careratings.com/uploads/newsfiles/{pdf}"

            pub_date = None
            date_str = item.get("Date") or item.get("Aborad_Date") or ""
            if date_str:
                try:
                    pub_date = datetime.strptime(date_str, "%d-%m-%Y").replace(tzinfo=IST_TZ)
                except ValueError:
                    pass

            desc = item.get("Description") or ""
            desc = re.sub(r'<[^>]+>', '', desc).strip()
            if len(desc) > 300:
                desc = desc[:300] + "..."

            articles.append({
                "title": title,
                "link": link,
                "date": pub_date,
                "description": desc,
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


def clean_twitter_title(title):
    """Strip RSS cruft from Twitter/X titles."""
    if not title:
        return title
    suffixes = [' - x.com', ' - Results on X | Live Posts & Updates']
    for suffix in suffixes:
        if title.endswith(suffix):
            title = title[:-len(suffix)]
    return title.strip()


def generate_html(article_groups, video_articles=None, twitter_articles=None):
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

    # Get unique publishers for multi-select dropdown
    all_publishers = sorted(set(a['publisher'] for a in sorted_articles if a.get('publisher')))

    # Publisher presets
    publisher_presets = {
        "India Desk": ["ET", "The Hindu", "BusinessLine", "Business Standard", "Mint", "ThePrint", "Firstpost", "Indian Express", "The Core", "Financial Express", "CareEdge"],
        "World Desk": ["BBC", "CNBC", "The Economist", "The Guardian", "Financial Times", "Reuters", "Bloomberg", "Rest of World", "Techmeme"],
        "Indie Voices": ["Finshots", "Filter Coffee", "SOIC", "The Ken", "The Morning Context", "India Dispatch", "Carbon Brief", "Our World in Data", "Data For India", "Down To Earth", "The LEAP Blog", "By the Numbers", "Musings on Markets", "A Wealth of Common Sense", "BS Number Wise", "AlphaEcon", "Market Bites", "Capital Quill", "This Week In Data", "Noah Smith"],
        "Official Channels": ["RBI", "SEBI", "ECB", "ADB", "FRED", "PIB"]
    }

    # Twitter publisher presets
    twitter_presets = {
        "Money Managers": ["Deepak Shenoy", "Samit Vartak", "ContrariianEPS", "Unseen Value", "Murali Srinivasan", "Dhirendra Kumar"],
        "Stock Pickers": ["SOIC", "SOIC Research", "Finstor", "Yatin Mota", "TarH", "Aditya Kondawar", "Abhy Murarka", "Prashant Nair", "Shashank Udupa", "Ritu Singh", "Equity Value", "Beat The Street", "Equity Insights", "Mohit Ish", "Kobeissi Letter", "Pranay Kotas"],
        "Newsroom": ["Menaka Doshi", "CNBC-TV18", "ET Markets", "Nigel D'Souza", "Andy Mukherjee", "Ira Dugal", "Javier Blas", "FT Energy"],
        "Macro & Policy": ["Michael Pettis", "Sanjeev Sanyal", "Ila Patnaik", "Ideas For India", "Shruti Rajagopalan", "CareEdge"],
        "Data & Climate": ["Down To Earth", "Carbon Brief", "Ember Energy", "Our World in Data", "Data For India", "IndiaSpend", "India Data Hub"],
    }
    twitter_presets_json = json.dumps(twitter_presets)

    # JSON for injection into script
    all_publishers_json = json.dumps(all_publishers)
    publisher_presets_json = json.dumps(publisher_presets)

    # Load Telegram reports if available
    telegram_reports_file = os.path.join(SCRIPT_DIR, "static", "telegram_reports.json")
    try:
        with open(telegram_reports_file, "r", encoding="utf-8") as f:
            telegram_data = json.load(f)
        telegram_reports_json = json.dumps(telegram_data.get("reports", []))
        telegram_generated_at = telegram_data.get("generated_at", "")
        telegram_warnings = telegram_data.get("warnings", [])
    except (IOError, json.JSONDecodeError):
        telegram_data = {}
        telegram_reports_json = "[]"
        telegram_generated_at = ""
        telegram_warnings = []

    # Prepare video data
    if video_articles is None:
        video_articles = []
    video_articles_json = json.dumps([{
        "title": v["title"],
        "link": v["link"],
        "date": v["date"].isoformat() if v.get("date") else None,
        "source": v.get("source", ""),
        "publisher": v.get("publisher", ""),
        "video_id": v.get("video_id", ""),
        "thumbnail": v.get("thumbnail", ""),
    } for v in video_articles])
    video_count = len(video_articles)
    video_channel_count = len(set(v.get("publisher", "") for v in video_articles if v.get("publisher")))
    youtube_publishers = sorted(set(v.get("publisher", v.get("source", "")) for v in video_articles if v.get("publisher") or v.get("source")))
    youtube_publishers_json = json.dumps(youtube_publishers)

    # Prepare twitter data
    if twitter_articles is None:
        twitter_articles = []
    twitter_articles_json = json.dumps([{
        "title": clean_twitter_title(t["title"]),
        "link": t["link"],
        "date": t["date"].isoformat() if t.get("date") else None,
        "source": t.get("source", ""),
        "publisher": t.get("publisher", ""),
    } for t in twitter_articles])
    twitter_count = len(twitter_articles)
    twitter_publishers = sorted(set(t.get("publisher", t.get("source", "")) for t in twitter_articles if t.get("publisher") or t.get("source")))
    twitter_publishers_json = json.dumps(twitter_publishers)

    # Count in-focus articles (covered by multiple sources)
    in_focus_count = sum(1 for g in sorted_groups if g["related_sources"])

    # Telegram reports stats for tabs
    telegram_reports_list = telegram_data.get("reports", [])
    report_count = len(telegram_reports_list)
    channel_count = len(set(r.get("channel", "") for r in telegram_reports_list))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <script>try{{document.documentElement.setAttribute('data-theme',localStorage.getItem('theme')||'light')}}catch(e){{}}</script>
    <script>try{{if(localStorage.getItem('financeradar_filters_collapsed')!=='false')document.documentElement.classList.add('filters-collapsed')}}catch(e){{}}</script>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FinanceRadar</title>
    <link rel="icon" href="static/favicon.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700;900&family=Source+Sans+Pro:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body {{ opacity: 0; }}
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

        /* Filter Row (presets + dropdown on one line) */
        .filter-row {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 0;
            flex-wrap: wrap;
        }}
        .filter-toggle {{
            display: none;
            background: none;
            border: none;
            padding: 2px;
            cursor: pointer;
            color: var(--text-muted);
            transition: color 0.15s;
            margin-left: 8px;
            flex-shrink: 0;
        }}
        .filter-toggle:hover {{ color: var(--text-secondary); }}
        .filter-toggle svg {{
            width: 14px;
            height: 14px;
            transition: transform 0.2s ease;
            display: block;
        }}
        html.filters-collapsed .filter-toggle svg {{ transform: rotate(-90deg); }}
        .preset-btn {{
            font-family: inherit;
            font-size: 13px;
            font-weight: 500;
            padding: 5px 14px;
            border-radius: 20px;
            border: 1.5px solid var(--border);
            background: transparent;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.15s;
            white-space: nowrap;
        }}
        .preset-btn:hover {{
            border-color: var(--accent);
            color: var(--accent);
        }}
        .preset-btn.active {{
            background: var(--accent);
            border-color: var(--accent);
            color: #fff;
        }}
        .preset-btn.partial {{
            background: transparent;
            border-color: var(--accent);
            color: var(--accent);
        }}

        /* Publisher Dropdown */
        .publisher-dropdown {{
            position: relative;
            margin-left: auto;
        }}
        .publisher-dropdown-trigger {{
            font-family: inherit;
            font-size: 13px;
            font-weight: 500;
            padding: 5px 14px;
            border-radius: 20px;
            border: 1.5px solid var(--border);
            background: transparent;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.15s;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .publisher-dropdown-trigger:hover {{
            border-color: var(--accent);
            color: var(--accent);
        }}
        .publisher-dropdown-trigger.has-selection {{
            border-color: var(--accent);
            color: var(--accent);
        }}
        .dropdown-arrow {{
            font-size: 10px;
            transition: transform 0.15s;
        }}
        .publisher-dropdown.open .dropdown-arrow {{
            transform: rotate(180deg);
        }}
        .publisher-dropdown-panel {{
            display: none;
            position: absolute;
            top: calc(100% + 4px);
            right: 0;
            z-index: 100;
            min-width: 260px;
            max-width: 320px;
            background: var(--bg-primary);
            border: 1px solid var(--border);
            border-radius: 12px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.12);
            overflow: hidden;
        }}
        .publisher-dropdown.open .publisher-dropdown-panel {{
            display: block;
        }}
        .dropdown-search {{
            width: 100%;
            padding: 10px 14px;
            border: none;
            border-bottom: 1px solid var(--border);
            background: var(--bg-primary);
            color: var(--text-primary);
            font-family: inherit;
            font-size: 13px;
            outline: none;
            box-sizing: border-box;
        }}
        .dropdown-search::placeholder {{
            color: var(--text-muted);
        }}
        .dropdown-actions {{
            display: flex;
            gap: 12px;
            padding: 8px 14px;
            border-bottom: 1px solid var(--border);
            font-size: 12px;
        }}
        .dropdown-action {{
            color: var(--accent);
            cursor: pointer;
            background: none;
            border: none;
            font-family: inherit;
            font-size: 12px;
            padding: 0;
        }}
        .dropdown-action:hover {{
            text-decoration: underline;
        }}
        .dropdown-list {{
            max-height: 280px;
            overflow-y: auto;
            padding: 4px 0;
        }}
        .dropdown-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 14px;
            cursor: pointer;
            font-size: 13px;
            color: var(--text-primary);
            transition: background 0.1s;
        }}
        .dropdown-item:hover {{
            background: var(--bg-hover);
        }}
        .dropdown-item.hidden {{
            display: none;
        }}
        .dropdown-item input[type="checkbox"] {{
            accent-color: var(--accent);
            cursor: pointer;
            width: 15px;
            height: 15px;
            flex-shrink: 0;
        }}
        .dropdown-item label {{
            cursor: pointer;
            flex: 1;
            user-select: none;
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

        /* Tweet feed layout */
        .tweet-item {{
            display: flex;
            gap: 12px;
            padding: 14px 0;
            border-bottom: 1px solid var(--border);
        }}
        .tweet-item:last-of-type {{
            border-bottom: none;
        }}
        .tweet-avatar {{
            width: 38px;
            height: 38px;
            min-width: 38px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            font-weight: 700;
            font-size: 15px;
            margin-top: 2px;
        }}
        .tweet-content {{
            flex: 1;
            min-width: 0;
        }}
        .tweet-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 4px;
            flex-wrap: wrap;
        }}
        .tweet-publisher {{
            font-weight: 700;
            font-size: 14px;
            color: var(--text-primary);
        }}
        .tweet-time {{
            font-size: 13px;
            color: var(--text-muted);
        }}
        .tweet-header .bookmark-btn {{
            margin-left: auto;
        }}
        .tweet-text {{
            font-family: 'Merriweather', Georgia, serif;
            font-size: 15px;
            font-weight: 400;
            line-height: 1.55;
            color: var(--text-primary);
            margin-bottom: 6px;
            overflow: hidden;
            display: -webkit-box;
            -webkit-line-clamp: 4;
            -webkit-box-orient: vertical;
        }}
        .tweet-text.expanded {{
            display: block;
            overflow: visible;
        }}
        .tweet-expand-btn {{
            background: none;
            border: none;
            color: var(--accent);
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            padding: 0;
            margin-bottom: 4px;
            display: none;
        }}
        .tweet-text a {{
            color: var(--text-primary);
            text-decoration: none;
        }}
        .tweet-text a:hover {{
            color: var(--accent);
        }}
        .tweet-footer {{
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }}
        .tweet-badge {{
            display: inline-flex;
            align-items: center;
            gap: 3px;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 10px;
            background: var(--bg-hover);
            color: var(--text-muted);
        }}
        .tweet-open-link {{
            font-size: 12px;
            font-weight: 500;
            color: var(--text-muted);
            text-decoration: none;
            margin-left: auto;
        }}
        .tweet-open-link:hover {{
            color: var(--accent);
        }}
        .tweet-image {{
            margin: 6px 0;
            border-radius: 8px;
            overflow: hidden;
            max-height: 280px;
        }}
        .tweet-image img {{
            width: 100%;
            height: auto;
            max-height: 280px;
            object-fit: cover;
            display: block;
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

        /* In Focus toggle — matches ai-toggle / bookmarks-toggle pattern */
        .in-focus-toggle {{
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
        .in-focus-toggle:hover {{
            border-color: var(--border-light);
            background: var(--bg-hover);
        }}
        .in-focus-toggle.active {{
            background: var(--accent);
            border-color: var(--accent);
        }}
        .in-focus-toggle.active .pulse-dot {{
            background: #fff;
            box-shadow: 0 0 0 0 rgba(255, 255, 255, 0.4);
        }}

        /* In Focus count badge — same pattern as .bookmark-count */
        .in-focus-count {{
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

        /* Custom tooltips for top-bar action buttons */
        [data-tooltip] {{
            position: relative;
        }}
        [data-tooltip]::after {{
            content: attr(data-tooltip);
            position: absolute;
            top: calc(100% + 8px);
            left: 50%;
            transform: translateX(-50%);
            background: var(--bg-primary);
            color: var(--text-secondary);
            border: 1px solid var(--border);
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 11px;
            white-space: nowrap;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.15s;
            z-index: 1000;
        }}
        [data-tooltip]:hover::after {{
            opacity: 1;
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
        .rank-title-nolink {{
            display: block;
            font-family: 'Merriweather', Georgia, serif;
            color: var(--text-muted);
            font-size: 13px;
            line-height: 1.4;
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

        .reports-warning {{
            background: var(--danger, #e14b4b);
            color: #fff;
            padding: 10px 16px;
            border-radius: 8px;
            margin-bottom: 12px;
            font-size: 13px;
            line-height: 1.5;
        }}
        .reports-warning strong {{ font-weight: 700; }}

        /* Report Cards (main area) */
        .report-card {{
            padding: 16px 20px;
            margin-bottom: 12px;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: var(--bg-secondary);
            transition: box-shadow 0.2s ease, border-color 0.2s ease, transform 0.15s ease;
        }}
        .report-card:hover {{
            box-shadow: var(--card-shadow);
            border-color: var(--border-light);
            transform: translateY(-1px);
        }}
        .report-card-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 6px;
        }}
        .report-channel {{
            font-size: 12px;
            font-weight: 600;
            color: var(--accent);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .report-text {{
            font-family: 'Merriweather', Georgia, serif;
            font-size: 14px;
            font-weight: 500;
            line-height: 1.5;
            color: var(--text-primary);
            margin-bottom: 8px;
            display: -webkit-box;
            -webkit-line-clamp: 8;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }}
        .report-doc-list {{ display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }}
        .report-doc-item {{ display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-secondary); background: var(--bg-hover); padding: 6px 10px; border-radius: 8px; }}
        .report-doc-item:hover {{ background: var(--border); }}
        .report-doc-icon {{ flex-shrink: 0; font-size: 14px; }}
        .report-doc-name {{ flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary); font-weight: 500; }}
        .report-doc-size {{ flex-shrink: 0; font-size: 11px; color: var(--text-muted); white-space: nowrap; }}
        .report-images {{ margin-bottom: 10px; position: relative; border-radius: 8px; overflow: hidden; }}
        .report-images img {{ width: 100%; max-height: 200px; object-fit: cover; border-radius: 8px; display: block; }}
        .report-images-badge {{ position: absolute; bottom: 8px; right: 8px; background: rgba(0,0,0,0.7); color: #fff; font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 12px; }}
        .report-doc-indicator {{ display: inline-flex; align-items: center; font-size: 11px; color: var(--text-secondary); background: var(--bg-hover); padding: 2px 6px; border-radius: 10px; white-space: nowrap; }}
        .report-text.expanded {{ -webkit-line-clamp: unset; overflow: visible; }}
        .report-expand-btn {{ background: none; border: none; color: var(--accent); font-size: 13px; font-weight: 600; cursor: pointer; padding: 4px 0; margin-bottom: 8px; font-family: 'Source Sans Pro', sans-serif; }}
        .report-expand-btn:hover {{ text-decoration: underline; }}
        .report-meta {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
            color: var(--text-muted);
        }}
        .report-meta a {{
            color: var(--accent);
            text-decoration: none;
            font-weight: 500;
        }}
        .report-meta a:hover {{
            text-decoration: underline;
        }}

        /* Video Cards */
        .video-card {{
            display: flex;
            gap: 14px;
            padding: 14px 16px;
            margin-bottom: 12px;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: var(--bg-secondary);
            transition: box-shadow 0.2s ease, border-color 0.2s ease, transform 0.15s ease;
        }}
        .video-card:hover {{
            box-shadow: var(--card-shadow);
            border-color: var(--border-light);
            transform: translateY(-1px);
        }}
        .video-thumb {{
            flex-shrink: 0;
            width: 180px;
            aspect-ratio: 16/9;
            border-radius: 8px;
            overflow: hidden;
            position: relative;
            background: var(--bg-hover);
        }}
        .video-thumb img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }}
        .video-thumb-play {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 40px;
            height: 40px;
            background: rgba(0,0,0,0.7);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            opacity: 0;
            transition: opacity 0.2s;
        }}
        .video-card:hover .video-thumb-play {{
            opacity: 1;
        }}
        .video-thumb-play svg {{
            width: 16px;
            height: 16px;
            fill: #fff;
            margin-left: 2px;
        }}
        .video-info {{
            flex: 1;
            min-width: 0;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .video-title {{
            font-family: 'Merriweather', Georgia, serif;
            font-size: 15px;
            font-weight: 700;
            line-height: 1.4;
            margin-bottom: 6px;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }}
        .video-title a {{
            color: var(--text-primary);
            text-decoration: none;
        }}
        .video-title a:hover {{
            color: var(--accent);
        }}
        .video-channel {{
            font-size: 13px;
            font-weight: 600;
            color: var(--accent);
            margin-bottom: 4px;
        }}
        .video-meta {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
            color: var(--text-muted);
            margin-top: auto;
        }}
        .video-meta a {{
            color: var(--accent);
            text-decoration: none;
            font-weight: 500;
        }}
        .video-meta a:hover {{
            text-decoration: underline;
        }}

        /* Tabs */
        .content-tabs {{
            display: flex;
            gap: 0;
            border-bottom: 2px solid var(--border);
            margin-bottom: 12px;
        }}
        .content-tab {{
            font-family: inherit;
            font-size: 14px;
            font-weight: 600;
            padding: 10px 20px;
            background: transparent;
            border: none;
            border-bottom: 2px solid transparent;
            margin-bottom: -2px;
            color: var(--text-muted);
            cursor: pointer;
            transition: color 0.15s, border-color 0.15s;
        }}
        .content-tab:hover {{
            color: var(--text-secondary);
        }}
        .content-tab.active {{
            color: var(--text-primary);
            border-bottom-color: var(--accent);
        }}
        .tab-count {{
            font-size: 12px;
            font-weight: 400;
            color: var(--text-muted);
            margin-left: 4px;
        }}
        .tab-content {{
            display: none;
        }}
        .tab-content.active {{
            display: block;
        }}

        /* Reports filter — reuses preset-btn look */
        .reports-filter-btn {{
            font-family: inherit;
            font-size: 13px;
            font-weight: 500;
            padding: 5px 14px;
            border-radius: 20px;
            border: 1.5px solid var(--border);
            background: transparent;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.15s;
            white-space: nowrap;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }}
        .reports-filter-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
        .reports-filter-btn.active {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
        .reports-filter-btn:disabled {{ opacity: 0.35; cursor: not-allowed; }}

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

            .filter-row {{
                gap: 6px;
            }}
            .preset-btn {{
                font-size: 12px;
                padding: 4px 10px;
            }}
            .publisher-dropdown {{
                margin-left: 0;
                width: 100%;
            }}
            .publisher-dropdown-panel {{
                min-width: 240px;
                max-width: calc(100vw - 32px);
                left: 0;
                right: auto;
            }}
            .filter-toggle {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }}
            html.filters-collapsed .filter-row {{ display: none; }}
            html.filters-collapsed .stats-bar {{ padding-bottom: 0; }}

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

            .report-card:hover {{
                transform: none;
                box-shadow: none;
                border-color: var(--border);
            }}

            .video-card {{
                flex-direction: column;
                gap: 10px;
            }}
            .video-thumb {{
                width: 100%;
            }}
            .video-card:hover {{
                transform: none;
                box-shadow: none;
                border-color: var(--border);
            }}

            .tweet-avatar {{
                width: 32px;
                height: 32px;
                min-width: 32px;
                font-size: 13px;
            }}
            .tweet-text {{
                font-size: 14px;
            }}
            .tweet-header {{
                gap: 6px;
            }}

            .content-tab {{
                padding: 8px 14px;
                font-size: 13px;
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
    <script>
    (function(){{
      if (document.fonts && document.fonts.ready) {{
        document.fonts.ready.then(function(){{ document.body.style.opacity='1'; }});
      }} else {{
        window.addEventListener('load', function(){{ document.body.style.opacity='1'; }});
      }}
      setTimeout(function(){{ document.body.style.opacity='1'; }}, 500);
    }})();
    </script>
</head>
<body>
    <div class="top-bar">
        <div class="top-bar-inner">
            <div class="brand">
                <a href="/" class="logo" style="text-decoration:none;color:inherit;cursor:pointer;">FinanceRadar</a>
            </div>
            <div class="search-box">
                <span class="search-icon">&#128269;</span>
                <input type="text" id="search" placeholder="Search articles..." oninput="onSearchInput()">
            </div>
            <button id="ai-toggle" class="ai-toggle" type="button" aria-label="Top AI stories" data-tooltip="Top AI stories" onclick="openAiSidebar()">
                <span style="font-size: 16px;">🤖</span>
            </button>
            <button id="bookmarks-toggle" class="bookmarks-toggle" type="button" aria-label="Your bookmarks" data-tooltip="Your bookmarks">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>
                </svg>
                <span id="bookmark-count" class="bookmark-count hidden">0</span>
            </button>
            <button id="in-focus-toggle" class="in-focus-toggle" type="button" aria-label="Stories in focus" data-tooltip="Stories in focus" onclick="toggleInFocus()">
                <span class="pulse-dot"></span>
                <span class="in-focus-count">{in_focus_count}</span>
            </button>
            <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Toggle theme" data-tooltip="Toggle theme">
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
        <div class="content-tabs">
            <button class="content-tab active" data-tab="news" onclick="switchTab('news')">
                News <span class="tab-count">{len(sorted_articles)}</span>
            </button>
            <button class="content-tab" data-tab="reports" onclick="switchTab('reports')">
                Telegram <span class="tab-count">{report_count}</span>
            </button>
            <button class="content-tab" data-tab="youtube" onclick="switchTab('youtube')">
                YouTube <span class="tab-count">{video_count}</span>
            </button>
            <button class="content-tab" data-tab="twitter" onclick="switchTab('twitter')">
                Twitter <span class="tab-count">{twitter_count}</span>
            </button>
        </div>

        <div id="tab-news" class="tab-content active">
        <div class="filter-card">
            <div class="stats-bar">
                <div class="stats">
                    <span><strong>{len(sorted_articles)}</strong> articles</span>
                    <span><strong>{len(sources)}</strong> sources</span>
                </div>
                <div style="display:flex;align-items:center;">
                    <span class="update-time" id="update-time" data-time="{now_ist.isoformat()}">Updated {now_ist.strftime("%b %d, %I:%M %p")} IST</span>
                    <script>
                    (function(){{
                        var el=document.getElementById('update-time'),t=el&&el.getAttribute('data-time');
                        if(!t)return;
                        var d=Math.floor((new Date()-new Date(t))/60000);
                        el.textContent='Updated '+(d<1?'just now':d<60?d+' min ago':d<1440?Math.floor(d/60)+' hr ago':Math.floor(d/1440)+' day ago');
                    }})();
                    </script>
                    <button class="filter-toggle" type="button" onclick="toggleFilterCollapse()" aria-label="Toggle filters">
                        <svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
                    </button>
                </div>
            </div>

            <div class="filter-row" id="filter-row">
                <button class="preset-btn" data-preset="India Desk" onclick="togglePreset('India Desk')">India Desk</button>
                <button class="preset-btn" data-preset="World Desk" onclick="togglePreset('World Desk')">World Desk</button>
                <button class="preset-btn" data-preset="Indie Voices" onclick="togglePreset('Indie Voices')">Indie Voices</button>
                <button class="preset-btn" data-preset="Official Channels" onclick="togglePreset('Official Channels')">Official Channels</button>
                <div class="publisher-dropdown" id="publisher-dropdown">
                    <button class="publisher-dropdown-trigger" id="publisher-trigger" onclick="toggleDropdown()">
                        <span id="publisher-summary">All publishers</span>
                        <span class="dropdown-arrow">▼</span>
                    </button>
                    <div class="publisher-dropdown-panel" id="publisher-panel">
                        <input type="text" class="dropdown-search" id="dropdown-search" placeholder="Search publishers..." oninput="filterPublisherList()">
                        <div class="dropdown-actions">
                            <button class="dropdown-action" onclick="selectAllPublishers()">Select All</button>
                            <button class="dropdown-action" onclick="clearAllPublishers()">Clear All</button>
                        </div>
                        <div class="dropdown-list" id="dropdown-list"></div>
                    </div>
                </div>
            </div>

        </div>

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

        publisher = escape(article.get("publisher", ""))
        html += f"""            <article class="article" data-source="{source.lower()}" data-date="{article_date_iso}" data-url="{link}" data-title="{title}" data-in-focus="{is_in_focus}" data-publisher="{publisher}">
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

    html += f"""        </div>

        <div id="pagination-bottom" class="pagination bottom" aria-label="Pagination"></div>
        </div><!-- /tab-news -->

        <div id="tab-reports" class="tab-content">
            <div class="filter-card">
                <div class="stats-bar">
                    <div class="stats">
                        <span><strong id="reports-visible-count">{report_count}</strong> messages</span>
                        <span><strong>{channel_count}</strong> channels</span>
                    </div>
                    <div style="display:flex;align-items:center;">
                        <span class="update-time" id="reports-update-time" data-time="{telegram_generated_at}">Updated: --</span>
                        <script>
                        (function(){{
                            var el=document.getElementById('reports-update-time'),t=el&&el.getAttribute('data-time');
                            if(!t)return;
                            var d=Math.floor((new Date()-new Date(t))/60000);
                            el.textContent='Updated '+(d<1?'just now':d<60?d+' min ago':d<1440?Math.floor(d/60)+' hr ago':Math.floor(d/1440)+' day ago');
                        }})();
                        </script>
                        <button class="filter-toggle" type="button" onclick="toggleFilterCollapse()" aria-label="Toggle filters">
                            <svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
                        </button>
                    </div>
                </div>
                <div class="filter-row">
                    <button class="reports-filter-btn" id="reports-pdf-filter" onclick="togglePdfFilter()">📄 PDFs only</button>
                    <button class="reports-filter-btn" id="reports-notarget-filter" onclick="toggleNoTargetFilter()" disabled>No stock targets</button>
                </div>
            </div>
            <div id="reports-warning" class="reports-warning" style="display:none"></div>
            <div id="reports-container"></div>
            <div id="reports-pagination-bottom" class="pagination bottom"></div>
        </div><!-- /tab-reports -->

        <div id="tab-youtube" class="tab-content">
            <div class="filter-card">
                <div class="stats-bar">
                    <div class="stats">
                        <span><strong id="youtube-visible-count">{video_count}</strong> videos</span>
                        <span id="youtube-publisher-count-label"><strong>{video_channel_count}</strong> channels</span>
                    </div>
                    <div style="display:flex;align-items:center;">
                        <span class="update-time" id="youtube-update-time" data-time="{now_ist.isoformat()}">Updated {now_ist.strftime("%b %d, %I:%M %p")} IST</span>
                        <script>
                        (function(){{
                            var el=document.getElementById('youtube-update-time'),t=el&&el.getAttribute('data-time');
                            if(!t)return;
                            var d=Math.floor((new Date()-new Date(t))/60000);
                            el.textContent='Updated '+(d<1?'just now':d<60?d+' min ago':d<1440?Math.floor(d/60)+' hr ago':Math.floor(d/1440)+' day ago');
                        }})();
                        </script>
                        <button class="filter-toggle" type="button" onclick="toggleFilterCollapse()" aria-label="Toggle filters">
                            <svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
                        </button>
                    </div>
                </div>
                <div class="filter-row" id="youtube-filter-row">
                    <div class="publisher-dropdown" id="youtube-publisher-dropdown">
                        <button class="publisher-dropdown-trigger" id="youtube-publisher-trigger" onclick="toggleYoutubeDropdown()">
                            <span id="youtube-publisher-summary">All channels</span>
                            <span class="dropdown-arrow">&#9660;</span>
                        </button>
                        <div class="publisher-dropdown-panel" id="youtube-publisher-panel">
                            <input type="text" class="dropdown-search" id="youtube-dropdown-search" placeholder="Search channels..." oninput="filterYoutubePublisherList()">
                            <div class="dropdown-actions">
                                <button class="dropdown-action" onclick="selectAllYoutubePublishers()">Select All</button>
                                <button class="dropdown-action" onclick="clearAllYoutubePublishers()">Clear All</button>
                            </div>
                            <div class="dropdown-list" id="youtube-dropdown-list"></div>
                        </div>
                    </div>
                </div>
            </div>
            <div id="youtube-container"></div>
            <div id="youtube-pagination-bottom" class="pagination bottom"></div>
        </div><!-- /tab-youtube -->

        <div id="tab-twitter" class="tab-content">
            <div class="filter-card">
                <div class="stats-bar">
                    <div class="stats">
                        <span><strong id="twitter-visible-count">{twitter_count}</strong> tweets</span>
                        <span id="twitter-publisher-count-label"></span>
                    </div>
                    <div style="display:flex;align-items:center;">
                        <span class="update-time" id="twitter-update-time" data-time="{now_ist.isoformat()}">Updated {now_ist.strftime("%b %d, %I:%M %p")} IST</span>
                        <script>
                        (function(){{
                            var el=document.getElementById('twitter-update-time'),t=el&&el.getAttribute('data-time');
                            if(!t)return;
                            var d=Math.floor((new Date()-new Date(t))/60000);
                            el.textContent='Updated '+(d<1?'just now':d<60?d+' min ago':d<1440?Math.floor(d/60)+' hr ago':Math.floor(d/1440)+' day ago');
                        }})();
                        </script>
                        <button class="filter-toggle" type="button" onclick="toggleFilterCollapse()" aria-label="Toggle filters">
                            <svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
                        </button>
                    </div>
                </div>
                <div class="filter-row" id="twitter-filter-row">
                    <button class="preset-btn" data-twitter-preset="Money Managers" onclick="toggleTwitterPreset('Money Managers')">Money Managers</button>
                    <button class="preset-btn" data-twitter-preset="Stock Pickers" onclick="toggleTwitterPreset('Stock Pickers')">Stock Pickers</button>
                    <button class="preset-btn" data-twitter-preset="Newsroom" onclick="toggleTwitterPreset('Newsroom')">Newsroom</button>
                    <button class="preset-btn" data-twitter-preset="Macro &amp; Policy" onclick="toggleTwitterPreset('Macro & Policy')">Macro &amp; Policy</button>
                    <button class="preset-btn" data-twitter-preset="Data &amp; Climate" onclick="toggleTwitterPreset('Data & Climate')">Data &amp; Climate</button>
                    <div class="publisher-dropdown" id="twitter-publisher-dropdown">
                        <button class="publisher-dropdown-trigger" id="twitter-publisher-trigger" onclick="toggleTwitterDropdown()">
                            <span id="twitter-publisher-summary">All publishers</span>
                            <span class="dropdown-arrow">&#9660;</span>
                        </button>
                        <div class="publisher-dropdown-panel" id="twitter-publisher-panel">
                            <input type="text" class="dropdown-search" id="twitter-dropdown-search" placeholder="Search publishers..." oninput="filterTwitterPublisherList()">
                            <div class="dropdown-actions">
                                <button class="dropdown-action" onclick="selectAllTwitterPublishers()">Select All</button>
                                <button class="dropdown-action" onclick="clearAllTwitterPublishers()">Clear All</button>
                            </div>
                            <div class="dropdown-list" id="twitter-dropdown-list"></div>
                        </div>
                    </div>
                </div>
            </div>
            <div id="twitter-container"></div>
            <div id="twitter-pagination-bottom" class="pagination bottom"></div>
        </div><!-- /tab-twitter -->
"""

    html += """        <footer>
            Aggregated from {source_count} sources · Built with Python · Made by <a href="https://kashishkapoor.com/" target="_blank" rel="noopener">Kashish Kapoor</a> · Built for <a href="https://thedailybrief.zerodha.com/" target="_blank" rel="noopener">The Daily Brief by Zerodha</a>
        </footer>
    </div>

    <button class="back-to-top" onclick="window.scrollTo({top:0,behavior:'smooth'})" title="Back to top">↑</button>

    <div class="keyboard-hint">
        <kbd>1</kbd> <kbd>2</kbd> <kbd>3</kbd> <kbd>4</kbd> tabs · <kbd>J</kbd> <kbd>K</kbd> navigate · <kbd>/</kbd> search
    </div>

    <script>
"""
    # Inject publisher data as JSON
    html += f"""        const ALL_PUBLISHERS = {all_publishers_json};
        const PUBLISHER_PRESETS = {publisher_presets_json};
        const TELEGRAM_REPORTS = {telegram_reports_json};
        const TELEGRAM_GENERATED_AT = "{telegram_generated_at}";
        const TELEGRAM_WARNINGS = {json.dumps(telegram_warnings)};
        const YOUTUBE_VIDEOS = {video_articles_json};
        const YOUTUBE_PUBLISHERS = {youtube_publishers_json};
        const TWITTER_ARTICLES = {twitter_articles_json};
        const TWITTER_PUBLISHERS = {twitter_publishers_json};
        const TWITTER_PRESETS = {twitter_presets_json};
"""
    html += """
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

        // Filter collapse toggle (mobile)
        function toggleFilterCollapse() {
            var dd = document.getElementById('publisher-dropdown');
            if (dd && dd.classList.contains('open')) closeDropdown();
            var tdd = document.getElementById('twitter-publisher-dropdown');
            if (tdd && tdd.classList.contains('open')) closeTwitterDropdown();
            var ydd = document.getElementById('youtube-publisher-dropdown');
            if (ydd && ydd.classList.contains('open')) closeYoutubeDropdown();
            var isCollapsed = document.documentElement.classList.toggle('filters-collapsed');
            safeStorage.set('financeradar_filters_collapsed', isCollapsed ? 'true' : 'false');
        }

        // Multi-select publisher filter
        let selectedPublishers = new Set();
        let inFocusOnly = false;

        function initPublisherDropdown() {
            const list = document.getElementById('dropdown-list');
            list.innerHTML = '';
            ALL_PUBLISHERS.forEach(pub => {
                const item = document.createElement('div');
                item.className = 'dropdown-item';
                item.dataset.publisher = pub;
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.id = 'pub-' + pub.replace(/\\s+/g, '-');
                cb.dataset.publisher = pub;
                cb.addEventListener('change', () => onPublisherCheckChange(pub, cb.checked));
                const lbl = document.createElement('label');
                lbl.htmlFor = cb.id;
                lbl.textContent = pub;
                item.appendChild(cb);
                item.appendChild(lbl);
                item.addEventListener('click', (e) => {
                    if (e.target !== cb) {
                        cb.checked = !cb.checked;
                        onPublisherCheckChange(pub, cb.checked);
                    }
                });
                list.appendChild(item);
            });
        }

        function toggleDropdown() {
            const dd = document.getElementById('publisher-dropdown');
            dd.classList.toggle('open');
            if (dd.classList.contains('open')) {
                document.getElementById('dropdown-search').focus();
            }
        }

        function closeDropdown() {
            const dd = document.getElementById('publisher-dropdown');
            if (dd) dd.classList.remove('open');
            const search = document.getElementById('dropdown-search');
            if (search) { search.value = ''; filterPublisherList(); }
        }

        function filterPublisherList() {
            const query = document.getElementById('dropdown-search').value.toLowerCase();
            document.querySelectorAll('#dropdown-list .dropdown-item').forEach(item => {
                const pub = item.dataset.publisher.toLowerCase();
                item.classList.toggle('hidden', query && !pub.includes(query));
            });
        }

        function selectAllPublishers() {
            selectedPublishers.clear();
            syncCheckboxes();
            syncPresetButtons();
            updatePublisherSummary();
            filterArticles();
        }

        function clearAllPublishers() {
            selectedPublishers.clear();
            syncCheckboxes();
            syncPresetButtons();
            updatePublisherSummary();
            filterArticles();
        }

        function onPublisherCheckChange(pub, checked) {
            if (checked) {
                selectedPublishers.add(pub);
            } else {
                selectedPublishers.delete(pub);
            }
            syncPresetButtons();
            updatePublisherSummary();
            filterArticles();
        }

        function syncCheckboxes() {
            document.querySelectorAll('#dropdown-list input[type="checkbox"]').forEach(cb => {
                cb.checked = selectedPublishers.has(cb.dataset.publisher);
            });
        }

        function togglePreset(name) {
            const pubs = PUBLISHER_PRESETS[name];
            if (!pubs) return;
            const allSelected = pubs.every(p => selectedPublishers.has(p));
            if (allSelected) {
                pubs.forEach(p => selectedPublishers.delete(p));
            } else {
                pubs.forEach(p => selectedPublishers.add(p));
            }
            syncCheckboxes();
            syncPresetButtons();
            updatePublisherSummary();
            filterArticles();
        }

        function syncPresetButtons() {
            document.querySelectorAll('.preset-btn').forEach(btn => {
                const name = btn.dataset.preset;
                const pubs = PUBLISHER_PRESETS[name];
                if (!pubs) return;
                const selected = pubs.filter(p => selectedPublishers.has(p));
                if (selectedPublishers.size === 0) {
                    btn.classList.remove('active', 'partial');
                } else if (selected.length === pubs.length) {
                    btn.classList.add('active');
                    btn.classList.remove('partial');
                } else if (selected.length > 0) {
                    btn.classList.remove('active');
                    btn.classList.add('partial');
                } else {
                    btn.classList.remove('active', 'partial');
                }
            });
        }

        function updatePublisherSummary() {
            const el = document.getElementById('publisher-summary');
            const trigger = document.getElementById('publisher-trigger');
            if (selectedPublishers.size === 0) {
                el.textContent = 'All publishers';
                trigger.classList.remove('has-selection');
            } else if (selectedPublishers.size === 1) {
                el.textContent = [...selectedPublishers][0];
                trigger.classList.add('has-selection');
            } else {
                el.textContent = selectedPublishers.size + ' of ' + ALL_PUBLISHERS.length + ' publishers';
                trigger.classList.add('has-selection');
            }
        }

        function getActiveTab() {
            return document.querySelector('.content-tab.active')?.dataset.tab || 'news';
        }

        function onSearchInput() {
            const tab = getActiveTab();
            if (tab === 'reports') {
                filterReports();
            } else if (tab === 'youtube') {
                filterYoutube();
            } else if (tab === 'twitter') {
                filterTwitter();
            } else {
                filterArticles();
            }
        }

        function filterArticles() {
            const query = document.getElementById('search').value.toLowerCase();
            const articles = document.querySelectorAll('.article');
            const dateHeaders = document.querySelectorAll('.date-header');

            articles.forEach(article => {
                const text = article.textContent.toLowerCase();
                const publisher = article.dataset.publisher || '';
                const isInFocus = article.dataset.inFocus === 'true';
                const matchesSearch = !query || text.includes(query);
                const matchesPublisher = selectedPublishers.size === 0 || selectedPublishers.has(publisher);
                const matchesInFocus = !inFocusOnly || isInFocus;
                article.classList.toggle('hidden', !(matchesSearch && matchesPublisher && matchesInFocus));
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

        function toggleInFocus() {
            inFocusOnly = !inFocusOnly;
            document.getElementById('in-focus-toggle').classList.toggle('active', inFocusOnly);
            filterArticles();
        }

        // Close dropdown on outside click
        document.addEventListener('click', (e) => {
            const dd = document.getElementById('publisher-dropdown');
            if (dd.classList.contains('open') && !dd.contains(e.target)) {
                closeDropdown();
            }
            const tdd = document.getElementById('twitter-publisher-dropdown');
            if (tdd && tdd.classList.contains('open') && !tdd.contains(e.target)) {
                closeTwitterDropdown();
            }
            const ydd = document.getElementById('youtube-publisher-dropdown');
            if (ydd && ydd.classList.contains('open') && !ydd.contains(e.target)) {
                closeYoutubeDropdown();
            }
        });

        // Close dropdown on Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                const dd = document.getElementById('publisher-dropdown');
                if (dd.classList.contains('open')) {
                    closeDropdown();
                    e.stopImmediatePropagation();
                    return;
                }
                const tdd = document.getElementById('twitter-publisher-dropdown');
                if (tdd && tdd.classList.contains('open')) {
                    closeTwitterDropdown();
                    e.stopImmediatePropagation();
                    return;
                }
                const ydd = document.getElementById('youtube-publisher-dropdown');
                if (ydd && ydd.classList.contains('open')) {
                    closeYoutubeDropdown();
                    e.stopImmediatePropagation();
                    return;
                }
            }
        });

        // Initialize publisher dropdown
        initPublisherDropdown();

        // Pagination
        const PAGE_SIZE = 20;
        let currentPage = 1;
        const TODAY_ISO = "{today_iso}";

        function getFilteredArticles() {
            return [...document.querySelectorAll('.article:not(.hidden)')];
        }

        function renderPagination(totalPages) {
            const bottom = document.getElementById('pagination-bottom');
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
            try { localStorage.setItem('financeradar_page', currentPage); } catch(e) {}
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
                onSearchInput();
            } else if (e.key === '1') {
                switchTab('news');
            } else if (e.key === '2') {
                switchTab('reports');
            } else if (e.key === '3') {
                switchTab('youtube');
            } else if (e.key === '4') {
                switchTab('twitter');
            }
        });

        // Initial pagination — restore saved page or default to today
        const savedPage = parseInt(safeStorage.get('financeradar_page'), 10);
        if (savedPage && savedPage > 0) {
            currentPage = savedPage;
        } else {
            setPageToToday();
        }
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

        function toggleGenericBookmark(btn) {
            const url = btn.dataset.url;
            const title = btn.dataset.title;
            const source = btn.dataset.source || '';

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

        function syncBookmarkState() {
            const bookmarks = getBookmarks();
            const urls = new Set(bookmarks.map(b => b.url));
            document.querySelectorAll('.bookmark-btn[data-url]').forEach(btn => {
                btn.classList.toggle('bookmarked', urls.has(btn.dataset.url));
            });
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
            const article = document.querySelector(`.article[data-url="${CSS.escape(url)}"], .tweet-item[data-url="${CSS.escape(url)}"]`);
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
        let currentAiProvider = 'auto';

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
                        ${r.url
                            ? `<a href="${escapeHtml(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.title)}</a>`
                            : `<span class="rank-title-nolink">${escapeHtml(r.title)}</span>`
                        }
                        <span class="rank-source">${escapeHtml(r.source)}</span>
                    </div>
                    <button class="ai-bookmark-btn ${isBookmarked(r.url) ? 'bookmarked' : ''}"
                            data-url="${escapeForAttr(r.url)}" data-title="${escapeForAttr(r.title)}" data-source="${escapeForAttr(r.source)}" title="Bookmark">
                        <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                    </button>
                </div>
            `).join('');
            const aiEl = document.getElementById('ai-updated');
            aiEl.setAttribute('data-time', aiRankings.generated_at);
            const aiD = Math.floor((new Date() - new Date(aiRankings.generated_at)) / 60000);
            aiEl.textContent = 'Updated ' + (aiD < 1 ? 'just now' : aiD < 60 ? aiD + ' min ago' : aiD < 1440 ? Math.floor(aiD / 60) + ' hr ago' : Math.floor(aiD / 1440) + ' day ago');
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
            const article = document.querySelector(`.article[data-url="${CSS.escape(url)}"], .tweet-item[data-url="${CSS.escape(url)}"]`);
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

        // ==================== REPORTS TAB ====================
        let reportsRendered = false;
        let filteredReports = [];
        let reportsPdfFilterActive = false;
        let reportsNoTargetFilterActive = false;
        let reportsPage = 1;
        const REPORTS_PAGE_SIZE = 20;

        // ==================== YOUTUBE TAB (vars) ====================
        let youtubeRendered = false;
        let filteredYoutube = [];
        let youtubePage = 1;
        const YOUTUBE_PAGE_SIZE = 20;
        let selectedYoutubePublishers = new Set();

        // ==================== TWITTER TAB (vars) ====================
        let twitterRendered = false;
        let filteredTwitter = [];
        let twitterPage = 1;
        const TWITTER_PAGE_SIZE = 30;
        let selectedTwitterPublishers = new Set();

        // Restore last active tab
        (function() {
            var saved = safeStorage.get('financeradar_active_tab');
            if (saved && saved !== 'news') switchTab(saved, true);
        })();

        function switchTab(tab, skipScroll) {
            document.querySelectorAll('.content-tab').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.tab === tab);
            });
            document.querySelectorAll('.tab-content').forEach(el => {
                el.classList.toggle('active', el.id === 'tab-' + tab);
            });
            const searchEl = document.getElementById('search');
            searchEl.placeholder = tab === 'reports' ? 'Search Telegram...' : tab === 'youtube' ? 'Search YouTube...' : tab === 'twitter' ? 'Search tweets...' : 'Search articles...';
            if (tab === 'reports') {
                if (!reportsRendered) {
                    renderMainReports();
                    reportsRendered = true;
                }
                filterReports();
            } else if (tab === 'youtube') {
                if (!youtubeRendered) {
                    renderMainYoutube();
                    youtubeRendered = true;
                }
                filterYoutube();
            } else if (tab === 'twitter') {
                if (!twitterRendered) {
                    renderMainTwitter();
                    twitterRendered = true;
                }
                filterTwitter();
            } else {
                filterArticles();
            }
            if (!skipScroll) window.scrollTo({top: 0, behavior: 'smooth'});
            safeStorage.set('financeradar_active_tab', tab);
        }

        function formatReportDate(isoStr) {
            if (!isoStr) return '';
            const date = new Date(isoStr);
            const now = new Date();
            const diffMs = now - date;
            const diffMin = Math.floor(diffMs / 60000);
            const diffHr = Math.floor(diffMs / 3600000);
            const diffDay = Math.floor(diffMs / 86400000);
            if (diffMin < 1) return 'Just now';
            if (diffMin < 60) return diffMin + 'm ago';
            if (diffHr < 24) return diffHr + 'h ago';
            if (diffDay === 1) return 'Yesterday';
            if (diffDay < 7) return diffDay + 'd ago';
            return date.toLocaleDateString();
        }

        function formatReportDateHeader(isoStr) {
            if (!isoStr) return 'Unknown Date';
            const date = new Date(isoStr);
            const now = new Date();
            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            const articleDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
            const diffDays = Math.floor((today - articleDay) / 86400000);
            if (diffDays === 0) return 'Today';
            if (diffDays === 1) return 'Yesterday';
            return date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
        }

        function renderMainReports() {
            filteredReports = [...TELEGRAM_REPORTS];
            reportsPage = 1;
            applyReportsPagination();
            // Show warnings if any
            var warnEl = document.getElementById('reports-warning');
            if (warnEl && TELEGRAM_WARNINGS && TELEGRAM_WARNINGS.length > 0) {
                warnEl.innerHTML = '<strong>⚠ Fetch issue:</strong> ' + TELEGRAM_WARNINGS.map(w => escapeHtml(w)).join(' · ') + ' — some reports may be missing.';
                warnEl.style.display = 'block';
            }
        }

        function togglePdfFilter() {
            reportsPdfFilterActive = !reportsPdfFilterActive;
            document.getElementById('reports-pdf-filter').classList.toggle('active', reportsPdfFilterActive);
            const noTargetBtn = document.getElementById('reports-notarget-filter');
            noTargetBtn.disabled = !reportsPdfFilterActive;
            if (!reportsPdfFilterActive && reportsNoTargetFilterActive) {
                reportsNoTargetFilterActive = false;
                noTargetBtn.classList.remove('active');
            }
            filterReports();
        }

        function toggleNoTargetFilter() {
            reportsNoTargetFilterActive = !reportsNoTargetFilterActive;
            document.getElementById('reports-notarget-filter').classList.toggle('active', reportsNoTargetFilterActive);
            filterReports();
        }

        function reportHasStockTarget(r) {
            const RE = /\\bupside\\b|\\bdownside\\b|\\bTP\\s+\\d|\\btarget\\s+price\\b/i;
            if (RE.test(r.text || '')) return true;
            const docs = (r.documents && r.documents.length > 0) ? r.documents
                : (r.document && r.document.title) ? [r.document] : [];
            return docs.some(d => RE.test(d.title || ''));
        }

        function reportHasPdf(r) {
            if (r.documents && r.documents.length > 0) return true;
            if (r.document && r.document.title) return true;
            if (/https?:\/\/\S+\.pdf(\b|\?)/i.test(r.text || '')) return true;
            return false;
        }

        function filterReports() {
            const query = document.getElementById('search').value.toLowerCase().trim();
            if (!query) {
                filteredReports = [...TELEGRAM_REPORTS];
            } else {
                filteredReports = TELEGRAM_REPORTS.filter(r => {
                    const text = (r.text || '').toLowerCase();
                    const channel = (r.channel || '').toLowerCase();
                    const docTitle = (r.documents && r.documents.length > 0
                        ? r.documents.map(d => d.title || '').join(' ')
                        : (r.document && r.document.title || '')).toLowerCase();
                    return text.includes(query) || channel.includes(query) || docTitle.includes(query);
                });
            }
            if (reportsPdfFilterActive) {
                filteredReports = filteredReports.filter(reportHasPdf);
            }
            if (reportsNoTargetFilterActive) {
                filteredReports = filteredReports.filter(r => !reportHasStockTarget(r));
            }
            document.getElementById('reports-visible-count').textContent = filteredReports.length;
            reportsPage = 1;
            applyReportsPagination();
        }

        function applyReportsPagination() {
            const totalPages = Math.max(1, Math.ceil(filteredReports.length / REPORTS_PAGE_SIZE));
            if (reportsPage > totalPages) reportsPage = totalPages;

            const start = (reportsPage - 1) * REPORTS_PAGE_SIZE;
            const end = start + REPORTS_PAGE_SIZE;
            const pageReports = filteredReports.slice(start, end);

            const container = document.getElementById('reports-container');
            if (pageReports.length === 0) {
                container.innerHTML = '<div style="padding:40px 20px;text-align:center;color:var(--text-muted);font-size:14px;">No reports found.</div>';
                renderReportsPagination(totalPages);
                return;
            }

            let html = '';
            let currentDateHeader = '';
            const bookmarks = getBookmarks();

            pageReports.forEach(r => {
                const dateHeader = formatReportDateHeader(r.date);
                if (dateHeader !== currentDateHeader) {
                    currentDateHeader = dateHeader;
                    html += `<h2 class="date-header">${dateHeader}</h2>`;
                }

                const text = escapeHtml(r.text || '').replace(/\\n/g, '<br>');
                const reportUrl = r.url || '';
                const isBookmarkedReport = bookmarks.some(b => b.url === reportUrl);
                let docHtml = '';
                const docs = (r.documents && r.documents.length > 0) ? r.documents
                    : (r.document && r.document.title) ? [r.document] : [];
                if (docs.length > 0) {
                    const docItems = docs.map(d => {
                        const name = escapeHtml(d.title || 'Document');
                        const size = d.size ? `<span class="report-doc-size">${escapeHtml(d.size)}</span>` : '';
                        return `<div class="report-doc-item"><span class="report-doc-icon">📄</span><span class="report-doc-name">${name}</span>${size}</div>`;
                    }).join('');
                    docHtml = `<div class="report-doc-list">${docItems}</div>`;
                }

                let imgHtml = '';
                const images = r.images || [];
                if (images.length > 0) {
                    const badge = images.length > 1
                        ? `<span class="report-images-badge">+${images.length - 1} more</span>` : '';
                    imgHtml = `<div class="report-images">
                        <img src="${escapeForAttr(images[0])}" alt="Report image" loading="lazy"
                             onerror="this.parentElement.style.display='none'">
                        ${badge}</div>`;
                }

                const hasDoc = !!(r.documents && r.documents.length > 0) || !!(r.document && r.document.title);
                const hasPdfLink = /https?:\\/\\/\\S+\\.pdf(\\b|\\?)/i.test(r.text || '');
                const docIndicatorHtml = (hasDoc || hasPdfLink)
                    ? '<span class="report-doc-indicator" title="Contains document/PDF">📄</span>' : '';

                const channel = escapeHtml(r.channel);

                html += `
                    <div class="report-card" data-url="${escapeForAttr(reportUrl)}" data-title="${escapeForAttr((r.text || '').split('\\n')[0].substring(0, 100))}" data-channel="${escapeForAttr(r.channel || '')}">
                        <div class="report-card-header">
                            <div style="display:flex;align-items:center;gap:6px">
                                <span class="report-channel">${channel}</span>
                                ${docIndicatorHtml}
                            </div>
                            <button class="bookmark-btn${isBookmarkedReport ? ' bookmarked' : ''}" onclick="toggleReportBookmark(this)" aria-label="Bookmark report" title="Bookmark">
                                <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                            </button>
                        </div>
                        ${docHtml}
                        ${imgHtml}
                        <div class="report-text">${text}</div>
                        <button class="report-expand-btn" style="display:none" onclick="toggleReportExpand(this)">Show more</button>
                        <div class="report-meta">
                            <span>${formatReportDate(r.date)}${r.views ? ' · ' + escapeHtml(r.views) + ' views' : ''}</span>
                            <a href="${escapeHtml(reportUrl)}" target="_blank" rel="noopener">Open in Telegram →</a>
                        </div>
                    </div>
                `;
            });

            container.innerHTML = html;
            container.querySelectorAll('.report-text').forEach(el => {
                if (el.scrollHeight > el.clientHeight) {
                    const btn = el.nextElementSibling;
                    if (btn && btn.classList.contains('report-expand-btn')) {
                        btn.style.display = 'block';
                    }
                }
            });
            renderReportsPagination(totalPages);
        }

        function renderReportsPagination(totalPages) {
            const bottom = document.getElementById('reports-pagination-bottom');
            bottom.innerHTML = '';

            if (totalPages <= 1) return;

            const makeBtn = (label, page, isActive = false, isDisabled = false) => {
                const btn = document.createElement('button');
                btn.className = 'page-btn' + (isActive ? ' active' : '');
                btn.textContent = label;
                if (isDisabled) {
                    btn.disabled = true;
                } else {
                    btn.addEventListener('click', () => {
                        reportsPage = page;
                        applyReportsPagination();
                        window.scrollTo({top: 0, behavior: 'smooth'});
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
            let startP = Math.max(1, reportsPage - half);
            let endP = Math.min(totalPages, reportsPage + half);
            if (endP - startP + 1 < windowSize) {
                if (startP === 1) endP = Math.min(totalPages, startP + windowSize - 1);
                else if (endP === totalPages) startP = Math.max(1, endP - windowSize + 1);
            }

            const build = (container) => {
                const prevBtn = makeBtn('← Prev', Math.max(1, reportsPage - 1), false, reportsPage === 1);
                prevBtn.classList.add('nav', 'prev');
                container.appendChild(prevBtn);
                if (startP > 1) {
                    container.appendChild(makeBtn('1', 1, reportsPage === 1));
                    if (startP > 2) container.appendChild(makeEllipsis());
                }
                for (let i = startP; i <= endP; i++) {
                    container.appendChild(makeBtn(String(i), i, i === reportsPage));
                }
                if (endP < totalPages) {
                    if (endP < totalPages - 1) container.appendChild(makeEllipsis());
                    container.appendChild(makeBtn(String(totalPages), totalPages, reportsPage === totalPages));
                }
                const nextBtn = makeBtn('Next →', Math.min(totalPages, reportsPage + 1), false, reportsPage === totalPages);
                nextBtn.classList.add('nav', 'next');
                container.appendChild(nextBtn);
            };

            build(bottom);
        }

        function toggleReportExpand(btn) {
            const textEl = btn.previousElementSibling;
            const isExpanded = textEl.classList.toggle('expanded');
            btn.textContent = isExpanded ? 'Show less' : 'Show more';
        }

        function toggleReportBookmark(btn) {
            const card = btn.closest('.report-card');
            const url = card.dataset.url;
            const title = card.dataset.title;
            const source = card.dataset.channel;

            let bookmarks = getBookmarks();
            const idx = bookmarks.findIndex(b => b.url === url);

            if (idx >= 0) {
                bookmarks.splice(idx, 1);
                btn.classList.remove('bookmarked');
            } else {
                bookmarks.unshift({ url, title, source: source + ' (Telegram)', addedAt: Date.now() });
                btn.classList.add('bookmarked');
            }

            saveBookmarks(bookmarks);
            updateBookmarkCount();
            renderSidebarContent();
        }

        // ==================== YOUTUBE TAB (functions) ====================
        function renderMainYoutube() {
            initYoutubePublisherDropdown();
            filteredYoutube = [...YOUTUBE_VIDEOS];
            youtubePage = 1;
            applyYoutubePagination();
        }

        function filterYoutube() {
            const query = document.getElementById('search').value.toLowerCase().trim();
            filteredYoutube = YOUTUBE_VIDEOS.filter(v => {
                const matchesSearch = !query || (v.title + ' ' + v.source + ' ' + v.publisher).toLowerCase().includes(query);
                const pub = v.publisher || v.source;
                const matchesPublisher = selectedYoutubePublishers.size === 0 || selectedYoutubePublishers.has(pub);
                return matchesSearch && matchesPublisher;
            });
            youtubePage = 1;
            applyYoutubePagination();
            updateYoutubePublisherSummary();
        }

        function initYoutubePublisherDropdown() {
            const list = document.getElementById('youtube-dropdown-list');
            if (!list) return;
            list.innerHTML = '';
            YOUTUBE_PUBLISHERS.forEach(pub => {
                const item = document.createElement('div');
                item.className = 'dropdown-item';
                item.dataset.publisher = pub;
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.id = 'ytpub-' + pub.replace(/\\s+/g, '-');
                cb.dataset.publisher = pub;
                cb.addEventListener('change', () => onYoutubePublisherChange(pub, cb.checked));
                const lbl = document.createElement('label');
                lbl.htmlFor = cb.id;
                lbl.textContent = pub;
                item.appendChild(cb);
                item.appendChild(lbl);
                item.addEventListener('click', (e) => {
                    if (e.target !== cb) {
                        cb.checked = !cb.checked;
                        onYoutubePublisherChange(pub, cb.checked);
                    }
                });
                list.appendChild(item);
            });
        }

        function toggleYoutubeDropdown() {
            const dd = document.getElementById('youtube-publisher-dropdown');
            dd.classList.toggle('open');
            if (dd.classList.contains('open')) {
                document.getElementById('youtube-dropdown-search').focus();
            }
        }

        function filterYoutubePublisherList() {
            const query = document.getElementById('youtube-dropdown-search').value.toLowerCase();
            document.querySelectorAll('#youtube-dropdown-list .dropdown-item').forEach(item => {
                const pub = item.dataset.publisher.toLowerCase();
                item.classList.toggle('hidden', query && !pub.includes(query));
            });
        }

        function selectAllYoutubePublishers() {
            selectedYoutubePublishers.clear();
            syncYoutubeCheckboxes();
            updateYoutubePublisherSummary();
            filterYoutube();
        }

        function clearAllYoutubePublishers() {
            selectedYoutubePublishers.clear();
            syncYoutubeCheckboxes();
            updateYoutubePublisherSummary();
            filterYoutube();
        }

        function onYoutubePublisherChange(pub, checked) {
            if (checked) {
                selectedYoutubePublishers.add(pub);
            } else {
                selectedYoutubePublishers.delete(pub);
            }
            updateYoutubePublisherSummary();
            filterYoutube();
        }

        function syncYoutubeCheckboxes() {
            document.querySelectorAll('#youtube-dropdown-list input[type="checkbox"]').forEach(cb => {
                cb.checked = selectedYoutubePublishers.has(cb.dataset.publisher);
            });
        }

        function updateYoutubePublisherSummary() {
            const el = document.getElementById('youtube-publisher-summary');
            const countLabel = document.getElementById('youtube-publisher-count-label');
            if (!el) return;
            const n = selectedYoutubePublishers.size;
            const total = YOUTUBE_PUBLISHERS.length;
            if (n === 0) {
                el.textContent = 'All channels';
                if (countLabel) countLabel.innerHTML = '<strong>' + total + '</strong> channels';
            } else if (n === 1) {
                el.textContent = [...selectedYoutubePublishers][0];
                if (countLabel) countLabel.textContent = '\u00b7 1 of ' + total + ' channels';
            } else {
                el.textContent = n + ' channels';
                if (countLabel) countLabel.textContent = '\u00b7 ' + n + ' of ' + total + ' channels';
            }
        }

        function closeYoutubeDropdown() {
            const dd = document.getElementById('youtube-publisher-dropdown');
            if (dd) dd.classList.remove('open');
            const search = document.getElementById('youtube-dropdown-search');
            if (search) { search.value = ''; filterYoutubePublisherList(); }
        }

        function formatYoutubeDate(isoStr) {
            if (!isoStr) return '';
            const date = new Date(isoStr);
            const now = new Date();
            const diffMs = now - date;
            const diffMin = Math.floor(diffMs / 60000);
            const diffHr = Math.floor(diffMs / 3600000);
            const diffDay = Math.floor(diffMs / 86400000);
            if (diffMin < 1) return 'Just now';
            if (diffMin < 60) return diffMin + 'm ago';
            if (diffHr < 24) return diffHr + 'h ago';
            if (diffDay === 1) return 'Yesterday';
            if (diffDay < 7) return diffDay + 'd ago';
            return date.toLocaleDateString();
        }

        function formatYoutubeDateHeader(isoStr) {
            if (!isoStr) return 'Unknown Date';
            const date = new Date(isoStr);
            const now = new Date();
            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            const videoDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
            const diffDays = Math.floor((today - videoDay) / 86400000);
            if (diffDays === 0) return 'Today';
            if (diffDays === 1) return 'Yesterday';
            return date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
        }

        function applyYoutubePagination() {
            const totalPages = Math.max(1, Math.ceil(filteredYoutube.length / YOUTUBE_PAGE_SIZE));
            if (youtubePage > totalPages) youtubePage = totalPages;

            document.getElementById('youtube-visible-count').textContent = filteredYoutube.length;

            const start = (youtubePage - 1) * YOUTUBE_PAGE_SIZE;
            const end = start + YOUTUBE_PAGE_SIZE;
            const pageVideos = filteredYoutube.slice(start, end);

            const container = document.getElementById('youtube-container');
            if (pageVideos.length === 0) {
                container.innerHTML = '<div style="padding:40px 20px;text-align:center;color:var(--text-muted);font-size:14px;">No videos found.</div>';
                renderYoutubePagination(totalPages);
                return;
            }

            let html = '';
            let currentDateHeader = '';

            pageVideos.forEach(v => {
                const dateHeader = formatYoutubeDateHeader(v.date);
                if (dateHeader !== currentDateHeader) {
                    currentDateHeader = dateHeader;
                    html += `<h2 class="date-header">${dateHeader}</h2>`;
                }

                const title = escapeHtml(v.title);
                const channel = escapeHtml(v.publisher || v.source);
                const link = escapeHtml(v.link);
                const thumbnail = v.thumbnail || (v.video_id ? `https://i.ytimg.com/vi/${v.video_id}/mqdefault.jpg` : '');

                html += `
                    <div class="video-card">
                        <a href="${link}" target="_blank" rel="noopener" class="video-thumb">
                            ${thumbnail ? `<img src="${escapeForAttr(thumbnail)}" alt="${title}" loading="lazy" onerror="this.style.display='none'">` : ''}
                            <div class="video-thumb-play">
                                <svg viewBox="0 0 24 24"><polygon points="5,3 19,12 5,21"/></svg>
                            </div>
                        </a>
                        <div class="video-info">
                            <div class="video-channel">${channel}</div>
                            <div class="video-title"><a href="${link}" target="_blank" rel="noopener">${title}</a></div>
                            <div class="video-meta">
                                <span>${formatYoutubeDate(v.date)}</span>
                                <a href="${link}" target="_blank" rel="noopener">Watch on YouTube &rarr;</a>
                                <button class="bookmark-btn" data-url="${link}" data-title="${escapeForAttr(v.title)}" data-source="${channel}" onclick="toggleGenericBookmark(this)" aria-label="Bookmark video" title="Bookmark">
                                    <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            });

            container.innerHTML = html;
            syncBookmarkState();
            renderYoutubePagination(totalPages);
        }

        function renderYoutubePagination(totalPages) {
            const bottom = document.getElementById('youtube-pagination-bottom');
            if (!bottom || totalPages <= 1) {
                if (bottom) bottom.innerHTML = '';
                return;
            }

            const build = (container) => {
                container.innerHTML = '';
                const makeBtn = (text, page, isActive, isDisabled) => {
                    const btn = document.createElement('button');
                    btn.className = 'page-btn' + (isActive ? ' active' : '');
                    btn.textContent = text;
                    btn.disabled = isDisabled;
                    if (!isDisabled && !isActive) btn.onclick = () => { youtubePage = page; applyYoutubePagination(); window.scrollTo({top: 0, behavior: 'smooth'}); };
                    return btn;
                };
                const prevBtn = makeBtn('← Prev', Math.max(1, youtubePage - 1), false, youtubePage === 1);
                prevBtn.classList.add('nav', 'prev');
                container.appendChild(prevBtn);

                const nums = document.createElement('div');
                nums.className = 'page-numbers';
                const addPage = (p) => nums.appendChild(makeBtn(String(p), p, p === youtubePage, false));
                const addEllipsis = () => { const el = document.createElement('span'); el.className = 'page-ellipsis'; el.textContent = '...'; nums.appendChild(el); };

                if (totalPages <= 7) {
                    for (let i = 1; i <= totalPages; i++) addPage(i);
                } else {
                    addPage(1);
                    if (youtubePage > 3) addEllipsis();
                    for (let i = Math.max(2, youtubePage - 1); i <= Math.min(totalPages - 1, youtubePage + 1); i++) addPage(i);
                    if (youtubePage < totalPages - 2) addEllipsis();
                    addPage(totalPages);
                }
                container.appendChild(nums);

                const nextBtn = makeBtn('Next →', Math.min(totalPages, youtubePage + 1), false, youtubePage === totalPages);
                nextBtn.classList.add('nav', 'next');
                container.appendChild(nextBtn);
            };

            build(bottom);
        }

        // ==================== TWITTER TAB (helpers) ====================
        function getTweetAvatarColor(name) {
            const colors = ['#4a7fb5','#c96b6b','#5a9e6f','#c49a4b','#8b6baf','#4a9e9e','#d07a5a','#7aab5a'];
            let hash = 0;
            for (let i = 0; i < name.length; i++) hash = ((hash << 5) - hash) + name.charCodeAt(i);
            return colors[Math.abs(hash) % colors.length];
        }
        function getTweetBadges(title) {
            const badges = [];
            if (title.startsWith('\u201c') || title.startsWith('"')) badges.push('💬 Quote');
            else if (title.startsWith('RT @')) badges.push('🔄 Retweet');
            if (title.includes('🧵')) badges.push('🧵 Thread');
            return badges;
        }
        function toggleTweetExpand(btn) {
            const textEl = btn.previousElementSibling;
            const expanded = textEl.classList.toggle('expanded');
            btn.textContent = expanded ? 'Show less' : 'Show more';
        }
        function checkTweetOverflow(container) {
            container.querySelectorAll('.tweet-text').forEach(el => {
                const btn = el.nextElementSibling;
                if (btn && btn.classList.contains('tweet-expand-btn')) {
                    btn.style.display = el.scrollHeight > el.clientHeight ? 'block' : 'none';
                }
            });
        }

        // ==================== TWITTER TAB (functions) ====================
        function renderMainTwitter() {
            initTwitterPublisherDropdown();
            syncTwitterPresetButtons();
            filteredTwitter = [...TWITTER_ARTICLES];
            twitterPage = 1;
            applyTwitterPagination();
        }

        function filterTwitter() {
            const query = document.getElementById('search').value.toLowerCase().trim();
            filteredTwitter = TWITTER_ARTICLES.filter(t => {
                const matchesSearch = !query || (t.title + ' ' + t.source + ' ' + (t.publisher || '')).toLowerCase().includes(query);
                const pub = t.publisher || t.source;
                const matchesPublisher = selectedTwitterPublishers.size === 0 || selectedTwitterPublishers.has(pub);
                return matchesSearch && matchesPublisher;
            });
            twitterPage = 1;
            applyTwitterPagination();
            updateTwitterPublisherSummary();
        }

        function initTwitterPublisherDropdown() {
            const list = document.getElementById('twitter-dropdown-list');
            if (!list) return;
            list.innerHTML = '';
            TWITTER_PUBLISHERS.forEach(pub => {
                const item = document.createElement('div');
                item.className = 'dropdown-item';
                item.dataset.publisher = pub;
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.id = 'twpub-' + pub.replace(/\\s+/g, '-');
                cb.dataset.publisher = pub;
                cb.addEventListener('change', () => onTwitterPublisherChange(pub, cb.checked));
                const lbl = document.createElement('label');
                lbl.htmlFor = cb.id;
                lbl.textContent = pub;
                item.appendChild(cb);
                item.appendChild(lbl);
                item.addEventListener('click', (e) => {
                    if (e.target !== cb) {
                        cb.checked = !cb.checked;
                        onTwitterPublisherChange(pub, cb.checked);
                    }
                });
                list.appendChild(item);
            });
        }

        function toggleTwitterDropdown() {
            const dd = document.getElementById('twitter-publisher-dropdown');
            dd.classList.toggle('open');
            if (dd.classList.contains('open')) {
                document.getElementById('twitter-dropdown-search').focus();
            }
        }

        function filterTwitterPublisherList() {
            const query = document.getElementById('twitter-dropdown-search').value.toLowerCase();
            document.querySelectorAll('#twitter-dropdown-list .dropdown-item').forEach(item => {
                const pub = item.dataset.publisher.toLowerCase();
                item.classList.toggle('hidden', query && !pub.includes(query));
            });
        }

        function selectAllTwitterPublishers() {
            selectedTwitterPublishers.clear();
            syncTwitterCheckboxes();
            syncTwitterPresetButtons();
            updateTwitterPublisherSummary();
            filterTwitter();
        }

        function clearAllTwitterPublishers() {
            selectedTwitterPublishers.clear();
            syncTwitterCheckboxes();
            syncTwitterPresetButtons();
            updateTwitterPublisherSummary();
            filterTwitter();
        }

        function onTwitterPublisherChange(pub, checked) {
            if (checked) {
                selectedTwitterPublishers.add(pub);
            } else {
                selectedTwitterPublishers.delete(pub);
            }
            syncTwitterPresetButtons();
            updateTwitterPublisherSummary();
            filterTwitter();
        }

        function syncTwitterCheckboxes() {
            document.querySelectorAll('#twitter-dropdown-list input[type="checkbox"]').forEach(cb => {
                cb.checked = selectedTwitterPublishers.has(cb.dataset.publisher);
            });
        }

        function toggleTwitterPreset(name) {
            const pubs = TWITTER_PRESETS[name];
            if (!pubs) return;
            const allSelected = pubs.every(p => selectedTwitterPublishers.has(p));
            if (allSelected) {
                pubs.forEach(p => selectedTwitterPublishers.delete(p));
            } else {
                pubs.forEach(p => selectedTwitterPublishers.add(p));
            }
            syncTwitterCheckboxes();
            syncTwitterPresetButtons();
            updateTwitterPublisherSummary();
            filterTwitter();
        }

        function syncTwitterPresetButtons() {
            document.querySelectorAll('[data-twitter-preset]').forEach(btn => {
                const name = btn.dataset.twitterPreset;
                const pubs = TWITTER_PRESETS[name];
                if (!pubs) return;
                const selected = pubs.filter(p => selectedTwitterPublishers.has(p));
                if (selectedTwitterPublishers.size === 0) {
                    btn.classList.remove('active', 'partial');
                } else if (selected.length === pubs.length) {
                    btn.classList.add('active');
                    btn.classList.remove('partial');
                } else if (selected.length > 0) {
                    btn.classList.remove('active');
                    btn.classList.add('partial');
                } else {
                    btn.classList.remove('active', 'partial');
                }
            });
        }

        function updateTwitterPublisherSummary() {
            const el = document.getElementById('twitter-publisher-summary');
            const countLabel = document.getElementById('twitter-publisher-count-label');
            if (!el) return;
            const n = selectedTwitterPublishers.size;
            const total = TWITTER_PUBLISHERS.length;
            if (n === 0) {
                el.textContent = 'All publishers';
                if (countLabel) countLabel.textContent = '';
            } else if (n === 1) {
                el.textContent = [...selectedTwitterPublishers][0];
                if (countLabel) countLabel.textContent = '· 1 of ' + total + ' publishers';
            } else {
                el.textContent = n + ' publishers';
                if (countLabel) countLabel.textContent = '· ' + n + ' of ' + total + ' publishers';
            }
        }

        function closeTwitterDropdown() {
            const dd = document.getElementById('twitter-publisher-dropdown');
            if (dd) dd.classList.remove('open');
            const search = document.getElementById('twitter-dropdown-search');
            if (search) { search.value = ''; filterTwitterPublisherList(); }
        }

        function formatTwitterDate(isoStr) {
            if (!isoStr) return '';
            const date = new Date(isoStr);
            const now = new Date();
            const diffMs = now - date;
            const diffMin = Math.floor(diffMs / 60000);
            const diffHr = Math.floor(diffMs / 3600000);
            const diffDay = Math.floor(diffMs / 86400000);
            if (diffMin < 1) return 'Just now';
            if (diffMin < 60) return diffMin + 'm ago';
            if (diffHr < 24) return diffHr + 'h ago';
            if (diffDay === 1) return 'Yesterday';
            if (diffDay < 7) return diffDay + 'd ago';
            return date.toLocaleDateString();
        }

        function formatTwitterDateHeader(isoStr) {
            if (!isoStr) return 'Unknown Date';
            const date = new Date(isoStr);
            const now = new Date();
            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            const tweetDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
            const diffDays = Math.floor((today - tweetDay) / 86400000);
            if (diffDays === 0) return 'Today';
            if (diffDays === 1) return 'Yesterday';
            return date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
        }

        function applyTwitterPagination() {
            const totalPages = Math.max(1, Math.ceil(filteredTwitter.length / TWITTER_PAGE_SIZE));
            if (twitterPage > totalPages) twitterPage = totalPages;

            document.getElementById('twitter-visible-count').textContent = filteredTwitter.length;

            const start = (twitterPage - 1) * TWITTER_PAGE_SIZE;
            const end = start + TWITTER_PAGE_SIZE;
            const pageTweets = filteredTwitter.slice(start, end);

            const container = document.getElementById('twitter-container');
            if (pageTweets.length === 0) {
                container.innerHTML = '<div style="padding:40px 20px;text-align:center;color:var(--text-muted);font-size:14px;">No tweets found.</div>';
                renderTwitterPagination(totalPages);
                return;
            }

            let html = '';
            let currentDateHeader = '';

            pageTweets.forEach(t => {
                const dateHeader = formatTwitterDateHeader(t.date);
                if (dateHeader !== currentDateHeader) {
                    currentDateHeader = dateHeader;
                    html += `<h2 class="date-header">${dateHeader}</h2>`;
                }

                const title = escapeHtml(t.title);
                const source = escapeHtml(t.source);
                const link = escapeHtml(t.link);

                const publisher = escapeHtml(t.publisher || t.source);
                const avatarColor = getTweetAvatarColor(publisher);
                const initial = publisher.charAt(0).toUpperCase();
                const badges = getTweetBadges(t.title);
                const badgeHtml = badges.map(b => `<span class="tweet-badge">${b}</span>`).join('');
                html += `
                    <div class="tweet-item" data-publisher="${publisher}" data-url="${link}">
                        <div class="tweet-avatar" style="background:${avatarColor}">${initial}</div>
                        <div class="tweet-content">
                            <div class="tweet-header">
                                <span class="tweet-publisher">${publisher}</span>
                                ${t.date ? `<span class="tweet-time">${formatTwitterDate(t.date)}</span>` : ''}
                                <button class="bookmark-btn" data-url="${link}" data-title="${escapeForAttr(t.title)}" data-source="${source}" onclick="toggleGenericBookmark(this)" aria-label="Bookmark tweet" title="Bookmark">
                                    <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                                </button>
                            </div>
                            <div class="tweet-text"><a href="${link}" target="_blank" rel="noopener">${title}</a></div>
                            <button class="tweet-expand-btn" onclick="toggleTweetExpand(this)">Show more</button>
                            ${t.image ? `<div class="tweet-image"><img src="${escapeForAttr(t.image)}" alt="" loading="lazy" onerror="this.parentElement.style.display='none'"></div>` : ''}
                            <div class="tweet-footer">
                                ${badgeHtml}
                                <a href="${link}" target="_blank" rel="noopener" class="tweet-open-link">Open on X &rarr;</a>
                            </div>
                        </div>
                    </div>
                `;
            });

            container.innerHTML = html;
            checkTweetOverflow(container);
            syncBookmarkState();
            renderTwitterPagination(totalPages);
        }

        function renderTwitterPagination(totalPages) {
            const bottom = document.getElementById('twitter-pagination-bottom');
            if (!bottom || totalPages <= 1) {
                if (bottom) bottom.innerHTML = '';
                return;
            }

            const build = (container) => {
                container.innerHTML = '';
                const makeBtn = (text, page, isActive, isDisabled) => {
                    const btn = document.createElement('button');
                    btn.className = 'page-btn' + (isActive ? ' active' : '');
                    btn.textContent = text;
                    btn.disabled = isDisabled;
                    if (!isDisabled && !isActive) btn.onclick = () => { twitterPage = page; applyTwitterPagination(); window.scrollTo({top: 0, behavior: 'smooth'}); };
                    return btn;
                };
                const prevBtn = makeBtn('← Prev', Math.max(1, twitterPage - 1), false, twitterPage === 1);
                prevBtn.classList.add('nav', 'prev');
                container.appendChild(prevBtn);

                const nums = document.createElement('div');
                nums.className = 'page-numbers';
                const addPage = (p) => nums.appendChild(makeBtn(String(p), p, p === twitterPage, false));
                const addEllipsis = () => { const el = document.createElement('span'); el.className = 'page-ellipsis'; el.textContent = '...'; nums.appendChild(el); };

                if (totalPages <= 7) {
                    for (let i = 1; i <= totalPages; i++) addPage(i);
                } else {
                    addPage(1);
                    if (twitterPage > 3) addEllipsis();
                    for (let i = Math.max(2, twitterPage - 1); i <= Math.min(totalPages - 1, twitterPage + 1); i++) addPage(i);
                    if (twitterPage < totalPages - 2) addEllipsis();
                    addPage(totalPages);
                }
                container.appendChild(nums);

                const nextBtn = makeBtn('Next →', Math.min(totalPages, twitterPage + 1), false, twitterPage === totalPages);
                nextBtn.classList.add('nav', 'next');
                container.appendChild(nextBtn);
            };

            build(bottom);
        }

        // Update relative time for all timestamped elements
        function formatTimeAgo(el) {
            if (!el || !el.dataset.time) return;
            const diff = Math.floor((new Date() - new Date(el.dataset.time)) / 1000);
            let text;
            if (diff < 60) text = 'Updated just now';
            else if (diff < 3600) text = `Updated ${Math.floor(diff / 60)} min ago`;
            else if (diff < 86400) text = `Updated ${Math.floor(diff / 3600)} hr ago`;
            else text = `Updated ${Math.floor(diff / 86400)} day ago`;
            el.textContent = text;
        }
        function updateRelativeTime() {
            formatTimeAgo(document.getElementById('update-time'));
            formatTimeAgo(document.getElementById('reports-update-time'));
            formatTimeAgo(document.getElementById('youtube-update-time'));
            formatTimeAgo(document.getElementById('twitter-update-time'));
            formatTimeAgo(document.getElementById('ai-updated'));
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
"""
    # Apply template replacements
    html = html.replace("{source_count}", str(len(sources)))
    html = html.replace("{in_focus_count}", str(in_focus_count))
    html = html.replace("{today_iso}", today_iso)

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
        futures = {}
        for feed in feeds:
            if feed.get("feed", "").startswith("careratings:"):
                futures[executor.submit(fetch_careratings, feed)] = feed
            else:
                futures[executor.submit(fetch_feed, feed)] = feed

        for future in as_completed(futures):
            try:
                articles = future.result()
                all_articles.extend(articles)
            except Exception as e:
                feed_cfg = futures[future]
                print(f"  [EXCEPTION] {feed_cfg.get('name', '?')}: {e}")

    print(f"\nTotal articles collected: {len(all_articles)}")

    # Separate video and twitter articles from regular articles
    video_articles = [a for a in all_articles if a.get("category") == "Videos"]
    twitter_articles = [a for a in all_articles if a.get("category") == "Twitter"]
    regular_articles = [a for a in all_articles if a.get("category") not in ("Videos", "Twitter")]
    print(f"Videos: {len(video_articles)}, Twitter: {len(twitter_articles)}, Regular: {len(regular_articles)}")

    # Sort videos and twitter by date (newest first), no filtering/grouping needed
    video_articles.sort(key=get_sort_timestamp, reverse=True)
    twitter_articles.sort(key=get_sort_timestamp, reverse=True)

    # YouTube cache: persist last successful fetch so CI failures don't wipe the tab
    YOUTUBE_CACHE_FILE = os.path.join(SCRIPT_DIR, "static", "youtube_cache.json")

    def serialize_video(v):
        return {**v, "date": v["date"].isoformat() if v.get("date") else None}

    def deserialize_video(v):
        if v.get("date"):
            from datetime import timezone
            try:
                v["date"] = datetime.fromisoformat(v["date"])
                if v["date"].tzinfo is None:
                    v["date"] = v["date"].replace(tzinfo=IST_TZ)
            except Exception:
                v["date"] = None
        return v

    if video_articles:
        # Successful fetch — update cache
        try:
            with open(YOUTUBE_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump([serialize_video(v) for v in video_articles], f)
            print(f"YouTube cache updated ({len(video_articles)} videos)")
        except Exception as e:
            print(f"Warning: could not write YouTube cache: {e}")
    else:
        # Zero videos — YouTube likely blocked; load from cache
        print("WARNING: 0 YouTube videos fetched — loading from cache")
        try:
            with open(YOUTUBE_CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            video_articles = [deserialize_video(v) for v in cached]
            print(f"Loaded {len(video_articles)} videos from cache")
        except FileNotFoundError:
            print("No YouTube cache found — YouTube tab will be empty this run")
        except Exception as e:
            print(f"Warning: could not read YouTube cache: {e}")

    # Filter out twitter articles older than 5 days
    twitter_cutoff = datetime.now(IST_TZ) - timedelta(days=5)
    twitter_articles = [t for t in twitter_articles
                        if t.get("date") is None or
                        (t["date"] if t["date"].tzinfo else t["date"].replace(tzinfo=IST_TZ)) >= twitter_cutoff]

    # Remove duplicates based on URL only (not title - to preserve source diversity)
    seen_urls = set()
    unique_articles = []

    for article in regular_articles:
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

    # Filter out articles older than 5 days
    now = datetime.now(IST_TZ)
    cutoff_date = now - timedelta(days=5)
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

    generate_html(article_groups, video_articles, twitter_articles)
    export_articles_json(article_groups)

    print("\nDone!")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
