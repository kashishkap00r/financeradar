"""Homepage "This Week" calendar.

Writes static/calendar.json (read by the browser) and static/calendar.ics
("Add to my calendar") from four inputs:

- calendar_macro.json (repo root, hand-kept): India data releases, policy dates
  and the main global events (US Fed decision, US CPI), from the agencies'
  published calendars. Unconfirmed dates carry "confirmed": false.
- NSE's event calendar: board meetings for results, kept to Nifty 200 members.
  NSE only lists dates from tomorrow on, so static/results_calendar_cache.json
  keeps today's entries and covers runs where NSE can't be reached.
- NSE's trading-holiday list (static/nse_holidays.json, refreshed daily).
- Rules: monthly F&O expiry (last Tuesday, moved back over holidays), the
  results deadline (45 days after a quarter, 60 after March), RBI's weekly forex
  reserves (Fridays).

Nothing here can stop the hourly run: build_calendar() logs and returns on any
failure, and every fetch falls back to the last good copy on disk.
"""

import csv
import hashlib
import http.cookiejar
import io
import json
import os
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(SCRIPT_DIR, "static")
MACRO_FILE = os.path.join(SCRIPT_DIR, "calendar_macro.json")
OUT_JSON = os.path.join(STATIC_DIR, "calendar.json")
OUT_ICS = os.path.join(STATIC_DIR, "calendar.ics")
RESULTS_CACHE = os.path.join(STATIC_DIR, "results_calendar_cache.json")
INDEX_CACHE = os.path.join(STATIC_DIR, "nifty200.json")
HOLIDAY_CACHE = os.path.join(STATIC_DIR, "nse_holidays.json")

IST = timezone(timedelta(hours=5, minutes=30))
WINDOW_DAYS = 35            # today + 5 weeks; the drawer shows four
INDEX_REFRESH_DAYS = 7      # Nifty indices rebalance twice a year
HOLIDAY_REFRESH_HOURS = 24
HTTP_TIMEOUT = 20

KINDS = ("india", "policy", "market", "global")

NSE_HOME = "https://www.nseindia.com/"
EVENT_CALENDAR_URL = "https://www.nseindia.com/api/event-calendar"
HOLIDAY_URL = "https://www.nseindia.com/api/holiday-master?type=trading"
INDEX_CSV_URLS = {
    50: "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
    100: "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
    200: "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv",
}
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

QUARTER_NAMES = {3: "March", 6: "June", 9: "September", 12: "December"}

# The names readers use for companies whose official name is long (by NSE symbol).
COMMON_NAMES = {
    "IRCTC": "IRCTC", "IREDA": "IREDA", "IRFC": "IRFC", "LICI": "LIC", "ONGC": "ONGC", "MCX": "MCX",
    "CHOLAFIN": "Cholamandalam Finance", "ICICIAMC": "ICICI Prudential AMC", "ICICIGI": "ICICI Lombard",
    "M&MFIN": "M&M Finance", "ADANIPORTS": "Adani Ports", "MOTHERSON": "Samvardhana Motherson",
    "OFSS": "Oracle Financial Services", "CGPOWER": "CG Power", "MOTILALOFS": "Motilal Oswal",
    "POWERGRID": "Power Grid", "HINDPETRO": "HPCL", "BPCL": "BPCL", "IOC": "Indian Oil",
    "SBICARD": "SBI Card", "CONCOR": "Container Corporation", "SUNPHARMA": "Sun Pharma",
    "HDFCAMC": "HDFC AMC", "HAL": "HAL", "BEL": "BEL", "BHEL": "BHEL", "NTPC": "NTPC", "GAIL": "GAIL",
    "SBIN": "SBI", "SBILIFE": "SBI Life", "HDFCLIFE": "HDFC Life", "ICICIPRULI": "ICICI Prudential Life",
    "M&M": "Mahindra & Mahindra", "TCS": "TCS", "LT": "L&T", "INDIGO": "IndiGo",
}


def _log(logger, msg, warn=False):
    if logger is None:
        print(f"[calendar] {msg}")
    elif warn:
        logger.warn("calendar", msg)
    else:
        logger.info(f"[calendar] {msg}")


# ---------------------------------------------------------------- files ----

def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def _write_json(path, payload, compact=False):
    if compact:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=1)
    _atomic_write(path, text + "\n")


def _age_hours(stamp, now):
    try:
        then = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return float("inf")
    if then.tzinfo is None:
        then = then.replace(tzinfo=IST)
    return (now - then).total_seconds() / 3600


# ---------------------------------------------------------------- fetch ----

