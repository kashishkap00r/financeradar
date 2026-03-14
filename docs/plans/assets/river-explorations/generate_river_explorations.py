#!/usr/bin/env python3
"""Generate 4 river exploration prototypes from FinanceRadar data."""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
BASE = Path(__file__).resolve().parent
PROJECT = BASE.parents[3]  # financeradar root
STATIC = PROJECT / "static"


# ─── Data Loading ────────────────────────────────────────────────────────────

def load_json(path):
    if not path.exists():
        print(f"  Warning: {path.name} not found, skipping")
        return None
    with open(path) as f:
        return json.load(f)


def parse_date(s):
    """Parse ISO date string to datetime."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def build_river():
    """Merge all data sources into a unified river array."""
    river = []
    ai_urls = set()
    ai_rank_map = {}
    cluster_url_map = {}

    # Load AI rankings — collect URLs of AI picks
    ai_data = load_json(STATIC / "ai_rankings.json")
    if ai_data:
        for provider_key, provider in ai_data.get("providers", {}).items():
            for bucket_name, items in provider.get("buckets", {}).items():
                for item in items:
                    url = item.get("url", "")
                    if url:
                        ai_urls.add(url)
                        if url not in ai_rank_map or item.get("rank", 999) < ai_rank_map[url]:
                            ai_rank_map[url] = item.get("rank", 999)
            break  # Use first provider only

    # Load WSW clusters — map URLs to cluster info
    wsw_data = load_json(STATIC / "wsw_clusters.json")
    clusters_out = []
    if wsw_data:
        for provider_key, provider in wsw_data.get("providers", {}).items():
            for cluster in provider.get("clusters", []):
                cid = f"c{cluster.get('rank', 0)}"
                clusters_out.append({
                    "id": cid,
                    "rank": cluster.get("rank", 0),
                    "cluster_title": cluster.get("cluster_title", ""),
                    "theme": cluster.get("theme", ""),
                    "core_claim": cluster.get("core_claim", ""),
                    "quote_snippet": cluster.get("quote_snippet", ""),
                    "quote_speaker": cluster.get("quote_speaker", ""),
                    "why_it_matters": cluster.get("why_it_matters", ""),
                    "related_urls": [
                        cluster.get("source_url_primary", ""),
                        cluster.get("source_url_secondary", ""),
                    ],
                })
                for url in [cluster.get("source_url_primary", ""), cluster.get("source_url_secondary", "")]:
                    if url:
                        cluster_url_map[url] = cid
            break  # Use first provider only

    def make_item(title, source, lane, url, date_str, meta=""):
        dt = parse_date(date_str)
        is_pick = url in ai_urls
        return {
            "title": title.strip() if title else "(untitled)",
            "source": source or "Unknown",
            "lane": lane,
            "meta": meta,
            "url": url or "",
            "is_ai_pick": is_pick,
            "ai_rank": ai_rank_map.get(url, None) if is_pick else None,
            "cluster_id": cluster_url_map.get(url),
            "time": date_str or "",
            "time_bucket": dt.astimezone(IST).strftime("%H:00") if dt else "",
            "time_short": dt.astimezone(IST).strftime("%H:%M") if dt else "",
            "date_label": dt.astimezone(IST).strftime("%b %d") if dt else "",
        }

    # Articles (news)
    articles = load_json(STATIC / "articles.json")
    if articles:
        for a in articles.get("articles", []):
            cat = a.get("category", "News")
            lane_map = {"News": "NW", "Videos": "YT", "Twitter": "TW", "Reports": "RP", "Telegram": "TG"}
            lane = lane_map.get(cat, "NW")
            river.append(make_item(a["title"], a.get("source", ""), lane, a.get("url", ""), a.get("date", "")))

    # Telegram reports
    tg = load_json(STATIC / "telegram_reports.json")
    if tg:
        for r in tg.get("reports", []):
            title = r.get("text", "")[:120].split("\n")[0]
            river.append(make_item(title, r.get("channel", "Telegram"), "TG", r.get("url", ""), r.get("date", "")))

    # YouTube
    yt = load_json(STATIC / "youtube_cache.json")
    if yt:
        for feed_id, videos in yt.items():
            if not isinstance(videos, list):
                continue
            for v in videos:
                river.append(make_item(v["title"], v.get("source", "YouTube"), "YT", v.get("link", ""), v.get("date", ""),
                                       meta=v.get("video_id", "")))

    # Twitter
    tw = load_json(STATIC / "twitter_clean_cache.json")
    if tw:
        for item in tw.get("items", []):
            river.append(make_item(item["title"], item.get("source", "Twitter"), "TW", item.get("link", ""), item.get("date", "")))

    # Reports
    rp = load_json(STATIC / "reports_cache.json")
    if rp:
        for feed_id, reports in rp.items():
            if not isinstance(reports, list):
                continue
            for r in reports:
                river.append(make_item(r["title"], r.get("source", feed_id), "RP", r.get("link", ""), r.get("date", ""),
                                       meta=r.get("description", "")[:100]))

    # Papers
    pp = load_json(STATIC / "papers_cache.json")
    if pp:
        for feed_id, papers in pp.items():
            if not isinstance(papers, list):
                continue
            for p in papers:
                river.append(make_item(p["title"], p.get("source", feed_id), "PP", p.get("link", ""), p.get("date", "")))

    # Sort by time descending, limit to most recent 300
    river.sort(key=lambda x: x["time"] or "", reverse=True)
    river = river[:300]

    return river, clusters_out


def save_sample_data(river, clusters):
    with open(BASE / "sample_data.json", "w") as f:
        json.dump({"river": river, "clusters": clusters}, f, indent=2, ensure_ascii=False)
    print(f"  Wrote sample_data.json ({len(river)} items, {len(clusters)} clusters)")


# ─── HTML Generation ─────────────────────────────────────────────────────────

def dark_mode_toggle_css():
    return """
    .dm-toggle { position: fixed; top: 12px; right: 12px; z-index: 9999;
      background: none; border: 1px solid currentColor; border-radius: 4px;
      padding: 4px 10px; font-size: 12px; cursor: pointer; color: inherit;
      font-family: inherit; opacity: 0.6; }
    .dm-toggle:hover { opacity: 1; }
    """


def dark_mode_toggle_js():
    return """
    <script>
    (function(){
      const btn = document.querySelector('.dm-toggle');
      const root = document.documentElement;
      function toggle() {
        const dark = root.classList.toggle('dark');
        btn.textContent = dark ? '☀' : '☾';
        localStorage.setItem('river-dark', dark ? '1' : '0');
      }
      btn.addEventListener('click', toggle);
      if (localStorage.getItem('river-dark') === '1') {
        root.classList.add('dark');
        btn.textContent = '☀';
      }
    })();
    </script>
    """


# ─── Prototype 1: The Ledger ─────────────────────────────────────────────────

def generate_ledger(river, clusters):
    items_json = json.dumps(river[:200], ensure_ascii=False)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>River Exploration 1: The Ledger</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  :root {{ --ink: #1a1a1a; --sec: #767676; --paper: #f5f3ef; --accent: #2563eb; }}
  html.dark {{ --ink: #d4d4d4; --sec: #888; --paper: #141414; --accent: #60a5fa; }}
  {dark_mode_toggle_css()}
  body {{ font-family: 'IBM Plex Mono', monospace; font-size: 12.5px; line-height: 1;
    background: var(--paper); color: var(--ink); padding: 20px 24px; }}
  header {{ display: flex; align-items: baseline; gap: 16px; margin-bottom: 16px;
    border-bottom: 2px solid var(--ink); padding-bottom: 8px; }}
  header h1 {{ font-size: 14px; font-weight: 500; letter-spacing: 0.05em; text-transform: uppercase; }}
  header .count {{ font-size: 11px; color: var(--sec); }}
  .river {{ display: grid; grid-template-columns: 46px 28px 1fr 20px;
    gap: 0; }}
  .row {{ display: contents; }}
  .row > * {{ padding: 5px 6px; border-bottom: 1px solid color-mix(in srgb, var(--ink) 8%, transparent);
    line-height: 18px; height: 28px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }}
  .row:hover > * {{ background: color-mix(in srgb, var(--accent) 6%, transparent); }}
  .row.ai > * {{ border-left: 2px solid var(--accent); }}
  .row.ai > :first-child {{ border-left: 2px solid var(--accent); }}
  .time {{ color: var(--sec); font-size: 11px; }}
  .src {{ color: var(--sec); font-size: 10px; font-weight: 500; text-align: center; }}
  .title a {{ color: var(--ink); text-decoration: none; }}
  .title a:hover {{ text-decoration: underline; }}
  .lane {{ color: var(--sec); font-size: 10px; text-align: center; }}
  .lane-NW::after {{ content: '·'; }}
  .lane-TG::after {{ content: '▸'; }}
  .lane-RP::after {{ content: '◆'; }}
  .lane-YT::after {{ content: '▶'; }}
  .lane-TW::after {{ content: '✕'; }}
  .lane-PP::after {{ content: '◇'; }}
  .legend {{ display: flex; gap: 16px; margin-top: 12px; padding-top: 8px;
    border-top: 1px solid color-mix(in srgb, var(--ink) 15%, transparent);
    font-size: 10px; color: var(--sec); }}
  .legend span {{ display: flex; align-items: center; gap: 4px; }}
  .legend .swatch {{ width: 2px; height: 12px; background: var(--accent); }}
</style>
</head>
<body>
<button class="dm-toggle">☾</button>
<header>
  <h1>The Ledger</h1>
  <span class="count" id="count"></span>
</header>
<div class="river" id="river"></div>
<div class="legend">
  <span><span class="swatch"></span> AI Pick</span>
  <span>· News</span><span>▸ Telegram</span><span>◆ Reports</span>
  <span>▶ YouTube</span><span>✕ Twitter</span><span>◇ Papers</span>
</div>
<script>
const DATA = {items_json};
const river = document.getElementById('river');
document.getElementById('count').textContent = DATA.length + ' items';
DATA.forEach(item => {{
  const ai = item.is_ai_pick ? ' ai' : '';
  const srcCode = item.lane || 'NW';
  river.insertAdjacentHTML('beforeend',
    '<div class="row' + ai + '">' +
    '<span class="time">' + (item.time_short || '') + '</span>' +
    '<span class="src">' + srcCode + '</span>' +
    '<span class="title"><a href="' + item.url + '" target="_blank" rel="noopener">' +
      item.title + '</a></span>' +
    '<span class="lane lane-' + srcCode + '"></span>' +
    '</div>'
  );
}});
</script>
{dark_mode_toggle_js()}
</body>
</html>"""
    return html


