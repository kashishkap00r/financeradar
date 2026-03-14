"""Generate 4 lightweight homepage mockups for visual review."""
from __future__ import annotations
import html as h
import json
from pathlib import Path

PROJECT = Path('/home/kashish.kapoor/vibecoding projects/financeradar')
STATIC = PROJECT / 'static'
OUT = PROJECT / 'docs' / 'plans' / 'assets' / 'from-scratch-explorations'

# ── Load real data ──────────────────────────────────────────────
def load():
    articles = json.loads((STATIC / 'articles.json').read_text())['articles'][:30]

    tg_raw = json.loads((STATIC / 'telegram_reports.json').read_text())['reports'][:10]

    reports_raw = json.loads((STATIC / 'reports_cache.json').read_text())
    reports = []
    for items in reports_raw.values():
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
        break  # first provider only
    ai.sort(key=lambda x: x.get('rank',99))
    ai = ai[:12]

    wsw_raw = json.loads((STATIC / 'wsw_clusters.json').read_text())
    wsw = []
    for prov in wsw_raw.get('providers',{}).values():
        wsw = prov.get('clusters',[])[:5]
        break

    return dict(articles=articles, telegram=tg_raw, reports=reports,
                videos=videos, twitter=tw, ai=ai, wsw=wsw)

def e(s): return h.escape(str(s or ''), quote=True)
def crop(s, n=80):
    s = str(s or '').strip()
    return s if len(s)<=n else s[:n-1].rstrip()+'…'

def time_short(dt_str):
    if not dt_str: return ''
    return dt_str[:10]  # just the date portion

