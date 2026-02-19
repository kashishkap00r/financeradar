# FinanceRadar

A Python RSS/Atom aggregator that fetches 106 feeds and generates a single static HTML page focused on Indian finance and business news. Deployed hourly via GitHub Actions to Cloudflare Pages.

**Live site:** [financeradar.kashishkapoor.com](https://financeradar.kashishkapoor.com)

---

## Table of Contents

1. [Features](#features)
2. [Quick Start](#quick-start)
3. [Project Structure](#project-structure)
4. [Architecture & Data Flow](#architecture--data-flow)
5. [Feed Configuration](#feed-configuration)
6. [Telegram Channels](#telegram-channels)
7. [Processing Pipeline](#processing-pipeline)
8. [aggregator.py Internals](#aggregatorpy-internals)
9. [filters.py](#filterspy)
10. [telegram_fetcher.py Internals](#telegram_fetcherpy-internals)
11. [ai_ranker.py Internals](#ai_rankerpy-internals)
12. [UI Features](#ui-features)
13. [GitHub Actions & Deployment](#github-actions--deployment)
14. [Customization](#customization)
15. [Generated Files](#generated-files)
16. [Git Conventions](#git-conventions)
17. [Troubleshooting](#troubleshooting)
18. [Requirements](#requirements)

---

## Features

- **106 feeds** — 96 news sources + 6 YouTube channels + 4 Twitter/X keyword feeds
- **Four tabs** — News, Telegram (brokerage reports), YouTube, Twitter
- **AI rankings** — Daily top-20 picks via OpenRouter, shown in an "In Focus" sidebar
- **Telegram brokerage reports** — Fetched from 7 channels via HTML scraping + Telethon MTProto
- **Content filtering** — 126 title regex + 24 URL substring patterns remove noise
- **Headline grouping** — Clusters near-duplicate headlines from different sources
- **Bookmarks** — Save articles with `localStorage` persistence
- **Search** — Real-time client-side filtering across all tabs
- **Keyboard navigation** — J/K to move, `/` to search
- **Dark/Light mode** — Theme toggle with persistence
- **10-day freshness** — Only recent articles shown
- **Zero runtime dependencies** — Single static HTML file, deploys anywhere
- **Mobile-friendly** — Collapsible filter row on ≤640px screens

---

## Quick Start

```bash
# Generate the static site (~2 minutes, fetches 106 feeds)
python3 aggregator.py

# Fetch Telegram reports (HTML-only without credentials)
python3 telegram_fetcher.py

# Fetch Telegram reports with MTProto private channels
TELEGRAM_API_ID="..." TELEGRAM_API_HASH="..." TELEGRAM_SESSION="..." python3 telegram_fetcher.py

# Run AI ranking (requires API key)
OPENROUTER_API_KEY="sk-or-..." python3 ai_ranker.py

# Preview locally
python3 -m http.server 8000
# Open http://localhost:8000

# Generate Telethon session string (one-time, interactive)
pip install telethon && python3 generate_session.py
```

**Dependencies:** `telethon>=1.36` (in `requirements.txt`). Everything else is Python 3.8+ stdlib. No tests, no linter, no build system.

---

## Project Structure

```
financeradar/
├── aggregator.py              # Everything: fetch, parse, filter, dedupe, group, render HTML
├── filters.py                 # Content filter patterns (extracted for easy editing)
├── telegram_fetcher.py        # Hybrid Telegram fetcher (HTML scraper + Telethon MTProto)
├── ai_ranker.py               # Reads articles.json, calls OpenRouter, writes ai_rankings.json
├── generate_session.py        # One-time interactive script to create Telethon StringSession
├── feeds.json                 # 106 feed configurations
├── telegram_channels.json     # 7 Telegram channel configurations
├── requirements.txt           # telethon>=1.36
├── .gitignore                 # Excludes __pycache__, *.pyc, cron.log, *.session, .env
├── .github/workflows/
│   ├── hourly.yml             # Hourly: telegram_fetcher.py → aggregator.py → commit/push
│   └── ai-ranking.yml         # Daily midnight UTC: ai_ranker.py → commit/push
├── static/
│   ├── articles.json          # GENERATED — structured articles for AI ranker
│   ├── ai_rankings.json       # GENERATED — AI-ranked top 20 stories
│   ├── telegram_reports.json  # GENERATED — scraped Telegram messages
│   ├── youtube_cache.json     # GENERATED — YouTube feed cache
│   └── favicon.svg            # Site icon (📰)
├── index.html                 # GENERATED — full static site (~3 MB)
└── cron.log                   # GENERATED — execution logs (gitignored)
```

---

## Architecture & Data Flow

```
feeds.json (106 feeds)
  → aggregator.py
      ├─ Parallel fetch (10 workers, 15s timeout, curl fallback on 403)
      ├─ Split: Videos → YouTube tab, Twitter → Twitter tab
      ├─ News pipeline: dedup → filter (filters.py) → group similar headlines → sort
      └─ generate_html() → index.html  +  static/articles.json

telegram_channels.json (7 channels)
  → telegram_fetcher.py
      ├─ "html" method  → scrapes t.me/s/{username} HTML
      └─ "mtproto" method → Telethon MTProto (private/restricted channels)
  → static/telegram_reports.json

static/articles.json
  → ai_ranker.py
      └─ OpenRouter API (LLM ranking) → static/ai_rankings.json

Browser loads index.html
  ├─ Fetches static/telegram_reports.json (Telegram tab)
  ├─ Fetches static/ai_rankings.json (In Focus sidebar)
  └─ All news/video/twitter content is embedded in the HTML at build time
```

---

## Feed Configuration

Each entry in `feeds.json`:

```json
{
  "id": "et-bfsi-articles",
  "name": "ET BFSI — Articles",
  "url": "https://bfsi.economictimes.indiatimes.com",
  "feed": "https://bfsi.economictimes.indiatimes.com/rss/articles",
  "category": "News"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique identifier (slug) |
| `name` | Yes | Display name shown in the UI |
| `url` | Yes | Homepage of the source |
| `feed` | Yes | RSS/Atom feed URL |
| `category` | Yes | Pipeline routing: `"News"`, `"Videos"`, or `"Twitter"` |
| `publisher` | No | Override publisher label shown on article cards |

### Category Routing

The `category` field is used **only for internal routing** — it is not displayed to users.

| Category | Routed to | Processing |
|----------|-----------|------------|
| `"News"` | News tab | Dedup → filter → group → paginate |
| `"Videos"` | YouTube tab | Parse Atom with `yt:videoId` + `media:thumbnail`, horizontal card layout |
| `"Twitter"` | Twitter tab | Google News RSS (`site:x.com` queries), standard card layout |

**Special feed URL patterns:**
- Google News RSS workaround: `news.google.com/rss/search?q=site:domain.com/section`
- The Core: `/category/google_feeds.xml`
- Indian Express: `/section/feed/`
- YouTube: `https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID`

---

## Telegram Channels

`telegram_channels.json` — 7 channels currently configured:

| Username | Label | Method |
|----------|-------|--------|
| `Brokerage_report` | Brokerage Reports | `mtproto` |
| `BeatTheStreetnews` | Beat The Street | `html` |
| `stockupdate9` | Stock Update | `html` |
| `btsreports` | BTS Reports | `mtproto` |
| `Equity_Insights` | Equity Insights | `mtproto` |
| `stockmarketbooksresearchreport` | Stock Market Research | `mtproto` |
| `researchreportss` | Research Reports | `mtproto` |

HTML method works only for public channels that serve preview pages at `t.me/s/{username}`. Private groups/channels require MTProto.

---

## Processing Pipeline

```
106 feeds
    ↓ Parallel fetch (10 workers)
~4,500 raw articles
    ↓ URL deduplication (normalized: lowercase, trailing slash, http→https)
~4,000 unique articles
    ↓ Content filtering (filters.py: 126 title regex + 24 URL patterns)
~3,500 relevant articles
    ↓ 10-day freshness filter
~1,300 recent articles
    ↓ Per-feed cap (50 articles max)
~1,200 final articles
    ↓ Headline grouping (SequenceMatcher 75% threshold, same-day only)
    ↓ HTML generation (embedded CSS + JS)
index.html (~3 MB) + static/articles.json
```

---

## aggregator.py Internals

This is the core file (~3,600 lines). Everything lives here: feed fetching, parsing, filtering, deduplication, headline grouping, and the entire frontend as a single embedded f-string.

### Key Python Functions

| Function | Description |
|----------|-------------|
| `fetch_feed(feed)` | Fetches one feed URL, falls back to `curl` on 403. Returns list of article dicts. |
| `parse_date(date_str)` | Parses 10+ date formats: RFC 2822, ISO 8601, SEBI (`%d %b, %Y %z`), RBI (no timezone → assumes IST). |
| `should_filter_article(article)` | Delegates to `filters.py`. Returns `True` if article should be dropped. |
| `group_similar_articles(articles)` | Clusters similar headlines using `SequenceMatcher` (75% threshold), same-date only. Returns groups. |
| `generate_html(articles, videos, tweets, generated_at)` | Produces the entire `index.html` as a single f-string with inline CSS and JS. |
| `main()` | Orchestrates: fetch → split → dedup → filter → group → generate → write files. |

**Feed fetching details:**
- `ThreadPoolExecutor` with 10 workers, 15-second timeout per feed
- Custom `User-Agent` header to avoid 403 blocking
- Falls back to subprocess `curl` when `urllib` gets a 403
- SSL verification disabled for feeds with certificate issues

### generate_html() Structure Map

The entire frontend lives inside `generate_html()`. All CSS and JS are inlined — no external dependencies at runtime.

| Section | Approx. Lines | Contents |
|---------|--------------|----------|
| `<head>` + fonts | ~621–708 | Meta tags, Google Fonts (Merriweather, Source Sans Pro), early theme + filters-collapsed `<script>` |
| `<style>` (all CSS) | ~709–2072 | CSS variables, layout, cards, filters, filter-toggle, pagination, reports, dark mode, mobile media queries |
| Font-loading `<script>` | ~2073–2083 | FontFace API loader for Google Fonts |
| `<body>` + top bar | ~2084–2188 | Header, search input, top-bar icon buttons (AI/In Focus, Bookmarks, Theme) |
| News tab (`#tab-news`) | ~2190–2306 | `.filter-card` → `.stats-bar` (+ collapse chevron) → `.filter-row` (presets, publisher, category pills) → article cards → pagination |
| Telegram tab (`#tab-reports`) | ~2308–2336 | `.filter-card` → `.stats-bar` → `.filter-row` (PDF / Without PDF toggle, No stock targets) → reports container → pagination |
| YouTube tab (`#tab-youtube`) | after reports | `.filter-card` → `.stats-bar` → horizontal video cards (thumbnail + title + channel + date) → pagination |
| Twitter tab (`#tab-twitter`) | after youtube | `.filter-card` → `.stats-bar` → article cards → pagination |
| Footer + overlays | ~2339–2349 | Footer, back-to-top button, keyboard hint overlay |
| `<script>` (all JS) | ~2350–3600 | State management, rendering, filtering, pagination, bookmarks, keyboard nav, sidebars, tab persistence |

### Key CSS Patterns

- **Theming:** CSS variables in `:root` / `[data-theme="light"]` / `[data-theme="dark"]`. Red accent `#e14b4b`, warm charcoal dark mode `#0f1419`. `--danger` variable for destructive action buttons.
- **Typography:** Merriweather headings + Source Sans Pro body.
- **Tab layout:** Every tab uses the same `.filter-card` → `.stats-bar` (with `.stats` pills + `.update-time`) → `.filter-row` pattern.
- **Top bar buttons:** All 32×32 icon buttons with `data-tooltip` CSS tooltips (not native `title` attribute). "In Focus" (AI) button has a 10px pulse dot + count badge.
- **Filter pills:** `.preset-btn` (News filters) and `.reports-filter-btn` (Telegram filters) share the same pill shape (20px border-radius, 1.5px border). Active state toggled via `.active` class.
- **Mobile collapsible filters:** On ≤640px screens, `.filter-row` is hidden by default via `html.filters-collapsed` class (set by an early `<head>` script before render). A `.filter-toggle` chevron button in each `.stats-bar` toggles visibility. The chevron is hidden on desktop via CSS.
- **Tab persistence:** Active tab saved to `localStorage`; restored on load via an IIFE placed after `REPORTS_PAGE_SIZE` variable declaration.

### Telegram Tab Filters

The Telegram tab has a two-state segmented view toggle and a secondary filter:

| Control | ID | Default |
|---------|----|---------|
| PDF view (shows reports with PDFs) | `reports-pdf-btn` | Active (default on load) |
| Without PDF view | `reports-nopdf-btn` | Inactive |
| No stock targets (hides reports with UPSIDE/DOWNSIDE) | `reports-notarget-filter` | Enabled when PDF active, disabled when Without PDF active |

JS state: `reportsViewMode` (`'pdf'` or `'nopdf'`), `reportsNoTargetFilterActive` (bool).

### Client-Side State (localStorage)

All reads/writes go through the `safeStorage` helper (try/catch wrapper to handle private browsing restrictions).

| Key | Values | Purpose |
|-----|--------|---------|
| `theme` | `light` / `dark` | Theme preference |
| `financeradar_filters_collapsed` | `true` / `false` | Mobile filter row visibility (default: collapsed when `null`) |
| `financeradar_active_tab` | `news` / `reports` / `youtube` / `twitter` | Persisted active tab across sessions |
| `financeradar_page` | number | Last viewed pagination page |
| `financeradar_bookmarks` | JSON array | Saved article bookmarks |

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `J` / `↓` | Next article |
| `K` / `↑` | Previous article |
| `/` | Focus search input |
| `Esc` | Clear filters / close sidebar |

### Telegram Reports Rendering

The JS `applyReportsPagination()` function renders each report's `documents` array as individual `.report-doc-item` rows inside a `.report-doc-list` container. Falls back to the single `document` field for backward compatibility with older data.

---

## filters.py

Extracted from `aggregator.py` for easy independent editing. Contains:

- **`FILTER_TITLE_PATTERNS`** — 126 case-insensitive regex patterns. Categories: market price movements (Sensex/Nifty daily closes), commodity prices (gold/silver/petrol/diesel), forex rates, corporate actions (AGM, board meetings, dividend records), brokerage calls (Buy/Sell/Hold/Target), Q-results roundups, PF/salary clickbait, govt job/salary news, penny stocks, IPO GMP/subscription noise, event promos, video/podcast tags.
- **`FILTER_URL_PATTERNS`** — 24 URL substring patterns. Catches press releases (`/pr-release/`, `prnewswire.com`), non-news content (`/video/`, `/podcast/`, `/sports/`).
- **`COMPILED_TITLE_PATTERNS`** — Pre-compiled regex list (done once at import time).
- **`should_filter_article(article)`** — Returns `True` if the article's title matches any title pattern or its URL contains any URL pattern.

To add new filters: just add a regex string to `FILTER_TITLE_PATTERNS` or a substring to `FILTER_URL_PATTERNS`. No logic changes needed — the compile step and `should_filter_article()` handle everything automatically.

To test a filter:
```bash
python3 -c "from filters import should_filter_article; print(should_filter_article({'title': 'Sensex surges 300 points', 'link': ''}))"
```

---

## telegram_fetcher.py Internals

### Hybrid Architecture

Supports two fetch methods per channel, configured via the `"method"` field in `telegram_channels.json`:

**`"html"` method:**
- Scrapes `t.me/s/{username}` HTML (Telegram's public channel preview page)
- Uses `TelegramHTMLParser` — a `HTMLParser` subclass with state-machine flags to extract messages, documents, views, images, and dates
- Works only for public channels that serve preview HTML (not groups)

**`"mtproto"` method:**
- Uses the Telethon library to connect via Telegram's MTProto protocol
- Authenticates as the actual user account (not a bot)
- Can read full message history from private channels, restricted channels, and groups
- Requires `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION` environment variables

### Graceful Fallback

If Telethon is not installed or credentials are missing, MTProto channels are silently skipped with a warning added to the output. HTML channels still fetch normally. No crash.

### Output Schema

Both methods write to `static/telegram_reports.json` in identical format:

```json
{
  "generated_at": "2026-02-18T14:30:00+05:30",
  "warnings": [],
  "reports": [
    {
      "text": "Message text content",
      "date": "2026-02-18T12:00:00+05:30",
      "url": "https://t.me/Brokerage_report/12345",
      "channel": "Brokerage Reports",
      "documents": [
        {"title": "HDFC_Bank_Report.pdf", "size": "2.3 MB"}
      ],
      "document": {"title": "HDFC_Bank_Report.pdf", "size": "2.3 MB"},
      "views": "749",
      "images": ["https://cdn4.telesco.pe/file/..."]
    }
  ]
}
```

- `documents` — array of all attached files (primary field)
- `document` — first item from `documents` (backward-compatibility alias)
- `warnings` — empty on success; contains human-readable error strings on failure (session expired, channel returned 0 messages, etc.)
- The frontend reads `TELEGRAM_WARNINGS` and renders a red `.reports-warning` banner when non-empty
- MTProto-fetched messages have `images: []` — no CDN URLs available via API; frontend handles this gracefully

### Session Management

`generate_session.py` runs an interactive session to generate a Telethon `StringSession` (phone number → confirmation code). The resulting string is stored as the `TELEGRAM_SESSION` GitHub Actions secret. Sessions rarely expire; re-run `generate_session.py` if authentication fails.

---

## ai_ranker.py Internals

Reads `static/articles.json` (last 48 hours, max 200 articles), sends headlines to an OpenRouter LLM, and writes ranked results to `static/ai_rankings.json`.

**Ranking prompt (`RANKING_PROMPT`):** 6-tier editorial prioritization — explanatory journalism and policy analysis ranked highest; routine earnings reports and wire noise excluded. Headlines are sent with `[Source Name]` tags for source-aware ranking; tags are stripped when matching responses back to article objects. Picks exactly 20 articles with a diversity rule (no single source dominates).

**Model:** OpenRouter free-tier models. `MODELS` dict maps provider keys to OpenRouter model IDs (currently free-tier).

**Rate limiting:** 2-second delay between API calls.

**Output (`static/ai_rankings.json`):**
```json
{
  "generated_at": "2026-02-18T08:00:00+05:30",
  "rankings": [
    {
      "rank": 1,
      "title": "Article headline",
      "link": "https://...",
      "source": "Source Name",
      "date": "2026-02-18T..."
    }
  ]
}
```

The "In Focus" sidebar in the UI fetches this file and displays the top 20. The 🤖 button in the top bar opens the sidebar with a count badge and a pulse dot animation.

---

## UI Features

### Four Tabs
- **News** — All 96 news feeds. Filter by preset (Today, This Week), publisher, or free-text search.
- **Telegram** — Brokerage reports from 7 Telegram channels. View mode toggle: PDF (shows only reports with attached PDFs) or Without PDF. Secondary filter: "No stock targets" (hides reports mentioning UPSIDE/DOWNSIDE targets). Enabled only in PDF view.
- **YouTube** — Videos from 6 channels (Rachana Ranade, Akshat Shrivastava, Pranjal Kamra, Labour Law Advisor, Zerodha Varsity, Shankar Nath). Horizontal card layout with thumbnails.
- **Twitter** — Posts from Google News RSS feeds covering Nithin Kamath, Deepak Shenoy, nifty/sensex, and India economy keywords.

### Bookmarks
- Click the bookmark icon on any article card to save it
- Bookmarks button in top bar shows a count badge
- Slide-in sidebar to view all saved bookmarks
- **Copy All** — copies bookmarks as clean `Title\nURL` text
- **Clear All** — removes all bookmarks (with confirmation via `--danger` styled button)
- Persisted in `localStorage` across sessions

### In Focus (AI Rankings)
- 🤖 icon button in the top bar with pulse dot + count badge
- Slide-in sidebar showing the AI-ranked top 20 stories
- Each item is bookmarkable
- Data loaded from `static/ai_rankings.json` (generated daily)

### Search
- Real-time client-side filtering as you type
- Searches title, source name, and URL
- Works across all four tabs
- Press `/` to focus the search input from anywhere

### Other
- **Date grouping** — Articles grouped under Today, Yesterday, weekday names
- **Pagination** — 20 articles per page (News/Twitter), 15 per page (YouTube), configurable for Telegram
- **Theme toggle** — Light/dark mode, persisted in `localStorage`
- **Back to top** — Floating button appears after scrolling down
- **Relative timestamps** — "Updated 5 min ago", updates every 60 seconds
- **Mobile filters** — Filter row collapses by default on ≤640px; chevron button in stats bar expands it

---

## GitHub Actions & Deployment

### Workflows

| Workflow | File | Schedule | Steps |
|----------|------|----------|-------|
| Update FinanceRadar | `hourly.yml` | Every hour (`0 * * * *`) | `pip install telethon` → `telegram_fetcher.py` → `aggregator.py` → commit `index.html`, `articles.json`, `telegram_reports.json`, `youtube_cache.json` |
| AI News Ranking | `ai-ranking.yml` | Midnight UTC / ~5:30 AM IST (`0 0 * * *`) | `ai_ranker.py` → commit `ai_rankings.json` |

Both workflows validate that required secrets are set before running, fail fast if missing.

**GitHub Actions delay note:** Cron jobs typically run 1–2 hours late due to queue pressure. The AI ranking cron is set to midnight UTC (5:30 AM IST) to absorb delays and finish by ~8 AM IST.

### Required GitHub Secrets

| Secret | Used by | How to get |
|--------|---------|------------|
| `TELEGRAM_API_ID` | `hourly.yml` | [my.telegram.org](https://my.telegram.org) → API development tools |
| `TELEGRAM_API_HASH` | `hourly.yml` | Same as above |
| `TELEGRAM_SESSION` | `hourly.yml` | Run `python3 generate_session.py` once interactively |
| `OPENROUTER_API_KEY` | `ai-ranking.yml` | [openrouter.ai](https://openrouter.ai) → Keys |

### Cloudflare Pages Setup

1. Connect your GitHub repo to Cloudflare Pages
2. Build command: *(leave empty)*
3. Output directory: `/` (root — serves `index.html` directly)
4. Add custom domain (optional)

Cloudflare automatically picks up the `index.html` pushed by GitHub Actions each hour.

---

## Customization

### Add a News Feed

Add an entry to `feeds.json`:
```json
{
  "id": "unique-slug",
  "name": "Display Name",
  "url": "https://source-homepage.com",
  "feed": "https://source-homepage.com/rss",
  "category": "News"
}
```
Then run `python3 aggregator.py`.

### Add a YouTube Channel

Find the channel ID from the YouTube channel page source (search for `channel_id`), then add to `feeds.json`:
```json
{
  "id": "yt-channel-name",
  "name": "Channel Display Name",
  "url": "https://www.youtube.com/@channelhandle",
  "feed": "https://www.youtube.com/feeds/videos.xml?channel_id=UC_CHANNEL_ID_HERE",
  "category": "Videos"
}
```

### Add a Twitter/X Feed

Uses Google News RSS to search for `site:x.com` content:
```json
{
  "id": "twitter-username",
  "name": "@username on X",
  "url": "https://x.com/username",
  "feed": "https://news.google.com/rss/search?q=site:x.com/username&hl=en-IN&gl=IN&ceid=IN:en",
  "category": "Twitter"
}
```

### Add a Telegram Channel

Add to `telegram_channels.json`:
```json
{"username": "channel_username", "label": "Display Name", "method": "html"}
```
Use `"method": "mtproto"` for private channels (requires credentials).

### Adjust Content Filters

Edit `filters.py` — add a regex string to `FILTER_TITLE_PATTERNS` or a substring to `FILTER_URL_PATTERNS`. No other changes needed.

### Change Freshness Window

In `aggregator.py`, find:
```python
cutoff_date = now - timedelta(days=10)
```
Change `10` to the desired number of days.

### Styling

CSS variables in `generate_html()` inside `aggregator.py`:
```css
:root {
    --accent: #e14b4b;        /* Red accent */
    --bg-primary: #ffffff;
    --text-primary: #1f1f1f;
    --danger: #c0392b;        /* Destructive actions */
}
[data-theme="dark"] {
    --bg-primary: #0f1419;    /* Warm charcoal */
}
```

---

## Generated Files

These are written automatically — **do not hand-edit**.

| File | Written by | Contents |
|------|-----------|----------|
| `index.html` | `aggregator.py` | Full static site (~3 MB) with all news/video/twitter content embedded |
| `static/articles.json` | `aggregator.py` | Structured article data for AI ranker (last 48h) |
| `static/ai_rankings.json` | `ai_ranker.py` | AI-ranked top 20 stories |
| `static/telegram_reports.json` | `telegram_fetcher.py` | All scraped Telegram messages with document metadata |
| `static/youtube_cache.json` | `aggregator.py` | YouTube feed cache to avoid re-fetching thumbnails |
| `cron.log` | shell/cron | Execution output (gitignored) |

---

## Git Conventions

Generated files conflict constantly because GitHub Actions commits them every hour. When rebasing your feature branch onto `main`:

```bash
# Take the remote (auto-generated) version for all generated files
git checkout --theirs index.html static/articles.json static/telegram_reports.json static/youtube_cache.json
git add index.html static/articles.json static/telegram_reports.json static/youtube_cache.json
git rebase --continue

# Then regenerate fresh output from your updated source files
python3 telegram_fetcher.py
python3 aggregator.py
git add index.html static/articles.json static/telegram_reports.json static/youtube_cache.json
git commit -m "Regenerate after rebase"
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Feed shows `[FAIL]` in logs | URL temporarily down, or blocked. Check manually. Curl fallback already attempted. |
| Articles missing | Filtered by `filters.py` patterns, or older than 10 days, or per-feed 50-article cap |
| Wrong article dates | Check `parse_date()` — add new format if needed. RBI feeds omit timezone; IST is assumed. |
| 403 errors not resolved by curl | Some sites block all scrapers. Remove the feed or find an alternative URL. |
| Telegram: 0 reports from a channel | Channel may be a group (not a channel) — use `"mtproto"` method instead of `"html"` |
| Telegram: session expired | Re-run `python3 generate_session.py`, update `TELEGRAM_SESSION` secret in GitHub |
| AI rankings not updating | Check `OPENROUTER_API_KEY` secret is set; check `ai-ranking.yml` run logs in GitHub Actions |
| Bookmarks lost | Browser cleared `localStorage`, or different browser/device (no sync) |
| GitHub Actions running late | Normal — cron jobs queue and run 1–2 hours late. Not a bug. |

---

## Requirements

- Python 3.8+
- `telethon>=1.36` (`pip install -r requirements.txt`) — only needed for MTProto Telegram channels
- `curl` — for 403 fallback on Cloudflare-protected feeds
- Internet access

No other `pip install` required. The HTML output has no runtime dependencies.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3 (stdlib only, except Telethon) |
| Frontend | Vanilla HTML/CSS/JS (fully embedded in `index.html`) |
| Fonts | Merriweather (headings) + Source Sans Pro (body) via Google Fonts |
| Telegram API | Telethon (MTProto) + HTML scraping |
| AI Ranking | OpenRouter API (free-tier LLM) |
| Hosting | Cloudflare Pages |
| CI/CD | GitHub Actions |
| Deployment trigger | Git push (hourly auto-commit) |

---

Built by [Kashish Kapoor](https://kashishkapoor.com)
