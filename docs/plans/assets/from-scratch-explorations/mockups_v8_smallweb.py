"""V12: SMALLWEB-INSPIRED — directly modeled on smallweb.blog's design system.
Fraunces + Nunito Sans, warm cream, burnt orange accent, lead grid, category stamps,
dashed dividers, archive strips."""
from __future__ import annotations
import html as h
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

PROJECT = Path('/home/kashish.kapoor/vibecoding projects/financeradar')
STATIC = PROJECT / 'static'
OUT = PROJECT / 'docs' / 'plans' / 'assets' / 'from-scratch-explorations'

SMALL_WORDS = {'a','an','the','and','but','or','nor','for','yet','so',
               'in','on','at','to','by','of','up','as','is','it','if',
               'vs','via','from','with','into','than','per'}

def title_case(s):
    s = str(s or '').strip()
    if not s: return s
    words = s.split()
    result = []
    for i, w in enumerate(words):
        if i == 0 or i == len(words)-1:
            result.append(w.capitalize())
        elif w.lower() in SMALL_WORDS:
            result.append(w.lower())
        else:
            result.append(w.capitalize())
    return ' '.join(result)

def sentence_case(s):
    s = str(s or '').strip()
    if not s: return s
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

BOOKMARK_SVG = '<svg class="bk-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>'

# Category colors (like smallweb's per-topic colors)
BUCKET_COLORS = {
    'news': '#4A8F7A',
    'telegram': '#5E6A96',
    'reports': '#9A8345',
    'twitter': '#4A8A9A',
    'youtube': '#A86565',
}
BUCKET_LABELS = {
    'news': 'News',
    'telegram': 'Telegram',
    'reports': 'Reports',
    'twitter': 'Twitter',
    'youtube': 'YouTube',
}

def item_card(p, size='normal'):
    """Render a single item. size: 'lead', 'featured', 'normal', 'compact'"""
    title = e(title_case(p.get('title', '')))
    url = e(p.get('url', ''))
    source = e(p.get('source', ''))
    why = e(sentence_case(crop(p.get('why_it_matters', ''), 180)))
    signal = e(p.get('signal_type', ''))
    bucket = p.get('_bucket', 'news')
    color = BUCKET_COLORS.get(bucket, '#6B645C')
    label = BUCKET_LABELS.get(bucket, 'News')

    if size == 'lead':
        return f'''<div class="lead-main">
  <span class="stamp" style="border-color:{color};color:{color}">{label}</span>
  <h2 class="lead-title"><a href="{url}" target="_blank">{title}</a></h2>
  <div class="lead-byline"><strong>{source}</strong></div>
  <p class="lead-excerpt">{why}</p>
</div>'''

    elif size == 'featured':
        return f'''<div class="featured-item">
  <div class="featured-top">
    <span class="cat-dot" style="background:{color}"></span>
    <span class="cat-label">{label}</span>
  </div>
  <h3 class="featured-title"><a href="{url}" target="_blank">{title}</a></h3>
  <p class="featured-excerpt">{why}</p>
  <div class="featured-meta"><strong>{source}</strong></div>
</div>'''

    elif size == 'compact':
        return f'''<div class="compact-item">
  <span class="cat-dot" style="background:{color}"></span>
  <div class="compact-body">
    <a href="{url}" target="_blank" class="compact-title">{title}</a>
    <span class="compact-meta">{source}</span>
  </div>
  <button class="btn-bk" aria-label="Bookmark">{BOOKMARK_SVG}</button>
</div>'''

    else:  # normal
        return f'''<div class="item-card">
  <div class="item-top">
    <span class="cat-dot" style="background:{color}"></span>
    <span class="cat-label">{label}</span>
    <button class="btn-bk" aria-label="Bookmark">{BOOKMARK_SVG}</button>
  </div>
  <h3 class="item-title"><a href="{url}" target="_blank">{title}</a></h3>
  <p class="item-excerpt">{why}</p>
  <div class="item-meta"><strong>{source}</strong>{f' &middot; <span class="item-signal">{signal}</span>' if signal else ''}</div>
</div>'''


