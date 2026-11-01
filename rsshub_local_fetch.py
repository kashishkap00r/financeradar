#!/usr/bin/env python3
"""
Local RSSHub Twitter fetcher.

Run this on your machine (where RSSHub is running on localhost:1200)
to fetch fresh tweets and save them as a cache file that the main
pipeline merges with Google RSS results.

Usage:
    python3 rsshub_local_fetch.py                # fetch + save
    python3 rsshub_local_fetch.py --push         # fetch + save + git commit & push

Requires: RSSHub running locally (npm run dev in rsshub-test/)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import RSSHUB_BASE_URL, RSSHUB_CACHE_FILE

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FEEDS_JSON = os.path.join(SCRIPT_DIR, "feeds.json")
CACHE_PATH = os.path.join(SCRIPT_DIR, RSSHUB_CACHE_FILE)

RETWEET_RE = re.compile(r"^RT\s+", re.IGNORECASE)
X_STATUS_RE = re.compile(r"https?://(?:x|twitter)\.com/([^/]+)/status/(\d+)")
IMG_SRC_RE = re.compile(r'<img[^>]+src="([^"]+pbs\.twimg\.com/[^"]+)"', re.IGNORECASE)
VIDEO_POSTER_RE = re.compile(r'<video[^>]+poster="([^"]+pbs\.twimg\.com/[^"]+)"', re.IGNORECASE)
QUOTE_DIV_RE = re.compile(r'class="rsshub-quote"', re.IGNORECASE)


def load_twitter_handles():
    """Read Twitter handles from feeds.json."""
    with open(FEEDS_JSON, "r", encoding="utf-8") as f:
        feeds = json.load(f)
    handles = []
    for feed in feeds:
        if feed.get("category") != "Twitter":
            continue
        url = feed.get("url", "")
        if "x.com/" in url:
            handle = url.split("x.com/")[-1].strip("/")
            publisher = feed.get("publisher", feed.get("name", handle))
            handles.append({"handle": handle, "publisher": publisher, "id": feed.get("id", "")})
    return handles


def fetch_rsshub_feed(handle, base_url=RSSHUB_BASE_URL, timeout=60):
    """Fetch one handle from RSSHub, return list of article dicts."""
    url = f"{base_url}/twitter/user/{handle}"
    try:
        req = Request(url, headers={"User-Agent": "FinanceRadar-RSSHub/1.0"})
        resp = urlopen(req, timeout=timeout)
        data = resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, Exception) as e:
        return [], str(e)

    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return [], "XML parse error"

    items = root.findall(".//item")
    articles = []
    for item in items:
        title = (item.find("title").text or "").strip() if item.find("title") is not None else ""
        link = (item.find("link").text or "").strip() if item.find("link") is not None else ""
        pub_date = (item.find("pubDate").text or "").strip() if item.find("pubDate") is not None else ""
        author = (item.find("author").text or "").strip() if item.find("author") is not None else ""
        desc = (item.find("description").text or "").strip() if item.find("description") is not None else ""

        # Parse date
        dt = None
        if pub_date:
            try:
                dt = parsedate_to_datetime(pub_date)
            except Exception:
                pass

        # Extract tweet_id from link
        tweet_id = ""
        m = X_STATUS_RE.search(link)
        if m:
            tweet_id = m.group(2)

        if not tweet_id or not link:
            continue

        # Extract first tweet image from description HTML (fallback to video poster)
        image = ""
        img_match = IMG_SRC_RE.search(desc)
        if img_match:
            image = img_match.group(1).replace("&amp;", "&")
        else:
            vid_match = VIDEO_POSTER_RE.search(desc)
            if vid_match:
                image = vid_match.group(1).replace("&amp;", "&")

        # Detect quote tweets (RSSHub wraps them in rsshub-quote div)
        is_quote = bool(QUOTE_DIV_RE.search(desc))

        articles.append({
            "title": title,
            "link": link,
            "date": dt.isoformat() if dt else None,
            "tweet_id": tweet_id,
            "source": author or handle,
            "publisher": "",  # filled by caller
            "source_mode": "rsshub",
            "image": image,
            "is_retweet": bool(RETWEET_RE.match(title)),
            "is_quote": is_quote,
            "is_reply": title.startswith("@"),
            "description_html": desc,
        })

    return articles, None


# Shared with refresh_local_caches.py (the IEA/Ember/PIIE timer) so the two
# local jobs never run git in the same checkout at the same time.
GIT_LOCK_PATH = "/tmp/financeradar-git.lock"
GIT_LOCK_WAIT_SECONDS = 300


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


def _is_generated(path):
    """Files the pipeline rebuilds every run — safe to take GitHub's copy on conflict."""
    return path == "index.html" or path.startswith("static/")