# ── C1: Command Center ─────────────────────────────────────────
def c1_command_center(data):
    # Build AI briefing rows
    ai_rows = ''
    for item in data['ai'][:8]:
        ai_rows += f'''<tr>
          <td class="rank">{item.get('rank','')}</td>
          <td><a href="{e(item.get('url','#'))}" target="_blank">{e(crop(item['title'],72))}</a></td>
          <td class="src">{e(crop(item.get('source',''),20))}</td>
        </tr>'''

    # Latest signals
    signal_rows = ''
    for i, art in enumerate(data['articles'][:12]):
        signal_rows += f'''<div class="signal-row">
          <span class="ts">{time_short(art.get('date',''))}</span>
          <span class="src-badge">{e(crop(art['source'],16))}</span>
          <a href="{e(art['url'])}" target="_blank">{e(crop(art['title'],70))}</a>
        </div>'''

    # WSW digest
    wsw_html = ''
    for cl in data['wsw'][:4]:
        voices = ''
        for v in cl.get('key_voices',[])[:2]:
            voices += f'<div class="voice">{e(crop(v.get("voice",""),20))}: {e(crop(v.get("claim",""),60))}</div>'
        wsw_html += f'''<div class="wsw-item">
          <div class="wsw-title">{e(crop(cl['cluster_title'],50))}</div>
          {voices}
        </div>'''

    # Reports mini
    rpt_rows = ''
    for r in data['reports'][:4]:
        rpt_rows += f'<div class="signal-row"><span class="src-badge">{e(r.get("publisher",""))}</span><a href="{e(r.get("link","#"))}" target="_blank">{e(crop(r["title"],60))}</a></div>'

    return f'''<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>C1 — Command Center</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@500;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0}}
:root{{--bg:#f8f9fc;--sf:#fff;--ink:#1e293b;--mut:#64748b;--ln:#e2e8f0;--acc:#3b82f6}}
[data-theme="dark"]{{--bg:#0a0e1a;--sf:#111827;--ink:#e2e8f0;--mut:#94a3b8;--ln:#1e293b;--acc:#60a5fa}}
body{{background:var(--bg);color:var(--ink);font-family:'Inter',sans-serif;-webkit-font-smoothing:antialiased}}
.topbar{{height:44px;background:var(--sf);border-bottom:1px solid var(--ln);display:flex;align-items:center;padding:0 20px;gap:16px}}
.logo{{font:500 13px 'JetBrains Mono',monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--ink)}}
.logo span{{color:var(--acc)}}
.status{{font:400 11px 'JetBrains Mono',monospace;color:var(--mut);margin-left:auto}}
.topbar button{{background:none;border:1px solid var(--ln);color:var(--mut);padding:4px 10px;font:400 11px 'JetBrains Mono',monospace;cursor:pointer}}
.topbar button:hover{{color:var(--ink)}}
.tabs{{display:flex;gap:0;background:var(--sf);border-bottom:1px solid var(--ln);padding:0 20px}}
.tab{{padding:10px 16px;font:500 11px 'JetBrains Mono',monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--mut);text-decoration:none;border-bottom:2px solid transparent;cursor:pointer}}
.tab.active{{color:var(--ink);border-bottom-color:var(--acc)}}
.tab:hover{{color:var(--ink)}}
.shell{{display:grid;grid-template-columns:1fr 1.4fr .9fr;gap:1px;background:var(--ln);margin:0;min-height:calc(100vh - 88px)}}
.col{{background:var(--bg);padding:16px}}
.col-head{{font:700 10px 'JetBrains Mono',monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--acc);padding-bottom:10px;border-bottom:1px solid var(--ln);margin-bottom:12px}}
table{{width:100%;border-collapse:collapse}}
td{{padding:6px 8px;font-size:12.5px;border-bottom:1px solid var(--ln);vertical-align:top}}
td.rank{{font:500 11px 'JetBrains Mono',monospace;color:var(--acc);width:24px}}
td.src{{font:400 10px 'JetBrains Mono',monospace;color:var(--mut);width:90px;text-align:right}}
td a{{color:var(--ink);text-decoration:none}}
td a:hover{{color:var(--acc)}}
.signal-row{{display:grid;grid-template-columns:auto auto 1fr;gap:8px;padding:7px 0;border-bottom:1px solid var(--ln);align-items:baseline;font-size:12.5px}}
.signal-row a{{color:var(--ink);text-decoration:none}}
.signal-row a:hover{{color:var(--acc)}}
.ts{{font:400 10px 'JetBrains Mono',monospace;color:var(--mut);white-space:nowrap}}
.src-badge{{font:500 9px 'JetBrains Mono',monospace;letter-spacing:.06em;text-transform:uppercase;color:var(--sf);background:var(--mut);padding:1px 5px;white-space:nowrap;max-width:100px;overflow:hidden;text-overflow:ellipsis}}
.wsw-item{{padding:10px 0;border-bottom:1px solid var(--ln)}}
.wsw-title{{font:600 12px 'DM Sans',sans-serif;margin-bottom:4px}}
.voice{{font:400 11px 'Inter',sans-serif;color:var(--mut);line-height:1.4;margin-top:3px}}
.status-bar{{position:fixed;bottom:0;left:0;right:0;height:24px;background:var(--sf);border-top:1px solid var(--ln);display:flex;align-items:center;padding:0 16px;gap:16px}}
.status-bar span{{font:400 10px 'JetBrains Mono',monospace;color:var(--mut)}}
.status-bar .ok{{color:#22c55e}}
</style></head>
<body data-theme="light">
<div class="topbar">
  <div class="logo">FINANCE<span>.</span>RADAR</div>
  <button>AI</button><button>WSW</button><button>Bookmarks</button>
  <div class="status">{len(data['articles'])} articles · updated {time_short(data['articles'][0].get('date',''))}</div>
  <button onclick="document.body.dataset.theme=document.body.dataset.theme==='dark'?'light':'dark'">THEME</button>
</div>
<div class="tabs">
  <a class="tab active">Home</a><a class="tab">News</a><a class="tab">Telegram</a>
  <a class="tab">Reports</a><a class="tab">YouTube</a><a class="tab">Twitter</a>
</div>
<div class="shell">
  <div class="col">
    <div class="col-head">PRIORITY BRIEFING</div>
    <table>{ai_rows}</table>
  </div>
  <div class="col">
    <div class="col-head">LATEST SIGNALS</div>
    {signal_rows}
    <div class="col-head" style="margin-top:20px">REPORTS</div>
    {rpt_rows}
  </div>
  <div class="col">
    <div class="col-head">WSW DIGEST</div>
    {wsw_html}
  </div>
</div>
<div class="status-bar">
  <span class="ok">● ALL FEEDS OK</span>
  <span>News: {len(data['articles'])}</span>
  <span>Reports: {len(data['reports'])}</span>
  <span>Videos: {len(data['videos'])}</span>
  <span>Tweets: {len(data['twitter'])}</span>
</div>
</body></html>'''


