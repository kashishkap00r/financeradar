# Repository Guidelines

## Project Structure & Module Organization
FinanceRadar is a Python-based static aggregator. Core orchestration is in `aggregator.py`. Data collection and transformation are split across focused modules such as `feeds.py`, `telegram_fetcher.py`, `twitter_fetcher.py`, `reports_fetcher.py`, `paper_fetcher.py`, `filters.py`, and `articles.py`.  
UI source lives in `templates/app.js` and `templates/style.css`; these are injected into generated `index.html`.  
Runtime outputs and caches are in `static/` (for example `articles.json`, `published_snapshot.json`, `youtube_cache.json`).  
Tests are under `tests/` with `test_*.py` naming. CI/CD lives in `.github/workflows/`. Cloudflare RSS proxy code is in `infra/rss-proxy/`.

## Build, Test, and Development Commands
- `pip install -r requirements.txt` — install Python dependencies.
- `python3 aggregator.py` — run full aggregation and regenerate site artifacts.
- `python3 telegram_fetcher.py` — refresh Telegram reports data.
- `python3 ai_ranker.py && python3 wsw_ranker.py` — rebuild AI ranking outputs.
- `python3 -m unittest discover -s tests` — run all unit tests.
- `python3 -m http.server 8000` — preview locally at `http://localhost:8000`.
- `cd infra/rss-proxy && npx wrangler deploy` — deploy RSS proxy worker.

## Coding Style & Naming Conventions
Use Python 3.8+ with 4-space indentation and `snake_case` for functions/variables; keep constants in `UPPER_CASE`.  
Prefer small, single-purpose functions and explicit logging for fallbacks/retries.  
For feed IDs and source keys, use lowercase, hyphenated names (example: `yt-norges-bank-im`).  
Frontend changes should be made in `templates/*`, not by manually editing generated `index.html`.

## Testing Guidelines
Testing uses `unittest`. Add regression tests for parser, filtering, dedupe, ranking, and fallback behavior changes.  
Name tests descriptively (example: `test_youtube_dedupes_duplicate_urls`).  
Run targeted tests during development, then run full discovery before opening a PR.

## Commit & Pull Request Guidelines
Follow existing commit style: concise, imperative, and scoped when useful (examples: `Telegram: ...`, `YouTube: ...`, `Update news feeds`).  
PRs should include:
- Summary of behavior changes
- Files/modules touched
- Commands run (tests/scripts)
- Screenshots for UI changes
- Any required secret/config updates

## Security & Configuration Tips
Never commit secrets. Use GitHub Actions secrets for `TELEGRAM_*`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, and optional Cloudflare keys.  
When changing feed/network logic, preserve safe URL handling and existing proxy fallback behavior.
