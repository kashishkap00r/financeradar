"""5 Magazine Spread variations — building on C4's whitespace-first direction."""
from __future__ import annotations
import html as h
import json
from pathlib import Path

PROJECT = Path('/home/kashish.kapoor/vibecoding projects/financeradar')
STATIC = PROJECT / 'static'
OUT = PROJECT / 'docs' / 'plans' / 'assets' / 'from-scratch-explorations'

def load():
    articles = json.loads((STATIC / 'articles.json').read_text())['articles'][:30]
    tg = json.loads((STATIC / 'telegram_reports.json').read_text())['reports'][:10]
    rpt_raw = json.loads((STATIC / 'reports_cache.json').read_text())
    reports = []
    for items in rpt_raw.values():
        reports.extend(items)
    reports.sort(key=lambda x: x.get('date') or '', reverse=True)
    reports = reports[:10]
    yt_raw = json.loads((STATIC / 'youtube_cache.json').read_text())
    videos = []
    for items in yt_raw.values():
        videos.extend(items)
    videos.sort(key=lambda x: x.get('date') or '', reverse=True)
    videos = videos[:10]
    tw = json.loads((STATIC / 'twitter_clean_cache.json').read_text())['items'][:10]
    ai_raw = json.loads((STATIC / 'ai_rankings.json').read_text())
    ai = []
    for prov in ai_raw.get('providers',{}).values():
        for bucket_items in prov.get('buckets',{}).values():
            ai.extend(bucket_items)
        break
    ai.sort(key=lambda x: x.get('rank',99))
    ai = ai[:12]
    wsw_raw = json.loads((STATIC / 'wsw_clusters.json').read_text())
    wsw = []
    for prov in wsw_raw.get('providers',{}).values():
        wsw = prov.get('clusters',[])[:5]
        break
    return dict(articles=articles, telegram=tg, reports=reports,
                videos=videos, twitter=tw, ai=ai, wsw=wsw)

def e(s): return h.escape(str(s or ''), quote=True)
def crop(s, n=80):
    s = str(s or '').strip()
    return s if len(s)<=n else s[:n-1].rstrip()+'…'
def ts(d):
    if not d: return ''
    return d[:10]


