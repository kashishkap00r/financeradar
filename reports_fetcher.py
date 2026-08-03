"""
Custom scrapers for institutional research report sources.

Each function accepts a feed_config dict and returns a list of article dicts
compatible with the standard article format used by fetch_feed() / fetch_careratings().
"""

import functools
import html
import json
import os
import re
import ssl
import socket
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
import subprocess
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from articles import IST_TZ
from config import (
    DEFAULT_USER_AGENT,
    FEED_CURL_TIMEOUT,
    SCRAPER_MAX_ARTICLES,
    SCRAPER_FRESHNESS_CUTOFF,
    SCRAPER_FETCH_TIMEOUT,
    SCRAPER_RETRY_ATTEMPTS,
    SCRAPER_RETRY_BACKOFF,
    SCRAPER_TIMEOUT_OVERRIDES,
    SCRAPER_RETRY_OVERRIDES,
    SSL_CONTEXT,
    SSL_CONTEXT_NOVERIFY,
)


UA = DEFAULT_USER_AGENT

# 30-day freshness guard — applied per-scraper to avoid fetching stale items
_FRESHNESS_CUTOFF = SCRAPER_FRESHNESS_CUTOFF

# Max articles per scraper invocation (prevents grabbing 1000+ historical PDFs)
_MAX_PER_SCRAPER = SCRAPER_MAX_ARTICLES


def _is_fresh(dt):
    """Return True if date is within last 30 days or None (undated)."""
    if dt is None:
        return True
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt) <= _FRESHNESS_CUTOFF


def scraper(func):
    """Decorator for report scrapers — handles errors, freshness, limits, logging."""
    @functools.wraps(func)
    def wrapper(feed_config):
        try:
            articles = func(feed_config)
            # Filter out stale articles
            articles = [a for a in articles if _is_fresh(a.get("date"))]
            # Enforce per-scraper limit
            articles = articles[:_MAX_PER_SCRAPER]
            print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
            return articles
        except Exception as e:
            print(f"  [FAIL] {feed_config['name']}: {str(e)[:120]}")
            return []
    return wrapper


def _fetch_url(url, accept="text/html", timeout=None, feed_config=None):
    """Shared URL fetcher with urllib + curl fallback and retry logic."""
    feed_id = (feed_config or {}).get("id", "")
    effective_timeout = timeout if timeout is not None else SCRAPER_FETCH_TIMEOUT
    if feed_id in SCRAPER_TIMEOUT_OVERRIDES:
        effective_timeout = SCRAPER_TIMEOUT_OVERRIDES[feed_id]

    max_retries = SCRAPER_RETRY_OVERRIDES.get(feed_id, SCRAPER_RETRY_ATTEMPTS)

    for attempt in range(max_retries + 1):
        try:
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": UA,
                    "Accept": accept,
                    "Accept-Language": "en-US,en;q=0.9",
                })
                try:
                    with urllib.request.urlopen(req, timeout=effective_timeout, context=SSL_CONTEXT) as resp:
                        return resp.read()
                except ssl.SSLCertVerificationError:
                    print(f"  [WARN] TLS verification failed for {url}, falling back to unverified")
                    req = urllib.request.Request(url, headers={
                        "User-Agent": UA,
                        "Accept": accept,
                        "Accept-Language": "en-US,en;q=0.9",
                    })
                    with urllib.request.urlopen(req, timeout=effective_timeout, context=SSL_CONTEXT_NOVERIFY) as resp:
                        return resp.read()
            except urllib.error.HTTPError as e:
                if e.code == 403:
                    for ua in ["FeedFetcher/1.0", "Mozilla/5.0 (compatible; RSS Reader)"]:
                        result = subprocess.run(
                            ["curl", "-sL", "-A", ua, url],
                            capture_output=True, timeout=FEED_CURL_TIMEOUT
                        )
                        if result.returncode == 0 and result.stdout:
                            return result.stdout
                raise
        except (urllib.error.URLError, socket.timeout) as e:
            # Don't retry HTTPError (subclass of URLError) — only transient network errors
            if isinstance(e, urllib.error.HTTPError):
                raise
            if attempt < max_retries:
                print(f"  [WARN] Retry {attempt + 1}/{max_retries} for {url}: {str(e)[:80]}")
                time.sleep(SCRAPER_RETRY_BACKOFF)
            else:
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
        "category": feed_config.get("category", "Reports"),
        "publisher": feed_config.get("publisher", ""),
        "region": feed_config.get("region", "Indian"),
        "feed_id": feed_config.get("id", ""),
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


# ── CRISIL Ratings (Press Releases) ───────────────────────────────────

@scraper
def fetch_crisil_ratings(feed_config):
    """Fetch press releases from CRISIL Ratings newsroom.

    crisilratings.com (AEM CMS) — different site from crisil.com research.
    Each card has: date span, linked title, description paragraph.
    """
    articles = []
    content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

    # Split on content-wrap to isolate individual press release cards
    cards = re.split(r'class="content-wrap"', content)

    for card in cards[1:]:  # skip preamble before first card
        # Date: <span class="pressreleases-analytics-cta-title">February 24, 2026</span>
        date_m = re.search(r'pressreleases-analytics-cta-title">\s*(.*?)\s*</span>', card, re.DOTALL)
        dt = _parse_date_flexible(date_m.group(1)) if date_m else None
        if not _is_fresh(dt):
            continue

        # Link: <a class="pressreleases-analytics-cta" href="/content/crisilratings/...">
        link_m = re.search(r'pressreleases-analytics-cta"\s+href="([^"]+)"', card)
        if not link_m:
            continue
        link = "https://www.crisilratings.com" + link_m.group(1)

        # Title: <p class="pdf-file-link">...</p>
        title_m = re.search(r'pdf-file-link"[^>]*>(.*?)</p>', card, re.DOTALL)
        title = _strip_html(title_m.group(1)).strip() if title_m else ""
        if not title or len(title) < 10:
            continue

        # Description: <div class="description"><p>...</p></div>
        desc_m = re.search(r'class="description">\s*<p>(.*?)</p>', card, re.DOTALL)
        desc = _strip_html(desc_m.group(1)).strip() if desc_m else ""

        articles.append(_make_article(title, link, dt, desc, feed_config))

    return articles


# ── CRISIL Research (All Our Thinking) ────────────────────────────────