def build_html(picks, wsw):
    # Split picks into sections
    lead = picks[0] if picks else None
    lead_sidebar = picks[1:4]
    # Group remaining by bucket for category pairs
    remaining = picks[4:]

    # Featured picks (next 6)
    featured = remaining[:6]
    # Rest go into archive
    archive = remaining[6:]

    # ── Lead section ──
    lead_html = item_card(lead, 'lead') if lead else ''
    sidebar_html = ''.join(item_card(p, 'compact') for p in lead_sidebar)

    # ── Featured section (2-col pairs) ──
    featured_left = ''.join(item_card(p, 'featured') for p in featured[:3])
    featured_right = ''.join(item_card(p, 'featured') for p in featured[3:6])

    # ── WSW as a quote section ──
    wsw_html = ''
    if wsw:
        cl = wsw[0]
        wsw_html = f'''
    <section class="quote-section">
      <div class="cut"><span>&#9998;</span></div>
      <blockquote class="pull-quote">
        <p>{e(title_case(cl.get('cluster_title', '')))}</p>
        <cite>{e(sentence_case(crop(cl.get('summary', ''), 200)))}</cite>
      </blockquote>
    </section>'''

    # ── Archive strip ──
    archive_items = ''
    for p in archive:
        title = e(title_case(crop(p.get('title', ''), 80)))
        url = e(p.get('url', ''))
        source = e(p.get('source', ''))
        bucket = p.get('_bucket', 'news')
        color = BUCKET_COLORS.get(bucket, '#6B645C')
        label = BUCKET_LABELS.get(bucket, 'News')
        archive_items += f'''
      <div class="archive-item">
        <span class="archive-source">{source}</span>
        <a href="{url}" target="_blank" class="archive-title">{title}</a>
        <span class="stamp stamp-sm" style="border-color:{color};color:{color}">{label}</span>
        <button class="btn-bk" aria-label="Bookmark">{BOOKMARK_SVG}</button>
      </div>'''

    # ── More WSW as quotes ──
    more_wsw = ''
    for cl in wsw[1:3]:
        more_wsw += f'''
    <section class="quote-section quote-mini">
      <blockquote class="pull-quote">
        <p>{e(title_case(cl.get('cluster_title', '')))}</p>
        <cite>{e(sentence_case(crop(cl.get('summary', ''), 160)))}</cite>
      </blockquote>
    </section>'''

    today = datetime.now().strftime('%A, %d %B %Y')

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Finance Radar</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,500;0,9..144,700;0,9..144,900;1,9..144,400;1,9..144,500&family=Nunito+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

:root {{
  --bg: #FAF7F2;
  --ink: #2C2825;
  --ink-muted: #6B645C;
  --ink-faint: #9E978F;
  --rule: #E2DCD3;
  --accent: #C45A35;
  --card-bg: #FFFFFF;
  --card-border: #E2DCD3;
  --serif: 'Fraunces', Georgia, serif;
  --sans: 'Nunito Sans', system-ui, sans-serif;
}}
html.dark {{
  --bg: #1A1816;
  --ink: #E0DCD5;
  --ink-muted: #9E978F;
  --ink-faint: #6B645C;
  --rule: #2E2A25;
  --accent: #D97A58;
  --card-bg: #222019;
  --card-border: #2E2A25;
}}

html {{
  background: var(--bg);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 17px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  transition: background 0.5s ease, color 0.5s ease;
}}
body {{
  max-width: 1000px;
  margin: 0 auto;
  padding: 0 2.5rem;
}}

/* ═══ Utility bar ═══ */
.utility {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 0;
  border-bottom: 1px solid var(--rule);
  font-size: 0.78rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-muted);
}}
.utility a {{
  color: var(--ink-muted);
  text-decoration: none;
}}
.utility a:hover {{ color: var(--accent); }}
.utility-links {{
  display: flex;
  gap: 1.5rem;
}}