# ── V1: Folio — hard vertical split, left hero / right sections ──
def v1_folio(data):
    hero = data['ai'][0] if data['ai'] else data['articles'][0]

    right_stories = ''
    for art in data['articles'][:5]:
        right_stories += f'''<div class="r-story">
          <a href="{e(art['url'])}" target="_blank">{e(crop(art['title'],75))}</a>
          <span>{e(art['source'])}</span>
        </div>'''

    reports_block = ''
    for r in data['reports'][:3]:
        reports_block += f'''<div class="r-story">
          <a href="{e(r.get('link','#'))}" target="_blank">{e(crop(r['title'],70))}</a>
          <span>{e(r.get('publisher',''))}</span>
        </div>'''

    wsw_block = ''
    for cl in data['wsw'][:2]:
        voice = cl.get('key_voices',[{}])[0] if cl.get('key_voices') else {}
        wsw_block += f'''<div class="wsw-quote">
          <p>"{e(crop(cl.get('core_claim',''),100))}"</p>
          <span>{e(voice.get('voice',''))} — {e(crop(cl['cluster_title'],40))}</span>
        </div>'''

    return f'''<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>V1 — Folio Split</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Space+Mono:wght@400;700&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0}}
:root{{--bg:#fefefe;--ink:#111;--mut:#888;--ln:#e8e8e8;--acc:#111}}
[data-theme="dark"]{{--bg:#0c0c0c;--ink:#f0f0f0;--mut:#666;--ln:#2a2a2a;--acc:#fff}}
body{{background:var(--bg);color:var(--ink);font-family:'DM Sans',sans-serif;-webkit-font-smoothing:antialiased}}
.topbar{{display:flex;align-items:center;padding:24px 48px;border-bottom:1px solid var(--ln)}}
.logo{{font:400 22px 'Instrument Serif',serif}}
.actions{{margin-left:auto;display:flex;gap:14px}}
.actions button{{background:none;border:none;font:400 12px 'Space Mono',monospace;color:var(--mut);cursor:pointer}}
.actions button:hover{{color:var(--ink)}}
.tabs{{display:flex;gap:28px;padding:14px 48px;border-bottom:1px solid var(--ln)}}
.tabs a{{font:400 15px 'DM Sans',sans-serif;color:var(--mut);text-decoration:none}}
.tabs a.active{{color:var(--ink);font-weight:600;text-decoration:underline;text-underline-offset:6px;text-decoration-thickness:1.5px}}
.folio{{display:grid;grid-template-columns:1fr 1px 1fr;min-height:calc(100vh - 120px)}}
.folio-rule{{background:var(--ln)}}
.folio-left{{padding:64px 56px 48px}}
.folio-right{{padding:48px 56px}}
.kicker{{font:700 10px 'Space Mono',monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);margin-bottom:16px}}
.hero-title{{font:400 42px/1.1 'Instrument Serif',serif;margin-bottom:14px;letter-spacing:-.01em}}
.hero-title a{{color:var(--ink);text-decoration:none}}
.hero-title a:hover{{text-decoration:underline;text-underline-offset:4px;text-decoration-thickness:1px}}
.hero-src{{font:700 9px 'Space Mono',monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--mut);margin-bottom:16px}}
.hero-lede{{font:400 15px/1.7 'DM Sans',sans-serif;color:var(--mut);max-width:420px}}
.section-head{{font:700 9px 'Space Mono',monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);padding-bottom:10px;border-bottom:1px solid var(--ln);margin:32px 0 16px}}
.section-head:first-child{{margin-top:0}}
.r-story{{padding:14px 0;border-bottom:1px solid var(--ln)}}
.r-story a{{font:400 16px/1.35 'Instrument Serif',serif;color:var(--ink);text-decoration:none;display:block}}
.r-story a:hover{{color:var(--mut)}}
.r-story span{{font:700 9px 'Space Mono',monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);display:block;margin-top:4px}}
.wsw-quote{{padding:18px 0;border-bottom:1px solid var(--ln)}}
.wsw-quote p{{font:400 15px/1.55 'Instrument Serif',serif;font-style:italic;color:var(--ink)}}
.wsw-quote span{{font:400 11px 'DM Sans',sans-serif;color:var(--mut);display:block;margin-top:6px}}
</style></head>
<body data-theme="light">
<div class="topbar">
  <div class="logo">Finance Radar</div>
  <div class="actions">
    <button>AI</button><button>WSW</button><button>Bookmarks</button>
    <button onclick="document.body.dataset.theme=document.body.dataset.theme==='dark'?'light':'dark'">Theme</button>
  </div>
</div>
<div class="tabs">
  <a class="active">Home</a><a>News</a><a>Telegram</a><a>Reports</a><a>YouTube</a><a>Twitter</a>
</div>
<div class="folio">
  <div class="folio-left">
    <div class="kicker">SPOTLIGHT</div>
    <div class="hero-src">{e(hero.get('source',''))}</div>
    <h1 class="hero-title"><a href="{e(hero.get('url','#'))}" target="_blank">{e(hero['title'])}</a></h1>
    <div class="hero-lede">{e(crop(hero.get('why_it_matters',''),200))}</div>
    <div class="section-head">VOICES</div>
    {wsw_block}
  </div>
  <div class="folio-rule"></div>
  <div class="folio-right">
    <div class="section-head">LATEST</div>
    {right_stories}
    <div class="section-head">REPORTS</div>
    {reports_block}
  </div>
</div>
</body></html>'''


