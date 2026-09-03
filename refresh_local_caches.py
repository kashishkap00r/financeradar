#!/usr/bin/env python3
"""
Refresh the caches GitHub Actions cannot populate on its own.

Two Reports sources block datacenter IPs, so CI can never fetch them:

  IEA    iea.org challenges GitHub Actions runners but serves normal
         connections. fetch_iea works here, and the aggregator's
         reports_cache.json entry is what CI falls back to.
  Ember  ember-energy.org challenges everything, including robots.txt.
         Only a real browser gets through — ember_local_fetch.py.
  PIIE   piie.com serves 403 to everything but a real browser, same as
         Ember — piie_local_fetch.py.

Left alone, both age out of the 30-day Reports window and quietly empty.
This script refreshes each, then commits and pushes the two cache files.

It is deliberately conservative: a source that fails is skipped and its
existing cache is left untouched, so a bad run can never make things worse
than not running at all.

Both browser-backed fetchers launch a visible Chrome (headless=False is
required to clear Cloudflare), so this needs DISPLAY set — the systemd unit
passes it through.

Usage:
    python3 refresh_local_caches.py                # all, commit + push
    python3 refresh_local_caches.py --no-push      # refresh only
    python3 refresh_local_caches.py --only iea     # or: ember, piie
    python3 refresh_local_caches.py --check        # report cache ages, no fetch
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
PIIE_CACHE = os.path.join(SCRIPT_DIR, "static", "piie_cache.json")

# Which cache content only this script can produce. On a merge conflict the
# generated-file rule is "take remote", but that is wrong for anything CI
# cannot fetch: taking remote there throws away the fetch we just did, which
# is why the IEA refresh never actually landed. Files CI never writes are
# resolved --ours; keys inside a CI-shared cache are re-applied after the merge.
OWNED_FILES = ("static/ember_cache.json", "static/piie_cache.json")
OWNED_REPORT_KEYS = ("iea-reports",)

# A cache older than this is reported as stale. The Reports window is 30 days,
# so anything past it is already invisible on the site.
STALE_AFTER_DAYS = 30

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


def refresh_piie():
    """Run the Playwright PIIE fetcher. Needs a display; tolerated if it fails."""
    before = _piie_count()
    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, "piie_local_fetch.py")],
        cwd=SCRIPT_DIR, capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        tail = (result.stdout or result.stderr or "").strip().splitlines()
        log(f"PIIE: refresh failed ({tail[-1][:90] if tail else 'no output'}); cache left as-is")
        return False
    log(f"PIIE: {_piie_count()} items cached (was {before})")
    return True


def _piie_count():
    try:
        with open(PIIE_CACHE, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("items", data) if isinstance(data, dict) else data
        return len(items) if isinstance(items, list) else 0
    except (FileNotFoundError, json.JSONDecodeError):
        return 0


def _newest_date(path, key=None):
    """Newest item date in a cache file, as a date string, or None."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if key is not None and isinstance(data, dict):
        items = data.get(key) or []
    elif isinstance(data, dict):
        items = data.get("items", [])
    else:
        items = data
    if not isinstance(items, list):
        return None
    stamps = []
    for it in items:
        if not isinstance(it, dict):
            continue
        raw = it.get("date") or it.get("published") or it.get("t")
        if raw:
            stamps.append(str(raw)[:10])
    return max(stamps) if stamps else None


def check_staleness():
    """Report the age of every cache this script owns.

    The failure mode this exists for: a browser-gated source stops refreshing,
    the aggregator keeps serving the last good cache, CI stays green, and the
    tab quietly shows months-old content. Ageing caches have to be loud.
    """
    from datetime import date

    today = date.today()
    stale = []
    for label, path, key in (
        ("IEA",   REPORTS_CACHE, "iea-reports"),
        ("Ember", EMBER_CACHE,   None),
        ("PIIE",  PIIE_CACHE,    None),
    ):
        newest = _newest_date(path, key)
        if not newest:
            log(f"STALE {label}: no dated items in cache")
            stale.append(label)
            continue
        try:
            age = (today - date.fromisoformat(newest)).days
        except ValueError:
            log(f"STALE {label}: unparseable newest date {newest!r}")
            stale.append(label)
            continue
        if age > STALE_AFTER_DAYS:
            log(f"STALE {label}: newest item {newest} is {age}d old (> {STALE_AFTER_DAYS}d)")
            stale.append(label)
        else:
            log(f"ok    {label}: newest item {newest} ({age}d)")
    return stale


