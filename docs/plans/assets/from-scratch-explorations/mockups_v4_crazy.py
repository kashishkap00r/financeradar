"""V8: FULL CRAZY editorial river — every content type gets a dramatically different card."""
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

    yt_raw = json.loads((STATIC / 'youtube_cache.json').read_text())
    yt_map = {}
    for items in yt_raw.values():
        for v in items:
            yt_map[v.get('link','')] = v

    tw_raw = json.loads((STATIC / 'twitter_clean_cache.json').read_text())['items']
    tw_map = {}
    for t in tw_raw:
        tw_map[t.get('link','')] = t

    tg_raw = json.loads((STATIC / 'telegram_reports.json').read_text())['reports']
    tg_map = {}
    for r in tg_raw:
        tg_map[r.get('url','')] = r

    wsw_raw = json.loads((STATIC / 'wsw_clusters.json').read_text())
    wsw = []
    for prov in wsw_raw.get('providers',{}).values():
        wsw = prov.get('clusters',[])[:6]
        break

    return dict(picks=picks, yt_map=yt_map, tw_map=tw_map, tg_map=tg_map, wsw=wsw)

def e(s): return h.escape(str(s or ''), quote=True)
def crop(s, n=80):
    s = str(s or '').strip()
    return s if len(s)<=n else s[:n-1].rstrip()+'…'


