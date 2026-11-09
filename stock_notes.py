"""Shared helpers for broker stock notes (Reports tab → "Stock notes" view).

A stock note is one broker's call on one listed Indian company: rating,
target price and a PDF. Notes arrive from aggregators today (Moneycontrol,
Business Standard) and from brokers' own sites later, so everything that has
to agree across sources lives here:

- canonical_broker(): one spelling per broker, and None for anything we
  must not show (foreign brokers — the view is Indian-only — and the
  aggregators' own picks, which are not brokerage research)
- canonical_rating(): "BUY"/"accumulate"/"N" → one display form
- dedup_stock_notes(): the same call listed on two sites is kept once
"""

import re
from datetime import timedelta

STOCK_NOTE_KIND = "stock_note"

# Extra per-note fields shipped to static/tab_research.json for the card.
STOCK_NOTE_FIELDS = ("company", "rating", "target", "reco_price", "prev_target", "prev_rating", "via")

# Days apart two listings of the same call can be. Moneycontrol dates a
# note by the report, Business Standard sometimes by its own posting day.
DEDUP_WINDOW_DAYS = 3

# (pattern on the lowercased name, canonical name). First match wins.
_BROKER_ALIASES = [
    (r"^motilal+a? oswal", "Motilal Oswal"),
    (r"^icici ?(securities|direct)", "ICICI Securities"),
    (r"^prabhudas|^pl capital", "Prabhudas Lilladher"),
    (r"^e[mn]kay", "Emkay Global"),
    (r"^choice", "Choice Broking"),
    (r"^centrum", "Centrum Broking"),
    (r"^edelwei", "Edelweiss Securities"),
    (r"^equirus", "Equirus Securities"),
    (r"^geojit", "Geojit"),
    (r"^share ?khan", "Sharekhan"),
    (r"^lkp", "LKP Securities"),
    (r"^anand rathi", "Anand Rathi"),
    (r"^jm financial", "JM Financial"),
    (r"^elara", "Elara Capital"),
    (r"^incred", "InCred Equities"),
    (r"^yes sec", "YES Securities"),
    (r"^hdfc sec", "HDFC Securities"),
    (r"^kotak sec", "Kotak Securities"),
    (r"^axis sec|^axis direct", "Axis Securities"),
    (r"^nirmal bang", "Nirmal Bang"),
    (r"^idbi cap", "IDBI Capital"),
    (r"^ambit", "Ambit Capital"),
    (r"^nuvama", "Nuvama"),
]

# Never shown in Stock notes: foreign houses (view is Indian-only) and
# aggregators' in-house picks. Matched as a prefix of the lowercased name.
_EXCLUDED_BROKERS = re.compile(
    r"^(citi|jefferies|morgan stanley|clsa|nomura|goldman|gs\b|jp ?morgan|jpm\b|"
    r"ubs|bofa|bank of america|merrill|macquarie|hsbc|bernstein|investec|"
    r"barclays|credit suisse|deutsche|daiwa|mizuho|bnp|societe|"
    r"moneycontrol|business standard|trendlyne)"
)

_RATINGS = {
    "b": "Buy", "buy": "Buy", "strong buy": "Buy", "outperform": "Buy",
    "accumulate": "Accumulate", "add": "Accumulate",
    "h": "Hold", "hold": "Hold", "n": "Hold", "neutral": "Neutral",
    "reduce": "Reduce", "underweight": "Reduce",
    "s": "Sell", "sell": "Sell", "underperform": "Sell",
    "initiating coverage": "Initiating coverage",
}

_COMPANY_SUFFIX = re.compile(r"[\s,.]+(ltd|limited|ltd\.)\.?$", re.I)
_TOKEN_STOP = {"the", "and", "of", "india", "ltd", "limited"}


def canonical_broker(name):
    """One display name per broker, or None if it must not be shown."""
    raw = re.sub(r"\s+", " ", (name or "")).strip()
    if not raw:
        return None
    low = raw.lower()
    if _EXCLUDED_BROKERS.match(low):
        return None
    for pattern, canonical in _BROKER_ALIASES:
        if re.match(pattern, low):
            return canonical
    return raw


def canonical_rating(raw):
    key = re.sub(r"\s+", " ", (raw or "")).strip().lower()
    return _RATINGS.get(key)


def clean_company(name):
    name = re.sub(r"\s+", " ", (name or "")).strip()
    return _COMPANY_SUFFIX.sub("", name).strip()


def parse_price(value):
    """'1,180' / 285 / '285.5' → float; anything else → None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        num = float(str(value).replace(",", "").replace("₹", "").strip())
    except ValueError:
        return None
    return num if num > 0 else None


def note_title(company, rating, target):
    """'Infosys: Buy, target ₹1,300' — the broker is shown beside it on the card."""
    parts = [p for p in (rating, f"target ₹{target:,.0f}" if target else None) if p]
    return f"{company}: {', '.join(parts)}" if parts else company


def _company_key(company):
    tokens = [t for t in re.findall(r"[a-z0-9]+", (company or "").lower()) if t not in _TOKEN_STOP]
    return tokens[0] if tokens else ""


def _richness(note):
    """Prefer the listing that carries more: previous call, then reco price."""
    return (note.get("prev_target") is not None, note.get("reco_price") is not None)


def dedup_stock_notes(items, window_days=DEDUP_WINDOW_DAYS):
    """Drop repeat listings of one broker call; other reports pass through.

    Same call = same broker, same target, same first word of the company
    name, dated within `window_days`. Sites spell company names differently
    ("M & M" vs "Mahindra and Mahindra") so the target does most of the
    work; two different stocks from one broker with one target in one
    3-day window is vanishingly rare. Order of survivors is preserved.
    """
    window = timedelta(days=window_days)
    kept = []          # survivors in input order
    by_key = {}        # (broker, target, company key) → [index into kept]
    for item in items:
        if item.get("kind") != STOCK_NOTE_KIND or not item.get("target"):
            kept.append(item)
            continue
        key = (item.get("publisher"), round(item["target"], 2), _company_key(item.get("company")))
        match = None
        for idx in by_key.get(key, []):
            other = kept[idx]
            d1, d2 = item.get("date"), other.get("date")
            if d1 is None or d2 is None or abs(d1 - d2) <= window:
                match = idx
                break
        if match is None:
            by_key.setdefault(key, []).append(len(kept))
            kept.append(item)
        elif _richness(item) > _richness(kept[match]):
            kept[match] = item
    return kept
