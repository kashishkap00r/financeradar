# Session 5: Resilience Architecture & Production Plan
**Date:** 2026-03-16

## Decision: RSSHub on Vercel (Recommended)

### Options Evaluated

| Option | Setup | Maintenance | Reliability | Cost |
|--------|-------|-------------|-------------|------|
| **A. Vercel-hosted RSSHub** | One-click deploy | Low (token rotation only) | High (Vercel uptime) | Free |
| B. GitHub Actions inline | Complex workflow changes | Medium | Medium (cold start) | Free |
| C. Direct Twitter API in Python | Heavy Python work | Very high (API changes) | Low | Free |
| D. Keep Google RSS only | Zero changes | None | Current (lossy) | Free |

**Winner: Option A** — Vercel-hosted RSSHub with Google RSS fallback.

### Why Vercel
- One-click deploy from RSSHub's GitHub repo
- Free tier: 100GB bandwidth, serverless functions — more than enough for 49 feeds/hour
- Auth token stored as Vercel environment variable
- No changes to GitHub Actions workflow (just URL swaps)
- Always-on (no cold start for RSS feeds — Vercel caches at edge)

---

## Architecture Overview

```
                    ┌─────────────────────┐
                    │   GitHub Actions     │
                    │   (hourly cron)      │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  twitter_fetcher.py  │
                    │  (modified)          │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Fallback Chain     │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼─────────┐ ┌───▼──────────┐ ┌───▼────────┐
    │  RSSHub (Vercel)   │ │ Google RSS   │ │   Cache    │
    │  PRIMARY           │ │ FALLBACK     │ │ LAST RESORT│
    │                    │ │              │ │            │
    │ • Direct x.com     │ │ • Redirect   │ │ • Stale    │
    │   links            │ │   URLs       │ │   warning  │
    │ • Rich content     │ │ • Plain text │ │ • Last-    │
    │ • Real-time        │ │ • 6hr+ lag   │ │   known-   │
    │ • Auth token       │ │ • No auth    │ │   good     │
    └────────────────────┘ └──────────────┘ └────────────┘
```

---

## Fallback Chain Logic

```python
def fetch_handle(handle, rsshub_base, google_url, cache):
    """
    Priority 1: RSSHub (Vercel) — freshest, richest content
    Priority 2: Google RSS — zero-auth fallback
    Priority 3: Cache — last-known-good data
    """

    # 1. Try RSSHub
    items = fetch_rsshub(rsshub_base, handle)
    if items and len(items) > 0:
        cache.update(handle, items)
        return items, "rsshub"

    # 2. RSSHub failed or rate-limited (0 items) — try Google
    items = fetch_google_rss(google_url)
    if items and len(items) > 0:
        # Google items need URL resolution
        items = resolve_google_urls(items)
        cache.update(handle, items)
        return items, "google"

    # 3. Both failed — serve cache
    cached = cache.get(handle)
    if cached:
        return cached, "cache"

    return [], "empty"
```

### Rate Limit Detection

```python
def fetch_rsshub(base, handle):
    resp = requests.get(f"{base}/twitter/user/{handle}", timeout=60)
    if resp.status_code != 200:
        return None

    items = parse_rss(resp.text)

    # Stealthy rate limit: 200 + valid XML + 0 items
    if len(items) == 0:
        return None  # Trigger fallback

    return items
```

---

## feeds.json Migration

### Before (current)
```json
{
  "id": "x-deepak-shenoy",
  "name": "Deepak Shenoy (X)",
  "url": "https://x.com/deepakshenoy",
  "feed": "https://news.google.com/rss/search?q=site:x.com/deepakshenoy/status&hl=en-IN&gl=IN&ceid=IN:en",
  "category": "Twitter",
  "publisher": "Deepak Shenoy"
}
```

### After (with fallback)
```json
{
  "id": "x-deepak-shenoy",
  "name": "Deepak Shenoy (X)",
  "url": "https://x.com/deepakshenoy",
  "feed": "https://your-rsshub.vercel.app/twitter/user/deepakshenoy",
  "feed_fallback": "https://news.google.com/rss/search?q=site:x.com/deepakshenoy/status&hl=en-IN&gl=IN&ceid=IN:en",
  "category": "Twitter",
  "publisher": "Deepak Shenoy"
}
```

The `feed_fallback` field is new. Only Twitter feeds need it. The fetcher tries `feed` first, then `feed_fallback`, then cache.

---

## twitter_fetcher.py Changes

### What Changes
1. **Primary fetch:** Use RSSHub RSS feed (standard RSS XML — same as Google, just different URL)
2. **Fallback fetch:** Keep existing Google RSS logic as fallback
3. **URL resolution:** Skip for RSSHub items (already have direct x.com links); keep for Google fallback
4. **Rate limit detection:** Check item count, not just HTTP status
5. **Source tracking:** Log which source served each handle (rsshub/google/cache)

### What Stays the Same
- `normalize_and_filter_tweets()` — works with any RSS items
- `clean_twitter_title()` — still needed
- `save_twitter_snapshot()` / `load_twitter_snapshot()` — cache mechanism unchanged
- `build_twitter_lanes()` in twitter_signal.py — unchanged
- All downstream processing in aggregator.py — unchanged