def render_card(item, data, idx):
    bucket = item.get('_bucket', 'news')
    title = item.get('title', '')
    url = item.get('url', '#')
    source = item.get('source', '')
    rank = item.get('rank', '')
    why = item.get('why_it_matters', '')
    signal = item.get('signal_type', '')

    if bucket == 'youtube':
        yt = data['yt_map'].get(url, {})
        thumb = yt.get('thumbnail', '')
        publisher = yt.get('publisher', source)
        # Alternating: landscape wide vs portrait-ish tall
        if idx % 2 == 0:
            return f'''<article class="c c-yt c-yt-wide">
              <a href="{e(url)}" target="_blank" class="yt-thumb">
                <img src="{e(thumb)}" alt="" loading="lazy">
                <div class="yt-play">&#9654;</div>
                <div class="yt-badge">YOUTUBE</div>
                <div class="yt-dur">#{rank}</div>
              </a>
              <div class="yt-body">
                <h3><a href="{e(url)}" target="_blank">{e(crop(title,100))}</a></h3>
                <span class="meta">{e(publisher)}</span>
                {f'<p class="why">{e(crop(why,140))}</p>' if why else ''}
              </div>
            </article>'''
        else:
            return f'''<article class="c c-yt c-yt-stack">
              <a href="{e(url)}" target="_blank" class="yt-thumb">
                <img src="{e(thumb)}" alt="" loading="lazy">
                <div class="yt-play">&#9654;</div>
              </a>
              <div class="yt-body">
                <div class="yt-badge-sm">YT · #{rank}</div>
                <h3><a href="{e(url)}" target="_blank">{e(crop(title,80))}</a></h3>
                <span class="meta">{e(publisher)}</span>
              </div>
            </article>'''

    elif bucket == 'twitter':
        tw = data['tw_map'].get(url, {})
        publisher = tw.get('publisher', source)
        handle = publisher.replace(' ','')
        # Big quote card
        return f'''<article class="c c-tw">
          <div class="tw-bar"></div>
          <div class="tw-inner">
            <div class="tw-top">
              <div class="tw-avi">{e(publisher[:1])}</div>
              <div>
                <div class="tw-name">{e(publisher)}</div>
                <div class="tw-handle">@{e(handle)}</div>
              </div>
              <div class="tw-badge">TWEET · #{rank}</div>
            </div>
            <blockquote><a href="{e(url)}" target="_blank">{e(crop(title,220))}</a></blockquote>
            {f'<p class="why">{e(crop(why,120))}</p>' if why else ''}
          </div>
        </article>'''

    elif bucket == 'telegram':
        tg = data['tg_map'].get(url, {})
        channel = tg.get('channel', source)
        views = tg.get('views', '')
        images = tg.get('images', [])
        img_html = f'<img class="tg-hero" src="{e(images[0])}" alt="" loading="lazy">' if images else ''
        # Tall card with optional image
        return f'''<article class="c c-tg">
          <div class="tg-stripe"></div>
          {img_html}
          <div class="tg-body">
            <div class="tg-top">
              <span class="tg-icon">TG</span>
              <span class="tg-ch">{e(channel)}</span>
              {f'<span class="tg-views">{e(views)} views</span>' if views else ''}
              <span class="tg-rank">#{rank}</span>
            </div>
            <h3><a href="{e(url)}" target="_blank">{e(crop(title,130))}</a></h3>
            {f'<p class="why">{e(crop(why,140))}</p>' if why else ''}
          </div>
        </article>'''

    elif bucket == 'reports':
        # Document-style card with heavy left border
        return f'''<article class="c c-rpt">
          <div class="rpt-left">
            <div class="rpt-doc">
              <div class="rpt-lines"><div></div><div></div><div></div><div></div><div></div></div>
              <div class="rpt-label">PDF</div>
            </div>
            <div class="rpt-rank">#{rank}</div>
          </div>
          <div class="rpt-right">
            <div class="rpt-badge">REPORT</div>
            <h3><a href="{e(url)}" target="_blank">{e(crop(title,100))}</a></h3>
            <span class="meta">{e(source)}</span>
            {f'<p class="why">{e(crop(why,160))}</p>' if why else ''}
          </div>
        </article>'''

    else:  # news
        is_hero = (idx % 8 == 0)
        is_mid = (idx % 8 == 3)
        if is_hero:
            return f'''<article class="c c-news c-hero">
              <div class="hero-rank">{rank}</div>
              <div class="hero-signal">{e(signal)}</div>
              <h2><a href="{e(url)}" target="_blank">{e(crop(title,120))}</a></h2>
              <span class="meta">{e(source)}</span>
              {f'<p class="hero-why">{e(crop(why,220))}</p>' if why else ''}
            </article>'''
        elif is_mid:
            return f'''<article class="c c-news c-news-wide">
              <div class="nw-left">
                <div class="nw-badge">NEWS · #{rank}</div>
                <h3><a href="{e(url)}" target="_blank">{e(crop(title,100))}</a></h3>
                <span class="meta">{e(source)}</span>
              </div>
              <div class="nw-right">
                {f'<p class="why">{e(crop(why,180))}</p>' if why else ''}
                {f'<div class="nw-signal">{e(signal)}</div>' if signal else ''}
              </div>
            </article>'''
        else:
            return f'''<article class="c c-news c-news-std">
              <div class="ns-badge">NEWS</div>
              <div class="ns-rank">{rank}</div>
              <h3><a href="{e(url)}" target="_blank">{e(crop(title,85))}</a></h3>
              <span class="meta">{e(source)}</span>
              {f'<div class="ns-signal">{e(signal)}</div>' if signal else ''}
              {f'<p class="why">{e(crop(why,120))}</p>' if why else ''}
            </article>'''


def wsw_breaker(cl):
    voices_html = ''
    for v in cl.get('key_voices',[])[:3]:
        voices_html += f'''<div class="wsw-voice">
          <div class="wsw-v-name">{e(v.get('voice',''))}</div>
          <div class="wsw-v-role">{e(v.get('role',''))}</div>
          <div class="wsw-v-claim">"{e(crop(v.get('claim',''),100))}"</div>
        </div>'''
    return f'''<div class="breaker">
      <div class="breaker-top">
        <div class="breaker-tag">WHO SAID WHAT</div>
        <div class="breaker-theme">{e(cl.get('theme',''))}</div>
      </div>
      <h2>{e(cl['cluster_title'])}</h2>
      <p class="breaker-claim">"{e(crop(cl.get('core_claim',''),180))}"</p>
      <div class="wsw-voices">{voices_html}</div>
    </div>'''


