# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

FinanceRadar is a Python RSS aggregator that generates a single static HTML page with 106 feeds (96 news + 6 YouTube + 4 Twitter/X). Deployed hourly via GitHub Actions to Cloudflare Pages. Four tabs: News, Telegram, YouTube, Twitter. An AI ranker (OpenRouter) picks the top 20 stories daily. A Telegram fetcher pulls brokerage reports from 7 channels.

**Live:** financeradar.kashishkapoor.com

## Commands

```bash
# Generate the static site (~2 minutes, fetches 102+ feeds)
python3 aggregator.py

# Fetch Telegram channel reports (HTML-only without creds, full with creds)
python3 telegram_fetcher.py

# Fetch with MTProto private channels (needs env vars)
TELEGRAM_API_ID="..." TELEGRAM_API_HASH="..." TELEGRAM_SESSION="..." python3 telegram_fetcher.py

# Run AI ranking (needs API key)
OPENROUTER_API_KEY="sk-or-..." python3 ai_ranker.py

# Local preview
python3 -m http.server 8000

# Generate Telethon session string (one-time, interactive)
pip install telethon && python3 generate_session.py
```

**Dependencies:** `telethon>=1.36` (in `requirements.txt`). Everything else is stdlib Python 3.8+. No tests, no linter, no build system.

## Architecture

### Data Flow
```
feeds.json (106 feeds: 96 news + 6 YouTube + 4 Twitter)
  → aggregator.py (parallel fetch → split YouTube/Twitter → dedup → filter → group → HTML)
  → index.html + static/articles.json

telegram_channels.json (7 channels: 2 html + 5 mtproto)
  → telegram_fetcher.py
     ├─ HTML scraper (public channels via t.me/s/)
     └─ Telethon MTProto (private channels via API)
  → static/telegram_reports.json

static/articles.json
  → ai_ranker.py (reads articles, calls OpenRouter)
  → static/ai_rankings.json
```

### Key Files

| File | Lines | Role |
|------|-------|------|
| `aggregator.py` | ~3530 | **Everything** — fetch, parse, filter, dedupe, group, generate HTML with embedded CSS/JS |
| `telegram_fetcher.py` | ~505 | Hybrid fetcher: HTML scraper for public channels + Telethon MTProto for private channels |
| `ai_ranker.py` | ~230 | Reads `articles.json`, sends headlines to OpenRouter, writes `ai_rankings.json` |
| `generate_session.py` | ~35 | One-time interactive script to create Telethon StringSession |
| `feeds.json` | 106 entries | Feed configs: `{id, name, url, feed, category, publisher?}`. Categories: News, Videos, Twitter (internal routing only) |
| `telegram_channels.json` | 7 entries | Channel configs: `{username, label, method}` where method is `"html"` or `"mtproto"` |

### Generated Files (do NOT hand-edit)
- `index.html` — full static site (~2.7 MB)
- `static/articles.json` — structured feed for AI ranker
- `static/ai_rankings.json` — AI-ranked top 20
- `static/telegram_reports.json` — scraped Telegram messages with documents
- `cron.log` — execution logs

These cause merge conflicts on rebase. **Always resolve with `git checkout --theirs`** for generated files, then regenerate.

## aggregator.py Internals

### generate_html() Structure Map (~lines 621–3420)

The entire frontend lives inside `generate_html()` as a single f-string. All CSS and JS are inlined — no external stylesheets or scripts.

