# Subtext: Person-Centric Aggregation

> Follow a curated list of writers and experts — everything they authored, in one place.

**Date:** 2026-07-29
**Status:** Design approved, ready for implementation plan

---

## Problem

FinanceRadar is organised entirely around *publishers*. Neither RSS branch in `feeds.py`
(`_parse_feed_content`, lines ~300–380) reads `dc:creator` or `<author>`, so no article in the
system carries an author. That makes it impossible to answer "what has Tamal Bandyopadhyay
published this fortnight?" — even though some of his work is already being fetched every hour.

Five people to follow:

| Person | Beat | Why they matter |
|---|---|---|
| Tamal Bandyopadhyay | Banking | Consulting Editor, Business Standard; weekly *Banker's Trust* column |
| Ajay Srivastava | Trade policy | Founder, GTRI; ex-DGFT / Indian Trade Service |
| Sandeep Parekh | Securities law | Founder, Finsec Law Advisors; ex-SEBI ED (Enforcement/Legal) |
| Bhargavi Zaveri Shah | Financial regulation | Doctoral researcher, NUS Law; LEAP Blog, ThePrint |
| Ananth Narayan | Markets / regulation | SEBI Whole-Time Member Oct 2022 – Jan 2026; formerly SPJIMR |

## Goal

A new **Subtext** tab: a chronological river of everything these five *authored* in the last
14 days, each item badged with its author, filterable per person — and templatized so adding
a sixth person is a JSON edit, not a code change.

## Non-goals

- **No historical backfill.** Rolling 14-day window only. No archive, no accumulation store,
  no Playwright scraping of paywalled/WAF-blocked author archives.
- **No content *about* them.** A news story quoting Sandeep Parekh does not qualify.
- **No interviews, podcasts, or speaking appearances.** Written output they authored only.
- **No re-routing.** Items continue to appear in their original tabs; Subtext is a lens.
- **No new cron.** Runs inside the existing hourly `aggregator.py` pass.

## Decisions taken

| Question | Decision |
|---|---|
| What counts as "theirs"? | Authored only |
| How far back? | Rolling 14 days, no backfill |
| UI shape | New tab, one chronological river with person badges + filter chips |
| Architecture | `people.json` config + `subtext_fetcher.py`, two-tier attribution |

---

## Feasibility (verified 2026-07-29)

| Channel | Result |
|---|---|
| Google News name query, unscoped | **Works.** 100 items Tamal, 56 Ananth, 25 Sandeep, 13 Bhargavi, 9 Ajay+GTRI |
| Google News `site:` scoped | **Works.** `site:business-standard.com "Tamal Bandyopadhyay"` → 100; `site:finseclaw.com` → 100; `site:gtri.co.in` → 13 |
| LEAP Blogger author-label RSS | **Works.** `/feeds/posts/default/-/author:%20Bhargavi%20Zaveri?alt=rss` returns her court/regulation posts |
| Business Standard author pages | **HTTP 403** — Akamai WAF. Reached via Google News instead |
| GTRI / Finsec native feeds | **404** — no RSS. Google News is the only route |

No new fetch infrastructure needed. Every channel resolves to a URL that the existing
`fetch_feed()` can retrieve, inheriting the Cloudflare RSS proxy, curl-on-403 fallback,
TLS retry and date parsing.

---

## Data model: `people.json`

Repo root, sibling to `feeds.json`. Single source of truth; the templatization surface.

### Person schema

| Field | Required | Purpose |
|---|---|---|
| `id` | yes | Stable slug, lowercase-hyphenated. Keys the filter chip and `person_id`. |
| `name` | yes | Display name on the badge. |
| `beat` | no | Short label ("Banking") for the chip tooltip. |
| `aliases` | yes | Every spelling to match. Must include `name`. |
| `signature_phrases` | no | Column/series names that prove authorship (`Banker's Trust`). |
| `author_slugs` | no | URL fragments proving authorship (`/author/bhargavi-zaveri-shah`). |
| `channels` | yes | List of channel objects (below). |

