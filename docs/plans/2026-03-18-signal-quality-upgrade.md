# FinanceRadar: Signal Quality Upgrade

> Improve what surfaces (catch missed stories) and what gets killed (eliminate noise) — the two daily pain points.

**Date:** 2026-03-18
**Context:** V13 redesign shipped, cleanup/hardening done. This plan targets content quality — the core value prop.

---

## Step 1: Semantic Dedup on AI Homepage

**Problem:** When a big story breaks (Iran/Hormuz, RBI policy), the homepage shows 8-10 articles that all say the same thing in different words. SequenceMatcher (75% string similarity) catches near-identical titles but misses semantic duplicates like "Iran tensions rattle oil markets" vs "Crude surges as Hormuz fears mount."

**Goal:** Keep every genuinely different *angle* on a story, kill rewrites. Not a hard cap — if 5 articles each bring a unique take, show all 5.

**Approach:**
- In `ai_ranker.py`, after the LLM returns its ranked picks, add a **story-clustering pass**: ask the LLM to group the picks by underlying story/event, then keep only the top-ranked article per story *plus* any article the LLM flags as a "distinct angle"
- This runs inside the existing AI ranking prompt (extend, don't add a new API call)
- Frontend unchanged — it just receives fewer, more diverse picks

**Files:** `ai_ranker.py` (ranking prompt + post-processing), possibly `config.py` (max-per-story tunable)

**Acceptance:** Homepage shows max 2-3 articles per story unless they bring genuinely different angles. No regression in total item count (other stories fill the freed slots).

---

## Step 2: Primary Source Ingestion (RBI, SEBI, PIB, BSE/NSE)

**Problem:** Authoritative regulatory sources have the most important content (new rules, policy shifts, landmark enforcement), but 95% is administrative noise (show-cause notices, penalty orders against random NBFCs, routine compliance circulars). Currently not ingested at all.

**Goal:** Add RBI, SEBI, PIB, and BSE/NSE feeds with an AI noise filter so only policy-significant items surface.

**Approach:**
- Add RSS feeds for RBI press releases, SEBI circulars, PIB (finance ministry), BSE/NSE corporate announcements to `feeds.json`
- In the aggregator pipeline, route these through a lightweight LLM classification step (Gemini Flash or Haiku): "Is this a new regulation / policy change / landmark enforcement / significant data release, or routine administrative noise?"
- Only items classified as significant pass through to the News tab and AI ranking
- Cache the classification per URL to avoid re-calling the LLM on every hourly run

**Files:** `feeds.json` (new feeds), `aggregator.py` (classification step), new `regulatory_filter.py` module, `config.py` (classification model config)

**Acceptance:** RBI/SEBI/PIB items appear in News tab and homepage. Routine penalty orders, compliance circulars, and administrative noise are filtered out. False negative rate < 5% on significant items (spot-check over 1 week).

---

## Step 3: Smarter Twitter Discovery

**Problem:** Missing expert voices on Twitter because the follow list is manually curated and static. When existing trusted handles quote or amplify someone, that's a strong "you should follow this person" signal.

**Goal:** Surface a "suggested handles" list based on who the existing expert handles are retweeting, quoting, or engaging with most frequently.

**Approach:**
- In `twitter_signal.py` or a new `twitter_discovery.py`, analyze the existing tweet stream for retweet/quote patterns: extract the original author from "RT @handle:" prefixes and quote-tweet URLs
- Track frequency over a rolling 7-day window: which external handles appear most often via the trusted network?
- Output a `static/twitter_suggestions.json` with handles ranked by frequency + sample tweets
- This is a **research/reporting tool only** — no auto-addition to feeds. Kashish reviews and approves before any handle gets added to `feeds.json`

**Files:** New `twitter_discovery.py`, `aggregator.py` (call it after Twitter processing), `config.py` (window size, min-frequency threshold)

**Acceptance:** After each run, a JSON file lists suggested handles with frequency counts and sample content. No handles are auto-added.

---

## Step 4: Story Arcs / Evolution Tracking

**Problem:** Running stories (Iran tensions, RBI rate cycle, SEBI regulation rollout) appear as disconnected daily items. No way to see how a story evolved over days.

**Goal:** Show story progression — day 1: initial event, day 2: market impact, day 3: policy response, day 5: resolution.

**Approach:**
- Extend WSW clustering (already groups by theme over 7 days) to track **temporal progression** within a story cluster
- Each cluster gets a timeline: ordered list of articles with dates, showing how the narrative shifted
- Frontend: add a "Story Arc" view accessible from WSW breaker cards on homepage — click to expand the timeline
- The LLM prompt already asks for `core_claim` and `counter_view` per cluster; extend to include `timeline_events` (list of date + headline + shift-in-narrative)

**Files:** `wsw_ranker.py` (prompt extension + output schema), `templates/app.js` (story arc UI), `templates/style.css` (timeline styling)

**Acceptance:** WSW clusters include a timeline showing story evolution. Clicking a cluster on the homepage reveals the arc. Works on mobile.

---

## Step 5: LLM-Based Noise Filter

**Problem:** The 126 regex title patterns are effective but brittle. Creative rephrasing bypasses them ("5 stocks to buy" is caught, but "Here's what smart money is buying this week" isn't). Shallow opinion rewrites and listicles slip through.

**Goal:** Add an LLM filter layer that catches noise regex can't — without slowing down the hourly pipeline significantly.

**Approach:**
- After regex filtering in `aggregator.py`, run remaining articles through a fast/cheap LLM (Gemini Flash) in batches
- Prompt: "For a professional financial journalist writing a daily market brief, classify each headline as KEEP (substantive news, analysis, data) or SKIP (listicle, clickbait, shallow opinion, stock tips, routine market commentary)"
- Batch 50-100 headlines per API call to minimize latency and cost
- Use a confidence threshold — only skip items the LLM is highly confident about (avoid false positives)
- Log all LLM-skipped items to a file for weekly review (catch filter drift)

**Files:** `aggregator.py` or new `llm_filter.py`, `config.py` (batch size, confidence threshold, model), `filters.py` (integration point)

**Acceptance:** Measurably fewer noise articles on all tabs. Zero false positives on important stories (verified by 1-week spot-check). Pipeline runtime increase < 15 seconds per run.

---

## Execution Order

| Step | What | Dependencies | Risk |
|------|------|-------------|------|
| 1. Semantic dedup | Extend AI ranker prompt | None | Low — contained in existing AI ranking flow |
| 2. Primary sources | New feeds + AI filter | None | Medium — need to tune filter accuracy |
| 3. Twitter discovery | Analyze existing stream | None | Low — reporting only, no auto-changes |
| 4. Story arcs | Extend WSW + frontend | Step 1 helps (deduped input) | Medium — frontend + LLM prompt changes |
| 5. LLM noise filter | New filter layer | None | Medium — latency budget, false positive risk |

Steps 1-3 are independent and can be done in any order. Step 4 benefits from Step 1 (cleaner input). Step 5 is independent but lower priority since regex filters already catch most noise.

**Recommended sequence:** 1 → 2 → 3 → 4 → 5
