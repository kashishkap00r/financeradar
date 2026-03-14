"""V7: Long-scroll editorial river — AI picks from all buckets, mixed shapes."""
from __future__ import annotations
import html as h
import json, random
from pathlib import Path

PROJECT = Path('/home/kashish.kapoor/vibecoding projects/financeradar')
STATIC = PROJECT / 'static'
OUT = PROJECT / 'docs' / 'plans' / 'assets' / 'from-scratch-explorations'

def load():
    # AI rankings — all buckets, all providers merged
    ai_raw = json.loads((STATIC / 'ai_rankings.json').read_text())
    picks = []
    for prov_name, prov in ai_raw.get('providers',{}).items():
        for bucket, items in prov.get('buckets',{}).items():
            for item in items:
                item['_bucket'] = bucket
                item['_provider'] = prov_name
                picks.append(item)
        break  # first provider only
    picks.sort(key=lambda x: x.get('rank', 99))

    # YouTube cache for thumbnails
    yt_raw = json.loads((STATIC / 'youtube_cache.json').read_text())
    yt_map = {}
    for items in yt_raw.values():
        for v in items:
            yt_map[v.get('link','')] = v
            yt_map[v.get('title','')] = v

    # Twitter cache for tweet details
    tw_raw = json.loads((STATIC / 'twitter_clean_cache.json').read_text())['items']
    tw_map = {}
    for t in tw_raw:
        tw_map[t.get('link','')] = t
        tw_map[t.get('title','')] = t

    # Telegram for report details
    tg_raw = json.loads((STATIC / 'telegram_reports.json').read_text())['reports']
    tg_map = {}
    for r in tg_raw:
        tg_map[r.get('url','')] = r
        tg_map[r.get('text','')[:60]] = r

    # WSW clusters
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


def render_pick(item, yt_map, tw_map, tg_map, idx):
    """Render a single AI pick as the right card shape for its bucket."""
    bucket = item.get('_bucket', 'news')
    title = item.get('title', '')
    url = item.get('url', '#')
    source = item.get('source', '')
    rank = item.get('rank', '')
    why = item.get('why_it_matters', '')
    signal = item.get('signal_type', '')

    # Determine layout variant based on position and bucket
    # This creates visual rhythm — not random, but varied

    if bucket == 'youtube':
        # Find thumbnail
        yt = yt_map.get(url, {})
        thumb = yt.get('thumbnail', '')
        publisher = yt.get('publisher', source)
        return f'''<article class="card card-video">
          <div class="card-rank">{rank}</div>
          <a href="{e(url)}" target="_blank" class="video-thumb">
            <img src="{e(thumb)}" alt="" loading="lazy">
            <div class="play-btn">&#9654;</div>
          </a>
          <div class="card-body">
            <div class="card-bucket">YouTube</div>
            <h3><a href="{e(url)}" target="_blank">{e(crop(title,90))}</a></h3>
            <span class="card-source">{e(publisher)}</span>
            {f'<p class="card-why">{e(crop(why,120))}</p>' if why else ''}
          </div>
        </article>'''

    elif bucket == 'twitter':
        tw = tw_map.get(url, {})
        publisher = tw.get('publisher', source)
        tweet_text = title  # title IS the tweet text
        return f'''<article class="card card-tweet">
          <div class="card-rank">{rank}</div>
          <div class="tweet-chrome">
            <div class="tweet-avatar">{e(publisher[:1])}</div>
            <div class="tweet-handle">@{e(publisher)}</div>
            <div class="card-bucket">Twitter</div>
          </div>
          <blockquote>
            <a href="{e(url)}" target="_blank">{e(crop(tweet_text,200))}</a>
          </blockquote>
          {f'<p class="card-why">{e(crop(why,100))}</p>' if why else ''}
        </article>'''

    elif bucket == 'telegram':
        tg = tg_map.get(url, {})
        channel = tg.get('channel', source)
        views = tg.get('views', '')
        images = tg.get('images', [])
        img_html = ''
        if images:
            img_html = f'<img class="tg-img" src="{e(images[0])}" alt="" loading="lazy">'
        return f'''<article class="card card-telegram">
          <div class="card-rank">{rank}</div>
          <div class="tg-chrome">
            <div class="tg-icon">TG</div>
            <div class="card-bucket">Telegram</div>
            <span class="tg-channel">{e(channel)}</span>
            {f'<span class="tg-views">{e(views)} views</span>' if views else ''}
          </div>
          {img_html}
          <h3><a href="{e(url)}" target="_blank">{e(crop(title,120))}</a></h3>
          {f'<p class="card-why">{e(crop(why,120))}</p>' if why else ''}
        </article>'''

    elif bucket == 'reports':
        return f'''<article class="card card-report">
          <div class="card-rank">{rank}</div>
          <div class="report-chrome">
            <div class="report-icon">PDF</div>
            <div class="card-bucket">Reports</div>
          </div>
          <h3><a href="{e(url)}" target="_blank">{e(crop(title,100))}</a></h3>
          <span class="card-source">{e(source)}</span>
          {f'<p class="card-why">{e(crop(why,140))}</p>' if why else ''}
        </article>'''

    else:  # news — varies between wide and standard
        # Every 3rd news item gets a "featured" wide treatment
        is_featured = (idx % 7 == 0)
        cls = 'card-news card-featured' if is_featured else 'card-news'
        return f'''<article class="card {cls}">
          <div class="card-rank">{rank}</div>
          <div class="card-bucket">News</div>
          <h3><a href="{e(url)}" target="_blank">{e(crop(title, 120 if is_featured else 90))}</a></h3>
          <span class="card-source">{e(source)}</span>
          {f'<div class="card-signal">{e(signal)}</div>' if signal else ''}
          {f'<p class="card-why">{e(crop(why, 180 if is_featured else 120))}</p>' if why else ''}
        </article>'''


