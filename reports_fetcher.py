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
import xml.etree.ElementTree as ET

from articles import IST_TZ
from stock_notes import (
    ARCHIVE_FILE as STOCK_NOTES_ARCHIVE,
    STOCK_NOTE_KIND,
    canonical_broker,
    canonical_rating,
    clean_company,
    known_note_keys,
    load_archive,
    note_title,
    parse_price,
    pdf_first_page_text,
)
# Google News RSS helpers, reused so the CREA news fallback resolves redirect
# links and strips source suffixes exactly like every other Google-backed feed.
# feeds.py does not import this module, so the dependency stays one-way.
from feeds import (
    _dedupe_articles,
    _fetch_url_bytes,
    _parse_feed_content,
    _post_process_google_rss_articles,
)
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


def _is_fresh(dt, cutoff=None):
    """Return True if date is within the cutoff (default 30 days) or None (undated)."""
    if dt is None:
        return True
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt) <= (cutoff or _FRESHNESS_CUTOFF)


def _feed_cutoff(feed_config):
    """Freshness window for a feed: feeds.json `max_age_days`, else 30 days."""
    days = (feed_config or {}).get("max_age_days")
    return timedelta(days=days) if days else _FRESHNESS_CUTOFF


def scraper(func):
    """Decorator for report scrapers — handles errors, freshness, limits, logging.

    Feeds may override the defaults in feeds.json: `max_items` (high-volume
    sources like broker stock notes post ~25 a day, far past the 30-item cap)
    and `max_age_days` (a shorter window keeps tab_research.json small).
    """
    @functools.wraps(func)
    def wrapper(feed_config):
        try:
            articles = func(feed_config)
            # Filter out stale articles
            cutoff = _feed_cutoff(feed_config)
            articles = [a for a in articles if _is_fresh(a.get("date"), cutoff)]
            # Enforce per-scraper limit
            articles = articles[:feed_config.get("max_items") or _MAX_PER_SCRAPER]
            print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
            return articles
        except Exception as e:
            print(f"  [FAIL] {feed_config['name']}: {str(e)[:120]}")
            return []
    return wrapper


def _fetch_url(url, accept="text/html", timeout=None, feed_config=None, data=None, extra_headers=None,
               ssl_context=None):
    """Shared URL fetcher with urllib + curl fallback and retry logic.

    Passing `data` (bytes) makes it a POST — needed for Drupal's /views/ajax,
    which is the only machine-readable route into some listing pages.
    """
    feed_id = (feed_config or {}).get("id", "")
    effective_timeout = timeout if timeout is not None else SCRAPER_FETCH_TIMEOUT
    if feed_id in SCRAPER_TIMEOUT_OVERRIDES:
        effective_timeout = SCRAPER_TIMEOUT_OVERRIDES[feed_id]

    max_retries = SCRAPER_RETRY_OVERRIDES.get(feed_id, SCRAPER_RETRY_ATTEMPTS)

    headers = {
        "User-Agent": UA,
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9",
    }
    headers.update(extra_headers or {})

    for attempt in range(max_retries + 1):
        try:
            try:
                req = urllib.request.Request(url, data=data, headers=headers)
                try:
                    with urllib.request.urlopen(req, timeout=effective_timeout, context=ssl_context or SSL_CONTEXT) as resp:
                        return resp.read()
                except ssl.SSLCertVerificationError:
                    if ssl_context is not None:
                        raise  # a site with its own trust setup must verify; never fall back to unverified
                    print(f"  [WARN] TLS verification failed for {url}, falling back to unverified")
                    req = urllib.request.Request(url, data=data, headers=headers)
                    with urllib.request.urlopen(req, timeout=effective_timeout, context=SSL_CONTEXT_NOVERIFY) as resp:
                        return resp.read()
            except urllib.error.HTTPError as e:
                if e.code == 403:
                    for ua in ["FeedFetcher/1.0", "Mozilla/5.0 (compatible; RSS Reader)"]:
                        cmd = ["curl", "-sL", "-A", ua]
                        if data is not None:
                            # Without this the retry would silently downgrade to
                            # a GET and parse whatever the bare URL returns.
                            cmd += ["--data-binary", data.decode("utf-8", "replace")]
                        result = subprocess.run(
                            cmd + [url],
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
        # "stock_note" sends the item to the Stock notes archive, not the Reports list
        "kind": feed_config.get("kind", ""),
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


# ── CREA (Centre for Research on Energy and Clean Air) ────────────────

# CREA runs WordPress with Polylang. Two things make the REST API the only
# sane route here:
#   - /publications/feed/ looks like a content feed and returns HTTP 200,
#     but it is the *comments* feed for that page ("Comments on: Publications")
#     and is permanently empty. There is no RSS for the publication CPT.
#   - Without lang=en, wp/v2/posts interleaves zh/ua translations of the same
#     story, which would land in the News tab as duplicates.
_CREA_API_BASE = "https://energyandcleanair.org/wp-json/wp/v2"

# feed suffix → WordPress rest_base. `publication` is a custom post type
# (the /publications/ page); `posts` is the regular blog (the /news/ page).
_CREA_ENDPOINTS = {
    "publications": "publication",
    "news": "posts",
}

_CREA_GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search?q=site:energyandcleanair.org"
    "&hl=en-IN&gl=IN&ceid=IN:en"
)

# Google labels some CREA items " - energyandcleanair.org" instead of " - CREA".
_CREA_DOMAIN_SUFFIX_RE = re.compile(r"\s*[-–—]\s*energyandcleanair\.org\s*$", re.IGNORECASE)


