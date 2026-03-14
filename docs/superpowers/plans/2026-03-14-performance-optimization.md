# Performance Optimization: index.html 2.5MB → ~300KB

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce index.html from 2.5MB to ~300KB by externalizing CSS/JS as cacheable files and client-rendering the News tab from JSON.

**Architecture:** Currently 88% of index.html is 1417 pre-rendered `<article>` HTML cards. Every other tab already renders client-side from JSON. We align News to the same pattern: aggregator.py writes `static/tab_news.json` containing the article data, and app.js renders the cards on demand. CSS and JS become separate files cached by the browser across page loads.

**Tech Stack:** Python (aggregator.py), vanilla JS (app.js), CSS (style.css)

---

## Step 1: Externalize CSS + JS as cacheable files

### Task 1.1: Link CSS as external file instead of inlining

**Files:**
- Modify: `aggregator.py` (~lines 457-464) — replace inline `<style>` with `<link>`

- [ ] **Step 1: Edit aggregator.py**

Replace the CSS inlining block:
```python
    html += f"""    <style>
"""
    css_path = os.path.join(SCRIPT_DIR, "templates", "style.css")
    with open(css_path, "r", encoding="utf-8") as f:
        css_content = f.read()
    html += css_content
    html += f"""    </style>
```

With an external link:
```python
    html += f"""    <link rel="stylesheet" href="templates/style.css">
```

- [ ] **Step 2: Update about.html to also link to the shared CSS file**

The about page has its own inline CSS. For now, leave it as-is since it's a standalone page with its own styles. No change needed.

- [ ] **Step 3: Regenerate and verify**

Run: `python3 aggregator.py`
Open in browser, verify all styles render correctly.

- [ ] **Step 4: Commit**

```
git add aggregator.py index.html
git commit -m "Externalize CSS as cacheable file"
```

### Task 1.2: Link JS as external file instead of inlining

**Files:**
- Modify: `aggregator.py` (~lines 970-975) — replace inline JS read with `<script src>`

- [ ] **Step 1: Edit aggregator.py**

Replace the JS inlining block:
```python
    js_path = os.path.join(SCRIPT_DIR, "templates", "app.js")
    with open(js_path, "r", encoding="utf-8") as f:
        js_content = f.read()
    html += "\n" + js_content
    html += """    </script>
```

With an external script reference. The inline const declarations (ALL_PUBLISHERS, etc.) must stay inline since they contain dynamic data. Close the inline script first, then add the external one:
```python
    html += """
    </script>
    <script src="templates/app.js" defer></script>
```

- [ ] **Step 2: Regenerate and verify**

Run: `python3 aggregator.py`
Open in browser, verify all JS functionality works (tabs, search, bookmarks, sidebars).

- [ ] **Step 3: Commit**

```
git add aggregator.py index.html
git commit -m "Externalize JS as cacheable file"
```

---

## Step 2: Client-render News tab from JSON

This is the big one. Currently 1417 `<article>` cards are pre-rendered as HTML (~2.2MB). We move this to client-side rendering from a JSON file.

### Task 2.1: Write tab_news.json from aggregator.py

**Files:**
- Modify: `aggregator.py` — add news data to the tab JSON export block (~line 417)

The JSON needs these fields per article (matching what the HTML template uses):
- `title`, `link`, `source`, `source_url`, `description`, `publisher`
- `date` (ISO string for grouping/sorting)
- `time` (display string like "9:30 AM")
- `in_focus` (boolean)
- `related_sources` (array of `{name, link}` for "Also covered by")

- [ ] **Step 1: Add tab_news.json generation**

In the tab data export block (around line 417), add news data generation. This must use `sorted_groups` (not `sorted_articles`) to get related_sources:

```python
_news_items = []
for group in sorted_groups:
    article = group["primary"]
    local_dt = article.get("date")
    if local_dt and hasattr(local_dt, 'astimezone'):
        local_dt = local_dt.astimezone(IST)
    _news_items.append({
        "title": article["title"],
        "link": article["link"],
        "source": article["source"],
        "source_url": article.get("source_url", ""),
        "description": article.get("description", ""),
        "publisher": article.get("publisher", ""),
        "date": local_dt.isoformat() if local_dt else None,
        "time": local_dt.strftime("%I:%M %p").lstrip("0") if local_dt else "",
        "in_focus": bool(group["related_sources"]),
        "related_sources": [
            {"name": rs["name"], "link": rs["link"]}
            for rs in (group["related_sources"] or [])[:5]
        ],
    })
_tab_data["tab_news.json"] = _news_items
```

