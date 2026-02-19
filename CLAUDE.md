# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

**Full codebase documentation is in `README.md`** — architecture, data flow, key files, internals, deployment, and customization all live there.

## Quick Commands

```bash
python3 aggregator.py                          # Regenerate index.html + static/articles.json
python3 telegram_fetcher.py                    # Fetch Telegram reports (HTML channels only without creds)
TELEGRAM_API_ID="..." TELEGRAM_API_HASH="..." TELEGRAM_SESSION="..." python3 telegram_fetcher.py
OPENROUTER_API_KEY="sk-or-..." python3 ai_ranker.py
python3 -m http.server 8000                    # Preview locally
```

## Critical Rules

- **Never hand-edit** `index.html`, `static/articles.json`, `static/telegram_reports.json`, `static/youtube_cache.json`, `static/ai_rankings.json` — all are generated.
- When rebasing, always `git checkout --theirs` for the generated files above, then re-run `python3 aggregator.py`.
- The entire frontend (HTML/CSS/JS) lives inside `generate_html()` in `aggregator.py` as one f-string. Edit there, then regenerate.
- Content filters live in `filters.py` — add patterns there, no other changes needed.
