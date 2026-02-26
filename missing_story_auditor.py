#!/usr/bin/env python3
"""Missing Story Auditor for FinanceRadar."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from auditor.adapters import TAB_NAMES, collect_source_snapshots, normalize_selected_tabs
from auditor.matcher import find_best_match
from auditor.output import write_json, write_text
from config import AUDIT_LOOKBACK_DAYS, AUDIT_SLA_HOURS, AUDIT_MAX_ITEMS_PER_SOURCE


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PUBLISHED_SNAPSHOT = os.path.join(SCRIPT_DIR, "static", "published_snapshot.json")
DEFAULT_AUDIT_ROOT = os.path.join(SCRIPT_DIR, "audit")


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


def _to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _story_id(payload: dict) -> str:
    base = "|".join([
        payload.get("tab", ""),
        payload.get("source_id", ""),
        payload.get("title", ""),
        payload.get("url", ""),
    ])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or "unknown"


def load_published_items(path: str, tabs: set[str]) -> list[dict]:
    """Load flattened published snapshot items."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Published snapshot not found at {path}. Run aggregator.py first."
        )

    import json

    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    published = []
    for tab in TAB_NAMES:
        if tab not in tabs:
            continue
        for item in payload.get(tab, []):
            published.append({
                "tab": tab,
                "source_id": item.get("source_id", ""),
                "source_name": item.get("source_name", ""),
                "publisher": item.get("publisher", ""),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "source_url": item.get("source_url", ""),
                "published_at": item.get("published_at"),
            })
    return published


def classify_story_status(
    source_item: dict,
    published_items: list[dict],
    sla_hours: int,
    now_utc: datetime,
) -> dict | None:
    """Classify one source story against published items.

    Returns a finding dict or None when item is still within SLA and unmatched.
    """
    source_seen_dt = _parse_iso(source_item.get("source_seen_at"))
    expected_by_dt = source_seen_dt + timedelta(hours=sla_hours) if source_seen_dt else None

    match = find_best_match(source_item, published_items)
    matched_item = match["matched_item"] if match else None
    published_dt = _parse_iso(matched_item.get("published_at")) if matched_item else None

    if matched_item:
        if source_seen_dt and expected_by_dt and published_dt and published_dt > expected_by_dt:
            status = "late"
            failure_stage = "render"
        else:
            status = "resolved"
            failure_stage = ""
    else:
        if expected_by_dt and now_utc <= expected_by_dt:
            return None
        status = "missing"
        failure_stage = "filter"

    finding = {
        "tab": source_item.get("tab", ""),
        "source_id": source_item.get("source_id", ""),
        "source_name": source_item.get("source_name", ""),
        "title": source_item.get("title", ""),
        "source_url": source_item.get("url", "") or source_item.get("source_url", ""),
        "source_seen_at": source_item.get("source_seen_at"),
        "expected_by": _to_iso(expected_by_dt),
        "published_at": matched_item.get("published_at") if matched_item else None,
        "status": status,
        "failure_stage": failure_stage,
        "evidence": {
            "match_type": match.get("match_type") if match else None,
            "match_score": match.get("score") if match else None,
            "cross_source_match": match.get("cross_source") if match else None,
            "matched_source_id": matched_item.get("source_id") if matched_item else None,
            "matched_url": matched_item.get("url") if matched_item else None,
            "matched_title": matched_item.get("title") if matched_item else None,
        },
    }
    finding["id"] = _story_id(finding)
    return finding


def make_blocked_finding(source: dict, now_utc: datetime) -> dict:
    """Create blocked-source finding when snapshot could not be collected."""
    finding = {
        "tab": source.get("tab", ""),
        "source_id": source.get("source_id", ""),
        "source_name": source.get("source_name", ""),
        "title": "(source fetch blocked)",
        "source_url": source.get("source_url", ""),
        "source_seen_at": None,
        "expected_by": None,
        "published_at": None,
        "status": "blocked",
        "failure_stage": "fetch",
        "evidence": {
            "error": source.get("error", "unknown fetch error"),
            "detected_at": now_utc.isoformat(),
        },
    }
    finding["id"] = _story_id(finding)
    return finding


def _write_raw_snapshots(raw_snapshots: list[dict], raw_root: str, run_day: str) -> None:
    """Write per-source raw snapshot files."""
    name_counts = defaultdict(int)
    for snapshot in raw_snapshots:
        tab = snapshot.get("tab", "unknown")
        source_key = snapshot.get("source_id") or snapshot.get("source_name") or "unknown"
        base = _slugify(source_key)
        name_counts[(tab, base)] += 1
        suffix = name_counts[(tab, base)]
        filename = f"{base}.json" if suffix == 1 else f"{base}-{suffix}.json"
        path = os.path.join(raw_root, run_day, tab, filename)
        write_json(path, snapshot)