`aliases` is load-bearing: Indian names transliterate inconsistently (Bandyopadhyay /
Bandopadhyay, Ananth / Anant). Attribution matches every alias, never just `name`.

### Channel schema

| Field | Purpose |
|---|---|
| `kind` | `owned` or `discovered` — the trust level |
| `type` | `x`, `google`, `blogger`, `internal` |
| `handle` | X handle, for `type: x` |
| `site` | Domain to scope a Google query. `null` = unscoped name search |
| `host` + `label` | Blogger host and author label, for `type: blogger` |
| `query_extra` | Extra terms appended to the Google query (disambiguation) |
| `require_path` | Link must contain one of these paths, else reject before scoring |
| `require_terms` | Title+description must contain one of these, else reject |

**`kind` is a property of the channel, not the source's prestige.** `owned` means the channel
*structurally cannot* contain someone else's writing — a personal X account, an author-scoped
Blogger feed. A firm's own site is **not** owned: `finseclaw.com` publishes Sandeep's partners,
`gtri.co.in` publishes GTRI staff. Both are `discovered` and get name-filtered.

### Seed configuration

```json
{
  "people": [
    {
      "id": "tamal-bandyopadhyay",
      "name": "Tamal Bandyopadhyay",
      "beat": "Banking",
      "aliases": ["Tamal Bandyopadhyay", "Tamal Bandopadhyay"],
      "signature_phrases": ["Banker's Trust", "Bankers Trust"],
      "author_slugs": ["/author/tamal-bandyopadhyay"],
      "channels": [
        { "kind": "owned",      "type": "x",      "handle": "TamalBandyo" },
        { "kind": "discovered", "type": "google", "site": "business-standard.com",
          "require_path": ["/opinion/", "/columns/"] },
        { "kind": "discovered", "type": "google", "site": null },
        { "kind": "discovered", "type": "internal" }
      ]
    },
    {
      "id": "ajay-srivastava",
      "name": "Ajay Srivastava",
      "beat": "Trade policy",
      "aliases": ["Ajay Srivastava"],
      "signature_phrases": [],
      "author_slugs": ["/author/ajay-srivastava"],
      "channels": [
        { "kind": "owned",      "type": "x",      "handle": "ajaydgft" },
        { "kind": "discovered", "type": "google", "site": "gtri.co.in",
          "require_terms": ["Ajay Srivastava", "GTRI"] },
        { "kind": "discovered", "type": "google", "site": "business-standard.com",
          "require_path": ["/opinion/", "/columns/"] },
        { "kind": "discovered", "type": "google", "site": "thehindubusinessline.com",
          "require_path": ["/opinion/"] },
        { "kind": "discovered", "type": "google", "site": null,
          "query_extra": "GTRI",
          "require_terms": ["GTRI", "trade", "tariff", "FTA", "export", "import", "WTO"] },
        { "kind": "discovered", "type": "internal",
          "require_terms": ["GTRI", "trade", "tariff", "FTA", "export", "import", "WTO"] }
      ]
    },
    {
      "id": "sandeep-parekh",
      "name": "Sandeep Parekh",
      "beat": "Securities law",
      "aliases": ["Sandeep Parekh", "Sandeep P Parekh", "Sandeep Pravin Parekh"],
      "signature_phrases": [],
      "author_slugs": [],
      "channels": [
        { "kind": "owned",      "type": "x",      "handle": "SandeepParekh" },
        { "kind": "discovered", "type": "google", "site": "finseclaw.com",
          "require_terms": ["Sandeep Parekh"] },
        { "kind": "discovered", "type": "google", "site": "economictimes.indiatimes.com",
          "require_path": ["/opinion/", "/blogs/"] },
        { "kind": "discovered", "type": "google", "site": "financialexpress.com",
          "require_path": ["/opinion/"] },
        { "kind": "discovered", "type": "google", "site": null },
        { "kind": "discovered", "type": "internal" }
      ]
    },
    {
      "id": "bhargavi-zaveri-shah",
      "name": "Bhargavi Zaveri Shah",
      "beat": "Financial regulation",
      "aliases": ["Bhargavi Zaveri Shah", "Bhargavi Zaveri-Shah", "Bhargavi Zaveri"],
      "signature_phrases": [],
      "author_slugs": ["/author/bhargavi-zaveri-shah", "/author/bhargavi-zaveri"],
      "channels": [
        { "kind": "owned",      "type": "x",       "handle": "bhargavizaveri" },
        { "kind": "owned",      "type": "blogger", "host": "blog.theleapjournal.org",
          "label": "author: Bhargavi Zaveri" },
        { "kind": "discovered", "type": "google",  "site": "theprint.in" },
        { "kind": "discovered", "type": "google",  "site": "business-standard.com",
          "require_path": ["/opinion/", "/columns/"] },
        { "kind": "discovered", "type": "google",  "site": null },
        { "kind": "discovered", "type": "internal" }
      ]
    },
    {
      "id": "ananth-narayan",
      "name": "Ananth Narayan",
      "beat": "Markets & regulation",
      "aliases": ["Ananth Narayan", "Anant Narayan",
                  "Ananth Narayan Gopalakrishnan", "Ananth Narayan G"],
      "signature_phrases": [],
      "author_slugs": [],
      "channels": [
        { "kind": "owned",      "type": "x",      "handle": "ananthng" },
        { "kind": "discovered", "type": "google", "site": null },
        { "kind": "discovered", "type": "internal" }
      ]
    }
  ]
}
```

