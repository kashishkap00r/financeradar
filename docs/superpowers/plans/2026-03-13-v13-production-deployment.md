# V13 Homepage Production Deployment Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port V13 newspaper-style design from mockup (`mockups_v9_homepage.py`) into production (`aggregator.py` + `templates/style.css` + `templates/app.js`), preserving all existing features (dark mode, AI sidebar, WSW sidebar, bookmarks, mobile menu, live data pipeline).

**Architecture:** The V13 mockup is a standalone design artifact with static JSON data and a completely different page structure (masthead + utility bar + newspaper layouts). Production uses a top bar + sidebars + bento grid. We port V13's **visual design language** (typography, colors, spacing, card styles) and **tab view improvements** (filter bars, desk buttons, show more/less, telegram lightbox) into production's existing architecture. We do NOT replace production's top bar, sidebars, or mobile menu — we restyle them to match V13's aesthetic. The Home tab gets the biggest overhaul with V13's newspaper-style layouts.

**Tech Stack:** Python (aggregator.py f-strings), CSS (templates/style.css), vanilla JS (templates/app.js)

---

## Design Decisions (Locked In)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Fonts | Fraunces + Nunito Sans (V13) | This is the whole point of the redesign |
| Accent color | `#C45A35` rust (V13) | Warmer, more editorial feel |
| Dark mode | Must keep, adapt to V13 palette | Non-negotiable production feature |
| Top bar | Keep production's top bar, restyle | Sidebars (AI, WSW, Bookmarks) need their trigger buttons |
| Home tab | V13 newspaper layout (Pattern A/B/C/D + sliders + WSW breakers) | This is the hero feature of V13 |
| Tab views | Port V13's filter bars, desk buttons, show more/less | Better UX than current production |
| WSW | Keep sidebar overlay (production) + add inline breakers (V13) on Home tab | Both serve different purposes |
| AI Rankings | Keep sidebar (production) | V13 doesn't have an alternative |
| Mobile menu | Keep production's, restyle | V13 doesn't have mobile menu |
| Pagination | Keep production's per-tab pagination | V13's is simpler but production handles 1500+ articles |

## File Map

| File | Action | Scope |
|------|--------|-------|
| `templates/style.css` (~2982 lines) | **Heavy edit** | CSS variables, typography, card styles, new newspaper layouts, restyle existing components |
| `templates/app.js` (~3924 lines) | **Moderate edit** | Home tab rendering (newspaper layouts), show more/less clone detection, telegram lightbox, news desk buttons, filter bar improvements |
| `aggregator.py` (~1683 lines) | **Moderate edit** | HTML structure for Home tab, tab filter bars, font imports, data attributes |

---

## Chunk 1: CSS Design System + Typography

### Task 1: Update CSS Custom Properties

**Files:**
- Modify: `templates/style.css:1-70`

- [ ] **Step 1: Update light theme variables**

Replace root/light theme CSS variables with V13's design tokens:

```css
/* OLD */
--bg-primary: #ffffff;
--bg-secondary: #f8f9fa;
--bg-hover: #f1f3f5;
--text-primary: #1a1a2e;
--text-secondary: #4a4a68;
--text-muted: #8a8aa3;
--accent: #e14b4b;
--accent-hover: #c73b3b;
--accent-soft: #ffeceb;
--border: #e2e4e9;
--border-light: #d0d3da;

/* NEW (V13 mapped to production variable names) */
--bg-primary: #FAF7F2;
--bg-secondary: #FFFFFF;
--bg-hover: #F2EDE6;
--text-primary: #2C2825;
--text-secondary: #6B645C;
--text-muted: #9E978F;
--accent: #C45A35;
--accent-hover: #A84A2B;
--accent-soft: rgba(196, 90, 53, 0.1);
--border: #D4CBC0;
--border-light: #E2DCD3;
```

- [ ] **Step 2: Update dark theme variables**

Create a dark theme that complements V13's warm palette:

```css
/* Dark theme — warm charcoal adapted for V13 */
--bg-primary: #1A1614;
--bg-secondary: #221E1B;
--bg-hover: #2A2522;
--text-primary: #E8E2DA;
--text-secondary: #B0A89E;
--text-muted: #7D756B;
--accent: #D4703F;
--accent-hover: #E8854F;
--accent-soft: rgba(212, 112, 63, 0.18);
--border: #3A3430;
--border-light: #4A433E;
--card-shadow: 0 1px 3px rgba(0,0,0,0.25);
--danger: #E8854F;
```

- [ ] **Step 3: Run `python3 aggregator.py` and verify light + dark modes**

Run: `cd "/home/kashish.kapoor/vibecoding projects/financeradar" && python3 aggregator.py`
Expected: `index.html` regenerated, open in browser, verify both themes look cohesive.

- [ ] **Step 4: Commit**

```bash
git add templates/style.css
git commit -m "design: port V13 color palette to production CSS variables"
```

### Task 2: Update Font Imports

**Files:**
- Modify: `aggregator.py` (font preload + link tags in head)
- Modify: `templates/style.css` (font-family references)

- [ ] **Step 1: Update Google Fonts import in aggregator.py**

Find the font preload/link tags in `aggregator.py` head section and replace:

```python
# OLD: Merriweather + Source Sans Pro
# NEW: Fraunces + Nunito Sans
```

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,500;0,9..144,700;0,9..144,900;1,9..144,400;1,9..144,500&family=Nunito+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
```

- [ ] **Step 2: Update font-family references in style.css**

Find-replace across the file:
- `font-family: 'Merriweather'` → `font-family: 'Fraunces'` (and all variations)
- `font-family: 'Source Sans Pro'` → `font-family: 'Nunito Sans'` (and all variations)
- Also update the fallback stacks: `'Fraunces', Georgia, serif` and `'Nunito Sans', system-ui, sans-serif`

- [ ] **Step 3: Regenerate and verify typography**

Run: `python3 aggregator.py && python3 -m http.server 8000`
Expected: All headings use Fraunces, all body text uses Nunito Sans.

- [ ] **Step 4: Commit**

```bash
git add aggregator.py templates/style.css
git commit -m "design: switch typography to Fraunces + Nunito Sans (V13)"
```

### Task 3: Update Top Bar Styling

**Files:**
- Modify: `templates/style.css` (top bar section, ~lines 72-213)

The top bar stays structurally the same (brand, search, AI/WSW/Bookmarks/Theme buttons) but gets V13's visual treatment.

- [ ] **Step 1: Restyle top bar to match V13 utility bar aesthetic**

Key changes:
- Brand text: Use Fraunces, font-weight 900, remove red underline accent, add letter-spacing -0.03em
- Top bar background: Use `color-mix(in srgb, var(--bg-primary) 85%, transparent)` with backdrop-filter blur
- Button styles: Simpler, smaller (match V13's minimal utility-nav)
- Date display: Add uppercase, 0.78rem, letter-spacing 0.08em (V13's utility bar style)

```css
.top-bar {
  /* Add backdrop blur like V13 utility bar */
  background: color-mix(in srgb, var(--bg-primary) 85%, transparent);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.brand {
  font-family: 'Fraunces', Georgia, serif;
  font-weight: 900;
  letter-spacing: -0.03em;
}

/* Remove the red underline accent on brand */
.brand::after { display: none; }
```

- [ ] **Step 2: Add `color-mix()` fallback for older browsers**

```css
.top-bar {
  background: var(--bg-primary); /* fallback */
  background: color-mix(in srgb, var(--bg-primary) 85%, transparent);
}
```

- [ ] **Step 3: Verify top bar in both themes, both viewport sizes**

- [ ] **Step 4: Commit**

```bash
git add templates/style.css
git commit -m "design: restyle top bar with V13 utility bar aesthetic"
```

### Task 4: Update Card Styles for Tab Views

**Files:**
- Modify: `templates/style.css` (article cards, tweet cards, video cards, report cards)

- [ ] **Step 1: Update article card styles**

Port V13's `.tv-item` styling to production's `.article` class:
- Remove box-shadow hover (V13 uses opacity + transform)
- Border-bottom instead of full card border
- Tighter padding (0.85rem)
- Title: Fraunces, 0.95rem, font-weight 500, line-height 1.35
- Meta: 0.72rem, use `--text-muted`
- Source: font-weight 600, uppercase, letter-spacing 0.06em (V13's `.tv-item-source`)

- [ ] **Step 2: Update tweet card styles**

Port V13's `.tg-text-body` + `.tg-expand-btn` styles:
- Line-clamp: 4 lines with `max-height` fallback
- Show more/less button: 0.7rem, font-weight 600, accent color

- [ ] **Step 3: Update video card styles**

Port V13's `.tv-yt-item` thumbnail + body layout:
- Thumbnail: 180px width, 16:9 aspect-ratio, border-radius 3px
- Play button overlay on hover

- [ ] **Step 4: Update report card styles**

Port V13's `.tv-item` with type badges:
- `.tg-type-badge` for Report/Photo indicators
- Region badge styling

- [ ] **Step 5: Regenerate and test all tabs**

- [ ] **Step 6: Commit**

```bash
git add templates/style.css
git commit -m "design: port V13 card styles to all tab views"
```

---

## Chunk 2: Tab View Feature Ports

### Task 5: Port News Tab Filter Bar (Desk Buttons + In Focus)

**Files:**
- Modify: `aggregator.py` (HTML for news tab filter bar)
- Modify: `templates/style.css` (desk button styles)
- Modify: `templates/app.js` (desk button logic, publisher resolution)

- [ ] **Step 1: Add desk button HTML to news tab filter bar in aggregator.py**

In the news tab filter section, add desk buttons before the publisher dropdown:

```html
<button class="tv-desk-btn" data-desk="india-desk">India Desk</button>
<button class="tv-desk-btn" data-desk="world-desk">World Desk</button>
<button class="tv-desk-btn" data-desk="indie-voices">Indie Voices</button>
<button class="tv-desk-btn" data-desk="official-channels">Official Channels</button>
```

Remember: In aggregator.py f-strings, literal braces need doubling (`{{`, `}}`).

- [ ] **Step 2: Add desk button CSS**

Port from V13:
```css
.tv-desk-btn {
  padding: 0.35rem 0.7rem;
  border: 1.5px solid var(--border);
  border-radius: 3px;
  background: transparent;
  font-family: 'Nunito Sans', system-ui, sans-serif;
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
}
.tv-desk-btn:hover { border-color: var(--text-secondary); color: var(--text-primary); }
.tv-desk-btn.active {
  background: var(--text-primary);
  color: var(--bg-primary);
  border-color: var(--text-primary);
}
.tv-desk-btn.partial {
  border-color: var(--text-secondary);
  color: var(--text-primary);
  border-style: dashed;
}
```

- [ ] **Step 3: Add desk button JS logic**

Port `NEWS_DESKS` constant and `resolveDeskPubs()` function from V13 to app.js. Wire desk buttons to additive publisher toggle (3-state: inactive → partial → active).

Key logic:
- Click: resolve desk publishers from `ALL_PUBLISHERS`, toggle all on/off
- Visual: `.active` if all desk pubs selected, `.partial` if some selected, plain if none
- Must work with existing `selectedPublishers` Set and `filterArticles()` function

- [ ] **Step 4: Restyle In Focus button**

Port V13's `.tv-focus-btn` style (currently In Focus is an icon button in top bar — move it to news filter bar as a pill button with pulse dot).

- [ ] **Step 5: Test desk buttons + In Focus with real data**

Verify: India Desk selects only Indian publishers, World Desk selects only international ones. Both can be active simultaneously (additive). In Focus filters to multi-source articles.

- [ ] **Step 6: Commit**

```bash
git add aggregator.py templates/style.css templates/app.js
git commit -m "feat: port V13 news desk buttons and In Focus filter"
```

### Task 6: Port Show More/Less with Clone-Based Detection

**Files:**
- Modify: `templates/app.js` (show more/less logic for Telegram + Twitter)
- Modify: `templates/style.css` (`.tg-text-body`, `.tg-expand-btn` styles)

- [ ] **Step 1: Add CSS for expandable text**

```css
.tg-text-body {
  font-size: 0.85rem;
  line-height: 1.55;
  color: var(--text-secondary);
  margin-top: 0.3rem;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-height: calc(1.55em * 4);
  transition: all 0.2s ease;
}
.tg-text-body.expanded {
  -webkit-line-clamp: unset;
  max-height: 1000px;
  overflow: visible;
}
.tg-expand-btn {
  display: inline-block;
  margin-top: 0.25rem;
  font-family: 'Nunito Sans', system-ui, sans-serif;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--accent);
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
}
```

- [ ] **Step 2: Update Telegram/Twitter rendering in app.js**

For both `renderMainReports()` (Telegram tab) and `renderMainTwitter()` (Twitter tab), update the card HTML to include:
- `.tg-text-body` wrapper around text content
- Hidden `.tg-expand-btn` button after the text body

- [ ] **Step 3: Add clone-based overflow detection**

After rendering items, add `requestAnimationFrame` callback that measures each `.tg-text-body`:
```javascript
requestAnimationFrame(() => {
  container.querySelectorAll('.tg-text-body').forEach(el => {
    const btn = el.nextElementSibling;
    if (btn && btn.classList.contains('tg-expand-btn')) {
      const clampedH = el.clientHeight;
      const clone = el.cloneNode(true);
      clone.classList.add('expanded');
      clone.style.position = 'absolute';
      clone.style.visibility = 'hidden';
      clone.style.width = el.offsetWidth + 'px';
      el.parentNode.appendChild(clone);
      const naturalH = clone.scrollHeight;
      clone.remove();
      btn.style.display = naturalH > clampedH ? '' : 'none';
    }
  });
});
```

- [ ] **Step 4: Test with real Telegram data**

Open Telegram tab, verify:
- Long posts show "Show more" button
- Short posts don't show the button
- Clicking toggles between clamped and expanded
- "Show less" collapses back

- [ ] **Step 5: Commit**

```bash
git add templates/style.css templates/app.js
git commit -m "feat: port show more/less with clone-based overflow detection"
```

### Task 7: Port Telegram Image Lightbox

**Files:**
- Modify: `templates/app.js` (lightbox creation, navigation)
- Modify: `templates/style.css` (lightbox styles)

- [ ] **Step 1: Add lightbox CSS**

Port V13's `.tg-lightbox`, `.tg-lb-close`, `.tg-lb-nav`, `.tg-lb-counter`, `.tg-lb-error` styles.

- [ ] **Step 2: Add lightbox JS**

Port V13's `ensureTgLightbox()`, `showTgImg()`, `closeTgLightbox()`, `window.openTgLightbox()` functions.

Note: Production already has a report image lightbox. Make sure the Telegram lightbox doesn't conflict (use different variable names or integrate into existing lightbox).

- [ ] **Step 3: Add image thumbnail CSS**

Port `.tg-img-thumb`, `.tg-img-placeholder`, `.tg-img-badge` styles.

- [ ] **Step 4: Update Telegram card rendering to include image thumbnails**

In the Telegram tab rendering function, add image thumbnail HTML before the text body (matching V13's template).

- [ ] **Step 5: Test lightbox with real Telegram images**

Verify: Click thumbnail opens lightbox, navigation arrows work for multi-image posts, Escape closes, backdrop click closes.

- [ ] **Step 6: Commit**

```bash
git add templates/style.css templates/app.js
git commit -m "feat: port V13 telegram image lightbox"
```

### Task 8: Port Tab View Filter Bars

**Files:**
- Modify: `aggregator.py` (HTML for filter bars in each tab)
- Modify: `templates/style.css` (filter bar styles)

- [ ] **Step 1: Add V13 filter bar CSS**

Port `.tv-filter-bar`, `.tv-stats`, `.tv-updated`, `.tv-filters`, `.tv-preset` styles.

- [ ] **Step 2: Update filter bar HTML for each tab**

Each tab gets a consistent filter bar with:
- Stats line: `<strong class="tv-count">N</strong> items · <strong class="tv-pub-count">M</strong> sources · <span class="tv-updated">Updated X min ago</span>`
- Preset buttons (tab-specific)
- Publisher dropdown (existing, restyle)

Tabs and their presets:
- **Telegram**: All | Reports | Posts
- **Reports**: All | Indian | International
- **YouTube**: All | Traditional Media | Indie Voices | Educational
- **Twitter**: High Signal | Full Stream

- [ ] **Step 3: Verify filter bars work with existing JS**

Production already has preset buttons and dropdowns — verify the HTML class names match what JS expects.

- [ ] **Step 4: Commit**

```bash
git add aggregator.py templates/style.css
git commit -m "design: port V13 filter bar styling to all tabs"
```

---

## Chunk 3: Home Tab Newspaper Layout

This is the hero feature — replacing the bento grid Home tab with V13's newspaper-style layout.

### Task 9: Add Newspaper Layout CSS

**Files:**
- Modify: `templates/style.css` (add Pattern A/B/C/D + slider styles)

- [ ] **Step 1: Add Pattern A CSS (Lead Grid)**

```css
.pa-lead {
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 2.5rem;
  padding: 2rem 0 2.25rem;
  border-bottom: 1px solid var(--border);
}
.pa-sidebar {
  border-left: 1px solid var(--border);
  padding-left: 1.5rem;
}
.pa-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 2.5rem;
  padding: 1.5rem 0;
}
```

- [ ] **Step 2: Add Patterns B, C, D CSS**

Port all four patterns from V13 including responsive overrides at 768px (V13's breakpoint matches close enough to production's 640px — use 640px for consistency).

- [ ] **Step 3: Add hero/medium/compact card CSS**

Port `.card-hero`, `.card-medium`, `.card-compact` with V13's styling. These are DIFFERENT from existing `.article` cards — they're used only on the Home tab.

- [ ] **Step 4: Add slider section CSS**

Port `.slider-section`, `.slider-header`, `.slider-track`, `.slider-card`, plus type-specific slider cards (`.slider-yt`, `.slider-rp`, `.slider-tw`, `.slider-pp`).

- [ ] **Step 5: Add WSW breaker CSS**

Port `.wsw-breaker`, `.wsw-rule`, `.wsw-quote` styles.

- [ ] **Step 6: Add responsive overrides**

Ensure all new layouts collapse properly at 640px breakpoint.

- [ ] **Step 7: Commit**

```bash
git add templates/style.css
git commit -m "design: add V13 newspaper layout CSS (patterns A/B/C/D, sliders, WSW breakers)"
```

### Task 10: Rewrite Home Tab Rendering in app.js

**Files:**
- Modify: `templates/app.js` (replace `renderHomeTab()` function)

- [ ] **Step 1: Study current `renderHomeTab()` function**

Read the existing function to understand:
- What data sources it uses (articles, telegram, research, youtube, twitter)
- How it accesses global data constants
- How it integrates with bookmarks

- [ ] **Step 2: Plan the newspaper layout sections**

The Home tab should render:
1. **Pattern A** (hero + sidebar + grid) — top news articles
2. **WSW Breaker 1** — first WSW quote
3. **YouTube Slider** — latest videos
4. **WSW Breaker 2** — second WSW quote
5. **Pattern B** (inverted) — more news + telegram mix
6. **Reports Slider** — latest research reports
7. **WSW Breaker 3** — third WSW quote
8. **Pattern C** (asymmetric 2-col) — news + compact sidebar
9. **Twitter Slider** — latest tweets
10. **Pattern D** (hero + scroll container) — remaining articles
11. **Papers Slider** — latest papers

This matches V13's "All" tab layout exactly.

- [ ] **Step 3: Write new `renderHomeTab()` function**

Replace the existing bento grid renderer with the newspaper layout.

Key differences from V13 mockup:
- V13 uses `TAB_DATA[tab]` — production uses separate constants (`ALL_PUBLISHERS`, `TELEGRAM_REPORTS`, `YOUTUBE_VIDEOS`, etc.)
- WSW data comes from `wswData` (loaded via fetch), not static
- Bookmarks must use production's `toggleBookmark()`/`toggleGenericBookmark()` API, not V13's `bindBk()`
- Article data includes `related_sources` for "In Focus" / "Also covered by"

The function should:
1. Collect recent items from all data sources
2. Assign items to layout positions (hero, medium, compact) based on source count and recency
3. Build HTML for each pattern section
4. Render slider sections with horizontal scroll
5. Insert WSW breakers between sections
6. Bind bookmark buttons
7. Initialize slider navigation (prev/next arrows)

- [ ] **Step 4: Add slider navigation JS**

Port V13's slider arrow click handlers:
```javascript
function initSlider(trackId) {
  const track = document.getElementById(trackId);
  if (!track) return;
  const prevBtn = track.parentElement.querySelector('.slider-prev');
  const nextBtn = track.parentElement.querySelector('.slider-next');
  const scrollAmount = 320;
  prevBtn?.addEventListener('click', () => track.scrollBy({ left: -scrollAmount, behavior: 'smooth' }));
  nextBtn?.addEventListener('click', () => track.scrollBy({ left: scrollAmount, behavior: 'smooth' }));
}
```

- [ ] **Step 5: Test home tab with real data**

Verify:
- Pattern A shows hero article + 4 compact sidebar articles + 2-col medium grid
- YouTube slider scrolls horizontally
- WSW breakers show actual quotes from `wsw_clusters.json`
- All bookmark buttons work
- Mobile view collapses to single column

- [ ] **Step 6: Commit**

```bash
git add templates/app.js
git commit -m "feat: port V13 newspaper layout for Home tab"
```

### Task 11: Update Home Tab HTML Structure in aggregator.py

**Files:**
- Modify: `aggregator.py` (Home tab HTML container)

- [ ] **Step 1: Replace bento grid HTML with newspaper layout container**

The Home tab in `aggregator.py` currently has a hero card + bento grid with 5 home cards. Replace with a simpler container that JS will populate:

```html
<div class="tab-content active" data-tab="home" id="tab-home">
  <div id="home-newspaper"></div>