# ── V2: Warm Ink — terracotta accent, slightly tighter, warmer paper ──
def v2_warm_ink(data):
    hero = data['ai'][0] if data['ai'] else data['articles'][0]

    secondary = ''
    for art in data['articles'][:4]:
        secondary += f'''<div class="side-story">
          <h3><a href="{e(art['url'])}" target="_blank">{e(crop(art['title'],72))}</a></h3>
          <span>{e(art['source'])}</span>
        </div>'''

    sections_html = ''
    groups = [
        ('News', data['articles'][4:7]),
        ('Reports', data['reports'][:3]),
        ('Videos', data['videos'][:3]),
        ('Twitter', data['twitter'][:3]),
    ]
    for label, items in groups:
        rows = ''
        for it in items:
            t = it.get('title','')
            u = it.get('url', it.get('link','#'))
            s = it.get('publisher', it.get('source',''))
            rows += f'<div class="sec-row"><a href="{e(u)}" target="_blank">{e(crop(t,68))}</a><span>{e(s)}</span></div>'
        sections_html += f'<div class="section"><h2>{label}</h2>{rows}</div>'

    return f'''<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>V2 — Warm Ink</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400&family=Space+Mono:wght@400;700&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0}}
:root{{--bg:#f9f6f2;--ink:#1a1714;--mut:#8a7e72;--ln:#e0d9d0;--acc:#b84c2a}}
[data-theme="dark"]{{--bg:#110f0d;--ink:#e8e0d6;--mut:#7a7068;--ln:#2e2820;--acc:#d4734e}}
body{{background:var(--bg);color:var(--ink);font-family:'DM Sans',sans-serif;-webkit-font-smoothing:antialiased}}
.topbar{{display:flex;align-items:center;padding:28px 48px 20px}}
.logo{{font:400 26px 'Cormorant Garamond',serif;font-style:italic}}
.topbar .right{{margin-left:auto;display:flex;gap:14px}}
.topbar button{{background:none;border:none;font:400 11px 'Space Mono',monospace;color:var(--mut);cursor:pointer}}
.topbar button:hover{{color:var(--ink)}}
.tabs{{display:flex;gap:24px;padding:0 48px 16px;border-bottom:1px solid var(--ln)}}
.tabs a{{font:500 14px 'DM Sans',sans-serif;color:var(--mut);text-decoration:none}}
.tabs a.active{{color:var(--acc);font-weight:600}}
.page{{max-width:1080px;margin:0 auto;padding:0 48px 60px}}
.hero-grid{{display:grid;grid-template-columns:1.5fr 1fr;gap:40px;padding:44px 0;border-bottom:1px solid var(--ln)}}
.hero-main .kicker{{font:700 10px 'Space Mono',monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--acc);margin-bottom:10px}}
.hero-main h1{{font:400 40px/1.1 'Cormorant Garamond',serif;margin-bottom:12px}}
.hero-main h1 a{{color:var(--ink);text-decoration:none}}
.hero-main h1 a:hover{{color:var(--acc)}}
.hero-main .lede{{font:400 15px/1.65 'DM Sans',sans-serif;color:var(--mut);max-width:480px;margin-top:10px}}
.side-story{{padding:16px 0;border-bottom:1px solid var(--ln)}}
.side-story h3{{font:400 17px/1.3 'Cormorant Garamond',serif}}
.side-story h3 a{{color:var(--ink);text-decoration:none}}
.side-story h3 a:hover{{color:var(--acc)}}
.side-story span{{font:700 9px 'Space Mono',monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);display:block;margin-top:3px}}
.sections{{display:grid;grid-template-columns:1fr 1fr;gap:40px 56px;padding:40px 0}}
.section h2{{font:400 26px 'Cormorant Garamond',serif;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid var(--ln)}}
.sec-row{{padding:10px 0;border-bottom:1px solid var(--ln)}}
.sec-row a{{font:400 15px/1.35 'Cormorant Garamond',serif;color:var(--ink);text-decoration:none;display:block}}
.sec-row a:hover{{color:var(--acc)}}
.sec-row span{{font:700 9px 'Space Mono',monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);display:block;margin-top:3px}}
</style></head>
<body data-theme="light">
<div class="topbar">
  <div class="logo">Finance Radar</div>
  <div class="right">
    <button>AI</button><button>WSW</button><button>Bookmarks</button>
    <button onclick="document.body.dataset.theme=document.body.dataset.theme==='dark'?'light':'dark'">Theme</button>
  </div>
</div>
<div class="tabs">
  <a class="active">Home</a><a>News</a><a>Telegram</a><a>Reports</a><a>YouTube</a><a>Twitter</a>
</div>
<main class="page">
  <div class="hero-grid">
    <div class="hero-main">
      <div class="kicker">{e(hero.get('source',''))}</div>
      <h1><a href="{e(hero.get('url','#'))}" target="_blank">{e(hero['title'])}</a></h1>
      <div class="lede">{e(crop(hero.get('why_it_matters',''),180))}</div>
    </div>
    <div class="hero-side">{secondary}</div>
  </div>
  <div class="sections">{sections_html}</div>
</main>
</body></html>'''


