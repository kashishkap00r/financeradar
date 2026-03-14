"""V13: INTERLEAVED EDITORIAL FEED — curated intelligence homepage.
Interleaves News+Telegram feed sections (4 distinct grid patterns) with
YouTube/Reports/Twitter horizontal sliders and WSW pull-quote breakers."""
from __future__ import annotations
import html as h
import json, re, urllib.parse
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher

PROJECT = Path('/home/kashish.kapoor/vibecoding projects/financeradar')
STATIC = PROJECT / 'static'
OUT = PROJECT / 'docs' / 'plans' / 'assets' / 'from-scratch-explorations'

# ── Text utilities ──────────────────────────────────────────────────

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

def e(s): return h.escape(str(s or ''), quote=True)
def crop(s, n=160):
    s = str(s or '').strip()
    return s if len(s) <= n else s[:n-1].rstrip() + '\u2026'

BOOKMARK_SVG = '<svg class="bk-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>'

BUCKET_COLORS = {
    'news': '#4A8F7A',
    'telegram': '#5E6A96',
    'reports': '#9A8345',
    'twitter': '#4A8A9A',
    'youtube': '#A86565',
    'papers': '#7A6B8F',
}
BUCKET_LABELS = {
    'news': 'News',
    'telegram': 'Telegram',
    'reports': 'Reports',
    'twitter': 'Twitter',
    'youtube': 'YouTube',
    'papers': 'Papers',
}

# ── Title similarity (simplified from articles.py) ─────────────────
_STOP = {'a','an','the','and','but','or','for','in','on','at','to','by','of','up','is','it','if','vs','via','from','with'}

def _sig(title):
    words = set(re.sub(r'[^\w\s]', '', title.lower()).split()) - _STOP
    return words

def _similar(t1, t2):
    s1, s2 = _sig(t1), _sig(t2)
    if s1 and s2:
        overlap = len(s1 & s2) / min(len(s1), len(s2))
        if overlap < 0.5:
            return False
    return SequenceMatcher(None, t1.lower(), t2.lower()).ratio() > 0.55

def group_news_articles(articles):
    """Group news articles with similar titles, return list with related_sources."""
    by_date = defaultdict(list)
    for i, a in enumerate(articles):
        dk = (a.get('date') or '')[:10]  # YYYY-MM-DD
        by_date[dk].append((i, a))
    used = set()
    result = []
    for dk, day_items in by_date.items():
        for idx, (i, art) in enumerate(day_items):
            if i in used:
                continue
            related = []
            used.add(i)
            for j, other in day_items[idx+1:]:
                if j in used:
                    continue
                if _similar(art['title'], other['title']) and art['source'] != other['source']:
                    related.append({'source': other['source'], 'url': other['url']})
                    used.add(j)
            art['related_sources'] = related
            art['source_count'] = 1 + len(related)
            art['has_related'] = len(related) > 0
            result.append(art)
    return result

# ── Data loading ────────────────────────────────────────────────────

def normalize_item(item, bucket):
    """Map raw cache items to unified schema matching AI ranking format."""
    return {
        'title': item.get('title', ''),
        'url': item.get('link') or item.get('url', ''),
        'source': item.get('source') or item.get('publisher', ''),
        'why_it_matters': item.get('description', ''),
        'signal_type': '',
        '_bucket': bucket,
        'rank': 999,
        # Specialized fields
        'video_id': item.get('video_id', ''),
        'thumbnail': item.get('thumbnail', ''),
        'tweet_id': item.get('tweet_id', ''),
        'region': item.get('region', ''),
        'publisher': item.get('publisher', ''),
    }

def load():
    # ── AI rankings (merge both providers, dedupe by URL) ──
    ai_raw = json.loads((STATIC / 'ai_rankings.json').read_text())
    url_best = {}  # url → item with best rank
    for prov_name, prov in ai_raw.get('providers', {}).items():
        for bucket, items in prov.get('buckets', {}).items():
            for item in items:
                item['_bucket'] = bucket
                item.setdefault('video_id', '')
                item.setdefault('thumbnail', '')
                item.setdefault('tweet_id', '')
                item.setdefault('region', '')
                item.setdefault('publisher', item.get('source', ''))
                url = item.get('url', '')
                if url not in url_best or item.get('rank', 99) < url_best[url].get('rank', 99):
                    url_best[url] = item

    # Separate AI-ranked items by bucket
    feed_items = []
    yt_items = []
    rp_items = []
    tw_items = []
    for item in url_best.values():
        b = item.get('_bucket', 'news')
        if b in ('news', 'telegram'):
            feed_items.append(item)
        elif b == 'youtube':
            yt_items.append(item)
        elif b == 'reports':
            rp_items.append(item)
        elif b == 'twitter':
            tw_items.append(item)

    feed_items.sort(key=lambda x: x.get('rank', 99))

    # ── Pad sliders from raw caches (cap at 12 for homepage sliders) ──
    yt_seen = {i['url'] for i in yt_items}
    rp_seen = {i['url'] for i in rp_items}
    tw_seen = {i['url'] for i in tw_items}

    # ── Load ALL items from raw caches for tab views ──
    # News (articles.json) — with similarity grouping for related sources
    all_news = []
    try:
        art_raw = json.loads((STATIC / 'articles.json').read_text())
        articles = art_raw.get('articles', []) if isinstance(art_raw, dict) else art_raw
        raw_news = []
        for a in articles:
            if a.get('category', '').lower() == 'news' or a.get('category', '') == 'News':
                raw_news.append({
                    'title': a.get('title', ''),
                    'url': a.get('url', ''),
                    'source': a.get('source', ''),
                    'date': a.get('date', ''),
                    '_bucket': 'news',
                })
        all_news = group_news_articles(raw_news)
    except Exception:
        pass

    # Telegram (telegram_reports.json)
    all_telegram = []
    try:
        tg_raw = json.loads((STATIC / 'telegram_reports.json').read_text())
        tg_items = tg_raw.get('reports', []) if isinstance(tg_raw, dict) else tg_raw
        for t in tg_items:
            docs = t.get('documents', [])
            doc_url = ''
            if docs and isinstance(docs, list) and docs[0]:
                doc_url = docs[0].get('url', '') if isinstance(docs[0], dict) else str(docs[0])
            images = t.get('images', [])
            if not isinstance(images, list):
                images = []
            full_text = (t.get('text', '') or '').strip()
            title = full_text[:200]
            # Skip posts with no displayable content
            if not full_text and not docs and not images:
                continue
            # Build doc metadata list (title + size)
            doc_meta = []
            for d in (docs if isinstance(docs, list) else []):
                if isinstance(d, dict):
                    doc_meta.append({'title': d.get('title', 'Document'), 'size': d.get('size', '')})
                elif isinstance(d, str) and d:
                    fname = urllib.parse.unquote(d.rsplit('/', 1)[-1].split('?')[0]) or 'Document'
                    doc_meta.append({'title': fname, 'size': ''})
            all_telegram.append({
                'title': title,
                'full_text': full_text,
                'url': t.get('url', ''),
                'source': t.get('channel', ''),
                'date': t.get('date', ''),
                '_bucket': 'telegram',
                'has_docs': bool(docs),
                'doc_url': doc_url,
                'documents': doc_meta,
                'images': images,
            })
    except Exception:
        pass

    # YouTube (youtube_cache.json) — ALL videos
    all_youtube = []
    try:
        yt_raw = json.loads((STATIC / 'youtube_cache.json').read_text())
        for feed_id, vids in yt_raw.items():
            if not isinstance(vids, list): continue
            for v in vids:
                url = v.get('link', '')
                if not url: continue
                vid = ''
                if 'watch?v=' in url:
                    vid = url.split('watch?v=')[1].split('&')[0]
                elif '/shorts/' in url:
                    vid = url.split('/shorts/')[1].split('?')[0]
                thumb = v.get('thumbnail', '')
                if not thumb and vid:
                    thumb = f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg'
                all_youtube.append({
                    'title': v.get('title', ''),
                    'url': url,
                    'source': v.get('source', v.get('publisher', '')),
                    'date': v.get('date', ''),
                    '_bucket': 'youtube',
                    'thumbnail': thumb,
                    'video_id': vid,
                    'youtube_bucket': v.get('youtube_bucket', ''),
                })
                if url not in yt_seen and len(yt_items) < 12:
                    yt_items.append(normalize_item(v, 'youtube'))
                    yt_seen.add(url)
    except Exception:
        pass

    # Reports (reports_cache.json) — ALL reports
    all_reports = []
    try:
        rp_raw = json.loads((STATIC / 'reports_cache.json').read_text())
        for feed_id, reports in rp_raw.items():
            if not isinstance(reports, list): continue
            for r in reports:
                url = r.get('link', '')
                if not url: continue
                all_reports.append({
                    'title': r.get('title', ''),
                    'url': url,
                    'source': r.get('source', r.get('publisher', '')),
                    'date': r.get('date', ''),
                    '_bucket': 'reports',
                    'why_it_matters': r.get('description', ''),
                    'region': r.get('region', ''),
                    'publisher': r.get('publisher', r.get('source', '')),
                })
                if url not in rp_seen and len(rp_items) < 12:
                    rp_items.append(normalize_item(r, 'reports'))
                    rp_seen.add(url)
    except Exception:
        pass

    # Twitter (twitter_clean_cache.json) — ALL tweets
    all_twitter = []
    try:
        tw_raw = json.loads((STATIC / 'twitter_clean_cache.json').read_text())
        tw_list = tw_raw.get('items', [])
        if isinstance(tw_list, list):
            for t in tw_list:
                url = t.get('link', '')
                if not url: continue
                all_twitter.append({
                    'title': t.get('title', ''),
                    'url': url,
                    'source': t.get('source', t.get('publisher', '')),
                    'date': t.get('date', ''),
                    '_bucket': 'twitter',
                })
                if url not in tw_seen and len(tw_items) < 12:
                    tw_items.append(normalize_item(t, 'twitter'))
                    tw_seen.add(url)
    except Exception:
        pass

    # ── WSW clusters ──
    wsw_raw = json.loads((STATIC / 'wsw_clusters.json').read_text())
    wsw = []
    for prov in wsw_raw.get('providers', {}).values():
        wsw = prov.get('clusters', [])[:6]
        break

    # ── Fallback: pad feed with in-focus articles ──
    if len(feed_items) < 50:
        try:
            art_raw = json.loads((STATIC / 'articles.json').read_text())
            articles = art_raw.get('articles', []) if isinstance(art_raw, dict) else art_raw
            feed_urls = {i['url'] for i in feed_items}
            for a in articles:
                if a.get('has_related') and a.get('url') not in feed_urls:
                    feed_items.append(normalize_item(a, 'news'))
                    feed_urls.add(a['url'])
                if len(feed_items) >= 70: break
        except Exception:
            pass

    # ── Papers — ALL ──
    all_papers = []
    try:
        pp_raw = json.loads((STATIC / 'papers_cache.json').read_text())
        pp_list = pp_raw.get('papers', []) if isinstance(pp_raw, dict) else pp_raw
        if isinstance(pp_list, list):
            for p in pp_list:
                all_papers.append({
                    'title': p.get('title', ''),
                    'url': p.get('link', ''),
                    'source': p.get('source', ''),
                    'why_it_matters': p.get('description', ''),
                    'publisher': p.get('authors', p.get('source', '')),
                    '_bucket': 'papers',
                    'date': p.get('date', ''),
                })
    except Exception:
        pass

    return dict(
        feed=feed_items,
        youtube=yt_items[:12],
        reports=rp_items[:12],
        twitter=tw_items[:12],
        papers=all_papers[:12],
        wsw=wsw,
        # Full datasets for tabs
        all_news=all_news,
        all_telegram=all_telegram,
        all_youtube=all_youtube,
        all_reports=all_reports,
        all_twitter=all_twitter,
        all_papers=all_papers,
    )

# ── Card renderers ──────────────────────────────────────────────────

def _meta(item):
    bucket = item.get('_bucket', 'news')
    color = BUCKET_COLORS.get(bucket, '#6B645C')
    label = BUCKET_LABELS.get(bucket, 'News')
    source = e(item.get('source', ''))
    return color, label, source

def card_hero(item):
    color, label, source = _meta(item)
    title = e(title_case(item.get('title', '')))
    url = e(item.get('url', ''))
    why = e(sentence_case(crop(item.get('why_it_matters', ''), 220)))
    return f'''<div class="card-hero">
  <div class="card-meta"><span class="cat-dot" style="background:{color}"></span><span class="cat-label">{label}</span></div>
  <h2 class="hero-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h2>
  <p class="hero-desc">{why}</p>
  <div class="hero-source">{source}</div>
  <button class="btn-bk" aria-label="Bookmark">{BOOKMARK_SVG}</button>
</div>'''