def _parse_crea_gmt(raw):
    """Parse WordPress date_gmt, which is naive ISO but always UTC.

    Deliberately not _parse_date_flexible: that helper stamps IST_TZ on every
    date it parses (correct for the Indian report sites it was written for),
    which would shift each CREA timestamp 5h30m earlier than it happened.
    """
    if not raw:
        return None
    try:
        dt = datetime.strptime(str(raw).strip()[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc)


def _parse_crea_items(payload, feed_config):
    """Map WordPress REST objects onto the standard article dict."""
    articles = []
    for post in payload:
        if not isinstance(post, dict):
            continue
        title = html.unescape(_strip_html((post.get("title") or {}).get("rendered", ""))).strip()
        link = (post.get("link") or "").strip()
        if not title or not link:
            continue
        # date_gmt is always UTC; the sibling `date` field is naive site-local
        # time with no offset, which silently skews the Reports freshness cut.
        dt = _parse_crea_gmt(post.get("date_gmt"))
        if not _is_fresh(dt):
            continue
        # _strip_html leaves a space per removed tag, so inline markup in the
        # excerpt ("<b>without</b>") turns into doubled spaces on the card.
        desc = re.sub(
            r"\s+", " ",
            html.unescape(_strip_html((post.get("excerpt") or {}).get("rendered", ""))),
        ).strip()
        articles.append(_make_article(title, link, dt, desc, feed_config))
    return articles


def _fetch_crea_google_fallback(feed_config):
    """Last-resort route for the News feed: Google's index of the site.

    energyandcleanair.org sits behind Cloudflare, so a datacenter IP can lose
    access to the REST API without warning. News articles get no cache
    fallback (only Reports are persisted to reports_cache.json), so this is
    the only thing standing between a Cloudflare block and an empty tab.
    """
    content = _fetch_url_bytes(_CREA_GOOGLE_NEWS_RSS, timeout=20)
    articles = _dedupe_articles(_parse_feed_content(content, feed_config))
    # Strips the " - CREA" suffix Google appends and unwraps the
    # news.google.com/rss/articles/ redirect back to the real URL where it can.
    _post_process_google_rss_articles(articles, feed_config)

    cleaned = []
    for article in articles:
        # Google labels roughly half of CREA's items by domain rather than by
        # publisher name, which the shared publisher-alias strip above misses.
        title = _CREA_DOMAIN_SUFFIX_RE.sub("", article.get("title", "")).strip()
        if not title or not article.get("link"):
            continue
        article["title"] = title
        cleaned.append(article)
    return cleaned


@scraper
def fetch_crea(feed_config):
    """Fetch CREA publications or news from the WordPress REST API."""
    suffix = feed_config["feed"].split(":", 1)[1].strip()
    rest_base = _CREA_ENDPOINTS.get(suffix)
    if not rest_base:
        raise ValueError(f"unknown CREA feed suffix: {suffix!r}")

    url = (
        f"{_CREA_API_BASE}/{rest_base}"
        f"?per_page={_MAX_PER_SCRAPER}&lang=en&orderby=date&order=desc"
        "&_fields=date_gmt,link,title,excerpt"
    )

    articles = []
    try:
        payload = json.loads(_fetch_url(url, accept="application/json", feed_config=feed_config))
        if isinstance(payload, list):
            articles = _parse_crea_items(payload, feed_config)
    except Exception as e:
        if suffix != "news":
            raise
        print(f"  [WARN] {feed_config['name']}: REST API failed ({str(e)[:60]}), trying Google")

    # Only the News feed falls back. Reports already have reports_cache.json,
    # and Google News does not index the /publication/ post type.
    if not articles and suffix == "news":
        articles = _fetch_crea_google_fallback(feed_config)
        if articles:
            # The @scraper wrapper prints the final post-cap count after this.
            print(f"  [INFO] {feed_config['name']}: served via Google fallback")

    articles.sort(key=lambda a: a["date"] or datetime.min.replace(tzinfo=IST_TZ), reverse=True)
    return articles


# ── Global Energy Monitor (Reports & Briefings) ───────────────────────

# GEM is Drupal, not WordPress: there is no /feed/, no /jsonapi, and the
# listing page ships zero report links in its HTML — the cards arrive via a
# Views AJAX call. That endpoint is unauthenticated and returns the full
# listing, so it is the only structured route in.
_GEM_ORIGIN = "https://globalenergymonitor.org"
_GEM_AJAX_URL = f"{_GEM_ORIGIN}/views/ajax"
_GEM_RSS_URL = f"{_GEM_ORIGIN}/rss.xml"

# Scraped from the listing page's drupalSettings. view_args is an internal
# taxonomy id, so if GEM re-numbers their content types this could start
# returning a *different* listing rather than failing — hence the explicit
# "is this tagged as a report" check in _gem_parse_cards().
_GEM_VIEW = {
    "view_name": "resource_listing",
    "view_display_id": "block_2",
    "view_args": "8",
    "view_path": "/node/1462",
    "page": "0",
}

_GEM_REPORT_TAGS = frozenset({"report", "briefing"})

_GEM_CARD_RE = re.compile(
    r'<a\s+href="(/research/[^"]+)"[^>]*class="card\b.*?</a>', re.DOTALL | re.IGNORECASE
)
_GEM_TAG_RE = re.compile(r'<div class="tag">\s*(.*?)\s*</div>', re.DOTALL)
_GEM_TITLE_RE = re.compile(r'<div class="card-title">(.*?)</div>', re.DOTALL)
_GEM_DATE_RE = re.compile(r'<div class="card-date">\s*(.*?)\s*</div>', re.DOTALL)


def _gem_month_start(date_text):
    """Resolve GEM's month-only card date ("September 2026") to the 1st, UTC.

    The cards carry no day. Anchoring to the 1st never makes a report look
    newer than it is, so the 30-day Reports window may retire an item early
    but will never hold a stale one. Where rss.xml covers the report we use
    its exact pubDate instead and this approximation never applies.
    """
    text = _strip_html(date_text or "").strip()
    if not text:
        return None
    for fmt in ("%B %Y", "%b %Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _gem_parse_cards(html_str):
    """Pull report cards out of the Views AJAX markup."""
    cards = []
    for block in _GEM_CARD_RE.finditer(html_str or ""):
        href = block.group(1)
        body = block.group(0)
        tags = [_strip_html(t).strip() for t in _GEM_TAG_RE.findall(body)]
        tags = [t for t in tags if t]
        if not tags or tags[0].lower() not in _GEM_REPORT_TAGS:
            # Not a report/briefing — either a different card type or the view
            # argument has drifted onto another listing. Skip rather than guess.
            continue
        title_match = _GEM_TITLE_RE.search(body)
        title = html.unescape(_strip_html(title_match.group(1) if title_match else "")).strip()
        title = re.sub(r"\s+", " ", title)
        if not title:
            continue
        date_match = _GEM_DATE_RE.search(body)
        cards.append({
            "slug": href.rsplit("/", 1)[-1],
            "link": urllib.parse.urljoin(_GEM_ORIGIN, href),
            "title": title,
            "date_text": _strip_html(date_match.group(1) if date_match else "").strip(),
            "topics": tags[1:],
        })
    return cards


def _gem_exact_dates():
    """Map slug → exact pubDate from the sitewide RSS feed.

    rss.xml only carries the 10 newest items sitewide, but those are exactly
    the ones sitting near the 30-day cutoff where a month-only guess does the
    most damage. Best-effort: a failure here just means coarser dates.
    """
    dates = {}
    try:
        content = _fetch_url_bytes(_GEM_RSS_URL, timeout=20)
        root = ET.fromstring(content)
    except Exception as e:
        print(f"  [WARN] GEM rss.xml unavailable ({str(e)[:60]}); using month-only dates")
        return dates

    for item in root.findall(".//item"):
        link = (item.findtext("link") or "").strip()
        if "/research/" not in link:
            continue
        try:
            dt = parsedate_to_datetime(item.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dates[link.rstrip("/").rsplit("/", 1)[-1]] = dt
    return dates


@scraper
def fetch_gem(feed_config):
    """Fetch reports and briefings from Global Energy Monitor."""
    body = urllib.parse.urlencode(_GEM_VIEW).encode("utf-8")
    payload = _fetch_url(
        _GEM_AJAX_URL,
        accept="application/json",
        feed_config=feed_config,
        data=body,
        extra_headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        },
    )

    markup = "".join(
        cmd.get("data") or ""
        for cmd in json.loads(payload)
        if isinstance(cmd, dict) and cmd.get("command") == "insert"
    )
    cards = _gem_parse_cards(markup)
    exact = _gem_exact_dates() if cards else {}

    articles = []
    for card in cards:
        dt = exact.get(card["slug"]) or _gem_month_start(card["date_text"])
        if not _is_fresh(dt):
            continue
        articles.append(
            _make_article(card["title"], card["link"], dt, ", ".join(card["topics"]), feed_config)
        )

    articles.sort(key=lambda a: a["date"] or datetime.min.replace(tzinfo=IST_TZ), reverse=True)
    return articles


# ── Apollo (Insights + Daily Spark) ───────────────────────────────────

_APOLLO_BASE = "https://www.apollo.com"
_APOLLO_DAILY_SPARK_PAGE = f"{_APOLLO_BASE}/insights-news/insights/daily-spark"
# The servlet behind the insights card grid, newest first. pageOffset is
# 1-based: pageOffset=0 answers HTTP 500. So does server-side format
# filtering (selectedFilter=apollo:format/...), so the unfiltered list is
# fetched and formats are filtered here instead.
_APOLLO_INSIGHTS_API = (
    f"{_APOLLO_BASE}/api/int.insight.json"
    "?selectedFilter=&pageOffset=1&listLimit=30&showBento=false&bentoListLimit=3"
    "&currentPagePath=/content/apolloaem/global/en/general-public/insights-news/insights"
    "&isHiderecentArticle=false&authoredTags=&authoredAndTags=&dateFormat=MMMM%20dd,%20yyyy"
)
# Reports keeps the written research; podcasts and videos go to the
# YouTube tab via the separate apollo:media feed.
_APOLLO_REPORT_FORMATS = {"apollo:format/whitepaper", "apollo:format/article"}
_APOLLO_MEDIA_FORMATS = {"apollo:format/podcast", "apollo:format/video"}
# Matches what a YouTube channel feed contributes to the tab.
_APOLLO_MEDIA_LIMIT = 15
_APOLLO_SPARK_CARD_RE = re.compile(
    r'<div class="blog-detail">.*?'
    r'blog-detail-info-eyebrow-text">(?P<eyebrow>[^<]*)</span>.*?'
    r'blog-detail-info-date">(?P<date>[^<]*)</p>.*?'
    r'<a class="blog-detail-info-title" href="(?P<href>[^"]+)">(?P<title>.*?)</a>',
    re.DOTALL,
)


def _fetch_apollo_insight_items(feed_config):
    """Fetch the newest insight.json cards; [] if the payload shape changed."""
    raw = _fetch_url(_APOLLO_INSIGHTS_API, accept="application/json", feed_config=feed_config)
    payload = json.loads(raw)
    if not isinstance(payload, list):
        print(f"  [WARN] {feed_config['name']}: unexpected payload type {type(payload).__name__}")
        return []
    return payload


def _parse_apollo_insights(payload, feed_config, keep_formats):
    """Map insight.json cards of the given formats onto the standard article dict."""
    articles = []
    for item in payload:
        if not isinstance(item, dict) or item.get("format") not in keep_formats:
            continue
        title = html.unescape(item.get("title") or "").strip()
        path = (item.get("contentPath") or "").strip()
        if not title or not path:
            continue
        link = urllib.parse.urljoin(_APOLLO_BASE, path)
        dt = _parse_date_flexible(item.get("releaseDate"))
        desc = html.unescape(_strip_html(item.get("description") or "")).strip()
        article = _make_article(title, link, dt, desc, feed_config)
        if feed_config.get("category") == "Videos":
            # The YouTube tab renders `thumbnail` and filters on `youtube_bucket`;
            # feeds.py sets both for RSS videos, so mirror that here.
            image = (item.get("featuredImage") or "").strip()
            article["thumbnail"] = urllib.parse.urljoin(_APOLLO_BASE, image) if image else ""
            article["youtube_bucket"] = feed_config.get("youtube_bucket", "")
        articles.append(article)
    return articles


def _parse_apollo_daily_spark(page_html, feed_config):
    """Parse the server-rendered Daily Spark listing (10 newest posts)."""
    articles = []
    for m in _APOLLO_SPARK_CARD_RE.finditer(page_html):
        title = html.unescape(_strip_html(m.group("title"))).strip()
        if not title:
            continue
        link = urllib.parse.urljoin(_APOLLO_BASE, m.group("href").strip())
        dt = _parse_date_flexible(m.group("date"))
        # The category eyebrow is the only descriptive text on a card.
        desc = html.unescape(m.group("eyebrow")).strip()
        articles.append(_make_article(title, link, dt, desc, feed_config))
    if not articles:
        # Zero cards from a 200 page means the markup changed, not a quiet day.
        print(f"  [WARN] {feed_config['name']}: no Daily Spark cards found — page layout may have changed")
    return articles


@scraper
def fetch_apollo(feed_config):
    """Fetch Apollo insights (Reports) or Daily Spark (News)."""
    suffix = feed_config["feed"].split(":", 1)[1].strip()
    if suffix == "insights":
        articles = _parse_apollo_insights(
            _fetch_apollo_insight_items(feed_config), feed_config, _APOLLO_REPORT_FORMATS,
        )
    elif suffix == "daily-spark":
        raw = _fetch_url(_APOLLO_DAILY_SPARK_PAGE, feed_config=feed_config)
        articles = _parse_apollo_daily_spark(raw.decode("utf-8", errors="replace"), feed_config)
    else:
        raise ValueError(f"unknown Apollo feed suffix: {suffix!r}")

    articles.sort(key=lambda a: a["date"] or datetime.min.replace(tzinfo=IST_TZ), reverse=True)
    return articles


def fetch_apollo_media(feed_config):
    """Fetch Apollo podcasts and videos for the YouTube tab.

    Deliberately not @scraper: that wrapper applies the 30-day Reports window,
    but the YouTube tab keeps a channel's latest items whatever their age.
    Error handling and logging mirror the wrapper.
    """
    try:
        articles = _parse_apollo_insights(
            _fetch_apollo_insight_items(feed_config), feed_config, _APOLLO_MEDIA_FORMATS,
        )
        articles.sort(key=lambda a: a["date"] or datetime.min.replace(tzinfo=IST_TZ), reverse=True)
        articles = articles[:_APOLLO_MEDIA_LIMIT]
        print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
        return articles
    except Exception as e:
        print(f"  [FAIL] {feed_config['name']}: {str(e)[:120]}")
        return []


# ── Filter Coffee (News, Stories, This Is Business) ───────────────────

_FILTERCOFFEE_BASE = "https://www.filtercoffee.co"
# A Next.js front end over a Ghost CMS whose own RSS is switched off. The
# /stories page loads posts through a server action ("ghostPosts") that
# forwards a Ghost Content API query string. Its ID changes on every site
# deploy, so it is read out of the page's JS chunk on each run.
_FILTERCOFFEE_ACTION_PAGE = f"{_FILTERCOFFEE_BASE}/stories"
# The daily newsletter (primary tag newsletter-2) already arrives through
# the filtercoffee.substack.com RSS feed, so Ghost leaves it out here.
_FILTERCOFFEE_NEWSLETTER_TAG = "newsletter-2"
_FILTERCOFFEE_QUERY = (
    "limit=40&include=tags&fields=title,slug,published_at,custom_excerpt"
    f"&filter=primary_tag:-{_FILTERCOFFEE_NEWSLETTER_TAG}"
)
_FILTERCOFFEE_CHUNK_RE = re.compile(r'src="(/_next/static/chunks/app/[^"]+\.js)"')
_FILTERCOFFEE_ACTION_RE = re.compile(
    r'createServerReference\)\("([0-9a-f]{20,})"[^)]*"ghostPosts"\)'
)
_FILTERCOFFEE_FLIGHT_RE = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')


def _filtercoffee_action_posts(feed_config):
    """Query Ghost through the site's ghostPosts server action."""
    page = _fetch_url(_FILTERCOFFEE_ACTION_PAGE, feed_config=feed_config).decode("utf-8", "replace")
    action_id = None
    for chunk in _FILTERCOFFEE_CHUNK_RE.findall(page):
        js = _fetch_url(_FILTERCOFFEE_BASE + chunk, accept="*/*", feed_config=feed_config)
        m = _FILTERCOFFEE_ACTION_RE.search(js.decode("utf-8", "replace"))
        if m:
            action_id = m.group(1)
            break
    if not action_id:
        raise ValueError("ghostPosts action ID not found in page JS")

    raw = _fetch_url(
        _FILTERCOFFEE_ACTION_PAGE,
        accept="text/x-component",
        feed_config=feed_config,
        data=json.dumps([_FILTERCOFFEE_QUERY]).encode("utf-8"),
        extra_headers={"Next-Action": action_id, "Content-Type": "text/plain;charset=UTF-8"},
    ).decode("utf-8", "replace")
    # React Server Components stream; line "1:" holds [result, error].
    for line in raw.split("\n"):
        if line.startswith("1:["):
            result, error = json.loads(line[2:])[:2]
            if error or not isinstance(result, dict):
                raise ValueError(f"ghostPosts returned an error: {str(error)[:80]}")
            return result.get("posts") or []
    raise ValueError("ghostPosts response had no result line")


def _filtercoffee_blog_posts(feed_config):
    """Fallback: the six newest posts streamed into the /blog page."""
    page = _fetch_url(f"{_FILTERCOFFEE_BASE}/blog", feed_config=feed_config).decode("utf-8", "replace")
    flight = "".join(json.loads(s) for s in _FILTERCOFFEE_FLIGHT_RE.findall(page))
    start = flight.find('"posts":[')
    if start < 0:
        return []
    posts, _ = json.JSONDecoder().raw_decode(flight, start + len('"posts":'))
    return posts


@scraper
def fetch_filtercoffee(feed_config):
    """Fetch Filter Coffee's non-newsletter posts (News, Stories, This Is Business)."""
    try:
        posts = _filtercoffee_action_posts(feed_config)
    except Exception as e:
        print(f"  [WARN] {feed_config['name']}: server action failed ({str(e)[:80]}), using /blog")
        posts = _filtercoffee_blog_posts(feed_config)

    articles = []
    for post in posts:
        tags = post.get("tags") or []
        # Ghost lists the primary tag first; it is also the URL's section.
        section = (tags[0].get("slug") if tags else "") or ""
        slug = (post.get("slug") or "").strip()
        title = html.unescape(post.get("title") or "").strip()
        if not section or not slug or not title or section == _FILTERCOFFEE_NEWSLETTER_TAG:
            continue
        link = f"{_FILTERCOFFEE_BASE}/{section}/{slug}"
        # Ghost stamps UTC with an offset ("…T04:01:15.000+00:00");
        # _parse_date_flexible would drop the offset and read it as IST.
        try:
            dt = datetime.fromisoformat(post.get("published_at") or "").astimezone(IST_TZ)
        except ValueError:
            dt = None
        desc = (post.get("custom_excerpt") or post.get("excerpt") or "").strip()
        articles.append(_make_article(title, link, dt, desc, feed_config))

    articles.sort(key=lambda a: a["date"] or datetime.min.replace(tzinfo=IST_TZ), reverse=True)
    return articles


# ── Dispatcher ────────────────────────────────────────────────────────

# Maps feed prefix → fetcher function
# ── Broker stock notes (Reports → "Stock notes") ─────────────────────
# One broker's call on one Indian stock: rating, target, PDF. Shared
# cleanup (broker names, Indian-only filter, dedup) is in stock_notes.py
# so the direct broker-site scrapers planned next can reuse it.

_MC_IDEAS_API = "https://api.moneycontrol.com/mcapi/v1/broker-research/stock-ideas"
_MC_IDEAS_PAGE_SIZE = 100
_MC_IDEAS_MAX_PAGES = 12  # ~25 calls/day → a 14-day window is ~4 pages
_BS_MEDIA_HOST = "https://bsmedia.business-standard.com"


def _stock_note(feed_config, *, broker, company, rating, target, reco_price, dt, pdf,
                prev_target=None, prev_rating=None):
    """Build a Reports article for one broker call (shared by all sources)."""
    article = _make_article(note_title(company, rating, target), pdf, dt, "", feed_config)
    article.update({
        "publisher": broker,
        "region": "Indian",
        "kind": STOCK_NOTE_KIND,
        "via": feed_config.get("publisher", ""),
        "company": company,
        "rating": rating,
        "target": target,
        "reco_price": reco_price,
        "prev_target": prev_target,
        "prev_rating": prev_rating,
    })
    return article


def _ist_date(value, fmt):
    try:
        return datetime.strptime(str(value or "").strip()[:10], fmt).replace(tzinfo=IST_TZ)
    except ValueError:
        return None


@scraper
def fetch_moneycontrol_ideas(feed_config):
    """Moneycontrol's broker-research JSON API (public, no login).

    Every row has a public PDF on images.moneycontrol.com plus the broker's
    previous call on the stock (`stock_data.previous`), which gives
    "target cut from ₹290" for free. Newest first, so page until a whole
    page is older than the feed's window.
    """
    cutoff = _feed_cutoff(feed_config)
    articles = []
    for page in range(feed_config.get("max_pages") or _MC_IDEAS_MAX_PAGES):
        url = (f"{_MC_IDEAS_API}?start={page * _MC_IDEAS_PAGE_SIZE}"
               f"&limit={_MC_IDEAS_PAGE_SIZE}&deviceType=W")
        raw = _fetch_url(url, accept="application/json", feed_config=feed_config)
        rows = (json.loads(raw.decode("utf-8", errors="replace")) or {}).get("data") or []
        if not isinstance(rows, list) or not rows:
            break
        any_fresh = False
        for row in rows:
            # Report date, unless it falls after the day Moneycontrol posted
            # the note — that is a typo on their side (seen: posted 2 Nov,
            # dated 11 Nov), and a future date would pin it to the top.
            report_dt = _ist_date(row.get("target_price_date"), "%Y-%m-%d")
            posted_dt = _ist_date(row.get("entry_date"), "%Y-%m-%d")
            dt = min(d for d in (report_dt, posted_dt) if d) if (report_dt or posted_dt) else None
            if not _is_fresh(dt, cutoff):
                continue
            any_fresh = True
            broker = canonical_broker(row.get("organization"))
            pdf = (row.get("attachment") or "").strip()
            company = clean_company(row.get("stkname") or row.get("stockShortName"))
            if not broker or not pdf.startswith("http") or not company:
                continue
            prev = ((row.get("stock_data") or {}).get("previous")) or {}
            same_broker = prev and canonical_broker(prev.get("P_ORGANIZATION")) == broker
            articles.append(_stock_note(
                feed_config,
                broker=broker,
                company=company,
                rating=canonical_rating(row.get("recommend_flag")),
                target=parse_price(row.get("target_price")),
                reco_price=parse_price(row.get("recommended_price")),
                dt=dt,
                pdf=pdf,
                prev_target=parse_price(prev.get("target_price")) if same_broker else None,
                prev_rating=canonical_rating(prev.get("recommend_flag")) if same_broker else None,
            ))
        if not any_fresh or len(rows) < _MC_IDEAS_PAGE_SIZE:
            break
    articles.sort(key=lambda a: a["date"] or datetime.min.replace(tzinfo=IST_TZ), reverse=True)
    return articles


@scraper
def fetch_bs_research(feed_config):
    """Business Standard's research-report page (Next.js).

    The whole list (~2.7k rows, back to 2024) is embedded in __NEXT_DATA__
    → props.pageProps.response2.data, so one fetch gets everything. Dates
    are DD/MM/YYYY; PDFs sit on bsmedia. Mostly brokers Moneycontrol lacks
    (JM, Elara, Edelweiss, InCred, YES); overlaps are removed downstream
    by dedup_stock_notes().
    """
    cutoff = _feed_cutoff(feed_config)
    page = _fetch_url(feed_config["url"], feed_config=feed_config).decode("utf-8", errors="replace")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        raise ValueError("no __NEXT_DATA__ on page")
    rows = json.loads(m.group(1))["props"]["pageProps"]["response2"]["data"]
    articles = []
    for row in rows:
        dt = (_ist_date(row.get("recommedation_date"), "%d/%m/%Y")  # sic: the site's spelling
              or _ist_date(row.get("brokertips_date"), "%d/%m/%Y"))
        if dt is None or not _is_fresh(dt, cutoff):
            continue
        broker = canonical_broker(row.get("broker_name"))
        pdf_path = (row.get("pdf_path") or "").strip()
        company = clean_company(row.get("company_full_name") or row.get("company_name"))
        if not broker or not pdf_path or not company:
            continue
        articles.append(_stock_note(
            feed_config,
            broker=broker,
            company=company,
            rating=canonical_rating(row.get("action")),
            target=parse_price(row.get("target_price")),
            reco_price=parse_price(row.get("price")),
            dt=dt,
            pdf=urllib.parse.urljoin(_BS_MEDIA_HOST, pdf_path),
        ))
    articles.sort(key=lambda a: a["date"], reverse=True)
    return articles


# ── Brokers' own sites (Stock notes, Nov 2026) ───────────────────────
# Seven brokers that publish single-stock PDFs without a login (map from
# India Research Hub's scrapers; recipes re-written, not copied). `via` is
# empty, so dedup_stock_notes() keeps these over a Moneycontrol/BS copy of
# the same note — "skip the middleman" (user, Nov 2026). Locked sites stay
# on the aggregators: Motilal Oswal, Anand Rathi, Emkay, Geojit (login),
# Sharekhan (OTP), Nirmal Bang (sign-up form).
#
# Some sources need one extra request per report (PL's report page for the
# PDF, Kotak's PDF header or ICICI's page 1 for the date). Links and pages
# already in static/stock_notes.json are skipped, and `max_lookups` caps
# the rest, so an hourly run makes a handful of requests per broker.

_KNOWN_NOTES = None
_NAME_SPELLINGS = None
_KNOWN_NOTES_LOCK = threading.Lock()
_DEFAULT_MAX_LOOKUPS = 40
_FORM_HEADERS = {"Content-Type": "application/x-www-form-urlencoded"}
_MONTH_DATE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-]+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,.\-]+(20\d\d)\b"
    r"|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", re.I)