# ── V3: Mono Journal — ruled notebook feel, Space Mono heavy ──
def v3_mono_journal(data):
    hero = data['ai'][0] if data['ai'] else data['articles'][0]

    entries = ''
    for i, art in enumerate(data['articles'][:8]):
        entries += f'''<div class="entry">
          <div class="entry-num">{i+1:02d}</div>
          <div class="entry-body">
            <a href="{e(art['url'])}" target="_blank">{e(crop(art['title'],80))}</a>
            <div class="entry-meta">{e(art['source'])} · {ts(art.get('date',''))}</div>
          </div>
        </div>'''

    ai_entries = ''
    for item in data['ai'][:5]:
        ai_entries += f'''<div class="entry">
          <div class="entry-num" style="color:var(--acc)">{item.get('rank',''):02d}</div>
          <div class="entry-body">
            <a href="{e(item.get('url','#'))}" target="_blank">{e(crop(item['title'],75))}</a>
            <div class="entry-meta">{e(item.get('source',''))} · {e(item.get('signal_type',''))}</div>
          </div>
        </div>'''

    reports_entries = ''
    for r in data['reports'][:4]:
        reports_entries += f'''<div class="entry">
          <div class="entry-num">—</div>
          <div class="entry-body">
            <a href="{e(r.get('link','#'))}" target="_blank">{e(crop(r['title'],75))}</a>
            <div class="entry-meta">{e(r.get('publisher',''))} · {e(r.get('region',''))}</div>
          </div>
        </div>'''

    return f'''<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>V3 — Mono Journal</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0}}
:root{{--bg:#fafafa;--ink:#111;--mut:#999;--ln:#ddd;--acc:#c0392b;--rule:repeating-linear-gradient(transparent,transparent 31px,var(--ln) 31px,var(--ln) 32px)}}
[data-theme="dark"]{{--bg:#0e0e0e;--ink:#ddd;--mut:#666;--ln:#2a2a2a;--acc:#e74c3c;--rule:repeating-linear-gradient(transparent,transparent 31px,var(--ln) 31px,var(--ln) 32px)}}
body{{background:var(--bg);color:var(--ink);font-family:'Space Mono',monospace;-webkit-font-smoothing:antialiased}}
.topbar{{display:flex;align-items:center;padding:20px 40px;border-bottom:2px solid var(--ink)}}
.logo{{font:700 14px 'Space Mono',monospace;letter-spacing:.1em;text-transform:uppercase}}
.logo span{{color:var(--acc)}}
.right{{margin-left:auto;display:flex;gap:16px}}
.right button{{background:none;border:1px solid var(--ln);font:400 10px 'Space Mono',monospace;color:var(--mut);padding:4px 10px;cursor:pointer}}
.right button:hover{{color:var(--ink);border-color:var(--ink)}}
.tabs{{display:flex;gap:0;border-bottom:2px solid var(--ink)}}
.tabs a{{font:400 11px 'Space Mono',monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);text-decoration:none;padding:10px 20px;border-right:1px solid var(--ln)}}
.tabs a.active{{color:var(--ink);background:var(--bg)}}
.tabs a:hover{{color:var(--ink)}}
.page{{max-width:960px;margin:0 auto;padding:32px 40px 60px}}
.hero{{padding:32px 0 28px;border-bottom:2px solid var(--ink);margin-bottom:32px}}
.hero-label{{font:700 10px 'Space Mono',monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--acc);margin-bottom:12px}}
.hero h1{{font:400 36px/1.12 'Instrument Serif',serif;margin-bottom:10px}}
.hero h1 a{{color:var(--ink);text-decoration:none}}
.hero h1 a:hover{{text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:4px}}
.hero-meta{{font:400 11px 'Space Mono',monospace;color:var(--mut)}}
.hero-lede{{font:400 13px/1.7 'Space Mono',monospace;color:var(--mut);margin-top:12px;max-width:560px}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:40px}}
.col-head{{font:700 10px 'Space Mono',monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--acc);padding-bottom:8px;border-bottom:2px solid var(--ink);margin-bottom:8px}}
.entry{{display:grid;grid-template-columns:32px 1fr;gap:10px;padding:8px 0;border-bottom:1px solid var(--ln)}}
.entry-num{{font:700 11px 'Space Mono',monospace;color:var(--mut);padding-top:2px}}
.entry-body a{{font:400 14px/1.35 'Instrument Serif',serif;color:var(--ink);text-decoration:none;display:block}}
.entry-body a:hover{{color:var(--acc)}}
.entry-meta{{font:400 10px 'Space Mono',monospace;color:var(--mut);margin-top:2px}}
.section{{margin-top:32px}}
</style></head>
<body data-theme="light">
<div class="topbar">
  <div class="logo">FINANCE<span>RADAR</span></div>
  <div class="right">
    <button>AI</button><button>WSW</button><button>★</button>
    <button onclick="document.body.dataset.theme=document.body.dataset.theme==='dark'?'light':'dark'">THEME</button>
  </div>
</div>
<div class="tabs">
  <a class="active">Home</a><a>News</a><a>Telegram</a><a>Reports</a><a>YouTube</a><a>Twitter</a>
</div>
<main class="page">
  <div class="hero">
    <div class="hero-label">SPOTLIGHT · #{hero.get('rank','1')}</div>
    <h1><a href="{e(hero.get('url','#'))}" target="_blank">{e(hero['title'])}</a></h1>
    <div class="hero-meta">{e(hero.get('source',''))} · {e(hero.get('signal_type',''))}</div>
    <div class="hero-lede">{e(crop(hero.get('why_it_matters',''),200))}</div>
  </div>
  <div class="two-col">
    <div>
      <div class="col-head">LATEST ENTRIES</div>
      {entries}
    </div>
    <div>
      <div class="col-head">AI PICKS</div>
      {ai_entries}
      <div class="section">
        <div class="col-head">REPORTS</div>
        {reports_entries}
      </div>
    </div>
  </div>
</main>
</body></html>'''


