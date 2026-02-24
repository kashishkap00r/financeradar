"""
Custom scrapers for institutional research report sources.

Each function accepts a feed_config dict and returns a list of article dicts
compatible with the standard article format used by fetch_feed() / fetch_careratings().
"""

import json
import re
import urllib.request
import urllib.error
import subprocess
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser

from feeds import SSL_CONTEXT
from articles import IST_TZ


# Shared User-Agent header
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 30-day freshness guard — applied per-scraper to avoid fetching stale items
_FRESHNESS_CUTOFF = timedelta(days=30)

# Max articles per scraper invocation (prevents grabbing 1000+ historical PDFs)
_MAX_PER_SCRAPER = 30


def _is_fresh(dt):
    """Return True if date is within last 30 days or None (undated)."""
    if dt is None:
        return True
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt) <= _FRESHNESS_CUTOFF


def _fetch_url(url, accept="text/html", timeout=15):
    """Shared URL fetcher with urllib + curl fallback."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 403:
            for ua in ["FeedFetcher/1.0", "Mozilla/5.0 (compatible; RSS Reader)"]:
                result = subprocess.run(
                    ["curl", "-sL", "-A", ua, url],
                    capture_output=True, timeout=20
                )
                if result.returncode == 0 and result.stdout:
                    return result.stdout
        raise


def _make_article(title, link, date, description, feed_config):
    """Build a standard article dict from scraped data."""
    return {
        "title": title.strip() if title else "No title",
        "link": link,
        "date": date,
        "description": (description or "")[:300].strip(),
        "source": feed_config["name"],
        "source_url": feed_config["url"],
        "category": "Reports",
        "publisher": feed_config.get("publisher", ""),
        "region": feed_config.get("region", "Indian"),
    }


class _SimpleHTMLExtractor(HTMLParser):
    """Minimal HTML tag stripper."""
    def __init__(self):
        super().__init__()
        self._text = []

    def handle_data(self, data):
        self._text.append(data)

    def get_text(self):
        return " ".join(self._text).strip()


def _strip_html(html_str):
    """Strip HTML tags from a string."""
    if not html_str:
        return ""
    parser = _SimpleHTMLExtractor()
    try:
        parser.feed(html_str)
        return parser.get_text()
    except Exception:
        return re.sub(r'<[^>]+>', '', html_str).strip()


def _parse_date_flexible(date_str):
    """Try multiple date formats and return a tz-aware datetime or None."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in (
        "%b %d, %Y", "%B %d, %Y",       # Feb 23, 2026 / February 23, 2026
        "%d %b %Y", "%d %B %Y",          # 23 Feb 2026 / 23 February 2026
        "%d/%m/%Y", "%d-%m-%Y",          # 23/02/2026 / 23-02-2026
        "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", # ISO formats
        "%m/%d/%Y",                        # US format
    ):
        try:
            dt = datetime.strptime(date_str[:19], fmt)
            return dt.replace(tzinfo=IST_TZ)
        except ValueError:
            continue
    return None


# ── CRISIL ────────────────────────────────────────────────────────────