def _known_notes(feed_config):
    """Links and broker pages already archived (tests pass `_known`)."""
    if "_known" in feed_config:
        return feed_config["_known"]
    _load_archive_lookups()
    return _KNOWN_NOTES


def _load_archive_lookups():
    global _KNOWN_NOTES, _NAME_SPELLINGS
    with _KNOWN_NOTES_LOCK:
        if _KNOWN_NOTES is None:
            archive = load_archive(STOCK_NOTES_ARCHIVE)
            _KNOWN_NOTES = known_note_keys(archive)
            _NAME_SPELLINGS = archive_spellings(archive)


def archive_spellings(entries):
    """lowercased company → the spelling Moneycontrol/BS use most ("ICICI Bank", not "Icici Bank")."""
    counts = {}
    for e in entries:
        name = e.get("company") or ""
        if e.get("via") and name and not name.isupper():
            counts.setdefault(name.lower(), {}).setdefault(name, 0)
            counts[name.lower()][name] += 1
    return {k: max(v, key=v.get) for k, v in counts.items()}


def _house_spelling(company, feed_config):
    """Sites that shout ("CIPLA", "MAHINDRA & MAHINDRA LTD") get the archive's usual spelling."""
    if "_known" in feed_config:  # tests: no real archive
        spellings = feed_config.get("_spellings", {})
    else:
        _load_archive_lookups()
        spellings = _NAME_SPELLINGS
    return spellings.get(company.lower(), company)