def card_medium(item):
    color, label, source = _meta(item)
    title = e(title_case(crop(item.get('title', ''), 100)))
    url = e(item.get('url', ''))
    why = e(sentence_case(crop(item.get('why_it_matters', ''), 120)))
    return f'''<div class="card-medium">
  <div class="card-meta"><span class="cat-dot" style="background:{color}"></span><span class="cat-label">{label}</span><button class="btn-bk" aria-label="Bookmark">{BOOKMARK_SVG}</button></div>
  <h3 class="medium-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>
  <p class="medium-desc">{why}</p>
  <div class="medium-source">{source}</div>
</div>'''

def card_compact(item):
    color, label, source = _meta(item)
    title = e(title_case(crop(item.get('title', ''), 90)))
    url = e(item.get('url', ''))
    return f'''<div class="card-compact">
  <span class="cat-dot" style="background:{color}"></span>
  <div class="compact-body">
    <a href="{url}" target="_blank" rel="noopener" class="compact-link">{title}</a>
    <span class="compact-src">{source}</span>
  </div>
  <button class="btn-bk" aria-label="Bookmark">{BOOKMARK_SVG}</button>
</div>'''


def card_youtube(item):
    title = e(title_case(crop(item.get('title', ''), 80)))
    url = e(item.get('url', ''))
    source = e(item.get('source', ''))
    vid = item.get('video_id', '')
    thumb = item.get('thumbnail', '')
    if not thumb and vid:
        thumb = f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg'
    thumb = e(thumb)
    return f'''<div class="slider-card slider-yt">
  <div class="yt-thumb" style="background-image:url('{thumb}')"><div class="yt-play">&#9654;</div></div>
  <div class="slider-card-body">
    <div class="slider-card-header">
      <a href="{url}" target="_blank" rel="noopener" class="yt-title">{title}</a>
      <button class="btn-bk" aria-label="Bookmark">{BOOKMARK_SVG}</button>
    </div>
    <div class="yt-channel">{source}</div>
  </div>
</div>'''

def card_report(item):
    title = e(title_case(crop(item.get('title', ''), 100)))
    url = e(item.get('url', ''))
    publisher = e(item.get('publisher') or item.get('source', ''))
    region = item.get('region', '')
    region_badge = f'<span class="region-badge">International</span>' if region and region.lower() == 'international' else ''
    return f'''<div class="slider-card slider-rp">
  <div class="slider-card-header">
    <div class="rp-publisher">{publisher}</div>
    <button class="btn-bk" aria-label="Bookmark">{BOOKMARK_SVG}</button>
  </div>
  <a href="{url}" target="_blank" rel="noopener" class="rp-title">{title}</a>
  {region_badge}
</div>'''

def card_twitter(item):
    title = e(crop(item.get('title', ''), 200))
    url = e(item.get('url', ''))
    source = e(item.get('source', ''))
    return f'''<div class="slider-card slider-tw">
  <div class="slider-card-header">
    <div class="tw-author">{source}</div>
    <button class="btn-bk" aria-label="Bookmark">{BOOKMARK_SVG}</button>
  </div>
  <a href="{url}" target="_blank" rel="noopener" class="tw-text">{title}</a>
</div>'''

def card_paper(item):
    title = e(title_case(crop(item.get('title', ''), 100)))
    url = e(item.get('url', ''))
    authors = e(item.get('publisher') or item.get('source', ''))
    desc = e(sentence_case(crop(item.get('why_it_matters', ''), 100)))
    return f'''<div class="slider-card slider-pp">
  <div class="slider-card-header">
    <div class="pp-authors">{authors}</div>
    <button class="btn-bk" aria-label="Bookmark">{BOOKMARK_SVG}</button>
  </div>
  <a href="{url}" target="_blank" rel="noopener" class="pp-title">{title}</a>
  <div class="pp-desc">{desc}</div>
</div>'''

# ── WSW breaker ─────────────────────────────────────────────────────

def wsw_breaker(cluster):
    quote = e(cluster.get('quote_snippet', ''))
    speaker = e(cluster.get('quote_speaker', ''))
    url = e(cluster.get('source_url_primary', ''))
    inner = f'''<blockquote class="wsw-quote">
    <p>&ldquo;{quote}&rdquo;</p>
    <cite>&mdash; {speaker}</cite>
  </blockquote>'''
    if url:
        inner = f'<a href="{url}" target="_blank" rel="noopener" class="wsw-link">{inner}</a>'
    return f'''<div class="wsw-breaker">
  <div class="wsw-rule"></div>
  {inner}
  <button class="btn-bk wsw-bk" aria-label="Bookmark" data-url="{url}" data-title="{quote[:80]}" data-source="{speaker}">{BOOKMARK_SVG}</button>
  <div class="wsw-rule"></div>
</div>'''

# ── Section renderers ───────────────────────────────────────────────

def render_pattern_a(items):
    """Lead Grid: hero + sidebar (4 compact) + 2-col grid of mediums."""
    if not items: return ''
    hero = items[0]
    sidebar = items[1:5]
    grid = items[5:]
    sidebar_html = ''.join(card_compact(p) for p in sidebar)
    grid_html = ''.join(card_medium(p) for p in grid)
    return f'''<section class="feed-section">
  <div class="pa-lead">
    {card_hero(hero)}
    <div class="pa-sidebar">{sidebar_html}</div>
  </div>
  <div class="pa-grid">{grid_html}</div>
</section>'''

def render_pattern_b(items):
    """Inverted Lead Grid: sidebar LEFT + hero RIGHT, then 2-col mediums."""
    if not items: return ''
    sidebar = items[:4]
    hero = items[4] if len(items) > 4 else items[0]
    grid = items[5:]
    sidebar_html = ''.join(card_compact(p) for p in sidebar)
    grid_html = ''.join(card_medium(p) for p in grid)
    return f'''<section class="feed-section">
  <div class="pb-lead">
    <div class="pb-sidebar">{sidebar_html}</div>
    {card_hero(hero)}
  </div>
  <div class="pb-grid">{grid_html}</div>
</section>'''

def render_pattern_c(items):
    """Asymmetric 2-Col: wide mediums LEFT + narrow compacts RIGHT."""
    if not items: return ''
    mid = len(items) // 2 + 1  # slightly more items on left (medium cards)
    left = items[:mid]
    right = items[mid:]
    left_html = ''.join(card_medium(p) for p in left)
    right_html = ''.join(card_compact(p) for p in right)
    return f'''<section class="feed-section">
  <div class="pc-grid">
    <div class="pc-col-left">{left_html}</div>
    <div class="pc-col-right">{right_html}</div>
  </div>
</section>'''

def render_pattern_d(items):
    """Lead Grid + Scrollable Tail: hero+sidebar top, then contained 2-col scroll."""
    if not items: return ''
    hero = items[0]
    sidebar = items[1:5]
    scroll = items[5:]
    sidebar_html = ''.join(card_compact(p) for p in sidebar)
    scroll_html = ''.join(card_compact(p) for p in scroll)
    remaining = len(scroll)
    return f'''<section class="feed-section">
  <div class="pd-lead">
    {card_hero(hero)}
    <div class="pd-sidebar">{sidebar_html}</div>
  </div>
  <div class="pd-scroll-label">
    <span class="pd-scroll-title">Also in the Feed</span>
    <span class="pd-scroll-count">{remaining} items</span>
  </div>
  <div class="pd-scroll-container">
    <div class="pd-scroll-grid">{scroll_html}</div>
  </div>
</section>'''

def _slider_arrows(track_id):
    return f'''<button class="slider-arrow slider-prev" onclick="document.getElementById('{track_id}').scrollBy({{left:-300,behavior:'smooth'}})">&larr;</button>
<button class="slider-arrow slider-next" onclick="document.getElementById('{track_id}').scrollBy({{left:300,behavior:'smooth'}})">&rarr;</button>'''

def render_yt_slider(items):
    cards = ''.join(card_youtube(p) for p in items)
    return f'''<section class="slider-section">
  <div class="slider-header">
    <h2 class="slider-label">Watch</h2>
    <div class="slider-nav">{_slider_arrows('yt-track')}</div>
  </div>
  <div class="slider-track" id="yt-track">{cards}</div>
</section>'''

def render_rp_slider(items):
    cards = ''.join(card_report(p) for p in items)
    return f'''<section class="slider-section">
  <div class="slider-header">
    <h2 class="slider-label">Research Reports</h2>
    <div class="slider-nav">{_slider_arrows('rp-track')}</div>
  </div>
  <div class="slider-track" id="rp-track">{cards}</div>
</section>'''

def render_tw_slider(items):
    cards = ''.join(card_twitter(p) for p in items)
    return f'''<section class="slider-section">
  <div class="slider-header">
    <h2 class="slider-label">Voices</h2>
    <div class="slider-nav">{_slider_arrows('tw-track')}</div>
  </div>
  <div class="slider-track" id="tw-track">{cards}</div>
</section>'''

def render_pp_slider(items):
    if not items: return ''
    cards = ''.join(card_paper(p) for p in items)
    return f'''<section class="slider-section">
  <div class="slider-header">
    <h2 class="slider-label">Papers</h2>
    <div class="slider-nav">{_slider_arrows('pp-track')}</div>
  </div>
  <div class="slider-track" id="pp-track">{cards}</div>
</section>'''

# ── Tab bar ────────────────────────────────────────────────────────

TABS = [
    ('All', None),
    ('News', 'news'),
    ('Telegram', 'telegram'),
    ('Reports', 'reports'),
    ('Papers', 'papers'),
    ('YouTube', 'youtube'),
    ('Twitter', 'twitter'),
]

def render_tab_bar(data):
    counts = {
        'news': len(data.get('all_news', [])),
        'telegram': len(data.get('all_telegram', [])),
        'reports': len(data.get('all_reports', [])),
        'papers': len(data.get('all_papers', [])),
        'youtube': len(data.get('all_youtube', [])),
        'twitter': len(data.get('all_twitter', [])),
    }
    pills = []
    for label, bucket in TABS:
        color = BUCKET_COLORS.get(bucket, '#6B645C') if bucket else ''
        dot = f'<span class="cat-dot" style="background:{color}"></span>' if bucket else ''
        active = ' tab-active' if label == 'All' else ''
        count_html = f' <span class="tab-count">{counts[bucket]}</span>' if bucket and counts.get(bucket) else ''
        data_tab = f' data-tab="{bucket}"' if bucket else ' data-tab="all"'
        aria_sel = ' aria-selected="true"' if label == 'All' else ' aria-selected="false"'
        pills.append(f'<button class="tab-pill{active}" role="tab"{aria_sel}{data_tab}>{dot}{label}{count_html}</button>')
    return f'<nav class="tab-bar" role="tablist">{" ".join(pills)}</nav>'


# ── HTML assembly ───────────────────────────────────────────────────

def build_html(data):
    feed = data['feed']
    wsw = data['wsw']

    # Split feed across 4 sections
    s1 = feed[:15]
    s3 = feed[15:27]
    s5 = feed[27:37]
    s7 = feed[37:]

    # Build sections
    sec1 = render_pattern_a(s1)
    sec3 = render_pattern_b(s3)
    sec5 = render_pattern_c(s5)
    sec7 = render_pattern_d(s7)

    # Sliders
    yt_slider = render_yt_slider(data['youtube'])
    rp_slider = render_rp_slider(data['reports'])
    tw_slider = render_tw_slider(data['twitter'])
    pp_slider = render_pp_slider(data.get('papers', []))

    # WSW breakers (distribute 6 across gaps)
    breakers = [wsw_breaker(c) for c in wsw[:6]] if wsw else [''] * 6
    while len(breakers) < 6:
        breakers.append('')

    # Tab bar
    tab_bar = render_tab_bar(data)

    # Stats for footer
    total_items = len(data.get('all_news',[])) + len(data.get('all_telegram',[])) + len(data.get('all_youtube',[])) + len(data.get('all_reports',[])) + len(data.get('all_twitter',[])) + len(data.get('all_papers',[]))
    today = datetime.now().strftime('%A, %d %B %Y')
    now_ts = datetime.now().strftime('%b %d, %Y, %I:%M %p UTC')
    now_iso = datetime.now().isoformat()

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
  --rule: #D4CBC0;
  --accent: #C45A35;
  --card-bg: #FFFFFF;
  --card-border: #E2DCD3;
  --serif: 'Fraunces', Georgia, serif;
  --sans: 'Nunito Sans', system-ui, sans-serif;
}}
html {{
  background: var(--bg);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 17px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}}
body {{
  max-width: 1100px;
  margin: 0 auto;
  padding: 0 2.5rem;
}}
a {{ color: inherit; }}


/* ═══ Bookmark panel toggle ═══ */
.bk-panel-toggle {{
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  padding: 0.2rem;
  color: var(--ink-muted);
  cursor: pointer;
  transition: color 0.2s ease;
}}
.bk-panel-toggle:hover {{
  color: var(--accent);
}}
.bk-panel-toggle .bk-icon {{
  width: 18px;
  height: 18px;
}}
.bk-count {{
  position: absolute;
  top: -4px;
  right: -6px;
  background: var(--accent);
  color: #fff;
  font-family: var(--sans);
  font-size: 0.55rem;
  font-weight: 700;
  padding: 0 4px;
  border-radius: 8px;
  min-width: 14px;
  height: 14px;
  line-height: 14px;
  text-align: center;
}}