# ─── Prototype 2: The Broadsheet ─────────────────────────────────────────────

def generate_broadsheet(river, clusters):
    items_json = json.dumps(river[:150], ensure_ascii=False)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>River Exploration 2: The Broadsheet</title>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,600&family=Public+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  :root {{ --bg: #fff1e5; --ink: #1a1a1a; --rule: #ccc1b7; --meta: #7d7168; }}
  html.dark {{ --bg: #1a1510; --ink: #d4c8b8; --rule: #3d352c; --meta: #8a7e72; }}
  {dark_mode_toggle_css()}
  body {{ font-family: 'Public Sans', sans-serif; font-size: 12px;
    background: var(--bg); color: var(--ink); max-width: 1100px; margin: 0 auto; padding: 32px 24px; }}

  /* Masthead */
  .masthead {{ text-align: center; border-bottom: 3px double var(--rule); padding-bottom: 12px; margin-bottom: 20px; }}
  .masthead h1 {{ font-family: 'Newsreader', serif; font-size: 36px; font-weight: 600;
    letter-spacing: 0.02em; }}
  .masthead .date {{ font-size: 11px; color: var(--meta); margin-top: 4px; text-transform: uppercase;
    letter-spacing: 0.1em; }}

  /* Lead story */
  .lead {{ border-bottom: 1px solid var(--rule); padding-bottom: 16px; margin-bottom: 20px; }}
  .lead h2 {{ font-family: 'Newsreader', serif; font-size: 28px; font-weight: 600; line-height: 1.2;
    margin-bottom: 6px; }}
  .lead h2 a {{ color: var(--ink); text-decoration: none; }}
  .lead h2 a:hover {{ text-decoration: underline; }}
  .lead .meta {{ font-size: 11px; color: var(--meta); }}

  /* Column flow */
  .columns {{ column-count: 3; column-gap: 28px; column-rule: 1px solid var(--rule); }}
  @media (max-width: 800px) {{ .columns {{ column-count: 2; }} }}
  @media (max-width: 500px) {{ .columns {{ column-count: 1; }} }}

  .item {{ break-inside: avoid; margin-bottom: 14px; padding-bottom: 10px;
    border-bottom: 1px solid color-mix(in srgb, var(--rule) 50%, transparent); }}
  .item h3 {{ font-family: 'Newsreader', serif; font-weight: 600; line-height: 1.25; margin-bottom: 3px; }}
  .item h3 a {{ color: var(--ink); text-decoration: none; }}
  .item h3 a:hover {{ text-decoration: underline; }}
  .item .meta {{ font-size: 10px; color: var(--meta); text-transform: uppercase; letter-spacing: 0.04em; }}
  .item .via {{ font-weight: 500; }}
</style>
</head>
<body>
<button class="dm-toggle">☾</button>
<div class="masthead">
  <h1>The Broadsheet</h1>
  <div class="date" id="date-line"></div>
</div>
<div id="lead" class="lead"></div>
<div id="columns" class="columns"></div>
<script>
const DATA = {items_json};

// Date line
const now = new Date();
document.getElementById('date-line').textContent =
  now.toLocaleDateString('en-IN', {{ weekday:'long', year:'numeric', month:'long', day:'numeric' }});

// Separate lead from rest — use top AI pick or first item
const lead = DATA.find(d => d.is_ai_pick) || DATA[0];
const rest = DATA.filter(d => d !== lead);

// Font sizes by rank tier
function fontSize(item, idx) {{
  if (item.ai_rank && item.ai_rank <= 3) return '20px';
  if (item.ai_rank && item.ai_rank <= 10) return '16px';
  if (idx < 20) return '14px';
  return '13px';
}}

function viaLabel(lane) {{
  const map = {{ TG: 'VIA TELEGRAM', YT: 'VIA YOUTUBE', TW: 'VIA TWITTER', RP: 'VIA RESEARCH', PP: 'VIA PAPER' }};
  return map[lane] || '';
}}

// Render lead
const leadEl = document.getElementById('lead');
leadEl.innerHTML =
  '<h2><a href="' + lead.url + '" target="_blank">' + lead.title + '</a></h2>' +
  '<div class="meta">' + lead.source + (lead.time_short ? ' · ' + lead.time_short : '') +
  (viaLabel(lead.lane) ? ' · <span class="via">' + viaLabel(lead.lane) + '</span>' : '') + '</div>';

// Render columns
const cols = document.getElementById('columns');
rest.forEach((item, idx) => {{
  const via = viaLabel(item.lane);
  cols.insertAdjacentHTML('beforeend',
    '<div class="item">' +
    '<h3 style="font-size:' + fontSize(item, idx) + '"><a href="' + item.url + '" target="_blank">' +
      item.title + '</a></h3>' +
    '<div class="meta">' + item.source + (item.time_short ? ' · ' + item.time_short : '') +
      (via ? ' · <span class="via">' + via + '</span>' : '') + '</div>' +
    '</div>'
  );
}});
</script>
{dark_mode_toggle_js()}
</body>
</html>"""
    return html


# ─── Prototype 3: The Tide Chart ─────────────────────────────────────────────

def generate_tide_chart(river, clusters):
    items_json = json.dumps(river[:250], ensure_ascii=False)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>River Exploration 3: The Tide Chart</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  :root {{ --bg: #fafafa; --ink: #1c1c1c; --sec: #888; --border: #e5e5e5;
    --nw: #94a3b8; --tg: #60a5fa; --rp: #a78bfa; --yt: #f87171; --tw: #38bdf8; --pp: #86efac; }}
  html.dark {{ --bg: #111; --ink: #d4d4d4; --sec: #666; --border: #2a2a2a;
    --nw: #64748b; --tg: #3b82f6; --rp: #7c3aed; --yt: #ef4444; --tw: #0ea5e9; --pp: #22c55e; }}
  {dark_mode_toggle_css()}
  body {{ font-family: 'Inter', sans-serif; font-size: 11px;
    background: var(--bg); color: var(--ink); overflow-x: auto; }}

  header {{ position: sticky; left: 0; padding: 16px 20px; display: flex;
    align-items: center; gap: 16px; border-bottom: 1px solid var(--border); }}
  header h1 {{ font-size: 14px; font-weight: 600; }}
  .filter-toggle {{ font-size: 10px; padding: 3px 8px; border: 1px solid var(--border);
    border-radius: 3px; background: none; color: var(--ink); cursor: pointer; font-family: inherit; }}
  .filter-toggle.active {{ background: var(--ink); color: var(--bg); }}

  .timeline {{ display: flex; gap: 0; padding: 16px 20px; min-width: min-content;
    scroll-snap-type: x mandatory; }}
  .hour {{ flex: 0 0 220px; scroll-snap-align: start; border-right: 1px solid var(--border);
    padding: 0 10px; }}
  .hour-label {{ font-size: 13px; font-weight: 600; color: var(--sec); margin-bottom: 8px;
    position: sticky; top: 0; background: var(--bg); padding: 4px 0; }}
  .chip {{ display: flex; align-items: center; gap: 5px; padding: 3px 6px; margin-bottom: 2px;
    border-radius: 3px; min-height: 24px; cursor: pointer; position: relative;
    border-left: 3px solid var(--nw); }}
  .chip:hover {{ background: color-mix(in srgb, var(--ink) 5%, transparent); }}
  .chip[data-lane="TG"] {{ border-left-color: var(--tg); }}
  .chip[data-lane="RP"] {{ border-left-color: var(--rp); }}
  .chip[data-lane="YT"] {{ border-left-color: var(--yt); }}
  .chip[data-lane="TW"] {{ border-left-color: var(--tw); }}
  .chip[data-lane="PP"] {{ border-left-color: var(--pp); }}
  .chip .dot {{ width: 5px; height: 5px; border-radius: 50%; background: var(--ink); flex-shrink: 0;
    display: none; }}
  .chip.ai .dot {{ display: block; }}
  .chip .text {{ overflow: hidden; white-space: nowrap; text-overflow: ellipsis; font-size: 11px; }}
  .chip a {{ color: var(--ink); text-decoration: none; }}
  .chip:hover a {{ text-decoration: underline; }}

  .legend {{ position: sticky; left: 0; display: flex; gap: 12px; padding: 12px 20px;
    border-top: 1px solid var(--border); font-size: 10px; color: var(--sec); }}
  .legend span {{ display: flex; align-items: center; gap: 4px; }}
  .legend .sw {{ width: 12px; height: 3px; border-radius: 1px; }}
</style>
</head>
<body>
<button class="dm-toggle">☾</button>
<header>
  <h1>The Tide Chart</h1>
  <button class="filter-toggle" id="ai-filter">AI Picks Only</button>
</header>
<div class="timeline" id="timeline"></div>
<div class="legend">
  <span><span class="sw" style="background:var(--nw)"></span>News</span>
  <span><span class="sw" style="background:var(--tg)"></span>Telegram</span>
  <span><span class="sw" style="background:var(--rp)"></span>Reports</span>
  <span><span class="sw" style="background:var(--yt)"></span>YouTube</span>
  <span><span class="sw" style="background:var(--tw)"></span>Twitter</span>
  <span><span class="sw" style="background:var(--pp)"></span>Papers</span>
  <span>● = AI Pick</span>
</div>
<script>
const DATA = {items_json};
const timeline = document.getElementById('timeline');

// Group by hour bucket
const buckets = {{}};
DATA.forEach(item => {{
  const b = item.time_bucket || '??:00';
  if (!buckets[b]) buckets[b] = [];
  buckets[b].push(item);
}});

// Sort hours descending (most recent first)
const hours = Object.keys(buckets).sort().reverse();
hours.forEach(h => {{
  const col = document.createElement('div');
  col.className = 'hour';
  col.innerHTML = '<div class="hour-label">' + h + '</div>';
  buckets[h].forEach(item => {{
    const ai = item.is_ai_pick ? ' ai' : '';
    col.insertAdjacentHTML('beforeend',
      '<div class="chip' + ai + '" data-lane="' + item.lane + '" data-ai="' + item.is_ai_pick + '">' +
      '<span class="dot"></span>' +
      '<span class="text"><a href="' + item.url + '" target="_blank" rel="noopener">' +
        item.title + '</a></span>' +
      '</div>'
    );
  }});
  timeline.appendChild(col);
}});

// AI filter toggle
let aiOnly = false;
document.getElementById('ai-filter').addEventListener('click', function() {{
  aiOnly = !aiOnly;
  this.classList.toggle('active', aiOnly);
  document.querySelectorAll('.chip').forEach(c => {{
    c.style.display = (aiOnly && c.dataset.ai !== 'true') ? 'none' : '';
  }});
}});
</script>
{dark_mode_toggle_js()}
</body>
</html>"""
    return html


# ─── Prototype 4: The Folio ──────────────────────────────────────────────────

def generate_folio(river, clusters):
    items_json = json.dumps(river[:200], ensure_ascii=False)
    clusters_json = json.dumps(clusters, ensure_ascii=False)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>River Exploration 4: The Folio</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  :root {{ --bg: #fff; --ink: #222; --grid: #e0e0e0; --meta: #999; --gold: #c4a882; }}
  html.dark {{ --bg: #0e0e0e; --ink: #ccc; --grid: #2a2a2a; --meta: #666; --gold: #a08060; }}
  {dark_mode_toggle_css()}
  body {{ font-family: 'DM Sans', sans-serif; font-size: 11px;
    background: var(--bg); color: var(--ink); max-width: 1200px; margin: 0 auto; padding: 32px 24px; }}

  header {{ margin-bottom: 24px; padding-bottom: 12px; border-bottom: 1px solid var(--grid); }}
  header h1 {{ font-family: 'Cormorant Garamond', serif; font-size: 28px; font-weight: 400;
    letter-spacing: 0.03em; }}
  header p {{ font-size: 10px; color: var(--meta); margin-top: 4px; text-transform: uppercase;
    letter-spacing: 0.08em; }}

  /* Cluster zones */
  .clusters {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 20px;
    margin-bottom: 32px; padding-bottom: 24px; border-bottom: 1px solid var(--grid); }}
  .cluster {{ grid-column: span 4; padding: 16px; border: 1px solid var(--grid); }}
  @media (max-width: 800px) {{ .cluster {{ grid-column: span 6; }} }}
  @media (max-width: 500px) {{ .cluster {{ grid-column: span 12; }} }}
  .cluster .theme {{ font-size: 9px; text-transform: uppercase; letter-spacing: 0.1em;
    color: var(--meta); margin-bottom: 6px; }}
  .cluster h2 {{ font-family: 'Cormorant Garamond', serif; font-size: 18px; font-weight: 600;
    line-height: 1.25; margin-bottom: 8px; }}
  .cluster .claim {{ font-size: 11px; line-height: 1.5; margin-bottom: 8px; color: var(--ink); }}
  .cluster blockquote {{ font-family: 'Cormorant Garamond', serif; font-style: italic;
    font-size: 13px; line-height: 1.4; color: var(--meta); border-left: 2px solid var(--gold);
    padding-left: 10px; margin-bottom: 6px; }}
  .cluster .speaker {{ font-size: 9px; color: var(--meta); }}

  /* River grid */
  .river-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 12px; }}
  .river-item {{ padding: 8px 0; border-bottom: 1px solid color-mix(in srgb, var(--grid) 50%, transparent); }}
  .river-item.ai {{ border-top: 2px solid var(--gold); padding-top: 6px; }}
  .river-item h3 {{ font-family: 'Cormorant Garamond', serif; font-size: 15px; font-weight: 600;
    line-height: 1.3; margin-bottom: 3px; }}
  .river-item h3 a {{ color: var(--ink); text-decoration: none; }}
  .river-item h3 a:hover {{ text-decoration: underline; }}
  .river-item .item-meta {{ font-size: 9px; color: var(--meta); }}
  .river-item .glyph {{ margin-right: 3px; }}
</style>
</head>
<body>
<button class="dm-toggle">☾</button>
<header>
  <h1>The Folio</h1>
  <p>Exhibition of today's financial discourse</p>
</header>
<div class="clusters" id="clusters"></div>
<div class="river-grid" id="river-grid"></div>
<script>
const RIVER = {items_json};
const CLUSTERS = {clusters_json};

const glyphMap = {{ NW: '', TG: '📄', RP: '◆', YT: '▶', TW: '🐦', PP: '📝' }};

// Render clusters
const clustersEl = document.getElementById('clusters');
CLUSTERS.forEach(c => {{
  clustersEl.insertAdjacentHTML('beforeend',
    '<div class="cluster">' +
    '<div class="theme">' + c.theme + ' · #' + c.rank + '</div>' +
    '<h2>' + c.cluster_title + '</h2>' +
    '<div class="claim">' + c.core_claim + '</div>' +
    (c.quote_snippet ? '<blockquote>' + c.quote_snippet + '</blockquote>' +
      '<div class="speaker">— ' + c.quote_speaker + '</div>' : '') +
    '</div>'
  );
}});

// Render river items (exclude cluster primary URLs to avoid duplication)
const clusterUrls = new Set();
CLUSTERS.forEach(c => c.related_urls.forEach(u => {{ if(u) clusterUrls.add(u); }}));

const grid = document.getElementById('river-grid');
RIVER.filter(item => !clusterUrls.has(item.url)).forEach(item => {{
  const ai = item.is_ai_pick ? ' ai' : '';
  const glyph = glyphMap[item.lane] || '';
  grid.insertAdjacentHTML('beforeend',
    '<div class="river-item' + ai + '">' +
    '<h3><a href="' + item.url + '" target="_blank" rel="noopener">' + item.title + '</a></h3>' +
    '<div class="item-meta">' + (glyph ? '<span class="glyph">' + glyph + '</span>' : '') +
      item.source + (item.time_short ? ' · ' + item.time_short : '') + '</div>' +
    '</div>'
  );
}});
</script>
{dark_mode_toggle_js()}
</body>
</html>"""
    return html


# ─── Gallery Index ────────────────────────────────────────────────────────────

def generate_index():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>River Explorations — FinanceRadar</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: system-ui, -apple-system, sans-serif; background: #f8f8f8; color: #1a1a1a;
    max-width: 720px; margin: 0 auto; padding: 48px 24px; }
  h1 { font-size: 24px; font-weight: 600; margin-bottom: 8px; }
  .subtitle { font-size: 14px; color: #666; margin-bottom: 32px; }
  .card { display: block; background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
    padding: 20px; margin-bottom: 16px; text-decoration: none; color: inherit;
    transition: box-shadow 0.15s, border-color 0.15s; }
  .card:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.08); border-color: #ccc; }
  .card h2 { font-size: 17px; margin-bottom: 4px; }
  .card .desc { font-size: 13px; color: #555; line-height: 1.5; }
  .card .tag { display: inline-block; font-size: 10px; background: #f0f0f0; color: #666;
    padding: 2px 6px; border-radius: 3px; margin-top: 8px; text-transform: uppercase;
    letter-spacing: 0.05em; }
</style>
</head>
<body>
<h1>River Explorations</h1>
<p class="subtitle">4 prototypes reimagining FinanceRadar as a unified content river</p>

<a class="card" href="r1-the-ledger.html">
  <h2>1. The Ledger</h2>
  <p class="desc">Every item = one fixed-height row. IBM Plex Mono, 3-color palette, 28px rows. Like <code>git log --oneline</code> for news.</p>
  <span class="tag">Monospace · Grid · Minimal</span>
</a>

<a class="card" href="r2-the-broadsheet.html">
  <h2>2. The Broadsheet</h2>
  <p class="desc">FT-inspired multi-column newspaper. AI rank drives visual hierarchy — bigger headline = more important. Salmon background.</p>
  <span class="tag">Serif · Newspaper · Warm</span>
</a>

<a class="card" href="r3-the-tide-chart.html">
  <h2>3. The Tide Chart</h2>
  <p class="desc">Horizontal timeline. Time flows left-to-right, items stack as compact chips within each hour column.</p>
  <span class="tag">Timeline · Chips · Clinical</span>
</a>

<a class="card" href="r4-the-folio.html">
  <h2>4. The Folio</h2>
  <p class="desc">Museum exhibition grid. WSW debate clusters are top-level zones; individual items flow in a dense grid below.</p>
  <span class="tag">Gallery · Serif · Elegant</span>
</a>
</body>
</html>"""


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("Building river explorations...")
    river, clusters = build_river()
    print(f"  River: {len(river)} items, {len(clusters)} clusters")
    print(f"  AI picks: {sum(1 for r in river if r['is_ai_pick'])}")

    save_sample_data(river, clusters)

    protos = [
        ("r1-the-ledger.html", generate_ledger),
        ("r2-the-broadsheet.html", generate_broadsheet),
        ("r3-the-tide-chart.html", generate_tide_chart),
        ("r4-the-folio.html", generate_folio),
    ]
    for fname, gen_fn in protos:
        html = gen_fn(river, clusters)
        out = BASE / fname
        with open(out, "w") as f:
            f.write(html)
        print(f"  Wrote {fname} ({len(html):,} bytes)")

    with open(BASE / "index.html", "w") as f:
        f.write(generate_index())
    print("  Wrote index.html")
    print("Done! Open index.html to browse all prototypes.")


if __name__ == "__main__":
    main()