/* ═══ Masthead ═══ */
.masthead {{
  padding: 2.5rem 0 1.25rem;
  border-bottom: 2.5px solid var(--ink);
}}
.masthead h1 {{
  font-family: var(--serif);
  font-size: clamp(2.8rem, 6vw, 4.2rem);
  font-weight: 900;
  line-height: 0.95;
  letter-spacing: -0.03em;
}}
.masthead .tagline {{
  font-family: var(--serif);
  font-size: 1.05rem;
  font-weight: 300;
  font-style: italic;
  color: var(--ink-muted);
  margin-top: 0.5rem;
}}

/* ═══ Stamps / Category badges ═══ */
.stamps {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  padding: 1rem 0;
  border-bottom: 1px solid var(--rule);
}}
.stamp {{
  display: inline-flex;
  align-items: center;
  font-size: 0.62rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  padding: 0.3rem 0.65rem;
  border: 1.5px solid;
  border-radius: 3px;
  cursor: pointer;
  transition: all 0.2s ease;
  text-decoration: none;
  background: transparent;
}}
.stamp:hover {{
  background: var(--ink);
  color: var(--bg) !important;
  border-color: var(--ink) !important;
}}
.stamp.active {{
  background: var(--ink);
  color: var(--bg) !important;
  border-color: var(--ink) !important;
}}
.stamp-sm {{
  font-size: 0.55rem;
  padding: 0.2rem 0.45rem;
}}

/* ═══ Cat dot ═══ */
.cat-dot {{
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}}
.cat-label {{
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-muted);
}}

/* ═══ Lead section ═══ */
.lead {{
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 3rem;
  padding: 2rem 0 2.5rem;
  border-bottom: 1px solid var(--rule);
}}
.lead-main .stamp {{ margin-bottom: 0.75rem; }}
.lead-title {{
  font-family: var(--serif);
  font-size: clamp(1.6rem, 3vw, 2.2rem);
  font-weight: 500;
  line-height: 1.15;
  letter-spacing: -0.02em;
}}
.lead-title a {{
  color: var(--ink);
  text-decoration: none;
}}
.lead-title a:hover {{ color: var(--accent); }}
.lead-byline {{
  font-size: 0.78rem;
  color: var(--ink-muted);
  margin-top: 0.75rem;
}}
.lead-excerpt {{
  font-family: var(--serif);
  font-size: 0.95rem;
  line-height: 1.7;
  color: var(--ink-muted);
  margin-top: 0.75rem;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}}
.lead-sidebar {{
  display: flex;
  flex-direction: column;
  gap: 0;
}}

/* ═══ Compact items (sidebar) ═══ */
.compact-item {{
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  padding: 0.85rem 0;
  border-bottom: 1px solid var(--rule);
  transition: transform 0.2s ease;
}}
.compact-item:last-child {{ border-bottom: none; }}
.compact-item:hover {{ transform: translateX(3px); }}
.compact-body {{ flex: 1; min-width: 0; }}
.compact-title {{
  font-family: var(--serif);
  font-size: 0.95rem;
  font-weight: 500;
  line-height: 1.3;
  color: var(--ink);
  text-decoration: none;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}}
.compact-title:hover {{ color: var(--accent); }}
.compact-meta {{
  font-size: 0.72rem;
  color: var(--ink-faint);
  display: block;
  margin-top: 0.2rem;
}}

/* ═══ Bookmark button ═══ */
.btn-bk {{
  background: none;
  border: none;
  color: var(--ink-faint);
  cursor: pointer;
  padding: 2px;
  flex-shrink: 0;
  transition: color 0.2s ease;
}}
.btn-bk:hover {{ color: var(--accent); }}
.btn-bk.active {{ color: var(--accent); }}

