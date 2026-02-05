# FinanceRadar - Session Notes

## Session: Feb 5, 2026 (Latest)

### 1. AI-Powered News Ranking Sidebar
- **New file: `ai_ranker.py`** - Calls OpenRouter API (Nemotron model) to rank top 20 stories
- Analyzes headlines from last 48 hours
- Ranks by: market impact, policy significance, corporate news, economic indicators, global events
- Outputs to `static/ai_rankings.json`

### 2. AI Sidebar UI
- 🤖 button in header (next to bookmarks)
- Slide-in sidebar showing AI-ranked top 20 articles
- Provider dropdown (currently OpenRouter only, expandable)
- Bookmark button on each AI-ranked item
- Shows ranking reason for each article

### 3. GitHub Actions Workflows
- **`hourly.yml`** - Runs every hour
  - Fetches RSS feeds via `aggregator.py`
  - Generates `index.html` + `static/articles.json`
  - Auto-commits and pushes

- **`ai-ranking.yml`** - Runs daily at 7:30 AM IST (2:00 AM UTC)
  - Runs `ai_ranker.py` with `OPENROUTER_API_KEY` secret
  - Generates `static/ai_rankings.json`
  - Auto-commits and pushes

### 4. Relative Time Display
- Changed "Updated Feb 05, 09:44 PM IST" to "Updated X min ago"
- Shows: "just now", "5 min ago", "2 hr ago", "1 day ago"
- Updates every 60 seconds

### 5. Favicon Fix
- Renamed `static/favikon.svg` → `static/favicon.svg`
- Changed emoji from 🤓 to 📰

### 6. New Feed Added
- ThePrint Economy (`https://theprint.in/category/economy/feed/`)

### 7. Articles Export
- `aggregator.py` now exports `static/articles.json`
- Used by `ai_ranker.py` for AI analysis

---

## Files Created/Modified

| File | Status | Purpose |
|------|--------|---------|
| `ai_ranker.py` | **NEW** | AI ranking script using OpenRouter |
| `static/ai_rankings.json` | **GENERATED** | Cached AI rankings |
| `static/articles.json` | **GENERATED** | Article data for AI ranker |
| `static/favicon.svg` | **RENAMED** | Site favicon (📰) |
| `.github/workflows/ai-ranking.yml` | **NEW** | Daily AI ranking workflow |
| `.github/workflows/hourly.yml` | **MODIFIED** | Added articles.json export |
| `aggregator.py` | **MODIFIED** | AI sidebar UI, articles export, relative time |
| `feeds.json` | **MODIFIED** | Added ThePrint Economy |

---

## API Keys & Secrets

### OpenRouter (Currently Active)
- **Model:** `nvidia/nemotron-nano-9b-v2:free`
- **Cost:** Free
- **GitHub Secret:** `OPENROUTER_API_KEY`

### Other Providers (Not Active - Had Issues)
- **Gemini:** 404 errors (API not enabled properly)
- **OpenAI:** 429 rate limits (separate from ChatGPT Plus subscription)
- **Claude/Anthropic:** Not configured (API key not provided)

---

## How to Run Locally

```bash
cd /home/kashish.kapoor/financeradar

# Generate index.html + articles.json
python3 aggregator.py

# Generate AI rankings (requires API key)
OPENROUTER_API_KEY="sk-or-v1-..." python3 ai_ranker.py

# Start local server
python3 -m http.server 8000
# Open http://localhost:8000
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Hourly (GitHub Actions)                                        │
│  └─ aggregator.py → index.html + articles.json                  │
├─────────────────────────────────────────────────────────────────┤
│  Daily 7:30 AM IST (GitHub Actions)                             │
│  └─ ai_ranker.py → ai_rankings.json                             │
├─────────────────────────────────────────────────────────────────┤
│  Browser                                                        │
│  └─ index.html loads ai_rankings.json for sidebar               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Previous Session: Feb 3, 2026

### 1. Bookmarks Feature
- Bookmark icon on each article (click to save)
- Header button with count badge
- Slide-in sidebar panel to view bookmarks
- **Copy All** button - copies as clean text (title + URL)
- **Clear All** button with confirmation
- Persisted in localStorage (`financeradar_bookmarks`)

### 2. Category System
- Removed source dropdown
- Added 3 category tabs: `[All] [News] [Institutions] [Ideas]`
- Each feed in `feeds.json` has a `"category"` field
- **News**: Mainstream media (ET, Mint, BBC, Reuters, FT, etc.)
- **Institutions**: RBI, SEBI, ECB, ADB, PIB, FRED
- **Ideas**: Blogs, substacks, data journalism

### 3. Content Filtering
- **10-day freshness filter** - articles older than 10 days removed

### 4. Bug Fixes
- **SEBI date format** - added `%d %b, %Y %z` to `parse_date()`
- **Scroll behavior** - page starts at top, pagination goes to absolute top
- **Bookmark JS fix** - escaped newlines properly for template literals

### 5. New Feeds Added (via Google News RSS workaround)
- Financial Times — India
- Carbon Brief (with curl fallback for Cloudflare)
- Business Standard — India, Industry, Economy
- Reuters — India

### 6. Technical Improvements
- **Curl fallback** for 403 errors (Cloudflare-protected sites)
- Updated User-Agent headers

---

## Current Stats
- **81+ feeds** total
- **~1500 articles** after filtering
- **3 categories**: News, Institutions, Ideas
- **1 AI provider**: OpenRouter (Nemotron)

---

## Key Files for Context

```
/home/kashish.kapoor/financeradar/
├── aggregator.py          # Main RSS aggregator + HTML generator
├── ai_ranker.py           # AI ranking script
├── feeds.json             # Feed configurations
├── index.html             # Generated static site
├── static/
│   ├── articles.json      # Exported articles for AI
│   ├── ai_rankings.json   # AI rankings cache
│   └── favicon.svg        # Site icon (📰)
└── .github/workflows/
    ├── hourly.yml         # Hourly RSS fetch
    └── ai-ranking.yml     # Daily AI ranking
```

---

## How to Resume
Tell Claude: "Let's continue working on FinanceRadar" and reference this file.
