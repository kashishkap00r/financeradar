"""Indian regulators and ministries without RSS, read from their own listing pages.

Each source is `official:<key>` in feeds.json (category News, source_tier official),
dispatched by aggregator.py to fetch_official(). A source = a fetch function that
returns raw rows (title, date, link) + an optional title filter that keeps the
signal (policy changes, orders, approvals) and drops the noise (tenders,
recruitment, corrigenda, event notices). Every row becomes the same article dict
the RSS path produces, so these items flow into the News tab's Official Channels
desk and the homepage's From the Source list like RBI and SEBI do.

Rules shared by all sources: verified TLS only, a browser User-Agent, a handful of
listing requests per source per run, and a [FAIL] line instead of an exception.
"""

import base64
import html
import json
import os
import re
import ssl
import subprocess
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from articles import IST_TZ

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
TIMEOUT = 25
MAX_AGE_DAYS = 30
SSL_CONTEXT = ssl.create_default_context()


def http_get(url, accept="text/html", headers=None, data=None, timeout=TIMEOUT):
    h = {"User-Agent": UA, "Accept": accept, "Accept-Language": "en-US,en;q=0.9"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def clean_text(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def encode_url(url):
    """Percent-encode spaces etc. in a link's path, leaving the rest alone."""
    url = html.unescape((url or "").strip())
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(parts._replace(path=urllib.parse.quote(parts.path, safe="/%:@!$&'()*+,;=")))


def to_article(feed_config, title, link, dt, description=""):
    return {
        "title": title,
        "link": link,
        "date": dt,
        "description": description,
        "source": feed_config["name"],
        "source_url": feed_config.get("url", ""),
        "category": feed_config.get("category", "News"),
        "region": feed_config.get("region", "Indian"),
        "publisher": feed_config.get("publisher", ""),
        "source_tier": feed_config.get("source_tier", "official"),
        "feed_id": feed_config["id"],
    }


# key -> (fetch_rows(feed_config) -> [(title, link, datetime, description)], keep(title) -> bool)
SOURCES = {}


def source(key, keep=None):
    def wrap(fn):
        SOURCES[key] = (fn, keep or (lambda title: True))
        return fn
    return wrap


def fetch_official(feed_config, now=None):
    name = feed_config["name"]
    key = feed_config.get("feed", "").split(":", 1)[-1]
    if key not in SOURCES:
        print(f"  [FAIL] {name}: unknown official source '{key}'")
        return []
    fetch_rows, keep = SOURCES[key]
    now = now or datetime.now(IST_TZ)
    cutoff = now - timedelta(days=feed_config.get("max_age_days", MAX_AGE_DAYS))
    try:
        rows = fetch_rows(feed_config)
    except Exception as e:
        print(f"  [FAIL] {name}: {str(e)[:70]}")
        return []
    out, seen = [], set()
    for title, link, dt, desc in rows:
        if not title or not link or link in seen or (dt and dt < cutoff) or not keep(title):
            continue
        seen.add(link)
        out.append(to_article(feed_config, title, link, dt, desc))
    print(f"  [OK] {name}: {len(out)} articles (official)")
    return out


def _ist(dt):
    return dt.replace(tzinfo=IST_TZ)


# ------------------------------------------------------------------ DGTR ----
# Directorate General of Trade Remedies: anti-dumping / countervailing / safeguard
# cases. The homepage's "What's New" box has one tab per document type, newest 5
# each; we read Initiations (block_5) and Preliminary/Final Findings (block_7).
# Oral hearings, questionnaire extensions and PUC/PCN notices are procedure.
DGTR_HOME = "https://www.dgtr.gov.in/en"
_DGTR_ROW = re.compile(
    r'\s*<span>\s*(\d{2} \w{3} \d{4})\s*</span>\s*<span>\s*<a href="([^"]+)"[^>]*>(.*?)</a>(.*?)<div class="file-details">',
    re.S)
_DGTR_PRODUCT = re.compile(
    r"imports? of\s+[\"“'‘]?(.+?)[\"”'’]?\s+(?:originating|from|exported|into)\b", re.I)
_DGTR_FROM = re.compile(r"(?:originating in(?: or exported from)?|exported from)\s+(.+?)(?:\s*[-–(]|\.?$)", re.I)
_DGTR_KEEP = re.compile(r"final finding|preliminary finding|initiation|termination|suo[- ]moto|sunset|anti[- ]circumvention", re.I)
_DGTR_DROP = re.compile(r"extension|timeline|\bPUC\b|\bPCN\b|questionnaire|oral hearing|corrigendum|reschedul|disclosure", re.I)


def parse_dgtr(page):
    rows = []
    for block in ("block_5", "block_7"):
        i = page.find("view-display-id-" + block)
        if i < 0:
            continue
        j = page.find("view-display-id-block_", i + 30)
        for chunk in page[i:j if j > 0 else None].split('<div class="notifi_list_inner">')[1:]:
            m = _DGTR_ROW.match(chunk)
            if not m:
                continue
            day, href, case, doc = m.groups()
            case, doc = clean_text(case), clean_text(doc)
            doc = re.sub(r"^SSR[_\s-]*", "Sunset review ", doc)  # "SSR_Final Findings"
            doc = doc[:1].upper() + doc[1:].lower() if doc.isupper() else doc
            if not _DGTR_KEEP.search(doc + " " + case) or _DGTR_DROP.search(doc):
                continue
            product = _DGTR_PRODUCT.search(case)
            origin = _DGTR_FROM.search(case)
            if product:
                title = f"{doc}: {product.group(1).strip(' .,')}"
                if origin:
                    title += f" from {origin.group(1).strip(' .,')}"
            else:
                title = f"{doc}: {case}"
            link = urllib.parse.urljoin(DGTR_HOME, html.unescape(href))
            rows.append((title, link, _ist(datetime.strptime(day, "%d %b %Y")), case))
    return rows


@source("dgtr")
def dgtr_rows(feed_config):
    return parse_dgtr(http_get(DGTR_HOME))


# ------------------------------------------------------------------ CBIC ----
# Customs notifications that change duties: Tariff, Anti Dumping Duty, CVD,
# Safeguards (Non Tariff is mostly tariff-value fixings and port notices). The
# site's own JSON API; its servers leave out Sectigo's OV R36 intermediate, which
# is shipped in certs/ so verification stays on. The `language: en` header is
# required (HTTP 500 without it).
CBIC_API = "https://taxinformation.cbic.gov.in/api/cbic-notification-msts"
CBIC_CATEGORIES = ("Tariff", "Anti Dumping Duty", "CVD", "Safeguards")
_CBIC_CERT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certs", "sectigo-public-server-auth-ca-ov-r36.pem")
_CBIC_DROP = re.compile(r"^corrigendum|^seeks to rescind", re.I)


def _cbic_context():
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(cafile=_CBIC_CERT)
    return ctx


def parse_cbic(items):
    rows = []
    for it in items or []:
        no = (it.get("notificationNo") or "").strip()
        name = clean_text(it.get("notificationName") or "")
        if not name or no.lower() == "corrigendum" or _CBIC_DROP.search(name):
            continue
        try:
            day = datetime.strptime((it.get("notificationDt") or "")[:10], "%Y-%m-%d")
        except ValueError:
            continue
        title = re.sub(r"^seeks to\s+", "", name, flags=re.I).rstrip(" .")
        title = title[:1].upper() + title[1:]
        link = f"https://taxinformation.cbic.gov.in/view-pdf/{it.get('id')}/ENG/Notifications"
        rows.append((title, link, _ist(day), f"Customs notification {no}".strip()))
    return rows


@source("cbic-customs")
def cbic_rows(feed_config):
    now = datetime.now(IST_TZ)
    years = [now.year] + ([now.year - 1] if now.month == 1 else [])
    ctx, rows = _cbic_context(), []
    for year in years:
        for cat in CBIC_CATEGORIES:
            url = (f"{CBIC_API}/fetchNotificationByYearAndCategory?page=0&size=20&year={year}"
                   f"&category={urllib.parse.quote(cat)}&taxId=1000002")
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", "language": "en"})
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
                rows.extend(parse_cbic(json.loads(resp.read().decode("utf-8", "replace"))))
    return rows


# ----------------------------------------------------------------- IRDAI ----
# Insurance regulator. Liferay pages, newest 20 per list, rows in the HTML.
# Titles are "Hindi / English": keep the English half.
IRDAI_LISTS = {
    "press-releases": r"grievance (redressal camps|resolution month)|workshop|joining of member|extension of last date|reminder on|felicitat|awareness (week|month)|\bhindi\b",
    "circulars": r"observance of|natural disaster|migration of .*returns|submission of (information|self-contained)",
    "consolidated-gazette-notified-regulations": None,
    "exposure-drafts": None,
}
_IRDAI_ROW = re.compile(r"table-col-shortDesc[^>]*>(.*?)</td>.*?table-col-lastUpdated[^>]*>\s*(\d{2}-\d{2}-\d{4})", re.S)


def _irdai_english(title):
    m = re.match(r"^[^A-Za-z]*?/\s*(.+)$", title)
    title = m.group(1) if m else title
    title = re.sub(r"^press release\s*[-–:]\s*", "", title, flags=re.I)
    return re.sub(r"\.pdf$", "", title, flags=re.I).strip()


def parse_irdai(page, list_key):
    drop = IRDAI_LISTS.get(list_key)
    rows = []
    for chunk in page.split("<tr")[1:]:
        m = _IRDAI_ROW.search(chunk)
        doc = re.search(r"document-detail\?documentId=(\d+)", chunk)
        if not m or not doc:
            continue
        title = _irdai_english(clean_text(m.group(1)))
        if not title:
            continue
        if list_key == "consolidated-gazette-notified-regulations":
            if not re.search(r"regulations?,?\s*20\d\d", title, re.I) or re.match(r"consolidated", title, re.I):
                continue
        elif list_key == "exposure-drafts":
            if not re.search(r"exposure draft|consultation paper", title, re.I):
                continue
        elif drop and re.search(drop, title, re.I):
            continue
        link = f"https://irdai.gov.in/document-detail?documentId={doc.group(1)}"
        rows.append((title, link, _ist(datetime.strptime(m.group(2), "%d-%m-%Y")), ""))
    return rows


@source("irdai")
def irdai_rows(feed_config):
    rows = []
    for key in IRDAI_LISTS:
        try:
            rows.extend(parse_irdai(http_get(f"https://irdai.gov.in/{key}"), key))
        except Exception as e:
            print(f"  [WARN] IRDAI {key}: {str(e)[:60]}")
    return rows


# ----------------------------------------------------------------- PFRDA ----
# Pension regulator (NPS). Liferay search portlet; 10 cards per list in the HTML.
PFRDA_LISTS = {
    "media/press-releases": None,
    "regulatory-framework/circulars/active-circulars": r"^(advisory|clarification)\b|frequency of submission|digital life certificate|\bDLC\b",
    "regulatory-framework/regulations": r"employees.?\s*service|\[last amended",
    "regulatory-framework/exposure-drafts": None,
}
_PFRDA_CARD = re.compile(
    r'<div class="basic-card">\s*<a href="([^"]+)"[^>]*>\s*<h2 class="basic-title">(.*?)</h2>(.*?)</a>', re.S)


def parse_pfrda(page, list_key):
    drop = PFRDA_LISTS.get(list_key)
    rows = []
    for href, title, rest in _PFRDA_CARD.findall(page):
        title = re.sub(r"^press release\s*[-–:]\s*", "", clean_text(title), flags=re.I)
        day = re.search(r"Issue Date:</strong>\s*(\d{2}-\d{2}-\d{4})", rest)
        if not title or not day:
            continue
        if list_key.endswith("exposure-drafts"):
            if not re.search(r"exposure draft|seeking public comments", title, re.I) or re.match(r"response to", title, re.I):
                continue
        elif drop and re.search(drop, title, re.I):
            continue
        link = urllib.parse.urljoin("https://www.pfrda.org.in/", html.unescape(href).split("?")[0])
        rows.append((title, link, _ist(datetime.strptime(day.group(1), "%d-%m-%Y")), ""))
    return rows


@source("pfrda")
def pfrda_rows(feed_config):
    rows, titles = [], set()
    for key in PFRDA_LISTS:
        try:
            for row in parse_pfrda(http_get(f"https://www.pfrda.org.in/{key}"), key):
                if row[0].lower() not in titles:  # the site sometimes lists one item twice under two slugs
                    titles.add(row[0].lower())
                    rows.append(row)
        except Exception as e:
            print(f"  [WARN] PFRDA {key}: {str(e)[:60]}")
    return rows


# ----------------------------------------------------------------- IFSCA ----
# GIFT City regulator. "What's New" lists every document with its type.
IFSCA_WHATS_NEW = "https://ifsca.gov.in/Home/NewSection"
IFSCA_TYPES = {"press release", "circular", "regulation", "public consultation", "notification", "guidelines"}
_IFSCA_ROW = re.compile(
    r'<td data-label="Date"><span style="display:none;">(\d{8})</span>\s*[\d/]+</td>\s*'
    r'<td[^>]*data-label="Type">(.*?)</td>\s*<td[^>]*data-label="Title">\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_IFSCA_DROP = re.compile(r"central tax|GST registration|\bhindi\b|message from|organised conference|world investor week|"
                         r"extension of timeline|certification (on|course)", re.I)


def parse_ifsca(page):
    rows, seen = [], set()
    for day, kind, href, title in _IFSCA_ROW.findall(page):
        kind, title = clean_text(kind).lower(), clean_text(title)
        if kind not in IFSCA_TYPES or not title or _IFSCA_DROP.search(title):
            continue
        key = re.sub(r"[^a-z0-9]+", " ", re.sub(r"^press release (on|regarding)\s+", "", title.lower())).strip()
        if key in seen:  # press releases often repeat the regulation they announce
            continue
        seen.add(key)
        link = urllib.parse.urljoin("https://ifsca.gov.in/", html.unescape(href).replace(" ", "%2B"))
        rows.append((title, link, _ist(datetime.strptime(day, "%Y%m%d")), kind.title()))
    return rows


@source("ifsca")
def ifsca_rows(feed_config):
    return parse_ifsca(http_get(IFSCA_WHATS_NEW))


# ------------------------------------------------------------------- CCI ----
# Competition Commission: press releases (merger approvals, penalties, orders).
CCI_PRESS = "https://www.cci.gov.in/media-gallery/press-release?draw=1&start=0&length=20"
_CCI_DROP = re.compile(r"\b(hosted|BRICS|conference|workshop|seminar|webinar|MoU|delegation|celebrat|annual day|visit)\b", re.I)


def parse_cci(data):
    rows = []
    for it in (data or {}).get("data") or []:
        title = clean_text(it.get("title"))
        try:
            day = datetime.strptime((it.get("order_date") or "").strip(), "%d/%m/%Y")
        except ValueError:
            continue
        if not title or _CCI_DROP.search(title):
            continue
        link = f"https://www.cci.gov.in/media-gallery/press-release/details/{it.get('id')}/0"
        rows.append((title, link, _ist(day), ""))
    return rows


@source("cci")
def cci_rows(feed_config):
    return parse_cci(json.loads(http_get(CCI_PRESS, accept="application/json",
                                         headers={"X-Requested-With": "XMLHttpRequest"})))


# ------------------------------------------------------------------- MCA ----
# Corporate Affairs: Companies Act / LLP Act notifications and general circulars.
# Akamai lets only curl's HTTP/2 through (urllib gets 403), so this one shells out
# to curl. Dates: notifications are uploaded days to weeks after their date, so
# the upload time is when they become news.
MCA_LIST = "https://www.mca.gov.in/bin/ebook/service/documentMetadata?docCategory={cat}&flag=initial&status=Current"
_MCA_DROP = re.compile(r"delegation|Establishment of (ROC|RD)s|section 454|Registrar of Companies|Regional Director", re.I)


def _curl(url, referer):
    out = subprocess.run(
        ["curl", "-sS", "--compressed", "--max-time", str(TIMEOUT), "-A", UA,
         "-H", "Accept: application/json, text/javascript, */*; q=0.01",
         "-H", "Accept-Language: en-US,en;q=0.9", "-H", f"Referer: {referer}", "-w", "\n%{http_code}", url],
        capture_output=True, timeout=TIMEOUT + 10)
    body, _, code = out.stdout.rpartition(b"\n")
    if code.strip() != b"200":
        raise RuntimeError(f"HTTP {code.decode(errors='replace').strip() or out.returncode}")
    return body.decode("cp1252", errors="replace")


def parse_mca(data, cat):
    rows = []
    for it in (data or {}).get("data") or []:
        title = clean_text(it.get("shortDescription")).rstrip(" .")
        if not title or (cat == "Notifications" and _MCA_DROP.search(title)):
            continue
        try:
            day = datetime.strptime((it.get("UploadDate") or "").strip(), "%m/%d/%Y %H:%M:%S")
        except ValueError:
            continue
        doc = base64.b64encode(str(it.get("link", "")).encode()).decode()
        link = f"https://www.mca.gov.in/bin/ebook/dms/getdocument?doc={urllib.parse.quote(doc)}&docCategory={cat}&type=open"
        rows.append((title, link, _ist(day), it.get("docGroup") or ""))
    return rows


@source("mca")
def mca_rows(feed_config):
    rows, titles = [], set()
    for cat, page in (("Notifications", "notifications"), ("Circulars", "circulars")):
        referer = f"https://www.mca.gov.in/content/mca/global/en/acts-rules/ebooks/{page}.html"
        for row in parse_mca(json.loads(_curl(MCA_LIST.format(cat=cat), referer)), cat):
            if row[0].lower() not in titles:
                titles.add(row[0].lower())
                rows.append(row)
    return rows


# ----------------------------------------------------------------- DPIIT ----
# FDI press notes (sector-by-sector changes to FDI policy; 1–4 a year) from the
# site's WordPress API. Titles say only "Press Note 3 (2026)", so the subject is
# read from the PDF's first page ("Subject: Review of FDI policy on ...").
DPIIT_API = "https://www.dpiit.gov.in/cms/wp-json"
_DPIIT_KEEP = re.compile(r"^\s*(Press\s*Notes?\s*\d*\s*\(\d{4}\)|Circulars\s*$)|Consolidated\s+FDI\s+Policy", re.I)


def _pdf_subject(url):
    try:
        data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}),
                                      timeout=TIMEOUT, context=SSL_CONTEXT).read()
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(data)
            f.flush()
            text = subprocess.run(["pdftotext", "-l", "1", f.name, "-"], capture_output=True, timeout=30).stdout.decode("utf-8", "replace")
    except Exception:
        return ""
    m = re.search(r"Subject\s*:\s*(.+?)(?:\n\s*\n|\.\s*\n)", text, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip().replace("FOi", "FDI") if m else ""


@source("dpiit")
def dpiit_rows(feed_config):
    cutoff = datetime.now(IST_TZ) - timedelta(days=feed_config.get("max_age_days", MAX_AGE_DAYS))
    data = json.loads(http_get(f"{DPIIT_API}/document/documents?document_category=orders-and-notices&limit=20&page=1",
                               accept="application/json"))
    rows = []
    for post in data.get("posts") or []:
        acf = post.get("acf_data") or {}
        title = clean_text(acf.get("title") or post.get("post_title"))
        try:
            day = _ist(datetime.strptime((acf.get("date") or "").strip(), "%d/%m/%Y"))
        except ValueError:
            continue
        if not _DPIIT_KEEP.search(title) or day < cutoff:
            continue
        files = [fid for block in acf.get("file") or [] for fid in block.get("file") or []]
        link, subject = "", ""
        for fid in files[-1:]:  # the newest file in a yearly bundle is the new press note
            meta = json.loads(http_get(f"{DPIIT_API}/post-page/post?id={fid}", accept="application/json"))
            pdf = ((meta.get("posts") or {}).get("acf_data") or {})
            link = (pdf.get("pdf") or {}).get("url") or (pdf.get("pdf_both") or {}).get("url") or ""
            subject = _pdf_subject(link) if link else ""
        if link:
            rows.append((f"{title}: {subject}" if subject else title, encode_url(link), day, "FDI policy"))
    return rows