# ── C2: Editorial Broadsheet ───────────────────────────────────
def c2_editorial_broadsheet(data):
    hero = data['ai'][0] if data['ai'] else data['articles'][0]
    hero_title = hero.get('title','')
    hero_source = hero.get('source','')
    hero_why = hero.get('why_it_matters','')

    top_stories = ''
    for art in data['articles'][:6]:
        top_stories += f'''<div class="story">
          <h3><a href="{e(art['url'])}" target="_blank">{e(crop(art['title'],90))}</a></h3>
          <div class="byline">{e(art['source'])} · {time_short(art.get('date',''))}</div>
        </div>'''

    reports_col = ''
    for r in data['reports'][:5]:
        reports_col += f'''<div class="story">
          <h3><a href="{e(r.get('link','#'))}" target="_blank">{e(crop(r['title'],80))}</a></h3>
          <div class="byline">{e(r.get('publisher',''))} · {e(r.get('region',''))}</div>
        </div>'''

    wsw_quotes = ''
    for cl in data['wsw'][:3]:
        voice = cl.get('key_voices',[{}])[0] if cl.get('key_voices') else {}
        wsw_quotes += f'''<div class="pull-quote">
          <div class="quote-mark">"</div>
          <div class="quote-text">{e(crop(cl.get('core_claim',''),120))}</div>
          <div class="quote-attr">— {e(voice.get('voice',''))}, on {e(crop(cl['cluster_title'],40))}</div>
        </div>'''

    return f'''<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>C2 — Editorial Broadsheet</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=Inter:wght@400;500&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0}}
:root{{--bg:#faf6f1;--sf:#fff;--ink:#1a1a1a;--mut:#6b5e50;--ln:#d4cdc4;--acc:#990f3d}}
[data-theme="dark"]{{--bg:#1a1610;--sf:#231f19;--ink:#e8ddd0;--mut:#9c8e7e;--ln:#342e26;--acc:#d4634a}}
body{{background:var(--bg);color:var(--ink);font-family:'Source Serif 4',serif;-webkit-font-smoothing:antialiased}}
.masthead{{text-align:center;padding:28px 20px 0}}
.masthead-date{{font:400 11px 'Inter',sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);margin-bottom:8px}}
.masthead h1{{font:400 48px/1 'Playfair Display',serif;font-style:italic;letter-spacing:-.02em}}
.masthead-rule{{border:none;border-top:1px solid var(--ln);margin:14px auto;width:min(100%,900px)}}
.masthead-rule.double{{border-top:3px double var(--ln)}}
.nav{{display:flex;justify-content:center;gap:28px;padding:10px 0 14px;border-bottom:1px solid var(--ln)}}
.nav a{{font:500 12px 'Inter',sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--mut);text-decoration:none;font-variant:small-caps}}
.nav a.active{{color:var(--ink);font-weight:700}}
.nav a:hover{{color:var(--acc)}}
.actions-row{{display:flex;justify-content:center;gap:16px;padding:10px 0;margin-bottom:8px}}
.actions-row button{{background:none;border:1px solid var(--ln);padding:6px 14px;font:400 11px 'Inter',sans-serif;letter-spacing:.06em;color:var(--mut);cursor:pointer}}
.actions-row button:hover{{color:var(--ink);border-color:var(--ink)}}
.page{{max-width:1100px;margin:0 auto;padding:0 24px 40px}}
.hero{{padding:32px 0;text-align:center;border-bottom:1px solid var(--ln)}}
.hero h2{{font:700 36px/1.1 'Playfair Display',serif;max-width:700px;margin:0 auto 12px;letter-spacing:-.01em}}
.hero h2 a{{color:var(--ink);text-decoration:none}}
.hero h2 a:hover{{color:var(--acc)}}
.hero .byline{{font:400 13px 'Inter',sans-serif;color:var(--mut)}}
.hero .lede{{font:400 16px/1.6 'Source Serif 4',serif;color:var(--mut);max-width:600px;margin:10px auto 0}}
.three-col{{display:grid;grid-template-columns:1fr 1px 1fr 1px 1fr;gap:0;padding-top:24px}}
.rule-v{{background:var(--ln)}}
.col{{padding:0 24px}}
.col-label{{font:500 11px 'Inter',sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--acc);padding-bottom:8px;border-bottom:1px solid var(--ln);margin-bottom:14px;font-variant:small-caps}}
.story{{padding:12px 0;border-bottom:1px solid var(--ln)}}
.story h3{{font:600 17px/1.25 'Playfair Display',serif;margin-bottom:4px}}
.story h3 a{{color:var(--ink);text-decoration:none}}
.story h3 a:hover{{color:var(--acc)}}
.byline{{font:400 11px/1.4 'Inter',sans-serif;color:var(--mut)}}
.pull-quote{{padding:16px 0;border-bottom:1px solid var(--ln)}}
.quote-mark{{font:400 48px/0.8 'Playfair Display',serif;color:var(--acc);margin-bottom:-4px}}
.quote-text{{font:400 14px/1.5 'Source Serif 4',serif;font-style:italic;color:var(--ink)}}
.quote-attr{{font:400 11px 'Inter',sans-serif;color:var(--mut);margin-top:6px}}
</style></head>
<body data-theme="light">
<header class="masthead">
  <div class="masthead-date">Wednesday, 12 March 2026</div>
  <h1>FinanceRadar</h1>
  <hr class="masthead-rule double">
</header>
<nav class="nav">
  <a class="active">Home</a><a>News</a><a>Telegram</a><a>Reports</a><a>YouTube</a><a>Twitter</a>
</nav>
<div class="actions-row">
  <button>AI Rankings</button><button>Who Said What</button><button>Bookmarks</button>
  <button onclick="document.body.dataset.theme=document.body.dataset.theme==='dark'?'light':'dark'">Theme</button>
</div>
<main class="page">
  <div class="hero">
    <h2><a href="{e(hero.get('url',hero.get('link','#')))}" target="_blank">{e(hero_title)}</a></h2>
    <div class="byline">{e(hero_source)}</div>
    <div class="lede">{e(crop(hero_why, 180))}</div>
  </div>
  <div class="three-col">
    <div class="col">
      <div class="col-label">Top Stories</div>
      {top_stories}
    </div>
    <div class="rule-v"></div>
    <div class="col">
      <div class="col-label">Market Intelligence</div>
      {reports_col}
    </div>
    <div class="rule-v"></div>
    <div class="col">
      <div class="col-label">Voices</div>
      {wsw_quotes}
    </div>
  </div>
</main>
</body></html>'''