@scraper
def fetch_crisil_research(feed_config):
    """Fetch research articles from CRISIL 'All Our Thinking' page.

    crisil.com (AEM CMS) — different site from crisilratings.com press releases.
    Cards use crisil-card-data containers with date, title, description, and link.
    """
    articles = []
    content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

    # Split on card-data containers to isolate individual cards
    cards = re.split(r'class="crisil-card-data"', content)

    for card in cards[1:]:  # skip preamble before first card
        # Date: <span class="card-publish-date">Feb 24, 2026</span>
        date_m = re.search(r'card-publish-date">\s*(.*?)\s*</span>', card, re.DOTALL)
        dt = _parse_date_flexible(date_m.group(1)) if date_m else None
        if not _is_fresh(dt):
            continue

        # Title: <h2 class="card-title">...</h2>
        title_m = re.search(r'card-title">\s*(.*?)\s*</h2>', card, re.DOTALL)
        title = _strip_html(title_m.group(1)).strip() if title_m else ""
        if not title or len(title) < 10:
            continue

        # Link: <a href="/content/..." class="card-redirection-link ...">
        link_m = re.search(r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*card-redirection-link', card)
        if not link_m:
            continue
        link = "https://www.crisil.com" + link_m.group(1)

        # Description: <p class="card-description">...</p>
        desc_m = re.search(r'card-description">\s*(.*?)\s*</p>', card, re.DOTALL)
        desc = _strip_html(desc_m.group(1)).strip() if desc_m else ""

        articles.append(_make_article(title, link, dt, desc, feed_config))

    return articles


# ── Baroda eTrade ─────────────────────────────────────────────────────

@scraper
def fetch_baroda_etrade(feed_config):
    """Fetch research reports from Baroda eTrade (STR/SOR pages)."""
    articles = []
    content = _fetch_url(feed_config["url"], feed_config=feed_config).decode("utf-8", errors="replace")

    # Extract parallel lists from the consistent HTML structure
    dates_raw = re.findall(r'<div\s+class="dateNtime1">\s*(.*?)\s*</div>', content, re.IGNORECASE)
    titles_raw = re.findall(r'<h4\s+class="newsheading">\s*([\s\S]*?)\s*<p[\s>]', content, re.IGNORECASE)
    descriptions_raw = re.findall(
        r'<span\s+id="ctl00_ContentPlaceHolder1_repeatdata_ctrl\d+_lblcaption">\s*(.*?)\s*</span>',
        content, re.DOTALL | re.IGNORECASE,
    )
    links_raw = re.findall(r'<a[^>]+href="(/Reports/[^"]+\.pdf[^"]*)"', content, re.IGNORECASE)

    # Zip parallel lists (use shortest length for safety)
    count = min(len(dates_raw), len(titles_raw), len(links_raw))

    seen = set()
    for i in range(count):
        # Parse date (DD-Mon-YY format, e.g. "20-Feb-26")
        try:
            dt = datetime.strptime(dates_raw[i].strip(), "%d-%b-%y")
            dt = dt.replace(tzinfo=IST_TZ)
        except ValueError:
            dt = None

        if dt and not _is_fresh(dt):
            continue

        href = links_raw[i]
        if href in seen:
            continue
        seen.add(href)

        title = _strip_html(titles_raw[i]).strip()
        if not title:
            title = href.split("/")[-1].replace(".pdf", "").replace("-", " ").replace("_", " ")

        link = "https://www.barodaetrade.com" + href
        description = _strip_html(descriptions_raw[i]).strip() if i < len(descriptions_raw) else ""

        articles.append(_make_article(title, link, dt, description, feed_config))

    return articles


# ── SBI Research ──────────────────────────────────────────────────────

@scraper
def fetch_sbi_research(feed_config):
    """Fetch Ecowrap economic research papers from SBI Research Desk."""
    articles = []
    content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

    # Extract only the Ecowrap section (after the Ecowrap </h3> until next <h3)
    eco_match = re.search(
        r'>Ecowrap</h3>\s*(.*?)(?=<h3\b|$)',
        content, re.DOTALL | re.IGNORECASE
    )
    if not eco_match:
        print(f"  [WARN] {feed_config['name']}: Ecowrap section not found")
        return articles

    ecowrap_html = eco_match.group(1)

    # Find all links within the Ecowrap section pointing to /documents/ PDFs
    link_pattern = r'<a[^>]+href="(/documents/[^"]+)"[^>]*>(.*?)</a>'
    matches = re.findall(link_pattern, ecowrap_html, re.DOTALL)

    # Pattern: DD.MM.YYYY:"Title" or DD.MM.YYYY: "Title"
    date_title_re = re.compile(r'(\d{2}\.\d{2}\.\d{4})\s*:\s*(.+)$')

    seen = set()
    for href, title_html in matches:
        if href in seen:
            continue
        seen.add(href)

        text = _strip_html(title_html).strip()
        m = date_title_re.search(text)
        if not m:
            continue  # Every Ecowrap entry has DD.MM.YYYY: format
        date_str = m.group(1)
        title = m.group(2).strip().strip('"\u201c\u201d').strip()
        try:
            dt = datetime.strptime(date_str, "%d.%m.%Y").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue  # Unparseable date — skip

        if not title or len(title) < 5:
            continue
        if not _is_fresh(dt):
            continue

        link = "https://sbi.bank.in" + href
        articles.append(_make_article(title, link, dt, "", feed_config))

    return articles


# ── FICCI ─────────────────────────────────────────────────────────────

@scraper
def fetch_ficci(feed_config):
    """Fetch FICCI Daily Economic News Wrap PDF reports."""
    articles = []
    content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

    dates = [_strip_html(m).strip() for m in re.findall(r'<time[^>]*>(.*?)</time>', content, re.DOTALL)]
    pdfs = re.findall(r'href="(https://ficci\.in/public/storage/sector/Report/[^"]+\.pdf)"', content)

    for date_str, pdf_url in zip(dates, pdfs):
        try:
            pub_date = datetime.strptime(date_str.strip(), "%b %d, %Y")
        except ValueError:
            pub_date = None
        if not _is_fresh(pub_date):
            continue
        articles.append(_make_article(
            "Economy \u2014 Daily News Wrap", pdf_url, pub_date, "", feed_config
        ))

    return articles


# ── CEEW (Council on Energy, Environment and Water) ───────────────────

@scraper
def fetch_ceew(feed_config):
    """Fetch CEEW publications from the site's native RSS feed.

    ceew.in/publications is behind a Cloudflare JS challenge (403), but
    ceew.in/rss.xml (a mixed frontpage feed) returns 200. We keep only
    /publications/ links and drop event/bio pages.
    """
    articles = []
    content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

    for block in re.findall(r"<item>(.*?)</item>", content, re.DOTALL):
        link_m = re.search(r"<link>(.*?)</link>", block, re.DOTALL)
        if not link_m:
            continue
        link = html.unescape(link_m.group(1).strip())
        if "/publications/" not in link:          # publications only
            continue

        title_m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, re.DOTALL)
        title = html.unescape(_strip_html(title_m.group(1)).strip()) if title_m else ""
        if not title:
            continue

        date_m = re.search(r"<pubDate>(.*?)</pubDate>", block, re.DOTALL)
        dt = None
        if date_m:
            try:
                dt = parsedate_to_datetime(date_m.group(1).strip())
            except (TypeError, ValueError):
                dt = None

        desc_m = re.search(r"<description>(.*?)</description>", block, re.DOTALL)
        desc = _strip_html(html.unescape(desc_m.group(1))).strip() if desc_m else ""

        articles.append(_make_article(title, link, dt, desc, feed_config))

    return articles


# ── ICICI Bank Research ───────────────────────────────────────────────

