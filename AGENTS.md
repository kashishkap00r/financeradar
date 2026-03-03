# Repository Guidelines

## Project Structure & Module Organization
- Core pipeline: `aggregator.py` (fetch, filter, dedupe, and HTML generation).
- Source/config inputs: `feeds.json`, `telegram_channels.json`, `config.py`.
- Data collectors and rankers: `telegram_fetcher.py`, `reports_fetcher.py`, `paper_fetcher.py`, `twitter_fetcher.py`, `ai_ranker.py`, `wsw_ranker.py`.
- Frontend sources: `templates/app.js`, `templates/style.css`; generated output: `index.html`.
- Generated datasets/caches: `static/*.json` (for example `articles.json`, `published_snapshot.json`).
- Tests: `tests/test_*.py` using Python `unittest`.
- CI/deployment: `.github/workflows/*.yml`; RSS proxy worker under `infra/rss-proxy/`.

## Build, Test, and Development Commands
- `python3 aggregator.py` — builds `index.html` and refreshes snapshots.
- `python3 telegram_fetcher.py` — updates Telegram feed data.
- `python3 ai_ranker.py` — writes AI picks from `static/articles.json`.
- `python3 -m unittest discover -s tests` — runs all tests.
- `python3 -m py_compile aggregator.py` — fast Python syntax check.
- `node --check templates/app.js` — fast JS syntax check.
- `python3 -m http.server 8000` — local preview at `http://localhost:8000`.

## Coding Style & Naming Conventions
- Python: 4-space indentation, `snake_case` functions/variables, `UPPER_SNAKE_CASE` constants.
- JS/CSS: follow existing patterns in `templates/` (`camelCase` JS helpers, kebab-case CSS classes).
- Prefer small, deterministic functions for parsing/filtering.
- Avoid manual edits to generated artifacts (`index.html`, most `static/*.json`) unless debugging generation output.

## Testing Guidelines
- Add tests in `tests/` with `test_*.py` names.
- For parser/fallback/date logic changes, include edge-case unit tests.
- Run full tests before opening a PR; no hard coverage gate, but new logic should be covered.

## Commit & Pull Request Guidelines
- Use concise imperative commits; preferred format: `type(scope): summary` (for example, `feat(home): add tab aggregation`).
- Reserve bot-style `Update news feeds` commits for automation output.
- PRs should include: change summary, reason, impact on workflows/data, validation commands, and UI screenshots (desktop + mobile) when relevant.

## Security & Configuration Tips
- Use environment variables for secrets (`OPENROUTER_API_KEY`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION`).
- Never commit tokens, session strings, or `.env` files.