def fetch_crisil(feed_config):
    """Fetch research articles from CRISIL all-our-thinking page.

    CRISIL uses Adobe AEM CMS. Links contain /content/crisilcom/,
    /content/intelligence/, or /content/coalition-greenwich/ paths.
    Each card has: h2 title, date div, p description, 'Read More' link.
    """
    articles = []
    try:
        content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

        # Match AEM content links — the actual paths on CRISIL's site
        # Pattern: <a href="/content/..."> (Read More links)
        link_pattern = r'<a[^>]+href="(/content/(?:crisilcom|intelligence|coalition-greenwich)/[^"]+)"[^>]*>'
        links = re.findall(link_pattern, content, re.DOTALL)

        # Also try relative links under /en/home/what-we-think/ or /en/home/our-analysis/
        alt_pattern = r'<a[^>]+href="(/en/home/(?:what-we-think|our-analysis)/[^"]+)"[^>]*>'
        links.extend(re.findall(alt_pattern, content, re.DOTALL))

        # Extract titles from h2 elements
        titles = [_strip_html(m) for m in re.findall(r'<h2[^>]*>(.*?)</h2>', content, re.DOTALL)]

        # Extract dates — format like "Feb 23, 2026" or "February 23, 2026"
        date_pattern = r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}'
        dates = re.findall(date_pattern, content)

        # Extract descriptions from <p> elements near cards
        descriptions = [_strip_html(m) for m in re.findall(r'<p[^>]*>(.*?)</p>', content, re.DOTALL)
                        if len(_strip_html(m)) > 30]

        seen = set()
        for i, href in enumerate(links):
            if len(articles) >= _MAX_PER_SCRAPER:
                break
            if href in seen:
                continue
            seen.add(href)
            link = "https://www.crisil.com" + href

            title = titles[i] if i < len(titles) else ""
            if not title or len(title) < 10:
                continue

            dt = _parse_date_flexible(dates[i]) if i < len(dates) else None
            if not _is_fresh(dt):
                continue

            desc = descriptions[i] if i < len(descriptions) else ""
            articles.append(_make_article(title, link, dt, desc, feed_config))

        print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
    except Exception as e:
        print(f"  [FAIL] {feed_config['name']}: {str(e)[:50]}")
    return articles


# ── Baroda eTrade ─────────────────────────────────────────────────────

def fetch_baroda_etrade(feed_config):
    """Fetch research reports from Baroda eTrade (STR/SOR pages)."""
    articles = []
    try:
        content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

        # Look for PDF links in report tables
        pattern = r'<a[^>]+href="([^"]*\.pdf[^"]*)"[^>]*>(.*?)</a>'
        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)

        seen = set()
        for href, title_html in matches:
            if len(articles) >= _MAX_PER_SCRAPER:
                break
            title = _strip_html(title_html).strip()
            if not title:
                # Use filename as title
                title = href.split("/")[-1].replace(".pdf", "").replace("-", " ").replace("_", " ")
            if href in seen:
                continue
            seen.add(href)

            # Resolve relative links against correct domain
            if href.startswith("http"):
                link = href
            elif href.startswith("/"):
                link = "https://www.barodaetrade.com" + href
            else:
                link = feed_config["url"].rstrip("/") + "/" + href.lstrip("/")

            articles.append(_make_article(title, link, None, "", feed_config))

        # Try date extraction
        date_pattern = r'(\d{2}[/-]\d{2}[/-]\d{4})'
        dates = re.findall(date_pattern, content)
        for i, article in enumerate(articles):
            if i < len(dates):
                dt = _parse_date_flexible(dates[i])
                if dt and _is_fresh(dt):
                    article["date"] = dt
                elif dt and not _is_fresh(dt):
                    articles[i] = None  # mark for removal
        articles = [a for a in articles if a is not None]

        print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
    except Exception as e:
        print(f"  [FAIL] {feed_config['name']}: {str(e)[:50]}")
    return articles


# ── SBI Research ──────────────────────────────────────────────────────

def fetch_sbi_research(feed_config):
    """Fetch publications from SBI Research Desk."""
    articles = []
    try:
        content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

        # SBI lists PDFs — look for /documents/ paths and other PDF links
        pattern = r'<a[^>]+href="([^"]*\.pdf[^"]*)"[^>]*>(.*?)</a>'
        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)

        seen = set()
        for href, title_html in matches:
            if len(articles) >= _MAX_PER_SCRAPER:
                break
            title = _strip_html(title_html).strip()
            if not title or len(title) < 5 or href in seen:
                continue
            seen.add(href)
            # Use sbi.bank.in for relative links (the new correct domain)
            if href.startswith("http"):
                link = href
            else:
                link = "https://sbi.bank.in" + href
            articles.append(_make_article(title, link, None, "", feed_config))

        print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
    except Exception as e:
        print(f"  [FAIL] {feed_config['name']}: {str(e)[:50]}")
    return articles


