"""V10: EDITORIAL RIVER — warm broadsheet aesthetic, long scroll with layout rhythm.
Unified card style but varied layout zones: hero, 2-col pairs, full-width pull-quotes,
3-col clusters, WSW breakers. The variety comes from COMPOSITION not from category colors."""
from __future__ import annotations
import html as h
import json
from pathlib import Path
from collections import defaultdict

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

    # Interleave by rank
    by_rank = defaultdict(list)
    for p in picks:
        by_rank[p.get('rank', 99)].append(p)
    ordered = []
    for r in sorted(by_rank.keys()):
        ordered.extend(by_rank[r])

    wsw_raw = json.loads((STATIC / 'wsw_clusters.json').read_text())
    wsw = []
    for prov in wsw_raw.get('providers',{}).values():
        wsw = prov.get('clusters',[])[:6]
        break

    return dict(picks=ordered, wsw=wsw)

def e(s): return h.escape(str(s or ''), quote=True)
def crop(s, n=120):
    s = str(s or '').strip()
    return s if len(s) <= n else s[:n-1].rstrip() + '\u2026'

def build_html(picks, wsw):
    # Split picks into layout zones:
    # Zone A: Hero (1 item)
    # Zone B: Two-col pair (2 items)
    # Zone C: Three compact rows (3 items)
    # Zone D: Pull-quote / wide feature (1 item)
    # Zone E: Three-col cluster (3 items)
    # Zone F: WSW breaker
    # Then repeat pattern...

    zones = []
    idx = 0
    wsw_idx = 0
    cycle = 0

    while idx < len(picks):
        if cycle == 0 and idx < len(picks):
            # HERO — first item gets big treatment
            zones.append(('hero', [picks[idx]]))
            idx += 1
        elif cycle % 5 == 1 and idx + 1 < len(picks):
            # TWO-COL pair
            zones.append(('pair', picks[idx:idx+2]))
            idx += 2
        elif cycle % 5 == 2 and idx + 2 < len(picks):
            # THREE compact rows
            zones.append(('rows', picks[idx:idx+3]))
            idx += 3
        elif cycle % 5 == 3 and idx < len(picks):
            # PULL-QUOTE / wide feature
            zones.append(('wide', [picks[idx]]))
            idx += 1
            # Insert WSW breaker after wide items
            if wsw_idx < len(wsw):
                zones.append(('wsw', [wsw[wsw_idx]]))
                wsw_idx += 1
        elif cycle % 5 == 4 and idx + 2 < len(picks):
            # THREE-COL cluster
            zones.append(('trio', picks[idx:idx+3]))
            idx += 3
        elif cycle % 5 == 0 and cycle > 0 and idx < len(picks):
            # FEATURE — another wide one to reset rhythm
            zones.append(('feature', [picks[idx]]))
            idx += 1
        else:
            # Fallback: single row
            zones.append(('rows', [picks[idx]]))
            idx += 1
        cycle += 1

    # Remaining WSW at end
    while wsw_idx < len(wsw):
        zones.append(('wsw', [wsw[wsw_idx]]))
        wsw_idx += 1

    # Render zones
    html_parts = []
    item_num = 0

    for ztype, items in zones:
        if ztype == 'hero':
            p = items[0]
            item_num += 1
            html_parts.append(f'''
    <section class="zone-hero">
      <div class="hero-kicker">{e(p.get('source',''))}</div>
      <h1><a href="{e(p.get('url',''))}" target="_blank">{e(p.get('title',''))}</a></h1>
      <p class="hero-why">{e(p.get('why_it_matters',''))}</p>
      <div class="hero-meta">
        <span class="signal">{e(p.get('signal_type',''))}</span>
      </div>
    </section>''')

        elif ztype == 'pair':
            left = items[0]
            right = items[1] if len(items) > 1 else None
            item_num += 1
            left_html = f'''
        <div class="pair-card">
          <h3><a href="{e(left.get('url',''))}" target="_blank">{e(crop(left.get('title',''), 90))}</a></h3>
          <div class="pair-meta"><span class="src">{e(left.get('source',''))}</span></div>
          <p class="pair-why">{e(crop(left.get('why_it_matters',''), 160))}</p>
        </div>'''
            right_html = ''
            if right:
                item_num += 1
                right_html = f'''
        <div class="pair-card">
          <h3><a href="{e(right.get('url',''))}" target="_blank">{e(crop(right.get('title',''), 90))}</a></h3>
          <div class="pair-meta"><span class="src">{e(right.get('source',''))}</span></div>
          <p class="pair-why">{e(crop(right.get('why_it_matters',''), 160))}</p>
        </div>'''
            html_parts.append(f'''
    <section class="zone-pair">
      {left_html}
      <div class="pair-rule"></div>
      {right_html}
    </section>''')

        elif ztype == 'rows':
            rows = ''
            for p in items:
                item_num += 1
                rows += f'''
        <div class="row-item">
          <span class="row-num">{item_num}</span>
          <div class="row-body">
            <a href="{e(p.get('url',''))}" target="_blank">{e(crop(p.get('title',''), 100))}</a>
            <span class="row-src">{e(p.get('source',''))}</span>
          </div>
        </div>'''
            html_parts.append(f'''
    <section class="zone-rows">{rows}
    </section>''')

        elif ztype in ('wide', 'feature'):
            p = items[0]
            item_num += 1
            html_parts.append(f'''
    <section class="zone-wide">
      <div class="wide-num">{item_num}</div>
      <blockquote class="wide-title">
        <a href="{e(p.get('url',''))}" target="_blank">{e(p.get('title',''))}</a>
      </blockquote>
      <div class="wide-footer">
        <span class="wide-src">{e(p.get('source',''))}</span>
        <span class="wide-signal">{e(p.get('signal_type',''))}</span>
      </div>
      <p class="wide-why">{e(crop(p.get('why_it_matters',''), 200))}</p>
    </section>''')

        elif ztype == 'trio':
            cards = ''
            for p in items:
                item_num += 1
                cards += f'''
        <div class="trio-card">
          <div class="trio-num">{item_num}</div>
          <h3><a href="{e(p.get('url',''))}" target="_blank">{e(crop(p.get('title',''), 80))}</a></h3>
          <span class="trio-src">{e(p.get('source',''))}</span>
        </div>'''
            html_parts.append(f'''
    <section class="zone-trio">{cards}
    </section>''')

        elif ztype == 'wsw':
            cl = items[0]
            # Build voices list
            voices = ''
            for v in cl.get('voices', [])[:3]:
                speaker = e(v.get('speaker',''))
                quote = e(crop(v.get('quote',''), 120))
                voices += f'<div class="wsw-voice"><span class="wsw-speaker">{speaker}</span><p>"{quote}"</p></div>'
            html_parts.append(f'''
    <section class="zone-wsw">
      <div class="wsw-label">Who Said What</div>
      <h2 class="wsw-title">{e(cl.get('cluster_title',''))}</h2>
      <p class="wsw-summary">{e(crop(cl.get('summary',''), 180))}</p>
      <div class="wsw-voices">{voices}</div>
    </section>''')

    body_content = '\n'.join(html_parts)

    return f'''<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>V10 — Editorial River</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400&family=Instrument+Serif:ital@0;1&family=Space+Mono:wght@400;700&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
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
  --serif: 'Cormorant Garamond', 'Instrument Serif', Georgia, serif;
  --display: 'Instrument Serif', 'Cormorant Garamond', Georgia, serif;
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
}}

html {{ background: var(--bg); color: var(--ink); }}
body {{
  max-width: 860px;
  margin: 0 auto;
  padding: 0 32px;
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
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted);
}}
.masthead h1 {{
  font-family: var(--display);
  font-size: 48px;
  font-weight: 400;
  font-style: italic;
  letter-spacing: -0.02em;
  margin: 6px 0 0;
}}
.masthead-rule {{
  border: none;
  border-top: 2.5px solid var(--ink);
  margin: 18px 0 0;
}}
.masthead-rule-thin {{
  border: none;
  border-top: 1px solid var(--line);
  margin: 4px 0 0;
}}

/* ═══ Nav ═══ */
nav {{
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 20px;
  padding: 14px 0;
  border-bottom: 1px solid var(--line);
  margin-bottom: 0;
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

/* ═══ ZONE: Hero ═══ */
.zone-hero {{
  padding: 52px 0 44px;
  border-bottom: 1px solid var(--line);
  max-width: 640px;
}}
.hero-kicker {{
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 14px;
}}
.zone-hero h1 {{
  font-family: var(--serif);
  font-size: 42px;
  font-weight: 400;
  line-height: 1.12;
  letter-spacing: -0.01em;
}}
.zone-hero h1 a {{
  color: var(--ink);
  text-decoration: none;
}}
.zone-hero h1 a:hover {{
  text-decoration: underline;
  text-underline-offset: 4px;
  text-decoration-thickness: 1px;
}}
.hero-why {{
  margin-top: 18px;
  font-size: 16px;
  line-height: 1.65;
  color: var(--muted);
  max-width: 560px;
}}
.hero-meta {{
  margin-top: 14px;
}}
.signal {{
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--faint);
  border: 1px solid var(--line);
  padding: 2px 6px;
  border-radius: 2px;
}}

/* ═══ ZONE: Pair (2 side-by-side) ═══ */
.zone-pair {{
  display: grid;
  grid-template-columns: 1fr 1px 1fr;
  gap: 0;
  padding: 36px 0;
  border-bottom: 1px solid var(--line);
}}
.pair-rule {{
  background: var(--line);
}}
.pair-card {{
  padding: 0 28px;
}}
.pair-card:first-child {{ padding-left: 0; }}
.pair-card:last-child {{ padding-right: 0; }}
.pair-card h3 {{
  font-family: var(--serif);
  font-size: 22px;
  font-weight: 400;
  line-height: 1.25;
}}
.pair-card h3 a {{
  color: var(--ink);
  text-decoration: none;
}}
.pair-card h3 a:hover {{ color: var(--accent); }}
.pair-meta {{
  margin-top: 8px;
}}
.pair-meta .src {{
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}}
.pair-why {{
  margin-top: 10px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--muted);
}}

/* ═══ ZONE: Compact rows ═══ */
.zone-rows {{
  padding: 8px 0;
  border-bottom: 1px solid var(--line);
}}
.row-item {{
  display: flex;
  gap: 16px;
  align-items: baseline;
  padding: 16px 0;
  border-bottom: 1px solid var(--line);
}}
.row-item:last-child {{ border-bottom: none; }}
.row-num {{
  font-family: var(--serif);
  font-size: 28px;
  color: var(--faint);
  min-width: 36px;
  text-align: right;
  line-height: 1;
  flex-shrink: 0;
}}
.row-body {{
  flex: 1;
}}
.row-body a {{
  font-family: var(--serif);
  font-size: 18px;
  font-weight: 400;
  line-height: 1.35;
  color: var(--ink);
  text-decoration: none;
  display: block;
}}
.row-body a:hover {{ color: var(--accent); }}
.row-src {{
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  display: block;
  margin-top: 4px;
}}

/* ═══ ZONE: Wide / Feature (pull-quote style) ═══ */
.zone-wide {{
  padding: 48px 0;
  border-bottom: 1px solid var(--line);
  position: relative;
}}
.wide-num {{
  font-family: var(--display);
  font-size: 80px;
  color: var(--line);
  position: absolute;
  right: 0;
  top: 32px;
  line-height: 1;
  pointer-events: none;
}}
.wide-title {{
  font-family: var(--serif);
  font-size: 28px;
  font-weight: 400;
  line-height: 1.25;
  font-style: italic;
  max-width: 680px;
  border: none;
  padding: 0;
}}
.wide-title a {{
  color: var(--ink);
  text-decoration: none;
}}
.wide-title a:hover {{
  color: var(--accent);
}}
.wide-footer {{
  margin-top: 14px;
  display: flex;
  gap: 12px;
  align-items: center;
}}
.wide-src {{
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent);
}}
.wide-signal {{
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--faint);
}}
.wide-why {{
  margin-top: 12px;
  font-size: 15px;
  line-height: 1.6;
  color: var(--muted);
  max-width: 580px;
}}

/* ═══ ZONE: Trio (3-col cluster) ═══ */
.zone-trio {{
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 0;
  padding: 36px 0;
  border-bottom: 1px solid var(--line);
}}
.trio-card {{
  padding: 0 20px;
  border-right: 1px solid var(--line);
}}
.trio-card:first-child {{ padding-left: 0; }}
.trio-card:last-child {{ padding-right: 0; border-right: none; }}
.trio-num {{
  font-family: var(--serif);
  font-size: 24px;
  color: var(--faint);
  margin-bottom: 6px;
}}
.trio-card h3 {{
  font-family: var(--serif);
  font-size: 17px;
  font-weight: 400;
  line-height: 1.3;
}}
.trio-card h3 a {{
  color: var(--ink);
  text-decoration: none;
}}
.trio-card h3 a:hover {{ color: var(--accent); }}
.trio-src {{
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  display: block;
  margin-top: 6px;
}}

/* ═══ ZONE: WSW Breaker ═══ */
.zone-wsw {{
  margin: 24px 0;
  padding: 40px 0;
  border-top: 2.5px solid var(--ink);
  border-bottom: 1px solid var(--line);
}}
.wsw-label {{
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 14px;
}}
.wsw-title {{
  font-family: var(--serif);
  font-size: 28px;
  font-weight: 400;
  line-height: 1.25;
  margin-bottom: 10px;
}}
.wsw-summary {{
  font-size: 15px;
  line-height: 1.6;
  color: var(--muted);
  font-style: italic;
  max-width: 600px;
  margin-bottom: 20px;
}}
.wsw-voices {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}}
.wsw-voice {{
  padding: 16px 0;
  border-top: 1px solid var(--line);
}}
.wsw-speaker {{
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--accent);
  display: block;
  margin-bottom: 6px;
}}
.wsw-voice p {{
  font-family: var(--serif);
  font-size: 15px;
  font-style: italic;
  line-height: 1.5;
  color: var(--muted);
}}

/* ═══ Footer ═══ */
footer {{
  padding: 56px 0 72px;
  text-align: center;
}}
footer .logo {{
  font-family: var(--display);
  font-size: 20px;
  font-style: italic;
  color: var(--faint);
  margin-bottom: 8px;
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
<hr class="masthead-rule">
<hr class="masthead-rule-thin">

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
  <button>WSW</button>
  <button>Bookmarks</button>
  <button onclick="document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark'">Theme</button>
</div>

<main>
{body_content}
</main>

<footer>
  <div class="logo">Finance Radar</div>
  <div class="count">{len(picks)} AI-curated picks</div>
</footer>

</body>
</html>'''


def main():
    data = load()
    out_dir = OUT / 'v10-editorial-river'
    out_dir.mkdir(parents=True, exist_ok=True)
    html = build_html(data['picks'], data['wsw'])
    (out_dir / 'home.html').write_text(html)
    print(f"wrote v10-editorial-river/home.html ({len(data['picks'])} picks)")

if __name__ == '__main__':
    main()
