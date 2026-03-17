# FinanceRadar: Cleanup & Hardening Plan

> Combined plan covering dead feature removal, completed plan cleanup, security/reliability hardening, CI improvements, and content expansion.

**Date:** 2026-03-17
**Context:** V13 redesign, performance optimization, and all prior design plans are fully shipped. This plan covers everything that remains.

---

## Step 1: Remove LinkedIn Brief Feature

Delete the LinkedIn brief/post generation pipeline entirely.

**Files to delete:**
- `linkedin_brief.py`
- `linkedin_post.py`
- `linkedin_briefs/` (entire directory)
- `linkedin_drafts/` (entire directory)
- `__pycache__/linkedin_brief.cpython-312.pyc`

**Files to edit:**
- `.github/workflows/ai-ranking.yml` — remove the "Generate LinkedIn brief" step (~line 52-55) and remove `linkedin_briefs/` from the git add (~line 62)
- `CLAUDE.md` — remove linkedin_brief.py and linkedin_post.py from Quick Commands (~line 24-25), Architecture note (~line 65), and workflow table (~line 189)

- [ ] Delete files and directories
- [ ] Edit ai-ranking.yml workflow
- [ ] Edit CLAUDE.md references
- [ ] Commit: `chore: remove LinkedIn brief feature`

---

## Step 2: Delete Completed Plans & Mockups

All of these are for shipped features — no reason to keep them.

**Files to delete:**
- `docs/superpowers/plans/2026-03-13-v13-production-deployment.md`
- `docs/superpowers/plans/2026-03-14-performance-optimization.md`
- `docs/plans/2026-02-26-missing-story-auditor-design.md`
- `docs/plans/2026-02-27-paper-tab-randomized-order-design.md`
- `docs/plans/2026-02-27-twitter-signal-lanes-design.md`
- `docs/plans/assets/` (entire directory — mockups v1-v9, explorations)
- `Final_Debug_Plan.md` (remaining items folded into this plan)

**Also delete empty parent dirs** if `docs/superpowers/plans/` becomes empty.

- [ ] Delete all listed files and directories
- [ ] Commit: `chore: remove completed plans and V13 mockup artifacts`

---

## Step 3: Fix Stray Font Reference + Dead CSS

Quick cleanup pass.

- [ ] Fix `templates/style.css:1921` — change `Source Sans Pro` to `Nunito Sans`
- [ ] Audit CSS for dead selectors (classes not referenced in app.js, aggregator.py, or index.html) and remove them
- [ ] Regenerate site: `python3 aggregator.py`
- [ ] Commit: `chore: fix stray font reference + remove dead CSS`

---

## Step 4: Security Hardening

From Final Debug Plan findings #3 and #4 — the highest-severity security issues.

### 4a: Re-enable TLS certificate verification

TLS verification is globally disabled in `aggregator.py` and `telegram_fetcher.py`. This is a MITM risk.

- [ ] Remove the global `ssl._create_default_https_context = ssl._create_unverified_context` calls
- [ ] Add per-source exception handling: if a specific feed fails with an SSL error, catch it, log it, and skip that feed — don't disable verification for everything
- [ ] Test with `python3 aggregator.py` — identify any feeds that break and add targeted exceptions
- [ ] Commit: `security: re-enable TLS verification with per-source exceptions`

### 4b: Add URL scheme allowlist

Feed URLs are rendered into `<a href>` without protocol validation. `javascript:` or `data:` URLs from a compromised feed could execute code.

- [ ] Add a `sanitize_url(url)` function (in `articles.py` or a new `sanitize.py`) that rejects URLs whose scheme is not `http` or `https`
- [ ] Apply it in `aggregator.py` wherever feed URLs are written into HTML attributes
- [ ] Apply it in `templates/app.js` wherever URLs from JSON are rendered into DOM
- [ ] Add test cases in `tests/` for the sanitizer
- [ ] Commit: `security: add URL scheme allowlist to prevent XSS via feed URLs`

---

## Step 5: Frontend Cleanup

From Final Debug Plan finding #8 — duplicated/inconsistent state logic.

- [ ] Audit `templates/app.js` for duplicate `isBookmarked` definitions and consolidate
- [ ] Audit for raw `localStorage` calls that should use the `safeStorage` wrapper — consolidate
- [ ] Check for freshness drift: verify that the freshness cutoff in code matches the log message (finding #7)
- [ ] Commit: `fix: consolidate bookmark state and localStorage usage`

---

## Step 6: Reliability Hardening

From Final Debug Plan findings #5 and #6.

### 6a: Failure thresholds instead of silent warnings

Currently, fetch/parse failures are downgraded to warnings and the pipeline continues. The system can look green while missing entire data sources.

- [ ] In `aggregator.py`, after fetching all feeds, check: if more than 30% of feeds failed, exit with error code instead of generating a partial site
- [ ] In `telegram_fetcher.py`, if all channels fail, exit with error code
- [ ] In `ai_ranker.py`, if both LLM providers fail, exit with error code (single-provider degradation is fine)
- [ ] Commit: `reliability: add failure thresholds to prevent silent partial outages`

### 6b: Structured logging

- [ ] Add a simple structured logger (JSON lines to stderr) in `log_utils.py`
- [ ] Key events to log: per-source fetch result (success/fail/skip), total article counts per category, filter stats, dedup stats, AI ranker pick counts
- [ ] This makes it possible to grep logs for failures and build dashboards later
- [ ] Commit: `observability: add structured JSON logging for pipeline events`

---

## Step 7: CI Hardening

From Final Debug Plan findings #10.

- [ ] In `hourly.yml` and `ai-ranking.yml`: replace `git pull --rebase` with `git pull --no-rebase` to avoid conflicts under concurrent auto-commits
- [ ] In `ai-ranking.yml`: validate both `GEMINI_API_KEY` and `OPENROUTER_API_KEY` at the start (currently only checks Gemini)
- [ ] Pin third-party GitHub Actions to commit SHA instead of version tags (e.g., `actions/checkout@v4` → `actions/checkout@<sha>`)
- [ ] Commit: `ci: harden workflows — no-rebase pull, secret validation, pinned actions`

---

## Step 8: Content Expansion

These are additive — no risk, do whenever.

### 8a: More YouTube channels
- [ ] Find channel IDs for: ET Now, CNBC-TV18, freefincal
- [ ] Add entries to `feeds.json` with `"category": "Videos"`
- [ ] Test with `python3 aggregator.py`
- [ ] Commit: `content: add ET Now, CNBC-TV18, freefincal YouTube channels`

### 8b: Telegram bot for private groups
- [ ] Set up a Telegram bot via BotFather
- [ ] Add the bot to `btsreports` and `researchreportss` groups
- [ ] Update `telegram_fetcher.py` to use Bot API or Telethon MTProto for these groups
- [ ] Test locally before enabling in CI
- [ ] Commit: `feat: Telegram bot for private group report fetching`

---

## Execution Order

Steps 1-3 are quick cleanup (can be done in one session).
Steps 4-5 are targeted security/quality fixes.
Steps 6-7 are reliability infrastructure.
Step 8 is content growth — independent, do anytime.

Suggested priority: **1 → 2 → 3 → 4 → 5 → 7 → 6 → 8**
(Security before reliability, CI before logging, content last.)
