"""V11: REFINED EDITORIAL RIVER — uniform cards, title case, bookmark icons,
subtle Zerodha-inspired decorative elements, WSW items flow inline."""
from __future__ import annotations
import html as h
import json, re
from pathlib import Path
from collections import defaultdict

PROJECT = Path('/home/kashish.kapoor/vibecoding projects/financeradar')
STATIC = PROJECT / 'static'
OUT = PROJECT / 'docs' / 'plans' / 'assets' / 'from-scratch-explorations'

# ── Title case helper (smarter than str.title) ──
SMALL_WORDS = {'a','an','the','and','but','or','nor','for','yet','so',
               'in','on','at','to','by','of','up','as','is','it','if',
               'vs','via','from','with','into','than','per'}

def title_case(s):
    """Title Case with small-word exceptions."""
    s = str(s or '').strip()
    if not s:
        return s
    words = s.split()
    result = []
    for i, w in enumerate(words):
        # Always capitalize first and last word
        if i == 0 or i == len(words)-1:
            result.append(w.capitalize())
        elif w.lower() in SMALL_WORDS:
            result.append(w.lower())
        else:
            result.append(w.capitalize())
    return ' '.join(result)

def sentence_case(s):
    """Sentence case: capitalize first letter, rest lowercase (preserve proper nouns as-is)."""
    s = str(s or '').strip()
    if not s:
        return s
    # Just capitalize first char, leave rest as-is (to preserve proper nouns like India, RBI etc.)
    return s[0].upper() + s[1:]

def load():
    ai_raw = json.loads((STATIC / 'ai_rankings.json').read_text())
    picks = []
    for prov_name, prov in ai_raw.get('providers',{}).items():
        for bucket, items in prov.get('buckets',{}).items():
            for item in items:
                item['_bucket'] = bucket
                picks.append(item)
        break

    by_rank = defaultdict(list)
    for p in picks:
        by_rank[p.get('rank', 99)].append(p)
    ordered = []
    for r in sorted(by_rank.keys()):
        ordered.extend(by_rank[r])

    wsw_raw = json.loads((STATIC / 'wsw_clusters.json').read_text())
    wsw = []
    for prov in wsw_raw.get('providers',{}).values():
        wsw = prov.get('clusters',[])[:5]
        break

    return dict(picks=ordered, wsw=wsw)

def e(s): return h.escape(str(s or ''), quote=True)
def crop(s, n=160):
    s = str(s or '').strip()
    return s if len(s) <= n else s[:n-1].rstrip() + '\u2026'

# ── SVG bookmark icon (Feather-style, 2px stroke) ──
BOOKMARK_SVG = '<svg class="bookmark-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>'