**Expect Ananth to be thin.** He was a SEBI Whole-Time Member from Oct 2022 to Jan 2026, when
almost all his output was official speeches and his name appeared in press coverage far more
often than on a byline. He also announced in Aug 2022 that his X activity would diminish, and
the account has been largely retweets since. His volume may recover now his term has ended.
This is a content reality, not a fixable design gap.

---

## Module: `subtext_fetcher.py`

```
load_people(path)                     → list[person]      pure
build_channel_feed_config(person, ch) → feed_config|None   pure
fetch_channel(person, channel)        → list[article]      network
scan_internal_pools(person, pools)    → list[article]      pure
is_authored_by(person, article, ch)   → bool               pure
fetch_subtext(pools=None, now=None)   → list[article]      orchestrator
save_subtext_cache / load_subtext_cache
```

Only `fetch_channel` and the orchestrator touch the network. Everything else is pure and
unit-testable without mocks or fixtures.

### Channel → URL resolution

| `type` | Resolves to |
|---|---|
| `google`, `site` set | `news.google.com/rss/search?q=site:{site}+"{name}"{+query_extra}&hl=en-IN&gl=IN&ceid=IN:en` |
| `google`, `site: null` | `news.google.com/rss/search?q="{name}"{+query_extra}&hl=en-IN&gl=IN&ceid=IN:en` |
| `blogger` | `https://{host}/feeds/posts/default/-/{urlquote(label)}?alt=rss` |
| `x` | Filter the passed-in Twitter pool by handle; fall back to `site:x.com/{handle}/status` Google query if absent |
| `internal` | No fetch — scan `pools` |
| unknown | `None`, logged and skipped |

`build_channel_feed_config` emits the same dict shape `feeds.py` already consumes, so
`fetch_feed()` handles the rest.

### Two integration decisions

**X channels read the Twitter pool, not the network.** The Twitter pipeline is dual-source with
RSSHub primary — that's where images, quote-tweet detection, true post times and roughly 5× the
coverage of Google RSS come from (CLAUDE.md puts Google RSS at ~20% coverage). An independent
`site:x.com/…` query would fetch thin fallback data for handles already being fetched well.
So `fetch_subtext(pools=...)` receives the built `twitter_full_stream` and filters by handle.

**`internal` channels harvest already-fetched data for free.** The LEAP Blog is *already* a News
feed (`feeds.json:757`), so Bhargavi's posts arrive hourly today and simply aren't attributed.
Same for GTRI commentary via ET and her papers in the Papers pool. Scanning `pools` costs no
network and materially improves coverage.

### Article shape

