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
python3 ieefa_local_fetch.py         # IEEFA backfill (headed Chrome, one manual Turnstile tick)
python3 ember_local_fetch.py         # Ember refresh (headed Chrome; CI cannot reach Ember at all)

# AI ranking (requires API keys)
GEMINI_API_KEY="..." python3 ai_ranker.py      # → static/ai_rankings.json
GEMINI_API_KEY="..." python3 wsw_ranker.py     # → static/wsw_clusters.json

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
├─ reports_fetcher.py (23 scrapers) ──→ static/reports_cache.json
├─ twitter_fetcher.py (dual-source) ──→ static/tab_twitter.json
└─ rsshub_local_fetch.py (local only) ──→ static/rsshub_twitter_cache.json

PROCESSING
├─ filters.py: 126 title regex + 24 URL patterns (noise removal)
├─ articles.py: dedup (SequenceMatcher 75%), grouping, HTML cleaning
└─ twitter_signal.py: URL resolution, noise filters, High Signal lane (top 25)

RANKING (separate crons, needs API keys)
├─ ai_ranker.py: 4-model Gemini ranking → static/ai_rankings.json
│   Buckets: news=25, telegram=20, reports=10, twitter=10, youtube=10
│   Post-ranking: cross-bucket clustering (all candidates → LLM → story clusters)
└─ wsw_ranker.py: debate clusters from 7-day window → static/wsw_clusters.json

OUTPUT
├─ index.html (HTML shell, loads templates/app.js + templates/style.css externally)
└─ static/tab_*.json (per-tab data for lazy loading)
```

### Homepage: AI-Curated Feed

The homepage **exclusively shows AI-ranked content** from `static/ai_rankings.json`. Individual tabs remain chronological.

- `getMergedAiRankings(bucket)` in `app.js` merges picks from all providers (four Gemini slots from different generations: 2.5 Flash, 3.5 Flash, 3.8 Flash, 3.1 Flash-Lite) with consensus scoring: items picked by 2+ models rank highest (average rank), single-provider items get a +50 penalty. The frontend is provider-key agnostic — it reads whatever keys `ai_rankings.json` has
- Cross-provider matching uses URL (exact, lowercased) with fallback to `normalizeAiTitle()` (handles unicode dash/quote/ellipsis variants)
- News + Telegram interleave in the newspaper feed (3:1 ratio); YouTube, Reports, Twitter render in dedicated slider sections
- WSW breakers auto-select the provider with the most clusters
- If AI data is unavailable, homepage shows an empty-state message directing users to tabs
- Two sliders are NOT AI-ranked, both chronological: **From The Source** (official channels + SEBI orders, from `tab_news.json`) and **Slow Reads** (`static/tab_slow_reads.json`). Slow Reads covers Indie Voices that post weekly or slower (`SLOW_READS_SOURCES` in `config.py`, matched on feed name — must be unique among News feeds; daily sources The Core, The Arc, The Ken, Finshots, Rest of World, Decoding the Dragon, BharatNama and Biz News+ are in too). `select_slow_reads()` picks them *before* the 5-day news cut: every post from the last 7 days (`SLOW_READS_ALL_POSTS_DAYS`) up to 5 per source, newest first (`SLOW_READS_MAX_PER_SOURCE` — added 2026-10-21 at the user's request once three daily Substacks joined; no total cap), and for any source quiet that week, its newest post from the 30-day window
- The Companies tab (Market Tide) was removed in Sept 2026 because the feed stopped refreshing. `companies_fetcher.py` is no longer called by anything
- The Papers tab was removed in Nov 2026 at the user's request (not useful). `paper_fetcher.py`, its test and `static/papers_cache.json` / `static/tab_papers.json` are no longer used by anything

### This Week calendar (Nov 2026)

A small calendar of India data releases, policy dates, market dates, Nifty 200 results and the main global events. **It never adds a section to the homepage's main column** (user: an extra, it must not take attention from the home page). Mockups: claude.ai/artifact/7nt6PhA8632GBGYuWB4JKH ("Final" page).

- **Data:** `calendar_events.py` → `static/calendar.json` (browser) + `static/calendar.ics` ("Add to my calendar"), built every hour by `build_calendar()` in aggregator.py's main (never raises).
  - `calendar_macro.json` (repo root, **hand-kept**): India CPI/WPI/IIP/GDP/PLFS/core/trade/PMI/fiscal deficit, RBI policy, Budget, US Fed decision + US CPI. `big: true` only for India CPI, GDP, RBI policy, Budget (◆). `confirmed: false` = worked out from the agency's rule, shown as "expected". Researched 11 Nov 2026 from the agencies' published calendars; **runs to 31 Mar 2027 — extend it before then** (MoSPI ARC, OEA/DPIIT ARCs, S&P Global PMI calendar, RBI MPC schedule, Fed FOMC calendar, BLS CPI schedule).
  - Results: NSE `api/event-calendar` (board meetings whose purpose includes "Financial Results"), kept to **all Nifty 200 companies** (user's call; the list comes from nsearchives `ind_nifty200list.csv`, refreshed weekly → `static/nifty200.json`; Nifty 50 names show first, then Nifty 100). `COMMON_NAMES` gives readers' names for long official ones (IRCTC, LIC, Sun Pharma). NSE lists only from tomorrow, so `static/results_calendar_cache.json` keeps today's entries; when NSE answers it is the truth for later dates (moved/cancelled meetings drop), when it doesn't the cache stands.
  - By rule: monthly F&O expiry (last Tuesday, moved back over NSE holidays — Nov 2026's falls on Mon 23 because 24 Nov is a holiday), market holidays (`static/nse_holidays.json`, NSE `holiday-master`, daily), the results deadline (45 days after a quarter, 60 after March), RBI forex reserves (Fridays 5 pm).
- **Browser** (`renderWeekCal()` in app.js, styles at the end of style.css, prefix `wk-`): one list of days, three ways by width. ≥1600px: rail in the right margin, sticky, the page shifts left just enough for it (`.wk-wide`). 769–1599px: folded column of day chips on the right edge, hover/tap → popover (`.wk-fold`, `.wk-pop`; below 1384px the container gets 88px right padding). ≤768px: day strip under the tabs (`.wk-strip`), tap a day → bottom sheet; once the strip scrolls away a "◆ CPI Thu" chip appears in the top bar (`#wk-chip`). Full calendar = the story drawer's frame (`openCalDrawer()`), four weeks, filters. Home tab only. **The two side rails live in `<body>` (`#week-cal-side`), not in `#tab-home`:** the tab's fade-in animates `transform`, which pins `position: fixed` children to the tab, so they sat over the text for half a second after every switch back to Home (user report, 11 Nov). CSS shows them via `body:has(#tab-home.active)`. Only the phone strip (`#week-cal`) is inside the tab. Markers: ◆ moves markets, dots for India data / policy / market / global / results; at most 3 per day.
- Version 2 (not built, user's call): after an event, show the actual figure and link the release (From the Source) / the broker result notes.

### Semantic Story Clustering

A post-ranking step in `ai_ranker.py` clusters articles **across all content types** (news, telegram, youtube, twitter, reports) by underlying story. This is additive — per-bucket rankings are unchanged.

**Backend (`ai_ranker.py`):**
- `cluster_ranked_items()` sends all ~830 candidates (titles only) to the LLM in a single clustering call
- `dedup_cluster_articles()` removes near-duplicate articles via Jaccard title similarity (0.4 same-type, 0.6 cross-type)
- `filter_cluster_noise()` strips Sensex/Nifty market-movement articles from clusters
- `enrich_clusters_from_rankings()` attaches `why_it_matters` and `signal_type` from ranked items
- Clustering failure → `clusters: []`, no crash, page looks like normal

**Frontend (`app.js`):**
- `getMergedClusters()` merges clusters across providers using any-URL overlap (not just lead URL), then sorts by `_providerCount` (how many models picked the story)
- "The Big Stories" section renders at the top of the homepage; clustered items are removed from the feed/sliders below (no duplicates)
- Layout (Oct 2026, "front page + drawer"): story 1 is the lead (headline, summary, signal row, and a **Coverage** list of its top 4 sources — the only sources shown up front); stories 2–3 sit side by side with "Show sources"; **every** story after the top 3 is a one-line brief in "Also developing" (single-model picks included)
- Sources open in a side drawer (`openStoryDrawer()`; a bottom sheet ≤768px), grouped by type. **Never expand sources in place** — the user hates anything that pushes the page down. Titles open the drawer too. `html { scrollbar-gutter: stable }` stops the sideways shift when scrolling locks
- Signal row (`bsSignals()`): dots for how many models picked the story (`agreementHtml()`), a colour strip of the source mix, the source count. Model fallback: dots count only models that ran; with one model the dots are hidden; the caption notes models that didn't run
- Subtitle under each label = `story_summary` from the clustering call (sentence-case label, one plain sentence), falling back to the lead's `why_it_matters`
- Every source has its own bookmark (there is no whole-cluster bookmark)

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

**`reports_fetcher.py`** — 23 `@scraper`-decorated functions for HTML/API scraping. The decorator handles errors, 30-day freshness, article limits, and retries. Dispatched via `REPORT_FETCHERS` dict.

**`feeds.py` → `fetch_careratings()`** — CareEdge uses a separate API-based fetcher (`insightspagedata` endpoint), NOT `reports_fetcher.py`. Dispatched in `aggregator.py` via `feed_field.startswith("careratings:")`.

To add a new scraper: write a `fetch_*()` function, decorate with `@scraper`, register in `REPORT_FETCHERS`, add feeds to `feeds.json` with matching ID prefix.

### Reports → Stock notes (Nov 2026)

Indian brokers' notes on single stocks live in the Reports tab's own **Stock notes** view, next to All / Indian / International. Card = broker, then **company — the PDF's own headline** (company alone until the headline is read). No rating, target or price history on the card (user's call). Clicking opens the PDF.