# ── C3: Data Dashboard ─────────────────────────────────────────
def c3_data_dashboard(data):
    # Spotlight card
    spot = data['ai'][0] if data['ai'] else data['articles'][0]

    # AI summary rows
    ai_list = ''
    for item in data['ai'][:5]:
        ai_list += f'''<div class="rank-row">
          <span class="rank-num">{item.get('rank','')}</span>
          <div class="rank-body">
            <a href="{e(item.get('url','#'))}" target="_blank">{e(crop(item['title'],65))}</a>
            <span class="rank-src">{e(item.get('source',''))}</span>
          </div>
        </div>'''

    # News cards
    news_cards = ''
    for art in data['articles'][:6]:
        news_cards += f'''<div class="card">
          <div class="card-top"><span class="dot" style="background:var(--acc)"></span><span class="card-src">{e(art['source'])}</span><span class="card-time">{time_short(art.get('date',''))}</span></div>
          <a class="card-title" href="{e(art['url'])}" target="_blank">{e(crop(art['title'],80))}</a>
        </div>'''

    # Video cards
    vid_cards = ''
    for v in data['videos'][:3]:
        vid_cards += f'''<div class="vid-card">
          <img src="{e(v.get('thumbnail',''))}" alt="" loading="lazy">
          <div class="vid-info">
            <a href="{e(v['link'])}" target="_blank">{e(crop(v['title'],55))}</a>
            <span>{e(v.get('publisher',''))}</span>
          </div>
        </div>'''

    # WSW horizontal
    wsw_chips = ''
    for cl in data['wsw'][:4]:
        wsw_chips += f'''<div class="wsw-chip">
          <div class="wsw-theme">{e(crop(cl['cluster_title'],40))}</div>
          <div class="wsw-claim">{e(crop(cl.get('core_claim',''),80))}</div>
        </div>'''

    return f'''<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>C3 — Data Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0}}
:root{{--bg:#f5f5f5;--sf:#fff;--ink:#171717;--mut:#737373;--ln:#e5e5e5;--acc:#6366f1;--r:12px}}
[data-theme="dark"]{{--bg:#0a0a0a;--sf:#171717;--ink:#fafafa;--mut:#a3a3a3;--ln:#262626;--acc:#818cf8}}
body{{background:var(--bg);color:var(--ink);font-family:'Inter',sans-serif;-webkit-font-smoothing:antialiased}}
.layout{{display:grid;grid-template-columns:200px 1fr;min-height:100vh}}
.sidebar{{background:var(--sf);border-right:1px solid var(--ln);padding:16px 0}}
.sb-logo{{padding:12px 16px;font:700 15px 'Inter',sans-serif}}
.sb-logo span{{color:var(--acc)}}
.sb-nav{{display:grid;gap:2px;padding:8px}}
.sb-item{{display:flex;align-items:center;gap:10px;padding:9px 14px;font:500 13px 'Inter',sans-serif;color:var(--mut);text-decoration:none;border-radius:8px;border-left:3px solid transparent;cursor:pointer}}
.sb-item:hover{{background:var(--bg)}}
.sb-item.active{{color:var(--ink);background:var(--bg);border-left-color:var(--acc)}}
.sb-item .cnt{{margin-left:auto;font:500 11px 'Geist Mono',monospace;color:var(--acc)}}
.main{{padding:0}}
.topbar{{height:52px;display:flex;align-items:center;padding:0 24px;gap:12px;border-bottom:1px solid var(--ln)}}
.search{{flex:1;max-width:480px;margin:0 auto;background:var(--bg);border:1px solid var(--ln);border-radius:999px;padding:8px 16px;font:400 13px 'Inter',sans-serif;color:var(--mut)}}
.topbar button{{background:var(--sf);border:1px solid var(--ln);border-radius:999px;padding:6px 12px;font:500 11px 'Inter',sans-serif;color:var(--mut);cursor:pointer}}
.topbar button:hover{{color:var(--ink)}}
.content{{padding:24px}}
.bento{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
.bento-card{{background:var(--sf);border:1px solid var(--ln);border-radius:var(--r);padding:20px;position:relative;overflow:hidden}}
.bento-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--acc),transparent)}}
.bento-label{{font:600 10px 'Geist Mono',monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--acc);margin-bottom:10px}}
.spot-title{{font:700 20px/1.25 'Inter',sans-serif;margin-bottom:6px}}
.spot-title a{{color:var(--ink);text-decoration:none}}
.spot-title a:hover{{color:var(--acc)}}
.spot-src{{font:400 12px 'Inter',sans-serif;color:var(--mut)}}
.rank-row{{display:flex;gap:10px;padding:7px 0;border-bottom:1px solid var(--ln);align-items:baseline}}
.rank-num{{font:500 12px 'Geist Mono',monospace;color:var(--acc);min-width:20px}}
.rank-body a{{font:500 13px 'Inter',sans-serif;color:var(--ink);text-decoration:none;display:block}}
.rank-body a:hover{{color:var(--acc)}}
.rank-src{{font:400 11px 'Inter',sans-serif;color:var(--mut)}}
.triple{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:16px}}
.card{{background:var(--sf);border:1px solid var(--ln);border-radius:var(--r);padding:14px}}
.card:hover{{box-shadow:0 4px 12px rgba(0,0,0,.06);transform:translateY(-1px);transition:.15s}}
.card-top{{display:flex;align-items:center;gap:6px;margin-bottom:8px}}
.dot{{width:6px;height:6px;border-radius:50%;flex-shrink:0}}
.card-src{{font:500 11px 'Inter',sans-serif;color:var(--mut)}}
.card-time{{margin-left:auto;font:400 10px 'Geist Mono',monospace;color:var(--mut)}}
.card-title{{font:600 14px/1.35 'Inter',sans-serif;color:var(--ink);text-decoration:none;display:block}}
.card-title:hover{{color:var(--acc)}}
.full-strip{{background:var(--sf);border:1px solid var(--ln);border-radius:var(--r);padding:16px;display:flex;gap:16px;overflow-x:auto}}
.wsw-chip{{min-width:220px;padding:12px;border:1px solid var(--ln);border-radius:8px;flex-shrink:0}}
.wsw-theme{{font:600 12px 'Inter',sans-serif;margin-bottom:4px}}
.wsw-claim{{font:400 11px 'Inter',sans-serif;color:var(--mut);line-height:1.4}}
.vids{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:16px}}
.vid-card{{background:var(--sf);border:1px solid var(--ln);border-radius:var(--r);overflow:hidden}}
.vid-card img{{width:100%;aspect-ratio:16/9;object-fit:cover;display:block}}
.vid-info{{padding:10px}}
.vid-info a{{font:600 13px/1.3 'Inter',sans-serif;color:var(--ink);text-decoration:none;display:block}}
.vid-info a:hover{{color:var(--acc)}}
.vid-info span{{font:400 11px 'Inter',sans-serif;color:var(--mut)}}
</style></head>
<body data-theme="light">
<div class="layout">
  <nav class="sidebar">
    <div class="sb-logo">Finance<span>Radar</span></div>
    <div class="sb-nav">
      <a class="sb-item active"><span>Home</span></a>
      <a class="sb-item"><span>News</span><span class="cnt">{len(data['articles'])}</span></a>
      <a class="sb-item"><span>Telegram</span><span class="cnt">{len(data['telegram'])}</span></a>
      <a class="sb-item"><span>Reports</span><span class="cnt">{len(data['reports'])}</span></a>
      <a class="sb-item"><span>YouTube</span><span class="cnt">{len(data['videos'])}</span></a>
      <a class="sb-item"><span>Twitter</span><span class="cnt">{len(data['twitter'])}</span></a>
    </div>
  </nav>
  <div class="main">
    <div class="topbar">
      <div class="search">Search articles... ⌘/</div>
      <button>AI</button><button>WSW</button><button>★</button>
      <button onclick="document.body.dataset.theme=document.body.dataset.theme==='dark'?'light':'dark'">Theme</button>
    </div>
    <div class="content">
      <div class="bento">
        <div class="bento-card">
          <div class="bento-label">SPOTLIGHT</div>
          <div class="spot-title"><a href="{e(spot.get('url',spot.get('link','#')))}" target="_blank">{e(crop(spot['title'],90))}</a></div>
          <div class="spot-src">{e(spot.get('source',''))} · {e(spot.get('signal_type',''))}</div>
        </div>
        <div class="bento-card">
          <div class="bento-label">AI RANKINGS</div>
          {ai_list}
        </div>
      </div>
      <div class="triple">{news_cards}</div>
      <div class="full-strip">{wsw_chips}</div>
      <div class="vids">{vid_cards}</div>
    </div>
  </div>
</div>
</body></html>'''