Standard article dict plus five fields:

```python
{
  # ... title, link, date, source, publisher, description, source_url
  "person_id":    "tamal-bandyopadhyay",
  "person_name":  "Tamal Bandyopadhyay",
  "channel_kind": "owned",       # owned | discovered
  "channel_type": "x",           # x | google | blogger | internal
  "category":     "Subtext",
}
```

---

## Attribution: `is_authored_by()`

### The core observation

When Google matches `site:business-standard.com "Tamal Bandyopadhyay"`, it matched his name
*somewhere on the page* — and for his own column that somewhere is the **byline**, not the
headline.

> **A name in the title is evidence the piece is _about_ him. Its absence is evidence he _wrote_ it.**

Verified against the live feed. His top results — *"50 years of RRBs: A story of reform and
transformation in rural India"*, *"Why Banks Are Struggling For Deposits"*, *"Bank Boards:
Missing The Woods For The Trees?"*, *"The Story Behind Mis-selling"*, *"A quiet exodus: Why
young bankers are walking out of public sector banks"*, *"Much Ado About Tata Sons Listing?"* —
carry no name in the title, and all six are his. A naive "does the title mention him" filter
rejects every one.

### Algorithm

```
is_authored_by(person, article, channel):
    if channel.kind == "owned":                      → True   (structurally self-attributing)
    if channel.require_path and no path matches      → False  (hard gate, pre-scoring)
    if channel.require_terms and none present        → False  (hard gate, pre-scoring)
    return score(person, article) >= SUBTEXT_ACCEPT_SCORE
```

| Signal | Score |
|---|---|
| Signature phrase in title+description | +3 |
| Link contains an `author_slug` | +3 |
| Link path matches opinion/column/blog/views/analysis | +2 |
| No alias in title (byline-only match) | +1 |
| Alias in title | −2 |
| Alias in title **and** attribution verb (`says`, `said`, `told`, `warns`, `flags`, `argues`) | −3 |
| Interview framing (`in conversation`, `speaks to`, `Q&A`, `podcast`, `interview`) | −3 |
| About-the-person framing (`appointed`, `resigns`, `joins`, `slams`, `book review`, `profile of`) | −4 |

Accept at `score >= 1`. **Default is deny**, correct for authored-only.

All patterns and weights live in `config.py`, so tuning precision is a constant change, not a
refactor. Scores are computed once and attached as `_score` for logging.

### Known residual and its mitigation

A Business Standard *news* piece quoting Tamal in the body, headlined "RBI cuts repo rate",
scores +1 (no alias in title) and would slip through. Rather than patch this with heuristics,
it is handled declaratively: `require_path: ["/opinion/", "/columns/"]` rejects it before
scoring, because BS news lives at `/finance/` and `/industry/` while columns live at `/opinion/`.
Explicit, per-person, tunable without code.

### Audit trail

Rejected items are sampled to `static/subtext_rejected.json` (capped, with scores and the
deciding signal) for weekly review of filter drift — the same discipline Step 5 of
`docs/plans/2026-03-18-signal-quality-upgrade.md` asks for.

---

## Pipeline integration

Position: after Twitter lanes are built (so the pool exists), before `generate_html`.
Mirrors the `companies_fetcher` / `paper_fetcher` contract exactly.

```
fetch 232 feeds → filter → dedup → group
        ↓
   twitter lanes built (full_stream, high_signal)
        ↓
   fetch_subtext(pools={twitter, news, reports, papers})
        ├─ owned channels      → trusted, no filter
        ├─ discovered channels → require_path / require_terms gate, then score
        ├─ 14-day window (undated items kept, sorted last)
        ├─ dedup by normalised URL, then by (person_id, normalised title)
        ├─ cap SUBTEXT_MAX_PER_PERSON per person
        └─ live → cache | cache fallback | empty
        ↓
   generate_html(..., subtext_articles=...)
        ↓
   static/tab_subtext.json  +  static/subtext_cache.json
```

Cost: ~10–15 HTTP fetches on the existing 10-worker pool. Adds 5–10s to a multi-minute run.

