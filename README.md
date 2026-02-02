# FinanceRadar

A lightweight Python RSS/Atom aggregator that fetches finance‑focused news and builds a single static HTML page (`index.html`). The output is a fast, no‑backend website with search, source filtering, pagination, date grouping, and keyboard navigation. A vibecoded tool that aggregates and cleans news from most major Indian business and finance publications.

## What This Project Does

- Fetches dozens of RSS/Atom feeds in parallel.
- Normalizes and sorts articles by published time.
- Removes duplicate links and filters routine/low‑value items with regex rules.
- Generates a static website (`index.html`) with a clean UI and client‑side search/filtering.

## Project Structure

```
financeradar/
├── aggregator.py               # Main script: fetch, parse, filter, render HTML
├── feeds.json                  # Feed configuration list
├── index.html                  # Generated static site (output)
├── .github/workflows/hourly.yml# GitHub Actions hourly refresh
├── .gitignore                  # Ignore runtime files
└── cron.log                    # Example run log (optional)
```

## Requirements

- Python 3.8+ (standard library only)
- Internet access for RSS/Atom endpoints

No external dependencies are required.

## Quick Start

From the project directory:

```bash
python3 aggregator.py
```

This will:

1. Load `feeds.json`
2. Fetch all feeds in parallel
3. Filter + dedupe articles
4. Write `index.html`

Open `index.html` in any browser to view the aggregated feed.

## How It Works

### 1) Feed Configuration (`feeds.json`)
Each feed entry contains:

- `id`: unique identifier
- `name`: human‑readable name (displayed in UI)
- `url`: source homepage
- `feed`: RSS/Atom feed URL

Example:

```json
{
  "id": "cnbc-economy",
  "name": "Economy",
  "url": "https://www.cnbc.com/economy/",
  "feed": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"
}
```

### 2) Fetching & Parsing
`fetch_feed()`:

- Uses `urllib.request` with a desktop User‑Agent.
- Uses a permissive SSL context for feeds with certificate issues.
- Parses **RSS 2.0** (`<item>`) and **Atom** (`<entry>`).

### 3) Date Parsing & Sorting
`parse_date()` tries multiple common date formats and normalizes timezones.

Articles are sorted by timestamp (newest first). Items without dates are placed last.

### 4) Deduplication
Duplicates are removed based on normalized URL only (within each run):

- Lowercased
- Trimmed
- Trailing slash removed
- `http://` converted to `https://`

### 5) Content Filtering
`should_filter_article()` removes routine/low‑value items based on:

- Title regex patterns (market closing ticks, price updates, IPO GMP, etc.)
- URL substring matches (press‑release / PR wires)

Patterns live in:

- `FILTER_TITLE_PATTERNS`
- `FILTER_URL_PATTERNS`

### 6) HTML Generation
`generate_html()` builds a single static file with:

- Sticky header with search + source filter
- Date headers (Today / Yesterday / weekday)
- Keyboard navigation (J/K, /, Esc)
- Theme toggle (light/dark) persisted in localStorage
- Back‑to‑top button

Everything is embedded (CSS + JS) for zero‑dependency deployment.

## Output UI Features

- **Search**: client‑side filter across visible articles
- **Source filter**: dropdown filter by feed name
- **Date grouping**: grouped by publication day
- **Keyboard shortcuts**:
  - `J` / `K` or arrow keys: jump between articles
  - `/`: focus search
  - `Esc`: clear filters / blur input
- **Theme toggle**: stored in `localStorage`

## Running on a Schedule

This project works well with cron. Example (every hour):

```cron
0 * * * * /usr/bin/python3 /home/kashish.kapoor/financeradar/aggregator.py >> /home/kashish.kapoor/financeradar/cron.log 2>&1
```

The script appends a summary to `cron.log` after each run.

## GitHub + Cloudflare Pages (No Git Required)

If you cannot install git locally, you can still deploy using the GitHub website:

1) Create a new GitHub repository (e.g., `financeradar`).
2) Click **“Add file → Upload files”** and drag the entire `financeradar/` folder contents.
3) Make sure `.github/workflows/hourly.yml` is included so hourly updates run.
4) Commit the upload.

Then connect the repo to **Cloudflare Pages**:

- Build command: **leave empty**
- Output directory: **/** (root)

Add the custom domain `financeradar.kashishkapoor.com` in Cloudflare Pages → Custom domains.

## Notes

- `index.html` is generated. Don’t edit it manually—run `aggregator.py`.
- GitHub Actions runs hourly and commits the new `index.html`.

## Customization Guide

### Add or Remove Feeds
Edit `feeds.json` and add/remove objects. Keep `id` unique.

### Adjust Filters
Edit `FILTER_TITLE_PATTERNS` and `FILTER_URL_PATTERNS` in `aggregator.py`.

### Change the Look & Feel
The HTML, CSS, and JS are embedded in `generate_html()` inside `aggregator.py`.

- Color scheme: CSS variables under `:root`
- Fonts: Google Fonts import in `<style>`
- Layout: `.top-bar`, `.container`, `.article` styles

## Design Notes & Tradeoffs

- **No external dependencies**: runs on any stock Python install.
- **Static output**: simple to host anywhere (GitHub Pages, S3, Nginx).
- **Fast client UX**: filtering and search are client‑side.
- **Best effort date parsing**: mixed timezones can exist across sources; timestamps are normalized before sorting.
- **Permissive SSL**: avoids failures from misconfigured feeds, but is less strict for security.

## Common Issues

- Some feeds may temporarily fail or return invalid XML. These are logged and skipped.
- If a feed has no `<pubDate>` / `<published>`, it will appear last.
- Title filters may remove articles you care about; adjust patterns as needed.

## Development Tips

- Start with a small subset of feeds to test formatting.
- Keep an eye on `cron.log` for failures.
- If duplicates still appear, improve URL normalization or add per‑site rules.

## License

Not specified. Add a license if you plan to redistribute.
