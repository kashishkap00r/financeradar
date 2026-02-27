"""
Fetcher for external academic-paper aggregator used by the Papers tab.
"""

import html
import json
import re
import urllib.request
from datetime import datetime

from articles import IST_TZ


PAPER_AGGREGATOR_URL = "https://paper-aggregator-india.netlify.app/"
PAPER_FEED_ID = "paper-aggregator-india"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_ARTICLE_RE = re.compile(
    r'(<article\s+class="paper"[^>]*>)(.*?)</article>',
    re.IGNORECASE | re.DOTALL,
)
_PAPER_TITLE_RE = re.compile(
    r'<a[^>]*class="[^"]*\bpaper-title\b[^"]*"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_PAPER_HREF_RE = re.compile(
    r'<a[^>]*class="[^"]*\bpaper-title\b[^"]*"[^>]*href="([^"]+)"',
    re.IGNORECASE | re.DOTALL,
)
_PAPER_AUTHORS_RE = re.compile(
    r'<div[^>]*class="[^"]*\bpaper-authors\b[^"]*"[^>]*>(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
_PAPER_SUMMARY_RE = re.compile(
    r'<div[^>]*class="[^"]*\bpaper-summary\b[^"]*"[^>]*>(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
_PAPER_META_RE = re.compile(
    r'<div[^>]*class="[^"]*\bpaper-meta\b[^"]*"[^>]*>(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
_SOURCE_TAG_RE = re.compile(
    r'<[^>]*class="[^"]*\btag-source\b[^"]*"[^>]*>(.*?)</[^>]+>',
    re.IGNORECASE | re.DOTALL,
)
_SOURCE_LINK_RE = re.compile(
    r'<a[^>]*class="[^"]*\btag-source\b[^"]*"[^>]*href="([^"]+)"',
    re.IGNORECASE | re.DOTALL,
)
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _clean_html(raw):
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_date_yyyy_mm_dd(raw):
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").replace(tzinfo=IST_TZ)
    except ValueError:
        return None


def _data_attr(opening_tag, attr):
    match = re.search(rf'{attr}="([^"]*)"', opening_tag, re.IGNORECASE)
    return html.unescape(match.group(1)).strip() if match else ""


def parse_paper_html(page_html, fetched_at=None):
    """Parse the aggregator HTML page into normalized paper objects."""
    if not page_html:
        return []

    fetched_at = fetched_at or datetime.now(IST_TZ)
    papers = []

    for article_match in _ARTICLE_RE.finditer(page_html):
        opening_tag = article_match.group(1)
        article_body = article_match.group(2)

        title_match = _PAPER_TITLE_RE.search(article_body)
        href_match = _PAPER_HREF_RE.search(article_body)
        summary_match = _PAPER_SUMMARY_RE.search(article_body)
        authors_match = _PAPER_AUTHORS_RE.search(article_body)
        meta_match = _PAPER_META_RE.search(article_body)

        title = _clean_html(title_match.group(1)) if title_match else _data_attr(opening_tag, "data-title")
        link = html.unescape(href_match.group(1)).strip() if href_match else _data_attr(opening_tag, "data-url")
        summary = _clean_html(summary_match.group(1)) if summary_match else ""
        authors = _clean_html(authors_match.group(1)) if authors_match else ""

        meta_block = meta_match.group(1) if meta_match else ""
        source_match = _SOURCE_TAG_RE.search(meta_block)
        source = (
            _clean_html(source_match.group(1))
            if source_match
            else _data_attr(opening_tag, "data-source")
        )
        source = source or "Paper Aggregator"

        source_link_match = _SOURCE_LINK_RE.search(meta_block)
        source_url = html.unescape(source_link_match.group(1)).strip() if source_link_match else ""

        date_match = _DATE_RE.search(meta_block)
        date_value = _parse_date_yyyy_mm_dd(date_match.group(1) if date_match else "")
        date_is_fallback = date_value is None
        if date_value is None:
            date_value = fetched_at

        if not title:
            continue

        papers.append(
            {
                "title": title,
                "link": link,
                "date": date_value,
                "description": summary,
                "authors": authors,
                "source": source,
                "publisher": source,
                "source_url": source_url,
                "category": "Papers",
                "feed_id": PAPER_FEED_ID,
                "date_is_fallback": date_is_fallback,
            }
        )

    epoch_ist = datetime(1970, 1, 1, tzinfo=IST_TZ)
    papers.sort(
        key=lambda item: (
            1 if item.get("date_is_fallback") else 0,
            -((item.get("date") or epoch_ist).timestamp()),
            item.get("title", "").lower(),
        )
    )
    return papers


def fetch_papers(url=PAPER_AGGREGATOR_URL, timeout=20):
    """Fetch and parse papers from the external aggregator page."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        html_text = resp.read().decode("utf-8", errors="replace")
    return parse_paper_html(html_text)


def save_papers_cache(cache_file, papers):
    """Persist papers to cache file with ISO datetime serialization."""
    payload = {
        "generated_at": datetime.now(IST_TZ).isoformat(),
        "papers": [
            {
                **paper,
                "date": paper["date"].isoformat() if paper.get("date") else None,
            }
            for paper in (papers or [])
        ],
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload["generated_at"]


def load_papers_cache(cache_file):
    """Load cached papers; returns (papers, generated_at)."""
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return [], ""

    if isinstance(payload, list):
        raw_papers = payload
        generated_at = ""
    else:
        raw_papers = payload.get("papers", [])
        generated_at = payload.get("generated_at", "")

    papers = []
    for item in raw_papers:
        if not isinstance(item, dict):
            continue
        paper = dict(item)
        date_raw = paper.get("date")
        if date_raw:
            try:
                paper["date"] = datetime.fromisoformat(date_raw)
            except ValueError:
                paper["date"] = None
        else:
            paper["date"] = None
        papers.append(paper)

    return papers, generated_at
