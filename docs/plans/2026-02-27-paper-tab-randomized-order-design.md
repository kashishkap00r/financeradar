# Paper Tab Randomized Order Design

## Goal
Make the `Paper` tab feel fresh each time it is opened so paper discovery is easier, without pretending that content itself is new.

## Confirmed product decisions
- Shuffle papers every time the user opens the `Paper` tab.
- Keep order fixed while user stays inside `Paper` (no reshuffle on search or pagination).
- Keep bookmarks in the same randomized flow (no bookmark pinning).
- Keep current card structure: title, date/undated marker, subtitle, source, authors.

## Approach options considered
1. Client-side shuffle on tab open (chosen).
2. Server-side shuffle during build.
3. Daily deterministic shuffle.

Why option 1:
- Exactly matches “new order every tab open.”
- Zero backend overhead.
- Preserves stable backend outputs (`papers_cache`, `published_snapshot`) for debugging/auditing.

## Technical design
- Add a front-end session pool, e.g. `paperSessionPool`, generated from `PAPER_ARTICLES`.
- On `switchTab('papers')`, always rebuild `paperSessionPool` via Fisher-Yates shuffle.
- `filterPapers()` filters `paperSessionPool` instead of raw `PAPER_ARTICLES`.
- Pagination runs on filtered result as-is.
- No reshuffle in `filterPapers()` or pagination handlers.

## UX details
- The tab feels “new” each entry, supporting quick pick workflows.
- Search and pagination remain predictable during a session.
- Undated papers continue to show `Date unavailable`.
- Date headers can remain, but if visual noise appears due to random order, we can switch Paper list to flat cards in a follow-up.

## Testing
- Opening `Paper` twice creates different orders.
- Search does not trigger reshuffle.
- Page next/prev does not trigger reshuffle.
- Leaving `Paper` and returning reshuffles.
- Bookmark behavior remains unchanged.

## Risks and mitigations
- Risk: user loses a paper position after reopening tab.
- Mitigation: bookmarking and search remain available; behavior is intentional for discovery.