- [ ] **Step 2: Regenerate and verify tab_news.json exists**

Run: `python3 aggregator.py`
Check: `ls -lh static/tab_news.json` — should be ~500-700KB
Check: `python3 -c "import json; d=json.load(open('static/tab_news.json')); print(len(d), 'articles'); print(json.dumps(d[0], indent=2)[:300])"`

- [ ] **Step 3: Commit**

```
git add aggregator.py static/tab_news.json
git commit -m "Generate tab_news.json with full article data"
```

### Task 2.2: Add client-side news rendering in app.js

**Files:**
- Modify: `templates/app.js` — add `renderNewsFromJSON()` function

- [ ] **Step 1: Add the NEWS_ARTICLES variable and ensureTabData entry**

At the top of app.js near the other `let` declarations added for lazy loading, and in `ensureTabData`:

```javascript
// In the inline script block in aggregator.py, add:
let NEWS_ARTICLES = null;

// In ensureTabData function in app.js, add the 'news' case:
if (tab === 'news' && !NEWS_ARTICLES) {
    loads.push(loadTabData('news', 'static/tab_news.json').then(function(d) { NEWS_ARTICLES = d; }));
}
// Also add to 'home' tab's preloading block
```

- [ ] **Step 2: Write the renderNewsFromJSON function**

This replicates the HTML that aggregator.py currently generates. Add near the other `renderMain*` functions:

```javascript
function renderNewsFromJSON() {
    if (!NEWS_ARTICLES) return;
    var container = document.getElementById('news-list');
    if (!container) return;
    var html = '';
    var lastDateLabel = '';
    var now = new Date();
    var todayStr = now.toISOString().slice(0, 10);
    var yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    var yesterdayStr = yesterday.toISOString().slice(0, 10);

    NEWS_ARTICLES.forEach(function(a) {
        var dateStr = a.date ? a.date.slice(0, 10) : '';
        var dateLabel = '';
        if (dateStr === todayStr) dateLabel = 'Today';
        else if (dateStr === yesterdayStr) dateLabel = 'Yesterday';
        else if (a.date) {
            var d = new Date(a.date);
            var days = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
            var months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
            dateLabel = days[d.getDay()] + ', ' + months[d.getMonth()] + ' ' + String(d.getDate()).padStart(2, '0');
        }
        if (dateLabel && dateLabel !== lastDateLabel) {
            html += '<h2 class="date-header">' + escapeHtml(dateLabel) + '</h2>\n';
            lastDateLabel = dateLabel;
        }

        var sourceBadge = '';
        var alsoCovered = '';
        if (a.in_focus && a.related_sources && a.related_sources.length) {
            var total = a.related_sources.length + 1;
            sourceBadge = '<span class="source-badge">' + total + ' sources</span>';
            var links = a.related_sources.map(function(rs) {
                var name = escapeHtml(rs.name);
                var display = name.length > 25 ? name.slice(0, 25) + '...' : name;
                return '<a href="' + escapeForAttr(rs.link) + '" target="_blank" rel="noopener" title="' + name + '">' + display + '</a>';
            });
            alsoCovered = '<div class="also-covered">Also covered by: ' + links.join(', ') + '</div>';
        }

        var sourceDisplay = a.source.length > 35 ? escapeHtml(a.source.slice(0, 35)) + '...' : escapeHtml(a.source);
        var timeHtml = a.time ? '<span class="meta-dot">·</span><span class="article-time">' + escapeHtml(a.time) + '</span>' : '';

        html += '<article class="article" data-source="' + escapeForAttr(a.source.toLowerCase()) + '" data-date="' + escapeForAttr(dateStr) + '" data-url="' + escapeForAttr(a.link) + '" data-title="' + escapeForAttr(a.title) + '" data-in-focus="' + (a.in_focus ? 'true' : 'false') + '" data-publisher="' + escapeForAttr(a.publisher) + '">'
            + '<h3 class="article-title"><a href="' + escapeForAttr(a.link) + '" target="_blank" rel="noopener">' + escapeHtml(a.title) + '</a>' + sourceBadge + '</h3>'
            + '<div class="article-meta">'
            + '<a href="' + escapeForAttr(a.source_url) + '" target="_blank" class="source-tag" title="' + escapeForAttr(a.source) + '">' + sourceDisplay + '</a>'
            + timeHtml
            + '<span class="meta-dot">·</span>'
            + '<button class="bookmark-btn" onclick="toggleBookmark(this)" aria-label="Bookmark article" title="Bookmark">'
            + '<svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>'
            + '</button>'
            + '</div>'
            + alsoCovered
            + '</article>\n';
    });

    container.innerHTML = html;
    syncBookmarkState();
}
```