# ── FICCI ─────────────────────────────────────────────────────────────

def fetch_ficci(feed_config):
    """Fetch FICCI Economic Wrap reports (may return 403)."""
    articles = []
    try:
        content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

        pattern = r'<a[^>]+href="([^"]*(?:\.pdf|\.asp|economy|economic|daily)[^"]*)"[^>]*>(.*?)</a>'
        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)

        seen = set()
        for href, title_html in matches:
            if len(articles) >= _MAX_PER_SCRAPER:
                break
            title = _strip_html(title_html).strip()
            if not title or len(title) < 8 or href in seen:
                continue
            seen.add(href)
            link = href if href.startswith("http") else "https://ficci.in/" + href.lstrip("/")
            articles.append(_make_article(title, link, None, "", feed_config))

        print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
    except Exception as e:
        print(f"  [FAIL] {feed_config['name']}: {str(e)[:50]}")
    return articles


# ── ICICI Bank Research ───────────────────────────────────────────────

def fetch_icici_research(feed_config):
    """Fetch PDFs from ICICI Bank research reports page.

    The page at icici.bank.in has ~2000 PDF links with /content/dam/icicibank/ paths.
    We match those and limit to 30 most recent (page is sorted by recency).
    """
    articles = []
    try:
        content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

        # Match PDF links under /content/dam/icicibank/
        pattern = r'<a[^>]+href="([^"]*content/dam/icicibank[^"]*\.pdf[^"]*)"[^>]*>(.*?)</a>'
        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)

        # Also try generic PDF links as fallback
        if not matches:
            pattern = r'<a[^>]+href="([^"]*\.pdf[^"]*)"[^>]*>(.*?)</a>'
            matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)

        seen = set()
        for href, title_html in matches:
            if len(articles) >= 30:
                break
            title = _strip_html(title_html).strip()
            if not title:
                # Extract title from filename
                fname = href.split("/")[-1].replace(".pdf", "")
                title = fname.replace("-", " ").replace("_", " ").title()
            if len(title) < 5 or href in seen:
                continue
            seen.add(href)

            if href.startswith("http"):
                link = href
            elif href.startswith("/"):
                link = "https://www.icici.bank.in" + href
            else:
                link = "https://www.icici.bank.in/" + href

            # Try to extract date from filename pattern like mms-24-feb-2026.pdf
            dt = None
            fname = href.split("/")[-1].lower()
            date_match = re.search(r'(\d{1,2})-?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)-?(\d{4})', fname)
            if date_match:
                try:
                    dt = datetime.strptime(f"{date_match.group(1)} {date_match.group(2)} {date_match.group(3)}", "%d %b %Y")
                    dt = dt.replace(tzinfo=IST_TZ)
                except ValueError:
                    pass

            if not _is_fresh(dt):
                continue

            articles.append(_make_article(title, link, dt, "", feed_config))

        print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
    except Exception as e:
        print(f"  [FAIL] {feed_config['name']}: {str(e)[:50]}")
    return articles


# ── HDFC Securities ───────────────────────────────────────────────────

