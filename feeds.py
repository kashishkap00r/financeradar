"""
Feed loading and fetching utilities.

Handles feed configuration loading, date parsing, RSS/Atom feed fetching,
and CareRatings JSON API fetching.
"""

import json
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import re
import ssl
import os
import subprocess

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
            try:
                with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as response:
                    content = response.read()
            except ssl.SSLCertVerificationError:
                print(f"  [WARN] TLS verification failed for {feed_url}, falling back to unverified")
                req = urllib.request.Request(
                    feed_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9"
                    }
                )
                with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT_NOVERIFY) as response:
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
                    "publisher": feed_config.get("publisher", ""),
                    "feed_id": feed_config["id"],
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
                    "image": image_url,
                    "feed_id": feed_config["id"],
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
