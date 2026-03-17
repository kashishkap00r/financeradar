# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

See [`AGENTS.md`](./AGENTS.md) for coding style, commit conventions, and PR standards.

## General Guidelines
- When the user interrupts or rejects an approach, stop immediately and ask what they want instead. Do not continue pushing similar ideas.
- If the user seems unsure, offer 2-3 concrete but distinct alternatives rather than building prototypes speculatively.

## Quick Commands

```bash
# Core pipeline (run in order for a full rebuild)
python3 telegram_fetcher.py          # Telegram reports → static/telegram_reports.json
python3 aggregator.py                # Fetch 220+ feeds → index.html + static/tab_*.json + static/articles.json
python3 reports_fetcher.py           # (called by aggregator.py, rarely run standalone)
python3 twitter_fetcher.py           # (called by aggregator.py, rarely run standalone)
python3 paper_fetcher.py             # Academic papers → static/papers_cache.json

# AI ranking (requires API keys)
GEMINI_API_KEY="..." OPENROUTER_API_KEY="..." python3 ai_ranker.py      # → static/ai_rankings.json
GEMINI_API_KEY="..." OPENROUTER_API_KEY="..." python3 wsw_ranker.py     # → static/wsw_clusters.json

# Local Twitter fetch (requires RSSHub running on localhost:1200)
python3 rsshub_local_fetch.py          # Fetch + save cache
python3 rsshub_local_fetch.py --push   # Fetch + save + git commit & push

# Testing
python3 -m unittest discover -s tests           # Full suite
python3 -m unittest tests.test_filters           # Single module
python3 -m py_compile aggregator.py              # Python syntax check
node --check templates/app.js                     # JS syntax check

# Local preview
python3 -m http.server 8000
```

## Architecture Overview

Static-site news aggregator: Python scripts fetch RSS/scraped data → filter/dedup/rank → generate `index.html` + JSON data files → deployed via GitHub Actions to Cloudflare Pages hourly.

### Data Pipeline

```
INGESTION (parallel, 10 workers)
├─ feeds.json (220+ feeds) ──→ aggregator.py ──→ News / Videos / Twitter / Reports routing
├─ telegram_channels.json ──→ telegram_fetcher.py ──→ static/telegram_reports.json
├─ reports_fetcher.py (16 scrapers) ──→ static/reports_cache.json
├─ twitter_fetcher.py (dual-source) ──→ static/tab_twitter.json
├─ paper_fetcher.py ──→ static/papers_cache.json
└─ rsshub_local_fetch.py (local only) ──→ static/rsshub_twitter_cache.json

PROCESSING
├─ filters.py: 126 title regex + 24 URL patterns (noise removal)
├─ articles.py: dedup (SequenceMatcher 75%), grouping, HTML cleaning
└─ twitter_signal.py: URL resolution, noise filters, High Signal lane (top 25)

RANKING (separate crons, needs API keys)
├─ ai_ranker.py: dual-LLM ranking → static/ai_rankings.json
│   Buckets: news=25, telegram=20, reports=10, twitter=10, youtube=10
└─ wsw_ranker.py: debate clusters from 7-day window → static/wsw_clusters.json

OUTPUT
├─ index.html (HTML shell, loads templates/app.js + templates/style.css externally)
└─ static/tab_*.json (per-tab data for lazy loading)
```

### Homepage: AI-Curated Feed

The homepage **exclusively shows AI-ranked content** from `static/ai_rankings.json`. Individual tabs remain chronological.

- `getMergedAiRankings(bucket)` in `app.js` merges picks from all providers (Gemini + DeepSeek) with consensus scoring: items picked by 2+ models rank highest (average rank), single-provider items get a +50 penalty
- Cross-provider matching uses URL (exact, lowercased) with fallback to `normalizeAiTitle()` (handles unicode dash/quote/ellipsis variants)
- News + Telegram interleave in the newspaper feed (3:1 ratio); YouTube, Reports, Twitter render in dedicated slider sections
- WSW breakers auto-select the provider with the most clusters
- If AI data is unavailable, homepage shows an empty-state message directing users to tabs

### Category Routing

`feeds.json` `category` field determines which tab an article appears in:

| category | Tab | Freshness | Notes |
|----------|-----|-----------|-------|
| `"News"` | News | 5 days | Dedup + grouping, 20/page |
| `"Videos"` | YouTube | 5 days | Atom feeds with `yt:videoId`, 15/page |
| `"Twitter"` | Twitter | 5 days | Dual-source (RSSHub + Google RSS), dual lanes |
| `"Reports"` | Reports | 30 days | Scraper registry, `region` filter (Indian/International) |

### Twitter Dual-Source Pipeline

```
Primary: RSSHub local (http://localhost:1200) → static/rsshub_twitter_cache.json
  - Runs locally via systemd timer (hourly)
  - Rich data: images, video thumbnails, quote tweet detection
  - 6-hour cache TTL (stale = skipped)

Fallback: Google News RSS (site:x.com queries from feeds.json)
  - Works in GitHub Actions (no auth needed)
  - Lower coverage (~20% of tweets)
  - Requires URL resolution (Google wrapper → canonical x.com/status/*)

Merge: RSSHub items take priority (by tweet_id), Google fills gaps
Last resort: static/twitter_clean_cache.json snapshot
```

### Reports: Two Dispatch Paths

Reports feeds dispatch by feed field prefix. There are two separate handlers:

**`reports_fetcher.py`** — 16 `@scraper`-decorated functions for HTML/API scraping. The decorator handles errors, 30-day freshness, article limits, and retries. Dispatched via `REPORT_FETCHERS` dict.

**`feeds.py` → `fetch_careratings()`** — CareEdge uses a separate API-based fetcher (`insightspagedata` endpoint), NOT `reports_fetcher.py`. Dispatched in `aggregator.py` via `feed_field.startswith("careratings:")`.

To add a new scraper: write a `fetch_*()` function, decorate with `@scraper`, register in `REPORT_FETCHERS`, add feeds to `feeds.json` with matching ID prefix.

### Frontend Architecture

