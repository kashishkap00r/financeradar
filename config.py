"""
Centralized configuration constants for FinanceRadar.

All magic numbers and tunable parameters in one place.
Import from here instead of hardcoding values across modules.
"""

from datetime import timedelta

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
AI_RANKER_ARTICLE_WINDOW_HOURS = 48   # look-back window for articles
AI_RANKER_EXTENDED_WINDOW_DAYS = 7    # look-back window for slower sources (reports/youtube/telegram)
AI_RANKER_MAX_ARTICLES = 200          # max articles sent to AI
AI_RANKER_TARGET_COUNT = 25           # ranked stories shown in AI sidebar
AI_RANKER_OPENROUTER_TIMEOUT = 60     # seconds
AI_RANKER_GEMINI_TIMEOUT = 120        # seconds
WSW_LOOKBACK_DAYS = 7                 # WSW 7-day rolling window
WSW_API_TIMEOUT = 90                  # seconds

# ── Failure thresholds ────────────────────────────────────────────────
FEED_FAILURE_ALERT_THRESHOLD = 0.3    # alert if >30% of feeds fail

# ── Missing story auditor ─────────────────────────────────────────────
AUDIT_LOOKBACK_DAYS = 7               # deep-audit lookback window
AUDIT_SLA_HOURS = 6                   # source story should appear within this SLA
AUDIT_MAX_ITEMS_PER_SOURCE = 30       # cap per source during audit comparisons
