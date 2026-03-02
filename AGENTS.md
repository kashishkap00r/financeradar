# Repository Guidelines

## Project Structure & Module Organization
FinanceRadar is a Python-first static site generator. Core pipeline logic lives in `aggregator.py`, with focused modules such as `feeds.py`, `filters.py`, `articles.py`, `reports_fetcher.py`, `telegram_fetcher.py`, `ai_ranker.py`, and `wsw_ranker.py`. Frontend source files are `templates/app.js` and `templates/style.css`; they are injected into generated `index.html`. Tests live in `tests/` (`test_*.py`). Automation is under `.github/workflows/`. Planning notes go in `docs/plans/`.

## Build, Test, and Development Commands
- `python3 aggregator.py`: run the main pipeline and regenerate site/data artifacts.
- `python3 telegram_fetcher.py`: refresh Telegram report data (public channels without MTProto creds).
- `GEMINI_API_KEY=... OPENROUTER_API_KEY=... python3 ai_ranker.py`: regenerate AI rankings.
- `python3 -m unittest discover -s tests`: run the unit test suite.
- `python3 -m http.server 8000`: serve locally and preview at `http://localhost:8000`.

## Coding Style & Naming Conventions
Use Python 3.8+ style with 4-space indentation, `snake_case` for functions/variables, and `UPPER_CASE` for constants. Keep feed/source identifiers lowercase and hyphenated in JSON configs (for example, `et-bfsi-articles`). Prefer editing `templates/*` for UI changes; do not hand-edit generated artifacts. If frontend logic must be changed in `aggregator.py` f-strings, remember literal braces require `{{` and `}}`.

## Testing Guidelines
The project uses `unittest`. Add or update tests in `tests/test_*.py` with descriptive names (for example, `test_filters_political_names`). Any parser, filter, ranking, or routing change should include a regression test. Run targeted tests during iteration (for example, `python3 -m unittest tests.test_filters`) and full discovery before pushing.

## Commit & Pull Request Guidelines
Follow existing history: short, imperative commit subjects (`Improve mobile navigation`, `Update news feeds`). Keep behavior changes and generated-data refreshes logically separated when possible. PRs should include: scope summary, files/modules affected, test commands run, and screenshots for UI/mobile changes. Mention regenerated artifacts explicitly.

## LLM Handoff Guidelines
Use this file as the canonical handoff reference. In every handoff, include: what changed, why, exact commands run, test results, generated files touched, unresolved risks, and required env vars/secrets (`TELEGRAM_*`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`). For major work, add a dated design/decision note in `docs/plans/`.