def _tidy_company(raw):
    """'Aarti Industries (ARTO)' / 'MAHINDRA & MAHINDRA LTD' → 'Aarti Industries' / 'Mahindra & Mahindra'."""
    name = re.sub(r"\s+", " ", html.unescape(raw or "")).strip()
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name)  # trailing ticker / short name
    name = re.sub(r"\s+\.", ".", name)               # "J .G. Chemicals" → "J.G. Chemicals"
    name = clean_company(name)
    if name.isupper() and len(name) > 5:
        # Short codes and vowel-less ones stay: M&M, ITC, HDFC, NTPC
        name = " ".join(w if len(w) <= 3 or not re.search(r"[AEIOU]", w) else w.capitalize()
                        for w in name.split())
    return name


def _first_date_in(text):
    """First 'DD Mon YYYY' / 'Month DD, YYYY' in text, as an IST datetime."""
    m = _MONTH_DATE.search(text or "")
    if not m:
        return None
    day, mon, year = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(5), m.group(4), m.group(6))
    try:
        return datetime.strptime(f"{int(day)} {mon[:3].title()} {year}", "%d %b %Y").replace(tzinfo=IST_TZ)
    except ValueError:
        return None


def _parse_day(text, fmt):
    """A whole date string in `fmt` → IST datetime (unlike _ist_date, no 10-char cut)."""
    try:
        return datetime.strptime(str(text or "").strip(), fmt).replace(tzinfo=IST_TZ)
    except ValueError:
        return None


_QUARTER = re.compile(r"\bQ\s*([1-4])\s*[_ ]?\s*(FY|CY)\s*[_ ']?\s*(\d{2})(?!\d)", re.I)
_QUARTER_NB = re.compile(r"\b([1-4])\s*Q\s*(FY|CY)\s*'?(\d{2})(?!\d)", re.I)  # Nirmal Bang writes "2QFY27"
_REPORT_KINDS = [  # (pattern, label) — first match wins
    (r"initiat", "Initiating Coverage"),
    (r"light\s*house", "Light House Update"),
    (r"result\s*preview", "Result Preview"),
    (r"result\s*review", "Result Review"),
    (r"result", "Result Update"),
    (r"management\s*meet|analyst\s*meet", "Management Meet Update"),
    (r"ipo\s*note", "IPO Note"),
    (r"co(mpany)?\s*update", "Company Update"),
    (r"update", "Update"),
]


