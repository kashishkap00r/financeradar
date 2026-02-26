"""Data collection adapters for missing story audits."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from feeds import load_feeds, fetch_feed, fetch_careratings, fetch_the_ken
from reports_fetcher import get_report_fetcher
from config import FEED_THREAD_WORKERS


TAB_NAMES = ("news", "reports", "youtube", "twitter", "telegram")


def normalize_selected_tabs(selected_tabs) -> set[str]:
    """Normalize tab selection input to canonical tab names."""
    if isinstance(selected_tabs, str):
        raw = [part.strip().lower() for part in selected_tabs.split(",") if part.strip()]
    else:
        raw = [str(part).strip().lower() for part in (selected_tabs or []) if str(part).strip()]

    if not raw or "all" in raw:
        return set(TAB_NAMES)

    aliases = {
        "videos": "youtube",
        "video": "youtube",
        "report": "reports",
        "tg": "telegram",
    }
    normalized = set()
    for tab in raw:
        tab = aliases.get(tab, tab)
        if tab in TAB_NAMES:
            normalized.add(tab)
    return normalized


def _tab_for_feed(feed_cfg: dict) -> str:
    category = (feed_cfg.get("category") or "News").lower()
    if category == "videos":
        return "youtube"
    if category == "twitter":
        return "twitter"
    if category == "reports":
        return "reports"
    return "news"


def _to_iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _parse_iso(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _is_within_lookback(dt: datetime | None, cutoff_dt: datetime) -> bool:
    if dt is None:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= cutoff_dt


def _telegram_source_id(channel: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (channel or "").lower()).strip("-")
    return f"telegram:{slug or 'unknown'}"


def _telegram_title(text: str) -> str:
    if not text:
        return "Untitled Telegram post"
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:220]
    cleaned = text.strip()
    return cleaned[:220] if cleaned else "Untitled Telegram post"


def _fetch_source_items_for_feed(feed_cfg: dict, cutoff_dt: datetime, max_items_per_source: int) -> tuple[list[dict], str | None]:
    """Fetch source-side items for one feed config."""
    feed_field = feed_cfg.get("feed", "")
    try:
        if feed_cfg.get("id") == "the-ken":
            items = fetch_the_ken(feed_cfg)
        elif feed_field.startswith("careratings:"):
            items = fetch_careratings(feed_cfg)
        else:
            report_fetcher = get_report_fetcher(feed_field)
            if report_fetcher:
                items = report_fetcher(feed_cfg)
            else:
                items = fetch_feed(feed_cfg)
    except Exception as exc:  # pragma: no cover - fetchers usually swallow and return []
        return [], str(exc)

    tab = _tab_for_feed(feed_cfg)
    source_items = []
    for item in items or []:
        dt = item.get("date")
        if not _is_within_lookback(dt, cutoff_dt):
            continue
        source_items.append({
            "tab": tab,
            "source_id": feed_cfg.get("id", ""),
            "source_name": feed_cfg.get("name", ""),
            "publisher": item.get("publisher", feed_cfg.get("publisher", "")),
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "source_url": item.get("source_url", feed_cfg.get("url", "")),
            "source_seen_at": _to_iso(dt),
        })
    return source_items[:max_items_per_source], None


def _collect_telegram_source_items(script_dir: str, cutoff_dt: datetime, max_items_per_source: int) -> tuple[list[dict], list[dict], list[dict]]:
    """Collect Telegram source-side items from `static/telegram_reports.json`."""
    telegram_path = os.path.join(script_dir, "static", "telegram_reports.json")
    source_items = []
    raw_snapshots = []
    blocked_sources = []

    try:
        with open(telegram_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        blocked_sources.append({
            "tab": "telegram",
            "source_id": "telegram:all",
            "source_name": "Telegram reports file",
            "source_url": telegram_path,
            "error": "telegram_reports.json not found",
        })
        return source_items, raw_snapshots, blocked_sources
    except json.JSONDecodeError as exc:
        blocked_sources.append({
            "tab": "telegram",
            "source_id": "telegram:all",
            "source_name": "Telegram reports file",
            "source_url": telegram_path,
            "error": f"invalid JSON: {exc}",
        })
        return source_items, raw_snapshots, blocked_sources

    by_channel = defaultdict(list)
    for report in payload.get("reports", []):
        channel = report.get("channel", "") or "Unknown Channel"
        dt = _parse_iso(report.get("date"))
        if not _is_within_lookback(dt, cutoff_dt):
            continue
        item = {
            "tab": "telegram",
            "source_id": _telegram_source_id(channel),
            "source_name": channel,
            "publisher": channel,
            "title": _telegram_title(report.get("text", "")),
            "url": report.get("url", ""),
            "source_url": "",
            "source_seen_at": _to_iso(dt),
        }
        by_channel[item["source_id"]].append(item)

    now_iso = datetime.now(timezone.utc).isoformat()
    for source_id, items in by_channel.items():
        limited = items[:max_items_per_source]
        source_items.extend(limited)
        raw_snapshots.append({
            "tab": "telegram",
            "source_id": source_id,
            "source_name": limited[0]["source_name"] if limited else "Unknown Channel",
            "source_url": "",
            "fetched_at": now_iso,
            "item_count": len(limited),
            "items": limited,
        })

    return source_items, raw_snapshots, blocked_sources


def collect_source_snapshots(
    selected_tabs,
    lookback_days: int,
    max_items_per_source: int,
    script_dir: str,
) -> dict:
    """Collect source-side snapshots across selected tabs."""
    tabs = normalize_selected_tabs(selected_tabs)
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    feeds = load_feeds()

    source_items = []
    raw_snapshots = []
    blocked_sources = []
    now_iso = datetime.now(timezone.utc).isoformat()
    eligible_feeds = [feed_cfg for feed_cfg in feeds if _tab_for_feed(feed_cfg) in tabs]

    futures = {}
    with ThreadPoolExecutor(max_workers=FEED_THREAD_WORKERS) as executor:
        for feed_cfg in eligible_feeds:
            futures[executor.submit(_fetch_source_items_for_feed, feed_cfg, cutoff_dt, max_items_per_source)] = feed_cfg

        for future in as_completed(futures):
            feed_cfg = futures[future]
            tab = _tab_for_feed(feed_cfg)
            try:
                items, error = future.result()
            except Exception as exc:  # pragma: no cover - defensive guard
                items, error = [], str(exc)

            if error:
                blocked_sources.append({
                    "tab": tab,
                    "source_id": feed_cfg.get("id", ""),
                    "source_name": feed_cfg.get("name", ""),
                    "source_url": feed_cfg.get("url", ""),
                    "error": error,
                })
                continue

            source_items.extend(items)
            raw_snapshots.append({
                "tab": tab,
                "source_id": feed_cfg.get("id", ""),
                "source_name": feed_cfg.get("name", ""),
                "source_url": feed_cfg.get("url", ""),
                "fetched_at": now_iso,
                "item_count": len(items),
                "items": items,
            })

    if "telegram" in tabs:
        tg_items, tg_raw, tg_blocked = _collect_telegram_source_items(
            script_dir=script_dir,
            cutoff_dt=cutoff_dt,
            max_items_per_source=max_items_per_source,
        )
        source_items.extend(tg_items)
        raw_snapshots.extend(tg_raw)
        blocked_sources.extend(tg_blocked)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": lookback_days,
        "tabs": sorted(tabs),
        "source_items": source_items,
        "raw_snapshots": raw_snapshots,
        "blocked_sources": blocked_sources,
    }
