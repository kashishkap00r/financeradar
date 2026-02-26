# Missing Story Auditor Design (FinanceRadar)

Date: 2026-02-26  
Owner: FinanceRadar

## Summary

Build an automated deep audit system that checks all four tabs (News, Reports, YouTube, Telegram) and detects stories that are visible on source websites but missing in FinanceRadar.  
Rule chosen: a story is "missing/late" if it does not appear in FinanceRadar within 6 hours of appearing on source side.  
Audit window: last 7 days.  
Execution model: continuous fix loop (audit daily, fix immediately, re-check).

## Goals

1. Detect missing and late stories across all tabs with clear evidence.
2. Identify root cause stage (`fetch`, `parse`, `filter`, `render`) for each miss.
3. Produce daily machine + human readable outputs for fast triage.
4. Reduce unresolved missing stories week-over-week.

## Scope

In scope:
1. Daily automated audits for all configured sources and tabs.
2. Source-side vs published-side comparison.
3. Consistent normalization and matching logic.
4. Daily summary and structured findings.

Out of scope:
1. Auto-fixing code in the auditor itself.
2. Historical backfill beyond 7 days.
3. Frontend UI changes for audit output.

## Architecture

Use a layered checker:
1. Source snapshot layer: collect latest source-side items by tab/source.
2. Pipeline layer: inspect scraper output where needed for root cause.
3. Published layer: compare against FinanceRadar final published output.

New modules:
1. `missing_story_auditor.py` (CLI orchestrator)
2. `auditor/adapters.py` (tab/source adapters)
3. `auditor/matcher.py` (canonical matching + fuzzy fallback)
4. `auditor/output.py` (result writers)

## Data Contracts

### Published snapshot export
`aggregator.py` will write `static/published_snapshot.json`:
1. `generated_at`
2. `news[]`, `reports[]`, `youtube[]`, `telegram[]`
3. Each item: `tab`, `source_id`, `source_name`, `title`, `url`, `published_at`, optional `publisher`

### Finding object
Each audit finding in `audit/results/missing_stories.json`:
1. `id`
2. `tab`
3. `source_id`
4. `source_name`
5. `title`
6. `source_url`
7. `source_seen_at`
8. `expected_by` (source_seen_at + 6 hours)
9. `published_at` (nullable)
10. `status` (`missing`, `late`, `resolved`, `blocked`)
11. `failure_stage` (`fetch`, `parse`, `filter`, `render`)
12. `evidence`

## Matching and SLA Logic

1. Primary key: canonical URL match.
2. Secondary key: normalized title + source identity.
3. Fuzzy fallback: strict threshold, only for same tab and same source.
4. Time comparison always in timezone-aware UTC timestamps.
5. SLA violation:
1. `late` if published but after 6 hours.
2. `missing` if not published and `now > expected_by`.
3. `resolved` if published within 6 hours.

## Outputs

1. `audit/raw/<YYYY-MM-DD>/<tab>/<source>.json` (source snapshots)
2. `audit/results/missing_stories.json` (machine readable findings)
3. `audit/results/daily_summary.md` (plain-English daily report)

Daily summary includes:
1. Total audited sources by tab
2. Missing and late counts by tab/source
3. Top broken sources
4. Root cause stage distribution
5. Fixed today vs still open

## CI and Scheduling

Add workflow: `.github/workflows/missing-story-audit.yml`
1. Trigger: daily schedule
2. Runs after data generation
3. Executes auditor for `--days 7 --sla-hours 6`
4. Uploads `audit/results/*` as artifacts
5. Does not auto-commit fixes

## Tests

New tests:
1. `tests/test_story_matcher.py`
2. `tests/test_missing_story_auditor.py`

Minimum scenarios:
1. On-time match within 6 hours -> `resolved`
2. Match after 6 hours -> `late`
3. No match past SLA -> `missing`
4. Source unavailable -> `blocked`
5. URL mismatch but title match -> valid match
6. Filter exclusion identified as `failure_stage=filter`
7. Cross-tab false positives prevented
8. Timezone correctness around date boundaries

## Rollout Plan

1. Phase 1: local dry-run and output validation.
2. Phase 2: enable daily CI audit with artifacts.
3. Phase 3: continuous fix operations from daily summary.

## Acceptance Criteria

1. 100% configured sources audited daily across all tabs.
2. Every missing/late story includes evidence + failure stage.
3. Daily summary generated reliably.
4. Missing/late backlog trend decreases week-over-week.