</div>
```

The JS `renderHomeTab()` function will build the full newspaper layout into `#home-newspaper`.

- [ ] **Step 2: Remove old bento grid HTML**

Delete the old home-hero-card, home-bento-grid, and all home-card-* elements.

- [ ] **Step 3: Regenerate and verify**

Run: `python3 aggregator.py && python3 -m http.server 8000`
Expected: Home tab renders newspaper layout with real data.

- [ ] **Step 4: Commit**

```bash
git add aggregator.py
git commit -m "refactor: replace Home tab bento grid with newspaper layout container"
```

---

## Chunk 4: Polish + Dark Mode Adaptation

### Task 12: Dark Mode for New Components

**Files:**
- Modify: `templates/style.css` (dark theme overrides for new V13 components)

- [ ] **Step 1: Add dark mode overrides for newspaper layouts**

Ensure all V13 components respect `[data-theme="dark"]`:
- Pattern grid borders use `var(--border)` ✓ (already variable-based)
- Slider section background: `color-mix(in srgb, var(--text-primary) 3%, var(--bg-primary))` → works in both themes
- WSW breaker dashed rule uses `var(--border)` ✓
- Card hover states use `var(--bg-hover)` ✓

- [ ] **Step 2: Fix `color-mix()` fallbacks**

V13 uses `color-mix()` in several places. Add fallbacks for Safari < 15.4:

```css
/* Fallback pattern */
.slider-section {
  background: var(--bg-secondary); /* fallback */
  background: color-mix(in srgb, var(--text-primary) 3%, var(--bg-primary));
}
```

- [ ] **Step 3: Test dark mode on all pages/tabs**

- [ ] **Step 4: Commit**

```bash
git add templates/style.css
git commit -m "design: dark mode adaptation for V13 newspaper components"
```

### Task 13: Port V13 Tab Bar Styling

**Files:**
- Modify: `templates/style.css` (tab bar styles)

- [ ] **Step 1: Decide: keep production tab style or port V13 pill style**

Production uses bottom-border indicator tabs. V13 uses pill-shaped tabs with filled active state.

**Decision: Port V13 pill style** — it's more distinctive and matches the editorial aesthetic.

Add tab pill styles alongside existing tab styles (or replace):
```css
.content-tab {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.85rem;
  border: 1.5px solid var(--border);
  border-radius: 3px;
  background: transparent;
  font-family: 'Nunito Sans', system-ui, sans-serif;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
}
.content-tab.active {
  background: var(--text-primary);
  color: var(--bg-primary);
  border-color: var(--text-primary);
}
```

- [ ] **Step 2: Add category color dots to tabs**

In `aggregator.py`, add `<span class="cat-dot" style="background:{COLOR}"></span>` to each tab button. Colors from V13:
- News: #4A8F7A
- Telegram: #5E6A96
- Reports: #9A8345
- YouTube: #A86565
- Twitter: #4A8A9A
- Papers: #7A6B8F

