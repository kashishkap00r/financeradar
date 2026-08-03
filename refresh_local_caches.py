#!/usr/bin/env python3
"""
Refresh the caches GitHub Actions cannot populate on its own.

Two Reports sources block datacenter IPs, so CI can never fetch them:

  IEA    iea.org challenges GitHub Actions runners but serves normal
         connections. fetch_iea works here, and the aggregator's
         reports_cache.json entry is what CI falls back to.
  Ember  ember-energy.org challenges everything, including robots.txt.
         Only a real browser gets through — ember_local_fetch.py.

Left alone, both age out of the 30-day Reports window and quietly empty.
This script refreshes each, then commits and pushes the two cache files.

It is deliberately conservative: a source that fails is skipped and its
existing cache is left untouched, so a bad run can never make things worse
than not running at all.

Usage:
    python3 refresh_local_caches.py                # both, commit + push
    python3 refresh_local_caches.py --no-push      # refresh only
    python3 refresh_local_caches.py --only iea     # or: ember
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_CACHE = os.path.join(SCRIPT_DIR, "static", "reports_cache.json")
EMBER_CACHE = os.path.join(SCRIPT_DIR, "static", "ember_cache.json")

# Shared with the rsshub timer so the two never push over each other.
LOCKFILE = "/tmp/financeradar-git.lock"


def log(msg):
    print(f"[refresh] {msg}", flush=True)


def wait_for_network(attempts=30, delay=2):
    """Block until the network is up — user timers can fire right after wake."""
    for i in range(attempts):
        try:
            urllib.request.urlopen("https://github.com", timeout=5)
            return True
        except Exception:
            if i == attempts - 1:
                return False
            time.sleep(delay)
    return False


def refresh_iea():
    """Re-fetch IEA and patch its entry in reports_cache.json.

    Mirrors aggregator.serialize_report_item so CI's cache-fallback path
    reads it back exactly as if the aggregator had written it.
    """
    from reports_fetcher import fetch_iea

    feeds = {f["id"]: f for f in json.load(open(os.path.join(SCRIPT_DIR, "feeds.json")))}
    cfg = feeds.get("iea-reports")
    if not cfg:
        log("IEA: feed iea-reports missing from feeds.json; skipped")
        return False

    items = fetch_iea(cfg)
    if not items:
        # Never overwrite a good cache with nothing — that is the whole point.
        log("IEA: fetch returned nothing; leaving existing cache untouched")
        return False

    try:
        with open(REPORTS_CACHE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        if not isinstance(cache, dict):
            raise ValueError("reports_cache.json is not an object")
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        log(f"IEA: reports_cache.json unreadable ({str(e)[:60]}); skipped")
        return False

    cache["iea-reports"] = [
        {**a, "date": a["date"].isoformat() if a.get("date") else None} for a in items
    ]

    tmp = REPORTS_CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, REPORTS_CACHE)

    log(f"IEA: {len(items)} reports cached (newest {items[0]['date'].strftime('%d %b %Y')})")
    return True


def refresh_ember():
    """Run the Playwright fetcher. Needs a display; tolerated if it fails."""
    before = _ember_count()
    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, "ember_local_fetch.py")],
        cwd=SCRIPT_DIR, capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        tail = (result.stdout or result.stderr or "").strip().splitlines()
        log(f"Ember: refresh failed ({tail[-1][:90] if tail else 'no output'}); cache left as-is")
        return False
    log(f"Ember: {_ember_count()} items cached (was {before})")
    return True


def _ember_count():
    try:
        with open(EMBER_CACHE, "r", encoding="utf-8") as f:
            return len(json.load(f).get("items", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return 0


def commit_and_push():
    """Commit the two cache files and push, taking remote on generated conflicts."""
    paths = [p for p in (REPORTS_CACHE, EMBER_CACHE) if os.path.exists(p)]
    subprocess.run(["git", "add"] + paths, cwd=SCRIPT_DIR, check=False)

    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=SCRIPT_DIR
    ).returncode
    if staged == 0:
        log("No cache changes to push.")
        return True

    subprocess.run(
        ["git", "commit", "-m", "chore: refresh IEA and Ember caches"],
        cwd=SCRIPT_DIR, capture_output=True, text=True,
    )

    pull = subprocess.run(
        ["git", "pull", "--no-rebase", "--no-edit", "--autostash", "origin", "main"],
        cwd=SCRIPT_DIR, capture_output=True, text=True,
    )
    if pull.returncode != 0:
        conflicted = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            cwd=SCRIPT_DIR, capture_output=True, text=True,
        ).stdout.split()
        # Only auto-resolve generated files; anything else needs a human.
        if conflicted and all(c.startswith("static/") or c == "index.html" for c in conflicted):
            log(f"Auto-resolving {len(conflicted)} generated conflicts (--theirs)")
            subprocess.run(["git", "checkout", "--theirs"] + conflicted, cwd=SCRIPT_DIR)
            subprocess.run(["git", "add"] + conflicted, cwd=SCRIPT_DIR)
            subprocess.run(["git", "commit", "--no-edit"], cwd=SCRIPT_DIR, capture_output=True)
        else:
            log(f"Pull failed with non-generated conflicts: {conflicted}; not pushing")
            return False

    if subprocess.run(["git", "push", "origin", "main"], cwd=SCRIPT_DIR).returncode != 0:
        log("Push failed; will retry next run.")
        return False
    log("Pushed to main.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Refresh CI-unreachable Reports caches")
    parser.add_argument("--only", choices=["iea", "ember"], help="refresh just one source")
    parser.add_argument("--no-push", action="store_true", help="refresh without committing")
    args = parser.parse_args()

    if not wait_for_network():
        log("ERROR: no network; aborting")
        return 1

    # Serialise against the rsshub timer, which also commits and pushes.
    import fcntl
    lock = open(LOCKFILE, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
    except OSError:
        log("Could not acquire git lock; skipping")
        return 0

    ok = []
    if args.only in (None, "iea"):
        ok.append(refresh_iea())
    if args.only in (None, "ember"):
        ok.append(refresh_ember())

    if args.no_push:
        log("Skipping push (--no-push).")
    elif any(ok):
        commit_and_push()
    else:
        log("Nothing refreshed; not pushing.")

    fcntl.flock(lock, fcntl.LOCK_UN)
    # Non-zero only if every requested source failed, so the timer surfaces it.
    return 0 if any(ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
