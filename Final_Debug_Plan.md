# Final Debug Plan

Code review findings. To be worked on incrementally.

---

## Top Findings (Ranked by Severity)

1. **Single-file monolith is the primary systemic risk**
   `aggregator.py` is 5,078 lines and contains feed ingestion, normalization, filtering, dedupe, grouping, HTML templating, and a massive inlined frontend JS/CSS blob (`aggregator.py:493`, `aggregator.py:4872`).
   Any non-trivial change has a high blast radius. Classic god-object architecture.

2. **No safety net for changes (no tests at all)**
   No unit, integration, or E2E test files. Core logic (date parsing, dedupe, filtering, ranking mapping, Telegram parsing, UI rendering) is unprotected.

3. **TLS certificate verification is explicitly disabled**
   `aggregator.py:27-29` and `telegram_fetcher.py:32-34` disable cert verification globally.
   High-severity integrity/security risk: MITM or poisoned content can enter the pipeline.

4. **Untrusted feed URLs rendered into `<a href>` without scheme allowlisting**
   Link values from feeds are HTML-escaped but not protocol-validated (`aggregator.py:2706`, `aggregator.py:4146`, `aggregator.py:4766`).
   `javascript:` / `data:` URLs are not blocked → XSS risk via upstream content.

5. **AI output parsing is heuristic and can silently degrade correctness**
   Best-effort JSON extraction (`ai_ranker.py:175-195`, `wsw_ranker.py:216-250`) and fuzzy title matching (`ai_ranker.py:160-172`, `ai_ranker.py:299-302`) can produce plausible-but-wrong mappings.

6. **Error handling tolerates partial failure without hard fail or alerting**
   Multiple paths convert hard failures into warnings and proceed (`telegram_fetcher.py:401-406`, `telegram_fetcher.py:521-530`, `ai_ranker.py:317-320`).
   System can "look green" while missing chunks of data.

7. **Operational correctness drift already visible**
   Freshness logic is 5 days (`aggregator.py:5039`) but log says ">10 days" (`aggregator.py:5058`). Concrete sign of drift.

8. **Frontend state logic is duplicated/inconsistent in generated JS**
   `isBookmarked` defined twice (`aggregator.py:3380-3382`, `aggregator.py:3652-3655`). `safeStorage` exists but bookmarks still call `localStorage` directly (`aggregator.py:3365-3377`).

9. **Telegram HTML parsing depends on unstable DOM shape**
   Parser tightly coupled to Telegram markup classes and manual state flags (`telegram_fetcher.py:47-188`, `telegram_fetcher.py:257-260`). Upstream markup changes can silently drop data.

10. **CI/release flow is fragile**
    AI workflow validates only `GEMINI_API_KEY` but still calls OpenRouter, so partial success is normal. Both workflows do `git pull --rebase` under concurrent auto-commits (`hourly.yml:55`, `ai-ranking.yml:51`), which is brittle.

---

## Risk Heatmap

| Category | Risk Level |
|---|---|
| Architecture & Structure | High |
| Test Quality & Coverage | High |
| Change Safety & Fragility | High |
| Error Handling & Failure Modes | High |
| Security | High |
| Observability & Monitoring | High |
| Technical Debt & Smells | High |
| Performance & Scalability | Medium-High |
| Dependency Risk | Medium |
| Bus Factor | High |

---

## What Could Cause a Production Outage

1. Telegram markup changes break parser → report ingestion silently empty
2. Feed provider anti-bot or schema changes → cascading fetch failures
3. CI `git pull --rebase` conflicts under frequent auto-commits → updates blocked
4. AI provider API changes/limits → ranking jobs fail or produce unusable output
5. Malformed upstream feed entry → parse failures in critical paths

## What Could Cause Silent Data Corruption

1. Heuristic JSON recovery + fuzzy title matching in AI ranking
2. Date parse fallback accepting invalid/naive timestamps inconsistently
3. URL normalization/dedupe heuristics collapsing distinct links
4. Partial source failures treated as warnings → incomplete datasets presented as normal
5. Telegram parser extracting wrong fields when DOM shifts slightly

---

## 30-Day Fix Priority Order

- [ ] 1. Split `aggregator.py` into modules: ingestion, normalization, filtering, clustering, rendering
- [ ] 2. Add minimum viable tests: date parsing, filter rules, clustering, AI parser contracts, Telegram parsing fixtures
- [ ] 3. Re-enable TLS verification; add explicit per-source exceptions instead of global disable
- [ ] 4. Add URL scheme allowlist (`http`/`https`) before writing any `href`
- [ ] 5. Add strict schema validation for all generated JSON artifacts
- [ ] 6. Convert warning-based partial failure into policy-based failure thresholds in CI
- [ ] 7. Add structured logging + basic metrics (per-source success rate, item counts, parse failures)
- [ ] 8. Externalize constants/magic numbers into config
- [ ] 9. Break generated JS into logically separated templates/modules before embedding
- [ ] 10. Pin GitHub Actions by commit SHA; harden workflow secret validation for all used providers