- [ ] **Step 3: Add tab count styling**

```css
.tab-count {
  font-size: 0.6rem;
  font-weight: 400;
  color: var(--text-muted);
  letter-spacing: normal;
  text-transform: none;
}
.content-tab.active .tab-count {
  color: color-mix(in srgb, var(--bg-primary) 70%, transparent);
}
```

- [ ] **Step 4: Verify tabs on desktop and mobile**

- [ ] **Step 5: Commit**

```bash
git add aggregator.py templates/style.css
git commit -m "design: port V13 pill-style tab bar with category dots"
```

### Task 14: Update Footer

**Files:**
- Modify: `aggregator.py` (footer HTML)
- Modify: `templates/style.css` (footer styles)

- [ ] **Step 1: Port V13 footer style**

```css
footer {
  padding: 2.5rem 0 3rem;
  border-top: 1.5px solid var(--text-primary);
  text-align: center;
}
.foot-stats {
  font-size: 0.78rem;
  color: var(--text-secondary);
  margin-bottom: 0.75rem;
}
.foot-nav {
  display: flex;
  justify-content: center;
  gap: 1.75rem;
}
.foot-nav a {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-secondary);
  text-decoration: none;
}
```

- [ ] **Step 2: Commit**

```bash
git add aggregator.py templates/style.css
git commit -m "design: port V13 footer styling"
```