def _merge_in_progress(repo):
    return _git(repo, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0


def _finish_or_abort_merge(repo, cache_rel):
    """Never leave the checkout mid-merge: a stuck merge blocks every later commit.

    If only generated files conflict, take GitHub's copy (but keep our own fresh
    Twitter cache) and finish the merge. If a real source file conflicts, abort —
    that needs a human, and aborting keeps the hourly job working meanwhile.
    Returns True when the merge was completed.
    """
    if not _merge_in_progress(repo):
        return True
    conflicted = _git(repo, "diff", "--name-only", "--diff-filter=U").stdout.splitlines()
    others = [p for p in conflicted if not _is_generated(p)]
    if others:
        print(f"WARNING: merge conflict in source files {others} — aborting merge; "
              "resolve by hand in the main checkout")
        _git(repo, "merge", "--abort")
        return False

    for path in conflicted:
        side = "--ours" if path == cache_rel else "--theirs"
        if _git(repo, "checkout", side, "--", path).returncode == 0:
            _git(repo, "add", "--", path)
        else:  # deleted on the side we wanted
            _git(repo, "rm", "-q", "--", path)
    if conflicted:
        print(f"Auto-resolved {len(conflicted)} generated file conflict(s): {', '.join(conflicted)}")

    done = _git(repo, "commit", "--no-edit")
    if done.returncode != 0:
        print(f"WARNING: could not finish merge — aborting: {done.stderr.strip()[:200]}")
        _git(repo, "merge", "--abort")
        return False
    return True


def _acquire_git_lock(lock_path, wait_seconds):
    import fcntl
    lock = open(lock_path, "w")
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock
        except OSError:
            if time.monotonic() >= deadline:
                lock.close()
                return None
            time.sleep(5)


def sync_cache_to_github(repo, cache_path, message,
                         lock_path=GIT_LOCK_PATH, lock_wait=GIT_LOCK_WAIT_SECONDS):
    """Commit ONLY the Twitter cache, merge GitHub's latest, push. Returns True on push.

    Rules learned the hard way (26 Oct 2026: a week of no tweets):
      * commit just the cache path, so unfinished work that happens to be
        staged never rides along into a "twitter cache" commit;
      * recover from a merge left stuck by an earlier run before anything else;
      * any conflict on a generated file is resolved, never left hanging.
    """
    cache_rel = os.path.relpath(cache_path, repo).replace(os.sep, "/")

    branch = _git(repo, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
    if branch != "main":
        print(f"WARNING: checkout is on '{branch or 'detached HEAD'}', not main — not pushing. "
              "Switch the main checkout back to main.")
        return False

    lock = _acquire_git_lock(lock_path, lock_wait)
    if lock is None:
        print("Another local job holds the git lock; will push next run.")
        return False
    try:
        if _merge_in_progress(repo):
            print("Found a merge left stuck by an earlier run — recovering...")
            _finish_or_abort_merge(repo, cache_rel)

        if _git(repo, "status", "--porcelain", "--", cache_rel).stdout.strip():
            committed = _git(repo, "commit", "-m", message, "--only", "--", cache_rel)
            if committed.returncode != 0:
                print(f"WARNING: commit failed: {(committed.stderr or committed.stdout).strip()[:200]}")
                return False
        else:
            print("Cache unchanged; pushing any earlier commits that are still local.")

        # Two attempts: GitHub Actions may push between our pull and our push.
        for attempt in (1, 2):
            pulled = _git(repo, "pull", "--no-rebase", "--no-edit", "--autostash", "origin", "main")
            if pulled.returncode != 0:
                if not _merge_in_progress(repo):  # network/auth error, not a conflict
                    print(f"WARNING: git pull failed: {pulled.stderr.strip()[:200]}")
                    return False
                if not _finish_or_abort_merge(repo, cache_rel):
                    return False
            pushed = _git(repo, "push", "origin", "main")
            if pushed.returncode == 0:
                print("Pushed to remote.")
                return True
            print(f"Push attempt {attempt} rejected: {pushed.stderr.strip().splitlines()[-1:]}")
        print("WARNING: git push failed — will retry next cycle.")
        return False
    finally:
        lock.close()


def main():
    parser = argparse.ArgumentParser(description="Fetch Twitter via local RSSHub")
    parser.add_argument("--push", action="store_true", help="Git commit and push after saving")
    parser.add_argument("--base-url", default=RSSHUB_BASE_URL, help="RSSHub base URL")
    args = parser.parse_args()

    # Check RSSHub is running
    try:
        urlopen(f"{args.base_url}/healthz", timeout=5)
    except Exception:
        print(f"ERROR: RSSHub not reachable at {args.base_url}")
        print("Start it first: cd rsshub-test && npm run dev")
        sys.exit(1)

    handles = load_twitter_handles()
    print(f"Fetching {len(handles)} handles from RSSHub at {args.base_url}")

    all_items = []
    ok = 0
    empty = 0
    errors = 0

    for i, h in enumerate(handles):
        articles, err = fetch_rsshub_feed(h["handle"], base_url=args.base_url)
        if err:
            errors += 1
            print(f"  [{i+1:2d}/{len(handles)}] @{h['handle']:<22s} ERROR: {err[:60]}")
        elif not articles:
            empty += 1
            print(f"  [{i+1:2d}/{len(handles)}] @{h['handle']:<22s} 0 items (empty/rate-limited)")
        else:
            ok += 1
            for a in articles:
                a["publisher"] = h["publisher"]
            all_items.extend(articles)
            print(f"  [{i+1:2d}/{len(handles)}] @{h['handle']:<22s} {len(articles)} items")

        time.sleep(1)  # stay under rate limit

    # Save cache
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": {
            "source": "rsshub_local",
            "base_url": args.base_url,
            "handles_total": len(handles),
            "handles_ok": ok,
            "handles_empty": empty,
            "handles_error": errors,
            "items_total": len(all_items),
        },
        "items": all_items,
    }

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)

    print(f"\nSaved {len(all_items)} items to {RSSHUB_CACHE_FILE}")
    print(f"  OK: {ok} | Empty: {empty} | Errors: {errors}")

    if args.push:
        print("\nCommitting and pushing...")
        pushed = sync_cache_to_github(
            SCRIPT_DIR, CACHE_PATH, f"chore: update RSSHub twitter cache ({len(all_items)} items)"
        )
        if not pushed:
            sys.exit(2)


if __name__ == "__main__":
    main()