/* ═══ Bookmark panel ═══ */
.bk-panel {{
  position: fixed;
  top: 0;
  right: -380px;
  width: 360px;
  height: 100vh;
  background: var(--bg);
  border-left: 1.5px solid var(--rule);
  z-index: 200;
  transition: right 0.3s ease;
  overflow-y: auto;
  box-shadow: -4px 0 20px rgba(0,0,0,0.06);
}}
.bk-panel.open {{
  right: 0;
}}
.bk-panel-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid var(--rule);
}}
.bk-panel-title {{
  font-family: var(--serif);
  font-size: 1.1rem;
  font-weight: 700;
}}
.bk-panel-close {{
  background: none;
  border: none;
  font-size: 1.5rem;
  color: var(--ink-muted);
  cursor: pointer;
  line-height: 1;
}}
.bk-panel-close:hover {{ color: var(--accent); }}
.bk-panel-list {{
  padding: 1rem 1.5rem;
}}
.bk-empty {{
  font-size: 0.85rem;
  color: var(--ink-faint);
  font-style: italic;
}}
.bk-saved-item {{
  padding: 0.65rem 0;
  border-bottom: 1px solid var(--rule);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.5rem;
}}
.bk-saved-item a {{
  font-family: var(--serif);
  font-size: 0.88rem;
  font-weight: 500;
  line-height: 1.3;
  color: var(--ink);
  text-decoration: none;
  flex: 1;
}}
.bk-saved-item a:hover {{ color: var(--accent); }}
.bk-saved-src {{
  font-size: 0.65rem;
  color: var(--ink-faint);
  display: block;
  font-family: var(--sans);
  margin-top: 0.15rem;
}}
.bk-remove {{
  background: none;
  border: none;
  color: var(--ink-faint);
  cursor: pointer;
  font-size: 0.85rem;
  padding: 0;
  flex-shrink: 0;
}}
.bk-remove:hover {{ color: var(--accent); }}

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
.masthead-link {{ color: inherit; text-decoration: none; transition: color 0.3s ease; }}
.masthead-link:hover {{ color: var(--accent); }}
.masthead .tagline {{
  font-family: var(--serif);
  font-size: 1.05rem;
  font-weight: 300;
  font-style: italic;
  color: var(--ink-muted);
  margin-top: 0.5rem;
}}

/* ═══ Utility bar (sticky) ═══ */
.utility {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.65rem 2.5rem;
  margin: 0 -2.5rem;
  border-bottom: 1px solid var(--rule);
  font-size: 0.78rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-muted);
  position: sticky;
  top: 0;
  z-index: 100;
  background: color-mix(in srgb, var(--bg) 85%, transparent);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}}

.utility-nav {{
  display: flex;
  align-items: center;
  gap: 1rem;
}}
.utility-link {{
  color: var(--ink-muted);
  text-decoration: none;
  transition: color 0.2s ease;
}}
.utility-link:hover {{ color: var(--accent); }}
.utility-link.active {{ color: var(--ink); }}

/* ═══ Shared card parts ═══ */
.card-meta {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}}
.card-meta .btn-bk {{ margin-left: auto; }}
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

/* ═══ HERO card ═══ */
.card-hero {{
  position: relative;
}}
.hero-title {{
  font-family: var(--serif);
  font-size: clamp(1.5rem, 2.5vw, 2rem);
  font-weight: 500;
  line-height: 1.15;
  letter-spacing: -0.02em;
}}
.hero-title a {{
  color: var(--ink);
  text-decoration: none;
  transition: color 0.2s ease;
}}
.hero-title a:hover {{ color: var(--accent); }}
.hero-desc {{
  font-family: var(--serif);
  font-size: 0.92rem;
  line-height: 1.65;
  color: var(--ink-muted);
  margin-top: 0.6rem;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-height: calc(1.65em * 3);
}}
.hero-source {{
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--ink-faint);
  margin-top: 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}}
.card-hero > .btn-bk {{
  position: absolute;
  top: 0;
  right: 0;
}}

/* ═══ MEDIUM card ═══ */
.card-medium {{
  padding: 1rem 0;
  border-bottom: 1px solid var(--rule);
  transition: opacity 0.2s ease;
}}
.card-medium:hover {{ opacity: 0.85; }}
.medium-title {{
  font-family: var(--serif);
  font-size: 1.05rem;
  font-weight: 500;
  line-height: 1.3;
}}
.medium-title a {{
  color: var(--ink);
  text-decoration: none;
  transition: color 0.2s ease;
}}
.medium-title a:hover {{ color: var(--accent); }}
.medium-desc {{
  font-size: 0.85rem;
  line-height: 1.55;
  color: var(--ink-muted);
  margin-top: 0.3rem;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-height: calc(1.55em * 2);
}}
.medium-source {{
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--ink-faint);
  margin-top: 0.35rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}}

/* ═══ COMPACT card ═══ */
.card-compact {{
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--rule);
  transition: transform 0.2s ease;
}}
.card-compact:last-child {{ border-bottom: none; }}
.card-compact:hover {{ transform: translateX(3px); }}
.compact-body {{ flex: 1; min-width: 0; }}
.compact-link {{
  font-family: var(--serif);
  font-size: 0.92rem;
  font-weight: 500;
  line-height: 1.3;
  color: var(--ink);
  text-decoration: none;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-height: calc(1.3em * 2);
}}
.compact-link:hover {{ color: var(--accent); }}
.compact-src {{
  font-size: 0.68rem;
  color: var(--ink-faint);
  display: block;
  margin-top: 0.15rem;
}}


/* ═══ PATTERN A — Lead Grid ═══ */
.pa-lead {{
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 2.5rem;
  padding: 2rem 0 2.25rem;
  border-bottom: 1px solid var(--rule);
}}
.pa-sidebar {{
  border-left: 1px solid var(--rule);
  padding-left: 1.5rem;
}}
.pa-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 2.5rem;
  padding: 1.5rem 0;
}}

/* ═══ PATTERN B — Inverted Lead Grid ═══ */
.pb-lead {{
  display: grid;
  grid-template-columns: 2fr 3fr;
  gap: 2.5rem;
  padding: 2rem 0 2.25rem;
  border-bottom: 1px solid var(--rule);
}}
.pb-sidebar {{
  border-right: 1px solid var(--rule);
  padding-right: 1.5rem;
}}
.pb-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 2.5rem;
  padding: 1.5rem 0;
}}

/* ═══ PATTERN C — Asymmetric 2-Col ═══ */
.pc-grid {{
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 0;
  padding: 1.5rem 0;
  align-items: start;
}}
.pc-col-left {{
  padding-right: 1.5rem;
}}
.pc-col-right {{
  border-left: 1px solid var(--rule);
  padding-left: 1.25rem;
  position: sticky;
  top: 3.5rem;
}}

/* ═══ PATTERN D — Lead Grid + Scroll Container ═══ */
.pd-lead {{
  display: grid;
  grid-template-columns: 3fr 2fr;
  gap: 2.5rem;
  padding: 2rem 0 2.25rem;
  border-bottom: 1px solid var(--rule);
}}
.pd-sidebar {{
  border-left: 1px solid var(--rule);
  padding-left: 1.5rem;
}}
.pd-scroll-label {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 0 0.5rem;
}}
.pd-scroll-title {{
  font-family: var(--serif);
  font-size: 0.85rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-muted);
}}
.pd-scroll-count {{
  font-size: 0.7rem;
  color: var(--ink-faint);
}}
.pd-scroll-container {{
  max-height: 420px;
  overflow-y: auto;
  border: 1px solid var(--rule);
  border-radius: 4px;
  padding: 0 1.25rem;
  position: relative;
  scrollbar-width: thin;
  scrollbar-color: var(--rule) transparent;
  mask-image: linear-gradient(to bottom, transparent 0%, black 3%, black 92%, transparent 100%);
  -webkit-mask-image: linear-gradient(to bottom, transparent 0%, black 3%, black 92%, transparent 100%);
}}
.pd-scroll-container::-webkit-scrollbar {{ width: 4px; }}
.pd-scroll-container::-webkit-scrollbar-track {{ background: transparent; }}
.pd-scroll-container::-webkit-scrollbar-thumb {{ background: var(--rule); border-radius: 2px; }}
.pd-scroll-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 2rem;
  padding: 0.5rem 0;
}}

/* ═══ Feed sections ═══ */

/* ═══ WSW BREAKER ═══ */
.wsw-breaker {{
  padding: 2rem 0;
  text-align: center;
}}
.wsw-rule {{
  border-top: 1px dashed var(--rule);
  margin: 0 auto;
  max-width: 60%;
}}
.wsw-quote {{
  max-width: 680px;
  margin: 0 auto;
  padding: 1.25rem 2rem;
}}
.wsw-quote p {{
  font-family: var(--serif);
  font-size: 1.15rem;
  font-weight: 400;
  font-style: italic;
  line-height: 1.4;
  color: var(--ink);
}}
.wsw-quote cite {{
  display: block;
  font-family: var(--sans);
  font-size: 0.78rem;
  font-style: normal;
  font-weight: 600;
  color: var(--ink-muted);
  margin-top: 0.6rem;
}}
.wsw-link {{
  text-decoration: none;
  color: inherit;
  display: block;
}}
.wsw-link:hover .wsw-quote p {{
  color: var(--accent);
}}
.wsw-bk {{
  display: block;
  margin: -0.5rem auto 0;
}}

/* ═══ Papers slider card ═══ */
.slider-pp {{
  width: 300px;
  padding: 1rem 0 0.75rem;
}}
.pp-authors {{
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-muted);
}}
.pp-title {{
  font-family: var(--serif);
  font-size: 0.95rem;
  font-weight: 500;
  line-height: 1.35;
  color: var(--ink);
  text-decoration: none;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-height: calc(1.35em * 3);
  margin-top: 0.4rem;
}}
.pp-title:hover {{ color: var(--accent); }}
.pp-desc {{
  font-size: 0.8rem;
  line-height: 1.45;
  color: var(--ink-muted);
  margin-top: 0.3rem;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-height: calc(1.45em * 2);
}}

/* ═══ SLIDERS (shared) ═══ */
.slider-section {{
  padding: 1.75rem 2.5rem;
  margin: 0 -2.5rem;
  background: color-mix(in srgb, var(--ink) 3%, var(--bg));
}}
.slider-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}}
.slider-label {{
  font-family: var(--serif);
  font-size: 1.4rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}}
.slider-nav {{
  display: flex;
  gap: 0.5rem;
}}
.slider-arrow {{
  width: 32px;
  height: 32px;
  border: 1.5px solid var(--rule);
  border-radius: 50%;
  background: var(--bg);
  color: var(--ink-muted);
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}}
.slider-arrow:hover {{
  border-color: var(--accent);
  color: var(--accent);
}}
.slider-track {{
  display: flex;
  gap: 1.25rem;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scrollbar-width: none;
  -ms-overflow-style: none;
  padding-bottom: 0.5rem;
}}
.slider-track::-webkit-scrollbar {{ display: none; }}
.slider-card {{
  flex-shrink: 0;
  scroll-snap-align: start;
  color: var(--ink);
  padding: 0 0 0.75rem;
  border-bottom: 1px solid var(--rule);
  transition: transform 0.2s ease;
}}
.slider-card:hover {{
  transform: translateY(-1px);
}}
.slider-card-body {{
  padding: 0.75rem 0.85rem 0;
}}
.slider-card-header {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.5rem;
}}

/* YouTube slider card */
.slider-yt {{
  width: 280px;
  padding: 0 0 0.75rem;
  overflow: hidden;
}}
.yt-thumb {{
  width: 100%;
  aspect-ratio: 16/9;
  background-size: cover;
  background-position: center;
  background-color: var(--rule);
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}}
.yt-play {{
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: rgba(0,0,0,0.6);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  opacity: 0;
  transition: opacity 0.2s ease;
}}
.slider-yt:hover .yt-play {{ opacity: 1; }}
.yt-title {{
  font-family: var(--serif);
  font-size: 0.88rem;
  font-weight: 500;
  line-height: 1.3;
  color: var(--ink);
  text-decoration: none;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-height: calc(1.3em * 2);
  flex: 1;
  min-width: 0;
}}
.yt-title:hover {{ color: var(--accent); }}
.yt-channel {{
  font-size: 0.68rem;
  color: var(--ink-faint);
}}

/* Reports slider card */
.slider-rp {{
  width: 300px;
  padding: 1rem 0 0.75rem;
}}
.rp-publisher {{
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-muted);
}}
.rp-title {{
  font-family: var(--serif);
  font-size: 0.95rem;
  font-weight: 500;
  line-height: 1.35;
  color: var(--ink);
  text-decoration: none;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-height: calc(1.35em * 3);
  margin-top: 0.5rem;
}}
.rp-title:hover {{ color: var(--accent); }}
.region-badge {{
  display: inline-block;
  font-size: 0.58rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 0.2rem 0.45rem;
  border: 1px solid var(--accent);
  color: var(--accent);
  border-radius: 3px;
  margin-top: 0.6rem;
}}