def report_label(text, default_kind=""):
    """'…Q2_FY_27_Result_Update…' / 'Q2FY27 result update' → 'Q2FY27 Result Update'.

    For brokers whose reports carry no headline (Ventura, Kotak, Way2Wealth:
    page 1 only names the report type), this is the most honest title there is.
    """
    text = re.sub(r"[_+]", " ", urllib.parse.unquote(text or ""))
    q = _QUARTER.search(text) or _QUARTER_NB.search(text)
    quarter = f"Q{q.group(1)}{q.group(2).upper()}{q.group(3)}" if q else ""
    kind = next((label for pat, label in _REPORT_KINDS if re.search(pat, text, re.I)), default_kind)
    return " ".join(p for p in (quarter, kind) if p)


def icici_headline(page_text):
    """ICICI Direct notes print the headline on the line after the report date, ending in '…'."""
    lines = [ln.strip() for ln in (page_text or "").splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        if _first_date_in(line) and len(line) < 40:
            picked = []
            for nxt in lines[i + 1:i + 3]:
                if nxt.startswith((":", "About the stock", "…")):
                    break
                picked.append(nxt)
                if nxt.endswith(("…", "...")):
                    break
            head = re.sub(r"\s*(…|\.\.\.)\s*$", "", " ".join(picked))
            head = re.sub(r"\s+([,;:)])", r"\1", re.sub(r"\s+", " ", head)).strip()
            return head if 8 <= len(head) <= 150 else ""
    return ""


def _direct_note(feed_config, *, company, headline, dt, pdf, target=None, page=None):
    """One note from a broker's own site. Headline only when the site gives a real one."""
    company = _house_spelling(company, feed_config)
    article = _make_article(f"{company}: {headline}" if headline else company, pdf, dt, "", feed_config)
    article.update({
        "publisher": canonical_broker(feed_config.get("publisher")) or feed_config.get("publisher", ""),
        "region": "Indian",
        "kind": STOCK_NOTE_KIND,
        "via": "",
        "company": company,
        "headline": headline or "",
        "target": target,
        "page": page,
    })
    return article


def _polite(feed_config):
    if feed_config.get("polite"):
        time.sleep(feed_config["polite"])


def _form_post(url, fields, feed_config):
    body = urllib.parse.urlencode(fields).encode()
    return _fetch_url(url, feed_config=feed_config, data=body, extra_headers=_FORM_HEADERS).decode("utf-8", "replace")


def _aspnet_hidden(page):
    """ASP.NET WebForms state (__VIEWSTATE etc.) to send back with a postback."""
    fields = {}
    for tag in re.findall(r"<input[^>]*>", page):
        if 'type="hidden"' not in tag:
            continue
        name = re.search(r'name="([^"]+)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name:
            fields[name.group(1)] = html.unescape(value.group(1)) if value else ""
    return fields


# PL Capital (Prabhudas Lilladher): plindia.com/pl-research/, 30 cards a
# page, newest first, ~2.6k reports back to late 2024. Card titles read
# "Safari Industries (India) (SII IN) – Q2FY27 Result Update – Capacity
# expansion to drive growth – BUY". The PDF and exact date are on the
# report's own page; its WordPress REST API is switched off (401).

_PL_TITLE = re.compile(r"^(?P<company>.+?)\s*\((?P<ticker>[A-Z0-9&.\-]+) IN\)\s*(?:[-–—]\s*(?P<rest>.*))?$")
_PL_RATING = re.compile(r"^(strong )?(buy|sell|hold|accumulate|reduce|add|neutral|under ?perform|out ?perform|not rated|nr)$", re.I)
_PL_RATING_MOVE = re.compile(r"^(up|down)grade(d)?\b|^(maintain|retain|reiterate)\w*\s+['‘’\"]?(buy|sell|hold|accumulate|reduce)", re.I)
_REPORT_KIND = re.compile(
    r"\b(result|update|initiating|coverage|preview|q[1-4]\s?fy\s?\d\d|analyst meet|management meet|visit)\b", re.I)


def split_pl_title(title):
    """PL card title → (company, headline). Non-company reports → ('', '')."""
    m = _PL_TITLE.match(re.sub(r"\s+", " ", html.unescape(title or "")).strip())
    if not m:
        return "", ""
    parts = [p.strip(" '\"‘’“”") for p in re.split(r"\s+[-–—]\s+", m.group("rest") or "") if p.strip()]
    while parts and (_PL_RATING.match(parts[-1]) or _PL_RATING_MOVE.match(parts[-1])):
        parts.pop()  # ratings stay off the card (user's call): "BUY", "Downgrade to 'ACCUMULATE'"
    if parts and _REPORT_KIND.search(parts[0]) and len(parts[0].split()) <= 5:
        parts.pop(0)  # "Q2FY27 Result Update" is the report type, not the headline
    return clean_company(m.group("company")), " – ".join(parts)


@scraper
def fetch_plindia(feed_config):
    cutoff = _feed_cutoff(feed_config)
    known = _known_notes(feed_config)
    lookups = feed_config.get("max_lookups", _DEFAULT_MAX_LOOKUPS)
    base = feed_config["url"]
    articles = []
    for page_no in range(1, (feed_config.get("max_pages") or 2) + 1):
        try:
            listing = _fetch_url(base if page_no == 1 else f"{base}page/{page_no}/",
                                 feed_config=feed_config).decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:  # past the last page
                break
            raise
        cards = re.findall(r'<a href="(https://www\.plindia\.com/pl-research/[^"]+)" class="report-card-link">'
                           r'.*?<h3>(.*?)</h3>', listing, re.S)
        if not cards:
            break
        stale = 0
        for page_url, raw_title in cards:
            company, headline = split_pl_title(_strip_html(raw_title))
            if not company or page_url in known:
                continue
            if lookups <= 0:
                return articles
            lookups -= 1
            _polite(feed_config)
            try:
                report = _fetch_url(page_url, feed_config=feed_config).decode("utf-8", "replace")
            except Exception as e:  # one bad report page must not drop the rest
                print(f"  [WARN] PL report page {page_url[-60:]}: {str(e)[:80]}")
                continue
            dm = re.search(r'"datePublished":"([^"]+)"', report)
            pm = re.search(r'class="research-cta">.*?href="([^"]+\.pdf)"', report, re.S | re.I)
            if not dm or not pm:
                continue
            dt = datetime.fromisoformat(dm.group(1)).astimezone(IST_TZ)
            if not _is_fresh(dt, cutoff):
                stale += 1
                continue
            pdf = re.sub(r"^http://", "https://", pm.group(1).replace(" ", "%20"))
            articles.append(_direct_note(feed_config, company=company, headline=headline, dt=dt,
                                         pdf=pdf, page=page_url))
        if stale and stale >= len(cards) - 2:  # whole page past the window
            break
    return articles


# ICICI Securities (ICICI Direct): the "Investing ideas" cards on
# /research/equity — the latest ~15 result notes, each a public PDF on
# mailcontent.icicidirect.com with CMP and target. No date on the card, so
# a new PDF's page 1 is read for it (pdftotext); else the day it was seen.
# A HEAD request is bounced to login; a plain GET returns the PDF.

@scraper
def fetch_icicidirect(feed_config):
    known = _known_notes(feed_config)
    lookups = feed_config.get("max_lookups", _DEFAULT_MAX_LOOKUPS)
    page = _fetch_url(feed_config["url"], feed_config=feed_config).decode("utf-8", "replace")
    now = datetime.now(IST_TZ)
    articles, seen = [], set()
    for m in re.finditer(r'href="(https://mailcontent\.icicidirect\.com/mailcontent/idirect_[^"]+\.pdf)"[^>]*'
                         r"onclick=\"trackCustomEventVPV_researchEquity\('investing_ideas_([^']+)'", page):
        pdf, company = m.group(1), _tidy_company(m.group(2))
        if pdf in seen or pdf in known or not company:
            continue
        seen.add(pdf)
        card = page[max(0, m.start() - 2500):m.start()]
        targets = re.findall(r"Target Price</label>\s*<\w+ class=\"label_value\">(?:<span[^>]*></span>)?([\d,.]+)", card)
        dt, headline = None, ""
        if lookups > 0:
            lookups -= 1
            try:
                text = pdf_first_page_text(pdf, user_agent=UA)
                dt, headline = _first_date_in(text), icici_headline(text)
            except Exception as e:
                print(f"  [WARN] ICICI page 1 {pdf[-40:]}: {str(e)[:80]}")
        if dt is None or dt > now or now - dt > timedelta(days=120):
            dt = now  # unreadable or implausible: the day we first saw it
        headline = headline or report_label(pdf.rsplit("/", 1)[-1].replace("coupdate", "company update"), "Result Update")
        articles.append(_direct_note(feed_config, company=company, headline=headline, dt=dt, pdf=pdf,
                                     target=parse_price(targets[-1]) if targets else None))
    return articles


# Kotak Securities (kotakneo.com): "Opportune" one-pagers, one per
# company (~90), newest edition only. PDFs are public on /uploads/; the
# date comes from the file name when it has one, else the PDF's
# Last-Modified header (GET — HEAD is bounced to a bot check).

def _last_modified(url, feed_config):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/pdf,*/*",
                                               "Referer": feed_config["url"]})
    with urllib.request.urlopen(req, timeout=SCRAPER_FETCH_TIMEOUT * 4, context=SSL_CONTEXT) as resp:
        stamp = resp.headers.get("Last-Modified")  # body is never read
    return parsedate_to_datetime(stamp).astimezone(IST_TZ) if stamp else None


@scraper
def fetch_kotak_opportune(feed_config):
    known = _known_notes(feed_config)
    lookups = feed_config.get("max_lookups", _DEFAULT_MAX_LOOKUPS)
    page = _fetch_url(feed_config["url"], feed_config=feed_config).decode("utf-8", "replace")
    articles, seen = [], set()
    for pdf, label in re.findall(r'href="(https://www\.kotakneo\.com/uploads/[^"]+\.pdf)"[^>]*'
                                 r'title="Download research report PDF for ([^"]+)"', page):
        company = _tidy_company(label)
        if pdf in seen or pdf in known or not company:
            continue
        seen.add(pdf)
        dt = _first_date_in(urllib.parse.unquote(pdf.rsplit("/", 1)[-1]).replace("_", " "))
        if dt is None:
            if lookups <= 0:
                continue
            lookups -= 1
            _polite(feed_config)
            try:
                dt = _last_modified(pdf, feed_config)
            except Exception as e:
                print(f"  [WARN] Kotak PDF date {pdf[-50:]}: {str(e)[:80]}")
        if dt is None:
            continue
        articles.append(_direct_note(feed_config, company=company, dt=dt, pdf=pdf,
                                     headline=report_label(pdf.rsplit("/", 1)[-1], "Update")))
    return articles


# SBI Securities: the research page's Angular app calls
# /apiconnect/research/getreports with an AES-CBC-wrapped body. Key and
# IV are fixed strings shipped in the site's public JS bundle (the hub's
# recipe), so this is an encoding, not a login. openssl does the AES —
# no Python crypto package needed. Only the single-stock lists are read.

_SBI_API = "https://www.sbisecurities.in/apiconnect/research/getreports"
_SBI_KEY = b"12345678901234567890123456789012"
_SBI_IV = b"1234567890123456"
_SBI_LISTS = ("Pick Of the Day", "Pick Of the Week", "IPO notes")


def _sbi_aes(data, decrypt=False):
    cmd = ["openssl", "enc", "-aes-256-cbc", "-K", _SBI_KEY.hex(), "-iv", _SBI_IV.hex(), "-base64", "-A"]
    return subprocess.run(cmd + (["-d"] if decrypt else []), input=data, capture_output=True,
                          check=True, timeout=30).stdout


def split_sbi_desc(desc):
    """'Pick of the Day (Short Term Delivery Call)_ITC Hotels Ltd.' → ('ITC Hotels', 'Pick of the Day (Short Term Delivery Call)')."""
    parts = [p.strip(" ._") for p in re.split(r"_+", desc or "") if p.strip(" ._")]
    label = next((p for p in parts if re.search(r"pick of the|ipo note", p, re.I)), "")
    rest = [p for p in parts if p != label]
    company = _tidy_company(" ".join(rest)) if label and rest else ""
    if not company:  # 'Acme Ltd IPO Note' without an underscore
        m = re.match(r"(.+?)\s+IPO note\s*$", desc or "", re.I)
        company, label = (_tidy_company(m.group(1)), "IPO note") if m else ("", label)
    return company, _sbi_label(label) if company else ""


def _sbi_label(label):
    """One spelling per list ('IPO NOTE', 'IPO Note-01-03-2023', 'Pick of the week' all occur)."""
    low = label.lower()
    if "ipo" in low:
        return "IPO note"
    if "week" in low:
        return "Pick of the Week"
    return "Pick of the Day (short-term delivery call)" if "short term" in low else "Pick of the Day"


@scraper
def fetch_sbisec(feed_config):
    headers = {"Content-Type": "application/json", "Origin": "https://www.sbisecurities.in",
               "Referer": feed_config["url"], "client_id": "no-client"}
    articles = []
    for sub in _SBI_LISTS:
        body = _sbi_aes(json.dumps({"category_name": "fundamental", "sub_category_name": sub}).encode())
        raw = _fetch_url(_SBI_API, accept="application/json", feed_config=feed_config, data=body,
                         extra_headers=headers)
        wrapped = json.loads(raw.decode("utf-8", "replace")).get("response")
        if not wrapped:
            continue
        for row in json.loads(_sbi_aes(wrapped.encode(), decrypt=True)).get("data") or []:
            company, label = split_sbi_desc(row.get("report_desc"))
            link = (row.get("report_link") or "").strip()
            dt = _parse_day(row.get("disp_date"), "%d %b %Y")
            if not company or not link.lower().endswith(".pdf") or dt is None:
                continue
            articles.append(_direct_note(feed_config, company=company, headline=label, dt=dt,
                                         pdf=urllib.parse.quote(link, safe=":/%()")))
    return articles


# Choice Broking: the JSON API behind choiceindia.com/research-listing.
# "Fundamental" rows are institutional research with a PDF; the first line
# of `plain_description` is the report's headline (sometimes run into the
# summary as "Headline: summary…"). "Technical" rows are desk trading calls
# and are skipped. Back to Nov 2024.

_CHOICE_API = "https://finx.choiceindia.com/api/researchreport/v2/api/research-report-new"
_CHOICE_PAGE = 100


def choice_headline(plain):
    line = re.sub(r"\s+", " ", (plain or "").strip().split("\n")[0]).strip()
    if len(line) > 110 and ": " in line:
        line = line.split(": ", 1)[0]
    return line if 8 <= len(line) <= 140 else ""


@scraper
def fetch_choice(feed_config):
    cutoff = _feed_cutoff(feed_config)
    headers = {"Content-Type": "application/json", "Origin": "https://choiceindia.com",
               "Referer": "https://choiceindia.com/"}
    articles = []
    for page_no in range(feed_config.get("max_pages") or 3):
        body = {"end_date": "", "is_expert": 0, "research_type": "", "limit": _CHOICE_PAGE,
                "offset": page_no * _CHOICE_PAGE, "segment": "EQ", "start_date": "", "status": "",
                "subcategory_id": "", "search": "", "id": "", "user_id": ""}
        raw = _fetch_url(_CHOICE_API, accept="application/json", feed_config=feed_config,
                         data=json.dumps(body).encode(), extra_headers=headers)
        rows = ((json.loads(raw.decode("utf-8", "replace")) or {}).get("response") or {}).get("research") or []
        any_fresh = False
        for row in rows:
            dt = (_parse_day(row.get("published_date"), "%Y-%m-%d %H:%M:%S")
                  or _ist_date(row.get("published_date"), "%Y-%m-%d"))
            if dt is None or not _is_fresh(dt, cutoff):
                continue
            any_fresh = True
            pdf = (row.get("file_upload") or "").replace("choiceindia.comresearchfiles", "choiceindia.com/researchfiles")
            company = _tidy_company(row.get("scrip_sec_desc"))
            if row.get("category_name") != "Fundamental" or not pdf.lower().endswith(".pdf") or not company:
                continue
            points = {d.get("key"): d.get("value") for d in row.get("datapoints") or [] if isinstance(d, dict)}
            articles.append(_direct_note(feed_config, company=company,
                                         headline=choice_headline(row.get("plain_description")),
                                         dt=dt, pdf=pdf, target=parse_price(points.get("target"))))
        if not any_fresh or len(rows) < _CHOICE_PAGE:
            break
    return articles


# Way2Wealth: an ASP.NET grid at /research-details/fundamental-research,
# 10 rows a page, one category at a time (postback on the drop-down; pages
# must be stepped through in order — a jump past the visible pager is a
# 500). Captions read "J K Cement Ltd. - Result Update – 09 November 2026";
# event notes and Diwali picks have no company and are skipped.

_W2W_CATEGORIES = ("3", "2", "1")  # Special Reports (default), Updates, Investment Ideas
_W2W_ROW = re.compile(r'grdreport_lblrdate_\d+">([^<]+)</span>.*?href="([^"]+\.pdf)".*?lblcap_\d+">(.*?)</span>', re.S)
_W2W_KIND = re.compile(r"result update|light ?house update|initiating coverage|company update|ipo note|"
                       r"q[1-4]\s?fy\d\d|update$", re.I)


def split_w2w_caption(caption):
    """'J K Cement Ltd. - Result Update – 09 November 2026' → ('J K Cement', 'Result Update')."""
    parts = re.split(r"\s*[-–]\s+", re.sub(r"\s+", " ", html.unescape(_strip_html(caption))).strip())
    if len(parts) < 2 or not _W2W_KIND.search(parts[1]) or re.search(r"event update", parts[1], re.I):
        return "", ""
    return _tidy_company(parts[0]), report_label(parts[1], "Update")


@scraper
def fetch_way2wealth(feed_config):
    cutoff = _feed_cutoff(feed_config)
    url = feed_config["url"]
    first = _fetch_url(url, feed_config=feed_config).decode("utf-8", "replace")
    select = re.search(r'<select name="([^"]*ddlsubcat[^"]*)"', first)
    articles, seen = [], set()
    for cat in _W2W_CATEGORIES:
        if cat == _W2W_CATEGORIES[0]:
            page = first
        elif select:
            page = _form_post(url, {**_aspnet_hidden(first), "__EVENTTARGET": select.group(1),
                                    "__EVENTARGUMENT": "", select.group(1): cat}, feed_config)
        else:
            break
        for page_no in range(1, (feed_config.get("max_pages") or 1) + 1):
            rows = [r for r in _W2W_ROW.findall(page) if r[1] not in seen]
            any_fresh = False
            for date_text, pdf, caption in rows:
                seen.add(pdf)
                dt = _parse_day(date_text, "%d %b %Y")
                if dt is None or not _is_fresh(dt, cutoff):
                    continue
                any_fresh = True
                company, label = split_w2w_caption(caption)
                if company:
                    articles.append(_direct_note(feed_config, company=company, headline=label, dt=dt,
                                                 pdf=urllib.parse.urljoin(url, pdf)))
            if not rows or not any_fresh or f"Page${page_no + 1}" not in page or not select:
                break
            _polite(feed_config)
            page = _form_post(url, {**_aspnet_hidden(page), "__EVENTTARGET": "grdreport",
                                    "__EVENTARGUMENT": f"Page${page_no + 1}", select.group(1): cat}, feed_config)
    return articles


# Ventura Securities (ventura1.com): Research/Recommendation.aspx lists
# company result updates, 10 a page with date, company and PDF. The plain
# page is the newest 10; history needs the date-range search postback plus
# "Next" (129 pages back to Nov 2023). Ventura's PDFs refuse GitHub's IPs
# (403) — fine, readers open them from their own browsers.

_VENTURA_CP = "ctl00$ContentPlaceHolder1$"


def _ventura_rows(page):
    rows = []
    for tr in re.findall(r'<tr>\s*<td class="GridDataCenter">(.*?)</tr>', page, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", '<td class="GridDataCenter">' + tr, re.S)
        link = re.search(r"href='([^']+\.pdf)'", tr, re.I)
        if len(cells) >= 2 and link:
            rows.append((_strip_html(cells[0]).strip(), _strip_html(cells[1]).strip(), link.group(1)))
    return rows


def _ventura_selects(page):
    out = {}
    for name, body in re.findall(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', page, re.S):
        opt = re.search(r'<option selected="selected" value="([^"]*)"', body) or re.search(r'<option value="([^"]*)"', body)
        out[name] = opt.group(1) if opt else ""
    return out


@scraper
def fetch_ventura(feed_config):
    cutoff = _feed_cutoff(feed_config)
    url = feed_config["url"]
    page = _fetch_url(url, feed_config=feed_config).decode("utf-8", "replace")
    max_pages = feed_config.get("max_pages") or 1
    if max_pages > 1:  # history: search from the window's start to today, then step "Next"
        today = datetime.now(IST_TZ)
        start = today - cutoff
        years = re.search(r'DateUsrCtl1\$ddlYear"[^>]*>(.*?)</select>', page, re.S)
        oldest = min((int(y) for y in re.findall(r'value="(\d{4})"', years.group(1))), default=start.year) if years else start.year
        if start.year < oldest:  # the form only offers some years; anything earlier silently returns page 1
            start = datetime(oldest, 1, 1, tzinfo=IST_TZ)
        cp = _VENTURA_CP
        fields = {**_aspnet_hidden(page), **_ventura_selects(page),
                  cp + "HiddenFromDate": start.strftime("%d-%b-%Y"), cp + "HiddenToDate": today.strftime("%d-%b-%Y"),
                  cp + "DateUsrCtl1$ddlYear": str(start.year), cp + "DateUsrCtl1$ddlMonth": start.strftime("%b"),
                  cp + "DateUsrCtl1$ddlDay": start.strftime("%d"),
                  cp + "DateUsrCtl2$ddlYear": str(today.year), cp + "DateUsrCtl2$ddlMonth": today.strftime("%b"),
                  cp + "DateUsrCtl2$ddlDay": today.strftime("%d"), "__EVENTTARGET": cp + "A1"}
        page = _form_post(url, fields, feed_config)
    articles, seen = [], set()
    for _ in range(max_pages):
        rows = [r for r in _ventura_rows(page) if r[2] not in seen]
        any_fresh = False
        for date_text, company, pdf in rows:
            seen.add(pdf)
            dt = _parse_day(date_text, "%d-%b-%Y")
            if dt is None or not _is_fresh(dt, cutoff):
                continue
            any_fresh = True
            company = _tidy_company(company)
            if company:
                articles.append(_direct_note(feed_config, company=company, dt=dt,
                                             headline=report_label(pdf.rsplit("/", 1)[-1], "Result Update"),
                                             pdf=urllib.parse.quote(pdf, safe=":/%")))
        if not rows or not any_fresh or "btnNext" not in page:
            break
        _polite(feed_config)
        page = _form_post(url, {**_aspnet_hidden(page), **_ventura_selects(page),
                                _VENTURA_CP + "btnNext": "Next >"}, feed_config)
    return articles


# IDBI Capital (idbidirect.in): Researchreports.aspx?Option=investment, an
# ASP.NET table (Name | Date), 10 rows a page, newest first, back to 2013.
# Titles read "Astral: Q2FY27 Result Review" — company + report type, no
# headline (page 1 has none either). Technical picks, sector and strategy
# reports share the table and are skipped. Paging is a postback that needs
# the session cookie, so history runs use their own cookie-keeping opener.

_IDBI_ROW = re.compile(r'<td style="text-align: left;">\s*<a class="Txtlink" href="([^"]+\.pdf)"[^>]*>(.*?)</a>\s*</td>'
                       r'\s*<td[^>]*>(.*?)</td>', re.S | re.I)
_IDBI_KEEP = re.compile(r"result review|result update|initiating|company update", re.I)
_IDBI_SKIP = re.compile(r"technical pick|sector|preview|strategy|monthly", re.I)
_IDBI_NEXT = "ctl00$ContentPlaceHolder1$dtpgrGain$ctl02$ctl00"


def split_idbi_title(title):
    """'India Shelter Finance (INDIASHL): Q2FY27 Result Review' → ('India Shelter Finance', 'Q2FY27 Result Review')."""
    title = re.sub(r"\s+", " ", html.unescape(_strip_html(title))).strip()
    if not _IDBI_KEEP.search(title) or _IDBI_SKIP.search(title) or ":" not in title:
        return "", ""
    company, _, kind = title.partition(":")
    return _tidy_company(company), report_label(kind, "Update")


@scraper
def fetch_idbi_capital(feed_config):
    cutoff = _feed_cutoff(feed_config)
    url = feed_config["url"]
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(),
                                         urllib.request.HTTPSHandler(context=SSL_CONTEXT))
    headers = {"User-Agent": UA, "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9", "Referer": url}

    def get(data=None):
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data else None,
                                     headers={**headers, **(_FORM_HEADERS if data else {})})
        with opener.open(req, timeout=SCRAPER_FETCH_TIMEOUT * 3) as resp:
            return resp.read().decode("utf-8", "replace")

    page = get()
    articles, seen = [], set()
    for _ in range(feed_config.get("max_pages") or 1):
        rows = [r for r in _IDBI_ROW.findall(page) if r[0] not in seen]
        any_fresh = False
        for href, title, date_text in rows:
            seen.add(href)
            dt = _parse_day(_strip_html(date_text), "%d-%b-%Y")
            if dt is None or not _is_fresh(dt, cutoff):
                continue
            any_fresh = True
            company, label = split_idbi_title(title)
            if company:
                articles.append(_direct_note(feed_config, company=company, headline=label, dt=dt,
                                             pdf=urllib.parse.quote(urllib.parse.urljoin(url, href), safe=":/%")))
        if not rows or not any_fresh or _IDBI_NEXT not in page:
            break
        _polite(feed_config)
        page = get({**_aspnet_hidden(page), "__EVENTTARGET": _IDBI_NEXT, "__EVENTARGUMENT": ""})
    return articles


# Monarch Networth Capital (mnclgroup.com/research-reports): one static page
# of company blocks, each listing its notes (PDF link, a "Company l BUY l TP"
# line, a month). The exact date and the real headline are on the PDF's
# page 1: "INDIA l Institutional Research l Capital Goods l 3 November 2026",
# then the company/rating line, then the headline. Sector reports and IPO
# notes are skipped. The server leaves out its intermediate certificate, so
# certs/ ships Sectigo's public "DV R36" and verification stays on.

_MNCL_CA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certs", "sectigo-public-server-auth-ca-dv-r36.pem")
_MNCL_SSL = None
_MNCL_BLOCK = re.compile(r'<h2 class="job-title">(.*?)</h2>(.*?)</ul>', re.S)
_MNCL_ITEM = re.compile(r'<a href="([^"]+)"[^>]*>\s*<span class="report-pdf-left">(.*?)</span>\s*'
                        r'<span class="year-reports">(.*?)</span>', re.S)
_MNCL_SKIP = re.compile(r"sector|preview|ipo|strategy|thematic|diwali|outlook", re.I)


def _mncl_ssl():
    global _MNCL_SSL
    if _MNCL_SSL is None:
        ctx = ssl.create_default_context()
        ctx.load_verify_locations(cafile=_MNCL_CA)
        _MNCL_SSL = ctx
    return _MNCL_SSL


def mncl_page_one(text):
    """(date, headline) from MNCL's page 1, either may be None/''."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        if re.search(r"institutional research", line, re.I):
            dt = _first_date_in(line)
            for cand in lines[i + 2:i + 4]:  # after the "Company l BUY l TP" line
                if 8 <= len(cand) <= 140 and len(cand.split()) >= 2 and not re.search(r"\bl\s+(buy|sell|hold|tp)\b|^we\b", cand, re.I):
                    return dt, cand.strip(" \"'“”‘’")
            return dt, ""
    return None, ""


def _month_start(text):
    m = re.match(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{4})", (text or "").strip())
    if not m:
        return None
    try:
        return datetime.strptime(f"1 {m.group(1).title()} {m.group(2)}", "%d %b %Y").replace(tzinfo=IST_TZ)
    except ValueError:
        return None


@scraper
def fetch_mncl(feed_config):
    cutoff = _feed_cutoff(feed_config)
    known = _known_notes(feed_config)
    lookups = feed_config.get("max_lookups", _DEFAULT_MAX_LOOKUPS)
    base = feed_config["url"]
    page = _fetch_url(base, feed_config=feed_config, ssl_context=_mncl_ssl()).decode("utf-8", "replace")
    now = datetime.now(IST_TZ)
    articles, seen = [], set()
    for name, body in _MNCL_BLOCK.findall(page):
        company = _tidy_company(_strip_html(name))
        if not company or _MNCL_SKIP.search(company):
            continue
        for href, title, month in _MNCL_ITEM.findall(body):
            pdf = urllib.parse.urljoin("https://www.mnclgroup.com/", href.strip())
            if not pdf.lower().endswith(".pdf") or pdf in seen or pdf in known or _MNCL_SKIP.search(pdf + " " + title):
                continue
            seen.add(pdf)
            listed = _month_start(_strip_html(month))
            if listed is None or not _is_fresh(listed + timedelta(days=31), cutoff):
                continue  # whole month is older than the window
            dt, headline = None, ""
            if lookups > 0:
                lookups -= 1
                _polite(feed_config)
                try:
                    dt, headline = mncl_page_one(pdf_first_page_text(pdf, user_agent=UA, context=_mncl_ssl()))
                except Exception as e:
                    print(f"  [WARN] MNCL page 1 {pdf[-50:]}: {str(e)[:80]}")
            if dt is None or dt > now:
                dt = now if (listed.year, listed.month) == (now.year, now.month) else listed
            if not _is_fresh(dt, cutoff):
                continue
            articles.append(_direct_note(feed_config, company=company, dt=dt, pdf=pdf,
                                         headline=headline or report_label(pdf.rsplit("/", 1)[-1], "Company Update")))
    return articles


# Nirmal Bang Institutional Equities (nirmalbang.com/nb-research): titles read
# "Fine Organic Industries (FINEORG) - BUY - Chemicals | 2QFY27 Result Update -
# Expansion plans to fructify from FY29 - 09 November 2026". Listing pages come
# from Ajaxpages/ResearchReports.aspx?id=49&pageNo=N (15 a page, back to 2018).
# The site puts a mobile-number form in front of each download, but the PDFs
# are plain public files at /Upload/<name>; the user chose direct links
# (11 Nov 2026). Mornings, macro trackers and "AI Powered Insights" are skipped.

_NB_PAGE = "https://www.nirmalbang.com/Ajaxpages/ResearchReports.aspx?id=49&pageNo={}"
_NB_ITEM = re.compile(r'<div class="rsrchsec">\s*<h2[^>]*>(.*?)</h2>\s*<span[^>]*>(.*?)</span>'
                      r".*?ValidateResearchPDF\('([^']+)','([^']+)'", re.S)
_NB_NOT_STOCK = re.compile(r"economy|sector|strategy|thematic|morning|insights|diwali|picks|tracker|"
                           r"preview|roundup|outlook|monthly|weekly", re.I)
_NB_KIND = re.compile(r"result update|result preview|initiating|company update|update|visit|meet|ipo note", re.I)
_NB_SEP = re.compile(r"\s*[-–]\s+")  # "Result Update - x" and older "Result Update- x"; "Broad-Based" stays whole
_NB_TAIL_RATING = re.compile(r"[;,.]?\s*\b(maintain|retain|reiterate|upgrade|downgrade)\w*\b[^;]*$"
                             r"|[;,.]?\s*\b(buy|sell|hold|accumulate|reduce|neutral)\b\.?$", re.I)


def split_nb_title(title):
    """Nirmal Bang title → (company, headline); ('', '') for anything but a single-stock note."""
    title = re.sub(r"\s+", " ", html.unescape(_strip_html(title))).strip()
    left, bar, right = title.partition("|")
    if not bar:  # before mid-2023: "Company- 4QFY23 Result Update- headline"
        head, *rest = _NB_SEP.split(title)
        left, right = head, " - ".join(rest)
        if not rest or _QUARTER_NB.search(left) or _QUARTER.search(left):
            return "", ""
    if _NB_NOT_STOCK.search(left):
        return "", ""
    parts = [p.strip() for p in _NB_SEP.split(right.strip()) if p.strip()]
    if not parts or not _NB_KIND.search(parts[0]) or re.search(r"economy|sector|strategy", parts[0], re.I):
        return "", ""
    m = re.match(r"(.*?)\s*\(([A-Z0-9&\-]{2,})\)", left)  # first upper-case paren is the ticker
    company = _tidy_company(m.group(1) if m else _NB_SEP.split(left)[0])
    if parts and _first_date_in(parts[-1]) and len(parts[-1]) < 30:
        parts.pop()  # trailing "09 November 2026"
    headline = _NB_TAIL_RATING.sub("", " - ".join(parts[1:])).strip(" -;,")
    return company, headline or report_label(parts[0], "Update")


@scraper
def fetch_nirmal_bang(feed_config):
    cutoff = _feed_cutoff(feed_config)
    articles, seen, stale_pages = [], set(), 0
    first = feed_config.get("start_page") or 1  # history runs can resume part-way
    for page_no in range(first, first + (feed_config.get("max_pages") or 2)):
        page = _fetch_url(_NB_PAGE.format(page_no), feed_config=feed_config,
                          extra_headers={"Referer": feed_config["url"]}).decode("utf-8", "replace")
        raw = _NB_ITEM.findall(page)
        for _retry in range(2):  # the server sometimes answers a burst of requests with a blank page
            if raw:
                break
            time.sleep(5)
            page = _fetch_url(_NB_PAGE.format(page_no), feed_config=feed_config,
                              extra_headers={"Referer": feed_config["url"]}).decode("utf-8", "replace")
            raw = _NB_ITEM.findall(page)
        if not raw:
            break  # past the last page
        items = [i for i in raw if i[2] not in seen]
        any_fresh = False
        for title, date_text, filename, folder in items:
            seen.add(filename)
            dt = _parse_day(_strip_html(date_text), "%d-%b-%y")
            if dt is None or not _is_fresh(dt, cutoff):
                continue
            any_fresh = True
            company, headline = split_nb_title(title)
            if company and filename.lower().endswith(".pdf"):
                pdf = f"https://www.nirmalbang.com/{urllib.parse.quote(folder)}/{urllib.parse.quote(filename)}"
                articles.append(_direct_note(feed_config, company=company, headline=headline, dt=dt, pdf=pdf))
        # One odd page (repeats, a blip) must not end a history run: stop after 3 stale pages.
        stale_pages = 0 if any_fresh else stale_pages + 1
        if stale_pages >= 3:
            break
        _polite(feed_config)
    return articles


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
    "crea:": fetch_crea,
    "gem:": fetch_gem,
    # Before "apollo:": get_report_fetcher matches prefixes in insertion order.
    "apollo:media": fetch_apollo_media,
    "apollo:": fetch_apollo,
    "filtercoffee:": fetch_filtercoffee,
    "mcideas:": fetch_moneycontrol_ideas,
    "bsresearch:": fetch_bs_research,
    # Brokers' own sites → Stock notes
    "plindia:": fetch_plindia,
    "icicidirect:": fetch_icicidirect,
    "kotaksec:": fetch_kotak_opportune,
    "sbisec:": fetch_sbisec,
    "choice:": fetch_choice,
    "way2wealth:": fetch_way2wealth,
    "ventura:": fetch_ventura,
    "idbicap:": fetch_idbi_capital,
    "mncl:": fetch_mncl,
    "nirmalbang:": fetch_nirmal_bang,
}


def get_report_fetcher(feed_field):
    """Return the appropriate fetcher function for a feed field, or None."""
    for prefix, fetcher in REPORT_FETCHERS.items():
        if feed_field.startswith(prefix):
            return fetcher
    return None
