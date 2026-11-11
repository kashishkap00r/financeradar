"""Which feeds have gone quiet? (Nov 2026, user: "spot broken feeds automatically")

Every hourly run records, per feed, the date of the newest item it has ever
returned (static/feed_health.json). A feed is *quiet* when that date is older
than its limit — a feed that breaks silently (blocked, layout change, dead
URL) stops moving its date, whatever the fetch log says.

    python3 feed_health.py            # print the quiet list
    python3 feed_health.py --report   # also write it to the GitHub job summary
                                      # and exit 1 if anything is quiet (the
                                      # weekly workflow fails → GitHub emails)

Stock-note feeds skip notes already archived, so "0 this run" is normal for
them; their date is the newest note in static/stock_notes.json from that
broker's own site.
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

from articles import IST_TZ

HERE = os.path.dirname(os.path.abspath(__file__))
HEALTH_FILE = os.path.join(HERE, "static", "feed_health.json")

# Days without a new item before a feed counts as quiet. feeds.json can set
# "quiet_days" per feed (e.g. a quarterly publication).
QUIET_DAYS = {"News": 10, "Reports": 30, "Videos": 21}
STOCK_NOTE_QUIET_DAYS = 21
SKIP_CATEGORIES = {"Twitter"}  # tweets have their own freshness checks


def _iso(dt):
    return dt.astimezone(IST_TZ).date().isoformat() if dt else ""


def load_health(path=HEALTH_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_health(data, path=HEALTH_FILE):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def record_run(data, results, now=None):
    """results: {feed_id: (articles returned live, error text or "")}. Updates data in place."""
    now = now or datetime.now(IST_TZ)
    data.setdefault("tracking_since", _iso(now))
    feeds = data.setdefault("feeds", {})
    for feed_id, (articles, error) in results.items():
        entry = feeds.setdefault(feed_id, {})
        dates = [a.get("date") for a in articles if a.get("date")]
        newest = _iso(max(dates)) if dates else ""
        if newest and newest > entry.get("newest", ""):
            entry["newest"] = newest
        entry["last_count"] = len(articles)
        entry["last_run"] = now.isoformat(timespec="minutes")
        if error:
            entry["last_error"] = error[:160]
            entry["last_error_at"] = entry["last_run"]
    return data


def record_stock_notes(data, feeds_config, archive):
    """Stock-note feeds: newest note from the broker's own site (via == '')."""
    from stock_notes import STOCK_NOTE_KIND, canonical_broker
    newest_by_broker = {}
    for e in archive:
        if not e.get("via") and e.get("date"):
            b = e.get("broker")
            if e["date"] > newest_by_broker.get(b, ""):
                newest_by_broker[b] = e["date"]
    feeds = data.setdefault("feeds", {})
    for f in feeds_config:
        if f.get("kind") != STOCK_NOTE_KIND or f.get("feed", "").startswith(("mcideas:", "bsresearch:")):
            continue
        broker = canonical_broker(f.get("publisher")) or f.get("publisher")
        newest = newest_by_broker.get(broker, "")
        entry = feeds.setdefault(f["id"], {})
        if newest and newest > entry.get("newest", ""):
            entry["newest"] = newest
    return data


def quiet_feeds(feeds_config, data, now=None):
    """[(feed, days quiet or None if nothing seen since tracking began, limit)] — quiet ones only."""
    from stock_notes import STOCK_NOTE_KIND
    now = now or datetime.now(IST_TZ)
    today = now.date()
    since = data.get("tracking_since") or today.isoformat()
    out = []
    for f in feeds_config:
        cat = f.get("category", "")
        if cat in SKIP_CATEGORIES or f.get("disabled"):
            continue
        limit = f.get("quiet_days") or (STOCK_NOTE_QUIET_DAYS if f.get("kind") == STOCK_NOTE_KIND
                                        else QUIET_DAYS.get(cat, 30))
        entry = (data.get("feeds") or {}).get(f["id"], {})
        newest = entry.get("newest", "")
        if newest:
            days = (today - datetime.fromisoformat(newest).date()).days
            if days > limit:
                out.append((f, days, limit))
        elif (today - datetime.fromisoformat(since).date()).days > limit:
            out.append((f, None, limit))
    out.sort(key=lambda x: (-(x[1] if x[1] is not None else 10**6), x[0].get("name", "")))
    return out


def report_markdown(quiet, data):
    if not quiet:
        return "All feeds have published within their limits. ✅\n"
    lines = [f"**{len(quiet)} feeds have gone quiet** (no new item within their limit).", "",
             "| Feed | Category | Newest item | Quiet for | Limit | Last error |", "|---|---|---|---|---|---|"]
    for f, days, limit in quiet:
        entry = (data.get("feeds") or {}).get(f["id"], {})
        newest = entry.get("newest") or "never (since tracking began)"
        quiet_for = f"{days} days" if days is not None else "—"
        err = (entry.get("last_error") or "").replace("|", "/")[:80]
        lines.append(f"| {f.get('name', f['id'])} | {f.get('category', '')} | {newest} | {quiet_for} | {limit} days | {err} |")
    lines += ["", f"Tracking since {data.get('tracking_since', '?')}. Limits per feed: `quiet_days` in feeds.json."]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true", help="write the GitHub job summary and exit 1 if any feed is quiet")
    args = ap.parse_args()
    with open(os.path.join(HERE, "feeds.json"), encoding="utf-8") as f:
        feeds_config = json.load(f)
    data = load_health()
    quiet = quiet_feeds(feeds_config, data)
    text = report_markdown(quiet, data)
    print(text)
    if args.report:
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as f:
                f.write("## Quiet feeds\n\n" + text)
        sys.exit(1 if quiet else 0)


if __name__ == "__main__":
    main()