@scraper
def fetch_icici_research(feed_config):
    """Fetch reports from ICICI Bank research page via embedded JSON.

    The page embeds ~2000 reports as HTML-entity-encoded JSON inside a hidden
    div with id="ergFilter". Each item has title, description, datetime, and
    pdfLink fields. We decode the JSON and extract fresh reports.
    """
    articles = []
    content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

    # Extract JSON from hidden div: <div class="hide" id="ergFilter">[...]</div>
    m = re.search(r'id="ergFilter"[^>]*>\s*(\[.*?\])\s*</div>', content, re.DOTALL)
    if not m:
        print(f"  [WARN] {feed_config['name']}: ergFilter div not found")
        return articles

    raw_json = html.unescape(m.group(1))
    items = json.loads(raw_json)

    for item in items:
        pdf_link = (item.get("pdfLink") or "").strip()
        if not pdf_link:
            continue

        title = (item.get("title") or "").strip()
        if not title or len(title) < 5:
            continue

        # Parse datetime: "24 Feb 26 06:30 PM"
        dt = None
        dt_str = (item.get("datetime") or "").strip()
        if dt_str:
            try:
                dt = datetime.strptime(dt_str, "%d %b %y %I:%M %p")
                dt = dt.replace(tzinfo=IST_TZ)
            except ValueError:
                pass

        if not _is_fresh(dt):
            continue

        link = "https://www.icici.bank.in" + pdf_link if pdf_link.startswith("/") else pdf_link
        desc = (item.get("description") or "").strip()[:300]

        articles.append(_make_article(title, link, dt, desc, feed_config))

    return articles


# ── HDFC Securities ───────────────────────────────────────────────────

@scraper
def fetch_hdfc_sec(feed_config):
    """Fetch from HDFC Securities research via CMS JSON API.

    The reports page loads data client-side from GetNonCallResearch API.
    We fetch two buckets: Periodic Reports (1912) and Institutional Reports (1913).
    """
    articles = []
    base = "https://www.hdfcsec.com"
    buckets = [1912, 1913]  # Periodic, Institutional

    for bucket_id in buckets:
        url = (f"{base}/api/cmsapi/GetNonCallResearch?"
               f"schemeId=&compCode=&bucketId={bucket_id}"
               f"&pageNo=1&pageSize={_MAX_PER_SCRAPER}&fromDate=&toDate=")
        raw = _fetch_url(url, accept="application/json").decode("utf-8", errors="replace")

        # API returns double-encoded JSON (string within string) — decode twice
        cleaned = raw.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
        data = json.loads(json.loads(cleaned))

        # data[0].data = articles, data[2].data = predicates (Title, Summary, UploadPdf)
        items = data[0].get("data", [])
        predicates = data[2].get("data", []) if len(data) > 2 else []

        # Build predicate lookup: {article_id: {predicate: value}}
        pred_map = {}
        for p in predicates:
            aid = p.get("ARTICLE_ID", "")
            pred = p.get("PREDICATE", "")
            val = p.get("OBJECT1", "")
            if aid and pred:
                pred_map.setdefault(aid, {})[pred] = val

        for item in items:
            if not item:
                continue

            aid = item.get("ARTICLE_ID", "")
            preds = pred_map.get(aid, {})

            title = (item.get("TITLE") or preds.get("Title") or "").strip()
            if not title or len(title) < 5:
                continue

            # PDF filename is in predicate UploadPdf
            pdf = (preds.get("UploadPdf") or "").strip()
            if not pdf:
                continue

            # Unescape HTML entities in filename (e.g. &amp; → &)
            link = f"{base}/hsl.docs/{html.unescape(pdf)}"

            # Parse date: "24-02-2026 17:24:29"
            dt = None
            dt_str = (item.get("PUBLISHED_ON") or "").strip()
            if dt_str:
                try:
                    dt = datetime.strptime(dt_str, "%d-%m-%Y %H:%M:%S")
                    dt = dt.replace(tzinfo=IST_TZ)
                except ValueError:
                    pass

            if not _is_fresh(dt):
                continue

            # Description from predicate Summary (URL-encoded)
            raw_summary = preds.get("Summary", "")
            try:
                desc = _strip_html(urllib.parse.unquote(raw_summary)).strip()
            except Exception:
                desc = raw_summary.strip()

            articles.append(_make_article(title, link, dt, desc, feed_config))

    return articles


# ── Axis Direct ───────────────────────────────────────────────────────

@scraper
def fetch_axis_direct(feed_config):
    """Fetch research reports from Axis Direct fundamental reports page.

    The page renders report cards as <li> elements containing:
      - <h5> with the report title
      - <p>  with the date (e.g. "24 Feb 2026")
      - description text
      - <a href="/app/index.php/insights/reports/downloadReport/file/...">
    We parse each card by anchoring on the downloadReport links, then
    extracting the preceding <h5> title and date <p>.
    """
    BASE = "https://simplehai.axisdirect.in"
    articles = []
    content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

    # Split on each <li to isolate report cards.
    # The report list lives inside a <ul> with each card in its own <li>.
    cards = re.split(r'<li\b', content)

    for card in cards:
        # Must have a downloadReport link to be a real report card
        dl_match = re.search(
            r'href="(/app/index\.php/insights/reports/downloadReport/file/[^"]+)"',
            card
        )
        if not dl_match:
            continue

        link = BASE + dl_match.group(1)

        # Title from <h5> tag
        h5 = re.search(r'<h5[^>]*>(.*?)</h5>', card, re.DOTALL)
        title = _strip_html(html.unescape(h5.group(1))).strip() if h5 else ""
        if not title or len(title) < 5:
            continue

        # Date from the first <p> after the title header div (format: "24 Feb 2026")
        date_match = re.search(r'<p[^>]*>\s*(\d{1,2}\s+\w+\s+\d{4})\s*</p>', card)
        dt = _parse_date_flexible(date_match.group(1)) if date_match else None
        if not _is_fresh(dt):
            continue

        # Description lives in <div class="reports-video"> inside panel-body
        desc = ""
        desc_block = re.search(
            r'<div\s+class="reports-video">\s*(.*?)\s*</div>',
            card, re.DOTALL
        )
        if desc_block:
            raw = _strip_html(html.unescape(desc_block.group(1))).strip()
            # Remove "Stocks covered (N)" prefix noise
            raw = re.sub(r'^Stocks covered\s*\(\d+\)\s*', '', raw).strip()
            desc = raw

        articles.append(_make_article(title, link, dt, desc, feed_config))

    return articles


# ── Goldman Sachs ─────────────────────────────────────────────────────

@scraper
def fetch_goldman_sachs(feed_config):
    """Fetch articles and reports from Goldman Sachs insights JSON API.

    GS exposes /feeds/insights.json with ~1,957 items. Each item has
    cmsPageProps.contentType — a list of objects like
    [{"id": "gscom:content-type/article", "title": "Article"}].
    We filter to contentType title in ("Article", "Report"), skipping
    videos and podcasts.
    """
    articles = []
    api_url = "https://www.goldmansachs.com/feeds/insights.json"
    raw = _fetch_url(api_url, accept="application/json", timeout=20)
    data = json.loads(raw.decode("utf-8", errors="replace"))

    items = data if isinstance(data, list) else data.get("items", data.get("results", []))
    if not isinstance(items, list):
        items = []

    for item in items:
        cms = item.get("cmsPageProps", {})

        # Filter by contentType — only articles and reports
        ct_list = cms.get("contentType") or []
        ct_title = ct_list[0].get("title", "") if ct_list else ""
        if ct_title not in ("Article", "Report"):
            continue

        title = item.get("title", "").strip()
        path = item.get("path", "")
        if not title or not path:
            continue

        link = path if path.startswith("http") else "https://www.goldmansachs.com" + path

        # Parse date from publishDate (ISO format YYYY-MM-DDTHH:MM:SS)
        dt = None
        date_str = cms.get("publishDate") or ""
        if date_str:
            dt = _parse_date_flexible(date_str)
            if not dt:
                try:
                    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

        if not _is_fresh(dt):
            continue

        desc = item.get("description", "")
        # primaryTopic is a list of objects like contentType
        topic_list = cms.get("primaryTopic") or []
        topic = topic_list[0].get("title", "") if isinstance(topic_list, list) and topic_list else ""
        if topic and desc:
            desc = f"[{topic}] {desc}"

        articles.append(_make_article(title, link, dt, desc, feed_config))

    return articles