# ── V4: Quiet Luxury — deep navy accent, ultra-refined, lots of air ──
def v4_quiet_luxury(data):
    hero = data['ai'][0] if data['ai'] else data['articles'][0]

    secondary = ''
    for art in data['articles'][:3]:
        secondary += f'''<div class="card">
          <a href="{e(art['url'])}" target="_blank">{e(crop(art['title'],70))}</a>
          <span>{e(art['source'])}</span>
        </div>'''

    ai_picks = ''
    for item in data['ai'][1:6]:
        ai_picks += f'''<div class="pick">
          <span class="pick-rank">{item.get('rank','')}</span>
          <a href="{e(item.get('url','#'))}" target="_blank">{e(crop(item['title'],65))}</a>
          <span class="pick-src">{e(item.get('source',''))}</span>
        </div>'''

    reports_block = ''
    for r in data['reports'][:3]:
        reports_block += f'''<div class="card">
          <a href="{e(r.get('link','#'))}" target="_blank">{e(crop(r['title'],70))}</a>
          <span>{e(r.get('publisher',''))}</span>
        </div>'''

    wsw_block = ''
    for cl in data['wsw'][:2]:
        wsw_block += f'''<div class="wsw-item">
          <h3>{e(crop(cl['cluster_title'],50))}</h3>
          <p>{e(crop(cl.get('core_claim',''),110))}</p>
        </div>'''

    return f'''<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>V4 — Quiet Luxury</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@400;500&family=Space+Mono:wght@400&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0}}
:root{{--bg:#fff;--ink:#111;--mut:#999;--ln:#eee;--acc:#1a3a5c}}
[data-theme="dark"]{{--bg:#090d11;--ink:#e8ecf0;--mut:#607080;--ln:#1e2a36;--acc:#6fa3d4}}
body{{background:var(--bg);color:var(--ink);font-family:'Inter',sans-serif;-webkit-font-smoothing:antialiased}}
.topbar{{display:flex;align-items:center;padding:32px 56px 24px}}
.logo{{font:400 24px 'Instrument Serif',serif;color:var(--acc)}}
.right{{margin-left:auto;display:flex;gap:16px;align-items:center}}
.right button{{background:none;border:none;font:400 12px 'Inter',sans-serif;color:var(--mut);cursor:pointer;padding:4px 8px}}
.right button:hover{{color:var(--ink)}}
.tabs{{display:flex;gap:32px;padding:0 56px 20px}}
.tabs a{{font:500 14px 'Inter',sans-serif;color:var(--mut);text-decoration:none}}
.tabs a.active{{color:var(--acc)}}
.tabs a:hover{{color:var(--ink)}}
.divider{{height:1px;background:var(--ln);margin:0 56px}}
.page{{max-width:1100px;margin:0 auto;padding:0 56px 64px}}
.hero-section{{padding:56px 0 48px;display:grid;grid-template-columns:1fr;gap:12px;max-width:640px}}
.hero-kicker{{font:500 11px 'Space Mono',monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--acc)}}
.hero-section h1{{font:400 44px/1.08 'Instrument Serif',serif;letter-spacing:-.01em}}
.hero-section h1 a{{color:var(--ink);text-decoration:none}}
.hero-section h1 a:hover{{opacity:.7}}
.hero-section .lede{{font:400 15px/1.7 'Inter',sans-serif;color:var(--mut);max-width:520px}}
.grid-3{{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;padding:32px 0;border-top:1px solid var(--ln)}}
.card{{padding:20px 0}}
.card a{{font:400 17px/1.3 'Instrument Serif',serif;color:var(--ink);text-decoration:none;display:block;margin-bottom:6px}}
.card a:hover{{color:var(--acc)}}
.card span{{font:400 10px 'Space Mono',monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mut)}}
.section-label{{font:500 10px 'Space Mono',monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--acc);margin-bottom:16px;padding-top:40px}}
.picks{{display:grid;gap:0;border-top:1px solid var(--ln)}}
.pick{{display:grid;grid-template-columns:28px 1fr auto;gap:10px;padding:12px 0;border-bottom:1px solid var(--ln);align-items:baseline}}
.pick-rank{{font:500 12px 'Space Mono',monospace;color:var(--acc)}}
.pick a{{font:400 15px/1.35 'Instrument Serif',serif;color:var(--ink);text-decoration:none}}
.pick a:hover{{color:var(--acc)}}
.pick-src{{font:400 10px 'Space Mono',monospace;color:var(--mut);letter-spacing:.06em;text-transform:uppercase}}
.bottom-grid{{display:grid;grid-template-columns:1fr 1fr;gap:48px;padding:40px 0;border-top:1px solid var(--ln)}}
.wsw-item h3{{font:400 18px/1.3 'Instrument Serif',serif;margin-bottom:6px}}
.wsw-item p{{font:400 13px/1.6 'Inter',sans-serif;color:var(--mut)}}
.wsw-item{{margin-bottom:20px}}
</style></head>
<body data-theme="light">
<div class="topbar">
  <div class="logo">Finance Radar</div>
  <div class="right">
    <button>AI</button><button>Voices</button><button>Bookmarks</button>
    <button onclick="document.body.dataset.theme=document.body.dataset.theme==='dark'?'light':'dark'">Theme</button>
  </div>
</div>
<div class="tabs">
  <a class="active">Home</a><a>News</a><a>Telegram</a><a>Reports</a><a>YouTube</a><a>Twitter</a>
</div>
<div class="divider"></div>
<main class="page">
  <div class="hero-section">
    <div class="hero-kicker">{e(hero.get('source',''))}</div>
    <h1><a href="{e(hero.get('url','#'))}" target="_blank">{e(hero['title'])}</a></h1>
    <div class="lede">{e(crop(hero.get('why_it_matters',''),180))}</div>
  </div>
  <div class="grid-3">{secondary}</div>
  <div class="section-label">AI PICKS</div>
  <div class="picks">{ai_picks}</div>
  <div class="bottom-grid">
    <div>
      <div class="section-label" style="padding-top:0">REPORTS</div>
      {reports_block}
    </div>
    <div>
      <div class="section-label" style="padding-top:0">VOICES</div>
      {wsw_block}
    </div>
  </div>
</main>
</body></html>'''


