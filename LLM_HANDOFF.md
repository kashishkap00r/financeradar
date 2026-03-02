# LLM Handoff

This repository now uses [`AGENTS.md`](./AGENTS.md) as the canonical contributor and handoff guide.

## How to Handoff
Before ending a task, capture these items in your final update:
- What changed and why.
- Exact commands run (build/test/preview).
- Test status and any known gaps.
- Generated artifacts touched (`index.html`, files in `static/`).
- Required env vars or secrets (`TELEGRAM_*`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`).
- Open risks, blockers, or TODOs.

## For Larger Changes
Add a dated design/decision note in `docs/plans/` and reference it in the handoff.