def build_daily_summary(
    findings: list[dict],
    tabs: set[str],
    lookback_days: int,
    sla_hours: int,
    published_count: int,
    source_count: int,
    include_resolved: bool,
) -> str:
    """Render markdown summary for human triage."""
    status_counts = Counter(item.get("status", "unknown") for item in findings)
    by_tab = Counter(item.get("tab", "unknown") for item in findings if item.get("status") in {"missing", "late"})

    source_breakdown = Counter()
    for item in findings:
        if item.get("status") in {"missing", "late", "blocked"}:
            key = f"{item.get('tab', 'unknown')} · {item.get('source_name', 'unknown')}"
            source_breakdown[key] += 1

    top_sources = source_breakdown.most_common(15)
    generated_at = datetime.now(timezone.utc).isoformat()

    lines = [
        "# Missing Story Audit Summary",
        "",
        f"- Generated at (UTC): `{generated_at}`",
        f"- Tabs audited: `{', '.join(sorted(tabs))}`",
        f"- Lookback: `{lookback_days}` days",
        f"- SLA: `{sla_hours}` hours",
        f"- Source-side items checked: `{source_count}`",
        f"- Published items loaded: `{published_count}`",
        f"- Includes resolved findings: `{include_resolved}`",
        "",
        "## Status Counts",
        "",
        f"- Missing: **{status_counts.get('missing', 0)}**",
        f"- Late: **{status_counts.get('late', 0)}**",
        f"- Blocked: **{status_counts.get('blocked', 0)}**",
        f"- Resolved: **{status_counts.get('resolved', 0)}**",
        "",
        "## Missing/Late by Tab",
        "",
    ]

    if by_tab:
        for tab in sorted(by_tab.keys()):
            lines.append(f"- {tab}: **{by_tab[tab]}**")
    else:
        lines.append("- No missing or late findings.")

    lines += ["", "## Top Problem Sources", ""]
    if top_sources:
        for key, count in top_sources:
            lines.append(f"- {key}: **{count}**")
    else:
        lines.append("- None")

    return "\n".join(lines) + "\n"


def run_audit(
    lookback_days: int,
    sla_hours: int,
    tabs,
    max_items_per_source: int,
    published_snapshot_path: str,
    audit_root: str,
    include_resolved: bool = True,
) -> dict:
    """Execute full missing story audit and write artifacts."""
    selected_tabs = normalize_selected_tabs(tabs)
    now_utc = datetime.now(timezone.utc)

    snapshot = collect_source_snapshots(
        selected_tabs=selected_tabs,
        lookback_days=lookback_days,
        max_items_per_source=max_items_per_source,
        script_dir=SCRIPT_DIR,
    )
    source_items = snapshot["source_items"]
    raw_snapshots = snapshot["raw_snapshots"]
    blocked_sources = snapshot["blocked_sources"]

    published_items = load_published_items(published_snapshot_path, selected_tabs)
    published_by_tab = defaultdict(list)
    for item in published_items:
        published_by_tab[item.get("tab", "")].append(item)

    findings = []
    for source_item in source_items:
        finding = classify_story_status(
            source_item=source_item,
            published_items=published_by_tab.get(source_item.get("tab", ""), []),
            sla_hours=sla_hours,
            now_utc=now_utc,
        )
        if finding is None:
            continue
        if finding["status"] != "resolved" or include_resolved:
            findings.append(finding)

    for blocked in blocked_sources:
        findings.append(make_blocked_finding(blocked, now_utc))

    severity_order = {"missing": 0, "late": 1, "blocked": 2, "resolved": 3}
    findings.sort(
        key=lambda item: (
            severity_order.get(item.get("status", "resolved"), 99),
            item.get("tab", ""),
            item.get("source_name", ""),
            item.get("title", ""),
        )
    )

    run_day = now_utc.date().isoformat()
    raw_root = os.path.join(audit_root, "raw")
    results_root = os.path.join(audit_root, "results")
    _write_raw_snapshots(raw_snapshots, raw_root=raw_root, run_day=run_day)

    findings_payload = {
        "generated_at": now_utc.isoformat(),
        "lookback_days": lookback_days,
        "sla_hours": sla_hours,
        "tabs": sorted(selected_tabs),
        "source_item_count": len(source_items),
        "published_item_count": len(published_items),
        "blocked_source_count": len(blocked_sources),
        "findings": findings,
    }
    write_json(os.path.join(results_root, "missing_stories.json"), findings_payload)

    summary = build_daily_summary(
        findings=findings,
        tabs=selected_tabs,
        lookback_days=lookback_days,
        sla_hours=sla_hours,
        published_count=len(published_items),
        source_count=len(source_items),
        include_resolved=include_resolved,
    )
    write_text(os.path.join(results_root, "daily_summary.md"), summary)

    return findings_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit missing stories across FinanceRadar tabs.")
    parser.add_argument("--days", type=int, default=AUDIT_LOOKBACK_DAYS, help="Lookback window in days.")
    parser.add_argument("--sla-hours", type=int, default=AUDIT_SLA_HOURS, help="SLA threshold in hours.")
    parser.add_argument("--tabs", default="all", help="Comma-separated tabs: news,reports,youtube,twitter,telegram,all")
    parser.add_argument(
        "--max-items-per-source",
        type=int,
        default=AUDIT_MAX_ITEMS_PER_SOURCE,
        help="Max source-side items per source during audit.",
    )
    parser.add_argument(
        "--published-snapshot",
        default=DEFAULT_PUBLISHED_SNAPSHOT,
        help="Path to static/published_snapshot.json",
    )
    parser.add_argument("--audit-root", default=DEFAULT_AUDIT_ROOT, help="Audit output root directory.")
    parser.add_argument(
        "--exclude-resolved",
        action="store_true",
        help="Exclude resolved stories from findings output.",
    )
    args = parser.parse_args()

    try:
        payload = run_audit(
            lookback_days=args.days,
            sla_hours=args.sla_hours,
            tabs=args.tabs,
            max_items_per_source=args.max_items_per_source,
            published_snapshot_path=args.published_snapshot,
            audit_root=args.audit_root,
            include_resolved=not args.exclude_resolved,
        )
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}")
        return 1
    except Exception as exc:
        print(f"[ERROR] Audit failed: {exc}")
        return 1

    statuses = Counter(item.get("status", "unknown") for item in payload.get("findings", []))
    print(
        "Audit complete: "
        f"missing={statuses.get('missing', 0)} "
        f"late={statuses.get('late', 0)} "
        f"blocked={statuses.get('blocked', 0)} "
        f"resolved={statuses.get('resolved', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
