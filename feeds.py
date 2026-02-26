"""
Feed loading and fetching utilities.

Handles feed configuration loading, date parsing, RSS/Atom feed fetching,
and CareRatings JSON API fetching.
"""

import json
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
import base64
from datetime import datetime, timedelta, timezone
import re
import ssl
import os
import subprocess
import html

from articles import IST_TZ

# Get script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FEEDS_FILE = os.path.join(SCRIPT_DIR, "feeds.json")

# TLS verification: use verified context by default, fallback for broken certs
SSL_CONTEXT = ssl.create_default_context()  # Verified (default)
SSL_CONTEXT_NOVERIFY = ssl.create_default_context()
SSL_CONTEXT_NOVERIFY.check_hostname = False
SSL_CONTEXT_NOVERIFY.verify_mode = ssl.CERT_NONE

INVIDIOUS_INSTANCES = ["inv.nadeko.net", "yewtu.be", "iv.datura.network"]
DC_NS = "http://purl.org/dc/elements/1.1/"
GOOGLE_RSS_PREFIX = "https://news.google.com/rss/"
GOOGLE_ARTICLE_PATH_RE = re.compile(r"/rss/articles/([^/?#]+)")
HTTP_URL_RE = re.compile(r"https?://[^\s\"'<>\\)]+", re.IGNORECASE)


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


THE_KEN_ALL_STORIES_URL = "https://the-ken.com/all-stories/"
THE_KEN_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q=site:the-ken.com&hl=en-IN&gl=IN&ceid=IN:en"