### Task 15: Tab Fade-In Animation

**Files:**
- Modify: `templates/style.css` (tab content animation)

- [ ] **Step 1: Add V13's tab fade-in**

```css
.tab-content { display: none; }
.tab-content.active {
  display: block;
  animation: tabFadeIn 0.45s cubic-bezier(0.25, 0.1, 0.25, 1);
}
@keyframes tabFadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
```

Note: Production already has opacity fade-in on body load. Make sure tab animation doesn't conflict.

- [ ] **Step 2: Commit**

```bash
git add templates/style.css
git commit -m "design: add V13 tab fade-in animation"
```

---

## Chunk 5: Dropdown Styling + Pagination + Scroll-to-Top

### Task 16: Port V13 Dropdown Styling

**Files:**
- Modify: `templates/style.css` (publisher dropdown styles)

- [ ] **Step 1: Update dropdown styles to match V13**

Port `.tv-dropdown`, `.tv-dropdown-trigger`, `.tv-dropdown-panel`, `.tv-dropdown-search`, `.tv-dropdown-list`, `.tv-dd-item` styles.

Key changes from current production:
- Border-radius: 4px (vs 9px)
- Font: Nunito Sans, 0.78rem
- Accent checkbox color: `accent-color: var(--accent)`
- Panel width: 280px
- Max-height: 360px