def generate(data):
    cards = ''
    wsw_i = 0
    for i, pick in enumerate(data['picks']):
        cards += render_card(pick, data, i)
        if (i+1) % 10 == 0 and wsw_i < len(data['wsw']):
            cards += wsw_breaker(data['wsw'][wsw_i])
            wsw_i += 1

    return f'''<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>V8 — Full Crazy River</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Space+Mono:wght@400;700&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#faf9f7;--ink:#111;--mut:#888;--ln:#e4e2de;--acc:#111;
  --card:#fff;--tw:#f0ede6;--tg:#eaf0f6;--rpt:#f4f1ea;
  --yt-accent:#ff0033;--tw-accent:#1a8cd8;--tg-accent:#229ed9;--rpt-accent:#8b6914;
}}
[data-theme="dark"]{{
  --bg:#0b0b0a;--ink:#e8e6e0;--mut:#706e68;--ln:#262420;--acc:#e8e6e0;
  --card:#151413;--tw:#181714;--tg:#121820;--rpt:#181610;
  --yt-accent:#ff4455;--tw-accent:#4aa3e0;--tg-accent:#44b4e8;--rpt-accent:#c4a040;
}}
body{{background:var(--bg);color:var(--ink);font-family:'DM Sans',sans-serif;-webkit-font-smoothing:antialiased}}

.topbar{{display:flex;align-items:baseline;padding:20px 40px 14px;max-width:1280px;margin:0 auto}}
.logo{{font:400 22px 'Instrument Serif',serif}}
.right{{margin-left:auto;display:flex;gap:12px}}
.right button{{background:none;border:none;font:400 11px 'Space Mono',monospace;color:var(--mut);cursor:pointer}}
.right button:hover{{color:var(--ink)}}
.tabs{{max-width:1280px;margin:0 auto;display:flex;gap:22px;padding:0 40px 12px;border-bottom:1px solid var(--ln)}}
.tabs a{{font:400 14px 'DM Sans',sans-serif;color:var(--mut);text-decoration:none}}
.tabs a.active{{color:var(--ink);font-weight:600;text-decoration:underline;text-underline-offset:6px;text-decoration-thickness:1.5px}}

/* ── RIVER GRID ── */
.river{{
  max-width:1280px;margin:0 auto;padding:24px 40px 80px;
  display:grid;grid-template-columns:repeat(12,1fr);gap:16px;align-items:start;
}}

/* ── Shared card bits ── */
.c{{background:var(--card);position:relative;overflow:hidden}}
h2,h3{{font-family:'Instrument Serif',serif;font-weight:400}}
h3{{font-size:17px;line-height:1.3}}
h3 a,.c h2 a{{color:var(--ink);text-decoration:none}}
h3 a:hover,.c h2 a:hover{{color:var(--mut)}}
.meta{{font:700 9px 'Space Mono',monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);display:block;margin-top:4px}}
.why{{font:400 13px/1.6 'DM Sans',sans-serif;color:var(--mut);margin-top:8px}}

/* ══════════════════════════════════════════
   NEWS CARDS
   ══════════════════════════════════════════ */
.c-hero{{
  grid-column:span 8;padding:48px 44px;
  border:none;border-bottom:3px solid var(--ink);
}}
.hero-rank{{font:700 72px 'Space Mono',monospace;color:var(--ln);position:absolute;top:24px;right:32px;line-height:1}}
.hero-signal{{font:700 10px 'Space Mono',monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--mut);margin-bottom:10px}}
.c-hero h2{{font-size:36px;line-height:1.1;margin-bottom:10px;max-width:680px}}
.hero-why{{font:400 15px/1.65 'DM Sans',sans-serif;color:var(--mut);margin-top:12px;max-width:600px}}

.c-news-wide{{
  grid-column:span 8;display:grid;grid-template-columns:1fr 1fr;
  border:1px solid var(--ln);
}}
.nw-left{{padding:24px;border-right:1px solid var(--ln)}}
.nw-right{{padding:24px;display:flex;flex-direction:column;justify-content:center}}
.nw-badge,.ns-badge{{font:700 9px 'Space Mono',monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--mut);margin-bottom:8px}}
.nw-signal,.ns-signal{{display:inline-block;font:400 10px 'Space Mono',monospace;border:1px solid var(--ln);padding:2px 8px;margin-top:8px;color:var(--mut)}}
.nw-left h3{{font-size:20px}}

.c-news-std{{
  grid-column:span 4;padding:24px;border:1px solid var(--ln);
}}
.ns-rank{{font:700 36px 'Space Mono',monospace;color:var(--ln);position:absolute;top:16px;right:18px;line-height:1}}

/* ══════════════════════════════════════════
   YOUTUBE CARDS
   ══════════════════════════════════════════ */
.c-yt{{border:none;overflow:hidden}}
.c-yt-wide{{
  grid-column:span 8;display:grid;grid-template-columns:1.2fr 1fr;
}}
.c-yt-stack{{grid-column:span 4}}
.yt-thumb{{display:block;position:relative;background:#000}}
.yt-thumb img{{width:100%;display:block;aspect-ratio:16/9;object-fit:cover}}
.yt-play{{
  position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
  width:64px;height:64px;background:rgba(0,0,0,.7);backdrop-filter:blur(4px);
  border-radius:50%;display:flex;align-items:center;justify-content:center;
  color:#fff;font-size:22px;padding-left:4px;
}}
.yt-badge{{
  position:absolute;top:12px;left:12px;
  font:700 9px 'Space Mono',monospace;letter-spacing:.1em;
  background:var(--yt-accent);color:#fff;padding:4px 10px;
}}
.yt-dur{{
  position:absolute;bottom:12px;right:12px;
  font:700 11px 'Space Mono',monospace;
  background:rgba(0,0,0,.75);color:#fff;padding:3px 8px;
}}
.yt-body{{padding:20px 24px 24px;background:var(--card);border:1px solid var(--ln);border-top:none}}
.yt-badge-sm{{font:700 9px 'Space Mono',monospace;letter-spacing:.1em;color:var(--yt-accent);margin-bottom:6px}}

/* ══════════════════════════════════════════
   TWEET CARDS
   ══════════════════════════════════════════ */
.c-tw{{grid-column:span 4;background:var(--tw);display:flex;overflow:visible}}
.tw-bar{{width:4px;background:var(--tw-accent);flex-shrink:0}}
.tw-inner{{padding:24px;flex:1}}
.tw-top{{display:flex;align-items:center;gap:10px;margin-bottom:14px}}
.tw-avi{{
  width:36px;height:36px;border-radius:50%;background:var(--tw-accent);
  color:#fff;display:flex;align-items:center;justify-content:center;
  font:700 14px 'DM Sans',sans-serif;flex-shrink:0;
}}
.tw-name{{font:600 13px 'DM Sans',sans-serif}}
.tw-handle{{font:400 11px 'Space Mono',monospace;color:var(--mut)}}
.tw-badge{{font:700 9px 'Space Mono',monospace;letter-spacing:.08em;color:var(--tw-accent);margin-left:auto}}
.c-tw blockquote{{font:400 17px/1.45 'Instrument Serif',serif;font-style:italic;border:none;margin:0}}
.c-tw blockquote a{{color:var(--ink);text-decoration:none}}
.c-tw blockquote a:hover{{color:var(--mut)}}

/* ══════════════════════════════════════════
   TELEGRAM CARDS
   ══════════════════════════════════════════ */
.c-tg{{grid-column:span 4;background:var(--tg);position:relative}}
.tg-stripe{{position:absolute;top:0;left:0;right:0;height:4px;background:var(--tg-accent)}}
.tg-hero{{width:100%;max-height:200px;object-fit:cover;display:block}}
.tg-body{{padding:20px}}
.tg-top{{display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap}}
.tg-icon{{font:700 9px 'Space Mono',monospace;letter-spacing:.06em;background:var(--tg-accent);color:#fff;padding:3px 7px}}
.tg-ch{{font:500 11px 'Space Mono',monospace;color:var(--mut)}}
.tg-views{{font:400 10px 'Space Mono',monospace;color:var(--mut)}}
.tg-rank{{margin-left:auto;font:700 10px 'Space Mono',monospace;color:var(--tg-accent)}}

/* ══════════════════════════════════════════
   REPORT CARDS
   ══════════════════════════════════════════ */
.c-rpt{{
  grid-column:span 6;display:grid;grid-template-columns:80px 1fr;
  background:var(--rpt);border:1px solid var(--ln);
}}
.rpt-left{{
  padding:20px 0;display:flex;flex-direction:column;align-items:center;gap:12px;
  border-right:1px solid var(--ln);
}}
.rpt-doc{{
  width:48px;height:60px;border:1.5px solid var(--rpt-accent);position:relative;
  display:flex;flex-direction:column;justify-content:center;align-items:center;gap:4px;padding:8px;
}}
.rpt-lines div{{width:28px;height:2px;background:var(--rpt-accent);opacity:.3}}
.rpt-label{{
  position:absolute;bottom:-1px;right:-1px;
  font:700 8px 'Space Mono',monospace;letter-spacing:.1em;
  background:var(--rpt-accent);color:#fff;padding:2px 5px;
}}
.rpt-rank{{font:700 11px 'Space Mono',monospace;color:var(--rpt-accent)}}
.rpt-right{{padding:20px 24px}}
.rpt-badge{{font:700 9px 'Space Mono',monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--rpt-accent);margin-bottom:8px}}
.c-rpt h3{{font-size:19px}}

/* ══════════════════════════════════════════
   WSW BREAKERS
   ══════════════════════════════════════════ */
.breaker{{
  grid-column:1/-1;padding:48px 0;
  border-top:2px solid var(--ink);border-bottom:2px solid var(--ink);
  margin:8px 0;
}}
.breaker-top{{display:flex;align-items:baseline;gap:16px;margin-bottom:12px}}
.breaker-tag{{font:700 10px 'Space Mono',monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--mut)}}
.breaker-theme{{font:400 12px 'DM Sans',sans-serif;color:var(--mut)}}
.breaker h2{{font:400 30px/1.15 'Instrument Serif',serif;margin-bottom:10px;max-width:700px}}
.breaker-claim{{font:400 16px/1.55 'Instrument Serif',serif;font-style:italic;color:var(--mut);max-width:650px}}
.wsw-voices{{display:flex;gap:20px;margin-top:20px;overflow-x:auto;padding-bottom:4px}}
.wsw-voice{{min-width:200px;padding:16px;border:1px solid var(--ln);background:var(--card);flex-shrink:0}}
.wsw-v-name{{font:600 12px 'DM Sans',sans-serif}}
.wsw-v-role{{font:400 10px 'Space Mono',monospace;color:var(--mut);margin-bottom:6px}}
.wsw-v-claim{{font:400 13px/1.5 'Instrument Serif',serif;font-style:italic;color:var(--mut)}}

/* ── Responsive ── */
@media(max-width:1000px){{
  .river{{grid-template-columns:repeat(6,1fr);padding:16px 20px 60px}}
  .c-hero,.c-news-wide,.c-yt-wide,.c-rpt{{grid-column:span 6}}
  .c-news-std,.c-tw,.c-tg,.c-yt-stack{{grid-column:span 3}}
}}
@media(max-width:640px){{
  .river{{grid-template-columns:1fr}}
  .c,.c-hero,.c-news-wide,.c-news-std,.c-yt-wide,.c-yt-stack,.c-tw,.c-tg,.c-rpt{{grid-column:span 1}}
  .c-yt-wide{{grid-template-columns:1fr}}
  .c-news-wide{{grid-template-columns:1fr}}
  .c-rpt{{grid-template-columns:60px 1fr}}
}}
</style></head>
<body data-theme="light">
<div class="topbar">
  <div class="logo">Finance Radar</div>
  <div class="right">
    <button>Bookmarks</button>
    <button onclick="document.body.dataset.theme=document.body.dataset.theme==='dark'?'light':'dark'">Theme</button>
  </div>
</div>
<div class="tabs">
  <a class="active">Home</a><a>News</a><a>Telegram</a><a>Reports</a><a>YouTube</a><a>Twitter</a>
</div>
<div class="river">
{cards}
</div>
</body></html>'''


def main():
    data = load()
    d = OUT / 'v8-crazy-river'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'home.html').write_text(generate(data))
    print(f'wrote v8-crazy-river/home.html ({len(data["picks"])} picks)')

if __name__ == '__main__':
    main()
