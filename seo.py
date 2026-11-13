"""Search-engine and AI-crawler support for the generated homepage.

Two pieces, both pure functions so they are easy to test:

- head_tags(): the <title>, description, canonical link, Open Graph/Twitter
  text tags and a JSON-LD block naming the site. Google uses these for the
  search result; chat apps use the og:* tags for link previews.
- crawler_digest_html(): today's top AI-ranked headlines as plain HTML. It is
  written inside #home-newspaper, which app.js replaces on load, and CSS hides
  it whenever JavaScript runs (html.js). So readers never see it, but crawlers
  that do not run JavaScript (most AI crawlers) read real stories, not an
  empty shell. Readers without JavaScript get a plain list instead of a blank
  page.
"""

import json
from html import escape

SITE_URL = "https://financeradar.news/"
SITE_NAME = "Finance Radar"
TITLE = "Finance Radar — India's finance news and research, in one feed"
DESCRIPTION = (
    "Indian finance news, research reports, broker stock notes, Telegram, "
    "YouTube and Twitter from 290+ sources, ranked twice a day by AI. "
    "No ads, no tracking."
)
TAGLINE = (
    "A calm way to read Indian finance: one feed from 290+ sources — news "
    "desks, independent writers, research houses, brokers' stock notes, "
    "official channels like RBI and SEBI, Telegram, YouTube and Twitter — "
    "ranked twice a day by four AI models. No ads, no tracking."
)

DIGEST_SIZE = 20


def head_tags():
    """Meta tags for <head>. Returns an HTML string (no <title> duplicates)."""
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": SITE_URL + "#website",
                "url": SITE_URL,
                "name": SITE_NAME,
                "alternateName": ["FinanceRadar", "financeradar.news"],
                "description": DESCRIPTION,
                "inLanguage": "en-IN",
                "creator": {"@id": SITE_URL + "#creator"},
            },
            {
                # Already public on /about.
                "@type": "Person",
                "@id": SITE_URL + "#creator",
                "name": "Kashish Kapoor",
                "url": "https://kashishkapoor.com",
            },
            {
                "@type": "Organization",
                "@id": SITE_URL + "#organization",
                "url": SITE_URL,
                "name": SITE_NAME,
            },
        ],
    }
    # "</" can't appear inside the JSON, so the script tag can't be closed early.
    ld_json = json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")
    t, d, u = escape(TITLE), escape(DESCRIPTION), escape(SITE_URL)
    return f"""<title>{t}</title>
    <meta name="description" content="{d}">
    <link rel="canonical" href="{u}">
    <meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="{escape(SITE_NAME)}">
    <meta property="og:title" content="{t}">
    <meta property="og:description" content="{d}">
    <meta property="og:url" content="{u}">
    <meta property="og:locale" content="en_IN">
    <meta name="twitter:card" content="summary">
    <meta name="twitter:title" content="{t}">
    <meta name="twitter:description" content="{d}">
    <script type="application/ld+json">{ld_json}</script>"""


def _story_key(item):
    url = (item.get("url") or "").strip().lower()
    return url or " ".join((item.get("title") or "").lower().split())


def top_headlines(rankings, limit=DIGEST_SIZE):
    """Consensus top news stories across the AI providers.

    Same idea as getMergedAiRankings() in app.js, kept simple: stories picked
    by more models first, then by average rank. Order is close to the
    homepage, not identical — it only feeds the crawler digest.
    """
    if not isinstance(rankings, dict):
        return []
    merged = {}
    for provider in (rankings.get("providers") or {}).values():
        if not isinstance(provider, dict) or provider.get("status") not in (None, "ok"):
            continue
        for item in (provider.get("buckets") or {}).get("news") or []:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            key = _story_key(item)
            entry = merged.setdefault(key, {"item": item, "ranks": []})
            entry["ranks"].append(item.get("rank") or 99)
    ordered = sorted(
        merged.values(),
        key=lambda e: (-len(e["ranks"]), sum(e["ranks"]) / len(e["ranks"])),
    )
    return [e["item"] for e in ordered[:limit]]


def _safe_url(url):
    url = (url or "").strip()
    return url if url.lower().startswith(("https://", "http://")) else ""


def crawler_digest_html(rankings, today_str):
    """Plain-HTML digest for crawlers and no-JS readers ('' if no rankings)."""
    items = top_headlines(rankings)
    rows = []
    for it in items:
        title = escape(it.get("title", "").strip())
        source = escape((it.get("source") or "").strip())
        url = _safe_url(it.get("url"))
        head = f'<a href="{escape(url)}" rel="noopener">{title}</a>' if url else title
        rows.append(f"<li>{head}{' — ' + source if source else ''}</li>")
    parts = [
        '<section class="crawler-digest">',
        f"<h1>{escape(SITE_NAME)}</h1>",
        f"<p>{escape(TAGLINE)}</p>",
    ]
    if rows:
        parts.append(f"<h2>Top stories in Indian finance — {escape(today_str)}</h2>")
        parts.append("<ol>" + "".join(rows) + "</ol>")
    parts.append('<p><a href="/about">About Finance Radar</a></p>')
    parts.append("</section>")
    return "".join(parts)