/* Twitter slider card */
.slider-tw {{
  width: 300px;
  padding: 1rem 0 0.75rem;
}}
.tw-author {{
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--accent);
}}
.tw-text {{
  font-family: var(--serif);
  font-size: 0.9rem;
  font-weight: 400;
  line-height: 1.45;
  color: var(--ink);
  text-decoration: none;
  display: block;
  margin-top: 0.4rem;
}}
.tw-text:hover {{ color: var(--accent); }}

/* ═══ Tab bar ═══ */
.tab-bar {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 1rem 0;
  border-bottom: 1px solid var(--rule);
}}
.tab-pill {{
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.85rem;
  border: 1.5px solid var(--rule);
  border-radius: 3px;
  background: transparent;
  font-family: var(--sans);
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-muted);
  cursor: pointer;
  transition: all 0.2s ease;
}}
.tab-pill:hover {{
  border-color: var(--ink-muted);
  color: var(--ink);
}}
.tab-pill:focus-visible {{
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}}
.tab-pill.tab-active {{
  background: var(--ink);
  color: var(--bg);
  border-color: var(--ink);
}}
.tab-pill .cat-dot {{
  width: 5px;
  height: 5px;
}}


/* ═══ Footer ═══ */
footer {{
  padding: 2.5rem 0 3rem;
  border-top: 1.5px solid var(--ink);
  text-align: center;
}}
.foot-stats {{
  font-size: 0.78rem;
  color: var(--ink-muted);
  margin-bottom: 0.75rem;
}}
.foot-stats strong {{
  color: var(--ink);
}}
.foot-nav {{
  display: flex;
  justify-content: center;
  gap: 1.75rem;
}}
.foot-nav a {{
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-muted);
  text-decoration: none;
  transition: color 0.2s ease;
}}
.foot-nav a:hover {{ color: var(--ink); }}
.foot-nav .foot-accent {{ color: var(--accent); }}
.foot-nav .foot-accent:hover {{ opacity: 0.8; }}

/* ═══ Tab content views ═══ */
.tab-content {{ display: none; }}
.tab-content-active {{ display: block; animation: tabFadeIn 0.45s cubic-bezier(0.25, 0.1, 0.25, 1); }}
@keyframes tabFadeIn {{
  from {{ opacity: 0; transform: translateY(10px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}
.tab-count {{
  font-size: 0.6rem;
  font-weight: 400;
  color: var(--ink-faint);
  letter-spacing: normal;
  text-transform: none;
}}
.tab-pill.tab-active .tab-count {{ color: color-mix(in srgb, var(--bg) 70%, transparent); }}

/* ═══ Tab view filter bar ═══ */
.tv-filter-bar {{
  padding: 1.25rem 0 1rem;
  border-bottom: 1px solid var(--rule);
}}
.tv-stats {{
  font-size: 0.78rem;
  color: var(--ink-muted);
  margin-bottom: 0.75rem;
}}
.tv-stats strong {{
  color: var(--ink);
  font-weight: 700;
}}
.tv-updated {{
  color: var(--ink-faint);
  font-style: italic;
}}
.tv-filters {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
}}
/* ═══ Preset buttons (non-news tabs) ═══ */
.tv-preset {{
  padding: 0.35rem 0.7rem;
  border: 1.5px solid var(--rule);
  border-radius: 3px;
  background: transparent;
  font-family: var(--sans);
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--ink-muted);
  cursor: pointer;
  transition: all 0.2s ease;
}}
.tv-preset:hover {{ border-color: var(--ink-muted); color: var(--ink); }}
.tv-preset.active {{
  background: var(--ink);
  color: var(--bg);
  border-color: var(--ink);
}}

/* ═══ Desk toggle buttons (news tab — 3 states) ═══ */
.tv-desk-btn {{
  padding: 0.35rem 0.7rem;
  border: 1.5px solid var(--rule);
  border-radius: 3px;
  background: transparent;
  font-family: var(--sans);
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--ink-muted);
  cursor: pointer;
  transition: all 0.2s ease;
}}
.tv-desk-btn:hover {{ border-color: var(--ink-muted); color: var(--ink); }}
.tv-desk-btn.active {{
  background: var(--ink);
  color: var(--bg);
  border-color: var(--ink);
}}
.tv-desk-btn.partial {{
  border-color: var(--ink-muted);
  color: var(--ink);
  border-style: dashed;
}}

/* ═══ In Focus toggle button ═══ */
.tv-focus-btn {{
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.35rem 0.7rem;
  border: 1.5px solid var(--rule);
  border-radius: 3px;
  background: transparent;
  font-family: var(--sans);
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--ink-muted);
  cursor: pointer;
  transition: all 0.2s ease;
}}
.tv-focus-btn:hover {{ border-color: var(--accent, #e14b4b); color: var(--accent, #e14b4b); }}
.tv-focus-btn.active {{
  background: var(--accent, #e14b4b);
  color: #fff;
  border-color: var(--accent, #e14b4b);
}}
.tv-focus-btn.active .pulse-dot-sm {{ background: #fff; }}
.pulse-dot-sm {{
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--accent, #e14b4b);
  display: inline-block;
  transition: background 0.25s;
}}
.tv-focus-btn.active .pulse-dot-sm {{
  animation: pulse 1.5s ease-in-out infinite;
}}
@keyframes pulse {{
  0%, 100% {{ opacity: 1; transform: scale(1); }}
  50% {{ opacity: 0.5; transform: scale(1.3); }}
}}

/* ═══ Source badge + Also covered by ═══ */
.source-badge {{
  display: inline-flex;
  padding: 2px 8px;
  background: var(--accent, #e14b4b);
  color: #fff;
  font-family: var(--sans);
  font-size: 0.65rem;
  font-weight: 600;
  border-radius: 3px;
  margin-left: 0.4rem;
  vertical-align: middle;
  letter-spacing: 0.02em;
}}
.also-covered {{
  margin-top: 0.3rem;
  font-family: var(--sans);
  font-size: 0.72rem;
  color: var(--ink-muted);
}}
.also-covered a {{
  color: var(--ink-secondary, var(--ink-muted));
  text-decoration: none;
  transition: color 0.2s ease;
}}
.also-covered a:hover {{
  color: var(--accent, #e14b4b);
}}

/* ═══ Telegram image thumbnails ═══ */
.tg-img-thumb {{
  position: relative;
  display: block;
  width: 100%;
  min-height: 120px;
  margin-bottom: 0.5rem;
  border-radius: 6px;
  overflow: hidden;
  background: color-mix(in srgb, var(--rule) 50%, transparent);
  border: 1px solid var(--rule);
  padding: 0;
  cursor: zoom-in;
  transition: border-color 0.2s ease;
}}
.tg-img-thumb:hover {{ border-color: var(--accent); }}
.tg-img-thumb img {{
  width: 100%;
  max-height: 240px;
  object-fit: cover;
  display: block;
  transition: opacity 0.2s ease;
}}
.tg-img-thumb:hover img {{ opacity: 0.85; }}
.tg-img-placeholder {{
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  width: 100%;
  height: 120px;
  color: var(--ink-faint);
  font-size: 0.72rem;
  font-weight: 600;
}}
.tg-img-placeholder svg {{ opacity: 0.5; }}
.tg-img-thumb:hover .tg-img-placeholder {{ color: var(--accent); }}
.tg-img-thumb:hover .tg-img-placeholder svg {{ stroke: var(--accent); opacity: 0.8; }}
.tg-img-badge {{
  position: absolute;
  bottom: 8px;
  right: 8px;
  background: rgba(0,0,0,0.65);
  color: #fff;
  font-size: 0.65rem;
  padding: 2px 8px;
  border-radius: 10px;
  font-family: var(--sans);
}}

/* ═══ Telegram lightbox ═══ */
.tg-lightbox {{
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(5,10,18,0.88);
  opacity: 0;
  transition: opacity 0.25s ease;
}}
.tg-lightbox.open {{ opacity: 1; }}
.tg-lightbox img {{
  max-width: 90vw;
  max-height: 85vh;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 16px 48px rgba(0,0,0,0.45);
  background: #111827;
}}
.tg-lb-error {{
  display: none;
  align-items: center;
  justify-content: center;
  min-width: 280px;
  min-height: 220px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.2);
  color: #e5e7eb;
  font-size: 0.82rem;
  font-weight: 600;
  background: rgba(17,24,39,0.92);
}}
.tg-lb-close {{
  position: absolute;
  top: 1rem;
  right: 1rem;
  background: rgba(255,255,255,0.15);
  color: #fff;
  border: 0;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  font-size: 1.3rem;
  cursor: pointer;
  transition: background 0.2s;
}}
.tg-lb-close:hover {{ background: rgba(255,255,255,0.3); }}
.tg-lb-nav {{
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(255,255,255,0.15);
  color: #fff;
  border: 0;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  font-size: 1.4rem;
  cursor: pointer;
  transition: background 0.2s;
}}
.tg-lb-nav:hover {{ background: rgba(255,255,255,0.3); }}
.tg-lb-prev {{ left: 1rem; }}
.tg-lb-next {{ right: 1rem; }}
.tg-lb-counter {{
  position: absolute;
  bottom: 1rem;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0,0,0,0.5);
  color: #fff;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 0.75rem;
  font-family: var(--sans);
}}

/* ═══ Dropdown ═══ */
.tv-dropdown {{ position: relative; margin-left: auto; }}
.tv-dropdown-trigger {{
  padding: 0.35rem 0.7rem;
  border: 1.5px solid var(--rule);
  border-radius: 3px;
  background: transparent;
  font-family: var(--sans);
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--ink-muted);
  cursor: pointer;
  transition: all 0.2s ease;
}}
.tv-dropdown-trigger:hover {{ border-color: var(--ink-muted); }}
.tv-dropdown-trigger.has-selection {{ border-color: var(--accent); color: var(--accent); }}
.tv-dropdown-panel {{
  display: none;
  position: absolute;
  right: 0;
  top: 100%;
  margin-top: 4px;
  width: 280px;
  max-height: 360px;
  background: var(--bg);
  border: 1.5px solid var(--rule);
  border-radius: 4px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.08);
  z-index: 50;
  overflow: hidden;
  flex-direction: column;
}}
.tv-dropdown-panel.open {{ display: flex; }}
.tv-dropdown-search {{
  margin: 0.5rem;
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--rule);
  border-radius: 3px;
  font-family: var(--sans);
  font-size: 0.78rem;
  background: var(--card-bg);
  color: var(--ink);
  outline: none;
}}
.tv-dropdown-search:focus {{ border-color: var(--accent); }}
.tv-dropdown-actions {{
  display: flex;
  gap: 0.5rem;
  padding: 0 0.5rem 0.5rem;
}}
.tv-dropdown-actions button {{
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--accent);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
}}
.tv-dropdown-actions button:hover {{ text-decoration: underline; }}
.tv-dropdown-list {{
  overflow-y: auto;
  max-height: 240px;
  padding: 0 0.5rem 0.5rem;
}}
.tv-dd-item {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.3rem 0;
  font-size: 0.78rem;
  color: var(--ink);
  cursor: pointer;
}}
.tv-dd-item input {{ accent-color: var(--accent); }}

/* ═══ Tab view list items ═══ */
.tv-date-header {{
  font-family: var(--serif);
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-faint);
  padding: 1.5rem 0 0.5rem;
  border-bottom: 1px solid var(--rule);
}}
.tv-item {{
  position: relative;
  padding: 0.85rem 2rem 0.85rem 0.5rem;
  border-bottom: 1px solid color-mix(in srgb, var(--rule) 60%, transparent);
  transition: opacity 0.2s ease, transform 0.2s ease;
}}
.tv-item:hover {{
  opacity: 0.85;
  transform: translate(2px);
}}
.tv-item > .btn-bk {{
  position: absolute;
  top: 0.85rem;
  right: 0.5rem;
  opacity: 0;
  transition: opacity 0.2s ease, color 0.2s ease;
}}
.tv-item:hover > .btn-bk {{ opacity: 1; }}
.tv-item > .btn-bk.active {{ opacity: 1; }}
/* hover handled above with smooth transitions */
.tv-item-title {{
  font-family: var(--serif);
  font-size: 0.95rem;
  font-weight: 500;
  line-height: 1.35;
}}
.tv-item-title a {{
  color: var(--ink);
  text-decoration: none;
  transition: color 0.2s ease;
}}
.tv-item-title a:hover {{ color: var(--accent); }}
.tv-item-meta {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.3rem;
  font-size: 0.72rem;
  color: var(--ink-faint);
}}
.tv-item-source {{
  font-weight: 600;
  color: var(--ink-muted);
}}
.tv-item-source a {{ color: var(--ink-muted); text-decoration: none; }}
.tv-item-source a:hover {{ color: var(--accent); }}
.tv-sep {{ color: var(--rule); }}
.tv-item-time {{ color: var(--ink-faint); }}
/* bookmark now positioned absolutely on .tv-item */
.tv-item-desc {{
  font-size: 0.82rem;
  line-height: 1.5;
  color: var(--ink-muted);
  margin-top: 0.25rem;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-height: calc(1.5em * 2);
}}
/* Telegram type badges */
.tg-type-badge {{
  font-size: 0.6rem;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 4px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  margin-left: 0.35rem;
  vertical-align: middle;
  flex-shrink: 0;
}}
.tg-type-doc {{
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  color: var(--accent);
}}
.tg-type-photo {{
  background: color-mix(in srgb, #3b82f6 12%, transparent);
  color: #3b82f6;
}}

.tv-empty {{
  padding: 3rem 0;
  text-align: center;
  color: var(--ink-faint);
  font-style: italic;
}}

/* ═══ Telegram "Show more" ═══ */
.tg-text-body {{
  font-size: 0.85rem;
  line-height: 1.55;
  color: var(--ink-muted);
  margin-top: 0.3rem;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-height: calc(1.55em * 4);
  transition: all 0.2s ease;
}}
.tg-text-body.expanded {{
  -webkit-line-clamp: unset;
  max-height: 1000px;
  overflow: visible;
}}
.tg-expand-btn {{
  display: inline-block;
  margin-top: 0.25rem;
  font-family: var(--sans);
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--accent);
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  transition: opacity 0.2s ease;
}}
.tg-expand-btn:hover {{ opacity: 0.7; }}
.tg-text-link {{
  color: var(--ink);
  text-decoration: none;
  display: block;
  transition: color 0.2s ease;
}}
.tg-text-link:hover {{ color: var(--accent); }}

