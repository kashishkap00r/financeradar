"""
Article processing utilities.

Pure data-processing functions for similarity detection, grouping,
text cleaning, and export. No feed fetching or HTML generation.
"""

import re
import json
import os
from datetime import datetime, timedelta, timezone
from html import unescape
from difflib import SequenceMatcher

# Get script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# IST timezone for consistent display
IST_TZ = timezone(timedelta(hours=5, minutes=30))


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
