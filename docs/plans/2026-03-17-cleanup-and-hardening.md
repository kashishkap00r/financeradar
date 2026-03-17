# FinanceRadar: Cleanup & Hardening Plan

> Combined plan covering dead feature removal, completed plan cleanup, security/reliability hardening, CI improvements, and content expansion.

**Date:** 2026-03-17
**Context:** V13 redesign, performance optimization, and all prior design plans are fully shipped. This plan covers everything that remains.

---

## Step 1: Remove LinkedIn Brief Feature ✅

Completed 2026-03-17. Commit `4599b68`.

Deleted `linkedin_brief.py`, `linkedin_post.py`, `linkedin_briefs/`, `linkedin_drafts/`. Removed from `ai-ranking.yml` workflow and `CLAUDE.md`.

---

## Step 2: Delete Completed Plans & Mockups ✅

Completed 2026-03-17. Commit `4599b68` (same as Step 1).

Deleted 5 completed plan docs, all mockup exploration assets (v1-v13), Final_Debug_Plan.md. ~119,800 lines removed.

---

## Step 3: Fix Stray Font Reference ✅

Completed 2026-03-17. Commit `db75957`.

Fixed last `Source Sans Pro` reference in `style.css:1921` → `Nunito Sans`. Zero stray old font refs remain.

---

## Step 4: Security Hardening ✅ (already done)

Verified 2026-03-17. Both items were already fixed in prior sessions:

- **4a: TLS verification** — Already uses try-verified-first, fallback-to-unverified pattern in `feeds.py`, `reports_fetcher.py`, `telegram_fetcher.py`. `SSL_CONTEXT` (verified) is tried first; `SSL_CONTEXT_NOVERIFY` only used on `SSLCertVerificationError` with a `[WARN]` log.
- **4b: URL scheme allowlist** — `sanitizeUrl()` already exists at `app.js:814-819`, rejects anything not `http://` or `https://`. Used at 30+ call sites.

---

## Step 5: Frontend Cleanup ✅ (already done)

Verified 2026-03-17. All items were already fixed in prior sessions:

- **`isBookmarked` duplication** — Only defined once at `app.js:1088`.
- **`localStorage` vs `safeStorage`** — Bookmark functions have their own try/catch wrappers (functionally identical to safeStorage). No change needed.
- **Freshness drift** — All freshness cutoffs now use config constants (`NEWS_FRESHNESS_DAYS`, `REPORTS_FRESHNESS_DAYS`). No mismatch.

---

## Step 6: Reliability Hardening ✅

### 6a: Failure thresholds

Completed 2026-03-17. Commit `3250909`.

- `aggregator.py`: prints warning to stderr when >30% of feeds fail (threshold already existed as `FEED_FAILURE_ALERT_THRESHOLD`, now also prints to stderr for CI visibility)
- `telegram_fetcher.py`: prints warning to stderr when all channels return 0 messages
- `ai_ranker.py`: already handles both-providers-fail gracefully (writes `status: "error"`, frontend shows empty state — correct behavior since stale rankings can still be served)

### 6b: Structured logging

Deferred. Current print-based logging is adequate for the project's scale. Can revisit if pipeline monitoring becomes a need.

---

## Step 7: CI Hardening ✅ (already done)

Verified 2026-03-17. All items were already in place:

- **`--no-rebase` pull** — Both `hourly.yml:69` and `ai-ranking.yml:59` already use `git pull --no-rebase`
- **Pinned actions** — All workflows pin `actions/checkout` and `actions/setup-python` by commit SHA
- **Secret validation** — `hourly.yml` validates all 3 Telegram secrets. `ai-ranking.yml` validates Gemini (OpenRouter intentionally not validated — single-provider degradation is by design)

---

## Step 8: Content Expansion (research only — pending approval)

### 8a: More YouTube channels
- [ ] Research channel IDs for: ET Now, CNBC-TV18, freefincal (in progress)
- [ ] Present to Kashish for approval before adding

### 8b: Telegram bot for private groups
- [ ] Set up a Telegram bot via BotFather
- [ ] Add the bot to `btsreports` and `researchreportss` groups
- [ ] Update `telegram_fetcher.py` to use Bot API or Telethon MTProto for these groups
- [ ] Test locally before enabling in CI

---

## Summary

| Step | Status | Commit |
|------|--------|--------|
| 1. Remove LinkedIn brief | ✅ Done | `4599b68` |
| 2. Delete completed plans | ✅ Done | `4599b68` |
| 3. Fix stray font | ✅ Done | `db75957` |
| 4. Security hardening | ✅ Already done | — |
| 5. Frontend cleanup | ✅ Already done | — |
| 6. Reliability hardening | ✅ Done | `3250909` |
| 7. CI hardening | ✅ Already done | — |
| 8. Content expansion | ⏳ Research in progress | — |