# ── C4: Magazine Spread ─────────────────────────────────────────
def c4_magazine_spread(data):
    hero = data['ai'][0] if data['ai'] else data['articles'][0]

    secondary = ''
    for art in data['articles'][:4]:
        secondary += f'''<div class="sec-story">
          <h3><a href="{e(art['url'])}" target="_blank">{e(crop(art['title'],75))}</a></h3>
          <div class="sec-src">{e(art['source'])}</div>
        </div>'''

    # Section previews
    def section_block(title, items, is_report=False):
        rows = ''
        for it in items[:3]:
            t = it.get('title','')
            u = it.get('url', it.get('link','#'))
            s = it.get('publisher', it.get('source',''))
            rows += f'''<div class="sec-row">
              <a href="{e(u)}" target="_blank">{e(crop(t,70))}</a>
              <span>{e(s)}</span>
            </div>'''
        return f'<div class="section"><h2>{title}</h2>{rows}</div>'

    sections = section_block('Latest News', data['articles'][4:7])
    sections += section_block('Reports', data['reports'][:3], True)
    sections += section_block('Videos', data['videos'][:3])
    sections += section_block('Twitter', data['twitter'][:3])

    return f'''<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>C4 — Magazine Spread</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Space+Mono:wght@400;700&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0}}
:root{{--bg:#fefefe;--sf:#f9f9f7;--ink:#111;--mut:#888;--ln:#ebebeb;--acc:#111}}
[data-theme="dark"]{{--bg:#0c0c0c;--sf:#161616;--ink:#f0f0f0;--mut:#666;--ln:#2a2a2a;--acc:#fff}}
body{{background:var(--bg);color:var(--ink);font-family:'DM Sans',sans-serif;-webkit-font-smoothing:antialiased}}
.topbar{{height:80px;display:flex;align-items:center;padding:0 48px}}
.logo{{font:400 24px 'Instrument Serif',serif}}
.topbar-actions{{margin-left:auto;display:flex;gap:12px}}
.topbar-actions button{{background:none;border:none;font:400 12px 'Space Mono',monospace;color:var(--mut);cursor:pointer;padding:6px}}
.topbar-actions button:hover{{color:var(--ink)}}
.nav{{display:flex;gap:32px;padding:0 48px 20px;border-bottom:1px solid var(--ln)}}
.nav a{{font:400 16px 'DM Sans',sans-serif;color:var(--mut);text-decoration:none}}
.nav a.active{{color:var(--ink);font-weight:600;text-decoration:underline;text-underline-offset:8px;text-decoration-thickness:2px}}
.nav a:hover{{color:var(--ink)}}
.issue-label{{position:fixed;top:20px;right:48px;font:700 9px 'Space Mono',monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--mut);writing-mode:vertical-rl}}
.page{{max-width:1100px;margin:0 auto;padding:0 48px 60px}}
.hero-grid{{display:grid;grid-template-columns:1.5fr 1fr;gap:48px;padding:48px 0;border-bottom:1px solid var(--ln)}}
.hero-main h2{{font:400 46px/1.08 'Instrument Serif',serif;letter-spacing:-.02em;margin-bottom:16px}}
.hero-main h2 a{{color:var(--ink);text-decoration:none}}
.hero-main h2 a:hover{{text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:4px}}
.hero-src{{font:700 10px 'Space Mono',monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--mut)}}
.hero-lede{{font:400 16px/1.6 'DM Sans',sans-serif;color:var(--mut);margin-top:12px;max-width:500px}}
.hero-side{{display:flex;flex-direction:column;gap:0}}
.sec-story{{padding:20px 0;border-bottom:1px solid var(--ln)}}
.sec-story h3{{font:400 18px/1.3 'Instrument Serif',serif}}
.sec-story h3 a{{color:var(--ink);text-decoration:none}}
.sec-story h3 a:hover{{color:var(--mut)}}
.sec-src{{font:700 9px 'Space Mono',monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--mut);margin-top:4px}}
.sections{{display:grid;grid-template-columns:1fr 1fr;gap:48px 64px;padding:48px 0}}
.section h2{{font:400 30px 'Instrument Serif',serif;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--ln)}}
.sec-row{{padding:12px 0;border-bottom:1px solid var(--ln)}}
.sec-row a{{font:400 16px/1.35 'Instrument Serif',serif;color:var(--ink);text-decoration:none;display:block}}
.sec-row a:hover{{color:var(--mut)}}
.sec-row span{{font:700 9px 'Space Mono',monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--mut);display:block;margin-top:4px}}
</style></head>
<body data-theme="light">
<div class="issue-label">Issue · Mar 2026</div>
<header class="topbar">
  <div class="logo">Finance Radar</div>
  <div class="topbar-actions">
    <button>Search</button><button>AI</button><button>WSW</button><button>★</button>
    <button onclick="document.body.dataset.theme=document.body.dataset.theme==='dark'?'light':'dark'">Theme</button>
  </div>
</header>
<nav class="nav">
  <a class="active">Home</a><a>News</a><a>Telegram</a><a>Reports</a><a>YouTube</a><a>Twitter</a>
</nav>
<main class="page">
  <div class="hero-grid">
    <div class="hero-main">
      <div class="hero-src">{e(hero.get('source',''))}</div>
      <h2><a href="{e(hero.get('url',hero.get('link','#')))}" target="_blank">{e(hero['title'])}</a></h2>
      <div class="hero-lede">{e(crop(hero.get('why_it_matters',''),180))}</div>
    </div>
    <div class="hero-side">{secondary}</div>
  </div>
  <div class="sections">{sections}</div>
</main>
</body></html>'''


# ── Main ────────────────────────────────────────────────────────
def main():
    data = load()
    generators = [
        ('c1-command-center', c1_command_center),
        ('c2-editorial-broadsheet', c2_editorial_broadsheet),
        ('c3-data-dashboard', c3_data_dashboard),
        ('c4-magazine-spread', c4_magazine_spread),
    ]
    for slug, fn in generators:
        html_content = fn(data)
        (OUT / slug / 'home.html').write_text(html_content)
        print(f'  wrote {slug}/home.html')
    print('Done — 4 mockups generated')

if __name__ == '__main__':
    main()