- [ ] **Step 3: Wire renderNewsFromJSON into switchTab**

In the `_doRender` function inside `switchTab`, change the `else` (news) branch:

```javascript
// Before:
} else {
    filterArticles();
}

// After:
} else {
    if (!newsRendered) {
        renderNewsFromJSON();
        newsRendered = true;
    }
    filterArticles();
}
```

Add `var newsRendered = false;` near the other `*Rendered` flags.

- [ ] **Step 4: Add NEWS_ARTICLES to ensureTabData**

In `ensureTabData`, add:
```javascript
if ((tab === 'news' || tab === 'home') && !NEWS_ARTICLES) {
    loads.push(loadTabData('news', 'static/tab_news.json').then(function(d) { NEWS_ARTICLES = d; }));
}
```

- [ ] **Step 5: Commit**

```
git add templates/app.js
git commit -m "Add client-side news rendering from JSON"
```

### Task 2.3: Remove pre-rendered article HTML from aggregator.py

**Files:**
- Modify: `aggregator.py` — remove the article generation loop (~lines 657-716)

- [ ] **Step 1: Replace the article HTML loop with empty container**

The current code loops through `sorted_groups` and generates `<article>` elements.
Replace the entire loop (from `for group in sorted_groups:` through the articles) with just the empty container div:

```python
# The news-list div should be empty — articles render client-side
html += '            <!-- Articles render client-side from tab_news.json -->\n'
```

Keep the `</div>` and pagination div that follow.

- [ ] **Step 2: Add NEWS_ARTICLES = null to inline script**

In the inline `<script>` const declarations, add:
```python
        let NEWS_ARTICLES = null;
```

- [ ] **Step 3: Regenerate and verify size**

Run: `python3 aggregator.py`
Check: `ls -lh index.html` — should be ~300-400KB
Open in browser, verify News tab renders correctly with date headers, in-focus badges, bookmark buttons.

- [ ] **Step 4: Test all tabs work**

Click through: All, News, Telegram, Reports, Papers, YouTube, Twitter.
Verify no JS console errors. Verify search works on News tab.

- [ ] **Step 5: Commit**

```
git add aggregator.py index.html static/tab_news.json
git commit -m "Remove pre-rendered news HTML: index.html 2.5MB → ~300KB"
```

---

## Step 3: Dead CSS cleanup

### Task 3.1: Find and remove unused CSS rules

**Files:**
- Modify: `templates/style.css`

- [ ] **Step 1: Audit CSS for rules targeting removed elements**

Search for CSS selectors that target elements/classes no longer in the HTML or JS:
- `.bookmarks-sidebar` — old sidebar class, replaced by `.bk-panel`
- `.util-btn` — removed utility bar buttons
- Any rules only used by the removed mobile menu (should be cleaned already)

- [ ] **Step 2: Remove confirmed dead rules**

Only remove rules where the selector has zero matches in: index.html, about.html, aggregator.py, app.js.

- [ ] **Step 3: Regenerate and verify styles**

Run: `python3 aggregator.py`
Visually verify all tabs, mobile view, about page still look correct.

- [ ] **Step 4: Commit**

```
git add templates/style.css index.html
git commit -m "Remove dead CSS rules"
```

---

## Final verification

- [ ] Check index.html file size (target: ~300KB raw, ~50KB gzipped)
- [ ] Test all 7 tabs render correctly
- [ ] Test mobile view (375px) — all tabs, search, bookmarks
- [ ] Test about page loads and links back to homepage
- [ ] Test homepage → about → homepage round-trip (should be fast)
- [ ] No JS console errors
- [ ] Push to remote