/* ═══ Twitter High Signal / Full Stream toggle ═══ */
.tv-signal-badge {{
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--ink-faint);
  font-style: italic;
  margin-left: 0.5rem;
}}

/* ═══ Bookmark panel overlay ═══ */
.bk-overlay {{
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.25);
  z-index: 149;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.3s ease, visibility 0.3s ease;
}}
.bk-overlay.open {{
  opacity: 1;
  visibility: visible;
}}

/* ═══ Tooltips ═══ */
[data-tooltip] {{
  position: relative;
}}
[data-tooltip]::after {{
  content: attr(data-tooltip);
  position: absolute;
  bottom: -28px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--ink);
  color: var(--bg);
  font-family: var(--sans);
  font-size: 0.6rem;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 3px;
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease;
  z-index: 200;
}}
[data-tooltip]:hover::after {{ opacity: 1; }}

/* ═══ Scroll-to-top button ═══ */
.scroll-top {{
  position: fixed;
  bottom: 2rem;
  right: 2rem;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: var(--ink);
  color: var(--bg);
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.25s ease, visibility 0.25s ease, transform 0.2s ease;
  z-index: 90;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}}
.scroll-top.visible {{
  opacity: 1;
  visibility: visible;
}}
.scroll-top:hover {{ transform: translateY(-2px); }}

/* YouTube tab items */
.tv-yt-item {{
  display: flex;
  gap: 1rem;
  align-items: flex-start;
}}
.tv-yt-thumb {{
  width: 180px;
  flex-shrink: 0;
  aspect-ratio: 16/9;
  background-size: cover;
  background-position: center;
  background-color: var(--rule);
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  text-decoration: none;
}}
.tv-yt-thumb .yt-play {{
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: rgba(0,0,0,0.6);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  opacity: 0;
  transition: opacity 0.2s ease;
}}
.tv-yt-item:hover .yt-play {{ opacity: 1; }}
.tv-yt-body {{ flex: 1; min-width: 0; }}

/* ═══ Pagination ═══ */
.tv-pagination {{
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  padding: 1.5rem 0 2rem;
}}
.tv-pg-btn {{
  padding: 0.4rem 0.7rem;
  border: 1.5px solid var(--rule);
  border-radius: 3px;
  background: transparent;
  font-family: var(--sans);
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--ink-muted);
  cursor: pointer;
  transition: all 0.15s ease;
}}
.tv-pg-btn:hover:not([disabled]) {{ border-color: var(--ink); color: var(--ink); }}
.tv-pg-btn.active {{
  background: var(--ink);
  color: var(--bg);
  border-color: var(--ink);
}}
.tv-pg-btn[disabled] {{
  opacity: 0.3;
  cursor: not-allowed;
}}
.tv-pg-dots {{
  padding: 0 0.3rem;
  color: var(--ink-faint);
  font-size: 0.72rem;
}}

/* ═══ Global search in utility bar ═══ */
/* ═══ Expandable search in utility bar ═══ */
.search-wrap {{
  position: relative;
  display: flex;
  align-items: center;
}}
.search-toggle {{
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  padding: 0.2rem;
  color: var(--ink-muted);
  cursor: pointer;
  transition: color 0.2s ease;
}}
.search-toggle:hover {{ color: var(--accent); }}
.search-input {{
  width: 0;
  padding: 0;
  border: 1.5px solid transparent;
  border-radius: 3px;
  background: transparent;
  font-family: var(--sans);
  font-size: 0.72rem;
  color: var(--ink);
  outline: none;
  opacity: 0;
  transition: width 0.25s ease, opacity 0.2s ease, padding 0.25s ease, border-color 0.2s ease;
}}
.search-wrap.open .search-input {{
  width: 200px;
  padding: 0.35rem 0.7rem;
  border-color: var(--rule);
  opacity: 1;
}}
.search-wrap.open .search-input:focus {{
  border-color: var(--accent);
}}
.search-input::placeholder {{ color: var(--ink-faint); }}
.search-wrap.open .search-toggle {{ color: var(--accent); }}

/* ═══ Responsive ═══ */
@media (max-width: 768px) {{
  body {{ padding: 0 1.25rem; }}
  .pa-lead {{ grid-template-columns: 1fr; gap: 1.5rem; }}
  .pa-sidebar {{ border-left: none; padding-left: 0; border-top: 1px solid var(--rule); padding-top: 0.75rem; }}
  .pa-grid {{ grid-template-columns: 1fr; }}
  .pb-lead {{ grid-template-columns: 1fr; gap: 1.5rem; }}
  .pb-sidebar {{ border-right: none; padding-right: 0; border-bottom: 1px solid var(--rule); padding-bottom: 0.75rem; }}
  .pb-grid {{ grid-template-columns: 1fr; }}
  .pc-grid {{ grid-template-columns: 1fr; }}
  .pc-col-left {{ padding-right: 0; }}
  .pc-col-right {{ border-left: none; padding-left: 0; border-top: 1px solid var(--rule); padding-top: 0.75rem; }}
  .pd-lead {{ grid-template-columns: 1fr; gap: 1.5rem; }}
  .pd-sidebar {{ border-left: none; padding-left: 0; border-top: 1px solid var(--rule); padding-top: 0.75rem; }}
  .pd-scroll-grid {{ grid-template-columns: 1fr; }}
  .pd-scroll-container {{ max-height: 350px; padding: 0 0.75rem; }}
  .slider-section {{ padding: 1.5rem 1.25rem; margin: 0 -1.25rem; }}
  .utility {{ padding: 0.65rem 1.25rem; margin: 0 -1.25rem; }}
  .slider-yt {{ width: 240px; }}
  .slider-rp {{ width: 260px; }}
  .slider-tw {{ width: 260px; }}
  .slider-pp {{ width: 260px; }}
  .tab-bar {{ gap: 0.35rem; flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch; white-space: nowrap; scrollbar-width: none; -ms-overflow-style: none; }}
  .tab-bar::-webkit-scrollbar {{ display: none; }}
  .tab-pill {{ padding: 0.35rem 0.65rem; font-size: 0.65rem; flex-shrink: 0; }}
  .foot-nav {{ flex-wrap: wrap; gap: 1rem; }}
  .tv-item > .btn-bk {{ opacity: 1; }}
  .tv-yt-item {{ flex-direction: column; }}
  .tv-yt-thumb {{ width: 100%; }}
  .search-wrap.open .search-input {{ width: 140px; }}
  .tv-dropdown-panel {{ width: 240px; }}
}}
</style>
</head>
<body data-generated="{now_iso}">

<div class="utility">
  <span>{today}</span>
  <div class="utility-nav">
    <a href="home.html" class="utility-link active">Feed</a>
    <a href="about.html" class="utility-link">About</a>
    <div class="search-wrap" id="search-wrap">
      <button class="search-toggle" id="search-toggle" aria-label="Search" data-tooltip="Search">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      </button>
      <input type="text" class="search-input" id="search-input" placeholder="Search...">
    </div>
    <button class="bk-panel-toggle" id="bk-toggle" aria-label="Bookmarks" data-tooltip="Bookmarks" onclick="document.getElementById('bk-panel').classList.toggle('open');document.getElementById('bk-overlay').classList.toggle('open')">
      {BOOKMARK_SVG} <span class="bk-count" id="bk-count">0</span>
    </button>
  </div>
</div>

<div class="bk-overlay" id="bk-overlay"></div>
<aside id="bk-panel" class="bk-panel">
  <div class="bk-panel-header">
    <h3 class="bk-panel-title">Bookmarks</h3>
    <button class="bk-panel-close" onclick="document.getElementById('bk-panel').classList.remove('open');document.getElementById('bk-overlay').classList.remove('open')">&times;</button>
  </div>
  <div class="bk-panel-list" id="bk-list">
    <p class="bk-empty">No bookmarks yet. Click the bookmark icon on any article to save it.</p>
  </div>
</aside>

<div class="masthead">
  <h1><a href="home.html" class="masthead-link">Finance Radar</a></h1>
  <div class="tagline">Curated intelligence from across Indian finance</div>
</div>

{tab_bar}

<div id="tab-all" class="tab-content tab-content-active">
{sec1}
{breakers[0]}

{yt_slider}
{breakers[1]}

{sec3}
{breakers[2]}

{rp_slider}
{breakers[3]}

{sec5}
{breakers[4]}

{tw_slider}
{breakers[5]}

{sec7}

{pp_slider}
</div>

<div id="tab-news" class="tab-content">
  <div class="tv-filter-bar">
    <div class="tv-stats"><strong class="tv-count"></strong> articles &middot; <strong class="tv-pub-count"></strong> publishers &middot; <span class="tv-updated"></span></div>
    <div class="tv-filters">
      <button class="tv-desk-btn" data-desk="india-desk">India Desk</button>
      <button class="tv-desk-btn" data-desk="world-desk">World Desk</button>
      <button class="tv-desk-btn" data-desk="indie-voices">Indie Voices</button>
      <button class="tv-desk-btn" data-desk="official-channels">Official Channels</button>
      <button class="tv-focus-btn"><span class="pulse-dot-sm"></span> In Focus</button>
      <div class="tv-dropdown">
        <button class="tv-dropdown-trigger">All publishers &#9662;</button>
        <div class="tv-dropdown-panel">
          <input type="text" class="tv-dropdown-search" placeholder="Search publishers...">
          <div class="tv-dropdown-actions"><button class="tv-sel-all">Select All</button><button class="tv-clr-all">Clear All</button></div>
          <div class="tv-dropdown-list"></div>
        </div>
      </div>
    </div>
  </div>
  <div class="tv-list"></div>
  <div class="tv-pagination"></div>
</div>

<div id="tab-telegram" class="tab-content">
  <div class="tv-filter-bar">
    <div class="tv-stats"><strong class="tv-count"></strong> posts &middot; <strong class="tv-pub-count"></strong> channels &middot; <span class="tv-updated"></span></div>
    <div class="tv-filters">
      <button class="tv-preset active" data-preset="all">All</button>
      <button class="tv-preset" data-preset="reports">Reports</button>
      <button class="tv-preset" data-preset="posts">Posts</button>
      <div class="tv-dropdown">
        <button class="tv-dropdown-trigger">All channels &#9662;</button>
        <div class="tv-dropdown-panel">
          <input type="text" class="tv-dropdown-search" placeholder="Search channels...">
          <div class="tv-dropdown-actions"><button class="tv-sel-all">Select All</button><button class="tv-clr-all">Clear All</button></div>
          <div class="tv-dropdown-list"></div>
        </div>
      </div>
    </div>
  </div>
  <div class="tv-list"></div>
  <div class="tv-pagination"></div>
</div>

<div id="tab-reports" class="tab-content">
  <div class="tv-filter-bar">
    <div class="tv-stats"><strong class="tv-count"></strong> reports &middot; <strong class="tv-pub-count"></strong> publishers &middot; <span class="tv-updated"></span></div>
    <div class="tv-filters">
      <button class="tv-preset active" data-preset="all">All</button>
      <button class="tv-preset" data-preset="indian">Indian</button>
      <button class="tv-preset" data-preset="international">International</button>
      <div class="tv-dropdown">
        <button class="tv-dropdown-trigger">All publishers &#9662;</button>
        <div class="tv-dropdown-panel">
          <input type="text" class="tv-dropdown-search" placeholder="Search publishers...">
          <div class="tv-dropdown-actions"><button class="tv-sel-all">Select All</button><button class="tv-clr-all">Clear All</button></div>
          <div class="tv-dropdown-list"></div>
        </div>
      </div>
    </div>
  </div>
  <div class="tv-list"></div>
  <div class="tv-pagination"></div>
