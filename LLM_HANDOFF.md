# FinanceRadar — Complete LLM Handoff Document

> **Purpose:** Everything another LLM needs to understand, maintain, and extend this project from scratch.
> **Last updated:** 2026-03-01

---

## Table of Contents

1. [What Is FinanceRadar?](#1-what-is-financeradar)
2. [Live Site & Deployment](#2-live-site--deployment)
3. [Directory Structure](#3-directory-structure)
4. [Architecture & Data Flow](#4-architecture--data-flow)
5. [Backend Modules — Detailed Breakdown](#5-backend-modules--detailed-breakdown)
6. [Frontend — app.js & style.css](#6-frontend--appjs--stylecss)
7. [Configuration Files](#7-configuration-files)
8. [GitHub Actions Workflows](#8-github-actions-workflows)
9. [Generated Files](#9-generated-files)
10. [Test Suite](#10-test-suite)
11. [Design System & UI Patterns](#11-design-system--ui-patterns)
12. [Key Conventions & Gotchas](#12-key-conventions--gotchas)
13. [How To Add Things](#13-how-to-add-things)
14. [Recent Architecture Decisions](#14-recent-architecture-decisions)
15. [Known Limitations & Future Work](#15-known-limitations--future-work)
16. [Secrets & Environment Variables](#16-secrets--environment-variables)
17. [Quick Reference Commands](#17-quick-reference-commands)

---

## 1. What Is FinanceRadar?

FinanceRadar is an **India-focused financial news aggregator** that collects articles, reports, tweets, YouTube videos, and Telegram messages from ~194 sources, deduplicates them, filters noise, and renders a **single static HTML page** (3+ MB) served via Cloudflare Pages.

**The core loop:**

1. GitHub Actions runs every hour
2. Python scripts fetch ~194 RSS/Atom feeds + 10 custom scrapers + 7 Telegram channels
3. Content is deduplicated, filtered (126 title regex + 24 URL patterns), and grouped by headline similarity
4. A single `index.html` is generated with all CSS/JS inlined and all article data embedded as JS constants
5. Cloudflare Pages serves it statically — no backend server, no database

**Additionally, once daily at midnight UTC:**

- An AI ranker (Gemini + DeepSeek) picks the top 25 stories
- A "Who Said What" ranker generates 8 debate clusters from 7-day rolling data
- A "Missing Story Auditor" checks for feed coverage gaps

**The site has 6 tabs:** News, Telegram, Reports, YouTube, Twitter, Papers

---

## 2. Live Site & Deployment

- **Live URL:** `financeradar.kashishkapoor.com`
- **Hosting:** Cloudflare Pages (connected to GitHub repo)
- **Build command:** None (Cloudflare serves pre-built files)
- **Output directory:** `/` (root — `index.html` is at repo root)
- **GitHub repo:** `github.com:kashishkap00r/financeradar.git` (branch: `main`)
- **Update cycle:** `index.html` is rebuilt and committed by GitHub Actions every hour

---

## 3. Directory Structure

```
financeradar/
├── aggregator.py              (961 lines)  Main orchestrator
├── feeds.py                   (304 lines)  RSS/Atom fetching & parsing
├── articles.py                (220 lines)  Dedup, grouping, text utils
├── filters.py                 (320 lines)  Noise filtering (regex + URL patterns)
├── reports_fetcher.py         (844 lines)  10 custom institutional report scrapers
├── telegram_fetcher.py        (579 lines)  Telegram channel scraping (HTML + MTProto)
├── ai_ranker.py               (349 lines)  AI top-25 story ranking
├── wsw_ranker.py              (420 lines)  "Who Said What" debate clusters
├── twitter_signal.py          (659 lines)  Twitter signal processing (High Signal + Full Stream)
├── paper_fetcher.py           (212 lines)  Academic paper aggregator scraper
├── missing_story_auditor.py   (377 lines)  Feed coverage gap detector
├── config.py                  (62 lines)   Centralized constants
├── log_utils.py               (52 lines)   Structured logging (FeedLogger)
├── generate_session.py        (43 lines)   One-time Telethon session generator
│
├── auditor/                   Package for missing story auditor
│   ├── __init__.py
│   ├── adapters.py            (267 lines)  Data collection adapters
│   ├── matcher.py             (139 lines)  Story matching/comparison
│   └── output.py              (26 lines)   JSON/text output helpers
│
├── templates/
│   ├── app.js                 (2254 lines) All frontend JavaScript
│   └── style.css              (1867 lines) All frontend CSS
│
├── feeds.json                 (~194 feeds) Feed configuration
├── telegram_channels.json     (7 channels) Telegram channel config
├── requirements.txt           telethon>=1.36
├── favicon.svg
│
├── static/                    Auto-generated data files
│   ├── articles.json          Deduplicated news articles
│   ├── telegram_reports.json  Telegram messages
│   ├── youtube_cache.json     YouTube video metadata
│   ├── ai_rankings.json       AI top-25 picks
│   ├── wsw_clusters.json      Debate clusters
│   ├── reports_cache.json     Institutional reports
│   ├── papers_cache.json      Academic papers
│   ├── twitter_url_cache.json Google→X URL resolution cache
│   ├── published_snapshot.json All published items (for auditor)
│   └── favicon.svg
│
├── index.html                 (3+ MB) Generated static site
│
├── .github/workflows/
│   ├── hourly.yml             Hourly feed update
│   ├── ai-ranking.yml         Daily AI ranking + WSW
│   └── missing-story-audit.yml Daily coverage audit
│
├── tests/                     105 unit tests across 14 files
│   ├── test_filters.py
│   ├── test_articles.py
│   ├── test_date_parsing.py
│   ├── test_ai_ranker.py
│   ├── test_telegram_parser.py
│   ├── test_google_rss_utils.py
│   ├── test_ing_feed_parser.py
│   ├── test_missing_story_auditor.py
│   ├── test_paper_fetcher.py
│   ├── test_reports_fetcher_overrides.py
│   ├── test_story_matcher.py
│   ├── test_the_ken_fetch.py
│   ├── test_twitter_signal.py
│   └── test_video_feed_buckets.py
│
├── audit/                     Audit artifacts
│   ├── raw/YYYY-MM-DD/        Per-source raw snapshots
│   └── results/               Daily summary + missing stories JSON
│
├── docs/plans/                Design documents
│   ├── 2026-02-26-missing-story-auditor-design.md
│   ├── 2026-02-27-paper-tab-randomized-order-design.md
│   └── 2026-02-27-twitter-signal-lanes-design.md
│
├── CLAUDE.md                  Instructions for Claude Code
├── README.md                  Project documentation
├── Final_Debug_Plan.md        Recent debug plan (19 items, all completed)
└── cron.log                   Execution log
```

---

## 4. Architecture & Data Flow

### High-Level Pipeline

```
┌─────────────────────────────────────────────────────────┐
│                    CONFIGURATION                         │
│  feeds.json (194 feeds)   telegram_channels.json (7 ch) │
│  config.py (all constants)                               │
└─────────────┬───────────────────────────┬───────────────┘
              │                           │
              ▼                           ▼
┌─────────────────────────┐  ┌──────────────────────────┐
│     aggregator.py       │  │  telegram_fetcher.py     │
│  (main orchestrator)    │  │  (HTML + MTProto scrape) │
│                         │  └──────────┬───────────────┘
│  Uses:                  │             │
│  ├─ feeds.py (RSS)      │             ▼
│  ├─ reports_fetcher.py  │  static/telegram_reports.json
│  ├─ paper_fetcher.py    │
│  ├─ twitter_signal.py   │
│  ├─ articles.py (dedup) │
│  ├─ filters.py (noise)  │
│  └─ log_utils.py        │
│                         │
│  Outputs:               │
│  ├─ index.html          │
│  ├─ static/articles.json│
│  ├─ static/youtube_cache│
│  ├─ static/reports_cache│
│  ├─ static/papers_cache │
│  ├─ static/twitter_url  │
│  └─ static/published_   │
│     snapshot.json        │
└─────────────────────────┘

┌────────────────────────────────────────────────┐
│           DAILY AI PROCESSING                   │
│                                                  │
│  ai_ranker.py ──→ static/ai_rankings.json       │
│    (reads articles.json, calls Gemini+DeepSeek)  │
│                                                  │
│  wsw_ranker.py ──→ static/wsw_clusters.json      │
│    (reads articles+telegram+youtube, AI ranking) │
└────────────────────────────────────────────────┘

┌────────────────────────────────────────────────┐
│           DAILY AUDIT                           │
│                                                  │
│  missing_story_auditor.py                        │
│    (compares source feeds vs published output)   │
│    → audit/raw/YYYY-MM-DD/ (snapshots)           │
│    → audit/results/ (summary + missing_stories)  │
└────────────────────────────────────────────────┘
```

### How Feed Routing Works

Every feed in `feeds.json` has a `category` field that determines which tab it appears in:

| `category` value | Tab displayed | Keyboard shortcut |
|-------------------|---------------|-------------------|
| `News` (default)  | News          | `1`               |
| (n/a — Telegram)  | Telegram      | `2`               |
| `Reports`         | Reports       | `3`               |
| `Videos`          | YouTube       | `4`               |
| `Twitter`         | Twitter       | `5`               |
| (n/a — Papers)    | Papers        | `6`               |

Telegram data comes from `telegram_fetcher.py` (separate pipeline, not feeds.json).
Paper data comes from `paper_fetcher.py` (scrapes external aggregator site).

### How Feed Fetching is Dispatched

The `feed` field in feeds.json determines *how* each feed is fetched:

| `feed` pattern | Handler | Example |
|----------------|---------|---------|
| Standard URL (`https://...`) | `fetch_feed()` in `feeds.py` | `https://bfsi.economictimes.indiatimes.com/rss/articles` |
| `careratings:{PageId}` | `fetch_careratings()` in `feeds.py` | `careratings:9` |
| `careratings:{PageId}:{SectionId}` | `fetch_careratings()` in `feeds.py` | `careratings:1:23` |
| `{scraper_name}:{slug}` | `REPORT_FETCHERS[key]` in `reports_fetcher.py` | `crisil:views`, `gs:insights` |

---

## 5. Backend Modules — Detailed Breakdown

### aggregator.py (961 lines) — The Orchestrator

The heart of the project. `main()` does:

1. Loads all feeds from `feeds.json` via `load_feeds()`
2. Fetches all feeds in parallel (ThreadPoolExecutor, 10 workers, 15s timeout)
3. Routes results by category (News, Videos, Twitter, Reports)
4. For Twitter: runs `twitter_signal.py` processing (High Signal + Full Stream lanes)
5. For Papers: runs `paper_fetcher.py`
6. Deduplicates and groups similar articles via `articles.py`
7. Filters noise via `filters.py`
8. Generates `index.html` via `generate_html()` — inlines CSS from `templates/style.css`, JS from `templates/app.js`, and embeds all data as JS constants
9. Exports `static/articles.json`, `static/youtube_cache.json`, etc.

**Key function:** `generate_html()` — Uses Python f-strings to build the HTML. CSS and JS are read from their template files and inlined. Article data is injected as JS `const` variables at the top of the script block, *before* the app.js content.

**Brace rule:** Inside `generate_html()`, all literal `{` and `}` must be doubled (`{{`/`}}`) because it's an f-string. The template files (`app.js`, `style.css`) use normal braces.

**URL sanitization:** `sanitize_url(url)` — validates that URLs start with `http://` or `https://` before inserting into `href` attributes (prevents `javascript:` XSS).

### feeds.py (304 lines) — Feed Fetching & Parsing

- `load_feeds()` — Reads `feeds.json`, returns list of feed configs
- `parse_date(date_str, source_name)` — Multi-format date parser (RFC 2822, ISO 8601, RBI, SEBI formats)
- `fetch_feed(feed_config)` — Fetches and parses RSS/Atom XML. On HTTP 403, falls back to curl with browser User-Agent
- `fetch_careratings(feed_config)` — Fetches CareRatings JSON API
- `fetch_the_ken(feed_config)` — Specialized fetcher for The Ken (paywalled)

**SSL handling:** Uses verified SSL by default. On `ssl.SSLCertVerificationError`, falls back to unverified context with a warning log. Two contexts are exported: `SSL_CONTEXT` (verified) and `SSL_CONTEXT_NOVERIFY` (fallback).

**Invidious instances:** `inv.nadeko.net`, `yewtu.be`, `iv.datura.network` — used to convert YouTube RSS to standard Atom format.

### articles.py (220 lines) — Dedup & Grouping

- `normalize_title(title)` — Lowercases, strips prefixes (`BREAKING:`, `EXCLUSIVE:`, etc.), cleans punctuation
- `titles_are_similar(t1, t2, threshold=0.75)` — SequenceMatcher fuzzy match
- `group_similar_articles(articles)` — Groups articles with similar headlines (same calendar day only). Returns `[{"primary": article, "all_articles": [...]}]`
- `clean_html(html)` — Strips tags, decodes entities, collapses whitespace, truncates to 250 chars
- `clean_twitter_title(title)` — Removes Twitter API meta patterns
- `to_local_datetime(dt)` — UTC → IST conversion
- `export_articles_json(articles, filename)` — Writes `static/articles.json`

### filters.py (320 lines) — Content Noise Filtering

- `should_filter_article(article)` → `bool` — Checks title against 126 regex patterns and URL against 24 substring patterns
- `should_filter_video(article)` → `bool` — Video-specific filters

**Filter categories include:** market price movements, RBI routine ops, live tickers, IPO noise, MF/SIP routine, holiday notices, weekly roundups, crypto prices, stock tips, brokerage calls, earnings roundups, personal finance clickbait, penny stocks, event promos, video meta tags.

**Effect:** Catches ~249 noise articles per run.

### reports_fetcher.py (844 lines) — Institutional Report Scrapers

10 custom scrapers for institutional research reports:

| Scraper key | Source | Method |
|-------------|--------|--------|
| `crisil` | CRISIL (ratings + research) | HTML scraping |
| `baroda` | Bank of Baroda eTrade | HTML scraping |
| `sbi` | SBI (Ecowrap publication) | HTML scraping |
| `ficci` | FICCI (economic wraps) | HTML scraping |
| `icici` | ICICI Securities | HTML scraping |
| `hdfcsec` | HDFC Securities | HTML scraping |
| `axis` | Axis Direct | HTML scraping |
| `gs` | Goldman Sachs (insights) | RSS |
| `creditsights` | CreditSights | HTML scraping |
| `jpmorgan` | JPMorgan | Google News RSS |

**Key pattern — `@scraper` decorator:**
```python
@scraper
def fetch_crisil(feed_config):
    # Only the unique parsing logic — decorator handles:
    # - try/except with [OK]/[FAIL] logging
    # - freshness filtering (30 days)
    # - max article cap (30 items)
    return articles
```

**Shared utilities:**
- `_fetch_url(url, accept, timeout)` — urllib with curl fallback on 403, retry logic (2 attempts, 1.5s backoff)
- `_make_article(title, source, link, date, html)` — Standard article dict constructor
- `_strip_html(html)` — Strips tags, decodes entities
- `_parse_date_flexible(date_str)` — Parses 10+ date formats
- `_is_fresh(dt)` — 30-day freshness guard

### telegram_fetcher.py (579 lines) — Telegram Channel Scraping

Two methods:
- **HTML scraping** (`method: "html"`) — Public channels via `t.me/s/{username}`. Uses custom `TelegramHTMLParser(HTMLParser)` to extract messages, documents, media, views, dates.
- **MTProto** (`method: "mtproto"`) — Private groups via Telethon library. Requires `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION` env vars.

**Key features:**
- Pagination via `before_id` for HTML scraping (up to 15 pages)
- Multi-document support per message (`"documents": [...]`)
- OG image extraction for thumbnails
- Credential redaction in error messages (`_redact_credentials()`)

### ai_ranker.py (349 lines) — AI Story Ranking

Selects top 25 stories from the last 48 hours of articles.

**Two AI providers (failover):**
1. **Gemini 3.0 Flash** → `generativelanguage.googleapis.com` (120s timeout)
2. **DeepSeek V3.2** → `openrouter.ai/api/v1` (60s timeout, via `OPENROUTER_API_KEY`)

**Ranking prompt priorities:**
- Explanatory "why/how" journalism over wire summaries
- Max 3 stories per sector (diversity rule)
- India-lens required for global stories
- Hard skips: earnings, routine filings, market noise, crypto, broker calls

**Title matching:** 3-stage lookup for mapping AI-returned titles to real articles:
1. Exact sanitized match
2. Normalized match (dash/quote normalization)
3. Fuzzy SequenceMatcher (0.72 threshold)

**Output validation:** Checks that returned JSON is a list; rejects if >50% of titles are blank.

### wsw_ranker.py (420 lines) — "Who Said What"

Generates 8 debate clusters from 7-day rolling data (news + Telegram + YouTube + Twitter).

**Same two AI providers as ai_ranker.py.**

**Cluster schema:** Each cluster has `cluster_title`, `theme`, `india_relevance`, `core_claim`, `quote_snippet`, `quote_speaker`, `quote_source_type`, URLs, `counter_view`, `why_it_matters`, `confidence`.

**JSON recovery:** If AI returns truncated JSON, uses progressive backward truncation to find the last valid `}` boundary.

### twitter_signal.py (659 lines) — Twitter Processing

Produces two tweet lanes:
- **Full Stream:** All cleaned tweets
- **High Signal:** Top 25 from last 24 hours, no retweets, AI-ranked with deterministic fallback

**Key operations:**
1. Resolves Google News RSS wrapper URLs to direct `x.com/.../status/...` URLs (concurrent, 8 workers)
2. Collapses thread bursts (one tweet per thread)
3. Applies noise filtering
4. AI ranking for High Signal lane (Gemini + DeepSeek, same providers)

### paper_fetcher.py (212 lines) — Academic Papers

Scrapes `paper-aggregator-india.netlify.app/` — an external aggregator of India-relevant academic papers. Extracts title, authors, summary, date, and source URL via regex on HTML.

### missing_story_auditor.py (377 lines) + auditor/ package

**Purpose:** Detects stories that appear on source websites but are missing from FinanceRadar output.

**How it works:**
1. **Source snapshot layer** (`auditor/adapters.py`): Fetches current state of all configured sources
2. **Matching layer** (`auditor/matcher.py`): Compares source items against `published_snapshot.json` using title normalization + URL normalization
3. **Output layer** (`auditor/output.py`): Writes results to `audit/raw/` (per-source snapshots) and `audit/results/` (summary)

**SLA:** A story is "missing/late" if it doesn't appear within 6 hours of source publication.
**Window:** Last 7 days.

### config.py (62 lines) — Centralized Constants

All tunable parameters in one place. Imported by every module. Key groups:

```python
# Feed fetching
FEED_FETCH_TIMEOUT = 15          # seconds
FEED_THREAD_WORKERS = 10         # concurrent workers
MAX_ARTICLES_PER_FEED = 50       # cap per feed

# Freshness windows
NEWS_FRESHNESS_DAYS = 5
TWITTER_FRESHNESS_DAYS = 5
REPORTS_FRESHNESS_DAYS = 30
VIDEO_FRESHNESS_DAYS = 10

# Report scrapers
SCRAPER_MAX_ARTICLES = 30
SCRAPER_RETRY_ATTEMPTS = 2
SCRAPER_RETRY_BACKOFF = 1.5

# Telegram
TELEGRAM_MAX_PAGES = 15
TELEGRAM_MAX_AGE_DAYS = 5

# AI rankers
AI_RANKER_ARTICLE_WINDOW_HOURS = 48
AI_RANKER_MAX_ARTICLES = 200
AI_RANKER_TARGET_COUNT = 25
WSW_LOOKBACK_DAYS = 7

# Thresholds
FEED_FAILURE_ALERT_THRESHOLD = 0.3  # alert if >30% feeds fail

# Auditor
AUDIT_LOOKBACK_DAYS = 7
AUDIT_SLA_HOURS = 6
```

### log_utils.py (52 lines) — Structured Logging

`FeedLogger` class wrapping `print()` with:
- `ok(source, detail)` / `fail(source, error)` / `warn(source, msg)` / `info(msg)` — All prefixed with `[HH:MM:SS]` IST timestamp
- `add_articles(count)` — Tracks total article count
- `summary()` — Prints `=== X/Y sources succeeded, Z failed, N articles ===`

---

## 6. Frontend — app.js & style.css

### templates/app.js (2254 lines)

The entire frontend is a single JS file, injected into `index.html` by `aggregator.py`. All article data is embedded as JS constants at the top of the `<script>` block (before app.js content is appended).

**Injected data constants (set by aggregator.py):**
- `ALL_PUBLISHERS` — Unique publisher names
- `PUBLISHER_PRESETS` — `{"India Desk": [...], "World Desk": [...], "Indie Voices": [...], ...}`
- `ALL_ARTICLES` — Full articles.json data
- `TELEGRAM_REPORTS` — telegram_reports.json
- `AI_RANKINGS` — ai_rankings.json
- `WSW_CLUSTERS` — wsw_clusters.json
- `YOUTUBE_VIDEOS` — youtube_cache.json
- `RESEARCH_REPORTS` — Reports tab articles
- `PAPER_ARTICLES` — papers_cache.json
- `TWITTER_FULL_STREAM` / `TWITTER_HIGH_SIGNAL` — Twitter lanes

**Major sections:**
1. **Theme system** — `safeStorage` localStorage wrapper, `setTheme()`/`toggleTheme()`, persisted to `theme` key
2. **Tab navigation** — 6 tabs (News, Telegram, Reports, YouTube, Twitter, Papers), keyboard shortcuts `1`-`6`
3. **Publisher filtering** — Multi-select dropdown, presets, search-within-dropdown
4. **Article rendering** — Card layout with headline, publisher, date, summary, similarity grouping
5. **Pagination** — Load-more button at bottom
6. **Bookmarks** — LocalStorage-based (`financeradar_bookmarks` key), per-article toggle
7. **Sidebars:**
   - AI Rankings (top-bar icon) — Top 25 picks
   - In Focus (pinned articles with count badge)
   - Who Said What (debate clusters)
   - Bookmarks modal
8. **Twitter sub-tabs** — "High Signal" (default) and "Full Stream" toggle
9. **Papers tab** — Fisher-Yates shuffle on tab open for discovery
10. **Keyboard shortcuts** — `1`-`6` tabs, `h` help, `Escape` close, `f` filter toggle, `b` bookmarks

**Security functions:**
- `escapeHtml(str)` — Escapes `&<>"'` for innerHTML
- `escapeForAttr(str)` — Escapes for HTML attributes
- `sanitizeUrl(url)` — Rejects non-http(s) URLs (prevents `javascript:` XSS)

### templates/style.css (1867 lines)

**Design system:**
- **Fonts:** Merriweather (headings), Source Sans Pro (body)
- **Accent color:** `#e14b4b` (red)
- **Dark mode:** `#0f1419` background (warm charcoal)
- **Theming:** CSS variables on `:root` and `[data-theme="dark"]`

**Key CSS variables:**
```css
--bg-primary, --bg-secondary, --bg-hover
--text-primary, --text-secondary, --text-muted
--accent, --accent-hover
--border, --border-light
--card-shadow
--danger  /* for destructive actions */
```

**Layout:** Sticky top bar → filter card → article card grid → load-more pagination

**Responsive:** Media queries for mobile (<600px) and tablet (600-900px). Filter bar collapses on mobile.

**Tooltip system:** All top-bar buttons use `data-tooltip` CSS tooltips (not native `title`).

---

## 7. Configuration Files

### feeds.json (~194 feeds)

```json
[
  {
    "id": "unique-feed-id",
    "name": "Display Name",
    "url": "https://source-website.com",
    "feed": "https://source.com/rss",
    "category": "News|Videos|Reports|Twitter",
    "publisher": "Publisher Name",
    "region": "Indian|International"
  }
]
```

**Feed counts by category (approximate):**
- News: ~107
- Twitter: ~47
- Reports: ~25
- Videos: ~15

### telegram_channels.json (7 channels)

```json
[
  {"username": "Brokerage_report", "label": "Brokerage Reports", "method": "mtproto"},
  {"username": "BeatTheStreetnews", "label": "Beat The Street", "method": "html"},
  {"username": "stockupdate9", "label": "Stock Update", "method": "html"},
  {"username": "btsreports", "label": "BTS Reports", "method": "mtproto"},
  {"username": "Equity_Insights", "label": "Equity Insights", "method": "mtproto", "max_age_days": 30},
  {"username": "stockmarketbooksresearchreport", "label": "Stock Market Research", "method": "mtproto"},
  {"username": "researchreportss", "label": "Research Reports", "method": "mtproto"}
]
```

- `html` = public channel, scraped via `t.me/s/` HTML
- `mtproto` = private group, requires Telethon credentials

### requirements.txt

```
telethon>=1.36
```

Only non-stdlib dependency. Everything else uses Python 3.8+ standard library (`urllib`, `html.parser`, `xml.etree`, `json`, `ssl`, `concurrent.futures`, `difflib`, etc.).

**Runtime dependency:** `curl` binary (used as fallback for HTTP 403 responses).

---

## 8. GitHub Actions Workflows

### hourly.yml — "Update FinanceRadar"

**Schedule:** `0 * * * *` (every hour) + manual dispatch
**Steps:**
1. Checkout (SHA-pinned `actions/checkout@34e...`)
2. Setup Python 3.x (SHA-pinned `actions/setup-python@a26...`)
3. `pip install -r requirements.txt`
4. Validate Telegram secrets
5. `python3 telegram_fetcher.py`
6. `python3 aggregator.py`
7. Commit + pull (no-rebase) + push if files changed

**Committed files:** `index.html`, `static/articles.json`, `static/telegram_reports.json`, `static/youtube_cache.json`, `static/reports_cache.json`, `static/published_snapshot.json`, `static/papers_cache.json`, `static/twitter_url_cache.json`

### ai-ranking.yml — "AI News Ranking"

**Schedule:** `0 0 * * *` (midnight UTC = 5:30 AM IST) + manual dispatch
**Steps:**
1. Checkout + Setup Python
2. Validate `GEMINI_API_KEY`
3. `python3 ai_ranker.py`
4. `python3 wsw_ranker.py`
5. Commit + pull (no-rebase) + push

**Committed files:** `static/ai_rankings.json`, `static/wsw_clusters.json`

**Schedule rationale:** Midnight UTC absorbs GitHub Actions 1-2 hour delay, so results are ready by ~8 AM IST.

### missing-story-audit.yml — "Missing Story Audit"

**Schedule:** `30 0 * * *` (30 min past midnight UTC) + manual dispatch
**Steps:**
1. Checkout (read-only, `persist-credentials: false`)
2. Setup Python
3. Ensure `published_snapshot.json` exists (runs `aggregator.py` if missing)
4. `python3 missing_story_auditor.py --days 7 --sla-hours 6 --tabs all`
5. Upload `audit/` as GitHub Actions artifact

**Important:** This workflow has `contents: read` only — it does NOT commit results to the repo. Audit artifacts are downloadable from the workflow run.

---

## 9. Generated Files

All tracked in git. **Never hand-edit these** — they will be overwritten hourly.

| File | Updated | By | Contents |
|------|---------|----|----------|
| `index.html` | Hourly | `aggregator.py` | Complete static site (3+ MB, CSS/JS/data inlined) |
| `static/articles.json` | Hourly | `articles.py` | Deduplicated, grouped news articles |
| `static/telegram_reports.json` | Hourly | `telegram_fetcher.py` | Telegram messages from 7 channels |
| `static/youtube_cache.json` | Hourly | `aggregator.py` | YouTube video metadata |
| `static/reports_cache.json` | Hourly | `aggregator.py` | Institutional research reports |
| `static/papers_cache.json` | Hourly | `aggregator.py` | Academic papers |
| `static/twitter_url_cache.json` | Hourly | `twitter_signal.py` | Google→X URL resolution cache |
| `static/published_snapshot.json` | Hourly | `aggregator.py` | All published items (for auditor) |
| `static/ai_rankings.json` | Daily | `ai_ranker.py` | AI top-25 ranked stories |
| `static/wsw_clusters.json` | Daily | `wsw_ranker.py` | 8 debate clusters |

**Merge conflict note:** These files conflict frequently when rebasing because GitHub Actions commits them every hour. **Always resolve by taking the remote version** (`--theirs`). Better yet, use `git merge` not `git rebase`.

---

## 10. Test Suite

**105 tests across 14 files.** Run with:

```bash
python3 -m unittest discover -s tests
```

All tests run in <0.1s (no network calls, no file I/O — pure unit tests with fixtures).

| Test file | Tests | What it covers |
|-----------|-------|---------------|
| `test_filters.py` | ~14 | `should_filter_article()` — title regex, URL patterns, edge cases |
| `test_articles.py` | ~13 | `clean_html()`, `titles_are_similar()`, `group_similar_articles()` |
| `test_date_parsing.py` | ~12 | `parse_date()` (feeds.py), `_parse_date_flexible()` (reports_fetcher.py) |
| `test_ai_ranker.py` | ~12 | JSON response parsing, title sanitization, fuzzy matching |
| `test_telegram_parser.py` | ~9 | HTML message extraction, document parsing, edge cases |
| `test_google_rss_utils.py` | ~8 | Google News RSS URL resolution |
| `test_ing_feed_parser.py` | ~7 | ING THINK RSS feed parser |
| `test_missing_story_auditor.py` | ~8 | Auditor matching and comparison logic |
| `test_paper_fetcher.py` | ~6 | Paper HTML scraping |
| `test_reports_fetcher_overrides.py` | ~5 | Scraper timeout/retry config overrides |
| `test_story_matcher.py` | ~5 | Title/URL normalization and matching |
| `test_the_ken_fetch.py` | ~3 | The Ken paywalled feed handling |
| `test_twitter_signal.py` | ~4 | Twitter signal processing lanes |
| `test_video_feed_buckets.py` | ~3 | YouTube feed bucket categorization |

**No linting or type-checking** is configured. Tests are the only automated quality gate.

---

## 11. Design System & UI Patterns

### Visual Design
- **Typography:** Merriweather (serif, headings), Source Sans Pro (sans-serif, body)
- **Accent:** `#e14b4b` red (links, buttons, active states)
- **Dark mode:** Warm charcoal `#0f1419` background, not pure black
- **Cards:** White/dark cards with subtle shadows, rounded corners
- **The `--danger` variable:** Used for destructive actions (delete, clear)

### Component Patterns

**Dropdown (multi-select):** Reused across all tabs for publisher filtering.
Structure: `.publisher-dropdown` → `.publisher-dropdown-trigger` → `.publisher-dropdown-panel`
Close wired in 3 places: click-outside handler, Escape key, `toggleFilterCollapse()`.

**Tab filter card:** `.filter-card` → `.stats-bar` (count + timestamp) → `.filter-row` (controls)

**Top bar icons:** 32x32 buttons with `data-tooltip` CSS tooltips:
- AI Rankings (pulse dot + count badge)
- Bookmarks
- In Focus (pulse dot + count badge)
- Who Said What
- Theme toggle

**Sidebar overlay:** Right-side panel sliding over content. Close via X button or Escape. Scrollable content area.

### localStorage Keys
- `theme` — `"light"` or `"dark"`
- `financeradar_bookmarks` — JSON array of bookmarked articles
- All access via `safeStorage` wrapper (try/catch for incognito mode)

---

## 12. Key Conventions & Gotchas

### Brace Rules (Critical)
- `templates/app.js` and `templates/style.css` use **normal braces** `{}`
- `aggregator.py generate_html()` uses **doubled braces** `{{`/`}}` for literal braces (f-string context)
- **Never mix these up** — wrong braces silently produce broken output

### JS Data Injection Order
Data constants (`ALL_PUBLISHERS`, `ALL_ARTICLES`, etc.) are injected *before* `app.js` content in the HTML `<script>` block. All `const`/`let` declarations must come before code that references them (temporal dead zone). `function` declarations are hoisted and safe anywhere.

### Git Workflow
- **Never use `git rebase`** — partial conflict resolution leaves merge markers in `index.html`
- Use `git merge origin/main -X ours --no-edit` to resolve remote-ahead conflicts
- Workflows use `git pull --no-rebase` before push

### GitHub Actions SHA Pinning
All Actions are pinned to commit SHAs (not version tags) for supply-chain security:
- `actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5` (v4)
- `actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065` (v5)
- `actions/upload-artifact@65462800fd760344b1a7b4382951275a0abb4808` (v4)

### SSL/TLS Pattern
All HTTP fetching uses verified SSL by default, with fallback to unverified on `ssl.SSLCertVerificationError`. The fallback logs a warning. Two contexts exported from `feeds.py`: `SSL_CONTEXT` and `SSL_CONTEXT_NOVERIFY`.

### Error Handling in Scrapers
The `@scraper` decorator in `reports_fetcher.py` wraps all 10 scrapers with uniform error handling, freshness filtering, and logging. Individual scrapers only contain the unique parsing logic.

### Credential Safety
- Telegram credentials are read at function call time (not module load) via `_get_telegram_credentials()`
- Error messages are sanitized via `_redact_credentials()` (strips hex hashes, long tokens)
- AI API keys are redacted with regex: `r'AIza\S{20,}|sk-or-\S{20,}|Bearer\s+\S+|key[=:]\s*["\']?\S{10,}'`

---

## 13. How To Add Things

### Add a New RSS Feed
1. Add entry to `feeds.json`:
   ```json
   {"id": "unique-id", "name": "Display Name", "url": "https://...", "feed": "https://.../rss", "category": "News", "publisher": "Publisher Name"}
   ```
2. Run `python3 aggregator.py` to verify
3. That's it — the hourly workflow picks it up automatically

### Add a New Report Scraper
1. Write `fetch_newname(feed_config)` in `reports_fetcher.py` returning `list[dict]` via `_make_article()`
2. Decorate with `@scraper`
3. Add to `REPORT_FETCHERS` dict: `"newname:": fetch_newname`
4. Add feed in `feeds.json`: `{"feed": "newname:slug", "category": "Reports", "region": "Indian"}`

### Add a New Telegram Channel
1. Add entry to `telegram_channels.json`:
   ```json
   {"username": "channel_name", "label": "Display Name", "method": "html"}
   ```
   Use `"method": "mtproto"` for private groups (requires credentials).

### Add a New Filter Pattern
1. Add regex to `TITLE_PATTERNS` or URL substring to `URL_PATTERNS` in `filters.py`
2. Run tests: `python3 -m unittest tests.test_filters`

### Add a New Tab
This is a larger change touching multiple files:
1. `aggregator.py` — Add data injection constant and HTML tab button in `generate_html()`
2. `templates/app.js` — Add tab switching logic, rendering function, pagination
3. `templates/style.css` — Add any tab-specific styles
4. `feeds.json` — Add feeds with new `category` value
5. `config.py` — Add freshness/limit constants if needed

### Add a New AI Provider
In `ai_ranker.py` or `wsw_ranker.py`:
1. Add `call_newprovider(prompt)` function
2. Add to the provider fallback chain in `main()`
3. Add timeout constant to `config.py`

---

## 14. Recent Architecture Decisions

### Debug & Improvement Plan (Feb 2026 — 19 items, all completed)
1. Removed duplicate `isBookmarked()` function
2. Fixed XSS in YouTube alt attributes
3. Fixed stale freshness log messages
4. Merged duplicate bookmark toggle functions
5. Added URL scheme allowlist (`sanitizeUrl`/`sanitize_url`)
6. Re-enabled TLS verification with SSLCertVerificationError fallback
7. Expanded API key redaction regex
8. Moved Telegram credentials to function-level
9. Added `@scraper` decorator to reports_fetcher.py
10. Added retry logic to `_fetch_url()`
11. Added UBS curl failure warning
12. Added JSON schema validation for AI outputs
13. Replaced brace-counting JSON recovery with progressive truncation
14. Added feed failure threshold alerts
15. Created test suite (now 105 tests)
16. Added structured logging (`FeedLogger`)
17. Changed CI from `git pull --rebase` to `--no-rebase`
18. Pinned GitHub Actions to commit SHAs
19. Created `config.py` for centralized constants

### Twitter Signal Lanes (Feb 2026)
Split Twitter tab into "High Signal" (AI-ranked top 25) and "Full Stream" (all tweets).

### Missing Story Auditor (Feb 2026)
Automated daily audit checking all source feeds against published output. Uses 6-hour SLA, 7-day window.

### Papers Tab (Feb 2026)
Academic papers from external aggregator. Client-side Fisher-Yates shuffle on tab open for discovery.

---

## 15. Known Limitations & Future Work

### Current Limitations
- **No database** — All data is in-memory during pipeline run, then serialized to JSON. Historical data is lost each run (except what's in git history).
- **Single HTML file** — At 3+ MB, initial load is heavy. No code splitting, lazy loading, or pagination API.
- **No authentication** — The site is fully public, no user accounts.
- **GitHub Actions cron latency** — Runs typically 1-2 hours late. Content freshness depends on this.
- **Telegram private groups** — Only work with MTProto credentials. HTML method fails for private groups.
- **No real-time updates** — Content updates hourly via static rebuild. No WebSocket/SSE.

### Pending / Future Ideas
- **Telegram Bot for Private Groups:** Use Bot API or Telethon for `btsreports`, `researchreportss`
- **More YouTube channels:** ET Now, CNBC-TV18, freefincal — need channel IDs
- **More Twitter accounts:** Can add via feeds.json entries
- **Incremental builds:** Only regenerate changed sections instead of full HTML rebuild
- **Client-side caching:** Service worker or localStorage for offline access
- **Search API:** Full-text search across historical articles

---

## 16. Secrets & Environment Variables

| Variable | Required by | Purpose |
|----------|-------------|---------|
| `TELEGRAM_API_ID` | telegram_fetcher.py | Telegram API application ID |
| `TELEGRAM_API_HASH` | telegram_fetcher.py | Telegram API application hash |
| `TELEGRAM_SESSION` | telegram_fetcher.py | Telethon StringSession (generated via `generate_session.py`) |
| `GEMINI_API_KEY` | ai_ranker.py, wsw_ranker.py, twitter_signal.py | Google Gemini API key (starts with `AIza...`) |
| `OPENROUTER_API_KEY` | ai_ranker.py, wsw_ranker.py, twitter_signal.py | OpenRouter API key (starts with `sk-or-...`), optional fallback |

All are set as GitHub repository secrets and passed to workflows via `env:` blocks.

---

## 17. Quick Reference Commands

```bash
# Full pipeline (what the hourly workflow does)
python3 telegram_fetcher.py
python3 aggregator.py

# AI ranking (what the daily workflow does)
GEMINI_API_KEY="..." OPENROUTER_API_KEY="..." python3 ai_ranker.py
GEMINI_API_KEY="..." OPENROUTER_API_KEY="..." python3 wsw_ranker.py

# Missing story audit
python3 missing_story_auditor.py --days 7 --sla-hours 6 --tabs all

# Run tests
python3 -m unittest discover -s tests

# Test a specific filter
python3 -c "from filters import should_filter_article; print(should_filter_article({'title': 'TEST', 'link': ''}))"

# Local preview
python3 -m http.server 8000

# Generate Telegram session string (one-time)
python3 generate_session.py

# Git: resolve remote-ahead conflicts
git fetch origin
git merge origin/main -X ours --no-edit
git push
```

---

*This document was generated on 2026-03-01 for LLM-to-LLM project handoff.*
