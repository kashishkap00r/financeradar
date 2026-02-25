"""
Custom scrapers for institutional research report sources.

Each function accepts a feed_config dict and returns a list of article dicts
compatible with the standard article format used by fetch_feed() / fetch_careratings().
"""

import html
import json
import re
import urllib.parse
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
        "category": feed_config.get("category", "Reports"),
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


# ── CRISIL Ratings (Press Releases) ───────────────────────────────────

def fetch_crisil_ratings(feed_config):
    """Fetch press releases from CRISIL Ratings newsroom.

    crisilratings.com (AEM CMS) — different site from crisil.com research.
    Each card has: date span, linked title, description paragraph.
    """
    articles = []
    try:
        content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

        # Split on content-wrap to isolate individual press release cards
        cards = re.split(r'class="content-wrap"', content)

        for card in cards[1:]:  # skip preamble before first card
            if len(articles) >= _MAX_PER_SCRAPER:
                break

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
            if len(articles) >= _MAX_PER_SCRAPER:
                break

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

            article = _make_article(title, link, dt, description, feed_config)
            articles.append(article)

        print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
    except Exception as e:
        print(f"  [FAIL] {feed_config['name']}: {str(e)[:50]}")
    return articles


# ── SBI Research ──────────────────────────────────────────────────────

def fetch_sbi_research(feed_config):
    """Fetch Ecowrap economic research papers from SBI Research Desk."""
    articles = []
    try:
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
            if len(articles) >= _MAX_PER_SCRAPER:
                break
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

        print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
    except Exception as e:
        print(f"  [FAIL] {feed_config['name']}: {str(e)[:50]}")
    return articles


# ── FICCI ─────────────────────────────────────────────────────────────

def fetch_ficci(feed_config):
    """Fetch FICCI Daily Economic News Wrap PDF reports."""
    articles = []
    try:
        content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

        dates = [_strip_html(m).strip() for m in re.findall(r'<time[^>]*>(.*?)</time>', content, re.DOTALL)]
        pdfs = re.findall(r'href="(https://ficci\.in/public/storage/sector/Report/[^"]+\.pdf)"', content)

        for date_str, pdf_url in zip(dates, pdfs):
            if len(articles) >= _MAX_PER_SCRAPER:
                break
            try:
                pub_date = datetime.strptime(date_str.strip(), "%b %d, %Y")
            except ValueError:
                pub_date = None
            if not _is_fresh(pub_date):
                continue
            articles.append(_make_article(
                "Economy \u2014 Daily News Wrap", pdf_url, pub_date, "", feed_config
            ))

        print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
    except Exception as e:
        print(f"  [FAIL] {feed_config['name']}: {str(e)[:50]}")
    return articles


# ── ICICI Bank Research ───────────────────────────────────────────────

def fetch_icici_research(feed_config):
    """Fetch reports from ICICI Bank research page via embedded JSON.

    The page embeds ~2000 reports as HTML-entity-encoded JSON inside a hidden
    div with id="ergFilter". Each item has title, description, datetime, and
    pdfLink fields. We decode the JSON and extract fresh reports.
    """
    articles = []
    try:
        content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

        # Extract JSON from hidden div: <div class="hide" id="ergFilter">[...]</div>
        m = re.search(r'id="ergFilter"[^>]*>\s*(\[.*?\])\s*</div>', content, re.DOTALL)
        if not m:
            print(f"  [FAIL] {feed_config['name']}: ergFilter div not found")
            return articles

        raw_json = html.unescape(m.group(1))
        items = json.loads(raw_json)

        for item in items:
            if len(articles) >= _MAX_PER_SCRAPER:
                break

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

        print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
    except Exception as e:
        print(f"  [FAIL] {feed_config['name']}: {str(e)[:50]}")
    return articles


# ── HDFC Securities ───────────────────────────────────────────────────

def fetch_hdfc_sec(feed_config):
    """Fetch from HDFC Securities research via CMS JSON API.

    The reports page loads data client-side from GetNonCallResearch API.
    We fetch two buckets: Periodic Reports (1912) and Institutional Reports (1913).
    """
    articles = []
    base = "https://www.hdfcsec.com"
    buckets = [1912, 1913]  # Periodic, Institutional

    try:
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
                if len(articles) >= _MAX_PER_SCRAPER:
                    break
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

        print(f"  [OK] {feed_config['name']}: {len(articles)} articles")
    except Exception as e:
        print(f"  [FAIL] {feed_config['name']}: {str(e)[:50]}")
    return articles


# ── Axis Direct ───────────────────────────────────────────────────────

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
    try:
        content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

        # Split on each <li to isolate report cards.
        # The report list lives inside a <ul> with each card in its own <li>.
        cards = re.split(r'<li\b', content)

        for card in cards:
            if len(articles) >= _MAX_PER_SCRAPER:
                break

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
    "crisilratings:": fetch_crisil_ratings,
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
