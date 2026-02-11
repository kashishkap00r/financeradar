#!/usr/bin/env python3
"""
Telegram Channel Fetcher
Scrapes public Telegram channel previews (t.me/s/) and extracts messages.
Zero dependencies — stdlib only.
"""

import json
import os
import re
import urllib.request
import urllib.error
import ssl
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNELS_FILE = os.path.join(SCRIPT_DIR, "telegram_channels.json")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "static", "telegram_reports.json")

SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class TelegramHTMLParser(HTMLParser):
    """Stateful parser that extracts messages from t.me/s/ HTML."""

    def __init__(self):
        super().__init__()
        self.messages = []

        # Current message being built
        self._msg = None

        # State flags
        self._in_message = False
        self._in_text = False
        self._in_owner = False
        self._in_doc_title = False
        self._in_doc_extra = False
        self._in_views = False
        self._text_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        href = attrs_dict.get("href", "")

        # Message wrapper: <div class="tgme_widget_message ..." data-post="channel/123">
        if tag == "div" and "js-widget_message" in cls and "tgme_widget_message " in cls:
            data_post = attrs_dict.get("data-post", "")
            self._msg = {
                "text": "",
                "date": "",
                "url": f"https://t.me/{data_post}" if data_post else "",
                "channel": "",
                "document": None,
                "views": "",
            }
            self._in_message = True

        if not self._in_message or self._msg is None:
            return

        # Text content: <div class="tgme_widget_message_text ...">
        if tag == "div" and "tgme_widget_message_text" in cls and "reply" not in cls:
            self._in_text = True
            self._text_depth = 1

        # Track div nesting inside text block
        elif self._in_text and tag == "div":
            self._text_depth += 1

        # Owner name: <a class="tgme_widget_message_owner_name" ...>
        elif tag == "a" and "tgme_widget_message_owner_name" in cls:
            self._in_owner = True

        # Date/permalink: <a class="tgme_widget_message_date" href="...">
        #   <time datetime="2026-02-11T03:06:01+00:00">
        elif tag == "a" and "tgme_widget_message_date" in cls:
            if href:
                self._msg["url"] = href

        # Time element with datetime
        elif tag == "time":
            dt = attrs_dict.get("datetime", "")
            if dt:
                self._msg["date"] = dt

        # Document title: <div class="tgme_widget_message_document_title" ...>
        elif tag == "div" and "tgme_widget_message_document_title" in cls:
            self._in_doc_title = True
            if self._msg["document"] is None:
                self._msg["document"] = {"title": "", "size": ""}

        # Document size: <div class="tgme_widget_message_document_extra" ...>
        elif tag == "div" and "tgme_widget_message_document_extra" in cls:
            self._in_doc_extra = True
            if self._msg["document"] is None:
                self._msg["document"] = {"title": "", "size": ""}

        # Views: <span class="tgme_widget_message_views" ...>
        elif tag == "span" and "tgme_widget_message_views" in cls:
            self._in_views = True

        # Handle <br/> inside text as newline
        if self._in_text and tag == "br":
            self._msg["text"] += "\n"

    def handle_endtag(self, tag):
        if self._in_text and tag == "div":
            self._text_depth -= 1
            if self._text_depth <= 0:
                self._in_text = False
                self._text_depth = 0

        if self._in_owner and tag == "a":
            self._in_owner = False

        if self._in_doc_title and tag == "div":
            self._in_doc_title = False

        if self._in_doc_extra and tag == "div":
            self._in_doc_extra = False

        if self._in_views and tag == "span":
            self._in_views = False

    def handle_data(self, data):
        if not self._in_message or self._msg is None:
            return

        if self._in_text:
            self._msg["text"] += data
        elif self._in_owner:
            self._msg["channel"] = data.strip()
        elif self._in_doc_title and self._msg["document"] is not None:
            self._msg["document"]["title"] += data.strip()
        elif self._in_doc_extra and self._msg["document"] is not None:
            self._msg["document"]["size"] += data.strip()
        elif self._in_views:
            self._msg["views"] = data.strip()

    def handle_startendtag(self, tag, attrs):
        # Self-closing <br/> inside text
        if self._in_text and tag == "br" and self._msg is not None:
            self._msg["text"] += "\n"

    def close(self):
        super().close()
        # Flush any in-progress message
        if self._msg is not None and self._msg["url"]:
            self.messages.append(self._msg)
            self._msg = None


