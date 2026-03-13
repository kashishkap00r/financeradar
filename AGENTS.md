# Repository Guidelines

## Project Structure & Module Organization
`aggregator.py` is the main pipeline: it fetches feeds, filters and groups stories, and renders the homepage. Supporting data collectors and rankers live beside it, including `telegram_fetcher.py`, `reports_fetcher.py`, `twitter_fetcher.py`, `paper_fetcher.py`, `ai_ranker.py`, and `wsw_ranker.py`. Frontend source belongs in `templates/app.js` and `templates/style.css`; checked-in outputs are `index.html` and `static/*.json`. Tests live in `tests/test_*.py`. Audit helpers are under `auditor/`, GitHub Actions under `.github/workflows/`, and the RSS proxy Worker under `infra/rss-proxy/`.

## Build, Test, and Development Commands
- `python3 aggregator.py` regenerates the homepage and core JSON snapshots from configured feeds.
- `python3 telegram_fetcher.py` refreshes Telegram report data.
- `OPENROUTER_API_KEY=... python3 ai_ranker.py` rebuilds AI picks; add other required API env vars if your local setup uses them.
- `python3 -m unittest discover -s tests` runs the full test suite.
- `python3 -m unittest tests.test_filters` runs one targeted module while iterating.
- `python3 -m py_compile aggregator.py && node --check templates/app.js` performs quick Python and JS syntax checks.
- `python3 -m http.server 8000` serves a local preview at `http://localhost:8000`.

## Coding Style & Naming Conventions
Use Python 3.8+ with 4-space indentation, `snake_case` for functions and variables, and `UPPER_CASE` for constants. Keep feed or channel IDs lowercase-hyphenated in JSON, for example `et-bfsi-articles`. For UI work, edit `templates/*` first and regenerate outputs rather than treating `index.html` as source. When editing embedded HTML, CSS, or JS inside Python f-strings, escape literal braces as `{{` and `}}`.

## Testing Guidelines
Use `unittest` and add regression coverage in `tests/test_*.py` for parser, filtering, ranking, or rendering changes. Run the smallest relevant test module while developing, then run full discovery before review. For UI-only tweaks, still run syntax checks and any tests touching the affected data flow.

## Commit & Pull Request Guidelines
Recent history favors short, imperative commit subjects such as `Update news feeds`, `Show mobile bookmarks in header`, and `Restyle mobile quick actions`. Keep logic changes separate from feed refreshes or generated-content churn when practical. Pull requests should summarize user-visible impact, list commands run, call out regenerated artifacts, and include desktop/mobile screenshots for UI changes.

## Security & Configuration Tips
Do not commit secrets such as `TELEGRAM_SESSION`, `TELEGRAM_API_HASH`, `OPENROUTER_API_KEY`, or `GEMINI_API_KEY`. Prefer environment variables or GitHub repository secrets. If you change proxy infrastructure, review host restrictions in `infra/rss-proxy/wrangler.toml` before deploying.