`aggregator.py` changes:
- Import `fetch_subtext`, `load_subtext_cache`, `save_subtext_cache`
- Live-fetch-with-cache-fallback block (same shape as Companies, `aggregator.py:1490-1511`)
- `generate_html(...)` gains `subtext_articles=None`
- Serialise into `_tab_data["tab_subtext.json"]`
- New tab pill with count; `SUBTEXT_PEOPLE` JSON injected for chip rendering
- `export_published_snapshot` gains a `subtext` array (feeds the AI ranker later if wanted)

Deliberately **not** added to the footer `total_items` sum. That sum already omits Companies
(`aggregator.py:559`), and Subtext items are re-surfaced from other tabs, so adding them would
double-count. The pre-existing Companies omission is left alone — out of scope here.

### Config additions (`config.py`)

```python
SUBTEXT_FRESHNESS_DAYS   = 14
SUBTEXT_CACHE_FILE       = "static/subtext_cache.json"
SUBTEXT_REJECTED_FILE    = "static/subtext_rejected.json"
SUBTEXT_MAX_PER_PERSON   = 50
SUBTEXT_ACCEPT_SCORE     = 1
SUBTEXT_REJECTED_SAMPLE  = 100
SUBTEXT_OPINION_PATHS    = ("/opinion/", "/columns/", "/column/", "/blog/",
                            "/blogs/", "/views/", "/analysis/", "/commentary/")
SUBTEXT_ATTRIBUTION_VERBS = (
    "says", "said", "tells", "told", "warns", "warned", "flags", "flagged",
    "argues", "argued", "adds", "notes", "asks", "urges", "cautions",
    "according to", "quoted", "remarks",
)
SUBTEXT_INTERVIEW_PATTERNS = (
    "in conversation", "speaks to", "speaking to", "interview",
    "q&a", "podcast", "in an interview", "talks to", "fireside",
)
SUBTEXT_ABOUT_PATTERNS = (
    "appointed", "reappointed", "resigns", "resigned", "steps down",
    "joins", "quits", "slams", "responds to", "hits back",
    "book review", "profile of", "felicitated", "honoured", "awarded",
)
```

All three are matched case-insensitively against `title + " " + description`. The verb list is
only consulted when an alias is already present in the title — it distinguishes
"Sandeep Parekh **says** SEBI must reform" (about) from a headline that happens to contain a
common verb.

---

## Frontend

`templates/app.js` + `templates/style.css` (never `index.html` directly).

**Tab.** New pill labelled `Subtext` — the eighth *content* tab (ninth pill, since `All` is the
homepage), keyboard shortcut `8`, category dot `#8C4F5B` (burgundy —
checked for collision against all seven existing dots: `#4A8F7A` news, `#5E6A96` telegram,
`#9A8345` reports, `#7A6B8F` papers, `#A86565` youtube, `#4A8A9A` twitter, `#6E8B3D` companies).

**Layout.** Chronological river, newest first, 20/page. Each row:

```
● India-Peru FTA: what's actually on the table
  AJAY SRIVASTAVA · GTRI report · 1d
```

Person name in a small uppercase badge tinted by a per-person colour derived from `id`;
headline as the link; meta line `channel source · relative date`.

**Filter chips.** Reuse the `.company-chip-row` pattern from the Companies tab — already styled
and mobile-tested. Generated from `SUBTEXT_PEOPLE`, so a new person in `people.json` gets a chip
with no frontend change. `All` plus one chip per person, multi-select.

**Reused machinery.** `buildPagination`, `toggleGenericBookmark`, `ensureTabData` lazy-load,
`escapeHtml` / `escapeForAttr` / `sanitizeUrl` on every interpolation.

**Touch points.** `switchTab`, `ensureTabData`, `resetSubtextTabState`, `filterSubtext` into the
shared search path, the `window.__preloaded` list and `<link rel=preload>` set, the
keyboard-hint footer (`1`–`8`), and a line in the hand-edited `about.html`.

---

## Failure modes