def fetch_hdfc_sec(feed_config):
    """Fetch from HDFC Securities server-rendered research page.

    The page has report cards with:
    - Date text like "24 Feb 2026"
    - PDF links at hdfcsec.com/hsl.docs/...pdf
    - Title in link text
    """
    articles = []
    try:
        content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

        # Look for PDF links at hsl.docs path
        pattern = r'<a[^>]+href="((?:https?://(?:www\.)?hdfcsec\.com)?/hsl\.docs/[^"]*\.pdf[^"]*)"[^>]*>(.*?)</a>'
        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)

        # Fallback: any PDF or research links
        if not matches:
            pattern = r'<a[^>]+href="([^"]*(?:\.pdf|/research/|/report)[^"]*)"[^>]*>(.*?)</a>'
            matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)

        # Extract dates near each card
        date_pattern = r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})'
        dates = re.findall(date_pattern, content, re.IGNORECASE)

        seen = set()
        for i, (href, title_html) in enumerate(matches):
            title = _strip_html(title_html).strip()
            if not title or len(title) < 8 or href in seen:
                continue
            seen.add(href)

            if href.startswith("http"):
                link = href
            else:
                link = "https://www.hdfcsec.com" + href

            dt = _parse_date_flexible(dates[i]) if i < len(dates) else None
            if not _is_fresh(dt):
                continue

            articles.append(_make_article(title, link, dt, "", feed_config))

        print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
    except Exception as e:
        print(f"  [FAIL] {feed_config['name']}: {str(e)[:50]}")
    return articles


# ── Axis Direct ───────────────────────────────────────────────────────

def fetch_axis_direct(feed_config):
    """Fetch research reports from Axis Direct."""
    articles = []
    try:
        content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

        pattern = r'<a[^>]+href="([^"]*(?:research|report|pdf|analysis)[^"]*)"[^>]*>(.*?)</a>'
        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)

        seen = set()
        for href, title_html in matches:
            title = _strip_html(title_html).strip()
            if not title or len(title) < 8 or href in seen:
                continue
            seen.add(href)
            link = href if href.startswith("http") else "https://simplehai.axisdirect.in" + href
            articles.append(_make_article(title, link, None, "", feed_config))

        print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
    except Exception as e:
        print(f"  [FAIL] {feed_config['name']}: {str(e)[:50]}")
    return articles


# ── Goldman Sachs ─────────────────────────────────────────────────────

def fetch_goldman_sachs(feed_config):
    """Fetch from Goldman Sachs insights JSON API.

    GS has a JSON feed at /feeds/insights.json with full article data:
    title, path, cmsPageProps.publishDate, description, cmsPageProps.pageType.
    """
    articles = []
    try:
        api_url = "https://www.goldmansachs.com/feeds/insights.json"
        raw = _fetch_url(api_url, accept="application/json", timeout=20)
        data = json.loads(raw.decode("utf-8", errors="replace"))

        items = data if isinstance(data, list) else data.get("items", data.get("results", []))
        if not isinstance(items, list):
            items = []

        for item in items:
            if len(articles) >= 30:
                break

            # Filter to articles and reports only
            cms = item.get("cmsPageProps", {})
            page_type = (cms.get("pageType") or "").lower()
            if page_type and page_type not in ("article", "report", ""):
                continue

            title = item.get("title", "").strip()
            path = item.get("path", "")
            if not title or not path:
                continue

            link = path if path.startswith("http") else "https://www.goldmansachs.com" + path

            # Parse date
            dt = None
            date_str = cms.get("publishDate") or item.get("publishDate") or item.get("date") or ""
            if date_str:
                dt = _parse_date_flexible(date_str)
                # Also try ISO with timezone
                if not dt:
                    try:
                        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

            if not _is_fresh(dt):
                continue

            desc = item.get("description", "")
            topic = cms.get("primaryTopic", "")
            if topic and desc:
                desc = f"[{topic}] {desc}"

            articles.append(_make_article(title, link, dt, desc, feed_config))

        # Fallback to HTML scraping if JSON API fails/returns empty
        if not articles:
            content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")
            pattern = r'<a[^>]+href="(https://www\.goldmansachs\.com/insights/[^"]+)"[^>]*>(.*?)</a>'
            for href, title_html in re.findall(pattern, content, re.DOTALL):
                title = _strip_html(title_html).strip()
                if title and len(title) >= 10:
                    articles.append(_make_article(title, href, None, "", feed_config))

        print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
    except Exception as e:
        print(f"  [FAIL] {feed_config['name']}: {str(e)[:50]}")
    return articles


# ── CreditSights ─────────────────────────────────────────────────────