/* ═══ Featured section (2-col) ═══ */
.featured-section {{
  display: grid;
  grid-template-columns: 1fr 1px 1fr;
  gap: 0;
  padding: 2.25rem 0 2.5rem;
  border-bottom: 1px solid var(--rule);
}}
.featured-col {{
  padding: 0 2.25rem;
}}
.featured-col:first-child {{ padding-left: 0; }}
.featured-col:last-child {{ padding-right: 0; }}
.featured-rule {{
  background: var(--rule);
}}
.featured-item {{
  padding: 1rem 0;
  border-bottom: 1px solid var(--rule);
}}
.featured-item:last-child {{ border-bottom: none; }}
.featured-top {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}}
.featured-title {{
  font-family: var(--serif);
  font-size: 1.05rem;
  font-weight: 500;
  line-height: 1.3;
}}
.featured-title a {{
  color: var(--ink);
  text-decoration: none;
}}
.featured-title a:hover {{ color: var(--accent); }}
.featured-excerpt {{
  font-size: 0.85rem;
  line-height: 1.6;
  color: var(--ink-muted);
  margin-top: 0.4rem;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}}
.featured-meta {{
  font-size: 0.72rem;
  color: var(--ink-faint);
  margin-top: 0.4rem;
}}

/* ═══ Quote / WSW section ═══ */
.quote-section {{
  padding: 2rem 0;
  text-align: center;
}}
.pull-quote {{
  max-width: 680px;
  margin: 0 auto;
  padding: 1.5rem 0;
  border-top: 1.5px solid var(--rule);
  border-bottom: 1.5px solid var(--rule);
}}
.pull-quote p {{
  font-family: var(--serif);
  font-size: 1.4rem;
  font-weight: 500;
  font-style: italic;
  line-height: 1.35;
  color: var(--ink);
}}
.pull-quote cite {{
  display: block;
  font-family: var(--sans);
  font-size: 0.82rem;
  font-style: normal;
  color: var(--ink-muted);
  margin-top: 0.75rem;
}}
.quote-mini .pull-quote p {{
  font-size: 1.15rem;
}}

/* ═══ Cut divider (scissors + dashed) ═══ */
.cut {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0;
  color: var(--ink-faint);
  font-size: 0.9rem;
}}
.cut::before, .cut::after {{
  content: '';
  flex: 1;
  border-top: 1px dashed var(--rule);
}}