| Section | Lines | Contents |
|---------|-------|----------|
| `<head>` + fonts | ~621–708 | Meta tags, Google Fonts (Merriweather, Source Sans Pro), early theme + filters-collapsed scripts |
| `<style>` (all CSS) | ~709–2072 | CSS variables, layout, cards, filters, filter-toggle, pagination, reports, dark mode, mobile media queries |
| Font-loading `<script>` | ~2073–2083 | FontFace API loader |
| `<body>` + top bar | ~2084–2188 | Header, search, top-bar icon buttons (AI, Bookmarks, In Focus, Theme) |
| News tab (`#tab-news`) | ~2190–2306 | `.filter-card` → `.stats-bar` (+ filter-toggle chevron) + `.filter-row` (presets, publisher, category), article cards, pagination |
| Telegram tab (`#tab-reports`) | ~2308–2336 | `.filter-card` → `.stats-bar` (+ filter-toggle chevron) + `.filter-row` (PDF filter), reports container, pagination |
| YouTube tab (`#tab-youtube`) | after reports | `.filter-card` → `.stats-bar`, video cards (thumbnail + info), pagination |
| Twitter tab (`#tab-twitter`) | after youtube | `.filter-card` → `.stats-bar`, tweet articles, pagination |
| Footer + overlays | ~2339–2349 | Footer, back-to-top, keyboard hints |
| `<script>` (all JS) | ~2350–3420 | State management, rendering, filtering, pagination, bookmarks, keyboard nav, sidebars, tab persistence |

### Key CSS Patterns

- **Theming:** CSS variables in `:root` / `[data-theme="light"]` / `[data-theme="dark"]`. Red accent `#e14b4b`, warm charcoal dark mode `#0f1419`.
- **Tab layout:** Both News and Telegram tabs use the same `.filter-card` → `.stats-bar` (with `.stats` pills + `.update-time`) → `.filter-row` pattern.
- **Top bar buttons:** All use 32x32 icon buttons with `data-tooltip` CSS tooltips (not native `title`). In Focus has a pulse dot (10px) + count badge.
- **Filter pills:** `.preset-btn` and `.reports-filter-btn` share the same pill shape (20px radius, 1.5px border).
- **Mobile collapsible filters:** On ≤640px, `.filter-row` is hidden by default via `html.filters-collapsed` class (set by early `<head>` script). A `.filter-toggle` chevron button in each `.stats-bar` toggles visibility. Desktop is unaffected (button hidden by CSS).
- **Tab persistence:** Active tab saved to localStorage; restored on load after reports variables are declared (IIFE placed after `REPORTS_PAGE_SIZE`).

### Key Python Functions

**Content filtering:** `FILTER_TITLE_PATTERNS` (126 regexes, lines 38–222) and `FILTER_URL_PATTERNS` (24 substrings, lines 225–250). Adding new patterns requires no logic changes — the compile step at line 253 and `should_filter_article()` handle them automatically.

**Headline grouping:** `group_similar_articles()` clusters similar headlines from different sources using `SequenceMatcher` (75% threshold), comparing only within the same date.

**Feed fetching:** `ThreadPoolExecutor` with 10 workers, 15s timeout. Falls back to subprocess `curl` on 403 errors. SSL verification disabled for problematic feeds.

**Date parsing:** `parse_date()` handles 10+ formats (RFC 2822, ISO 8601, SEBI, RBI). RBI dates without timezone assume IST.

**Telegram reports rendering:** The JS `applyReportsPagination()` function renders each report's `documents` array as individual `.report-doc-item` rows. Falls back to single `document` field for backward compatibility.

### Client-Side State (localStorage)

All reads/writes go through `safeStorage` helper (try/catch wrapper). Keys:

| Key | Values | Purpose |
|-----|--------|---------|
| `theme` | `light` / `dark` | Theme preference |
| `financeradar_filters_collapsed` | `true` / `false` | Mobile filter row visibility (default: collapsed on `null`) |
| `financeradar_active_tab` | `news` / `reports` / `youtube` / `twitter` | Persisted active tab |
| `financeradar_page` | number | Last viewed pagination page |
| `financeradar_bookmarks` | JSON array | Saved article bookmarks |

## telegram_fetcher.py Internals

### Hybrid Architecture

The fetcher supports two methods per channel, configured via `"method"` field in `telegram_channels.json`:

- **`"html"`** (default): Scrapes `t.me/s/{username}` HTML. Uses `TelegramHTMLParser` (stdlib `HTMLParser` subclass) with state machine flags. Works only for public channels that serve preview HTML.
- **`"mtproto"`**: Uses Telethon to connect via MTProto protocol with the user's own Telegram account. Reads full message history from private/restricted channels. Requires `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION` env vars.

### Graceful Fallback

If Telethon isn't installed or credentials aren't set, MTProto channels are skipped with a warning. HTML channels still fetch normally. No crash.

### Output Schema (both methods produce identical format)

```json
{
  "generated_at": "ISO8601",
  "warnings": [],
  "reports": [{
    "text": "string", "date": "ISO8601", "url": "https://t.me/...",
    "channel": "Display Name",
    "documents": [{"title": "file.pdf", "size": "2.3 MB"}],
    "document": {"title": "...", "size": "..."} or null,
    "views": "749", "images": ["https://cdn.t.me/..."]
  }]
}
```

The `"warnings"` array is empty on success. On failure (session expired, channel returned 0 messages, client error), it contains human-readable strings. The frontend reads `TELEGRAM_WARNINGS` and renders a red `.reports-warning` banner on the Telegram tab when non-empty.

Note: MTProto-fetched messages have empty `images: []` (no CDN URLs available via API). Frontend handles this gracefully.

### Session Management

`generate_session.py` creates a Telethon `StringSession` (one-time, interactive: phone + code). The session string is stored as a GitHub Actions secret. Sessions rarely expire; re-run the script if auth fails.

## ai_ranker.py Internals

`RANKING_PROMPT` defines a 6-tier editorial prioritization (explanatory journalism highest, earnings/wire news excluded). Headlines are sent with `[Source Name]` tags for source-aware ranking; tags are stripped back on response matching.

`MODELS` dict maps provider keys to OpenRouter model IDs. Currently uses free-tier models. Rate-limited to 2s between API calls. Reads last 48 hours of articles (max 200).

## Feed Categories

No visible categorization in the frontend. The `category` field in feeds.json is used only for internal pipeline routing: `"News"` → News tab, `"Videos"` → YouTube tab, `"Twitter"` → Twitter tab. YouTube and Twitter articles are separated early and skip content filtering/headline grouping.

Special feed URL patterns:
- Google News RSS workaround: `news.google.com/rss/search?q=site:domain.com/section`
- The Core: `/category/google_feeds.xml`
- Indian Express: `/section/feed/`

## GitHub Actions

| Workflow | File | Schedule | Runs |
|----------|------|----------|------|
| Update FinanceRadar | `hourly.yml` | `0 * * * *` (every hour) | `pip install telethon` → `telegram_fetcher.py` → `aggregator.py` |
| AI News Ranking | `ai-ranking.yml` | `0 0 * * *` (midnight UTC / 5:30 AM IST) | `ai_ranker.py` (needs `OPENROUTER_API_KEY` secret) |

### Required Secrets

| Secret | Used by | Purpose |
|--------|---------|---------|
| `TELEGRAM_API_ID` | `hourly.yml` | Telegram API app ID (from my.telegram.org) |
| `TELEGRAM_API_HASH` | `hourly.yml` | Telegram API app hash |
| `TELEGRAM_SESSION` | `hourly.yml` | Telethon StringSession (from `generate_session.py`) |
| `OPENROUTER_API_KEY` | `ai-ranking.yml` | OpenRouter API key for AI ranking |

**GitHub Actions delay note:** Cron jobs typically run 1–2 hours late. The AI ranking cron is set early (5:30 AM IST) to absorb delays and finish by ~8 AM IST.

## Git Conventions

Generated files conflict constantly because the cron job commits them hourly. When rebasing:
```bash
git checkout --theirs index.html static/articles.json static/telegram_reports.json
git add index.html static/articles.json static/telegram_reports.json
git rebase --continue
```
Then regenerate with `python3 aggregator.py` and commit the fresh output.