MAX_PAGES = 15  # Max pagination requests per channel (15 pages x 20 = ~300 msgs)
MAX_AGE_DAYS = 3  # Only keep messages from the last N days


def fetch_url(url):
    """Fetch a URL and return decoded HTML."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(f"  ERROR fetching {url}: {e}")
        return ""


def get_before_id(html):
    """Extract the 'before' pagination ID from the HTML (oldest post ID on the page)."""
    match = re.search(r'data-before="(\d+)"', html)
    return int(match.group(1)) if match else None


def fetch_channel_pages(username):
    """Fetch multiple pages of a channel, paginating with ?before= until MAX_PAGES or MAX_AGE_DAYS."""
    pages = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

    # First page (most recent)
    url = f"https://t.me/s/{username}"
    html = fetch_url(url)
    if not html:
        return pages

    # Check if the channel serves message previews
    if "tgme_widget_message_wrap" not in html:
        print(f"  No preview available (content may be restricted)")
        return pages

    pages.append(html)

    for page_num in range(2, MAX_PAGES + 1):
        before_id = get_before_id(html)
        if not before_id:
            break

        # Check if the oldest date on the current page is already past our cutoff
        dates = re.findall(r'datetime="([^"]+)"', html)
        if dates:
            oldest = min(dates)
            try:
                oldest_dt = datetime.fromisoformat(oldest)
                if oldest_dt < cutoff:
                    print(f"  Reached {MAX_AGE_DAYS}-day cutoff at page {page_num - 1}")
                    break
            except ValueError:
                pass

        url = f"https://t.me/s/{username}?before={before_id}"
        print(f"  Fetching page {page_num} (before={before_id})...")
        html = fetch_url(url)
        if not html or "tgme_widget_message_wrap" not in html:
            break
        pages.append(html)

    return pages


def parse_messages(html, channel_label):
    """Parse messages from Telegram preview HTML."""
    # Quick check: if no widget messages, the channel might not have preview enabled
    if "tgme_widget_message " not in html:
        return []

    # Split HTML into per-message blocks for reliable parsing
    # Each message starts with tgme_widget_message_wrap
    messages = []
    blocks = re.split(r'(?=<div class="tgme_widget_message_wrap)', html)

    for block in blocks:
        if "tgme_widget_message_wrap" not in block:
            continue

        parser = TelegramHTMLParser()
        try:
            parser.feed(block)
            parser.close()
        except Exception:
            continue

        for msg in parser.messages:
            # Clean up text: collapse whitespace, strip
            text = msg["text"].strip()
            text = re.sub(r"\n{3,}", "\n\n", text)
            msg["text"] = text

            # Use config label as fallback channel name
            if not msg["channel"]:
                msg["channel"] = channel_label

            # Remove empty document entries
            if msg["document"] and not msg["document"]["title"]:
                msg["document"] = None

            messages.append(msg)

    return messages


def main():
    print("=" * 50)
    print("Telegram Channel Fetcher")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Load channel config
    if not os.path.exists(CHANNELS_FILE):
        print(f"ERROR: {CHANNELS_FILE} not found")
        return

    with open(CHANNELS_FILE, "r") as f:
        channels = json.load(f)

    print(f"Channels: {len(channels)}")

    all_messages = []
    seen_urls = set()

    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

    for ch in channels:
        username = ch["username"]
        label = ch["label"]
        print(f"\nFetching: {username} ({label})...")

        pages = fetch_channel_pages(username)
        if not pages:
            continue

        channel_count = 0
        for html in pages:
            msgs = parse_messages(html, label)
            for msg in msgs:
                if msg["url"] in seen_urls:
                    continue
                # Filter out messages older than MAX_AGE_DAYS
                if msg["date"]:
                    try:
                        msg_dt = datetime.fromisoformat(msg["date"])
                        if msg_dt < cutoff:
                            continue
                    except ValueError:
                        pass
                seen_urls.add(msg["url"])
                all_messages.append({
                    "text": msg["text"],
                    "date": msg["date"],
                    "url": msg["url"],
                    "channel": msg["channel"],
                    "document": msg["document"],
                    "views": msg["views"],
                })
                channel_count += 1

        print(f"  Total: {channel_count} messages (last {MAX_AGE_DAYS} days, {len(pages)} pages)")

    # Sort by date descending
    all_messages.sort(key=lambda m: m.get("date", ""), reverse=True)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reports": all_messages,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nTotal reports: {len(all_messages)}")
    print(f"Output: {OUTPUT_FILE}")
    print("=" * 50)


if __name__ == "__main__":
    main()