### What Gets Removed/Simplified
- `resolve_google_twitter_urls()` — not needed for RSSHub items (still needed for Google fallback)
- `TWITTER_RESOLVE_WORKERS` config — can be reduced or removed
- `twitter_url_cache.json` — becomes fallback-only (shrinks over time)

### Estimated Diff Size
~80 lines changed in twitter_fetcher.py, ~5 lines in config.py, 49 URL swaps in feeds.json.

---

## Vercel Deployment Steps

### One-Time Setup (~10 minutes)
1. Go to github.com/DIYgod/RSSHub
2. Click "Deploy to Vercel" button (in README)
3. Sign in with GitHub account
4. During setup, add environment variable:
   - Key: `TWITTER_AUTH_TOKEN`
   - Value: `<your auth_token cookie>`
5. Deploy — get URL like `https://financeradar-rsshub.vercel.app`
6. Test: `https://financeradar-rsshub.vercel.app/twitter/user/deepakshenoy`

### GitHub Secrets
Add to financeradar repo secrets:
- `RSSHUB_BASE_URL`: `https://financeradar-rsshub.vercel.app`

### Token Rotation
When Twitter auth_token expires:
1. Log into X → DevTools → Cookies → copy new `auth_token`
2. Go to Vercel dashboard → Environment Variables → update `TWITTER_AUTH_TOKEN`
3. Redeploy (or wait for next cold start)

---

## Monitoring & Alerting

### Source Tracking
Add to `twitter_clean_cache.json` metadata:
```json
{
  "meta": {
    "generated": "2026-03-16T...",
    "source_mode": "rsshub+fallback",
    "sources": {
      "rsshub": 42,
      "google": 3,
      "cache": 4
    },
    "rate_limited": false
  }
}
```

### Alert Conditions
| Condition | Severity | Action |
|-----------|----------|--------|
| RSSHub returns 0 items for >10 handles | Warning | Google fallback active |
| ALL RSSHub requests return 0 items | Critical | Token likely expired |
| Google fallback also fails | Critical | Serving stale cache |
| Cache age > 24 hours | Warning | All sources broken |

### How to Alert
- GitHub Actions logs already visible in workflow runs
- Add a summary step that prints source distribution
- Optional: Telegram bot notification if critical (reuse existing Telegram infrastructure)

---

## Caching Strategy

| Scenario | Behavior |
|----------|----------|
| RSSHub succeeds | Update cache, serve fresh |
| RSSHub fails, Google succeeds | Update cache, serve Google data |
| Both fail | Serve cache (mark as stale) |
| Cache age < 6 hours | Acceptable staleness |
| Cache age 6-24 hours | Warning in logs |
| Cache age > 24 hours | Critical alert |
| Cache format | Same as current `twitter_clean_cache.json` |

---

## Token Management

| Aspect | Approach |
|--------|----------|
| Storage | Vercel env var (primary), GitHub Secret (backup reference) |
| Rotation | Manual: copy new cookie → update Vercel env var |
| Expected lifetime | TBD (soak test ongoing — typically 30-90 days for Twitter cookies) |
| Expiry detection | All RSSHub handles return 0 items + long timeouts |
| Multi-token | TWITTER_AUTH_TOKEN supports comma-separated list (load balancing) |
| Automation | Not possible (cookie requires browser login) |

---

## Migration Sequence

### Phase 1: Vercel Deploy (no code changes)
1. Deploy RSSHub to Vercel with auth_token
2. Verify all 49 handles work via browser
3. Confirm rate limits are acceptable

### Phase 2: Code Changes
1. Add `feed_fallback` field to feeds.json (49 entries)
2. Modify `twitter_fetcher.py` with fallback chain
3. Update `config.py` with RSSHUB_BASE_URL
4. Add source tracking to cache metadata
5. Test locally: `python3 aggregator.py`

### Phase 3: Workflow Update
1. Add `RSSHUB_BASE_URL` to GitHub Secrets
2. Pass it as env var in hourly.yml
3. Deploy, monitor first few hourly runs
4. Verify source distribution in logs

### Phase 4: Cleanup (optional, after 1 week)
1. Remove URL resolution code if Google fallback rarely triggers
2. Reduce/remove `twitter_url_cache.json` tracking
3. Update AGENTS.md / CLAUDE.md documentation

---

## Results Matrix (Session 6)

| Method | Coverage | Freshness | Reliability | Auth Burden | Maintenance |
|--------|----------|-----------|-------------|-------------|-------------|
| **RSSHub (Vercel)** | 92% (45/49) | **Minutes** | High (Vercel) | Cookie rotation | Low |
| Google RSS (fallback) | ~20% recent | 4-53 hours | Very high | None | None |
| Cache | 100% (last known) | Stale | 100% | None | None |
| **Combined** | **~95%+** | **Minutes** | **Very high** | Cookie rotation | **Low** |

---

## What We're NOT Doing

| Temptation | Why skip |
|------------|----------|
| Twitter API ($5K/month) | Cost prohibitive |
| Nitter self-hosting | All instances dead, complex setup |
| LinkedIn feeds | Unsolved in open source, defer |
| Direct Twitter scraping | Breaks every 2-4 weeks |
| Tab rename to "Social" | No LinkedIn = no need for rename |
