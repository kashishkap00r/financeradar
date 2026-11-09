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

import json
import os
import re
import subprocess
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from articles import IST_TZ

STOCK_NOTE_KIND = "stock_note"

# The archive: every note ever seen, newest first. The page loads it only
# when someone opens Stock notes, so its size never touches the homepage.
ARCHIVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "stock_notes.json")

# Headline extraction: page 1 of each PDF → Gemini picks the report's own
# headline. A note is given up on after this many tries (bad PDF, scanned
# image, no headline on the page).
HEADLINE_MAX_TRIES = 2
HEADLINE_CHAIN = ["gemini-3.1-flash-lite", "gemini-2.5-flash", "gemini-flash-latest"]
HEADLINE_PAGE_CHARS = 1800
PDF_MAX_BYTES = 30 * 1024 * 1024
PDF_TIMEOUT = 40

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
    (r"^(mirae asset )?share ?khan", "Sharekhan"),
    (r"^kr ?choksey|^deven choksey", "KR Choksey"),
    (r"^iifl", "IIFL"),
    (r"^religare", "Religare"),
    (r"^lkp", "LKP Securities"),
    (r"^anand ?rathi", "Anand Rathi"),
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


_COMPANY_FORM = re.compile(r"[\s,.]+(pvt\.?|private)?\s*(ltd\.?|limited)$", re.I)


def canonical_broker(name):
    """One display name per broker, or None if it must not be shown."""
    raw = _COMPANY_FORM.sub("", re.sub(r"\s+", " ", (name or "")).strip()).strip()
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
    """Prefer the listing that carries more: a headline, then previous call, then reco price."""
    return (bool(note.get("headline")), note.get("prev_target") is not None, note.get("reco_price") is not None)


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


# ── Archive: static/stock_notes.json ─────────────────────────────────

def _archive_sort_key(entry):
    return (entry.get("date") or "", entry.get("broker") or "", entry.get("company") or "", entry.get("link") or "")


def _to_entry(article):
    dt = article.get("date")
    if dt is not None and dt.tzinfo is not None:
        dt = dt.astimezone(IST_TZ)
    return {
        "date": dt.date().isoformat() if dt else "",
        "broker": article.get("publisher") or "",
        "company": article.get("company") or "",
        "headline": "",
        "link": article.get("link") or "",
        "via": article.get("via") or "",
        "target": article.get("target"),
        "headline_tries": 0,
    }


def _entry_as_note(entry, **extra):
    """Archive entry → the shape dedup_stock_notes() reads."""
    try:
        dt = datetime.fromisoformat(entry["date"]).replace(tzinfo=IST_TZ) if entry.get("date") else None
    except ValueError:
        dt = None
    return {"kind": STOCK_NOTE_KIND, "publisher": entry.get("broker"), "company": entry.get("company"),
            "target": entry.get("target"), "date": dt, "headline": entry.get("headline"),
            "_entry": entry, **extra}


def merge_into_archive(archive, articles):
    """Add newly fetched notes to the archive; returns it sorted newest first.

    Links already archived are left alone (they keep their headline). A new
    listing of a call the archive already holds — same call on the other
    site — is dropped by the same rule as dedup_stock_notes(), with the
    headline-bearing entry winning.
    """
    known = {e["link"] for e in archive}
    fresh = []
    for art in articles:
        if art.get("kind") != STOCK_NOTE_KIND or not art.get("link") or art["link"] in known:
            continue
        known.add(art["link"])
        fresh.append(_entry_as_note(_to_entry(art), prev_target=art.get("prev_target"),
                                    reco_price=art.get("reco_price")))
    if not fresh:
        return sorted(archive, key=_archive_sort_key, reverse=True)
    notes = [_entry_as_note(e) for e in archive] + fresh
    kept = dedup_stock_notes(notes)
    return sorted((n["_entry"] for n in kept), key=_archive_sort_key, reverse=True)