# ── V5: Stacked Rhythm — single column, editorial scroll, dramatic pacing ──
def v5_stacked_rhythm(data):
    hero = data['ai'][0] if data['ai'] else data['articles'][0]

    articles_html = ''
    for i, art in enumerate(data['articles'][:6]):
        size_class = 'story-lg' if i % 4 == 0 else 'story-sm'
        articles_html += f'''<div class="{size_class}">
          <a href="{e(art['url'])}" target="_blank">{e(crop(art['title'], 100 if size_class=='story-lg' else 75))}</a>
          <span>{e(art['source'])} · {ts(art.get('date',''))}</span>
        </div>'''

    ai_strip = ''
    for item in data['ai'][:6]:
        ai_strip += f'''<div class="ai-card">
          <div class="ai-rank">{item.get('rank','')}</div>
          <a href="{e(item.get('url','#'))}" target="_blank">{e(crop(item['title'],55))}</a>
          <span>{e(item.get('source',''))}</span>
        </div>'''

    reports_html = ''
    for r in data['reports'][:3]:
        reports_html += f'''<div class="rpt-row">
          <a href="{e(r.get('link','#'))}" target="_blank">{e(crop(r['title'],70))}</a>
          <span>{e(r.get('publisher',''))}</span>
        </div>'''

    wsw_html = ''
    for cl in data['wsw'][:3]:
        voice = cl.get('key_voices',[{}])[0] if cl.get('key_voices') else {}
        wsw_html += f'''<div class="wsw-block">
          <h3>{e(crop(cl['cluster_title'],50))}</h3>
          <p>"{e(crop(cl.get('core_claim',''),100))}"</p>
          <span>{e(voice.get('voice',''))}</span>
        </div>'''

    return f'''<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>V5 — Stacked Rhythm</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Space+Mono:wght@400;700&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0}}
:root{{--bg:#fdfdfc;--ink:#111;--mut:#888;--ln:#e6e4e0;--acc:#111}}
[data-theme="dark"]{{--bg:#0b0b0a;--ink:#eae8e4;--mut:#6a6864;--ln:#282624;--acc:#eae8e4}}
body{{background:var(--bg);color:var(--ink);font-family:'DM Sans',sans-serif;-webkit-font-smoothing:antialiased}}
.topbar{{display:flex;align-items:baseline;padding:28px 0 20px;max-width:720px;margin:0 auto}}
.logo{{font:400 22px 'Instrument Serif',serif}}
.right{{margin-left:auto;display:flex;gap:14px}}
.right button{{background:none;border:none;font:400 11px 'Space Mono',monospace;color:var(--mut);cursor:pointer}}
.right button:hover{{color:var(--ink)}}
.tabs{{max-width:720px;margin:0 auto;display:flex;gap:24px;padding-bottom:16px;border-bottom:1px solid var(--ln)}}
.tabs a{{font:400 14px 'DM Sans',sans-serif;color:var(--mut);text-decoration:none}}
.tabs a.active{{color:var(--ink);font-weight:600;text-decoration:underline;text-underline-offset:6px;text-decoration-thickness:1.5px}}
.page{{max-width:720px;margin:0 auto;padding:0 0 80px}}
.hero{{padding:56px 0 40px;border-bottom:1px solid var(--ln)}}
.hero-kicker{{font:700 9px 'Space Mono',monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);margin-bottom:14px}}
.hero h1{{font:400 42px/1.08 'Instrument Serif',serif;margin-bottom:12px}}
.hero h1 a{{color:var(--ink);text-decoration:none}}
.hero h1 a:hover{{text-decoration:underline;text-underline-offset:4px;text-decoration-thickness:1px}}
.hero .lede{{font:400 15px/1.7 'DM Sans',sans-serif;color:var(--mut);max-width:540px}}
.section-divider{{font:700 9px 'Space Mono',monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--mut);padding:36px 0 12px;border-bottom:1px solid var(--ln)}}
.story-lg{{padding:24px 0;border-bottom:1px solid var(--ln)}}
.story-lg a{{font:400 24px/1.2 'Instrument Serif',serif;color:var(--ink);text-decoration:none;display:block;margin-bottom:6px}}
.story-lg a:hover{{color:var(--mut)}}
.story-sm{{padding:16px 0;border-bottom:1px solid var(--ln)}}
.story-sm a{{font:400 17px/1.3 'Instrument Serif',serif;color:var(--ink);text-decoration:none;display:block;margin-bottom:4px}}
.story-sm a:hover{{color:var(--mut)}}
.story-lg span,.story-sm span{{font:700 9px 'Space Mono',monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mut)}}
.ai-scroll{{display:flex;gap:16px;overflow-x:auto;padding:20px 0;scrollbar-width:none;-webkit-overflow-scrolling:touch}}
.ai-scroll::-webkit-scrollbar{{display:none}}
.ai-card{{min-width:200px;flex-shrink:0;padding:16px;border:1px solid var(--ln)}}
.ai-rank{{font:700 20px 'Space Mono',monospace;color:var(--ln);margin-bottom:8px}}
.ai-card a{{font:400 14px/1.3 'Instrument Serif',serif;color:var(--ink);text-decoration:none;display:block;margin-bottom:4px}}
.ai-card a:hover{{color:var(--mut)}}
.ai-card span{{font:400 10px 'Space Mono',monospace;color:var(--mut);letter-spacing:.06em;text-transform:uppercase}}
.rpt-row{{padding:12px 0;border-bottom:1px solid var(--ln)}}
.rpt-row a{{font:400 16px/1.35 'Instrument Serif',serif;color:var(--ink);text-decoration:none;display:block}}
.rpt-row a:hover{{color:var(--mut)}}
.rpt-row span{{font:700 9px 'Space Mono',monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);display:block;margin-top:3px}}
.wsw-block{{padding:20px 0;border-bottom:1px solid var(--ln)}}
.wsw-block h3{{font:400 18px 'Instrument Serif',serif;margin-bottom:6px}}
.wsw-block p{{font:400 14px/1.55 'Instrument Serif',serif;font-style:italic;color:var(--mut)}}
.wsw-block span{{font:400 11px 'DM Sans',sans-serif;color:var(--mut);display:block;margin-top:4px}}
</style></head>
<body data-theme="light">
<div class="topbar">
  <div class="logo">Finance Radar</div>
  <div class="right">
    <button>AI</button><button>WSW</button><button>★</button>
    <button onclick="document.body.dataset.theme=document.body.dataset.theme==='dark'?'light':'dark'">Theme</button>
  </div>
</div>
<div class="tabs">
  <a class="active">Home</a><a>News</a><a>Telegram</a><a>Reports</a><a>YouTube</a><a>Twitter</a>
</div>
<main class="page">
  <div class="hero">
    <div class="hero-kicker">{e(hero.get('source',''))}</div>
    <h1><a href="{e(hero.get('url','#'))}" target="_blank">{e(hero['title'])}</a></h1>
    <div class="lede">{e(crop(hero.get('why_it_matters',''),180))}</div>
  </div>
  <div class="section-divider">AI PICKS</div>
  <div class="ai-scroll">{ai_strip}</div>
  <div class="section-divider">LATEST</div>
  {articles_html}
  <div class="section-divider">REPORTS</div>
  {reports_html}
  <div class="section-divider">VOICES</div>
  {wsw_html}
</main>
</body></html>'''


