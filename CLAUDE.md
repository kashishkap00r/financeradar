# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Full architecture documentation lives in `README.md`. This file covers rules, corrections to outdated README sections, and session-learned patterns.

## Quick Commands

```bash
python3 aggregator.py                          # Regenerate index.html + static/articles.json
python3 telegram_fetcher.py                    # Fetch Telegram reports (HTML channels only without creds)
TELEGRAM_API_ID="..." TELEGRAM_API_HASH="..." TELEGRAM_SESSION="..." python3 telegram_fetcher.py
OPENROUTER_API_KEY="sk-or-..." python3 ai_ranker.py
python3 -m http.server 8000                    # Preview locally
python3 -c "from filters import should_filter_article; print(should_filter_article({'title': 'TEST', 'link': ''}))"
```

## Critical Rules

- **Never hand-edit** `index.html`, `static/articles.json`, `static/telegram_reports.json`, `static/youtube_cache.json`, `static/ai_rankings.json` — all are generated.
- The entire frontend (HTML/CSS/JS) lives inside `generate_html()` in `aggregator.py` as one f-string (~4,500 lines). Edit there, then `python3 aggregator.py` to regenerate.
- Content filters live in `filters.py` — add patterns there, no other changes needed.
- All JS `const` declarations inside `generate_html()` are subject to the temporal dead zone. Place `const`/`let` declarations **before** any code path that calls functions referencing them. `function` declarations are safe anywhere (hoisted).

## Git: Handling Remote-Ahead Conflicts

GitHub Actions commits generated files every hour, so pushes are frequently rejected. Use merge (not rebase) to avoid corrupt generated files:

```bash
git fetch origin
git merge origin/main -X ours --no-edit   # our source wins, their generated files win via -X ours on non-generated
python3 aggregator.py                      # regenerate cleanly
git add index.html static/articles.json static/telegram_reports.json static/youtube_cache.json
git push
```

**Never use `git rebase` with generated files** — partial conflict resolution leaves merge markers embedded in `index.html` which then renders to the browser literally.

## Architecture: What README Has Wrong / Outdated

### Telegram Tab (current UI, not README)

The Telegram filter bar has two rows:
- **Row 1:** Segmented toggle `[All] [Reports] [Posts]` (IDs: `reports-view-all`, `reports-view-pdf`, `reports-view-nopdf`) + count·timestamp meta
- **Row 2:** Channel dropdown (same `publisher-dropdown` component as YouTube/Twitter) + `[No price targets]` chip (`tg-chip`)

JS state: `reportsViewMode` (`'all'`/`'pdf'`/`'nopdf'`), `reportsNoTargetFilterActive` (bool), `selectedTgChannels` (Set — empty = all channels).

Filter logic in `filterReports()` applies in order: search query → `reportHasContent()` (always — drops image-only posts) → view mode → channel Set → no-targets.

`TG_CHANNEL_COLORS` and `getChannelColor` have been **removed**. Channel cards no longer show colored dots.

### AI Ranker Output (current schema)

Each ranked item in `ai_rankings.json` now includes four additional fields the LLM returns:
```json
{
  "rank": 1,
  "title": "...",
  "url": "...",
  "source": "...",
  "india_relevance": "One sentence.",
  "signal_type": "mechanism | structural-shift | supply-chain | policy-implication | credible-opinion | labour-trend",
  "why_it_matters": "Up to 2 lines.",
  "confidence": "high | medium | low"
}
```

Title matching uses a 3-stage lookup in `main()`: exact sanitized → exact `normalize_title()` (handles en/em-dash↔hyphen, smart quotes, whitespace) → fuzzy SequenceMatcher at threshold 0.72 against normalized keys. The `normalize_title()` function is in `ai_ranker.py`.

### Telegram Reports: Image-only Posts

Posts with no `text` and no `documents` (image-only messages) are filtered out by `reportHasContent()` in `filterReports()`. They were previously appearing as empty cards.

## Key Patterns

- **Dropdown component:** All four tabs (News, Telegram, YouTube, Twitter) use the same `publisher-dropdown` / `publisher-dropdown-trigger` / `publisher-dropdown-panel` HTML pattern with shared CSS. Adding a new tab's publisher filter should reuse this component. Close logic must be added to three places: click-outside handler, Escape keydown handler, and `toggleFilterCollapse()`.
- **Tab filter card structure:** Every tab wraps its filters in `.filter-card` → `.stats-bar` (count + timestamp) → `.filter-row` (controls).
- **`safeStorage`:** All `localStorage` reads/writes use this try/catch wrapper. Don't call `localStorage` directly.
- **`escapeHtml` / `escapeForAttr`:** Always use these when inserting user-sourced data into innerHTML templates.