def _fetch_url_bytes(url, timeout=15):
    """Fetch raw bytes from URL with SSL and 403 curl fallback."""
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    req = urllib.request.Request(url, headers=req_headers)
    try:
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT) as response:
                return response.read()
        except ssl.SSLCertVerificationError:
            print(f"  [WARN] TLS verification failed for {url}, falling back to unverified")
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT_NOVERIFY) as response:
                return response.read()
    except urllib.error.HTTPError as e:
        if e.code != 403:
            raise
        for ua in ["FeedFetcher/1.0", "Mozilla/5.0 (compatible; RSS Reader)"]:
            result = subprocess.run(
                ["curl", "-sL", "-A", ua, url],
                capture_output=True,
                timeout=20,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        raise


def _parse_feed_content(content, feed_config):
    """Parse raw RSS/Atom XML content into article objects."""
    feed_name = feed_config["name"]
    source_url = feed_config["url"]
    articles = []

    # Parse XML
    root = ET.fromstring(content)
    feed_id = feed_config.get("id", "")

    def _ing_link_allowed(link):
        if feed_id != "ing-think-rss":
            return True
        link_l = (link or "").lower()
        return "/articles/" in link_l or "/snaps/" in link_l

    # Handle RSS 2.0 format
    items = root.findall(".//item")

    # Handle Atom format
    if not items:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//atom:entry", ns)

        for item in items:
            title = item.find("atom:title", ns)
            link = item.find("atom:link", ns)

            pub_date = item.find("atom:published", ns)
            if pub_date is None:
                pub_date = item.find("atom:updated", ns)

            summary = item.find("atom:summary", ns)
            if summary is None:
                summary = item.find("atom:content", ns)
            guid = item.find("atom:id", ns)

            link_href = link.get("href") if link is not None else ""
            if not _ing_link_allowed(link_href):
                continue

            article_data = {
                "title": title.text if title is not None and title.text else "No title",
                "link": link_href,
                "date": parse_date(pub_date.text if pub_date is not None else "", feed_name),
                "description": summary.text[:300] if summary is not None and summary.text else "",
                "source": feed_name,
                "source_url": source_url,
                "category": feed_config.get("category", "News"),
                "publisher": feed_config.get("publisher", ""),
                "feed_id": feed_config["id"],
                "guid": guid.text.strip() if guid is not None and guid.text else "",
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
        media_ns = "{http://search.yahoo.com/mrss/}"
        for item in items:
            title = item.find("title")
            link = item.find("link")
            pub_date = item.find("pubDate")
            if pub_date is None:
                pub_date = item.find(f"{{{DC_NS}}}date")
            if pub_date is None:
                pub_date = item.find("updated")
            if pub_date is None:
                pub_date = item.find("published")
            guid = item.find("guid")
            description = item.find("description")
            link_text = link.text if link is not None and link.text else ""
            if not _ing_link_allowed(link_text):
                continue

            # Extract image from media:thumbnail, media:content, or enclosure
            image_url = ""
            thumb = item.find(f"{media_ns}thumbnail")
            if thumb is not None:
                image_url = thumb.get("url", "")
            if not image_url:
                media_content = item.find(f"{media_ns}content")
                if media_content is not None and media_content.get("medium", "") == "image":
                    image_url = media_content.get("url", "")
            if not image_url:
                enclosure = item.find("enclosure")
                if enclosure is not None and enclosure.get("type", "").startswith("image/"):
                    image_url = enclosure.get("url", "")

            articles.append({
                "title": title.text if title is not None and title.text else "No title",
                "link": link_text,
                "date": parse_date(pub_date.text if pub_date is not None else "", feed_name),
                "description": description.text[:300] if description is not None and description.text else "",
                "source": feed_name,
                "source_url": source_url,
                "category": feed_config.get("category", "News"),
                "publisher": feed_config.get("publisher", ""),
                "image": image_url,
                "feed_id": feed_config["id"],
                "guid": guid.text.strip() if guid is not None and guid.text else "",
            })

    return articles


def _clean_html_text(raw):
    """Strip tags/entities and collapse whitespace."""
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _is_google_rss_feed(feed_url):
    return (feed_url or "").startswith(GOOGLE_RSS_PREFIX)


def _extract_first_non_google_url(raw_text):
    """Find first URL in text that is not a Google News link."""
    text = html.unescape(raw_text or "")
    for match in HTTP_URL_RE.findall(text):
        cleaned = match.rstrip(".,;:!?)\"'")
        lower = cleaned.lower()
        if "news.google.com/" in lower:
            continue
        return cleaned
    return ""


def _extract_google_article_token(link):
    """Get Google RSS article token from /rss/articles/<token> URL."""
    if not link:
        return ""
    parsed = urllib.parse.urlparse(link)
    match = GOOGLE_ARTICLE_PATH_RE.search(parsed.path)
    if not match:
        return ""
    return match.group(1).strip()


def _decode_google_article_token(token):
    """Best-effort decode of Google article token to original URL."""
    if not token:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        return ""
    padded = token + ("=" * (-len(token) % 4))
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception:
        return ""
    decoded_text = decoded.decode("utf-8", errors="ignore")
    return _extract_first_non_google_url(decoded_text)


def _normalize_google_source_suffix(title, publisher):
    """Strip trailing source suffix in Google RSS titles (e.g., ' - WSJ')."""
    cleaned = (title or "").strip()
    if not cleaned:
        return ""

    aliases = []
    normalized_publisher = (publisher or "").strip()
    if normalized_publisher:
        aliases.append(normalized_publisher)
    if normalized_publisher.upper() == "WSJ":
        aliases.extend(["The Wall Street Journal", "Wall Street Journal"])
    if normalized_publisher.lower() == "the economist":
        aliases.append("Economist")

    for alias in aliases:
        cleaned = re.sub(rf"\s*-\s*{re.escape(alias)}\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def _best_effort_resolve_google_link(link, guid="", description=""):
    """Try to resolve Google RSS redirect link to original publisher URL."""
    if not link:
        return ""
    if "news.google.com/rss/articles/" not in link:
        return link

    # Some feeds include direct links inside description HTML.
    direct_from_description = _extract_first_non_google_url(description)
    if direct_from_description:
        return direct_from_description

    # Rarely, original URL is present in query parameters.
    parsed = urllib.parse.urlparse(link)
    query_params = urllib.parse.parse_qs(parsed.query)
    for key in ("url", "u", "q"):
        candidate = (query_params.get(key) or [""])[0]
        if candidate.startswith("http://") or candidate.startswith("https://"):
            return candidate

    # Token decode fallback from article path and GUID.
    for token in (_extract_google_article_token(link), (guid or "").strip()):
        resolved = _decode_google_article_token(token)
        if resolved:
            return resolved

    return link


def _post_process_google_rss_articles(articles, feed_config):
    """Normalize Google RSS titles and resolve links when possible."""
    publisher = feed_config.get("publisher", "")
    resolved_count = 0
    attempted_count = 0
    for article in articles:
        article["title"] = _normalize_google_source_suffix(article.get("title", ""), publisher)
        original_link = article.get("link", "")
        if "news.google.com/rss/articles/" in original_link:
            attempted_count += 1
            resolved_link = _best_effort_resolve_google_link(
                original_link,
                guid=article.get("guid", ""),
                description=article.get("description", ""),
            )
            if resolved_link and resolved_link != original_link:
                article["link"] = resolved_link
                resolved_count += 1
    return {"attempted": attempted_count, "resolved": resolved_count}


def _normalize_the_ken_title(title):
    """Remove trailing source suffix from Google headlines."""
    title = (title or "").strip()
    title = re.sub(r"\s*-\s*The Ken\s*$", "", title, flags=re.IGNORECASE)
    return title.strip()


def _parse_the_ken_date(date_str):
    """Parse date strings seen in The Ken HTML/JSON-LD."""
    if not date_str:
        return None

    dt = parse_date(date_str, "The Ken")
    if dt:
        return dt

    normalized = date_str.strip().replace("Z", "+0000")
    normalized = re.sub(r"\s+", " ", normalized)

    fmts = (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%b %d, %Y",
    )
    for fmt in fmts:
        try:
            dt = datetime.strptime(normalized[:32], fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST_TZ)
            return dt
        except ValueError:
            continue
    return None


def _iter_json_nodes(node):
    """Yield nested dict nodes from JSON object/list."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_json_nodes(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_json_nodes(item)


def _extract_the_ken_html_articles(content, feed_config):
    """Extract The Ken stories from all-stories HTML/JSON-LD."""
    text = content.decode("utf-8", errors="replace")
    articles = []

    # First preference: JSON-LD often includes url/title/datePublished cleanly.
    jsonld_blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for block in jsonld_blocks:
        raw = html.unescape((block or "").strip())
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for node in _iter_json_nodes(payload):
            title = (node.get("headline") or node.get("name") or "").strip()
            if not title:
                continue

            link = node.get("url") or node.get("mainEntityOfPage")
            if isinstance(link, dict):
                link = link.get("@id") or link.get("url") or ""
            if isinstance(link, list):
                link = link[0] if link else ""
            link = (link or "").strip()
            if not link:
                continue
            link = urllib.parse.urljoin(feed_config["url"], link)
            if "the-ken.com/story/" not in link:
                continue

            date_str = (
                node.get("datePublished")
                or node.get("dateCreated")
                or node.get("uploadDate")
                or ""
            )
            desc = _clean_html_text(node.get("description", ""))
            articles.append({
                "title": _normalize_the_ken_title(title),
                "link": link,
                "date": _parse_the_ken_date(date_str),
                "description": desc[:300],
                "source": feed_config["name"],
                "source_url": feed_config["url"],
                "category": feed_config.get("category", "News"),
                "publisher": feed_config.get("publisher", ""),
                "feed_id": feed_config["id"],
            })

    # Secondary fallback: parse <article> cards with <a> + <time>.
    if articles:
        return articles

    cards = re.findall(r"<article\b[\s\S]*?</article>", text, flags=re.IGNORECASE)
    for card in cards:
        link_match = re.search(r'<a[^>]+href=["\']([^"\']+)["\']', card, flags=re.IGNORECASE)
        if not link_match:
            continue
        link = urllib.parse.urljoin(feed_config["url"], link_match.group(1).strip())
        if "the-ken.com/story/" not in link:
            continue

        title_match = re.search(r"<h[1-6][^>]*>(.*?)</h[1-6]>", card, flags=re.IGNORECASE | re.DOTALL)
        if title_match:
            title = _clean_html_text(title_match.group(1))
        else:
            anchor_match = re.search(r"<a[^>]*>(.*?)</a>", card, flags=re.IGNORECASE | re.DOTALL)
            title = _clean_html_text(anchor_match.group(1)) if anchor_match else ""
        if not title:
            continue

        dt = None
        datetime_match = re.search(r'datetime=["\']([^"\']+)["\']', card, flags=re.IGNORECASE)
        if datetime_match:
            dt = _parse_the_ken_date(datetime_match.group(1))
        if dt is None:
            time_match = re.search(r"<time[^>]*>(.*?)</time>", card, flags=re.IGNORECASE | re.DOTALL)
            if time_match:
                dt = _parse_the_ken_date(_clean_html_text(time_match.group(1)))

        desc_match = re.search(r"<p[^>]*>(.*?)</p>", card, flags=re.IGNORECASE | re.DOTALL)
        desc = _clean_html_text(desc_match.group(1)) if desc_match else ""

        articles.append({
            "title": _normalize_the_ken_title(title),
            "link": link,
            "date": dt,
            "description": desc[:300],
            "source": feed_config["name"],
            "source_url": feed_config["url"],
            "category": feed_config.get("category", "News"),
            "publisher": feed_config.get("publisher", ""),
            "feed_id": feed_config["id"],
        })

    return articles


def _dedupe_articles(articles):
    """Deduplicate article list by normalized URL/title."""
    seen = set()
    unique = []
    for article in articles:
        link_key = (article.get("link") or "").strip().rstrip("/").lower()
        title_key = _normalize_the_ken_title(article.get("title", "")).lower()
        key = link_key or title_key
        if not key or key in seen:
            continue
        seen.add(key)
        article["title"] = _normalize_the_ken_title(article.get("title", ""))
        unique.append(article)
    return unique


def fetch_feed(feed_config):
    """Fetch and parse a single RSS feed."""
    feed_url = feed_config["feed"]
    feed_name = feed_config["name"]
    articles = []
    google_stats = None

    try:
        content = _fetch_url_bytes(feed_url, timeout=15)
        if not content:
            raise Exception("No content received")

        articles = _parse_feed_content(content, feed_config)
        if _is_google_rss_feed(feed_url):
            google_stats = _post_process_google_rss_articles(articles, feed_config)

        print(f"  [OK] {feed_name}: {len(articles)} articles")
        if google_stats and google_stats["attempted"] > 0:
            print(f"    [INFO] Google link decode: {google_stats['resolved']}/{google_stats['attempted']} resolved")

    except Exception as e:
        print(f"  [FAIL] {feed_name}: {str(e)[:50]}")

    return articles


def fetch_the_ken(feed_config):
    """Fetch The Ken with resilient fallback: RSS -> HTML -> Google News RSS."""
    feed_name = feed_config["name"]
    attempts = []

    # 1) Direct site RSS
    try:
        content = _fetch_url_bytes(feed_config["feed"], timeout=20)
        articles = _dedupe_articles(_parse_feed_content(content, feed_config))
        if articles:
            print(f"  [OK] {feed_name}: {len(articles)} articles (direct RSS)")
            return articles
        attempts.append("direct RSS: 0 articles")
    except Exception as e:
        attempts.append(f"direct RSS failed ({str(e)[:50]})")

    # 2) HTML all-stories extraction (JSON-LD + card parsing)
    try:
        content = _fetch_url_bytes(THE_KEN_ALL_STORIES_URL, timeout=20)
        articles = _dedupe_articles(_extract_the_ken_html_articles(content, feed_config))
        if articles:
            print(f"  [OK] {feed_name}: {len(articles)} articles (HTML fallback)")
            return articles
        attempts.append("HTML fallback: 0 articles")
    except Exception as e:
        attempts.append(f"HTML fallback failed ({str(e)[:50]})")

    # 3) Google News RSS fallback for site:the-ken.com
    try:
        content = _fetch_url_bytes(THE_KEN_GOOGLE_NEWS_RSS, timeout=20)
        articles = _parse_feed_content(content, feed_config)
        normalized = []
        for article in articles:
            title = _normalize_the_ken_title(article.get("title", ""))
            if not title:
                continue
            article["title"] = title
            if len(title) < 8:
                continue
            normalized.append(article)
        normalized = _dedupe_articles(normalized)
        if normalized:
            print(f"  [OK] {feed_name}: {len(normalized)} articles (Google fallback)")
            return normalized
        attempts.append("Google fallback: 0 articles")
    except Exception as e:
        attempts.append(f"Google fallback failed ({str(e)[:50]})")

    # Auto-disable for this run if every route failed.
    print(f"  [WARN] {feed_name}: disabled for this run ({'; '.join(attempts)})")
    return []


def fetch_careratings(feed_config):
    """Fetch articles from CareRatings industry research JSON API."""
    feed_name = feed_config["name"]
    source_url = feed_config["url"]
    articles = []

    try:
        parts = feed_config["feed"].split(":")
        page_id = int(parts[1])
        section_id = int(parts[2]) if len(parts) > 2 else 5034
        year = datetime.now().year
        api_url = f"https://www.careratings.com/insightspagedata?PageId={page_id}&SectionId={section_id}&YearID={year}&MonthID=0"

        req = urllib.request.Request(api_url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json"
        })
        try:
            with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as response:
                data = json.loads(response.read())
        except ssl.SSLCertVerificationError:
            print(f"  [WARN] TLS verification failed for {api_url}, falling back to unverified")
            req = urllib.request.Request(api_url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/json"
            })
            with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT_NOVERIFY) as response:
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
