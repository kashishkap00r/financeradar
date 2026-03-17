---
name: new-scraper
description: Add a new institutional report scraper to FinanceRadar's Reports tab
---

# Add New Report Scraper

Follow this exact process when adding a new scraper to `reports_fetcher.py`.

## Step 1: Probe the Target URL

Before writing any code, test the URL with curl to check for WAF/Cloudflare blocks:

```bash
curl -sS -o /dev/null -w "%{http_code}" -H "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36" "TARGET_URL"
```

- **200**: Proceed with HTML scraping via `_fetch_url()`
- **403/503 with Cloudflare challenge**: Use Google News RSS proxy pattern in feeds.json instead: `https://news.google.com/rss/search?q=site:domain.com/path&hl=en-IN&gl=IN&ceid=IN:en`
- **403 Akamai/other WAF**: Try adding `Accept`, `Accept-Language` headers. If still blocked, use the cache-based pattern (local Playwright scrape → JSON cache → pipeline reads cache)

Save a sample of the HTML to understand the page structure before writing selectors.

## Step 2: Write the Scraper Function

Add to `reports_fetcher.py` following this exact pattern:

```python
# ── SOURCE NAME ──────────────────────────────────────────────────────

@scraper
def fetch_source_name(feed_config):
    """Fetch reports from Source Name."""
    articles = []
    content = _fetch_url(feed_config["url"]).decode("utf-8", errors="replace")

    # Parse articles using regex on HTML (not BeautifulSoup — not in deps)
    # Use _strip_html() to clean extracted text
    # Use _make_article(title, link, date, description, feed_config) to build items

    return articles
```

Key rules:
- **Use `_fetch_url()`** — it handles urllib + curl fallback + retries + timeouts
- **Use `_make_article()`** — it builds the standard article dict with all required fields
- **Use `_strip_html()`** — strips HTML tags from extracted text
- **Use `_is_fresh(dt)`** — check freshness (30 days) if you filter manually
- **Parse with regex, not BeautifulSoup** — BS4 is not in requirements.txt. Use `re.findall()` on HTML
- **Date parsing**: Use `datetime.strptime()` with explicit format, always set `tzinfo=timezone.utc`
- The `@scraper` decorator already handles: error catching, freshness filtering, article limit (30), logging

## Step 3: Register in REPORT_FETCHERS

Add the mapping near line 1223 in `reports_fetcher.py`:

```python
REPORT_FETCHERS = {
    # ... existing entries ...
    "newsource:": fetch_source_name,
}
```

The prefix (e.g., `"newsource:"`) must match the feed IDs in feeds.json.

## Step 4: Add Feeds to feeds.json

```json
{
    "id": "newsource-section",
    "name": "Source Name — Section",
    "url": "https://source.com/research",
    "feed": "newsource:newsource-section",
    "category": "Reports",
    "publisher": "Source Name",
    "region": "Indian"
}
```

Rules:
- `id`: lowercase-hyphenated, unique
- `feed`: starts with the prefix registered in `REPORT_FETCHERS`
- `category`: must be `"Reports"`
- `region`: `"Indian"` or `"International"`
- `publisher`: groups multiple feeds under one filter in the UI

## Step 5: Test

```bash
# Run the scraper standalone
python3 -c "
from reports_fetcher import *
import json
cfg = {'id': 'newsource-test', 'name': 'Test', 'url': 'https://source.com/research', 'category': 'Reports', 'publisher': 'Source Name', 'region': 'Indian'}
results = fetch_source_name(cfg)
print(json.dumps(results, indent=2, default=str))
print(f'Total: {len(results)} articles')
"

# Must return ≥ 5 articles with title, link, date, source fields
# Then run existing tests to check nothing is broken
python3 -m unittest discover -s tests
```

## Step 6: Verify in Full Pipeline

```bash
python3 aggregator.py
# Check that Reports tab count increased
# Check static/reports_cache.json contains new source
```

## Step 7: Commit

```bash
git add reports_fetcher.py feeds.json
git commit -m "feat: add {Source Name} scraper for Reports tab"
```

## Common Patterns from Existing Scrapers

**JSON API** (like CareRatings):
```python
data = json.loads(_fetch_url(url, accept="application/json"))
for item in data["results"]:
    articles.append(_make_article(item["title"], item["url"], parse_date(item["date"]), "", feed_config))
```

**HTML with regex** (like SBI, CRISIL):
```python
content = _fetch_url(url).decode("utf-8", errors="replace")
for match in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', content, re.DOTALL):
    link, title_html = match.groups()
    title = _strip_html(title_html).strip()
    articles.append(_make_article(title, link, None, "", feed_config))
```

**Cache-based** (like PIIE — for Cloudflare-blocked sites):
```python
@scraper
def fetch_source_cache(feed_config):
    path = os.path.join(os.path.dirname(__file__), "static", "source_cache.json")
    data = json.load(open(path))
    # Filter by feed_id, convert dates, return articles
```

## Timeout/Retry Overrides

If the source is slow or flaky, add overrides in `config.py`:

```python
SCRAPER_TIMEOUT_OVERRIDES = {
    "newsource-section": 8,  # seconds (default is 5)
}
SCRAPER_RETRY_OVERRIDES = {
    "newsource-section": 3,  # attempts (default is 2)
}
```