# ── V6: Broadsheet Minimal — newspaper DNA but ultra-minimal, big type ──
def v6_broadsheet_minimal(data):
    hero = data['ai'][0] if data['ai'] else data['articles'][0]

    col_left = ''
    for art in data['articles'][:5]:
        col_left += f'''<div class="story">
          <h3><a href="{e(art['url'])}" target="_blank">{e(crop(art['title'],85))}</a></h3>
          <span>{e(art['source'])}</span>
        </div>'''

    col_right = ''
    for r in data['reports'][:3]:
        col_right += f'''<div class="story">
          <h3><a href="{e(r.get('link','#'))}" target="_blank">{e(crop(r['title'],80))}</a></h3>
          <span>{e(r.get('publisher',''))}</span>
        </div>'''
    for cl in data['wsw'][:2]:
        col_right += f'''<div class="story quote">
          <p>"{e(crop(cl.get('core_claim',''),100))}"</p>
          <span>{e(crop(cl['cluster_title'],40))}</span>
        </div>'''

    return f'''<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>V6 — Broadsheet Minimal</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Space+Mono:wght@400;700&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0}}
:root{{--bg:#fff;--ink:#111;--mut:#999;--ln:#ddd;--acc:#111}}
[data-theme="dark"]{{--bg:#0a0a0a;--ink:#eee;--mut:#666;--ln:#282828;--acc:#eee}}
body{{background:var(--bg);color:var(--ink);font-family:'DM Sans',sans-serif;-webkit-font-smoothing:antialiased}}
.masthead{{text-align:center;padding:36px 0 0}}
.masthead .date{{font:400 10px 'Space Mono',monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--mut)}}
.masthead h1{{font:400 52px 'Instrument Serif',serif;font-style:italic;margin:8px 0 0;letter-spacing:-.02em}}
.rule{{border:none;border-top:1px solid var(--ln);margin:16px 48px}}
.rule.thick{{border-top-width:3px;border-color:var(--ink)}}
.nav-row{{display:flex;justify-content:center;align-items:center;gap:20px;padding:0 0 14px}}
.nav-row a{{font:400 14px 'DM Sans',sans-serif;color:var(--mut);text-decoration:none}}
.nav-row a.active{{color:var(--ink);font-weight:600}}
.nav-row a:hover{{color:var(--ink)}}
.nav-row .sep{{color:var(--ln)}}
.actions-row{{display:flex;justify-content:center;gap:16px;padding:8px 0 0}}
.actions-row button{{background:none;border:none;font:400 11px 'Space Mono',monospace;color:var(--mut);cursor:pointer}}
.actions-row button:hover{{color:var(--ink)}}
.page{{max-width:1000px;margin:0 auto;padding:0 48px 60px}}
.hero{{padding:48px 0 40px;max-width:680px}}
.hero .kicker{{font:700 10px 'Space Mono',monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);margin-bottom:12px}}
.hero h2{{font:400 40px/1.1 'Instrument Serif',serif;margin-bottom:10px}}
.hero h2 a{{color:var(--ink);text-decoration:none}}
.hero h2 a:hover{{text-decoration:underline;text-underline-offset:4px;text-decoration-thickness:1px}}
.hero .lede{{font:400 15px/1.7 'DM Sans',sans-serif;color:var(--mut);max-width:520px}}
.two-col{{display:grid;grid-template-columns:1fr 1px 1fr;gap:0;border-top:1px solid var(--ln);padding-top:24px}}
.col{{padding:0 28px}}
.col:first-child{{padding-left:0}}
.col:last-child{{padding-right:0}}
.col-rule{{background:var(--ln)}}
.col-head{{font:700 9px 'Space Mono',monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);margin-bottom:14px}}
.story{{padding:14px 0;border-bottom:1px solid var(--ln)}}
.story h3{{font:400 17px/1.3 'Instrument Serif',serif}}
.story h3 a{{color:var(--ink);text-decoration:none}}
.story h3 a:hover{{color:var(--mut)}}
.story span{{font:700 9px 'Space Mono',monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);display:block;margin-top:4px}}
.story.quote p{{font:400 15px/1.5 'Instrument Serif',serif;font-style:italic}}
.story.quote span{{font-weight:400;text-transform:none;letter-spacing:0;font-family:'DM Sans',sans-serif;font-size:11px}}
</style></head>
<body data-theme="light">
<div class="masthead">
  <div class="date">Wednesday, 12 March 2026</div>
  <h1>Finance Radar</h1>
</div>
<hr class="rule thick">
<div class="nav-row">
  <a class="active">Home</a><span class="sep">·</span>
  <a>News</a><span class="sep">·</span>
  <a>Telegram</a><span class="sep">·</span>
  <a>Reports</a><span class="sep">·</span>
  <a>YouTube</a><span class="sep">·</span>
  <a>Twitter</a>
</div>
<div class="actions-row">
  <button>AI Rankings</button><button>Voices</button><button>Bookmarks</button>
  <button onclick="document.body.dataset.theme=document.body.dataset.theme==='dark'?'light':'dark'">Theme</button>
</div>
<hr class="rule">
<main class="page">
  <div class="hero">
    <div class="kicker">{e(hero.get('source',''))}</div>
    <h2><a href="{e(hero.get('url','#'))}" target="_blank">{e(hero['title'])}</a></h2>
    <div class="lede">{e(crop(hero.get('why_it_matters',''),180))}</div>
  </div>
  <div class="two-col">
    <div class="col">
      <div class="col-head">LATEST</div>
      {col_left}
    </div>
    <div class="col-rule"></div>
    <div class="col">
      <div class="col-head">REPORTS & VOICES</div>
      {col_right}
    </div>
  </div>
</main>
</body></html>'''


def main():
    data = load()
    variants = [
        ('v1-folio', v1_folio),
        ('v2-warm-ink', v2_warm_ink),
        ('v3-mono-journal', v3_mono_journal),
        ('v4-quiet-luxury', v4_quiet_luxury),
        ('v5-stacked-rhythm', v5_stacked_rhythm),
        ('v6-broadsheet-minimal', v6_broadsheet_minimal),
    ]
    for slug, fn in variants:
        d = OUT / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / 'home.html').write_text(fn(data))
        print(f'  wrote {slug}/home.html')
    print(f'Done — {len(variants)} variations generated')

if __name__ == '__main__':
    main()