def _ember_count():
    try:
        with open(EMBER_CACHE, "r", encoding="utf-8") as f:
            return len(json.load(f).get("items", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return 0


def _snapshot_owned_report_keys():
    """Copy of the reports_cache entries only this script can fill."""
    try:
        with open(REPORTS_CACHE, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if not isinstance(cache, dict):
        return {}
    return {k: cache[k] for k in OWNED_REPORT_KEYS if k in cache}


def _reapply_owned_report_keys(snapshot):
    """Put our entries back on top of the merged (remote) reports cache."""
    if not snapshot:
        return
    try:
        with open(REPORTS_CACHE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        if not isinstance(cache, dict):
            return
    except (FileNotFoundError, json.JSONDecodeError):
        return
    cache.update(snapshot)
    tmp = REPORTS_CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, REPORTS_CACHE)
    log(f"Re-applied {', '.join(snapshot)} on top of the merged cache")


def commit_and_push():
    """Commit the cache files and push, preserving locally-fetched data on conflict."""
    paths = [p for p in (REPORTS_CACHE, EMBER_CACHE, PIIE_CACHE) if os.path.exists(p)]
    subprocess.run(["git", "add"] + paths, cwd=SCRIPT_DIR, check=False)

    staged = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=SCRIPT_DIR
    ).returncode
    if staged == 0:
        log("No cache changes to push.")
        return True

    subprocess.run(
        ["git", "commit", "-m", "chore: refresh IEA, Ember and PIIE caches"],
        cwd=SCRIPT_DIR, capture_output=True, text=True,
    )

    # Taken before the pull, because the merge is what destroys it.
    owned = _snapshot_owned_report_keys()

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
            ours = [c for c in conflicted if c in OWNED_FILES]
            theirs = [c for c in conflicted if c not in OWNED_FILES]
            log(f"Auto-resolving {len(conflicted)} generated conflicts "
                f"({len(theirs)} --theirs, {len(ours)} --ours)")
            if theirs:
                subprocess.run(["git", "checkout", "--theirs"] + theirs, cwd=SCRIPT_DIR)
            if ours:
                subprocess.run(["git", "checkout", "--ours"] + ours, cwd=SCRIPT_DIR)
            # The remote copy of reports_cache.json cannot contain the sources
            # CI is unable to fetch, so put ours back before committing.
            if "static/reports_cache.json" in theirs:
                _reapply_owned_report_keys(owned)
            subprocess.run(["git", "add"] + conflicted, cwd=SCRIPT_DIR)
            subprocess.run(["git", "commit", "--no-edit"], cwd=SCRIPT_DIR, capture_output=True)
        else:
            log(f"Pull failed with non-generated conflicts: {conflicted}; not pushing")
            return False
    else:
        # A clean merge can still bring in a remote reports_cache without our keys.
        _reapply_owned_report_keys(owned)
        if subprocess.run(["git", "diff", "--quiet", "--", REPORTS_CACHE],
                          cwd=SCRIPT_DIR).returncode != 0:
            subprocess.run(["git", "add", REPORTS_CACHE], cwd=SCRIPT_DIR)
            subprocess.run(["git", "commit", "-m", "chore: restore locally-fetched report caches"],
                           cwd=SCRIPT_DIR, capture_output=True)

    if subprocess.run(["git", "push", "origin", "main"], cwd=SCRIPT_DIR).returncode != 0:
        log("Push failed; will retry next run.")
        return False
    log("Pushed to main.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Refresh CI-unreachable Reports caches")
    parser.add_argument("--only", choices=["iea", "ember", "piie"], help="refresh just one source")
    parser.add_argument("--no-push", action="store_true", help="refresh without committing")
    parser.add_argument("--check", action="store_true",
                        help="report cache ages and exit without fetching")
    args = parser.parse_args()

    if args.check:
        return 1 if check_staleness() else 0

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
    if args.only in (None, "piie"):
        ok.append(refresh_piie())

    if args.no_push:
        log("Skipping push (--no-push).")
    elif any(ok):
        commit_and_push()
    else:
        log("Nothing refreshed; not pushing.")

    fcntl.flock(lock, fcntl.LOCK_UN)

    # Report ages regardless of what refreshed — a source that has been failing
    # for weeks looks identical to one that just failed once unless we say so.
    stale = check_staleness()

    # Non-zero if every requested source failed, or if any cache is past the
    # Reports window, so the timer surfaces it instead of failing silently.
    return 0 if (any(ok) and not stale) else 1


if __name__ == "__main__":
    raise SystemExit(main())