- [ ] **Step 2: Verify dropdowns work on all tabs**

- [ ] **Step 3: Commit**

```bash
git add templates/style.css
git commit -m "design: port V13 dropdown styling"
```

### Task 17: Port V13 Pagination Styling

**Files:**
- Modify: `templates/style.css` (pagination styles)

- [ ] **Step 1: Update pagination button styles**

Port `.tv-pagination`, `.tv-pg-btn`, `.tv-pg-dots` styles from V13.

- [ ] **Step 2: Verify pagination on News tab (1500+ articles)**

- [ ] **Step 3: Commit**

```bash
git add templates/style.css
git commit -m "design: port V13 pagination styling"
```

### Task 18: Port V13 Scroll-to-Top Button

**Files:**
- Modify: `templates/style.css` (scroll-to-top button)

- [ ] **Step 1: Update scroll-to-top styling**

Port V13's `.scroll-top` style (38px circle, `var(--text-primary)` background, `var(--bg-primary)` color).

- [ ] **Step 2: Commit**

```bash
git add templates/style.css
git commit -m "design: port V13 scroll-to-top button style"
```

---

## Chunk 6: Final Integration + Verification

### Task 19: Full Regeneration and Smoke Test

- [ ] **Step 1: Run full pipeline**

```bash
cd "/home/kashish.kapoor/vibecoding projects/financeradar"
python3 aggregator.py
python3 -m http.server 8000
```

- [ ] **Step 2: Verify all tabs load correctly**

Open each tab: Home, News, Telegram, Reports, Papers, YouTube, Twitter

- [ ] **Step 3: Verify dark mode**

Toggle theme — all components should look correct in both themes.

- [ ] **Step 4: Verify sidebars**

- AI Rankings sidebar opens, shows rankings, source pills work
- WSW sidebar opens, shows clusters, bookmarks work
- Bookmarks sidebar opens, can add/remove bookmarks

- [ ] **Step 5: Verify mobile view (640px)**

- Tab bar scrolls horizontally
- Newspaper layouts collapse to single column
- Mobile menu works
- Sidebars are full-width

- [ ] **Step 6: Verify Home tab newspaper layout**

- Pattern A/B/C/D render with real articles
- Sliders scroll with arrows
- WSW breakers show real quotes
- Bookmark buttons work on all card types

- [ ] **Step 7: Verify News tab desk buttons**

- India Desk, World Desk, etc. filter correctly
- In Focus toggle works
- Three-state visual (active/partial/inactive)

- [ ] **Step 8: Verify Show more/less**

- Telegram tab: long posts show "Show more"
- Twitter tab: long tweets show "Show more"
- Short content does NOT show the button

- [ ] **Step 9: Verify keyboard shortcuts**

H=Home, 1-6=tabs, J/K=navigate, /=search, Escape=clear

### Task 20: Final Commit + Push

- [ ] **Step 1: Run tests**

```bash
python3 -m unittest discover -s tests
```

- [ ] **Step 2: Commit any remaining changes**

- [ ] **Step 3: Push to remote**

```bash
git push origin main
```

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Font loading delay (Fraunces is heavier than Merriweather) | FOUT flash | Keep existing font-display:swap + opacity:1 timeout |
| `color-mix()` not supported in Safari < 15.4 | Broken backgrounds | Add solid-color fallbacks everywhere |
| Newspaper layout breaks with < 7 articles | Empty sections | JS should gracefully degrade to fewer pattern sections |
| Home tab JS render is slow with 1500+ articles | Noticeable delay | Only use recent articles for Home (top 50-100 per source) |
| Dark mode colors look wrong | Poor readability | Test extensively, iterate on dark theme variables |
| Existing bookmark URLs stored in localStorage won't match | Lost bookmarks | No action needed — URLs don't change, only visual styling |
| Production's 7 tabs vs V13's 7 tabs alignment | Tab order confusion | V13 "All" → Prod "Home", rest match |