def fetch_creditsights(feed_config):
    """Fetch from CreditSights blog-research page.

    Real URL is know.creditsights.com/blog-research/.
    Links use /insights/ path pattern.
    """
    articles = []
    try:
        content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

        # Match links to insights articles
        pattern = r'<a[^>]+href="(https://know\.creditsights\.com/insights/[^"]+)"[^>]*>(.*?)</a>'
        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)

        # Fallback: relative /insights/ links
        if not matches:
            pattern = r'<a[^>]+href="(/insights/[^"]+)"[^>]*>(.*?)</a>'
            matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)

        # Also try blog/research paths as secondary fallback
        if not matches:
            pattern = r'<a[^>]+href="((?:https://know\.creditsights\.com)?/(?:blog|research|insights)/[^"]+)"[^>]*>(.*?)</a>'
            matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)

        # Extract dates
        date_pattern = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}'
        dates = re.findall(date_pattern, content)

        seen = set()
        for i, (href, title_html) in enumerate(matches):
            title = _strip_html(title_html).strip()
            if not title or len(title) < 10 or href in seen:
                continue
            seen.add(href)

            if href.startswith("http"):
                link = href
            else:
                link = "https://know.creditsights.com" + href

            dt = _parse_date_flexible(dates[i]) if i < len(dates) else None
            if not _is_fresh(dt):
                continue

            articles.append(_make_article(title, link, dt, "", feed_config))

        print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
    except Exception as e:
        print(f"  [FAIL] {feed_config['name']}: {str(e)[:50]}")
    return articles


# ── JPMorgan ──────────────────────────────────────────────────────────

def fetch_jpmorgan(feed_config):
    """Fetch from JPMorgan insights/research page.

    Server-rendered cards with jpmorgan.com/insights/ links.
    """
    articles = []
    try:
        content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

        # Try JSON-LD first
        json_match = re.search(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', content, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") in ("Article", "NewsArticle", "Report", "WebPage"):
                        title = item.get("headline") or item.get("name", "")
                        link = item.get("url", "")
                        if title and link:
                            dt = None
                            date_str = item.get("datePublished") or item.get("dateModified") or ""
                            if date_str:
                                try:
                                    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                                except (ValueError, TypeError):
                                    dt = _parse_date_flexible(date_str)
                            if _is_fresh(dt):
                                articles.append(_make_article(title, link, dt, item.get("description", ""), feed_config))
            except json.JSONDecodeError:
                pass

        # Fallback: scrape insight links
        if not articles:
            pattern = r'<a[^>]+href="(https://www\.jpmorgan\.com/(?:insights|research)/[^"]+)"[^>]*>(.*?)</a>'
            seen = set()
            for href, title_html in re.findall(pattern, content, re.DOTALL):
                title = _strip_html(title_html).strip()
                if title and len(title) >= 10 and href not in seen:
                    seen.add(href)
                    articles.append(_make_article(title, href, None, "", feed_config))

        print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
    except Exception as e:
        print(f"  [FAIL] {feed_config['name']}: {str(e)[:50]}")
    return articles


# ── Dispatcher ────────────────────────────────────────────────────────

# Maps feed prefix → fetcher function
REPORT_FETCHERS = {
    "crisil:": fetch_crisil,
    "baroda:": fetch_baroda_etrade,
    "sbi:": fetch_sbi_research,
    "ficci:": fetch_ficci,
    "icici:": fetch_icici_research,
    "hdfcsec:": fetch_hdfc_sec,
    "axis:": fetch_axis_direct,
    "gs:": fetch_goldman_sachs,
    "creditsights:": fetch_creditsights,
    "jpmorgan:": fetch_jpmorgan,
}


def get_report_fetcher(feed_field):
    """Return the appropriate fetcher function for a feed field, or None."""
    for prefix, fetcher in REPORT_FETCHERS.items():
        if feed_field.startswith(prefix):
            return fetcher
    return None