- Source: `templates/app.js` (vanilla JS, ~3700 lines) + `templates/style.css` (~2900 lines)
- Loaded by `index.html` as external files (`<script src>` / `<link href>`) — **never edit `index.html` directly**, edit `templates/*`, then run `python3 aggregator.py`
- Theme: Fraunces headings, Source Sans Pro body, burnt orange accent (#C45A35), warm dark mode
- All state in localStorage (theme, active tab, bookmarks, page number)
- Keyboard nav: J/K (next/prev), / (search), Esc (clear), 1-6 (tab shortcuts)
- Homepage loads only `ai_rankings.json`; individual tabs lazy-load their own `tab_*.json` on first visit

### Module Map

19 Python modules (~8900 lines total). Key cross-file relationships:

| Module | Role | Called by |
|--------|------|-----------|
| `aggregator.py` (1463L) | Main pipeline: fetch → filter → dedup → group → generate HTML | Standalone / hourly.yml |
| `feeds.py` (829L) | Feed loading, RSS fetching, date parsing, **CareEdge API** | aggregator.py |
| `reports_fetcher.py` (1250L) | 16 `@scraper` functions for institutional reports | aggregator.py |
| `articles.py` (220L) | Dedup, grouping, HTML cleaning, JSON export | aggregator.py |
| `filters.py` (356L) | 126 title regex + 24 URL patterns | aggregator.py |
| `twitter_fetcher.py` (345L) | Dual-source Twitter (RSSHub + Google RSS) | aggregator.py |
| `twitter_signal.py` (659L) | URL resolution, noise filters, High Signal lane | twitter_fetcher.py |
| `ai_ranker.py` (758L) | Dual-LLM article ranking (Gemini + DeepSeek) | ai-ranking.yml |
| `wsw_ranker.py` (418L) | "Who Said What" debate clusters | ai-ranking.yml (after ai_ranker) |
| `telegram_fetcher.py` (580L) | HTML scraping + Telethon MTProto | Standalone / hourly.yml |
| `piie_local_fetch.py` (210L) | Playwright scraper → `static/piie_cache.json` | Local only (manual) |
| `config.py` (86L) | All magic numbers and tunables | Imported by most modules |

Frontend: `templates/app.js` (3690L) + `templates/style.css` (2884L). Tests: 18 modules in `tests/`.

## Key Rules

### Generated Files — Do Not Hand-Edit
All files in `static/` and `index.html` are auto-generated. Edit source scripts or `templates/*` instead, then regenerate.

### F-String Brace Escaping
When editing HTML/CSS/JS templates inside `aggregator.py` (which uses Python f-strings), escape literal braces: `{{` and `}}`. The `templates/` files use normal braces.

### Git Conflicts on Generated Files
Generated files conflict often between local pushes and GH Actions commits. Resolve by taking remote:
```bash
git checkout --theirs index.html static/articles.json static/tab_*.json
git add index.html static/articles.json static/tab_*.json
```
Then regenerate locally if needed. Prefer `git pull --no-rebase` over rebase.

### feeds.json Conventions
- `id`: unique, lowercase-hyphenated (e.g., `piie-blogs`)
- `category`: routing only — `News`, `Reports`, `Videos`, `Twitter`
- `publisher`: groups feeds in UI filter (e.g., both Swarajya Economy and Business → "Swarajya")
- `region`: Reports-only, `"Indian"` or `"International"` (omit for other categories)
- For sites behind Cloudflare/WAF, use Google News RSS proxy: `https://news.google.com/rss/search?q=site:domain.com/path&hl=en-IN&gl=IN&ceid=IN:en`

## Scraper Development
- Start with `curl` + browser-like headers (`User-Agent`, `Accept`, `Accept-Language`). Many financial sites (Akamai WAF, Cloudflare) block basic HTTP clients.
- Fall back to Playwright only if curl fails.
- For Cloudflare JS-challenge sites (e.g., PIIE), use the cache-based pattern: scrape locally with a real browser → save to `static/*_cache.json` → pipeline reads cache.

## UI Development
- Edit `templates/app.js` and `templates/style.css`, then `python3 aggregator.py` to regenerate.
- Test mobile (≤640px) before committing — filters collapse by default on mobile, sidebars use body scroll lock.
- Make changes incrementally. Never introduce a rendering gate that can blank the page.
- Hero cards on the homepage support `why_it_matters`, `signal_type` badges, and consensus indicators from AI rankings.

## GitHub Actions Workflows

| Workflow | Schedule | What it does |
|----------|----------|-------------|
| `hourly.yml` | Every hour | telegram_fetcher → aggregator → commit + push |
| `ai-ranking.yml` | 4x daily (UTC 0,6,12,18) | ai_ranker → wsw_ranker → commit + push |
| `missing-story-audit.yml` | Daily UTC 00:30 | Audit 7-day SLA breaches |
| `deploy-rss-proxy.yml` | Manual | Deploy Cloudflare RSS proxy worker |

Required secrets: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `RSS_PROXY_URL` (optional), `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.

## Local Services (systemd user units)

RSSHub runs locally as a systemd user service for Twitter feed enrichment:
- `rsshub.service`: RSSHub Node.js server on port 1200 (auto-start on login, auto-restart on crash)
- `rsshub-fetch.timer`: Triggers hourly fetch + git push (catches up after sleep via `Persistent=true`)
- Config: `~/.config/systemd/user/rsshub*.service|timer`
- Scripts: `~/.local/bin/start-rsshub.sh`, `~/.local/bin/fetch-rsshub.sh`
- Check status: `systemctl --user status rsshub.service rsshub-fetch.timer`
- View logs: `journalctl --user -u rsshub-fetch.service --since "1 hour ago"`

## Config (config.py)

Key constants: `FEED_FETCH_TIMEOUT=15`, `FEED_THREAD_WORKERS=10`, `NEWS_FRESHNESS_DAYS=5`, `REPORTS_FRESHNESS_DAYS=30`, `RSSHUB_CACHE_MAX_AGE_HOURS=6`, `TWITTER_HIGH_SIGNAL_TARGET=25`, `AI_RANKER_TARGET_COUNT=25`. Per-scraper timeout/retry overrides via `SCRAPER_TIMEOUT_OVERRIDES` and `SCRAPER_RETRY_OVERRIDES` dicts.

AI ranker bucket targets are in `ai_ranker.py:BUCKET_TARGETS` (news=25, telegram=20, reports=10, twitter=10, youtube=10).

## API Integration
- Always verify the correct Gemini model IDs before making API calls. Use `gemini-1.5-flash` or `gemini-1.5-pro` (not legacy names). Test API calls with a simple request before integrating.
- AI rankers (`ai_ranker.py`, `wsw_ranker.py`) use both Gemini and OpenRouter (DeepSeek). Both API keys are required for full multi-provider operation; single-provider degradation is handled gracefully.