def v7_river(data):
    picks = data['picks']

    # Build the river — interleave picks with WSW breakers
    cards_html = ''
    wsw_idx = 0
    for i, pick in enumerate(picks):
        cards_html += render_pick(pick, data['yt_map'], data['tw_map'], data['tg_map'], i)

        # Insert a WSW "breaker" quote every ~10 items
        if (i + 1) % 10 == 0 and wsw_idx < len(data['wsw']):
            cl = data['wsw'][wsw_idx]
            voice = cl.get('key_voices', [{}])[0] if cl.get('key_voices') else {}
            cards_html += f'''<div class="breaker">
              <div class="breaker-line"></div>
              <div class="breaker-content">
                <div class="breaker-label">WHO SAID WHAT</div>
                <h2>{e(crop(cl['cluster_title'],60))}</h2>
                <blockquote>"{e(crop(cl.get('core_claim',''),150))}"</blockquote>
                <span>— {e(voice.get('voice',''))}, {e(voice.get('role',''))}</span>
              </div>
              <div class="breaker-line"></div>
            </div>'''
            wsw_idx += 1

    return f'''<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>V7 — Editorial River</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Space+Mono:wght@400;700&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0}}
:root{{
  --bg:#fefefe;--ink:#111;--mut:#888;--ln:#e8e6e2;--acc:#111;
  --card-bg:#fff;--tweet-bg:#f8f7f5;--report-bg:#f5f3ef;--tg-bg:#f0f4f8;
}}
[data-theme="dark"]{{
  --bg:#0b0b0a;--ink:#eae8e4;--mut:#6a6864;--ln:#282624;--acc:#eae8e4;
  --card-bg:#141413;--tweet-bg:#161714;--report-bg:#151412;--tg-bg:#111418;
}}
body{{background:var(--bg);color:var(--ink);font-family:'DM Sans',sans-serif;-webkit-font-smoothing:antialiased}}

/* ── Top bar ── */
.topbar{{display:flex;align-items:baseline;padding:24px 48px 16px;max-width:1200px;margin:0 auto}}
.logo{{font:400 22px 'Instrument Serif',serif}}
.right{{margin-left:auto;display:flex;gap:14px}}
.right button{{background:none;border:none;font:400 11px 'Space Mono',monospace;color:var(--mut);cursor:pointer}}
.right button:hover{{color:var(--ink)}}
.tabs{{max-width:1200px;margin:0 auto;display:flex;gap:24px;padding:0 48px 14px;border-bottom:1px solid var(--ln)}}
.tabs a{{font:400 14px 'DM Sans',sans-serif;color:var(--mut);text-decoration:none}}
.tabs a.active{{color:var(--ink);font-weight:600;text-decoration:underline;text-underline-offset:6px;text-decoration-thickness:1.5px}}

/* ── River grid ── */
.river{{
  max-width:1200px;margin:0 auto;padding:32px 48px 80px;
  display:grid;
  grid-template-columns:repeat(12,1fr);
  gap:20px;
  align-items:start;
}}

/* ── Cards — base ── */
.card{{
  padding:24px;border:1px solid var(--ln);background:var(--card-bg);
  position:relative;
}}
.card-rank{{
  font:700 32px 'Space Mono',monospace;color:var(--ln);
  position:absolute;top:16px;right:20px;line-height:1;
}}
.card-bucket{{
  font:700 9px 'Space Mono',monospace;letter-spacing:.12em;text-transform:uppercase;
  color:var(--mut);margin-bottom:8px;
}}
.card h3{{font:400 18px/1.3 'Instrument Serif',serif;margin-bottom:6px}}
.card h3 a{{color:var(--ink);text-decoration:none}}
.card h3 a:hover{{color:var(--mut)}}
.card-source{{font:700 9px 'Space Mono',monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);display:block;margin-bottom:6px}}
.card-signal{{display:inline-block;font:400 10px 'Space Mono',monospace;color:var(--acc);border:1px solid var(--ln);padding:2px 8px;margin-bottom:6px}}
.card-why{{font:400 13px/1.6 'DM Sans',sans-serif;color:var(--mut);margin-top:8px}}

/* ── News cards ── */
.card-news{{grid-column:span 4}}
.card-featured{{
  grid-column:span 8;
  padding:36px;
}}
.card-featured h3{{font-size:28px;line-height:1.15;margin-bottom:10px}}
.card-featured .card-rank{{font-size:48px}}

/* ── Video cards ── */
.card-video{{grid-column:span 6;padding:0;overflow:hidden}}
.video-thumb{{display:block;position:relative}}
.video-thumb img{{width:100%;aspect-ratio:16/9;object-fit:cover;display:block}}
.play-btn{{
  position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
  width:56px;height:56px;background:rgba(0,0,0,.6);color:#fff;
  border-radius:50%;display:flex;align-items:center;justify-content:center;
  font-size:20px;padding-left:3px;
}}
.card-video .card-body{{padding:20px 24px 24px}}
.card-video .card-rank{{top:auto;bottom:16px;right:20px;color:rgba(255,255,255,.4)}}
.card-video h3{{font-size:17px}}

/* ── Tweet cards ── */
.card-tweet{{grid-column:span 4;background:var(--tweet-bg);padding:28px}}
.tweet-chrome{{display:flex;align-items:center;gap:8px;margin-bottom:12px}}
.tweet-avatar{{
  width:28px;height:28px;border-radius:50%;background:var(--ln);
  display:flex;align-items:center;justify-content:center;
  font:600 12px 'DM Sans',sans-serif;color:var(--mut);
}}
.tweet-handle{{font:400 12px 'Space Mono',monospace;color:var(--mut)}}
.card-tweet blockquote{{font:400 16px/1.45 'Instrument Serif',serif;font-style:italic;margin:0;padding:0;border:none}}
.card-tweet blockquote a{{color:var(--ink);text-decoration:none}}
.card-tweet blockquote a:hover{{color:var(--mut)}}

/* ── Telegram cards ── */
.card-telegram{{grid-column:span 4;background:var(--tg-bg)}}
.tg-chrome{{display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap}}
.tg-icon{{font:700 9px 'Space Mono',monospace;background:var(--ink);color:var(--bg);padding:3px 6px;letter-spacing:.06em}}
.tg-channel{{font:400 11px 'Space Mono',monospace;color:var(--mut)}}
.tg-views{{font:400 10px 'Space Mono',monospace;color:var(--mut);margin-left:auto}}
.tg-img{{width:100%;border-radius:2px;margin-bottom:10px;max-height:180px;object-fit:cover}}

/* ── Report cards ── */
.card-report{{grid-column:span 4;background:var(--report-bg)}}
.report-chrome{{display:flex;align-items:center;gap:8px;margin-bottom:10px}}
.report-icon{{
  font:700 9px 'Space Mono',monospace;letter-spacing:.06em;
  border:1.5px solid var(--ink);padding:3px 7px;
}}

/* ── WSW Breakers ── */
.breaker{{
  grid-column:1/-1;
  display:grid;grid-template-columns:1fr auto 1fr;gap:24px;
  align-items:center;padding:40px 0;
}}
.breaker-line{{height:1px;background:var(--ln)}}
.breaker-content{{text-align:center;max-width:600px}}
.breaker-label{{font:700 9px 'Space Mono',monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--mut);margin-bottom:10px}}
.breaker h2{{font:400 24px/1.2 'Instrument Serif',serif;margin-bottom:10px}}
.breaker blockquote{{font:400 15px/1.55 'Instrument Serif',serif;font-style:italic;color:var(--mut);margin:0;padding:0;border:none}}
.breaker span{{font:400 11px 'DM Sans',sans-serif;color:var(--mut);display:block;margin-top:8px}}

/* ── Responsive ── */
@media(max-width:1000px){{
  .river{{grid-template-columns:repeat(6,1fr);padding:20px 24px 60px}}
  .card-news,.card-tweet,.card-telegram,.card-report{{grid-column:span 3}}
  .card-featured{{grid-column:span 6}}
  .card-video{{grid-column:span 6}}
}}
@media(max-width:640px){{
  .river{{grid-template-columns:1fr;padding:16px 16px 48px}}
  .card,.card-news,.card-featured,.card-video,.card-tweet,.card-telegram,.card-report{{grid-column:span 1}}
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
{cards_html}
</div>
</body></html>'''


def main():
    data = load()
    d = OUT / 'v7-river'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'home.html').write_text(v7_river(data))
    print(f'  wrote v7-river/home.html ({len(data["picks"])} AI picks)')

if __name__ == '__main__':
    main()