/* ═══ Archive section ═══ */
.archive-section {{
  padding: 2rem 0;
  border-top: 2px solid var(--ink);
}}
.archive-header {{
  font-family: var(--serif);
  font-size: 1.6rem;
  font-weight: 700;
  margin-bottom: 1.25rem;
}}
.archive-item {{
  display: grid;
  grid-template-columns: 120px 1fr auto auto;
  gap: 0.75rem;
  align-items: center;
  padding: 0.65rem 0;
  border-bottom: 1px solid var(--rule);
  transition: transform 0.2s ease;
}}
.archive-item:hover {{ transform: translateX(3px); }}
.archive-source {{
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.archive-title {{
  font-family: var(--serif);
  font-size: 0.92rem;
  font-weight: 500;
  color: var(--ink);
  text-decoration: none;
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}}
.archive-title:hover {{ color: var(--accent); }}

/* ═══ Footer ═══ */
footer {{
  padding: 2.5rem 0 3rem;
  border-top: 1px solid var(--rule);
  display: flex;
  justify-content: space-between;
  align-items: center;
}}
footer .foot-brand {{
  font-family: var(--serif);
  font-size: 1rem;
  font-weight: 700;
  color: var(--ink-faint);
}}
footer .foot-links {{
  display: flex;
  gap: 1.25rem;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}}
footer .foot-links a {{
  color: var(--ink-faint);
  text-decoration: none;
}}
footer .foot-links a:hover {{ color: var(--accent); }}

/* ═══ Theme toggle ═══ */
.theme-toggle {{
  position: fixed;
  top: 1.25rem;
  right: 1.25rem;
  width: 34px;
  height: 34px;
  border: 1.5px solid var(--rule);
  border-radius: 6px;
  background: var(--bg);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  transition: all 0.2s ease;
  transform: rotate(2deg);
  z-index: 100;
  color: var(--ink-muted);
}}
.theme-toggle:hover {{
  transform: rotate(-2deg);
  border-color: var(--accent);
  color: var(--accent);
}}

/* ═══ Responsive ═══ */
@media (max-width: 768px) {{
  body {{ padding: 0 1.25rem; }}
  .lead {{ grid-template-columns: 1fr; gap: 1.5rem; }}
  .featured-section {{ grid-template-columns: 1fr; }}
  .featured-rule {{ display: none; }}
  .featured-col {{ padding: 0; }}
  .archive-item {{ grid-template-columns: 1fr auto auto; }}
  .archive-source {{ display: none; }}
}}
</style>
</head>
<body>

<button class="theme-toggle" onclick="document.documentElement.classList.toggle('dark')" aria-label="Toggle theme">&#9681;</button>

<div class="utility">
  <span>{today}</span>
  <div class="utility-links">
    <a href="#">AI Rankings</a>
    <a href="#">Bookmarks</a>
  </div>
</div>

<div class="masthead">
  <h1>Finance Radar</h1>
  <div class="tagline">AI-curated intelligence from across Indian finance</div>
</div>

<div class="stamps">
  <span class="stamp active" style="border-color:var(--ink);color:var(--ink)">All</span>
  <span class="stamp" style="border-color:#4A8F7A;color:#4A8F7A">News</span>
  <span class="stamp" style="border-color:#5E6A96;color:#5E6A96">Telegram</span>
  <span class="stamp" style="border-color:#9A8345;color:#9A8345">Reports</span>
  <span class="stamp" style="border-color:#A86565;color:#A86565">YouTube</span>
  <span class="stamp" style="border-color:#4A8A9A;color:#4A8A9A">Twitter</span>
</div>

<section class="lead">
  {lead_html}
  <div class="lead-sidebar">
    {sidebar_html}
  </div>
</section>

<section class="featured-section">
  <div class="featured-col">{featured_left}</div>
  <div class="featured-rule"></div>
  <div class="featured-col">{featured_right}</div>
</section>

{wsw_html}

<section class="archive-section">
  <div class="archive-header">More Picks</div>
  {archive_items}
</section>

{more_wsw}

<footer>
  <div class="foot-brand">Finance Radar</div>
  <div class="foot-links">
    <a href="#">Home</a>
    <a href="#">News</a>
    <a href="#">Telegram</a>
    <a href="#">Reports</a>
    <a href="#">YouTube</a>
    <a href="#">Twitter</a>
  </div>
</footer>

<script>
document.querySelectorAll('.btn-bk').forEach(btn => {{
  btn.addEventListener('click', () => {{
    btn.classList.toggle('active');
    const svg = btn.querySelector('svg');
    svg.setAttribute('fill', btn.classList.contains('active') ? 'currentColor' : 'none');
  }});
}});
document.querySelectorAll('.stamp').forEach(s => {{
  s.addEventListener('click', () => {{
    document.querySelectorAll('.stamp').forEach(x => x.classList.remove('active'));
    s.classList.add('active');
  }});
}});
if (localStorage.getItem('theme') === 'dark') document.documentElement.classList.add('dark');
document.querySelector('.theme-toggle').addEventListener('click', () => {{
  localStorage.setItem('theme', document.documentElement.classList.contains('dark') ? 'dark' : 'light');
}});
</script>

</body>
</html>'''


def main():
    data = load()
    out_dir = OUT / 'v12-smallweb'
    out_dir.mkdir(parents=True, exist_ok=True)
    html = build_html(data['picks'], data['wsw'])
    (out_dir / 'home.html').write_text(html)
    print(f"wrote v12-smallweb/home.html ({len(data['picks'])} picks)")

if __name__ == '__main__':
    main()