# ── CreditSights ─────────────────────────────────────────────────────

@scraper
def fetch_creditsights(feed_config):
    """Fetch from CreditSights blog-research page.

    Real URL is know.creditsights.com/blog-research/.
    Links use /insights/ path pattern.
    """
    articles = []
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

        articles.append(_make_article(title, link, dt, "", feed_config))

    return articles


# ── JPMorgan ──────────────────────────────────────────────────────────

@scraper
def fetch_jpmorgan(feed_config):
    """Fetch Global Research Reports cards from JPMorgan's research-tiles JS."""
    articles = []
    content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

    script_match = re.search(r'<script[^>]+src="([^"]*research-tiles\.js)"', content, re.IGNORECASE)
    if not script_match:
        return articles

    script_url = script_match.group(1)
    if script_url.startswith("/"):
        script_url = "https://www.jpmorgan.com" + script_url

    js_content = _fetch_url(script_url, accept="application/javascript").decode("utf-8", errors="replace")

    def _extract_js_string_field(block, key):
        field_match = re.search(rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"', block, re.DOTALL)
        if not field_match:
            return ""
        raw = field_match.group(1).strip()
        try:
            return json.loads(f'"{raw}"')
        except Exception:
            return raw.replace('\\"', '"').replace("\\n", " ").strip()

    seen_urls = set()
    object_pattern = re.compile(r'const\s+[A-Za-z0-9_]+\s*=\s*\{(.*?)\}\s*;?', re.DOTALL)
    for obj_match in object_pattern.finditer(js_content):
        block = obj_match.group(1)

        title = _extract_js_string_field(block, "title")
        link = _extract_js_string_field(block, "url")
        date_str = _extract_js_string_field(block, "date")
        description = _extract_js_string_field(block, "subtitle")

        if not title or not link or not date_str:
            continue
        if link.startswith("/"):
            link = "https://www.jpmorgan.com" + link
        if not link.startswith("http"):
            continue
        if link in seen_urls:
            continue

        dt = _parse_date_flexible(date_str)
        if dt is None:
            continue

        seen_urls.add(link)
        articles.append(_make_article(title, link, dt, description, feed_config))

    return articles


# ── UBS ──────────────────────────────────────────────────────────────

@scraper
def fetch_ubs(feed_config):
    """Fetch articles from UBS insights JSON API (IB + Asset Management).

    Uses curl because Akamai WAF requires sec-fetch-* browser headers
    that urllib doesn't send, resulting in 403.
    """
    _UBS_IB_API_KEY = "lNrNbJjmsIZtVSia4DRZubdYTzGwJKVmDy5bOBNE8uLDCSBPXDlaSGa1Qq9Bbn7bza0OgXfHwDGSyQQ1AVGnJNxSSvwX5ikSnPneGUMt0DoOkvYtx0wwD4wkChn1VcIF9AIegkooTlCrvmHpEXuWgYRnvSgYkRBiQwlUWsE0cdOJ5gQXbtc6gduaN3S8TmzAM5GIiDeCG6TqN6aKPpEf18vBf8VVvfgtMA98UlWnRJVmJx1eGrqEPZkYIpO79WJN"
    _UBS_AM_PAGE = "https://www.ubs.com/global/en/assetmanagement/insights.html"
    _UBS_DEFAULT_API = "https://www.ubs.com/bin/ubs/caas/v2/searchContentAbstracts"
    _UBS_DEFAULT_HEADERS = [
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json, text/plain, */*",
        "-H", "Origin: https://www.ubs.com",
        "-H", "sec-fetch-dest: empty",
        "-H", "sec-fetch-mode: cors",
        "-H", "sec-fetch-site: same-origin",
        "-H", f"User-Agent: {UA}",
    ]

    def _curl_ubs(endpoint, api_key, referer, payload):
        cmd = [
            "curl", "-sL", "--compressed",
            "-X", "POST", endpoint,
            *_UBS_DEFAULT_HEADERS,
            "-H", "x-app-id: ActivityStream",
            "-H", f"x-api-key: {api_key}",
            "-H", f"Referer: {referer}",
            "-d", json.dumps(payload),
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=25)
        if result.returncode != 0 or not result.stdout:
            return {}
        try:
            return json.loads(result.stdout.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return {}

    def _load_am_role_visibilities():
        """Fetch AM role visibility values used by UBS context disclaimer."""
        try:
            investor_type_url = _UBS_AM_PAGE.replace(".html", ".investortype.xjson")
            investor_raw = _fetch_url(investor_type_url, accept="application/json").decode("utf-8", errors="replace")
            investor_data = json.loads(investor_raw)
            return [
                role for role in investor_data.get("rolevisibility", [])
                if isinstance(role, str) and role.strip()
            ]
        except Exception:
            return []

    def _load_am_query_from_page():
        """Extract the same ActivityStream query options used by the AM page."""
        try:
            content = _fetch_url(_UBS_AM_PAGE).decode("utf-8", errors="replace")
        except Exception:
            return None
        match = re.search(r"data-nc-params-Sdas='(\{.*?\})'", content, re.DOTALL)
        if not match:
            return None
        try:
            raw = html.unescape(match.group(1))
            options = json.loads(raw).get("options", {})
        except Exception:
            return None
        if not options:
            return None

        return {
            "api_key": options.get("apiKey", _UBS_IB_API_KEY),
            "api_endpoint": options.get("apiEndpoint", _UBS_DEFAULT_API),
            "referer": _UBS_AM_PAGE,
            "role_visibilities": _load_am_role_visibilities(),
            # UBS v2 expects maxResult/offset (not pageSize/pageNumber)
            "payload": {
                "contentTypes": options.get("contentTypes", ["ARTICLE", "CONTENT"]),
                "mediaTypes": options.get("mediaTypes", ["video", "audio", "webinar", "pdf", "none"]),
                "language": options.get("language", "en"),
                "isoLanguage": options.get("isoLanguage", "en"),
                "tagSelectionLogic": options.get("tagSelectionLogic", ""),
                "maxResult": 100,
                "offset": 0,
                "useLanguageFallback": options.get("useLanguageFallback", True),
                "includePaths": options.get("includePaths", ["/content/sites/global/en/assetmanagement"]),
                "excludePaths": options.get("excludePaths", []),
                "siteContext": options.get("siteContext", "/content/sites/global/assetmanagement"),
                "currentPagePath": options.get("currentPagePath", "/content/sites/global/en/assetmanagement/insights"),
                "sortingRule": options.get("sortingRule", "DATE"),
            },
        }

    # IB fallback query (kept for broader UBS coverage)
    ib_query = {
        "api_key": _UBS_IB_API_KEY,
        "api_endpoint": _UBS_DEFAULT_API,
        "referer": "https://www.ubs.com/global/en/investment-bank/insights-and-data/latest-insights.html",
        "payload": {
            "contentTypes": ["ARTICLE", "CONTENT"],
            "mediaTypes": ["none"],
            "language": "en",
            "isoLanguage": "en",
            "maxResult": 100,
            "offset": 0,
            "useLanguageFallback": True,
            "includePaths": [
                "/content/sites/global/en/investment-bank/insights-and-data/2026",
                "/content/sites/global/en/investment-bank/insights-and-data/2025",
                "/content/sites/global/en/investment-bank/insights-and-data/articles",
            ],
            "excludePaths": [],
            "siteContext": "/content/sites/global/investment-bank",
            "currentPagePath": "/content/sites/global/en/investment-bank/insights-and-data/latest-insights",
            "sortingRule": "DATE",
        },
    }

    am_query = _load_am_query_from_page()
    queries = [ib_query]
    if am_query:
        am_roles = am_query.get("role_visibilities", [])
        am_base_query = {
            "api_key": am_query["api_key"],
            "api_endpoint": am_query["api_endpoint"],
            "referer": am_query["referer"],
            "payload": dict(am_query["payload"]),
        }
        if am_roles:
            for role in am_roles:
                role_query = {
                    "api_key": am_base_query["api_key"],
                    "api_endpoint": am_base_query["api_endpoint"],
                    "referer": am_base_query["referer"],
                    "payload": dict(am_base_query["payload"]),
                }
                role_query["payload"]["roleVisibility"] = role
                queries.append(role_query)
        else:
            queries.append(am_base_query)
    else:
        # Fallback if page config parsing fails.
        fallback_payload = {
            "contentTypes": ["ARTICLE", "CONTENT"],
            "mediaTypes": ["video", "audio", "webinar", "pdf", "none"],
            "language": "en",
            "isoLanguage": "en",
            "maxResult": 100,
            "offset": 0,
            "useLanguageFallback": True,
            "includePaths": ["/content/sites/global/en/assetmanagement"],
            "excludePaths": [],
            "siteContext": "/content/sites/global/assetmanagement",
            "currentPagePath": "/content/sites/global/en/assetmanagement/insights",
            "sortingRule": "DATE",
        }
        fallback_query = {
            "api_key": _UBS_IB_API_KEY,
            "api_endpoint": _UBS_DEFAULT_API,
            "referer": _UBS_AM_PAGE,
            "payload": fallback_payload,
        }
        fallback_roles = _load_am_role_visibilities()

        if fallback_roles:
            for role in fallback_roles:
                role_query = {
                    "api_key": fallback_query["api_key"],
                    "api_endpoint": fallback_query["api_endpoint"],
                    "referer": fallback_query["referer"],
                    "payload": dict(fallback_query["payload"]),
                }
                role_query["payload"]["roleVisibility"] = role
                queries.append(role_query)
        else:
            queries.append(fallback_query)

    articles = []
    seen_urls = set()

    for query_cfg in queries:
        data = _curl_ubs(
            query_cfg["api_endpoint"],
            query_cfg["api_key"],
            query_cfg["referer"],
            query_cfg["payload"],
        )
        docs = data.get("documents", []) if isinstance(data, dict) else []
        if not docs:
            continue

        is_am = "/assetmanagement/" in query_cfg["referer"]
        for doc in docs:
            fields = doc.get("fields", {})
            title = (fields.get("title") or [""])[0].strip()
            url = (fields.get("targetUrl") or [""])[0]
            if not title or not url or url in seen_urls:
                continue

            # For AM query, keep actual insights pages and skip generic utility pages.
            if is_am and "/global/en/assetmanagement/insights/" not in url:
                continue

            seen_urls.add(url)
            dt = None
            date_str = (fields.get("as_displayDate") or [""])[0]
            if date_str:
                dt = _parse_date_flexible(date_str)
            desc = (fields.get("as_teaserText") or [""])[0]
            articles.append(_make_article(title, url, dt, desc, feed_config))

    # Keep freshest items first so cap is applied to most relevant entries.
    def _sort_ts(article):
        dt = article.get("date")
        if not dt:
            return 0
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()

    articles.sort(key=_sort_ts, reverse=True)
    return articles


# ── State Street (SSGA) ───────────────────────────────────────────────

@scraper
def fetch_ssga_insights(feed_config):
    """Fetch SSGA intermediary insights from the public search API.

    The insights page renders results client-side by calling:
    /public-api/aem/v2/search?geoloc=us:en&roleproduct=intermediary&site=ssmp&n=Insights

    Relevant fields in each result:
      - k: title
      - l: canonical URL
      - d: subheading/description
      - t: date string (e.g., "March 2, 2026")
    """
    params = {
        "geoloc": "us:en",
        "roleproduct": "intermediary",
        "site": "ssmp",
        "n": "Insights",
    }
    api_url = "https://www.ssga.com/public-api/aem/v2/search?" + urllib.parse.urlencode(params)
    raw = _fetch_url(api_url, accept="application/json", feed_config=feed_config)
    data = json.loads(raw.decode("utf-8", errors="replace"))
    results = data.get("results", []) if isinstance(data, dict) else []
    if not isinstance(results, list):
        return []

    articles = []
    seen_urls = set()
    for item in results:
        if not isinstance(item, dict):
            continue

        title = (item.get("k") or "").strip()
        url = (item.get("l") or "").strip()
        if not title or not url:
            continue

        if url.startswith("/"):
            url = urllib.parse.urljoin("https://www.ssga.com", url)
        if not url.startswith("http"):
            continue

        dedupe_key = url.lower().strip().rstrip("/")
        if dedupe_key in seen_urls:
            continue
        seen_urls.add(dedupe_key)

        date_str = (item.get("t") or "").strip()
        dt = _parse_date_flexible(date_str) if date_str else None
        desc = (item.get("d") or "").strip()
        articles.append(_make_article(title, url, dt, desc, feed_config))

    return articles


# ── GS Publishing (Goldman Sachs Research papers) ────────────────────

@scraper
def fetch_gs_publishing(feed_config):
    """Fetch public research papers from GS Publishing.

    gspublishing.com — Next.js SSR page listing research papers.
    Links: /content/research/en/reports/YYYY/MM/DD/UUID.html
    Metadata: "DD Mon YYYY | time | pages | Research | Category - Author"
    """
    articles = []
    content = _fetch_url(
        "https://www.gspublishing.com/content/public.html",
        timeout=25, feed_config=feed_config,
    ).decode("utf-8", errors="replace")

    for m in re.finditer(
        r'href="(/content/research/en/reports/(\d{4})/(\d{2})/(\d{2})/[^"]+\.html)"'
        r'[^>]*>([^<]+)</a>',
        content,
    ):
        path, year, month, day, title = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5).strip()
        link = "https://www.gspublishing.com" + path
        dt = _parse_date_flexible(f"{year}-{month}-{day}")

        # Try to extract category from metadata text after the link
        after = content[m.end():m.end() + 300]
        cat_m = re.search(r'Research\s*\|\s*(\w[\w\s&]*?)(?:\s*-\s*|\s*<)', after)
        desc = f"[{cat_m.group(1).strip()}]" if cat_m else ""

        articles.append(_make_article(title, link, dt, desc, feed_config))

    return articles


# ── Kpler Blog (commodity/energy market analysis) ────────────────────

@scraper
def fetch_kpler(feed_config):
    """Fetch blog posts from Kpler.

    kpler.com/pt/resources/blog — Webflow-rendered blog with SSR HTML.
    Two layouts: featured (main-blog-link-wrap) and grid (blog-link-wrap).
    Dates in blog-grid-date divs or featured-author divs.
    """
    articles = []
    content = _fetch_url(
        "https://www.kpler.com/pt/resources/blog",
        timeout=20, feed_config=feed_config,
    ).decode("utf-8", errors="replace")

    seen_urls = set()

    # Grid articles: <a href="/pt/blog/slug" class="blog-link-wrap ...">
    for m in re.finditer(
        r'<a[^>]*href="(/pt/blog/[^"]+)"[^>]*class="[^"]*blog-link-wrap[^"]*"[^>]*>(.*?)</a>',
        content, re.DOTALL,
    ):
        url = "https://www.kpler.com" + m.group(1)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        block = m.group(2)

        # Title: <h1>, <h5>, or <h6> tags
        title_m = re.search(r'<h[1-6][^>]*>([^<]+)</h[1-6]>', block)
        title = _strip_html(title_m.group(1)).strip() if title_m else ""
        if not title or len(title) < 10:
            continue

        # Date: blog-grid-date or featured-author with date pattern
        date_m = re.search(r'blog-grid-date[^>]*>([^<]+)<', block)
        if not date_m:
            date_m = re.search(r'featured-author[^>]*>(\w+ \d{1,2}, \d{4})<', block)
        dt = _parse_date_flexible(date_m.group(1).strip()) if date_m else None

        # Description: <p> tag (featured articles only)
        desc_m = re.search(r'<p[^>]*>([^<]{20,})</p>', block)
        desc = _strip_html(desc_m.group(1)).strip()[:300] if desc_m else ""

        articles.append(_make_article(title, url, dt, desc, feed_config))

    return articles


# ── CRISIL Ratings Reports (research reports, separate from press releases) ──

@scraper
def fetch_crisil_reports(feed_config):
    """Fetch research reports from CRISIL Ratings analysis section.

    crisilratings.com/en/home/our-analysis/reports.html — uses analyticstile-link
    class with title attribute. Different HTML from press releases page.
    """
    articles = []
    content = _fetch_url(
        "https://www.crisilratings.com/en/home/our-analysis/reports.html",
        feed_config=feed_config,
    ).decode("utf-8", errors="replace")

    seen = set()
    for m in re.finditer(
        r'(?:analyticstile-link|banner-link)"\s+href="([^"]+/our-analysis/reports/[^"]+)"'
        r'[^>]*\s+title="([^"]+)"',
        content,
    ):
        path, title = m.group(1), html.unescape(m.group(2)).strip()
        if not title or len(title) < 10 or path in seen:
            continue
        seen.add(path)
        link = "https://www.crisilratings.com" + path

        # Search backward from the match for a nearby date like "March 05, 2026"
        before = content[max(0, m.start() - 800):m.start()]
        date_m = re.search(r'(\w+ \d{1,2}, \d{4})', before)
        if not date_m:
            # Also search forward (some layouts put date after title)
            after = content[m.end():m.end() + 500]
            date_m = re.search(r'(\w+ \d{1,2}, \d{4})', after)
        if not date_m:
            # Fallback: extract from URL path /reports/YYYY/MM/ (use 15th as midpoint)
            url_date_m = re.search(r'/reports/(\d{4})/(\d{2})/', path)
            dt = _parse_date_flexible(f"{url_date_m.group(1)}-{url_date_m.group(2)}-15") if url_date_m else None
        else:
            dt = _parse_date_flexible(date_m.group(1))

        articles.append(_make_article(title, link, dt, "", feed_config))

    return articles


# ── PIIE (Playwright cache) ───────────────────────────────────────────

_PIIE_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "piie_cache.json")
_PIIE_CACHE_MAX_AGE_HOURS = 48  # PIIE publishes infrequently; generous staleness window


@scraper
def fetch_piie_cache(feed_config):
    """Read PIIE articles from locally-generated Playwright cache."""
    try:
        with open(_PIIE_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    # Check freshness
    generated = data.get("generated_at", "")
    try:
        gen_dt = datetime.fromisoformat(generated)
        if gen_dt.tzinfo is None:
            gen_dt = gen_dt.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - gen_dt).total_seconds() / 3600
    except Exception:
        age_hours = 999
    if age_hours > _PIIE_CACHE_MAX_AGE_HOURS:
        return []

    feed_id = feed_config.get("id", "")
    articles = []
    for item in data.get("items", []):
        if item.get("feed_id") != feed_id:
            continue
        title = item.get("title", "").strip()
        link = item.get("link", "").strip()
        if not title or not link:
            continue
        dt = _parse_date_flexible(item.get("date", ""))
        if not _is_fresh(dt):
            continue
        articles.append(_make_article(title, link, dt, "", feed_config))
    return articles


# ── NITI Aayog (Division Reports) ─────────────────────────────────────

@scraper
def fetch_niti_aayog(feed_config):
    """Fetch reports from NITI Aayog's publications listing.

    niti.gov.in (Drupal Views) renders reports as a server-side HTML table
    (<table class="cols-5">). Each <tr> has parallel cells: title, date,
    division ("vertical"), and a PDF download anchor. Dates are month-only
    (e.g. "July 2026"), so we anchor them to the 15th as a midpoint — the
    same convention fetch_crisil_reports uses for month-granularity sources.
    """
    articles = []
    content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

    # Extract parallel lists from the consistent 5-column table structure.
    # The <th> header cells share the same classes as the <td> data cells, so
    # we key data cells on their `headers="..."` attribute to skip the header row.
    titles = re.findall(
        r'headers="view-title-table-column"[^>]*>(.*?)</td>', content, re.DOTALL
    )
    dates = re.findall(
        r'headers="view-field-publication-date-papers-table-column"[^>]*>(.*?)</td>',
        content, re.DOTALL,
    )
    divisions = re.findall(
        r'headers="view-field-vertical-table-column"[^>]*>(.*?)</td>', content, re.DOTALL
    )
    links = re.findall(
        r'headers="view-nothing-table-column"[^>]*>\s*<a\s+href="([^"]+)"',
        content, re.DOTALL,
    )

    count = min(len(titles), len(dates), len(links))
    seen = set()
    for i in range(count):
        title = html.unescape(_strip_html(titles[i])).strip()
        if not title or len(title) < 5:
            continue

        href = links[i].strip()
        if not href or href in seen:
            continue
        seen.add(href)
        link = href if href.startswith("http") else "https://www.niti.gov.in" + href

        # Date is month-only ("July 2026"); anchor to the 15th as a midpoint.
        dt = None
        date_str = _strip_html(dates[i]).strip()
        if date_str:
            try:
                dt = datetime.strptime(date_str, "%B %Y").replace(
                    day=15, tzinfo=IST_TZ
                )
            except ValueError:
                dt = _parse_date_flexible(date_str)
        if not _is_fresh(dt):
            continue

        division = html.unescape(_strip_html(divisions[i])).strip() if i < len(divisions) else ""
        desc = f"[{division}]" if division else ""

        articles.append(_make_article(title, link, dt, desc, feed_config))

    return articles


# ── IEEFA (Institute for Energy Economics and Financial Analysis) ─────

_IEEFA_RSS_URL = "https://ieefa.org/rss.xml"
_IEEFA_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "ieefa_cache.json")
_IEEFA_CACHE_WINDOW_DAYS = 35  # a little wider than the 30-day freshness cutoff
_IEEFA_LOCK = threading.Lock()  # both IEEFA feeds run on separate aggregator threads
_ieefa_refreshed = False        # network refresh happens once per process, not per feed

# Labels used by the research hub's "Type" filter. The RSS description embeds
# the label as a bare <div>; matching against this closed vocabulary beats
# positional parsing, because press releases (/articles/) carry no label at all.
_IEEFA_RESOURCE_TYPES = frozenset({
    "Report",
    "Insights",
    "Briefing Note",
    "Testimony | Submission",
    "Fact Sheet",
    "Public Comment",
    "Slides",
})

# feed id → the single resource type that feed surfaces.
# tid_1[6]=6 is "Report", tid_1[583]=583 is "Insights" in the research hub URLs.
_IEEFA_FEED_TYPES = {
    "ieefa-reports": "Report",
    "ieefa-insights": "Insights",
}


def _ieefa_resource_type(description):
    """Return the resource-type label embedded in an RSS description, or ""."""
    for raw in re.findall(r"<div>([^<>]*)</div>", description):
        label = raw.strip()
        if label in _IEEFA_RESOURCE_TYPES:
            return label
    return ""


def _ieefa_parse_rss(content):
    """Parse ieefa.org/rss.xml into cache rows, keeping only typed resources."""
    rows = []
    for block in re.findall(r"<item>(.*?)</item>", content, re.DOTALL):
        link_m = re.search(r"<link>(.*?)</link>", block, re.DOTALL)
        title_m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, re.DOTALL)
        if not link_m or not title_m:
            continue
        link = html.unescape(link_m.group(1).strip())
        title = html.unescape(_strip_html(title_m.group(1)).strip())
        if not link or not title:
            continue

        desc_m = re.search(r"<description>(.*?)</description>", block, re.DOTALL)
        res_type = _ieefa_resource_type(html.unescape(desc_m.group(1))) if desc_m else ""
        if not res_type:  # press releases and untyped nodes
            continue

        dt = None
        date_m = re.search(r"<pubDate>(.*?)</pubDate>", block, re.DOTALL)
        if date_m:
            try:
                dt = parsedate_to_datetime(date_m.group(1).strip())
            except (TypeError, ValueError):
                dt = None

        rows.append({
            "title": title,
            "link": link,
            "date": dt.isoformat() if dt else None,
            "type": res_type,
        })
    return rows


def _atomic_write_json(path, payload, label):
    """Write JSON via a temp file + rename, so readers never see a partial file.

    These caches are read and written by the same pipeline (and, locally, by a
    systemd timer doing git operations alongside it), so a half-written file is
    a real failure mode rather than a theoretical one.
    """
    tmp = f"{path}.tmp"
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except Exception as e:
        # Catch broadly: a cache write must never take the pipeline down, and
        # json.dump raises TypeError (not OSError) on an unserializable value.
        print(f"  [WARN] {label} write failed: {str(e)[:80]}")
        try:
            os.remove(tmp)  # don't leave a partial file behind
        except OSError:
            pass
        return False


def _ieefa_cache_file_looks_populated(min_bytes=200):
    """True if the cache file exists with real content — used as a loss guard."""
    try:
        return os.path.getsize(_IEEFA_CACHE_FILE) > min_bytes
    except OSError:
        return False


def _coerce_iso_date(raw):
    """Parse an ISO date string from the cache into a tz-aware datetime."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _ieefa_load_cache():
    """Load the rolling cache as a {link: row} dict."""
    try:
        with open(_IEEFA_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    items = data.get("items", []) if isinstance(data, dict) else []
    return {
        item["link"]: item
        for item in items
        if isinstance(item, dict) and item.get("link") and item.get("title")
    }


def _ieefa_prune(by_link):
    """Drop rows older than the cache window. Undated rows are kept."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=_IEEFA_CACHE_WINDOW_DAYS)
    kept = {}
    for link, item in by_link.items():
        if not item.get("date"):
            kept[link] = item
            continue
        dt = _coerce_iso_date(item["date"])
        if dt and dt >= cutoff:
            kept[link] = item
    return kept


def _ieefa_refresh_cache(feed_config):
    """Merge the newest RSS items into the rolling cache and persist it.

    ieefa.org/research-hub sits behind a Cloudflare JS challenge (403 to any
    non-browser client), but ieefa.org/rss.xml returns 200 — same trade as
    CEEW. The catch is that rss.xml is a 10-item sitewide firehose with no
    paging, roughly three days of output, so one read cannot fill the 30-day
    Reports window. Accumulating across hourly runs does; ieefa_local_fetch.py
    seeds/backfills the same file with a real browser.

    A failed fetch is non-fatal — we serve whatever the cache already holds.
    """
    global _ieefa_refreshed

    by_link = _ieefa_load_cache()
    loaded_count = len(by_link)
    try:
        content = _fetch_url(
            _IEEFA_RSS_URL,
            accept="application/rss+xml, application/xml, text/xml",
            feed_config=feed_config,
        ).decode("utf-8", errors="replace")
        for row in _ieefa_parse_rss(content):
            by_link[row["link"]] = row  # freshest metadata wins
    except Exception as e:
        print(f"  [WARN] IEEFA RSS refresh failed ({str(e)[:80]}); serving cache only")

    by_link = _ieefa_prune(by_link)

    # Guard the accumulation. A load that comes back empty while the file on
    # disk is clearly populated means we caught it mid-write or mid-checkout —
    # writing then would replace a month of history with one RSS window. Skip
    # the write and let the next run pick it up. (This has actually happened,
    # via the local rsshub timer's git operations racing an aggregator run.)
    if loaded_count == 0 and _ieefa_cache_file_looks_populated():
        print("  [WARN] IEEFA cache unreadable but non-empty on disk; skipping write to avoid data loss")
        _ieefa_refreshed = True
        return by_link

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": sorted(by_link.values(), key=lambda i: i.get("date") or "", reverse=True),
    }
    _atomic_write_json(_IEEFA_CACHE_FILE, payload, "IEEFA cache")

    _ieefa_refreshed = True
    return by_link


@scraper
def fetch_ieefa(feed_config):
    """Fetch IEEFA reports/insights from the rolling RSS-fed cache."""
    wanted = _IEEFA_FEED_TYPES.get(feed_config.get("id", ""))
    if not wanted:
        return []

    # Serialised so the two IEEFA feeds share one network call and one writer.
    with _IEEFA_LOCK:
        by_link = _ieefa_load_cache() if _ieefa_refreshed else _ieefa_refresh_cache(feed_config)

    articles = []
    for item in sorted(by_link.values(), key=lambda i: i.get("date") or "", reverse=True):
        if item.get("type") != wanted:
            continue
        dt = _coerce_iso_date(item.get("date"))
        if not _is_fresh(dt):
            continue
        articles.append(_make_article(item.get("title", ""), item["link"], dt, "", feed_config))
    return articles


# ── Ember (Playwright cache) ──────────────────────────────────────────

_EMBER_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "ember_cache.json")
_EMBER_STALE_WARN_DAYS = 7

# ember-energy.org `insight_type` taxonomy → feed id. Term ids live in
# ember_local_fetch.py; the label is what gets stored in the cache.
_EMBER_FEED_TYPES = {
    "ember-analysis": "Analysis",
    "ember-commentary": "Commentary",
    "ember-policy-papers": "Policy papers",
}


@scraper
def fetch_ember_cache(feed_config):
    """Read Ember insights from the locally-generated Playwright cache.

    Every path on ember-energy.org is Cloudflare-challenged — robots.txt and
    the WordPress REST API included — so unlike IEEFA there is no CI-reachable
    feed to top this up. `ember_local_fetch.py` refreshes it from a real
    browser; the pipeline only ever reads.

    There is deliberately no cache TTL. Each item carries its own date and the
    30-day Reports window already filters on it, so a cache that stops being
    refreshed empties itself rather than serving stale reports — a TTL would
    just blank the source early. We warn instead.
    """
    wanted = _EMBER_FEED_TYPES.get(feed_config.get("id", ""))
    if not wanted:
        return []

    try:
        with open(_EMBER_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    generated = _coerce_iso_date(data.get("generated_at"))
    if generated:
        age_days = (datetime.now(timezone.utc) - generated).days
        if age_days > _EMBER_STALE_WARN_DAYS:
            print(f"  [WARN] Ember cache is {age_days}d old — run python3 ember_local_fetch.py")

    articles = []
    for item in data.get("items", []):
        if not isinstance(item, dict) or item.get("type") != wanted:
            continue
        title = html.unescape((item.get("title") or "").strip())
        link = (item.get("link") or "").strip()
        if not title or not link:
            continue
        dt = _coerce_iso_date(item.get("date"))
        if not _is_fresh(dt):
            continue
        articles.append(_make_article(title, link, dt, item.get("description", ""), feed_config))

    articles.sort(key=lambda a: a["date"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return articles


# ── IEA (International Energy Agency) ─────────────────────────────────

@scraper
def fetch_iea(feed_config):
    """Fetch IEA reports from the analysis listing.

    iea.org renders the listing server-side, so no browser is needed — but
    Cloudflare challenges on request *rate*, not per request. We therefore
    make exactly one call per run and treat a challenge page as a failure so
    the reports cache fills in, rather than silently parsing zero cards out of
    the interstitial. Page one reaches back roughly nine months, well past the
    30-day window, so there is nothing to gain from paginating.
    """
    content = _fetch_url(feed_config["url"], feed_config=feed_config).decode("utf-8", errors="replace")
    if "Just a moment" in content[:2000] or "challenges.cloudflare.com" in content[:2000]:
        raise Exception("Cloudflare challenge served instead of the listing")

    # The nav mega-menu reuses the same card markup — drop it before parsing.
    listing = content.split("m-card-listing--nav")[-1]

    articles = []
    seen = set()
    for block in re.findall(r'<li class="m-card-listing-item[^"]*"[^>]*>(.*?)</li>', listing, re.DOTALL):
        href_m = re.search(r'href="([^"]+)"', block)
        title_m = re.search(r'class="[^"]*m-card__title"[^>]*>(.*?)</h2>', block, re.DOTALL)
        if not href_m or not title_m:
            continue

        href = href_m.group(1).strip()
        if not href or href in seen:  # a featured block repeats items further down
            continue
        seen.add(href)

        title = html.unescape(_strip_html(title_m.group(1))).strip()
        if not title:
            continue
        link = href if href.startswith("http") else "https://www.iea.org" + href

        # One node packs both kind and date: "Fuel report   —   10 July 2026".
        kind, dt = "", None
        type_m = re.search(r'class="m-card__type"[^>]*>(.*?)</p>', block, re.DOTALL)
        if type_m:
            text = re.sub(r"\s+", " ", html.unescape(_strip_html(type_m.group(1)))).strip()
            parts = re.split(r"\s+[—–]\s+", text)
            kind = parts[0].strip()
            if len(parts) > 1:
                dt = _parse_date_flexible(parts[-1].strip())

        if not _is_fresh(dt):
            continue
        articles.append(_make_article(title, link, dt, kind, feed_config))

    # The featured block at the top is not in date order, so sort explicitly.
    articles.sort(key=lambda a: a["date"] or datetime.min.replace(tzinfo=IST_TZ), reverse=True)
    return articles


# ── CSEP (Centre for Social and Economic Progress) ────────────────────

# Each publication kind is its own WordPress post type, so the listing page's
# "posttypes=all" means one REST call per type. `multimedia` and `interactives`
# are deliberately excluded — they are media and tools, not reports.
_CSEP_POST_TYPES = (
    "reports",
    "working-paper",
    "flagship-paper",
    "policy-brief",
    "discussion-note",
    "technical-note",
    "impact-paper",
    "opinion-commentary",
)


@scraper
def fetch_csep(feed_config):
    """Fetch CSEP publications across every publication post type.

    csep.org leaves the WordPress REST API open, so we read that instead of
    the admin-ajax call its /publication/ page makes — structured JSON with
    real dates beats scraping a 1.5MB listing. All types pool into one CSEP
    source. A type that errors is skipped rather than failing the whole feed.
    """
    articles = []
    for post_type in _CSEP_POST_TYPES:
        url = (
            f"https://csep.org/wp-json/wp/v2/{post_type}"
            "?per_page=10&orderby=date&order=desc&_fields=title,link,date,excerpt"
        )
        try:
            payload = json.loads(
                _fetch_url(url, accept="application/json", feed_config=feed_config)
            )
        except Exception as e:
            print(f"  [WARN] CSEP {post_type}: {str(e)[:70]}")
            continue
        if not isinstance(payload, list):
            continue

        for post in payload:
            if not isinstance(post, dict):
                continue
            title = html.unescape(_strip_html((post.get("title") or {}).get("rendered", ""))).strip()
            link = (post.get("link") or "").strip()
            if not title or not link:
                continue
            # WordPress reports site-local time; CSEP is Delhi-based, so IST.
            dt = _parse_date_flexible(post.get("date") or "")
            if not _is_fresh(dt):
                continue
            desc = html.unescape(_strip_html((post.get("excerpt") or {}).get("rendered", ""))).strip()
            articles.append(_make_article(title, link, dt, desc, feed_config))

    articles.sort(key=lambda a: a["date"] or datetime.min.replace(tzinfo=IST_TZ), reverse=True)
    return articles


# ── Dispatcher ────────────────────────────────────────────────────────

# Maps feed prefix → fetcher function
REPORT_FETCHERS = {
    "crisilratings:": fetch_crisil_ratings,
    "crisilreports:": fetch_crisil_reports,
    "crisil:": fetch_crisil_research,
    "baroda:": fetch_baroda_etrade,
    "sbi:": fetch_sbi_research,
    "ficci:": fetch_ficci,
    "ceew:": fetch_ceew,
    "icici:": fetch_icici_research,
    "hdfcsec:": fetch_hdfc_sec,
    "axis:": fetch_axis_direct,
    "gs:": fetch_goldman_sachs,
    "gspub:": fetch_gs_publishing,
    "creditsights:": fetch_creditsights,
    "jpmorgan:": fetch_jpmorgan,
    "ubs:": fetch_ubs,
    "ssga:": fetch_ssga_insights,
    "kpler:": fetch_kpler,
    "piie:": fetch_piie_cache,
    "niti:": fetch_niti_aayog,
    "ieefa:": fetch_ieefa,
    "ember:": fetch_ember_cache,
    "iea:": fetch_iea,
    "csep:": fetch_csep,
}


def get_report_fetcher(feed_field):
    """Return the appropriate fetcher function for a feed field, or None."""
    for prefix, fetcher in REPORT_FETCHERS.items():
        if feed_field.startswith(prefix):
            return fetcher
    return None
