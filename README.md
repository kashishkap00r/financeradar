# FinanceRadar

A lightweight, zero-dependency Python RSS/Atom aggregator that fetches finance-focused news and generates a single static HTML page. Built for Indian business and finance news, featuring bookmarks, category filtering, and a clean, keyboard-friendly UI.

**Live site**: [financeradar.kashishkapoor.com](https://financeradar.kashishkapoor.com)

## Features

- **70+ RSS/Atom feeds** from major financial publications
- **Category filtering** - News, Institutions, Ideas
- **Bookmarks** - Save articles with localStorage persistence
- **Search** - Real-time client-side filtering
- **Keyboard navigation** - J/K to navigate, / to search
- **Dark/Light mode** - Theme toggle with persistence
- **10-day freshness** - Only shows recent articles
- **Zero dependencies** - Standard library only
- **Static output** - Single HTML file, deploy anywhere

## Quick Start

```bash
# Generate the static site
python3 aggregator.py

# View locally
python3 -m http.server 8000
# Open http://localhost:8000
```

## Project Structure

```
financeradar/
├── aggregator.py                # Main script: fetch, parse, filter, render
├── feeds.json                   # Feed configuration with categories
├── index.html                   # Generated static site (output)
├── README.md                    # This file
├── .github/workflows/hourly.yml # GitHub Actions hourly refresh
└── cron.log                     # Execution log (optional)
```

## Categories

Feeds are organized into three categories:

| Category | Description | Examples |
|----------|-------------|----------|
| **News** | Mainstream financial media | ET, Mint, BusinessLine, BBC, CNBC, FT |
| **Institutions** | Central banks, regulators, development banks | RBI, SEBI, ECB, ADB, FRED |
| **Ideas** | Blogs, substacks, data journalism, independent voices | Our World in Data, Carbon Brief, Fundoo Professor |

## Feed Configuration

Each feed in `feeds.json` has:

```json
{
  "id": "et-bfsi-articles",
  "name": "ET BFSI — Articles",
  "url": "https://bfsi.economictimes.indiatimes.com",
  "feed": "https://bfsi.economictimes.indiatimes.com/rss/articles",
  "category": "News"
}
```

### Current Sources (70+)

**News**: Economic Times, ET Now, Mint, BusinessLine, The Hindu, BBC News, CNBC, The Guardian, The Economist, Financial Times India, Business Standard, Techmeme, and more.

**Institutions**: RBI, SEBI, ECB (Press, Blog, Working Papers, Publications), ADB (Features, Blogs, Publications), PIB India, FRED Blog.

**Ideas**: Our World in Data, Carbon Brief, Data For India, This Week In Data, Fundoo Professor, Musings on Markets, A Wealth of Common Sense, By the Numbers, Rest of World, India Dispatch, downtoearth.

## UI Features

### Bookmarks
- Click the bookmark icon on any article to save it
- Access bookmarks via the header button (shows count badge)
- Slide-in sidebar panel to view all bookmarks
- **Copy All** - Copies bookmarks as clean text (title + URL)
- **Clear All** - Remove all bookmarks
- Persisted in `localStorage` across sessions

### Category Tabs
- Filter articles by category: `[All] [News] [Institutions] [Ideas]`
- Located below the stats bar
- Combines with search for refined filtering

### Keyboard Shortcuts
| Key | Action |
|-----|--------|
| `J` / `↓` | Next article |
| `K` / `↑` | Previous article |
| `/` | Focus search |
| `Esc` | Clear filters / close sidebar |

### Other Features
- **Date grouping** - Today, Yesterday, weekday names
- **Pagination** - 20 articles per page
- **Theme toggle** - Light/dark mode (persisted)
- **Back to top** - Floating button after scrolling

## How It Works

### 1. Parallel Fetching
- 10 concurrent workers fetch all feeds
- Custom User-Agent to avoid blocking
- Curl fallback for Cloudflare-protected sites (e.g., Carbon Brief)
- 15-second timeout per feed

### 2. Date Parsing
Handles multiple date formats:
- RFC 2822: `Mon, 02 Feb 2026 10:30:00 +0530`
- ISO 8601: `2026-02-02T10:30:00Z`
- SEBI format: `02 Feb, 2026 +0530`
- RBI format (no timezone, assumes IST)

### 3. Content Filtering

**10-day freshness**: Articles older than 10 days are automatically removed.

**Title patterns filtered** (100+ regex rules):
- Market movements: "Sensex closes at", "Nifty rises"
- Price updates: "Gold price today", "Petrol rate"
- Routine: "Money market operations", "Treasury bills auction"
- IPO noise: "IPO GMP", "subscription status"
- Stock tips: "Buy or sell", "Multibagger stocks"

**URL patterns filtered**:
- Press releases: `/pr-release/`, `prnewswire.com`
- Non-news: `/video/`, `/podcast/`, `/sports/`

### 4. Deduplication
URLs are normalized before comparison:
- Lowercased
- Trailing slash removed
- `http://` → `https://`

### 5. HTML Generation
Single static file with embedded CSS and JS:
- No external dependencies at runtime
- Works offline after loading
- ~1-2 MB depending on article count

## Deployment

### GitHub Actions (Recommended)
The included workflow runs hourly:
```yaml
# .github/workflows/hourly.yml
on:
  schedule:
    - cron: '0 * * * *'  # Every hour
```

### Cloudflare Pages
1. Connect GitHub repo to Cloudflare Pages
2. Build command: *leave empty*
3. Output directory: `/` (root)
4. Add custom domain

### Local Cron
```cron
0 * * * * /usr/bin/python3 /path/to/aggregator.py >> /path/to/cron.log 2>&1
```

## Customization

### Add a Feed
Edit `feeds.json`:
```json
{
  "id": "new-feed-id",
  "name": "Display Name",
  "url": "https://source-homepage.com",
  "feed": "https://source-homepage.com/rss",
  "category": "News"
}
```

### Adjust Filters
In `aggregator.py`, modify:
- `FILTER_TITLE_PATTERNS` - Regex patterns for titles
- `FILTER_URL_PATTERNS` - Substring matches for URLs

### Change Freshness Window
In `aggregator.py`, find:
```python
cutoff_date = now - timedelta(days=10)
```
Change `10` to desired number of days.

### Styling
CSS variables in `generate_html()`:
```css
:root {
    --bg-primary: #ffffff;
    --accent: #e14b4b;
    --text-primary: #1f1f1f;
    /* ... */
}
```

## Requirements

- Python 3.8+
- `curl` (for Cloudflare-protected feeds)
- Internet access

No `pip install` required.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Feed shows `[FAIL]` | Check if URL is accessible, may be temporarily down |
| Missing articles | May be filtered by title/URL patterns or >10 days old |
| SEBI dates wrong | Fixed in current version with custom date format |
| 403 errors | Curl fallback handles most cases automatically |
| Bookmarks lost | Cleared browser localStorage or different browser |

## Processing Pipeline

```
70+ Feeds
    ↓ Parallel fetch (10 workers)
~3,500 raw articles
    ↓ URL deduplication
~3,200 unique articles
    ↓ Content filtering (regex)
~3,100 relevant articles
    ↓ 10-day freshness filter
~1,300 recent articles
    ↓ Per-feed cap (50 max)
~1,200 final articles
    ↓ HTML generation
index.html (1-2 MB)
```

## Tech Stack

- **Backend**: Python 3 (stdlib only)
- **Frontend**: Vanilla HTML/CSS/JS (embedded)
- **Font**: IBM Plex Mono (Google Fonts)
- **Hosting**: GitHub Pages / Cloudflare Pages
- **CI/CD**: GitHub Actions

## License

MIT License - see LICENSE file.

---

Built by [Kashish Kapoor](https://kashishkapoor.com) for [The Daily Brief by Zerodha](https://thedailybrief.zerodha.com/)
