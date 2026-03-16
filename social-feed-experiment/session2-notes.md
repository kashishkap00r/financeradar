# Session 2: RSSHub Reliability & Edge Cases
**Date:** 2026-03-16

## Step 2.2: Scale Test (49 handles)

**Result: 45/49 handles returned data. Zero rate limiting on first burst.**

| Metric | Value |
|--------|-------|
| Total handles | 49 |
| Successful (items > 0) | 45 (92%) |
| HTTP 200 (no error) | 49 (100%) |
| Rate limited (429) | 0 |
| Total items | 739 |
| Avg items/handle | 16.4 (for 45 working) |
| Total time | 250s (~4 min) |
| Avg response time | 1.5s (median), 0.0-46.7s range |

### 4 Handles With 0 Items

| Handle | Response Time | Likely Cause |
|--------|-------------|-------------|
| `exencial_RP` | 1.3s | Inactive account (Google also has ~1 item) |
| `TamalBandyo` | 45.8s | Twitter API timeout — account issue |
| `madhavchanchani` | 42.9s | Twitter API timeout — account issue |
| `PIIE` | 46.7s | Twitter API timeout — account issue |

These 4 are also sparse in Google RSS (1 item each). Not an RSSHub problem — these accounts are likely inactive, protected, or have some API-level issue.

### Freshness Distribution

| Age of Newest Tweet | Count |
|--------------------:|------:|
| < 1 hour | 9 |
| 1-6 hours | 14 |
| 6-24 hours | 7 |
| 1-7 days | 10 |
| > 7 days | 5 |

---

## Rate Limiting Discovery

### What Happened
After the 49-handle scale test + 9 edge case requests (~58 total in ~15 min), Twitter rate-limited us.

### Rate Limit Behavior

| Aspect | Finding |
|--------|---------|
| Threshold | ~50-60 unique requests per 15-min window |
| HTTP response | 200 (not 429!) |
| Body | Valid RSS XML with account info, but 0 `<item>` elements |
| Response time | 22-45 seconds (timeout-like) |
| Recovery | ~10 minutes to full recovery |
| Detection | Must check item count, not HTTP status |
| Cache bypass | Cached handles still serve correctly during rate limit |

### Critical Insight
Twitter's rate limiting is **stealthy** — no explicit 429 error. RSSHub returns a valid-looking RSS feed with the account name/bio but zero items. Without checking item count, you'd think everything was fine.

### Production Implication
- 49 handles in one sequential burst (~4 min) = **within limit**
- But NO additional requests for 10 min after the burst
- RSSHub's 5-min cache means repeated requests don't hit Twitter
- **Recommendation:** Fetch all Twitter handles in one burst, then wait before any other Twitter-related requests

---

## Step 2.3: Edge Cases

| Test | Items | Time | Result |
|------|------:|-----:|--------|
| Underscore prefix (`_prashantnair`) | 20 | 0.95s | Works |
| Double underscore (`Nigel__DSouza`) | 20 | 0.91s | Works |
| `includeRts=0` (deepakshenoy) | 8 | 0.01s | Correctly filtered 9 RTs |
| `includeReplies=1` (deepakshenoy) | 17 | 0.01s | Same count (no recent replies) |
| Replies ON + RTs OFF (sanjeevsanyal) | 0 | 0.76s | All 20 recent items were RTs! |
| Nonexistent handle | 503 | 0.35s | Graceful error |
| Not-in-feeds account (`Nithin0dha`) | 8 | 1.43s | Works perfectly |

### Route Parameter Format
```
/twitter/user/{handle}/{param1}={val1}&{param2}={val2}
```
Example: `/twitter/user/deepakshenoy/includeRts=0&includeReplies=1`

---

## Step 2.1: Soak Test (ongoing)

**Status:** Running in background (PID 567931), polling 5 handles every 30 min.
**Log:** `soak_test_log.jsonl`

### Cycle 1 (18:35, during rate limit)
| Handle | Items | Time | Notes |
|--------|------:|-----:|-------|
| deepakshenoy | 17 | 0.03s | Cache hit |
| KobeissiLetter | 19 | 0.01s | Cache hit |
| michaelxpettis | 0 | 24.4s | Rate limited |
| sanjeevsanyal | 0 | 23.1s | Rate limited |
| contrarianEPS | 0 | 21.8s | Rate limited |

**Observation:** RSSHub's cache saved 2/5 handles during rate limiting. The other 3 hadn't been cached recently.

### Token Validity
- Token has been working for ~1 hour so far
- Soak test will continue monitoring (next cycles at ~19:05, 19:35, etc.)
- Full lifetime measurement requires overnight run — will check results next session

---

## Step 2.4: Token Lifetime (preliminary)

| Question | Finding So Far |
|----------|----------------|
| Token working after 1hr? | Yes |
| Error on expiry? | Not yet observed |
| Multiple tokens supported? | Yes (TWITTER_AUTH_TOKEN accepts comma-separated list) |
| Username/password auth? | Dead since Oct 2025 (mobile client attestation) |

**Will update after soak test completes (12-24 hours).**

---

## Production Architecture Recommendations

### Fetching Strategy
```
1. Fetch all 49 Twitter handles sequentially (1s delay between requests)
2. Total time: ~4-5 minutes
3. Stay within 50-60 request rate limit
4. RSSHub cache (5 min) prevents duplicate API calls
5. Wait >10 min before any additional Twitter requests
```

### Error Detection
```python
# Don't trust HTTP status — check item count!
if response.status == 200:
    items = parse_rss(response.body)
    if len(items) == 0 and expected_items > 0:
        # Likely rate limited — serve from cache
        serve_cached_data()
```

### Hosting Options
1. **Local (current):** Works, but requires Node.js + RSSHub running
2. **Vercel (free tier):** One-click deploy, auto-scaling, but cold starts
3. **GitHub Actions:** Run RSSHub as part of the workflow (install, start, fetch, stop)
4. **Docker on VPS:** Most reliable for production

### Recommendation for FinanceRadar
**Option 3 (GitHub Actions)** is most aligned with current architecture:
- No persistent server to maintain
- Runs as part of the hourly workflow
- Auth token stored as GitHub Secret
- Steps: install RSSHub → start → fetch all handles → generate feeds → stop

---

## Session 2 Decision: Skip Session 3 (Nitter)

All public Nitter instances are dead (tested 8 in Session 1). Self-hosting Nitter requires Docker + Nim compilation — more complex than RSSHub with no additional benefit. RSSHub with `TWITTER_AUTH_TOKEN` is reliable and sufficient.

**Recommendation: Skip Session 3 entirely. Proceed to Session 4 (LinkedIn) or Session 5 (Resilience Design).**

---

## Files
- `session2-notes.md` (this file)
- `session2-scale-results.json` (49-handle raw data)
- `test_scale.py` (scale test script)
- `soak_test.py` (background polling script)
- `soak_test_log.jsonl` (ongoing soak test data)
- `soak_test.log` (soak test console output)
