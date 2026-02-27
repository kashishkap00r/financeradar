# Twitter Signal Lanes Design

## Goal
Improve Twitter usability by separating high-quality signals from noisy flow, without reducing source coverage.

## Confirmed product decisions
- Keep all existing Twitter sources; do not prune feeds now.
- Add two Twitter sub-tabs: `High Signal` and `Full Stream`.
- Default to `High Signal` when opening Twitter tab.
- Keep retweets in `Full Stream`; exclude retweets from `High Signal`.
- Collapse thread bursts to one tweet per thread in both lanes.
- `High Signal` window: last 24 hours.
- `High Signal` size: 25 items.
- Use AI ranking for `High Signal` after deterministic cleanup.
- If AI fails, use deterministic fallback ranking (auto, no blank state).
- Resolve Google RSS Twitter links to direct `x.com/.../status/...` where possible.

## Approach options considered
1. Rule-based only cleanup and ranking.
2. Hybrid cleanup + AI ranking (chosen).
3. External tweet-enrichment service first.

Why option 2:
- Solves current messiness quickly.
- Keeps behavior controllable through hard rules.
- Uses AI only where it adds value: final signal ordering.

## Architecture
- Add a dedicated Twitter processing stage (new module: `twitter_signal.py`) between fetch and UI rendering.
- Keep current ingestion from `feeds.json` and `fetch_feed`.
- Produce two precomputed datasets per run:
  - `twitter_full_stream`
  - `twitter_high_signal`
- Keep existing bookmark flow unchanged.

## Data flow
1. Ingest all Twitter feed items.
2. Normalize title/source/date/url fields.
3. Resolve Google RSS wrapper links to direct tweet URLs when possible.
4. Extract structure from URL/title:
- Tweet id
- Author handle (best effort)
- Flags: retweet, quote, reply-like
- Thread key (conversation or heuristic fallback)
5. Deduplicate by canonical URL/tweet id and collapse near-duplicates.
6. Enforce one item per thread for both lanes.
7. Build lanes:
- `Full Stream`: cleaned items, includes retweets.
- `High Signal candidates`: last 24h, no retweets, deduped/thread-collapsed.
8. Rank `High Signal` candidates:
- AI rank to 25.
- Fallback deterministic rank if AI fails.
9. Persist final artifacts for UI and auditing.

## UI behavior
- In Twitter tab, add sub-tabs:
  - `High Signal` (default)
  - `Full Stream`
- Keep existing search and publisher filters; apply to active sub-tab.
- Show independent counts for each lane.
- Preserve current source link and bookmark interactions.
- Optionally show label in High Signal when fallback ranking is used.

## Error handling and safeguards
- If URL resolution fails, retain original link and continue.
- If thread extraction is weak, prefer under-collapsing over over-merging.
- Always return lane outputs even on partial failures.
- Hard checks:
  - No duplicate URL/thread in `High Signal`.
  - No retweet in `High Signal`.
  - `High Signal` target count = 25 when enough candidates exist.

## Testing plan
- Unit tests:
  - Google RSS Twitter URL resolution
  - Retweet/quote detection
  - Thread grouping and one-per-thread enforcement
  - Deterministic fallback ranking output size and stability
- Integration tests:
  - Mixed noisy fixture (retweets, quotes, repeated thread tweets)
  - Validate lane rules end-to-end
- Run-time audit metrics per build:
  - Ingested count
  - URL resolution success
  - Deduped count
  - Thread-collapsed count
  - Retweets excluded from high signal
  - Final lane counts

## Rollout
1. Build backend lane pipeline and caches.
2. Add Twitter sub-tabs in UI wired to lane outputs.
3. Validate for 2-3 runs and inspect audit metrics.
4. Tune heuristics only where needed.
