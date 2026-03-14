"""V9: CALM RIVER — one unified card style, generous whitespace, long editorial scroll."""
from __future__ import annotations
import html as h
import json
from pathlib import Path

PROJECT = Path('/home/kashish.kapoor/vibecoding projects/financeradar')
STATIC = PROJECT / 'static'
OUT = PROJECT / 'docs' / 'plans' / 'assets' / 'from-scratch-explorations'

def load():
    ai_raw = json.loads((STATIC / 'ai_rankings.json').read_text())
    picks = []
    for prov_name, prov in ai_raw.get('providers',{}).items():
        for bucket, items in prov.get('buckets',{}).items():
            for item in items:
                item['_bucket'] = bucket
                picks.append(item)
        break
    picks.sort(key=lambda x: x.get('rank', 99))

    wsw_raw = json.loads((STATIC / 'wsw_clusters.json').read_text())
    wsw = []
    for prov in wsw_raw.get('providers',{}).values():
        wsw = prov.get('clusters',[])[:6]
        break

    return dict(picks=picks, wsw=wsw)

def e(s): return h.escape(str(s or ''), quote=True)

def html_page(picks, wsw):
    # Interleave: round-robin by rank across buckets
    from collections import defaultdict
    by_rank = defaultdict(list)
    for p in picks:
        by_rank[p.get('rank', 99)].append(p)
    ordered = []
    for r in sorted(by_rank.keys()):
        ordered.extend(by_rank[r])

    cards_html = []
    wsw_idx = 0
    for i, p in enumerate(ordered):
        title = e(p.get('title',''))
        link = e(p.get('url',''))
        source = e(p.get('source',''))
        reason = e(p.get('why_it_matters',''))
        bucket = p.get('_bucket','news')
        signal = p.get('signal_type','')

        # Tiny source-type hint
        type_label = {'telegram':'TG','twitter':'TW','youtube':'YT','reports':'RPT'}.get(bucket,'')

        # Hero treatment for very first item only
        if i == 0:
            cards_html.append(f'''
            <article class="item hero">
              <div class="item-rank">1</div>
              <h2><a href="{link}" target="_blank">{title}</a></h2>
              <div class="item-meta">
                <span class="item-source">{source}</span>
                {f'<span class="item-type">{type_label}</span>' if type_label else ''}
                {f'<span class="item-tag">{e(signal)}</span>' if signal else ''}
              </div>
              {f'<p class="item-reason">{reason}</p>' if reason else ''}
            </article>''')
        else:
            cards_html.append(f'''
            <article class="item">
              <div class="item-rank">{i+1}</div>
              <div class="item-body">
                <h3><a href="{link}" target="_blank">{title}</a></h3>
                <div class="item-meta">
                  <span class="item-source">{source}</span>
                  {f'<span class="item-type">{type_label}</span>' if type_label else ''}
                  {f'<span class="item-tag">{e(signal)}</span>' if signal else ''}
                </div>
                {f'<p class="item-reason">{reason}</p>' if reason else ''}
              </div>
            </article>''')

        # WSW breather every 15 items
        if (i+1) % 15 == 0 and wsw_idx < len(wsw):
            cl = wsw[wsw_idx]
            wsw_idx += 1
            cl_title = e(cl.get('cluster_title',''))
            cl_summary = e(cl.get('summary',''))
            cl_topic = e(cl.get('topic',''))
            cards_html.append(f'''
            <aside class="wsw-break">
              <div class="wsw-label">Who Said What <span class="wsw-topic">— {cl_topic}</span></div>
              <h2 class="wsw-title">{cl_title}</h2>
              <p class="wsw-summary">{cl_summary}</p>
            </aside>''')

    items_html = '\n'.join(cards_html)

    return f'''<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>V9 — Calm River</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Sans:wght@400;500&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin:0; padding:0; }}

:root {{
  --bg: #fefefe;
  --surface: #f7f7f5;
  --ink: #111111;
  --muted: #777777;
  --faint: #bbbbbb;
  --line: #e8e8e8;
  --accent: #111111;
  --serif: 'Instrument Serif', Georgia, serif;
  --sans: 'DM Sans', system-ui, sans-serif;
  --mono: 'Space Mono', monospace;
}}
[data-theme="dark"] {{
  --bg: #0c0c0c;
  --surface: #151515;
  --ink: #e8e8e8;
  --muted: #888888;
  --faint: #444444;
  --line: #222222;
  --accent: #e8e8e8;
}}

html {{ background: var(--bg); color: var(--ink); }}
body {{
  max-width: 720px;
  margin: 0 auto;
  padding: 0 24px;
  font-family: var(--sans);
  font-size: 15px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}}

/* ─── Top bar ─── */
header {{
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 32px 0 12px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 8px;
}}
.logo {{
  font-family: var(--serif);
  font-size: 22px;
  font-style: italic;
  color: var(--ink);
  letter-spacing: -0.02em;
}}
.top-actions {{
  display: flex;
  gap: 16px;
}}
.top-actions button {{
  background: none;
  border: none;
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  color: var(--muted);
  cursor: pointer;
  text-transform: uppercase;
}}
.top-actions button:hover {{ color: var(--ink); }}

/* ─── Tabs ─── */
nav {{
  display: flex;
  gap: 28px;
  padding: 14px 0 20px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 48px;
}}
nav a {{
  font-family: var(--sans);
  font-size: 14px;
  font-weight: 500;
  color: var(--muted);
  text-decoration: none;
  transition: color 0.15s;
}}
nav a:hover {{ color: var(--ink); }}
nav a.active {{
  color: var(--ink);
  text-decoration: underline;
  text-underline-offset: 6px;
  text-decoration-thickness: 1.5px;
}}

/* ─── Hero (rank 1) ─── */
.item.hero {{
  margin-bottom: 56px;
  padding-bottom: 48px;
  border-bottom: 1px solid var(--line);
  position: relative;
}}
.item.hero .item-rank {{
  font-family: var(--serif);
  font-size: 120px;
  color: var(--line);
  position: absolute;
  right: 0;
  top: -24px;
  line-height: 1;
  pointer-events: none;
  z-index: 0;
}}
.item.hero h2 {{
  font-family: var(--serif);
  font-size: 38px;
  line-height: 1.15;
  font-weight: 400;
  max-width: 580px;
  position: relative;
  z-index: 1;
}}
.item.hero h2 a {{
  color: var(--ink);
  text-decoration: none;
}}
.item.hero h2 a:hover {{
  text-decoration: underline;
  text-underline-offset: 4px;
  text-decoration-thickness: 1px;
}}
.item.hero .item-meta {{
  margin-top: 12px;
  position: relative;
  z-index: 1;
}}
.item.hero .item-reason {{
  margin-top: 16px;
  max-width: 540px;
  color: var(--muted);
  font-size: 15px;
  line-height: 1.6;
  position: relative;
  z-index: 1;
}}

/* ─── Regular items ─── */
.item {{
  display: flex;
  gap: 20px;
  align-items: flex-start;
  padding: 28px 0;
  border-bottom: 1px solid var(--line);
}}
.item .item-rank {{
  font-family: var(--serif);
  font-size: 32px;
  color: var(--faint);
  min-width: 40px;
  text-align: right;
  line-height: 1;
  padding-top: 4px;
  flex-shrink: 0;
}}
.item .item-body {{
  flex: 1;
  min-width: 0;
}}
.item h3 {{
  font-family: var(--serif);
  font-size: 19px;
  font-weight: 400;
  line-height: 1.35;
}}
.item h3 a {{
  color: var(--ink);
  text-decoration: none;
}}
.item h3 a:hover {{
  text-decoration: underline;
  text-underline-offset: 3px;
  text-decoration-thickness: 1px;
}}

/* ─── Meta line ─── */
.item-meta {{
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted);
}}
.item-source {{
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}}
.item-type {{
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--faint);
  border: 1px solid var(--line);
  padding: 1px 5px;
  border-radius: 2px;
}}
.item-tag {{
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.05em;
  color: var(--faint);
}}
.item-reason {{
  margin-top: 8px;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.55;
}}

/* ─── WSW breather ─── */
.wsw-break {{
  margin: 56px 0;
  padding: 40px 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}}
.wsw-label {{
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--faint);
  margin-bottom: 12px;
}}
.wsw-topic {{
  color: var(--muted);
}}
.wsw-title {{
  font-family: var(--serif);
  font-size: 24px;
  font-weight: 400;
  line-height: 1.3;
  margin-bottom: 10px;
}}
.wsw-summary {{
  color: var(--muted);
  font-size: 14px;
  line-height: 1.6;
  max-width: 600px;
  font-style: italic;
}}

/* ─── Footer ─── */
footer {{
  padding: 48px 0 64px;
  text-align: center;
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--faint);
}}

/* ─── Scrollbar ─── */
::-webkit-scrollbar {{ width: 6px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: var(--line); border-radius: 3px; }}
</style>
</head>
<body>

<header>
  <div class="logo">Finance Radar</div>
  <div class="top-actions">
    <button onclick="document.documentElement.dataset.theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'">Theme</button>
  </div>
</header>

<nav>
  <a href="#" class="active">Home</a>
  <a href="#">News</a>
  <a href="#">Telegram</a>
  <a href="#">Reports</a>
  <a href="#">YouTube</a>
  <a href="#">Twitter</a>
</nav>

<main>
{items_html}
</main>

<footer>Finance Radar · {len(picks)} AI picks · Calm River</footer>

</body>
</html>'''


def main():
    data = load()
    out_dir = OUT / 'v9-calm-river'
    out_dir.mkdir(parents=True, exist_ok=True)
    html = html_page(data['picks'], data['wsw'])
    (out_dir / 'home.html').write_text(html)
    print(f"wrote v9-calm-river/home.html ({len(data['picks'])} picks)")

if __name__ == '__main__':
    main()