- **Archive, last 5 years:** `static/stock_notes.json` — a rolling window (`NOTE_HISTORY_YEARS`, `min_note_date()`; user, 11 Nov 2026: "max 5 years"; older notes drop on every merge, so it trims itself daily), ~14k notes, newest first, one note per line so hourly commits touch a few lines. It is the pipeline's copy; the browser never loads it. **The browser loads pieces** (user, 11 Nov 2026: Stock notes was slow to open): `write_note_chunks()` writes `static/stock_notes/recent.json` (newest 200 notes = the first 10 pages, plus the broker list and the years on offer; ~9 KB gzipped, vs ~630 KB for the whole archive) and `static/stock_notes/<year>.json` (only the six fields a card needs). `loadStockNotes()` in app.js fetches recent.json when Stock notes is first opened; `loadMoreStockNotes()` fetches the next year when the reader is two pages from the end of what's loaded, and every remaining year as soon as they search or pick brokers. Only changed files are rewritten, so an hourly run touches recent.json and the current year. Notes never reach `published_snapshot.json` or the AI ranker.
- **Sources — aggregators:** `mcideas:` → Moneycontrol's broker-research JSON API (`fetch_moneycontrol_ideas`; history back to Jan 2024, ~25/day), `bsresearch:` → Business Standard's research page, whole list in `__NEXT_DATA__` (`fetch_bs_research`; back to Nov 2024, mostly brokers Moneycontrol lacks). The hourly run fetches 14 days (`max_age_days`) and `update_stock_notes_archive()` in aggregator.py merges new ones in. Brokers' own sites were added next (below); the aggregators stay for brokers whose sites are locked.
- **Broker-site feeds moved in (user, 10 Nov):** Axis Direct, Baroda eTrade (SOR — "First Light"; its STR page turned out to be BOBCAPS' *sector* research, ~790 reports, and moved back to Reports → Indian on 11 Nov; its MER page, BOB Economics incl. the daily "Morning Mocha", was added to Reports → Indian the same day at the user's request) and HDFC Securities have `"kind": "stock_note"` in feeds.json, so they leave the Reports list for Stock notes. They only have a title, so `split_report_title()` makes "Company: headline" → company + headline, "Result Update:Britannia Inds." → company only (headline read from the PDF), and multi-stock dailies ("First Light | …", "HSIE Results Daily: …") keep the whole title as the headline. The aggregator also splits by feed id, because `reports_cache.json` items written before the move carry no `kind`.
- **Brokers' own sites (11 Nov 2026, user: "skip the middleman"):** seven brokers publish single-stock PDFs without a login, each with its own scraper in `reports_fetcher.py` (section "Brokers' own sites") and a `kind: stock_note` feed: PL Capital (`plindia:` — card title gives company + headline, the report page gives the PDF and date), ICICI Direct (`icicidirect:` — latest ~15 "Investing ideas", date read from the PDF's page 1), Kotak (`kotaksec:` — "Opportune" one-pagers, date from the file name or the PDF's Last-Modified), SBI Securities (`sbisec:` — Pick of the Day/Week + IPO notes; the API body is AES with a fixed key from the site's own JS, done with the `openssl` CLI), Choice (`choice:` — JSON API, headline = first line of the description), Way2Wealth (`way2wealth:`) and Ventura (`ventura:`) (both ASP.NET postback grids). Locked, so still via Moneycontrol/BS: Motilal Oswal, Anand Rathi, Emkay, Geojit (login), Sharekhan (OTP), Nirmal Bang (sign-up form). India Research Hub's scrapers were the map; its repo has no licence, so the recipes were re-written, not copied.
  - **Round 2 (11 Nov 2026):** IDBI Capital (`idbicap:` — idbidirect.in ASP.NET table, "Company: Q2FY27 Result Review", no headline anywhere; paging is a postback that needs the session cookie) and Monarch Networth Capital (`mncl:` — one static page of company blocks; exact date + real headline read from PDF page 1 by `mncl_page_one()`; its server omits the intermediate certificate, so `certs/sectigo-public-server-auth-ca-dv-r36.pem` is shipped and passed as `ssl_context` — verification stays on, `_fetch_url` never falls back to unverified when a context is given). **Nirmal Bang** (`nirmalbang:` — added 11 Nov 2026 with direct PDF links at the user's call: the site shows a mobile-number form before downloads, but that form lives only in the browser and the files are plain public `/Upload/<name>` URLs; listing via `Ajaxpages/ResearchReports.aspx?id=49&pageNo=N`; `split_nb_title()` takes company + real headline from "Company (TICKER) - RATING - Sector | 2QFY27 Result Update - headline - date", drops ratings and skips mornings/macro/AI-insights items). Checked and **not built**: Sharekhan (listing public, PDF links only after OTP), Mehta Equities (PDFs deliberately hidden), Systematix / YES Sec / ICICI Sec institutional (login), KR Choksey, Centrum, LKP, Asit C. Mehta, Angel One, Hem, Bonanza (nothing recent on their own sites), Reliance Securities (TLS certificate expired 10 Nov 2026 — recheck).
  - **Sector & thematic reports → Reports (Indian), not Stock notes (user, 11 Nov 2026):** `nirmalbang:sector` (`nb_sector_title()`, 8 listing pages ≈ a month) and `sbisector:` (SBI's "Thematic Reports" list via `split_sbi_thematic()`; that list also carries single-stock result updates, initiations and plant visits, which `fetch_sbisec` sends to Stock notes). Plain Reports items (no `kind`): 30-day window, AI-ranked. Economy notes (macro trackers, CPI/WPI, RBI) are in too (user, 11 Nov 2026); only market dailies (morning roundups, AI insights) and picks lists are left out (`_SECTOR_NOISE`). `STOCK_NOTE_PUBLISHERS` (homepage Research Reports filter) now lists only brokers with no Reports feed, so these brokers' sector reports still reach the homepage.
  - **HDFC Securities and Axis Direct sector reports (11 Nov 2026):** both sit in the *same* listings as their stock notes, so each broker has one fetcher and two feeds; a feed whose `feed` contains `:sector` (`_wants_sector()`) keeps the sector/economy half, the other keeps stock notes. HDFC: bucket 1913 mixes both — `is_hdfc_sector()` reads the title (sector name before the colon, or series like Bharat Barometer, Capex Tracker, Flipbook; "HSIE Results Daily" stays a stock note); the sector feed reads 300 items (`page_size`). Axis: the page shows 9 cards; more come from `insights/reports/search` (POST) only when every card id seen so far is sent as `ids`; `_axis_cards()` crawls once per run (shared by both feeds, up to 40 pages ≈ a month in results season) and `classify_axis()` splits stock / sector / skip (picks lists, daily views, quant). Checked and skipped: Acuité (1–2 pieces a year), IBEF (reports behind login, pages rewritten in place). **ICRA** (`icra:` — sector research table; page 1 is plain HTML, later pages a POST needing the session cookie, the page's `__RequestVerificationToken`, the page's empty filter fields and `X-Requested-With`; later pages are best-effort) and **India Ratings** (`indiaratings:` — one POST to `pressReleases/GetListing?type=research` lists every report; card links `/pressrelease/<id>`) were added 11 Nov 2026: full reports need a login (many ICRA ones cost ₹20,000), so cards open the free summary page and carry a small **"Paid"** label — feeds.json `"paid": true` → `PAID_PUBLISHERS` → `paidTagHtml()` in app.js (Reports cards and the homepage slider). **ICICI Direct sector notes** (`icicisector:`, publisher ICICI Securities) are short blog posts with no PDF: sitemap slugs shortlist, the post title decides (`is_icici_sector_title()` rejects company news).
  - **FICCI Studies and more NITI (11 Nov 2026, user pasted FICCI/NITI report links):** `ficcistudies:` reads ficci.in/studies (title, date, sector per card) and opens each in-window study's page for its direct public PDF (`SPDocument/<id>/…pdf`); FICCI's Knowledge Paper Series is skipped (titles are just "Knowledge Paper Series 2/2026"). NITI now also reads Working Papers and Research Papers (same Drupal table, PDF in a `report-upload` column). NITI dates were broken until then ("October, 2026" with a comma failed to parse, so every NITI item counted as fresh forever); now month-only dates use the 15th, year-only ones take the upload month from the PDF path, and undated items are skipped.
  - **Arihant Capital (`arihant:`, 11 Nov 2026 — user chose to include it after being told the source is an open server folder):** `Mumbai_Research/` (current) and `Insti/` (to Dec 2025, history only) are raw IIS file listings. Only `.pdf` files are ever fetched (the folder also exposes `web.config` etc. — never touch them). `classify_arihant()` routes by file name: result updates, initiations ("IC"), management/IR meets, plant visits, company updates, stock ideas, **IPO/FPO notes** → Stock notes; sector/industry/strategy/budget/FTA/GST notes, channel checks, previews and compendiums → Reports (Indian) via `arihant:sector`; Diwali picks, "Chhota Packet" portfolios, conference/webinar links, test files and another broker's report → skipped. `arihant_page_one()` reads page 1 for the real date (upload times change on re-upload — an Aug note showed 11 Nov), the headline and the full company name ("HUL" → "Hindustan Unilever"). If Arihant closes the folder listing, the scraper just returns nothing.
  - These notes have `via: ""`. `dedup_stock_notes()` prefers them over a Moneycontrol/BS copy of the same note and carries over a headline already read for the copy. Broker sites rarely print a target, so without one the match is same broker + first two company words (prefix ok: "Aarti Ind" = "Aarti Industries") within 3 days; two direct notes never merge (HDFC put out two Dabur reports a day apart).
  - Some sources need a request per report (PL's report page, Kotak's PDF header, ICICI's page 1). Scrapers skip links and pages already in the archive (`known_note_keys()`; PL entries store the report page as `page`) and cap the rest with `max_lookups` (default 40), so an hourly run makes a handful of requests per broker.
  - **Titles (user, 11 Nov 2026: no company-only cards):** PL and Choice give real headlines; ICICI Direct's is read from the PDF's page 1 (`icici_headline()`: the line after the report date, ending in "…"). Ventura, Kotak and Way2Wealth reports carry **no headline at all** — page 1 only names the report type — so their title is `report_label()` from the file name or caption, e.g. "Q2FY27 Result Update". SBI's is its list label.
  - **Order (user, 11 Nov 2026): latest day first, then A→Z by company** so one stock's notes sit together (`sort_notes()`, names tidied by `_company_sort_key()`: "Mahindra & Mahindra Ltd" = "Mahindra and Mahindra"); within one stock, latest first by `ts` — the time the note was published (PL/Choice/Kotak give one; Moneycontrol and HDFC links carry `YYYYMMDDHHMM…`; Ventura file names start with .NET ticks of the upload) or else when first seen. Multi-stock dailies close the day.
  - HEAD requests lie on these sites: ICICI and Kotak bounce HEAD to login / a bot check but serve the PDF to a plain GET. Ventura's PDFs return 403 to GitHub's IPs (its list works); readers open them from their own browsers.
  - History: `python3 stock_notes_backfill.py --no-headlines --direct [feed ids]` (per-site depth in `DIRECT_HISTORY`). PL alone is ~2.6k report pages.
- No counts anywhere in the Stock notes view (button or header line) — user's call.
- **No ratings in headlines either:** `strip_rating()` (stock_notes.py) trims a tail that names a rating — "…; maintain BUY", "… – Downgrade to 'ACCUMULATE'", "…. BUY" — in `_to_entry()` and `clean_headline()`, so every source goes through it. It must name a rating: on 12 Nov 2026 a looser first version also cut "Volume guidance maintained" and "…Valuation Upgrade" and had to be rolled back from git; tests now pin both.
- **By date / By company (user, 11 Nov 2026):** a toggle under the view switch, shown only in Stock notes. By company lists every company with a note in the last 3 months (`STOCK_NOTES_COMPANY_DAYS = 91` in app.js), A–Z, each with all of its notes from that window, newest first; 20 companies a page, an A–Z letter strip to jump (hidden while searching). No counts and no "most notes" sort (user dropped it from the mockup). It loads only the year files the window needs, even when searching. Company names are grouped by `stockNoteCompanyKey()` in app.js — keep it in step with `_company_sort_key()` in stock_notes.py (both drop Ltd/the and a trailing "Company/India/Industries/Corporation/Enterprises", so "Titan" = "Titan Company", "GAIL (India)" = "GAIL India").
- **Homepage:** a chronological **Stock Notes** slider (newest 30 single-company notes, `select_home_notes()` → `static/tab_stock_notes_home.json`, ~9 KB) sits just above the quote before From the Source (user, 10 Nov). The homepage Research Reports slider never shows stock notes: the ranker never sees them, and `buildRpSlider` also drops any pick whose publisher is in `STOCK_NOTE_PUBLISHERS` (injected from feeds.json) in case `ai_rankings.json` predates the move.
- **Headlines, last 90 days (10 Nov):** read by Claude subagents from page-1 text instead of Gemini (the laptop key was 402): 1,023 of 1,041 filled; 18 deliberately blank (no headline on page 1, or Moneycontrol's PDF link points at another company's report — seen for Aarti Industries→Syrma SGS, IRCTC→Petronet LNG, Indian Bank→Tech Mahindra) with `headline_tries` maxed so CI won't retry them. Older history is left to the hourly Gemini fill.
- **No-AI headlines ON in CI (11 Nov 2026):** `rule_headline()` reads page 1's layout with `pdftotext -bbox-layout` (`pdf_first_page_lines()`) for the two big brokers that only reach us via Moneycontrol/BS — ICICI Securities (the line after "India | Equity Research", company and sector, set larger than body text) and Motilal Oswal (the largest line that isn't the company, a price, a rating or a disclaimer; wrapped lines joined). Checked against 150 Claude-read headlines: 149 matched. **Emkay and Anand Rathi added 12 Nov 2026** (60/60 each): the largest line that isn't the company, a rating, a price line or a bare report-type banner (rating words allowed — their headlines end "…; maintain BUY"); Anand Rathi takes the first sizeable line after its big company name. Choice was tried and left out (47/60 — several desk layouts; most Choice notes come from its own site with headlines). `fill_headlines(..., ask_model=rule_headlines, brokers=RULE_HEADLINE_BROKERS)` runs every hour (`STOCK_NOTE_RULE_HEADLINES`). Other brokers get no rule: a wrong guess is worse than none.
- **Gemini headlines are OFF in CI** (`STOCK_NOTE_HEADLINES_ENABLED = False`, user's call 10 Nov 2026: no Gemini headlines). Headlines for Jan 2025 → 10 Nov 2026 were read by Claude subagents locally and stay; older and newer notes show the company only. When enabled: `fill_headlines()` downloads each PDF, reads page 1 with `pdftotext` (poppler-utils, installed by hourly.yml), and Gemini (`HEADLINE_CHAIN`, flash-lite first, 8 notes per call) copies out the headline. Up to 1,000 per hourly run within 10 min, newest first. `STOCK_NOTE_HEADLINE_MAX_AGE_DAYS` in aggregator.py limits how far back CI reaches (None = all history. Jan 2025 onwards was filled by local Claude batches in Nov 2026; Gemini in CI filled Nov 2023 – Dec 2024 at the user's request, then handles new notes). A failed download / no headline burns one of 2 tries; a Gemini outage burns none. Skipped cleanly without `GEMINI_API_KEY` or `pdftotext`.
- `stock_notes_backfill.py` re-fetches the full history (`--no-headlines` needs no key; ~9 min) and can fill headlines locally (`--headlines-only`). Re-runnable; saves as it goes. (Nov 2026: the laptop's own GEMINI_API_KEY returned HTTP 402 on every model while the Actions secret worked — that is why headlines are filled in CI.)
- `stock_notes.py` holds what every source must agree on: `canonical_broker()` (one spelling per broker — AnandRathi, Mirae Asset Sharekhan, KRChoksey/Deven Choksey and "Pvt Ltd" are folded; returns None for foreign houses like Citi/Jefferies and for aggregators' own picks — the view is **Indian-only**, user rule), `dedup_stock_notes()` (same broker + same first company word within 3 days + equal targets, or the two-word match when a target is missing = one call; the broker's own site wins, then the entry with a headline), archive load/save/merge.
- Moneycontrol sometimes dates a report after the day it posted it (posted 2 Nov, dated 11 Nov). The fetcher takes the earlier date.
- Notes carry a date but no time, so the card shows no "Nh ago".
- Inspiration: yashsarda31's India Research Hub (github.com/yashsarda31/india-research-hub) — used as a map of sources, not as a data feed (one person's hand-run Windows build, no licence).

### Frontend Architecture

- Source: `templates/app.js` (vanilla JS, ~3700 lines) + `templates/style.css` (~2900 lines)
- Loaded by `index.html` as external files (`<script src>` / `<link href>`) — **never edit `index.html` directly**, edit `templates/*`, then run `python3 aggregator.py`
- Theme: Fraunces headings, Nunito Sans body, burnt orange accent (#C45A35), light-only (no dark mode)
- Design system (Oct 2026 redesign): the "Redesign" section at the end of `style.css` holds the tokens — one type scale (`--t-xs/s/m`), one spacing scale (`--s-1…8`, `--gap-col`, `--gap-block`, `--row-pad`). Hairline rules instead of boxes, no all-caps labels, bookmarks always visible. Top bar + tabs are pinned together in `.site-head`; `app.js` measures its height into `--head-h` so sticky day headers sit right under it
- Home order: Big Stories → quote → Research Reports → From the Feed (lead + side list + rows) → quote → Slow Reads → rows → quote → Watch → rows → **Stock Notes** → quote → From the Source (a list in a fixed-height scroll box, not a slider) → Voices → quote → More from the feed (every remaining story in a fixed-height box that scrolls inside itself — the homepage must end, not grow)
- Section signals: Research Reports show India/International + publish date (ai_ranker carries `region` from feeds.json and `date`); Voices mark reposts/quotes/threads + model dots; From the Source rows start with an issuer badge in a fixed colour (`ISSUERS`) with a count strip above
- Every homepage heading has an (i) with one or two lines from `SECTION_INFO`; the note floats in one fixed element (`showInfo()`), never in the DOM text (keeps it out of homepage search)
- `deshoutTitle()` turns ALL-CAPS headlines (Telegram, SBI notes) into Title Case, keeping acronyms, letter+digit codes (FY27) and a leading ticker ("CMPDI : …")
- All state in localStorage (active tab, bookmarks, page number)
- Keyboard nav: J/K (next/prev), / (search), Esc (clear), H (home), 1-5 (tab shortcuts: News, Reports, Telegram, YouTube, Twitter — tab order since Nov 2026; note `data-tab="research"` is the Reports tab and `data-tab="reports"` is Telegram)
- Homepage loads only `ai_rankings.json`; individual tabs lazy-load their own `tab_*.json` on first visit

### Module Map

19 Python modules (~8900 lines total). Key cross-file relationships:

| Module | Role | Called by |
|--------|------|-----------|
| `aggregator.py` (1463L) | Main pipeline: fetch → filter → dedup → group → generate HTML | Standalone / hourly.yml |
| `feeds.py` (829L) | Feed loading, RSS fetching, date parsing, **CareEdge API** | aggregator.py |
| `reports_fetcher.py` (1660L) | 23 `@scraper` functions for institutional reports | aggregator.py |
| `articles.py` (220L) | Dedup, grouping, HTML cleaning, JSON export | aggregator.py |
| `filters.py` (356L) | 126 title regex + 24 URL patterns | aggregator.py |
| `twitter_fetcher.py` (345L) | Dual-source Twitter (RSSHub + Google RSS) | aggregator.py |
| `twitter_signal.py` (659L) | URL resolution, noise filters, High Signal lane | twitter_fetcher.py |
| `ai_ranker.py` (~1080L) | 4-slot Gemini ranking + cross-bucket clustering | ai-ranking.yml |
| `gemini_client.py` | Shared Gemini caller: fallback chains, retries, model discovery | ai_ranker, wsw_ranker, twitter_signal |
| `wsw_ranker.py` (418L) | "Who Said What" debate clusters | ai-ranking.yml (after ai_ranker) |
| `telegram_fetcher.py` (580L) | HTML scraping + Telethon MTProto | Standalone / hourly.yml |
| `piie_local_fetch.py` (210L) | Playwright scraper → `static/piie_cache.json` | Local only (manual) |
| `ieefa_local_fetch.py` (205L) | Playwright backfill → tops up `static/ieefa_cache.json` | Local only (manual) |
| `ember_local_fetch.py` (170L) | Playwright + Ember WP REST API → `static/ember_cache.json` | Local only (manual) |
| `config.py` (86L) | All magic numbers and tunables | Imported by most modules |
| `stock_notes.py` | Stock notes: broker names, Indian-only filter, dedup, archive, PDF headlines | reports_fetcher.py, aggregator.py |
| `stock_notes_backfill.py` | Re-runnable full-history fetch + headline fill | Local only (manual) |
| `official_sources.py` | Regulators without RSS (DGTR, CBIC, IRDAI, PFRDA, IFSCA, CCI, MCA, DPIIT) → Official Channels | aggregator.py |
| `calendar_events.py` | This Week calendar: macro file + NSE results/holidays + rule dates → `static/calendar.json` / `.ics` | aggregator.py |

Frontend: `templates/app.js` (~4080L) + `templates/style.css` (~3100L). Tests: 18 modules in `tests/`.

## Key Rules

### Generated Files — Do Not Hand-Edit
All files in `static/` and `index.html` are auto-generated. Edit source scripts or `templates/*` instead, then regenerate. Note: `about.html` is **not** generated — it's a standalone hand-edited page.

### F-String Brace Escaping
When editing HTML/CSS/JS templates inside `aggregator.py` (which uses Python f-strings), escape literal braces: `{{` and `}}`. The `templates/` files use normal braces.

### Git Conflicts on Generated Files
Generated files conflict often between local pushes and GH Actions commits. A third actor is easy to miss: the local `rsshub-fetch.timer` commits and pulls on the hour, so a long local `aggregator.py` run straddling :15 can come back to a half-merged index. Check `git diff --diff-filter=U` before blaming your own changes; clear it with `git checkout HEAD -- <generated files>` and regenerate.

Resolve conflicts by taking remote:
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
- `keep_days`: News-only, optional. For publishers whose RSS only holds a day or two (The Core), `merge_news_cache()` keeps every post in `static/news_cache.json` for this many days, so stories survive the full 5-day news window and the 30-day Slow Reads window
- `link_contains`: optional. Keep only items whose link contains this substring. Bloomberg newsletters have no feeds of their own (newsletter pages + their `newsletters-signup-next` API sit behind PerimeterX), so each is pulled from its **steady writers'** author RSS with `"link_contains": "/newsletters/"`. Rotating-writer newsletters (New Economy, Deals, Business of Food/Sports, Green Daily) were deliberately left out — the user wants no stray writers or editions. `dedupe_by_link()` collapses co-written issues
- `max_items` / `max_age_days`: Reports-only, optional. Override the scraper decorator's 30-item cap and 30-day window per feed (stock-note feeds use 800/400 and 14 days; `max_pages` caps Moneycontrol paging)
- `kind`: Reports-only, optional. `"stock_note"` routes a feed's items into the Stock notes archive instead of the Reports list (set on the item by the fetcher; the feeds.json key documents it)
- `link_excludes`: optional. Drop items whose link contains this substring. The Core's main feed (`thecore`) excludes `"/opinion/"`, and a second entry on the same feed URL (`thecore-opinion`, "The Core Opinion") keeps only `"/opinion/"`, so The Take + The Plinth get their own Slow Reads slots instead of competing with The Core's daily news for its 5
- `dgft:<list>` (News, official): DGFT's listing pages are server-rendered tables (number | year | subject | date | hidden timestamp | PDF) — `fetch_dgft()` / `parse_dgft_table()` in feeds.py. Only **Notifications** is on (import/export policy changes, e.g. the 10 Nov 2026 ban on exporting lithium-ion battery black mass; user asked for it in Official Channels). Public notices and trade notices (`dgft:public-notices`, `dgft:trade-notices`) work too but are mostly procedural (HBP paras, SIONs, portal changes), so they're left out. DGFT is in the Official Channels desk and has its own From the Source badge
- `official:<key>` (News, official) → `official_sources.py`: Indian regulators without RSS, added 12 Nov 2026 at the user's request (trade remedies & customs, other financial regulators, competition & company law, FDI policy). Each is a `@source` parser that keeps policy signal and drops procedure: **DGTR** (homepage "What's New": Initiations + Prelim/Final Findings tabs, 5 newest each; no paging exists), **CBIC** customs notifications (JSON API `taxinformation.cbic.gov.in/api/cbic-notification-msts`, categories Tariff / Anti Dumping Duty / CVD / Safeguards, header `language: en` required; its servers omit Sectigo's OV R36 intermediate → shipped as `certs/sectigo-public-server-auth-ca-ov-r36.pem`, verification stays on), **IRDAI** (press releases, circulars, regulations, exposure drafts; English half of "Hindi / English" titles), **PFRDA** (same four lists), **IFSCA** ("What's New" page, filtered by Type), **CCI** (press-release DataTables JSON, `X-Requested-With` header; mostly merger approvals + penalties), **MCA** (notifications + general circulars; Akamai only lets curl's HTTP/2 through, so `_curl()` shells out; dated by upload time because uploads lag weeks), **DPIIT** (FDI press notes from its WordPress API; subject read from the PDF's page 1 with pdftotext). All land in Official Channels + From the Source with their own badges. A failing source logs `[FAIL]` and returns nothing
- For sites behind Cloudflare/WAF, use Google News RSS proxy: `https://news.google.com/rss/search?q=site:domain.com/path&hl=en-IN&gl=IN&ceid=IN:en`

## Scraper Development
- Start with `curl` + browser-like headers (`User-Agent`, `Accept`, `Accept-Language`). Many financial sites (Akamai WAF, Cloudflare) block basic HTTP clients.
- Fall back to Playwright only if curl fails.
- For Cloudflare JS-challenge sites (e.g., PIIE), use the cache-based pattern: scrape locally with a real browser → save to `static/*_cache.json` → pipeline reads cache.
- Before falling back to a browser, check whether the site publishes an `/rss.xml` that the WAF lets through — CEEW and IEEFA both block their listing pages but serve RSS at 200. If that feed is a short sitewide firehose, accumulate it into a rolling cache instead of reading it fresh each run (see `fetch_ieefa`).
- If the site is WordPress, try `/wp-json/wp/v2/<type>` from inside a cleared browser session before scraping the DOM. Ember exposes `insight_page` plus an `insight_type` taxonomy that way — structured JSON with real dates and categories. `?_fields=` keeps the payload small.
- Ember is the strictest case in the repo: every path including `robots.txt` is challenged, so **nothing** refreshes in CI. `fetch_ember_cache` is a pure reader with no TTL — items carry their own dates and the 30-day window filters them, so a neglected cache empties itself rather than serving stale reports. It warns past 7 days.
- Some sites challenge on request *rate*, not per request — IEA serves 200s until you fetch twice quickly, then returns an interstitial. Fetch once per run and detect the challenge explicitly (`fetch_iea`), or you will parse zero cards out of the interstitial and cache that as a real empty result.
- Adobe AEM sites (Apollo, CRISIL Ratings) often back their card grids with a `/api/int.*.json` servlet named in a `data-*` attribute on the page. Read the site's clientlib JS for the exact query string. Apollo's `int.insight.json` answers HTTP 500 for `pageOffset=0` (it is 1-based) and for any `selectedFilter`, so `fetch_apollo` requests page 1 unfiltered and filters formats locally. A 500 from AEM usually means a bad parameter, not a bot block.
- A feed that is fine in a browser but fails with `not well-formed (invalid token)` usually has a raw `&` in it. `_parse_feed_content()` retries once with `_escape_bare_ampersands()` (CDATA left alone), which fixed Rest of World (Nov 2026: `?width=380&dpr=2` in image URLs).
- The FRED Blog moved from `fredblog.stlouisfed.org` to `fred.stlouisfed.org/blog/`, and that host drops scripted connections (HTTP/2 reset, HTTP/1.1 hang, also from Actions and the RSS proxy), so it is read through Google News (`site:fred.stlouisfed.org/blog when:30d`). Keep the `when:30d`: a plain `site:` search is ranked by relevance and changes between calls — one call gave the newest 61 posts, the next 100 older ones with nothing after 19 Oct, which silently emptied FRED from the 5-day News window. Use `when:` on any Google `site:` feed for a low-volume source whose new posts go missing. The " - Federal Reserve Bank of St. Louis" title tail is stripped via a `FRED` alias in `_normalize_google_source_suffix()`.
- **TLS is always verified (Nov 2026).** The old "verification failed → retry unverified" fallback (in reports_fetcher, feeds and telegram_fetcher) was removed; it had not fired once in 40 hourly runs. A site whose server leaves out its intermediate certificate gets that public certificate shipped in `certs/` and passed as `ssl_context` (Monarch Networth); never disable verification. Tests fail if `CERT_NONE` or `NOVERIFY` appears in any module.
- Any cache the pipeline both reads and writes must be written atomically (`_atomic_write_json`). A half-written file read back as `{}` will silently wipe an accumulating cache — this happened to `ieefa_cache.json` when the rsshub timer's git operations raced an aggregator run. `fetch_ieefa` also refuses to write when the load came back empty but the file on disk is populated.

## UI Development
- Edit `templates/app.js` and `templates/style.css`, then `python3 aggregator.py` to regenerate.
- Test mobile (≤640px) before committing — filters collapse by default on mobile, sidebars use body scroll lock.
- Make changes incrementally. Never introduce a rendering gate that can blank the page.
- The feed's lead card on the homepage supports `why_it_matters`, `signal_type` badges, and consensus indicators from AI rankings.
- `about.html` is standalone (its own inline CSS) but mirrors the site's design tokens — keep the two in step when the design changes.
- Tabs show no counts (user, 11 Nov 2026: "just let those tabs be"). Don't add numbers back to the tab bar.
- No dark mode. The site is light-only — do not add dark theme variables, toggle buttons, or theme-switching JS.

## GitHub Actions Workflows

| Workflow | Schedule | What it does |
|----------|----------|-------------|
| `hourly.yml` | Every hour | telegram_fetcher → aggregator → commit + push |
| `ai-ranking.yml` | 2x daily (UTC 10, 22) | ai_ranker → wsw_ranker → commit + push. WSW and commit run with `if: !cancelled()`, so one ranker failing never blocks the other's output. Targets 6 AM / 6 PM IST completion (cron offset 2.5 hrs earlier for Actions delay) |
| `missing-story-audit.yml` | Daily UTC 00:30 | Audit 7-day SLA breaches |
| `feed-health.yml` | Mondays UTC 03:30 | `feed_health.py --report`: lists feeds quiet past their limit (newest item older than News 10 / Reports 30 / Videos 21 / Stock notes 21 days, or `quiet_days` in feeds.json) from `static/feed_health.json`, which every hourly run updates. Fails when anything is quiet, so GitHub emails the owner; the table is on the run summary |
| `deploy-rss-proxy.yml` | Manual | Deploy Cloudflare RSS proxy worker |

Required secrets: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION`, `GEMINI_API_KEY`, `RSS_PROXY_URL` (optional), `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.

## Local Services (systemd user units)

RSSHub runs locally as a systemd user service for Twitter feed enrichment:
- `rsshub.service`: RSSHub Node.js server on port 1200 (auto-start on login, auto-restart on crash)
- `rsshub-fetch.timer`: Triggers hourly fetch + git push (catches up after sleep via `Persistent=true`)
- Config: `~/.config/systemd/user/rsshub*.service|timer`
- Scripts: `~/.local/bin/start-rsshub.sh`, `~/.local/bin/fetch-rsshub.sh`
- Check status: `systemctl --user status rsshub.service rsshub-fetch.timer`

Cache refresh for the two sources CI cannot reach (IEA, Ember):
- `financeradar-caches.timer`: Mon/Thu 09:30, runs `refresh_local_caches.py` → refreshes both caches, commits, pushes
- Offset from the `:15` rsshub timer; both take `/tmp/financeradar-git.lock` (the rsshub side only since 1 Nov 2026), so they never run git at the same time
- Refuses to overwrite a cache with an empty result — a failed run leaves things exactly as they were
- Check status: `systemctl --user list-timers financeradar-caches.timer`
- Run now: `systemctl --user start financeradar-caches.service`

**Logs: this user cannot read journald** (not in `adm`/`systemd-journal`), so `journalctl --user` returns nothing for any unit. `financeradar-caches` writes to `~/.local/state/financeradar-caches.log` instead — `tail ~/.local/state/financeradar-caches.log`. The rsshub fetch now logs to `~/.local/state/rsshub-fetch.log` (`fetch-rsshub.sh` redirects itself there, trimmed to ~2000 lines) — check it first when tweets look stale.

**How the Twitter push stays unstuck** (`sync_cache_to_github()` in `rsshub_local_fetch.py`, tests in `tests/test_rsshub_git_sync.py`). On 26 Oct 2026 a pull conflict on `static/news_cache.json` left the checkout mid-merge and no tweets reached GitHub for a week. It also swept staged, unfinished work into a "twitter cache" commit. The function now: takes `/tmp/financeradar-git.lock` (waits up to 5 min); finishes or aborts any merge an earlier run left behind; commits **only** the cache path (`git commit --only`); on a pull conflict takes GitHub's copy of every generated file (`index.html`, `static/*`) except its own fresh Twitter cache, and **aborts** the merge if a source file conflicts; retries the push once; refuses to push when the checkout isn't on `main`. A failed push exits 2, so the unit shows as failed.

**The local checkout must stay on `main`.** `fetch-rsshub.sh` runs `git pull origin main` regardless of the checked-out branch and then a bare `git push`. On a feature branch that used to merge main in hourly and push nowhere — which stranded 33 cache commits and left production on a 5-day-stale RSSHub cache. Since 1 Nov 2026 it refuses to push off `main` (logged warning, exit 2), but tweets still stop until you switch back. Do feature work in a worktree.

## Config (config.py)

Key constants: `FEED_FETCH_TIMEOUT=15`, `FEED_THREAD_WORKERS=10`, `NEWS_FRESHNESS_DAYS=5`, `REPORTS_FRESHNESS_DAYS=30`, `RSSHUB_CACHE_MAX_AGE_HOURS=6`, `TWITTER_HIGH_SIGNAL_TARGET=25`, `AI_RANKER_TARGET_COUNT=25`, `AI_RANKER_MAX_CLUSTERS=7`. Per-scraper timeout/retry overrides via `SCRAPER_TIMEOUT_OVERRIDES` and `SCRAPER_RETRY_OVERRIDES` dicts.

AI ranker bucket targets are in `ai_ranker.py:BUCKET_TARGETS` (news=25, telegram=20, reports=10, twitter=10, youtube=10). Clustering constants: `AI_RANKER_MAX_CLUSTERS`, `AI_RANKER_MIN_CLUSTER_SIZE`, `AI_RANKER_CLUSTER_TIMEOUT`.

## API Integration
- **All AI calls go to Gemini via `gemini_client.generate_json()`** (Oct 2026 — OpenRouter was dropped after its prepaid credit ran out and every DeepSeek call returned HTTP 402). Users: `ai_ranker.py` (4 slots in `MODELS`), `wsw_ranker.py` (3 slots in `WSW_MODELS`), `twitter_signal.py` (`TWITTER_SIGNAL_MODEL_CHAIN`, hourly). Each slot is a *chain* of model IDs, not one ID:
  - 429/5xx/unparseable JSON → retried with backoff; a timeout (120s, `AI_RANKER_GEMINI_TIMEOUT`) → straight to the next model, no retry; 404 or an exhausted quota → model skipped for the rest of the run; 400 with a `thinkingConfig` → retried without it
  - Slot fallbacks avoid other slots' primaries so a fallback never gives one model two consensus votes. Typical Flash call: ~10s (logged per call as `[OK] news: 25 (model, Ns)`)
  - The API's model list is fetched once per run: chain IDs Google no longer lists go to the back, and the 2 newest listed Flash models are appended as a last resort. The log line `[gemini] N models available; Flash: …` shows what exists — use it to pick new IDs
  - Thinking is kept off/low (`thinking_config()`): 2.5 Flash `thinkingBudget: 0`, Gemini 3+ `thinkingLevel: low`
  - When a slot falls back, its `name` in the JSON becomes the model that actually answered; `ai_rankings.json` also records `models_used` per slot
  - If every slot fails, `ai_ranker.py` exits 1 **without** overwriting `ai_rankings.json` (an all-error file would blank the homepage)
