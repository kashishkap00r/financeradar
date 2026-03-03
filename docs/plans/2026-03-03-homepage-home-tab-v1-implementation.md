# FinanceRadar Home Tab V1 Implementation

## Scope
Implemented a new `Home` tab that aggregates all content sections into a single premium-light overview while preserving the existing FinanceRadar color system.

## What Was Added
- `Home` tab added as the first tab in the tab strip.
- `Home` tab layout includes:
  - AI hero strip (`AI Picks`) with provider/bucket-aware content.
  - Six section blocks with `View More` actions:
    - News
    - Telegram
    - Reports
    - Papers
    - YouTube
    - Twitter
- Home search behavior (`Search home highlights...`) filters Home cards/hero content.

## Behavior Rules Implemented
- First-visit behavior:
  - First time after rollout in a browser profile opens `Home`.
  - Controlled by `localStorage` key: `financeradar_home_seen`.
- Existing last-tab memory remains active after first visit.
- Home `View More` behavior:
  - Opens target tab in clean default state.
  - Resets search + target tab filters/pagination/lane state.
- Direct tab clicks still preserve/resume tab state as before.

## Keyboard Mapping
- Updated numeric shortcuts:
  - `1` Home
  - `2` News
  - `3` Telegram
  - `4` Reports
  - `5` Papers
  - `6` YouTube
  - `7` Twitter

## Technical Notes
- HTML shell updated in `aggregator.py`.
- Home rendering/state logic implemented in `templates/app.js`.
- Premium-light home styling implemented in `templates/style.css`.
- Added token `--accent-soft` to support consistent accent surfaces across themes.

## Validation Checklist
- [ ] Home tab visible and selectable.
- [ ] First visit opens Home once.
- [ ] Subsequent visits follow last-tab memory.
- [ ] Home search filters Home cards.
- [ ] `View More` resets target tab state and navigates correctly.
- [ ] Direct tab click resumes previous state.
- [ ] Keyboard shortcuts `1..7` map correctly.