def _opener():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def _get(opener, url, accept="application/json"):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": NSE_HOME,
    })
    with opener.open(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.read()


def fetch_nse_json(url):
    """NSE's JSON API. Tries straight away, then again after loading the home
    page for cookies (what NSE expects from a browser)."""
    opener = _opener()
    try:
        return json.loads(_get(opener, url))
    except Exception:
        _get(opener, NSE_HOME, accept="text/html")
        return json.loads(_get(opener, url))


def fetch_text(url):
    return _get(_opener(), url, accept="text/csv,*/*").decode("utf-8-sig", "replace")


# ---------------------------------------------------------------- index ----

def short_company_name(name):
    name = re.sub(r"\s+", " ", (name or "")).strip()
    name = re.sub(r"\s*\b(Ltd\.?|Limited)$", "", name, flags=re.I).strip()
    return name.rstrip(".,").strip()


def parse_index_csv(text):
    """NSE index constituent CSV → {symbol: short company name}."""
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        sym = (row.get("Symbol") or "").strip()
        if sym:
            out[sym] = short_company_name(row.get("Company Name"))
    return out


def build_index(lists):
    """{50: {...}, 100: {...}, 200: {...}} → {symbol: {"name", "tier"}}.
    Tier 1 = Nifty 50, 2 = rest of Nifty 100, 3 = rest of Nifty 200. Tiers set
    which names a day shows first ("Results: Tata Steel, HAL +8")."""
    index = {}
    for size, tier in ((200, 3), (100, 2), (50, 1)):
        for sym, name in (lists.get(size) or {}).items():
            index[sym] = {"name": COMMON_NAMES.get(sym, name), "tier": tier}
    return index


def load_index(now, fetch=True, logger=None):
    cache = _read_json(INDEX_CACHE, {})
    index = cache.get("index") or {}
    if fetch and (not index or _age_hours(cache.get("fetched_at"), now) > INDEX_REFRESH_DAYS * 24):
        try:
            lists = {size: parse_index_csv(fetch_text(url)) for size, url in INDEX_CSV_URLS.items()}
            if len(lists[200]) >= 150:
                index = build_index(lists)
                _write_json(INDEX_CACHE, {"fetched_at": now.isoformat(timespec="seconds"), "index": index})
                _log(logger, f"Nifty 200 list refreshed ({len(index)} companies)")
            else:
                _log(logger, f"Nifty 200 list looked short ({len(lists[200])}); kept the cached one", warn=True)
        except Exception as e:
            _log(logger, f"Nifty 200 list fetch failed ({e}); using cache", warn=True)
    return index


# -------------------------------------------------------------- results ----

def _parse_nse_date(text):
    try:
        return datetime.strptime((text or "").strip(), "%d-%b-%Y").date()
    except ValueError:
        return None


def parse_event_calendar(items, index):
    """NSE event-calendar rows → [{"date", "symbol"}] for index members' results."""
    out, seen = [], set()
    for it in items or []:
        sym = (it.get("symbol") or "").strip()
        if sym not in index or "financial results" not in (it.get("purpose") or "").lower():
            continue
        d = _parse_nse_date(it.get("date"))
        if not d or (d, sym) in seen:
            continue
        seen.add((d, sym))
        out.append({"date": d.isoformat(), "symbol": sym})
    return out


def merge_results(cached, fresh, today, fetched_ok):
    """Today's entries come only from the cache (NSE lists from tomorrow on).
    When NSE answered, it is the truth for every later date: a company it no
    longer lists has moved or cancelled. When it didn't, keep what we had."""
    keep_from = today - timedelta(days=0 if fetched_ok else 1)
    out = []
    if fetched_ok:
        fresh_syms = {r["symbol"] for r in fresh}
        for r in cached:
            d = r.get("date", "")
            if d == today.isoformat() and r.get("symbol") not in fresh_syms:
                out.append({"date": d, "symbol": r["symbol"]})
        out.extend({"date": r["date"], "symbol": r["symbol"]} for r in fresh if r["date"] >= today.isoformat())
    else:
        out = [{"date": r["date"], "symbol": r["symbol"]} for r in cached
               if r.get("date", "") >= keep_from.isoformat()]
    uniq = {(r["date"], r["symbol"]): r for r in out}
    return sorted(uniq.values(), key=lambda r: (r["date"], r["symbol"]))


def load_results(index, now, fetch=True, logger=None):
    today = now.date()
    cache = _read_json(RESULTS_CACHE, {})
    cached = cache.get("results") or []
    fresh, ok = [], False
    if fetch and index:
        try:
            fresh = parse_event_calendar(fetch_nse_json(EVENT_CALENDAR_URL), index)
            ok = True
        except Exception as e:
            _log(logger, f"NSE event calendar fetch failed ({e}); using cache", warn=True)
    merged = merge_results(cached, fresh, today, ok)
    payload = {"fetched_at": now.isoformat(timespec="seconds") if ok else cache.get("fetched_at"),
               "results": merged}
    if ok or merged != cached:
        _write_json(RESULTS_CACHE, payload)
    if ok:
        _log(logger, f"Results dates: {len(fresh)} upcoming Nifty 200 board meetings")
    return merged


# ------------------------------------------------------------- holidays ----

def parse_holidays(data):
    out = {}
    for row in (data or {}).get("CM") or []:
        d = _parse_nse_date(row.get("tradingDate"))
        if d:
            out[d.isoformat()] = (row.get("description") or "Trading holiday").strip()
    return out


def load_holidays(now, fetch=True, logger=None):
    cache = _read_json(HOLIDAY_CACHE, {})
    holidays = cache.get("holidays") or {}
    if fetch and _age_hours(cache.get("fetched_at"), now) > HOLIDAY_REFRESH_HOURS:
        try:
            fresh = parse_holidays(fetch_nse_json(HOLIDAY_URL))
            if fresh:
                holidays = {**holidays, **fresh}  # keep last year's when the new list arrives
                _write_json(HOLIDAY_CACHE, {"fetched_at": now.isoformat(timespec="seconds"),
                                            "holidays": dict(sorted(holidays.items()))})
        except Exception as e:
            _log(logger, f"NSE holiday list fetch failed ({e}); using cache", warn=True)
    return holidays


# ------------------------------------------------------- dates by rule ----

def _is_trading_day(d, holidays):
    return d.weekday() < 5 and d.isoformat() not in holidays


def _event(d, name, kind, time=None, source="", short="", big=False, confirmed=True):
    return {"date": d.isoformat(), "time": time, "name": name, "short": short, "kind": kind,
            "big": big, "source": source, "confirmed": confirmed}


def monthly_expiry(year, month, holidays):
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    d = nxt - timedelta(days=1)
    while d.weekday() != 1:  # Tuesday
        d -= timedelta(days=1)
    while not _is_trading_day(d, holidays):
        d -= timedelta(days=1)
    return d


def expiry_events(start, end, holidays):
    out, y, m = [], start.year, start.month
    while date(y, m, 1) <= end:
        d = monthly_expiry(y, m, holidays)
        if start <= d <= end:
            out.append(_event(d, "Monthly F&O expiry", "market", short="F&O expiry", source="NSE"))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def results_deadline_events(start, end):
    out = []
    for year in range(start.year - 1, end.year + 1):
        for month, last_day in ((3, 31), (6, 30), (9, 30), (12, 31)):
            q_end = date(year, month, last_day)
            d = q_end + timedelta(days=60 if month == 3 else 45)
            if start <= d <= end:
                out.append(_event(d, f"Last day for {QUARTER_NAMES[month]}-quarter results", "market",
                                  short="Results deadline", source="SEBI"))
    return out


def forex_reserve_events(start, end):
    out, d = [], start + timedelta(days=(4 - start.weekday()) % 7)
    while d <= end:
        out.append(_event(d, "Forex reserves", "india", time="17:00", source="RBI, weekly"))
        d += timedelta(days=7)
    return out


def holiday_events(holidays, start, end):
    out = []
    for ds, desc in sorted(holidays.items()):
        d = date.fromisoformat(ds)
        if start <= d <= end and d.weekday() < 5:
            out.append(_event(d, f"Markets shut: {desc}", "market", short="Market holiday", source="NSE"))
    return out


# ---------------------------------------------------------------- macro ----

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def load_macro_events(path=MACRO_FILE):
    """Hand-kept events. Bad rows are skipped (a typo must not empty the rail);
    a bad time becomes "no time"."""
    data = _read_json(path, {})
    rows = data.get("events") if isinstance(data, dict) else data
    out = []
    for r in rows or []:
        try:
            d = date.fromisoformat(r.get("date", ""))
        except (TypeError, ValueError):
            continue
        kind = r.get("kind", "india")
        if kind not in KINDS or not r.get("name"):
            continue
        t = r.get("time")
        out.append(_event(d, r["name"].strip(), kind,
                          time=t if isinstance(t, str) and _TIME_RE.match(t) else None,
                          source=r.get("source", ""), short=r.get("short", ""),
                          big=bool(r.get("big")), confirmed=r.get("confirmed", True) is not False))
    return out


# ---------------------------------------------------------------- build ----

def build_days(events, results, index, start, end):
    days = {}
    for e in events:
        if start.isoformat() <= e["date"] <= end.isoformat():
            days.setdefault(e["date"], {"events": [], "results": []})["events"].append(e)
    for r in results:
        co = index.get(r["symbol"])
        if co and start.isoformat() <= r["date"] <= end.isoformat():
            days.setdefault(r["date"], {"events": [], "results": []})["results"].append(co)
    out = []
    for ds in sorted(days):
        evs = sorted(days[ds]["events"], key=lambda e: (e.get("time") is None, e.get("time") or "", e["name"]))
        cos = sorted(days[ds]["results"], key=lambda c: (c["tier"], c["name"].lower()))
        out.append({"date": ds, "events": [_public_event(e) for e in evs], "results": [c["name"] for c in cos]})
    return out


def _public_event(e):
    """The fields the browser needs, empty ones left out. An unconfirmed date
    becomes "expected": true (shown as "expected")."""
    out = {k: e[k] for k in ("name", "time", "short", "kind", "source") if e.get(k)}
    if e.get("big"):
        out["big"] = True
    if e.get("confirmed", True) is False or e.get("expected"):
        out["expected"] = True
    return out


def _ics_escape(text):
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n"))


def _ics_fold(line):
    """RFC 5545: lines at most 75 octets; continuation lines start with a space."""
    out, cur = [], ""
    for ch in line:
        limit = 75 if not out else 74
        if len((cur + ch).encode("utf-8")) > limit:
            out.append(cur)
            cur = ch
        else:
            cur += ch
    out.append(cur)
    return "\r\n ".join(out)


def build_ics(days, now):
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//FinanceRadar//This Week//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:FinanceRadar · This Week",
             "X-WR-TIMEZONE:Asia/Kolkata"]

    def add(ds, summary, time=None, desc=""):
        uid = hashlib.sha1(f"{ds}|{summary}".encode("utf-8")).hexdigest()[:20]
        lines.extend(["BEGIN:VEVENT", f"UID:{uid}@financeradar", f"DTSTAMP:{stamp}"])
        d = date.fromisoformat(ds)
        if time:
            hh, mm = (int(x) for x in time.split(":"))
            start = datetime(d.year, d.month, d.day, hh, mm, tzinfo=IST).astimezone(timezone.utc)
            lines.append("DTSTART:" + start.strftime("%Y%m%dT%H%M%SZ"))
            lines.append("DTEND:" + (start + timedelta(minutes=30)).strftime("%Y%m%dT%H%M%SZ"))
        else:
            lines.append("DTSTART;VALUE=DATE:" + d.strftime("%Y%m%d"))
            lines.append("DTEND;VALUE=DATE:" + (d + timedelta(days=1)).strftime("%Y%m%d"))
        lines.append("SUMMARY:" + _ics_escape(summary))
        if desc:
            lines.append("DESCRIPTION:" + _ics_escape(desc))
        lines.append("TRANSP:TRANSPARENT")
        lines.append("END:VEVENT")

    for day in days:
        for e in day["events"]:
            desc = " · ".join(x for x in (e.get("source", ""), "date expected" if e.get("expected") else "") if x)
            add(day["date"], e["name"], e.get("time"), desc)
        if day["results"]:
            add(day["date"], "Results: " + ", ".join(day["results"]),
                desc="Nifty 200 companies' board meetings for results (NSE). Companies can move their dates.")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_ics_fold(l) for l in lines) + "\r\n"


def build_calendar(now=None, fetch=True, logger=None):
    """Write static/calendar.json + static/calendar.ics. Never raises."""
    try:
        now = (now or datetime.now(IST)).astimezone(IST)
        start = now.date() - timedelta(days=1)   # browsers a little behind IST still see "today"
        end = now.date() + timedelta(days=WINDOW_DAYS)
        index = load_index(now, fetch, logger)
        holidays = load_holidays(now, fetch, logger)
        results = load_results(index, now, fetch, logger)
        events = (load_macro_events() + forex_reserve_events(start, end) + expiry_events(start, end, holidays)
                  + results_deadline_events(start, end) + holiday_events(holidays, start, end))
        days = build_days(events, results, index, start, end)
        _write_json(OUT_JSON, {"generated": now.isoformat(timespec="seconds"), "days": days}, compact=True)
        _atomic_write(OUT_ICS, build_ics(days, now))
        _log(logger, f"This Week calendar: {len(days)} days, "
                     f"{sum(len(d['events']) for d in days)} events, {sum(len(d['results']) for d in days)} results")
        return days
    except Exception as e:  # the homepage must never depend on this
        _log(logger, f"calendar build failed: {e}", warn=True)
        return None


if __name__ == "__main__":
    build_calendar()
