"""
Centralized configuration constants for FinanceRadar.

All magic numbers and tunable parameters in one place.
Import from here instead of hardcoding values across modules.
"""

import ssl
from datetime import timedelta

# ── Shared SSL contexts ──────────────────────────────────────────────
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT_NOVERIFY = ssl.create_default_context()
SSL_CONTEXT_NOVERIFY.check_hostname = False
SSL_CONTEXT_NOVERIFY.verify_mode = ssl.CERT_NONE

# ── Default User-Agent ───────────────────────────────────────────────
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ── Feed fetching ─────────────────────────────────────────────────────
FEED_FETCH_TIMEOUT = 15          # seconds, per-feed HTTP timeout
FEED_CURL_TIMEOUT = 20           # seconds, curl fallback timeout
FEED_THREAD_WORKERS = 10         # concurrent feed fetches
MAX_ARTICLES_PER_FEED = 50       # cap per feed in final output
RSS_PROXY_ENV_VAR = "RSS_PROXY_URL"   # optional Cloudflare RSS proxy base URL
RSS_PROXY_TIMEOUT = 20                # seconds for proxy fallback request
RSS_PROXY_ALLOWED_CATEGORIES = ("News", "Reports", "Twitter")
RSS_PROXY_RETRY_HTTP_CODES = (403, 429)

# ── Article freshness ─────────────────────────────────────────────────
NEWS_FRESHNESS_DAYS = 5          # News tab: discard articles older than this
TWITTER_FRESHNESS_DAYS = 5       # Twitter tab: discard tweets older than this
TWITTER_HIGH_SIGNAL_WINDOW_HOURS = 24  # Twitter high-signal window
TWITTER_HIGH_SIGNAL_TARGET = 25        # Twitter high-signal lane size
REPORTS_FRESHNESS_DAYS = 30      # Reports tab: discard reports older than this
VIDEO_FRESHNESS_DAYS = 10        # YouTube tab (used by CLAUDE.md, not code)
TWITTER_RESOLVE_WORKERS = 8      # concurrent Google->X resolve workers

# ── Twitter/X ingestion ───────────────────────────────────────────────
TWITTER_GOOGLE_MAX_ITEMS_PER_HANDLE = 30  # max fetched per handle in Google mode
TWITTER_CACHE_FILE = "static/twitter_clean_cache.json"  # clean fallback snapshot
RSSHUB_CACHE_FILE = "static/rsshub_twitter_cache.json"  # RSSHub local fetch cache
RSSHUB_CACHE_MAX_AGE_HOURS = 24  # treat RSSHub cache as stale after this (needs headroom for overnight/laptop-off gaps)
RSSHUB_BASE_URL = "http://localhost:1200"  # local RSSHub instance

# ── Companies (Tipsheet integration) ──────────────────────────────────
COMPANIES_SEARCH_INDEX_URL = "https://tipsheet.markets/search-index.json"  # source feed
COMPANIES_SITE_BASE = "https://tipsheet.markets"  # prepend to relative item URLs
COMPANIES_CACHE_FILE = "static/companies_cache.json"  # cache fallback (CI safety)
COMPANIES_FETCH_TIMEOUT = 20     # seconds, HTTP timeout for search-index fetch
COMPANIES_FRESHNESS_DAYS = 30    # discard filings older than this
COMPANIES_MAX_ITEMS = 500        # cap total items kept in the tab payload

# ── Report scrapers ───────────────────────────────────────────────────
SCRAPER_MAX_ARTICLES = 30        # max articles per scraper invocation
SCRAPER_FRESHNESS_CUTOFF = timedelta(days=30)
SCRAPER_FETCH_TIMEOUT = 15       # seconds, per-scraper HTTP timeout
SCRAPER_RETRY_ATTEMPTS = 2       # number of retries for transient failures
SCRAPER_RETRY_BACKOFF = 1.5      # seconds between retries
SCRAPER_TIMEOUT_OVERRIDES = {    # source-specific timeout overrides by feed id
    "baroda-etrade-str": 8,
    "baroda-etrade-sor": 8,
}
SCRAPER_RETRY_OVERRIDES = {      # source-specific retry overrides by feed id
    "baroda-etrade-str": 0,
    "baroda-etrade-sor": 0,
}

# ── Telegram fetcher ──────────────────────────────────────────────────
TELEGRAM_MAX_PAGES = 15          # max pagination requests per channel
TELEGRAM_MAX_AGE_DAYS = 5        # default message age cutoff
TELEGRAM_FETCH_TIMEOUT = 30      # seconds

# ── AI rankers ────────────────────────────────────────────────────────
AI_RANKER_ARTICLE_WINDOW_HOURS = 48   # look-back window for news articles
AI_RANKER_TWITTER_WINDOW_HOURS = 96   # look-back window for tweets (slower-moving than news)
AI_RANKER_EXTENDED_WINDOW_DAYS = 7    # look-back window for slower sources (reports/youtube/telegram)
AI_RANKER_MAX_ARTICLES = 200          # max articles sent to AI
AI_RANKER_TARGET_COUNT = 25           # ranked stories shown in AI sidebar
AI_RANKER_OPENROUTER_TIMEOUT = 60     # seconds
AI_RANKER_GEMINI_TIMEOUT = 120        # seconds
AI_RANKER_MAX_CLUSTERS = 7            # max story clusters per ranking run
AI_RANKER_MIN_CLUSTER_SIZE = 2        # minimum articles to form a cluster
AI_RANKER_CLUSTER_TIMEOUT = 60        # seconds for clustering API call
WSW_LOOKBACK_DAYS = 7                 # WSW 7-day rolling window
WSW_API_TIMEOUT = 90                  # seconds

# ── Failure thresholds ────────────────────────────────────────────────
FEED_FAILURE_ALERT_THRESHOLD = 0.3    # alert if >30% of feeds fail

# ── Missing story auditor ─────────────────────────────────────────────
AUDIT_LOOKBACK_DAYS = 7               # deep-audit lookback window
AUDIT_SLA_HOURS = 6                   # source story should appear within this SLA
AUDIT_MAX_ITEMS_PER_SOURCE = 30       # cap per source during audit comparisons
