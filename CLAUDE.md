# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Commands

```bash
python3 aggregator.py                          # Regenerate index.html + static/articles.json + static/youtube_cache.json
python3 telegram_fetcher.py                    # Fetch Telegram reports (public channels only without creds)
TELEGRAM_API_ID="..." TELEGRAM_API_HASH="..." TELEGRAM_SESSION="..." python3 telegram_fetcher.py
GEMINI_API_KEY="AIza..." OPENROUTER_API_KEY="sk-or-..." python3 ai_ranker.py
GEMINI_API_KEY="AIza..." OPENROUTER_API_KEY="sk-or-..." python3 wsw_ranker.py
python3 -m http.server 8000                    # Preview locally
python3 -c "from filters import should_filter_article; print(should_filter_article({'title': 'TEST', 'link': ''}))"
python3 -m unittest discover -s tests             # Run test suite (62 tests)
```

**Tests:** 62 unit tests in `tests/` covering date parsing, filters, articles, AI ranker JSON parsing, and Telegram HTML parsing. Run with `python3 -m unittest discover -s tests`. No linting or type-checking configurations.

**Dependencies:** Python 3.8+ stdlib only, except `telethon>=1.36` (in `requirements.txt`) for Telegram MTProto. `curl` required for 403 fallback.

## Critical Rules

- **Never hand-edit generated files:** `index.html`, `static/articles.json`, `static/telegram_reports.json`, `static/youtube_cache.json`, `static/ai_rankings.json`, `static/wsw_clusters.json`.
- **Frontend is split across three files** with different brace rules:
  - `templates/style.css` — source file, normal `{}` braces
  - `templates/app.js` — source file, normal `{}` braces
  - `aggregator.py` `generate_html()` — f-string template, uses `{{`/`}}` for literal braces
  - Both CSS and JS are inlined into `index.html` at build time. Run `python3 aggregator.py` after editing.
- **JS data constants** (`ALL_PUBLISHERS`, `TELEGRAM_REPORTS`, `RESEARCH_REPORTS`, etc.) are injected via f-string in `aggregator.py` *before* `templates/app.js` content is appended. All JS `const`/`let` declarations must appear before any code path that references them (temporal dead zone). `function` declarations are hoisted and safe anywhere.
- **Content filters** live in `filters.py` (title regex + URL substring patterns). Add new patterns there — no other files need changes.

## Git: Handling Remote-Ahead Conflicts

GitHub Actions commits generated files every hour, so pushes are frequently rejected. Use merge (not rebase):

```bash
git fetch origin
git merge origin/main -X ours --no-edit
git push
```

**Never use `git rebase`** — partial conflict resolution leaves merge markers in `index.html` that render literally in the browser.

## Architecture

### Data Flow

```
feeds.json (186 feeds: 106 News, 23 Reports, 14 Videos, 43 Twitter)
    ↓
aggregator.py  ←── feeds.py (RSS/Atom parsing, CareEdge API, date parsing)
    │               reports_fetcher.py (10 custom scrapers)
    │               filters.py (content filtering)
    │               articles.py (similarity, grouping, export)
    ↓
index.html + static/articles.json + static/youtube_cache.json

telegram_fetcher.py  →  static/telegram_reports.json
ai_ranker.py         →  static/ai_rankings.json     (reads articles.json)
wsw_ranker.py        →  static/wsw_clusters.json     (reads articles.json + telegram_reports.json + youtube_cache.json)
```

### Backend Modules

| File | Lines | Purpose |
|------|-------|---------|
| `aggregator.py` | ~930 | Main orchestrator: parallel fetch (10 workers, 15s timeout), dedup, filter, group, HTML generation |
| `templates/app.js` | ~2260 | All frontend JS: state, rendering, filtering, pagination, bookmarks, keyboard nav, sidebars |
| `templates/style.css` | ~1880 | All CSS: variables, layout, cards, dark mode, mobile media queries |
| `feeds.py` | ~280 | Feed config loading, RSS/Atom/YouTube parsing, CareEdge JSON API, curl fallback on 403 |
| `articles.py` | ~220 | Headline similarity (SequenceMatcher ≥0.75, same-day), article grouping, text utils, articles.json export |
| `filters.py` | ~280 | Content filtering: title regex + URL substring patterns |
| `config.py` | ~50 | Centralized constants (timeouts, limits, thresholds) imported by all modules |
| `log_utils.py` | ~50 | Structured logging wrapper (`FeedLogger`) with IST timestamps and summary |
| `reports_fetcher.py` | ~660 | Custom HTML/JSON scrapers for institutional research (10 sources), `@scraper` decorator |
| `ai_ranker.py` | — | Two-provider AI ranking (Gemini 3.0 Flash + DeepSeek V3.2), top-20 picks |
| `wsw_ranker.py` | — | "Who Said What" — 7-day rolling data, 8 debate clusters, same two AI providers |
| `telegram_fetcher.py` | — | HTML scraping (public channels) + Telethon MTProto (private groups) |

### Five Tabs and Category Routing

Articles are routed to tabs by the `category` field in `feeds.json`:

| Category | Tab | Keyboard | Freshness |
|----------|-----|----------|-----------|
| `News` (default) | News | `1` | 10 days |
| — | Telegram | `2` | — |
| `Reports` | Reports | `3` | 30 days |
| `Videos` | YouTube | `4` | 10 days |
| `Twitter` | Twitter | `5` | 5 days |

Telegram data comes from `telegram_fetcher.py`, not from feeds.json.

### Feed String Conventions

The `feed` field in `feeds.json` determines how each feed is fetched:

| Pattern | Handler | Example |
|---------|---------|---------|
| Standard URL | `fetch_feed()` in feeds.py (RSS/Atom) | `https://example.com/rss` |
| `careratings:{PageId}` | `fetch_careratings()` in feeds.py | `careratings:9` (SectionId defaults to 5034) |
| `careratings:{PageId}:{SectionId}` | `fetch_careratings()` in feeds.py | `careratings:1:23` (Economy Updates) |
| `{prefix}:{slug}` | Dispatched via `REPORT_FETCHERS` dict in reports_fetcher.py | `crisil:views`, `goldman:insights` |

### Adding a New Report Scraper

1. Write `fetch_newname(feed_config)` in `reports_fetcher.py` returning list of article dicts via `_make_article()`
2. Add entry to `REPORT_FETCHERS` dict: `"newname:": fetch_newname`
3. Add feed entry in `feeds.json` with `"feed": "newname:slug"`, `"category": "Reports"`, `"region": "Indian"` or `"International"`

Shared utilities available: `_fetch_url()`, `_make_article()`, `_strip_html()`, `_parse_date_flexible()`, `_is_fresh()` (30-day guard), `_MAX_PER_SCRAPER` (30 items).

Current scrapers in `REPORT_FETCHERS`: `crisil`, `baroda`, `sbi` (Ecowrap only), `ficci`, `icici`, `hdfcsec`, `axis`, `gs` (Goldman Sachs), `creditsights`, `jpmorgan`.

### AI Ranker Schema

`ai_ranker.py` calls two models and saves under separate provider keys in `static/ai_rankings.json`:

- **`gemini-3-flash`** → Gemini API (`generativelanguage.googleapis.com`) using `GEMINI_API_KEY`
- **`deepseek-v3`** → OpenRouter (`openrouter.ai/api/v1`) using `OPENROUTER_API_KEY`

Empty-title guard: if >50% of returned titles are blank, saves `"status": "error"` instead of garbage data.

Title matching uses 3-stage lookup: exact sanitized → `normalize_title()` (dash/quote normalization) → fuzzy SequenceMatcher at 0.72 threshold.

### GitHub Actions

| Workflow | Schedule | What it does |
|----------|----------|-------------|
| `hourly.yml` | Every hour | telegram_fetcher.py → aggregator.py → commit `index.html`, `articles.json`, `telegram_reports.json`, `youtube_cache.json` |
| `ai-ranking.yml` | Midnight UTC (5:30 AM IST) | ai_ranker.py → wsw_ranker.py → commit `ai_rankings.json`, `wsw_clusters.json` |

**Cron delay:** GitHub Actions crons typically run 1–2 hours late. AI ranking is scheduled early to absorb this and finish by ~8 AM IST.

### Required GitHub Secrets

| Secret | Used by |
|--------|---------|
| `TELEGRAM_API_ID` | `hourly.yml` |
| `TELEGRAM_API_HASH` | `hourly.yml` |
| `TELEGRAM_SESSION` | `hourly.yml` |
| `OPENROUTER_API_KEY` | `ai-ranking.yml` |
| `GEMINI_API_KEY` | `ai-ranking.yml` |

## Key Frontend Patterns

- **Dropdown component:** All five tabs reuse the same `publisher-dropdown` / `publisher-dropdown-trigger` / `publisher-dropdown-panel` HTML+CSS pattern. When adding a new tab's publisher filter, reuse this component. Close logic must be wired in three places: click-outside handler, Escape keydown handler, and `toggleFilterCollapse()`.
- **Tab filter card structure:** Every tab uses `.filter-card` → `.stats-bar` (count + timestamp) → `.filter-row` (controls).
- **`safeStorage`:** All `localStorage` access goes through this try/catch wrapper. Never call `localStorage` directly.
- **`escapeHtml` / `escapeForAttr`:** Always use these when inserting user-sourced data into innerHTML templates.
- **Reports tab filter bar:** Region toggle `[All] [Indian] [International]` + publisher dropdown. Region is set via `"region"` field in `feeds.json` (`"Indian"` or `"International"`).
- **Telegram tab filter bar:** Row 1 = segmented toggle `[All] [Reports] [Posts]` + count/timestamp. Row 2 = channel dropdown + `[No price targets]` chip.

## Deployment

Cloudflare Pages connected to the GitHub repo. Build command: empty. Output directory: `/` (root). Cloudflare picks up the `index.html` pushed by GitHub Actions each hour.

**Live site:** [financeradar.kashishkapoor.com](https://financeradar.kashishkapoor.com)