Every failure degrades to fewer items. None can blank the tab or break the page.

| Failure | Behaviour |
|---|---|
| `people.json` missing or malformed | `[]` + warn; tab shows 0. Mirrors `load_feeds()` |
| Person entry missing required key | That person skipped + warn; others proceed |
| One channel throws | Per-channel try/except; siblings unaffected |
| All channels return nothing | `static/subtext_cache.json` fallback |
| Google News rate-limits / 403 | Existing proxy → curl → cache chain in `fetch_feed()` |
| Handle absent from Twitter pool | Falls back to a Google `site:x.com/…` query |
| `pools` not passed (standalone run) | `internal` channels no-op; network channels still work |
| Person has zero items | Chip shows 0; river has no empty headers by construction |
| Corrupt cache file | Treated as empty, rebuilt next run |

Attribution errs toward **false negatives** (missing a real column) over false positives
(admitting a story that merely quotes them), which suits authored-only. The rejected-items
log exists to catch over-filtering.

---

## Testing

`tests/test_subtext_fetcher.py`, ~30 tests:

- **`load_people`** — valid config; missing file; malformed JSON; person missing `id`/`name`/
  `channels`; `aliases` auto-includes `name`
- **`build_channel_feed_config`** — each of the four types produces the expected URL;
  `query_extra` appended; Blogger label percent-encoded; unknown type → `None`
- **`is_authored_by`** — the full scoring table, with the **six real Tamal headlines as
  fixtures** (must all pass) and quote/interview/appointment headlines (must all fail);
  `owned` bypass; `require_path` and `require_terms` hard gates; alias matching across
  transliterations
- **`scan_internal_pools`** — alias hit; miss; multi-pool; `require_terms` respected
- **Window and caps** — 14-day cutoff boundary; undated items retained and sorted last;
  `SUBTEXT_MAX_PER_PERSON` enforced per person, not globally
- **Dedup** — same URL across two channels collapses; same title different URL collapses
  within a person but not across people
- **Cache** — save/load round-trip preserves datetimes; corrupt file returns empty

Plus: `python3 -m py_compile` on changed modules, `node --check templates/app.js`, and the
full 168-test suite green.

---

## Files touched

| File | Change |
|---|---|
| `people.json` | **new** — five-person seed config |
| `subtext_fetcher.py` | **new** — ~300 lines |
| `tests/test_subtext_fetcher.py` | **new** — ~30 tests |
| `config.py` | +10 constants |
| `aggregator.py` | fetch block, `generate_html` param, tab pill, tab JSON, snapshot array |
| `templates/app.js` | render, filter, chips, pagination, tab wiring |
| `templates/style.css` | Subtext row + badge + chip styles |
| `about.html` | one line describing the section |
| `CLAUDE.md` | Subtext section, module map row, `people.json` conventions |

Generated (`index.html`, `static/tab_*.json`) regenerate via `python3 aggregator.py`.

---

## Deliberate deferrals

- **LLM by-vs-about classifier.** The scored heuristic ships first. If the rejected-items log
  shows the heuristic straining, a batch Gemini classifier is the natural upgrade and aligns
  with Step 5 of the signal-quality plan.
- **AI ranking of Subtext.** The snapshot gains a `subtext` array so `ai_ranker.py` *could*
  add a bucket later. Not wired now — the tab is chronological by design.
- **Homepage slider.** Tab only for v1.
- **Per-person RSS/email digests.** Out of scope.

## Risks

| Risk | Mitigation |
|---|---|
| Attribution over-filters, real columns vanish | Rejected-items log; scores in `config.py`; six real headlines as regression fixtures |
| Google News caps at 100 items/query | 14-day window is well inside the cap for all five |
| "Ajay Srivastava" is a common name (an ET Now markets commentator shares it) | `query_extra: "GTRI"` shapes the search; `require_terms` post-filters |
| Google News shape changes | Same dependency the existing Twitter fallback and WAF-proxied feeds already carry; cache absorbs outages |
| Ananth Narayan yields near-zero | Documented expectation, not a defect |