</div>

<div id="tab-papers" class="tab-content">
  <div class="tv-filter-bar">
    <div class="tv-stats"><strong class="tv-count"></strong> papers &middot; <strong class="tv-pub-count"></strong> sources &middot; <span class="tv-updated"></span></div>
    <div class="tv-filters">
      <div class="tv-dropdown">
        <button class="tv-dropdown-trigger">All sources &#9662;</button>
        <div class="tv-dropdown-panel">
          <input type="text" class="tv-dropdown-search" placeholder="Search sources...">
          <div class="tv-dropdown-actions"><button class="tv-sel-all">Select All</button><button class="tv-clr-all">Clear All</button></div>
          <div class="tv-dropdown-list"></div>
        </div>
      </div>
    </div>
  </div>
  <div class="tv-list"></div>
  <div class="tv-pagination"></div>
</div>

<div id="tab-youtube" class="tab-content">
  <div class="tv-filter-bar">
    <div class="tv-stats"><strong class="tv-count"></strong> videos &middot; <strong class="tv-pub-count"></strong> channels &middot; <span class="tv-updated"></span></div>
    <div class="tv-filters">
      <button class="tv-preset active" data-preset="all">All</button>
      <button class="tv-preset" data-preset="Traditional Media">Traditional Media</button>
      <button class="tv-preset" data-preset="Indie Voices">Indie Voices</button>
      <button class="tv-preset" data-preset="Educational/Explainers">Educational</button>
      <div class="tv-dropdown">
        <button class="tv-dropdown-trigger">All channels &#9662;</button>
        <div class="tv-dropdown-panel">
          <input type="text" class="tv-dropdown-search" placeholder="Search channels...">
          <div class="tv-dropdown-actions"><button class="tv-sel-all">Select All</button><button class="tv-clr-all">Clear All</button></div>
          <div class="tv-dropdown-list"></div>
        </div>
      </div>
    </div>
  </div>
  <div class="tv-list"></div>
  <div class="tv-pagination"></div>
</div>

<div id="tab-twitter" class="tab-content">
  <div class="tv-filter-bar">
    <div class="tv-stats"><strong class="tv-count"></strong> tweets &middot; <strong class="tv-pub-count"></strong> accounts &middot; <span class="tv-updated"></span> <span class="tv-signal-badge" id="tw-signal-label"></span></div>
    <div class="tv-filters">
      <button class="tv-preset active" data-preset="high-signal">High Signal</button>
      <button class="tv-preset" data-preset="all">Full Stream</button>
      <div class="tv-dropdown">
        <button class="tv-dropdown-trigger">All accounts &#9662;</button>
        <div class="tv-dropdown-panel">
          <input type="text" class="tv-dropdown-search" placeholder="Search accounts...">
          <div class="tv-dropdown-actions"><button class="tv-sel-all">Select All</button><button class="tv-clr-all">Clear All</button></div>
          <div class="tv-dropdown-list"></div>
        </div>
      </div>
    </div>
  </div>
  <div class="tv-list"></div>
  <div class="tv-pagination"></div>
</div>

<button class="scroll-top" id="scroll-top" aria-label="Back to top">
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"/></svg>
</button>

<footer>
  <div class="foot-stats">
    <strong>{total_items}</strong> items &middot; last updated {now_ts} &middot; no ads, ever
  </div>
  <nav class="foot-nav">
    <a href="home.html">Feed</a>
    <a href="about.html">About</a>
    <a href="https://github.com/kashishkap00r/financeradar" target="_blank" rel="noopener">GitHub</a>
    <a href="home.html" class="foot-accent">RSS (soon)</a>
  </nav>
</footer>