def build_html(picks, wsw):
    # Interleave WSW items into the stream naturally
    # Insert a WSW item every ~12 regular items
    stream = []
    wsw_idx = 0
    decorative_idx = 0

    for i, p in enumerate(picks):
        stream.append(('item', p))

        # Insert WSW after every 12 items
        if (i + 1) % 12 == 0 and wsw_idx < len(wsw):
            stream.append(('wsw', wsw[wsw_idx]))
            wsw_idx += 1

        # Insert decorative breaker every 8 items (offset from WSW)
        if (i + 1) % 8 == 0 and (i + 1) % 12 != 0:
            decorative_idx += 1
            stream.append(('deco', decorative_idx))

    # ── Render ──
    parts = []
    item_count = 0
    prev_was_special = False

    for entry_type, data in stream:
        if entry_type == 'item':
            item_count += 1
            p = data
            title = e(title_case(p.get('title', '')))
            url = e(p.get('url', ''))
            source = e(p.get('source', ''))
            why = e(sentence_case(crop(p.get('why_it_matters', ''), 180)))
            signal = e(p.get('signal_type', ''))

            # First item gets slightly larger treatment (hero)
            if item_count == 1:
                parts.append(f'''
    <article class="card card-hero">
      <div class="card-top">
        <span class="card-source">{source}</span>
        <button class="btn-bookmark" aria-label="Bookmark">{BOOKMARK_SVG}</button>
      </div>
      <h2 class="card-title"><a href="{url}" target="_blank">{title}</a></h2>
      {f'<p class="card-desc">{why}</p>' if why else ''}
      {f'<span class="card-signal">{signal}</span>' if signal else ''}
    </article>''')
            else:
                parts.append(f'''
    <article class="card">
      <div class="card-top">
        <span class="card-source">{source}</span>
        <button class="btn-bookmark" aria-label="Bookmark">{BOOKMARK_SVG}</button>
      </div>
      <h3 class="card-title"><a href="{url}" target="_blank">{title}</a></h3>
      {f'<p class="card-desc">{why}</p>' if why else ''}
      {f'<span class="card-signal">{signal}</span>' if signal else ''}
    </article>''')

        elif entry_type == 'wsw':
            cl = data
            cl_title = e(title_case(cl.get('cluster_title', '')))
            cl_summary = e(sentence_case(crop(cl.get('summary', ''), 200)))
            # Render as a regular-looking card but with an italic pull-quote feel
            parts.append(f'''
    <aside class="card card-quote">
      <div class="card-top">
        <span class="card-source">Voices</span>
      </div>
      <h3 class="card-title"><em>{cl_title}</em></h3>
      {f'<p class="card-desc">{cl_summary}</p>' if cl_summary else ''}
    </aside>''')

        elif entry_type == 'deco':
            # Alternate between decorative breaker styles
            n = data % 3
            if n == 1:
                # Dashed line with dot
                parts.append('''
    <div class="deco deco-dash">
      <span class="deco-dot"></span>
    </div>''')
            elif n == 2:
                # Dot grid
                parts.append('''
    <div class="deco deco-dots">
      <span></span><span></span><span></span><span></span><span></span>
      <span></span><span></span><span></span><span></span><span></span>
      <span></span><span></span><span></span><span></span><span></span>
    </div>''')
            else:
                # Small arrow + dashed line
                parts.append('''
    <div class="deco deco-arrow">
      <span class="deco-dot"></span>
      <svg width="10" height="10" viewBox="0 0 10 10"><polygon points="0,0 10,5 0,10" fill="var(--accent)"/></svg>
    </div>''')

    body = '\n'.join(parts)

    return f'''<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>V11 — Refined Editorial River</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400&family=DM+Sans:wght@400;500;600&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

:root {{
  --bg: #f9f6f1;
  --surface: #ffffff;
  --ink: #1a1714;
  --muted: #8a7e72;
  --faint: #c4bdb4;
  --line: #ddd7ce;
  --accent: #b84c2a;
  --dot: #FFA412;
  --serif: 'Cormorant Garamond', Georgia, serif;
  --sans: 'DM Sans', system-ui, sans-serif;
  --mono: 'Space Mono', monospace;
}}
[data-theme="dark"] {{
  --bg: #110f0d;
  --surface: #1a1714;
  --ink: #e8e0d6;
  --muted: #8a7e72;
  --faint: #4a4238;
  --line: #2e2820;
  --accent: #d4734e;
  --dot: #FFA412;
}}

html {{ background: var(--bg); color: var(--ink); }}
body {{
  max-width: 680px;
  margin: 0 auto;
  padding: 0 24px;
  font-family: var(--sans);
  font-size: 15px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}}

/* ═══ Masthead ═══ */
.masthead {{
  text-align: center;
  padding: 40px 0 0;
}}
.masthead .date {{
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
}}
.masthead h1 {{
  font-family: var(--serif);
  font-size: 42px;
  font-weight: 400;
  font-style: italic;
  letter-spacing: -0.02em;
  margin: 6px 0 0;
}}
.rule {{ border: none; border-top: 2px solid var(--ink); margin: 16px 0 0; }}
.rule-thin {{ border: none; border-top: 1px solid var(--line); margin: 3px 0 0; }}

/* ═══ Nav ═══ */
nav {{
  display: flex;
  justify-content: center;
  gap: 20px;
  padding: 14px 0;
  border-bottom: 1px solid var(--line);
}}
nav a {{
  font-family: var(--sans);
  font-size: 14px;
  font-weight: 500;
  color: var(--muted);
  text-decoration: none;
}}
nav a:hover {{ color: var(--ink); }}
nav a.active {{ color: var(--ink); font-weight: 600; }}
nav .dot {{ color: var(--faint); font-size: 10px; }}

.actions {{
  display: flex;
  justify-content: center;
  gap: 16px;
  padding: 10px 0 0;
}}
.actions button {{
  background: none;
  border: none;
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  cursor: pointer;
}}
.actions button:hover {{ color: var(--ink); }}

/* ═══ Cards (uniform) ═══ */
.card {{
  padding: 28px 0;
  border-bottom: 1px solid var(--line);
}}
.card-top {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}}
.card-source {{
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}}
.btn-bookmark {{
  background: none;
  border: none;
  color: var(--faint);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: color 0.15s;
  display: flex;
  align-items: center;
}}
.btn-bookmark:hover {{
  color: var(--accent);
}}
.btn-bookmark.active {{
  color: var(--accent);
}}
.btn-bookmark .bookmark-icon {{
  display: block;
}}

.card-title {{
  font-family: var(--serif);
  font-size: 20px;
  font-weight: 400;
  line-height: 1.3;
}}
.card-title a {{
  color: var(--ink);
  text-decoration: none;
}}
.card-title a:hover {{
  color: var(--accent);
}}
.card-desc {{
  margin-top: 8px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--muted);
}}
.card-signal {{
  display: inline-block;
  margin-top: 8px;
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.06em;
  color: var(--faint);
  border: 1px solid var(--line);
  padding: 2px 6px;
  border-radius: 2px;
}}

/* ═══ Hero (first card only — slightly larger title) ═══ */
.card-hero .card-title {{
  font-size: 30px;
  line-height: 1.2;
}}
.card-hero {{
  padding: 36px 0;
}}

/* ═══ Quote cards (WSW inline) ═══ */
.card-quote .card-title {{
  font-style: italic;
}}
.card-quote {{
  border-left: 3px solid var(--accent);
  padding-left: 20px;
  margin-left: 0;
}}

/* ═══ Decorative breakers (Zerodha-inspired) ═══ */
.deco {{
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 0;
  gap: 8px;
}}
.deco-dot {{
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--dot);
  display: inline-block;
}}

/* Dashed line with dot */
.deco-dash {{
  gap: 12px;
}}
.deco-dash::before,
.deco-dash::after {{
  content: '';
  flex: 1;
  height: 0;
  border-top: 1.5px dashed var(--faint);
}}

/* Dot grid */
.deco-dots {{
  display: grid;
  grid-template-columns: repeat(5, 6px);
  gap: 8px;
  justify-content: center;
  padding: 20px 0;
}}
.deco-dots span {{
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--faint);
  opacity: 0.5;
}}
.deco-dots span:nth-child(3),
.deco-dots span:nth-child(8),
.deco-dots span:nth-child(13) {{
  background: var(--dot);
  opacity: 1;
}}

/* Arrow + dashed line */
.deco-arrow {{
  gap: 6px;
}}
.deco-arrow::before {{
  content: '';
  flex: 1;
  height: 0;
  border-top: 1.5px dashed var(--faint);
}}
.deco-arrow::after {{
  content: '';
  flex: 1;
  height: 0;
  border-top: 1.5px dashed var(--faint);
}}

/* ═══ Footer ═══ */
footer {{
  padding: 48px 0 64px;
  text-align: center;
}}
footer .logo {{
  font-family: var(--serif);
  font-size: 18px;
  font-style: italic;
  color: var(--faint);
  margin-bottom: 6px;
}}
footer .count {{
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--faint);
}}

/* ═══ Scrollbar ═══ */
::-webkit-scrollbar {{ width: 5px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: var(--line); border-radius: 3px; }}
</style>
</head>
<body>

<div class="masthead">
  <div class="date">Wednesday, 12 March 2026</div>
  <h1>Finance Radar</h1>
</div>
<hr class="rule">
<hr class="rule-thin">

<nav>
  <a class="active">Home</a><span class="dot">&middot;</span>
  <a>News</a><span class="dot">&middot;</span>
  <a>Telegram</a><span class="dot">&middot;</span>
  <a>Reports</a><span class="dot">&middot;</span>
  <a>YouTube</a><span class="dot">&middot;</span>
  <a>Twitter</a>
</nav>
<div class="actions">
  <button>AI Rankings</button>
  <button>Bookmarks</button>
  <button onclick="document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark'">Theme</button>
</div>

<main>
{body}
</main>

<footer>
  <div class="logo">Finance Radar</div>
  <div class="count">{len(picks)} curated picks</div>
</footer>

<script>
// Bookmark toggle
document.querySelectorAll('.btn-bookmark').forEach(btn => {{
  btn.addEventListener('click', () => {{
    btn.classList.toggle('active');
    const icon = btn.querySelector('.bookmark-icon');
    if (btn.classList.contains('active')) {{
      icon.setAttribute('fill', 'currentColor');
    }} else {{
      icon.setAttribute('fill', 'none');
    }}
  }});
}});
</script>

</body>
</html>'''


def main():
    data = load()
    out_dir = OUT / 'v11-refined-river'
    out_dir.mkdir(parents=True, exist_ok=True)
    html = build_html(data['picks'], data['wsw'])
    (out_dir / 'home.html').write_text(html)
    print(f"wrote v11-refined-river/home.html ({len(data['picks'])} picks)")

if __name__ == '__main__':
    main()