def load_archive(path=ARCHIVE_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return [e for e in data if isinstance(e, dict) and e.get("link")] if isinstance(data, list) else []


def save_archive(path, entries):
    """Atomic write, one note per line: hourly commits then touch a few lines, not the file."""
    entries = sorted(entries, key=_archive_sort_key, reverse=True)
    body = "[\n" + ",\n".join(json.dumps(e, ensure_ascii=False, sort_keys=True) for e in entries) + "\n]\n"
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        os.chmod(tmp, 0o644)  # mkstemp makes it owner-only; this is a public web file
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ── Headlines: page 1 of the PDF → the report's own title ───────────

def clean_headline(text, company):
    h = re.sub(r"\s+", " ", (text or "")).strip().strip("\"'“”‘’").strip()
    if len(h) < 4 or len(h) > 200:
        return ""
    if h.lower() == (company or "").strip().lower():
        return ""
    return h


def pdf_first_page_text(link, user_agent="Mozilla/5.0 (compatible; FinanceRadar)"):
    """Download one PDF to a temp file and return page 1 as text (needs poppler's pdftotext)."""
    req = urllib.request.Request(link, headers={"User-Agent": user_agent, "Accept": "application/pdf,*/*"})
    with urllib.request.urlopen(req, timeout=PDF_TIMEOUT) as resp:
        data = resp.read(PDF_MAX_BYTES + 1)
    if len(data) > PDF_MAX_BYTES or not data.startswith(b"%PDF"):
        raise ValueError("not a PDF (or too large)")
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(data)
        tmp.flush()
        out = subprocess.run(["pdftotext", "-f", "1", "-l", "1", "-enc", "UTF-8", tmp.name, "-"],
                             capture_output=True, timeout=30, check=True)
    text = re.sub(r"[ \t]+", " ", out.stdout.decode("utf-8", "replace"))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    if len(text) < 40:
        raise ValueError("page 1 has no text (scanned image?)")
    return text[:HEADLINE_PAGE_CHARS]


_HEADLINE_PROMPT = """Below is the text of page 1 of {n} Indian brokerage research reports, extracted from PDFs (columns may be jumbled).
For each report, return the report's HEADLINE: the analyst's one-line title or thesis, usually in large type near the top.
Examples of headlines: "Production drag persists; valuations factor in USD62/bbl Brent", "2Q beat led by strong growth across brands", "Consistent and meaningful execution!".

Never return: the company name on its own, sector, the rating (BUY/HOLD/SELL), CMP or target-price lines, dates, analyst names, disclaimers, or a bare report-type label like "Result Update" — unless the page truly has nothing else, in which case return "".
Copy the headline exactly as written; only repair broken spacing or hyphenation. Do not invent or summarise.

Reply with JSON only: {{"headlines": [{{"n": 1, "headline": "..."}}, ...]}}

{reports}"""


def _gemini_headlines(batch):
    """Default ask_model: one Gemini call for a batch of notes → {link: headline}."""
    from gemini_client import generate_json  # imported lazily: tests and offline runs don't need it

    reports = "\n\n".join(
        f"### Report {i}\nCompany: {b['company']}\nBroker: {b['broker']}\n---\n{b['text']}"
        for i, b in enumerate(batch, 1)
    )
    prompt = _HEADLINE_PROMPT.format(n=len(batch), reports=reports)

    def parse(text):
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(json)?|```$", "", text, flags=re.M).strip()
        return json.loads(text)

    data, _model = generate_json(prompt, HEADLINE_CHAIN, parse=parse, timeout=90, attempts=2, label="stock-headlines")
    by_n = {}
    for row in (data or {}).get("headlines", []):
        if isinstance(row, dict) and isinstance(row.get("n"), int):
            by_n[row["n"]] = row.get("headline") or ""
    return {b["link"]: by_n.get(i, "") for i, b in enumerate(batch, 1)}


def fill_headlines(entries, *, limit, pdf_text=pdf_first_page_text, ask_model=_gemini_headlines,
                   workers=4, batch_size=8, time_budget=None, on_progress=None):
    """Give archive entries their PDF headline, newest first, in place.

    Returns how many got one. A failed download or a page with no headline
    burns one of HEADLINE_MAX_TRIES; a Gemini outage does not (it is not
    the PDF's fault), so those notes are simply retried next run.
    """
    started = time.monotonic()
    pending = [e for e in sorted(entries, key=_archive_sort_key, reverse=True)
               if not e.get("headline") and e.get("headline_tries", 0) < HEADLINE_MAX_TRIES][:limit]
    filled = 0
    for start in range(0, len(pending), batch_size * workers):
        if time_budget is not None and time.monotonic() - started > time_budget:
            break
        chunk = pending[start:start + batch_size * workers]

        def _text(entry):
            try:
                return entry, pdf_text(entry["link"])
            except Exception:
                return entry, None

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            got = list(pool.map(_text, chunk))
        ready = []
        for entry, text in got:
            if text is None:
                entry["headline_tries"] = entry.get("headline_tries", 0) + 1
            else:
                ready.append({"link": entry["link"], "company": entry.get("company", ""),
                              "broker": entry.get("broker", ""), "text": text, "_entry": entry})
        batches = [ready[i:i + batch_size] for i in range(0, len(ready), batch_size)]

        def _ask(batch):
            try:
                return batch, ask_model(batch)
            except Exception as err:
                print(f"    [stock-headlines] model call failed: {str(err)[:120]}")
                return batch, None

        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(batches) or 1))) as pool:
            answers = list(pool.map(_ask, batches))
        for batch, answer in answers:
            if answer is None:
                continue
            for b in batch:
                entry = b["_entry"]
                headline = clean_headline(answer.get(b["link"], ""), entry.get("company"))
                if headline:
                    entry["headline"] = headline
                    filled += 1
                else:
                    entry["headline_tries"] = entry.get("headline_tries", 0) + 1
        if on_progress:
            on_progress(start + len(chunk), len(pending), filled)
    return filled