<script>
const TAB_DATA = {{
  news: {json.dumps(data.get('all_news', []), ensure_ascii=False)},
  telegram: {json.dumps(data.get('all_telegram', []), ensure_ascii=False)},
  reports: {json.dumps(data.get('all_reports', []), ensure_ascii=False)},
  papers: {json.dumps(data.get('all_papers', []), ensure_ascii=False)},
  youtube: {json.dumps(data.get('all_youtube', []), ensure_ascii=False)},
  twitter: {json.dumps(data.get('all_twitter', []), ensure_ascii=False)},
}};
</script>
<script>
(function() {{
  const BK_SVG = `{BOOKMARK_SVG}`;
  const PAGE_SIZE = 20;

  // ── Bookmark system ──
  const KEY = 'fr_bookmarks';
  function bkLoad() {{ try {{ return JSON.parse(localStorage.getItem(KEY)) || []; }} catch {{ return []; }} }}
  function bkSave(bk) {{ try {{ localStorage.setItem(KEY, JSON.stringify(bk)); }} catch(e) {{ console.warn('Bookmarks save failed:', e); }} }}

  function findMeta(btn) {{
    if (btn.classList.contains('wsw-bk')) {{
      return btn.dataset.url ? {{ url: btn.dataset.url, title: btn.dataset.title || '', source: btn.dataset.source || '' }} : null;
    }}
    let card = btn.closest('.card-hero, .card-medium, .card-compact, .slider-card, .tv-item');
    if (!card) return null;
    let a = card.querySelector('a[href]');
    let title = '';
    let src = '';
    if (card.classList.contains('card-hero')) {{
      title = (card.querySelector('.hero-title a') || a)?.textContent || '';
      src = card.querySelector('.hero-source')?.textContent || '';
    }} else if (card.classList.contains('card-medium')) {{
      title = (card.querySelector('.medium-title a') || a)?.textContent || '';
      src = card.querySelector('.medium-source')?.textContent || '';
    }} else if (card.classList.contains('card-compact')) {{
      title = (card.querySelector('.compact-link') || a)?.textContent || '';
      src = card.querySelector('.compact-src')?.textContent || '';
    }} else if (card.classList.contains('slider-card')) {{
      title = (card.querySelector('.yt-title, .rp-title, .tw-text, .pp-title') || a)?.textContent || '';
      src = (card.querySelector('.yt-channel, .rp-publisher, .tw-author, .pp-authors'))?.textContent || '';
    }} else if (card.classList.contains('tv-item')) {{
      title = (card.querySelector('.tv-item-title a') || a)?.textContent || '';
      src = card.querySelector('.tv-item-source a, .tv-item-source')?.textContent || '';
    }}
    return a ? {{ url: a.href, title: title.trim(), source: src.trim() }} : null;
  }}

  function renderPanel() {{
    const bk = bkLoad();
    const list = document.getElementById('bk-list');
    const count = document.getElementById('bk-count');
    count.textContent = bk.length;
    if (!bk.length) {{
      list.innerHTML = '<p class="bk-empty">No bookmarks yet.</p>';
      return;
    }}
    list.innerHTML = bk.map((b, i) => `
      <div class="bk-saved-item">
        <a href="${{esc(b.url)}}" target="_blank" rel="noopener">${{esc(b.title)}}<span class="bk-saved-src">${{esc(b.source)}}</span></a>
        <button class="bk-remove" data-idx="${{i}}" title="Remove">&times;</button>
      </div>
    `).join('');
    list.querySelectorAll('.bk-remove').forEach(rb => {{
      rb.addEventListener('click', () => {{
        const bk2 = bkLoad();
        bk2.splice(parseInt(rb.dataset.idx), 1);
        bkSave(bk2);
        renderPanel();
        syncAllBk();
      }});
    }});
  }}

  function syncAllBk() {{
    const bk = bkLoad();
    const urls = new Set(bk.map(b => b.url));
    document.querySelectorAll('.btn-bk').forEach(btn => {{
      const meta = findMeta(btn);
      if (meta && urls.has(meta.url)) {{
        btn.classList.add('active');
        btn.querySelector('svg')?.setAttribute('fill', 'currentColor');
      }} else {{
        btn.classList.remove('active');
        btn.querySelector('svg')?.setAttribute('fill', 'none');
      }}
    }});
  }}

  function bindBk(root) {{
    (root || document).querySelectorAll('.btn-bk').forEach(btn => {{
      if (btn._bkBound) return;
      btn._bkBound = true;
      btn.addEventListener('click', (ev) => {{
        ev.preventDefault();
        ev.stopPropagation();
        const meta = findMeta(btn);
        if (!meta) return;
        let bk = bkLoad();
        const idx = bk.findIndex(b => b.url === meta.url);
        if (idx >= 0) bk.splice(idx, 1); else bk.unshift(meta);
        bkSave(bk);
        renderPanel();
        syncAllBk();
      }});
    }});
  }}

  // Bookmark overlay click-to-close
  const bkOverlay = document.getElementById('bk-overlay');
  if (bkOverlay) bkOverlay.addEventListener('click', () => {{
    document.getElementById('bk-panel')?.classList.remove('open');
    bkOverlay.classList.remove('open');
  }});

  // Scroll-to-top button
  const scrollTopBtn = document.getElementById('scroll-top');
  if (scrollTopBtn) {{
    window.addEventListener('scroll', () => {{
      scrollTopBtn.classList.toggle('visible', window.scrollY > 400);
    }}, {{ passive: true }});
    scrollTopBtn.addEventListener('click', () => {{
      window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }});
  }}

  // ── Tab switching ──
  let currentTab = 'all';
  const tabPills = document.querySelectorAll('.tab-pill');
  // Expandable search
  const searchWrap = document.getElementById('search-wrap');
  const searchToggle = document.getElementById('search-toggle');
  const globalSearch = document.getElementById('search-input');

  if (searchToggle) searchToggle.addEventListener('click', () => {{
    searchWrap?.classList.toggle('open');
    if (searchWrap?.classList.contains('open')) {{
      globalSearch?.focus();
    }} else if (globalSearch) {{
      globalSearch.value = '';
      globalSearch.dispatchEvent(new Event('input'));
    }}
  }});

  if (globalSearch) globalSearch.addEventListener('blur', () => {{
    if (!globalSearch.value) {{
      searchWrap?.classList.remove('open');
    }}
  }});

  if (globalSearch) globalSearch.addEventListener('keydown', (ev) => {{
    if (ev.key === 'Escape') {{
      globalSearch.value = '';
      globalSearch.dispatchEvent(new Event('input'));
      searchWrap?.classList.remove('open');
      globalSearch.blur();
    }}
  }});

  function switchTab(tab) {{
    tabPills.forEach(p => {{ p.classList.remove('tab-active'); p.setAttribute('aria-selected', 'false'); }});
    const pill = document.querySelector(`.tab-pill[data-tab="${{tab}}"]`);
    if (pill) {{ pill.classList.add('tab-active'); pill.setAttribute('aria-selected', 'true'); }}
    currentTab = tab;
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('tab-content-active'));
    const el = document.getElementById('tab-' + tab);
    if (el) el.classList.add('tab-content-active');
    // Carry search query across tabs
    if (tab !== 'all' && globalSearch.value) {{
      const state = getState(tab);
      state.search = globalSearch.value;
      state.page = 1;
    }}
    if (tab !== 'all') renderTab(tab);
    history.replaceState(null, '', tab === 'all' ? 'home.html' : `home.html#${{tab}}`);
  }}

  tabPills.forEach(pill => {{
    pill.addEventListener('click', () => switchTab(pill.dataset.tab));
  }});

  // ── Time formatting ──
  function timeAgo(dateStr) {{
    if (!dateStr) return '';
    const d = new Date(dateStr);
    if (isNaN(d)) return '';
    const now = new Date();
    const diff = (now - d) / 1000;
    if (diff < 60) return 'just now';
    if (diff < 3600) return Math.floor(diff/60) + 'm ago';
    if (diff < 86400) return Math.floor(diff/3600) + 'h ago';
    if (diff < 172800) return 'yesterday';
    return d.toLocaleDateString('en-IN', {{ day: 'numeric', month: 'short' }});
  }}

  function dateGroup(dateStr) {{
    if (!dateStr) return 'Undated';
    const d = new Date(dateStr);
    if (isNaN(d)) return 'Undated';
    const today = new Date();
    today.setHours(0,0,0,0);
    const yesterday = new Date(today); yesterday.setDate(today.getDate()-1);
    const itemDate = new Date(d); itemDate.setHours(0,0,0,0);
    if (itemDate >= today) return 'Today';
    if (itemDate >= yesterday) return 'Yesterday';
    return d.toLocaleDateString('en-IN', {{ weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }});
  }}

  function esc(s) {{ const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }}

  // ── News desk presets (publisher groupings) ──
  const NEWS_DESKS = {{
    'india-desk': ["ET", "The Hindu", "BusinessLine", "Business Standard", "Mint", "ThePrint", "Firstpost", "Indian Express", "The Core", "Financial Express"],
    'world-desk': ["BBC", "CNBC", "WSJ", "The Economist", "The Guardian", "Financial Times", "Reuters", "Bloomberg", "Rest of World", "Techmeme"],
    'indie-voices': ["Finshots", "Filter Coffee", "SOIC", "The Ken", "The Morning Context", "India Dispatch", "Carbon Brief", "Our World in Data", "Data For India", "Down To Earth", "The LEAP Blog", "By the Numbers", "Musings on Markets", "A Wealth of Common Sense", "BS Number Wise", "AlphaEcon", "Market Bites", "Capital Quill", "This Week In Data", "Noah Smith", "Ideas For India", "The India Forum", "Neel Chhabra", "Ember"],
    'official-channels': ["RBI", "SEBI", "ECB", "ADB", "FRED"]
  }};

  // ── Tab state ──
  const tabState = {{}};
  function getState(tab) {{
    if (!tabState[tab]) tabState[tab] = {{ page: 1, preset: tab === 'twitter' ? 'high-signal' : 'all', search: '', selectedPubs: new Set(), inFocus: false }};
    return tabState[tab];
  }}

  // Resolve desk preset publishers to actual allPubs entries
  function resolveDeskPubs(deskKey, allPubs) {{
    const deskNames = NEWS_DESKS[deskKey];
    if (!deskNames) return [];
    return allPubs.filter(p => deskNames.some(d => p.includes(d)));
  }}

  // ── Render a tab ──
  function renderTab(tab) {{
    const container = document.getElementById('tab-' + tab);
    const items = TAB_DATA[tab] || [];
    const state = getState(tab);

    // Sort by date descending
    items.sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0));

    // Collect unique publishers/sources
    const allPubs = [...new Set(items.map(i => i.source || i.publisher || '').filter(Boolean))].sort();
    // Cache allPubs on state for dropdown access
    state._allPubs = allPubs;

    // Apply filters
    let filtered = items;

    // Search
    if (state.search) {{
      const q = state.search.toLowerCase();
      filtered = filtered.filter(i => (i.title || '').toLowerCase().includes(q) || (i.source || '').toLowerCase().includes(q) || (i.why_it_matters || '').toLowerCase().includes(q));
    }}

    // Publisher filter: empty set = show all (no filter)
    if (tab === 'news') {{
      if (state.selectedPubs.size > 0) {{
        filtered = filtered.filter(i => state.selectedPubs.has(i.source || i.publisher || ''));
      }}
      if (state.inFocus) {{
        filtered = filtered.filter(i => i.has_related);
      }}
    }} else {{
      // Other tabs: selectedPubs null/empty = show all, non-empty = filter
      if (state.selectedPubs.size > 0) {{
        filtered = filtered.filter(i => state.selectedPubs.has(i.source || i.publisher || ''));
      }}
      // Content-based preset filters
      if (tab === 'telegram') {{
        if (state.preset === 'reports') filtered = filtered.filter(i => i.has_docs);
        if (state.preset === 'posts') filtered = filtered.filter(i => !i.has_docs);
      }}
      if (tab === 'reports') {{
        if (state.preset === 'indian') filtered = filtered.filter(i => (i.region || '').toLowerCase() === 'indian');
        if (state.preset === 'international') filtered = filtered.filter(i => (i.region || '').toLowerCase() === 'international');
      }}
      if (tab === 'youtube' && state.preset !== 'all') {{
        filtered = filtered.filter(i => i.youtube_bucket === state.preset);
      }}
      if (tab === 'twitter') {{
        if (state.preset === 'high-signal' || !state.preset) {{
          // High Signal: take top 25 by AI rank (items already sorted by date; take first 25 unique)
          filtered = filtered.slice(0, 25);
        }}
        // 'all' = full stream, no additional filter
      }}
    }}

    // Stats
    const statsEl = container.querySelector('.tv-stats');
    if (!statsEl) return;
    const countEl = statsEl.querySelector('.tv-count');
    const pubCountEl = statsEl.querySelector('.tv-pub-count');
    if (countEl) countEl.textContent = filtered.length;
    if (pubCountEl) pubCountEl.textContent = allPubs.length;
    // Updated time
    const updatedEl = statsEl.querySelector('.tv-updated');
    if (updatedEl) {{
      const gen = new Date(document.body.dataset.generated);
      if (!isNaN(gen)) {{
        const mins = Math.max(1, Math.floor((Date.now() - gen) / 60000));
        updatedEl.textContent = mins < 60 ? `Updated ${{mins}} min ago` : `Updated ${{Math.floor(mins/60)}}h ago`;
      }}
    }}

    // Twitter signal label
    if (tab === 'twitter') {{
      const sigLabel = document.getElementById('tw-signal-label');
      if (sigLabel) {{
        if (state.preset === 'high-signal') {{
          sigLabel.textContent = `High Signal \u2014 ${{filtered.length}} of ${{items.length}} \u2014 AI ranked`;
        }} else {{
          sigLabel.textContent = '';
        }}
      }}
    }}

    // Pagination — reset to page 1 if filters emptied results
    if (filtered.length === 0) state.page = 1;
    const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    if (state.page > totalPages) state.page = totalPages;
    const start = (state.page - 1) * PAGE_SIZE;
    const pageItems = filtered.slice(start, start + PAGE_SIZE);

    // Render list
    const listEl = container.querySelector('.tv-list');
    let html = '';
    let lastGroup = '';
    for (const item of pageItems) {{
      const group = dateGroup(item.date);
      if (group !== lastGroup) {{
        html += `<h2 class="tv-date-header">${{esc(group)}}</h2>`;
        lastGroup = group;
      }}
      html += renderItem(tab, item);
    }}
    listEl.innerHTML = html || '<p class="tv-empty">No items match your filters.</p>';

    // Show "Show more" buttons only where text is actually truncated
    // Note: -webkit-line-clamp makes scrollHeight === clientHeight, so we
    // measure via an off-screen clone with clamping removed
    requestAnimationFrame(() => {{
      listEl.querySelectorAll('.tg-text-body').forEach(el => {{
        const btn = el.nextElementSibling;
        if (btn && btn.classList.contains('tg-expand-btn')) {{
          const clampedH = el.clientHeight;
          const clone = el.cloneNode(true);
          clone.classList.add('expanded');
          clone.style.position = 'absolute';
          clone.style.visibility = 'hidden';
          clone.style.width = el.offsetWidth + 'px';
          el.parentNode.appendChild(clone);
          const naturalH = clone.scrollHeight;
          clone.remove();
          btn.style.display = naturalH > clampedH ? '' : 'none';
        }}
      }});
    }});

    // Pagination
    renderPagination(container.querySelector('.tv-pagination'), state, totalPages, tab);

    // Dropdown
    renderDropdown(container, allPubs, state, tab);

    // Bind bookmarks
    bindBk(container);
    syncAllBk();

    // ── News desk buttons: additive toggles with 3 visual states ──
    if (tab === 'news') {{
      container.querySelectorAll('.tv-desk-btn').forEach(btn => {{
        const deskKey = btn.dataset.desk;
        const deskPubs = resolveDeskPubs(deskKey, allPubs);
        const selectedCount = deskPubs.filter(p => state.selectedPubs.has(p)).length;
        btn.classList.remove('active', 'partial');
        if (state.selectedPubs.size > 0 && selectedCount === deskPubs.length && deskPubs.length > 0) {{
          btn.classList.add('active');
        }} else if (state.selectedPubs.size > 0 && selectedCount > 0) {{
          btn.classList.add('partial');
        }}
        if (!btn._bound) {{
          btn._bound = true;
          btn.addEventListener('click', () => {{
            const resolved = resolveDeskPubs(deskKey, state._allPubs);
            const allSelected = resolved.length > 0 && resolved.every(p => state.selectedPubs.has(p));
            if (allSelected) {{
              resolved.forEach(p => state.selectedPubs.delete(p));
            }} else {{
              resolved.forEach(p => state.selectedPubs.add(p));
            }}
            state.page = 1;
            renderTab(tab);
          }});
        }}
      }});
      // In Focus toggle
      const focusBtn = container.querySelector('.tv-focus-btn');
      if (focusBtn) {{
        focusBtn.classList.toggle('active', state.inFocus);
        if (!focusBtn._bound) {{
          focusBtn._bound = true;
          focusBtn.addEventListener('click', () => {{
            state.inFocus = !state.inFocus;
            state.page = 1;
            renderTab(tab);
          }});
        }}
      }}
    }} else {{
      // Other tabs: exclusive presets with dropdown sync
      container.querySelectorAll('.tv-preset').forEach(btn => {{
        btn.classList.toggle('active', btn.dataset.preset === state.preset);
        if (!btn._bound) {{
          btn._bound = true;
          btn.addEventListener('click', () => {{
            state.preset = btn.dataset.preset;
            state.page = 1;
            // Sync dropdown with preset
            if (tab === 'reports') {{
              if (state.preset === 'indian') {{
                state.selectedPubs = new Set(allPubs.filter(p => items.some(i => (i.source || i.publisher || '') === p && (i.region || '').toLowerCase() === 'indian')));
              }} else if (state.preset === 'international') {{
                state.selectedPubs = new Set(allPubs.filter(p => items.some(i => (i.source || i.publisher || '') === p && (i.region || '').toLowerCase() === 'international')));
              }} else {{
                state.selectedPubs = new Set();
              }}
            }} else if (tab === 'youtube') {{
              if (state.preset !== 'all') {{
                state.selectedPubs = new Set(allPubs.filter(p => items.some(i => (i.source || i.publisher || '') === p && i.youtube_bucket === state.preset)));
              }} else {{
                state.selectedPubs = new Set();
              }}
            }} else {{
              state.selectedPubs = new Set();
            }}
            renderTab(tab);
          }});
        }}
      }});
    }}
  }}

  function renderItem(tab, item) {{
    const title = esc(item.title || '');
    const url = esc(item.url || '');
    const source = esc(item.source || item.publisher || '');
    const time = timeAgo(item.date);

    if (tab === 'youtube') {{
      const thumb = esc(item.thumbnail || '');
      return `<article class="tv-item tv-yt-item">
        <a href="${{url}}" target="_blank" rel="noopener" class="tv-yt-thumb" style="background-image:url('${{thumb}}')"><span class="yt-play">&#9654;</span></a>
        <div class="tv-yt-body">
          <h3 class="tv-item-title"><a href="${{url}}" target="_blank" rel="noopener">${{title}}</a></h3>
          <div class="tv-item-meta"><span class="tv-item-source">${{source}}</span> <span class="tv-sep">&middot;</span> <span class="tv-item-time">${{time}}</span></div>
        </div>
        <button class="btn-bk" aria-label="Bookmark">${{BK_SVG}}</button>
      </article>`;
    }}

    if (tab === 'reports') {{
      return `<article class="tv-item">
        <h3 class="tv-item-title"><a href="${{url}}" target="_blank" rel="noopener">${{title}}</a></h3>
        <div class="tv-item-meta"><span class="tv-item-source">${{source}}</span> <span class="tv-sep">&middot;</span> <span class="tv-item-time">${{time}}</span></div>
        <button class="btn-bk" aria-label="Bookmark">${{BK_SVG}}</button>
      </article>`;
    }}

    if (tab === 'papers') {{
      const desc = esc((item.why_it_matters || '').slice(0, 150));
      const authors = esc(item.publisher || '');
      return `<article class="tv-item">
        <h3 class="tv-item-title"><a href="${{url}}" target="_blank" rel="noopener">${{title}}</a></h3>
        <div class="tv-item-source">${{authors}}</div>
        ${{desc ? `<p class="tv-item-desc">${{desc}}</p>` : ''}}
        <div class="tv-item-meta"><span class="tv-item-time">${{time}}</span></div>
        <button class="btn-bk" aria-label="Bookmark">${{BK_SVG}}</button>
      </article>`;
    }}

    if (tab === 'telegram') {{
      const images = Array.isArray(item.images) ? item.images.filter(Boolean) : [];
      const docs = Array.isArray(item.documents) ? item.documents : [];
      const hasDoc = docs.length > 0;
      const hasImages = images.length > 0;

      // Type badge (Report or Photo)
      let typeBadge = '';
      if (hasDoc) {{
        typeBadge = '<span class="tg-type-badge tg-type-doc">Report</span>';
      }} else if (hasImages) {{
        typeBadge = '<span class="tg-type-badge tg-type-photo">Photo</span>';
      }}

      // For doc-only posts (no text), use doc filename as title
      let displayTitle = '';
      if (!title && hasDoc) {{
        displayTitle = esc(docs[0].title || 'Document');
      }}

      // Image thumbnail (clickable, opens lightbox)
      let imgHtml = '';
      if (hasImages) {{
        const badge = images.length > 1 ? `<span class="tg-img-badge">+${{images.length - 1}} more</span>` : '';
        const encodedImgs = esc(JSON.stringify(images));
        const countLabel = images.length > 1 ? images.length + ' photos' : '1 photo';
        imgHtml = `<button type="button" class="tg-img-thumb" onclick="openTgLightbox(this)" data-images='${{encodedImgs}}' aria-label="View ${{countLabel}}">
          <img src="${{esc(images[0])}}" alt="Post image" loading="lazy"
            onload="this.style.display='block';this.nextElementSibling.style.display='none'"
            onerror="this.style.display='none'" style="display:none">
          <div class="tg-img-placeholder">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>
            <span>${{countLabel}}</span>
          </div>
          ${{badge}}</button>`;
      }}

      // Title line (only for doc-only posts without text)
      const titleHtml = displayTitle
        ? `<h3 class="tv-item-title"><a href="${{url}}" target="_blank" rel="noopener">${{displayTitle}}</a></h3>`
        : '';

      // Full text body with Show more/less (button always rendered, visibility set post-render)
      const fullText = esc(item.full_text || '');
      const textHtml = fullText
        ? `<div class="tg-text-body"><a href="${{url}}" target="_blank" rel="noopener" class="tg-text-link">${{fullText}}</a></div><button class="tg-expand-btn" style="display:none" onclick="var b=this.previousElementSibling;b.classList.toggle(&#39;expanded&#39;);this.textContent=b.classList.contains(&#39;expanded&#39;)?&#39;Show less&#39;:&#39;Show more&#39;">Show more</button>`
        : '';

      return `<article class="tv-item">
        ${{imgHtml}}
        ${{titleHtml}}
        ${{textHtml}}
        <div class="tv-item-meta"><span class="tv-item-source">${{source}}</span> ${{typeBadge}} <span class="tv-sep">&middot;</span> <span class="tv-item-time">${{time}}</span></div>
        <button class="btn-bk" aria-label="Bookmark">${{BK_SVG}}</button>
      </article>`;
    }}

    // Twitter — same text body + Show more as Telegram (button always rendered, visibility set post-render)
    if (tab === 'twitter') {{
      const textHtml = `<div class="tg-text-body"><a href="${{url}}" target="_blank" rel="noopener" class="tg-text-link">${{title}}</a></div><button class="tg-expand-btn" style="display:none" onclick="var b=this.previousElementSibling;b.classList.toggle(&#39;expanded&#39;);this.textContent=b.classList.contains(&#39;expanded&#39;)?&#39;Show less&#39;:&#39;Show more&#39;">Show more</button>`;
      return `<article class="tv-item">
        ${{textHtml}}
        <div class="tv-item-meta"><span class="tv-item-source">${{source}}</span> <span class="tv-sep">&middot;</span> <span class="tv-item-time">${{time}}</span></div>
        <button class="btn-bk" aria-label="Bookmark">${{BK_SVG}}</button>
      </article>`;
    }}

    // News — with source badges and "Also covered by"
    const related = item.related_sources || [];
    const srcCount = item.source_count || 1;
    const badge = srcCount > 1 ? `<span class="source-badge">${{srcCount}} sources</span>` : '';
    let coveredBy = '';
    if (related.length > 0) {{
      const links = related.slice(0, 5).map(r => `<a href="${{esc(r.url)}}" target="_blank" rel="noopener">${{esc(r.source)}}</a>`).join(', ');
      coveredBy = `<div class="also-covered">Also covered by: ${{links}}</div>`;
    }}
    return `<article class="tv-item">
      <h3 class="tv-item-title"><a href="${{url}}" target="_blank" rel="noopener">${{title}}</a> ${{badge}}</h3>
      <div class="tv-item-meta"><span class="tv-item-source">${{source}}</span> <span class="tv-sep">&middot;</span> <span class="tv-item-time">${{time}}</span></div>
      ${{coveredBy}}
      <button class="btn-bk" aria-label="Bookmark">${{BK_SVG}}</button>
    </article>`;
  }}

  function renderPagination(el, state, totalPages, tab) {{
    if (totalPages <= 1) {{ el.innerHTML = ''; return; }}
    let html = `<button class="tv-pg-btn" ${{state.page <= 1 ? 'disabled' : ''}} data-page="${{state.page-1}}">&larr; Prev</button>`;
    const maxShow = 7;
    let pages = [];
    if (totalPages <= maxShow) {{
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    }} else {{
      pages.push(1);
      let start = Math.max(2, state.page - 2);
      let end = Math.min(totalPages - 1, state.page + 2);
      if (start > 2) pages.push('...');
      for (let i = start; i <= end; i++) pages.push(i);
      if (end < totalPages - 1) pages.push('...');
      pages.push(totalPages);
    }}
    for (const p of pages) {{
      if (p === '...') {{ html += `<span class="tv-pg-dots">&hellip;</span>`; }}
      else {{ html += `<button class="tv-pg-btn ${{p===state.page?'active':''}}" data-page="${{p}}">${{p}}</button>`; }}
    }}
    html += `<button class="tv-pg-btn" ${{state.page >= totalPages ? 'disabled' : ''}} data-page="${{state.page+1}}">Next &rarr;</button>`;
    el.innerHTML = html;
    el.querySelectorAll('.tv-pg-btn[data-page]').forEach(btn => {{
      btn.addEventListener('click', () => {{
        const p = parseInt(btn.dataset.page);
        if (p >= 1 && p <= totalPages) {{
          state.page = p;
          renderTab(tab);
          document.getElementById('tab-' + tab).scrollIntoView({{ behavior: 'smooth', block: 'start' }});
        }}
      }});
    }});
  }}

  function renderDropdown(container, allPubs, state, tab) {{
    const dd = container.querySelector('.tv-dropdown');
    if (!dd) return;
    const trigger = dd.querySelector('.tv-dropdown-trigger');
    const panel = dd.querySelector('.tv-dropdown-panel');
    const listEl = dd.querySelector('.tv-dropdown-list');
    const searchInput = dd.querySelector('.tv-dropdown-search');

    function renderList(filter) {{
      const q = (filter || '').toLowerCase();
      const pubs = q ? allPubs.filter(p => p.toLowerCase().includes(q)) : allPubs;
      listEl.innerHTML = pubs.map(p => `<label class="tv-dd-item"><input type="checkbox" value="${{esc(p)}}" ${{state.selectedPubs.has(p)?'checked':''}}><span>${{esc(p)}}</span></label>`).join('');
      listEl.querySelectorAll('input[type="checkbox"]').forEach(cb => {{
        cb.addEventListener('change', () => {{
          if (cb.checked) state.selectedPubs.add(cb.value); else state.selectedPubs.delete(cb.value);
          state.page = 1;
          renderTab(tab);
        }});
      }});
    }}
    renderList(searchInput ? searchInput.value : '');

    // Update trigger text — empty set = "All publishers", otherwise "N of M"
    const effectiveSelected = allPubs.filter(p => state.selectedPubs.has(p)).length;
    if (effectiveSelected === 0) {{
      trigger.textContent = 'All publishers \u25BE';
      trigger.classList.remove('has-selection');
    }} else if (effectiveSelected === 1) {{
      const name = allPubs.find(p => state.selectedPubs.has(p)) || '';
      trigger.textContent = name + ' \u25BE';
      trigger.classList.add('has-selection');
    }} else {{
      trigger.textContent = effectiveSelected + ' of ' + allPubs.length + ' publishers \u25BE';
      trigger.classList.add('has-selection');
    }}

    if (!dd._bound) {{
      dd._bound = true;
      trigger.addEventListener('click', (ev) => {{
        ev.stopPropagation();
        panel.classList.toggle('open');
      }});
      document.addEventListener('click', (ev) => {{ if (!dd.contains(ev.target)) panel.classList.remove('open'); }});
      searchInput.addEventListener('input', () => renderList(searchInput.value));
      // Select All = clear set (empty = show all, matching live site behavior)
      dd.querySelector('.tv-sel-all').addEventListener('click', () => {{
        state.selectedPubs = new Set();
        state.page = 1;
        renderTab(tab);
      }});
      dd.querySelector('.tv-clr-all').addEventListener('click', () => {{
        state.selectedPubs = new Set();
        state.page = 1;
        renderTab(tab);
      }});
    }}
  }}

  // ── Global search ──
  globalSearch.addEventListener('input', () => {{
    if (currentTab === 'all') return;
    const state = getState(currentTab);
    state.search = globalSearch.value;
    state.page = 1;
    renderTab(currentTab);
  }});

  // ── Keyboard shortcuts ──
  document.addEventListener('keydown', (ev) => {{
    if (ev.target.tagName === 'INPUT' || ev.target.tagName === 'TEXTAREA') {{
      if (ev.key === 'Escape') {{ ev.target.blur(); globalSearch.value = ''; }}
      return;
    }}
    const tabKeys = {{ h: 'all', '1': 'news', '2': 'telegram', '3': 'reports', '4': 'papers', '5': 'youtube', '6': 'twitter' }};
    if (tabKeys[ev.key]) {{
      const pill = document.querySelector(`.tab-pill[data-tab="${{tabKeys[ev.key]}}"]`);
      if (pill) pill.click();
    }}
    if (ev.key === '/') {{
      ev.preventDefault();
      searchWrap.classList.add('open');
      globalSearch.focus();
    }}
  }});

  // ── Telegram lightbox ──
  let tgLb = null, tgLbImages = [], tgLbIdx = 0;
  function ensureTgLightbox() {{
    if (tgLb) return;
    tgLb = document.createElement('div');
    tgLb.className = 'tg-lightbox';
    tgLb.innerHTML = `<button class="tg-lb-close">&times;</button>
      <button class="tg-lb-nav tg-lb-prev">&lsaquo;</button>
      <img src="" alt="Image">
      <div class="tg-lb-error">Image unavailable</div>
      <button class="tg-lb-nav tg-lb-next">&rsaquo;</button>
      <div class="tg-lb-counter">1 / 1</div>`;
    document.body.appendChild(tgLb);
    tgLb.querySelector('.tg-lb-close').addEventListener('click', closeTgLightbox);
    tgLb.addEventListener('click', (e) => {{ if (e.target === tgLb) closeTgLightbox(); }});
    tgLb.querySelector('.tg-lb-prev').addEventListener('click', () => showTgImg(tgLbIdx - 1));
    tgLb.querySelector('.tg-lb-next').addEventListener('click', () => showTgImg(tgLbIdx + 1));
    document.addEventListener('keydown', (e) => {{
      if (!tgLb.classList.contains('open')) return;
      if (e.key === 'Escape') closeTgLightbox();
      if (e.key === 'ArrowLeft') showTgImg(tgLbIdx - 1);
      if (e.key === 'ArrowRight') showTgImg(tgLbIdx + 1);
    }});
  }}
  function showTgImg(idx) {{
    if (idx < 0 || idx >= tgLbImages.length) return;
    tgLbIdx = idx;
    const img = tgLb.querySelector('img');
    const errEl = tgLb.querySelector('.tg-lb-error');
    img.style.display = 'block';
    errEl.style.display = 'none';
    img.onerror = () => {{ img.style.display = 'none'; errEl.style.display = 'flex'; }};
    img.onload = () => {{ img.style.display = 'block'; errEl.style.display = 'none'; }};
    img.src = tgLbImages[idx];
    tgLb.querySelector('.tg-lb-counter').textContent = (idx + 1) + ' / ' + tgLbImages.length;
    tgLb.querySelector('.tg-lb-prev').style.display = tgLbImages.length > 1 ? '' : 'none';
    tgLb.querySelector('.tg-lb-next').style.display = tgLbImages.length > 1 ? '' : 'none';
  }}
  function closeTgLightbox() {{
    tgLb.classList.remove('open');
    setTimeout(() => tgLb.style.display = 'none', 300);
  }}
  window.openTgLightbox = function(btn) {{
    ensureTgLightbox();
    try {{ tgLbImages = JSON.parse(btn.dataset.images || '[]'); }} catch(e) {{ tgLbImages = []; }}
    if (!tgLbImages.length) return;
    tgLb.style.display = 'flex';
    requestAnimationFrame(() => tgLb.classList.add('open'));
    showTgImg(0);
  }};

  try {{
    bindBk();
    renderPanel();
    syncAllBk();

    // Open tab from URL hash (e.g. home.html#telegram)
    const initHash = location.hash.replace('#', '');
    if (initHash && document.getElementById('tab-' + initHash)) {{
      switchTab(initHash);
    }}
  }} catch(e) {{ console.error('Init failed:', e); }}
}})();
</script>

</body>
</html>'''


def main():
    data = load()
    out_dir = OUT / 'v13-homepage'
    out_dir.mkdir(parents=True, exist_ok=True)
    html = build_html(data)
    (out_dir / 'home.html').write_text(html)
    feed_n = len(data['feed'])
    yt_n = len(data['youtube'])
    rp_n = len(data['reports'])
    tw_n = len(data['twitter'])
    wsw_n = len(data.get('wsw', []))
    print(f"wrote v13-homepage/home.html (feed={feed_n}, yt={yt_n}, rp={rp_n}, tw={tw_n}, wsw={wsw_n})")

if __name__ == '__main__':
    main()
