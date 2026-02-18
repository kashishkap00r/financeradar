#!/usr/bin/env python3
"""
Content filters for FinanceRadar.
Extracted from aggregator.py for independent editing and testing.

Usage:
    from filters import should_filter_article
    python3 -c "from filters import should_filter_article; print(should_filter_article({'title':'Sensex surges 300 points','link':''}))"
"""
import re

# =============================================================================
# CONTENT FILTERS - Patterns to filter out irrelevant/routine content
# =============================================================================

# Title patterns to filter (case-insensitive regex)
FILTER_TITLE_PATTERNS = [
    # Market price movements (routine daily updates)
    r"sensex (closes|ends|opens|gains|loses|falls|rises|at)",
    r"nifty (closes|ends|opens|gains|loses|falls|rises|at)",
    r"sensex.{0,10}nifty.*(close|end|open|gain|lose|fall|rise)",
    r"market (closes|ends|opens) (at|flat|higher|lower)",
    r"gold.*(rate|price).*(today|january|february|march|april|may|june|july|august|september|october|november|december)",
    r"silver.*(rate|price).*(today|january|february|march|april|may|june|july|august|september|october|november|december)",
    r"crude oil price today",
    r"petrol.*(price|rate).*today",
    r"diesel.*(price|rate).*today",
    r"dollar.*rupee.*(today|rate)",
    r"rupee (opens|closes|ends) at",
    r"forex rate today",
    r"currency rate today",

    # RBI routine operations
    r"money market operations as on",
    r"auction of.*treasury bills",
    r"auction of.*government securities",
    r"auction of state government securities",
    r"weekly statistical supplement",
    r"lending and deposit rates of scheduled commercial banks",
    r"directions under section 35a",
    r"auction result",

    # Live tickers
    r"live updates.*sensex",
    r"live updates.*nifty",
    r"stock market live",
    r"market live updates",
    r"trading live",

    # IPO routine
    r"ipo.*(gmp|grey market|gray market)",
    r"ipo subscription.*(status|day \d|times|x subscribed|\dx)",

    # MF/SIP routine
    r"best.*(mutual fund|mf|sip)",
    r"top \d+.*(mutual fund|fund|sip)",
    r"sip.*(contribution|inflow|record)",
    r"mutual fund.*(buy|invest|best)",

    # Holidays
    r"bank.*(holiday|closed|shut)",
    r"market.*(holiday|closed|shut)",
    r"trading holiday",
    r"banks closed",

    # Roundups
    r"week ahead.*market",
    r"markets this week",
    r"monthly roundup",
    r"weekly roundup",
    r"week in review",

    # Crypto prices
    r"bitcoin (falls|rises|drops|surges|crashes|slips|at \$)",
    r"ethereum (falls|rises|drops|surges|crashes|slips|at \$)",
    r"crypto.*(price|market update|today)",
    r"cryptocurrency.*(price|market update|today)",

    # Stock tips
    r"stock tip",
    r"intraday tip",
    r"\bbuy or sell\b",
    r"multibagger",
    r"stocks to buy",

    # Quarterly results roundups (routine lists)
    r"q[1-4]\s*results?\s*today",
    r"q[1-4]\s*results?\s*live",
    r"q[1-4]\s*earnings?\s*today",
    r"q[1-4]\s*earnings?\s*live",
    r"results?\s*today\s*live",
    r"earnings?\s*today\s*live",

    # Stock recommendations / stock picks (MarketSmith etc.)
    r"stock\s+recommendations?",
    r"stock\s+picks?\s+for",

    # Stocks to watch (routine daily lists) — broad match
    r"stocks?\s+to\s+watch\b",
    r"shares?\s+to\s+watch\b",

    # Stocks/shares in focus — broad match
    r"stocks?\s+in\s+focus\b",
    r"shares?\s+in\s+focus\b",
    r"stocks?\s*in\s*news\s*today",

    # Daily routine listicles ("10 shares", "5 stocks for tomorrow", "full list here")
    r"\d+\s+(shares?|stocks?)\s+(in\s+focus|to\s+(buy|watch|sell))",
    r"\bfull\s+list\s+here\b",
    r"here.?s\s+the\s+list\b",

    # Political news (not economic policy analysis)
    r"\b(rally|rallies)\s+(against|for|in)\b",
    r"\b(congress|bjp|aap|tmc|shiv\s+sena|ncp)\s+(rally|protest|march|campaign)",
    r"\b(rahul\s+gandhi|modi\s+rally|kejriwal|mamata|yogi)\b",
    r"\belection\s+(result|poll|campaign|rally)",

    # Weather / temperature / climate (non-finance)
    r"\b(temperature|mercury|heat\s+wave|cold\s+wave|heatwave)\b.*\b(soar|rise|surge|drop|fall|record)",
    r"\bimd\s+(weather|update|forecast)",
    r"\bair\s+quality\b.*\b(poor|severe|moderate|good|aqi)\b",
    r"\bweather\s+(update|forecast|alert)\b",

    # Accidents / deaths / crime (non-finance)
    r"\b(dead|killed|injured|dies)\b.*\b(accident|crash|collapse|fire|derail)\b",
    r"\b(metro|bridge|building|wall)\s+(collapse|crash|accident)\b",

    # Sports (cricket, IPL, etc.)
    r"\b(cricket|cricketer|ipl|t20|test\s+match|odi)\b",

    # Market opening predictions
    r"(flat|flattish|positive|negative|cautious|muted|weak|strong|higher|lower)\s*opening\s*(seen|expected|likely)",
    r"opening\s*(seen|expected)\s*(for|on)\s*(sensex|nifty|market)",

    # Stock Market Today/Highlights (daily roundups)
    r"stock\s*market\s*today",
    r"stock\s*market\s*highlights",
    r"market\s*highlights.*(sensex|nifty)",

    # Sensex/Nifty with big movement verbs
    r"sensex\s*(surges?|zooms?|jumps?|soars?|rallies?|tanks?|plunges?|crashes?|tumbles?|slumps?|skyrockets?)",
    r"nifty\s*(surges?|zooms?|jumps?|soars?|rallies?|tanks?|plunges?|crashes?|tumbles?|slumps?|skyrockets?)",

    # Point/percentage movements
    r"(sensex|nifty).{0,30}(up|down|adds?|sheds?|gains?|loses?)\s*\d+\s*(pts|points?|%)",

    # Prediction articles
    r"(sensex|nifty)\s*prediction",
    r"what\s*to\s*expect.*stock\s*market",
    r"what\s*to\s*expect.*(sensex|nifty)",

    # Top gainers/losers
    r"top\s*gainers",
    r"top\s*losers",
    r"gainers.{0,20}losers",

    # Technical analysis jargon
    r"(support|resistance).{0,15}(support|resistance)?\s*levels?",

    # Closing/Opening Bell
    r"closing\s*bell",
    r"opening\s*bell",

    # "Sensex today" / "Nifty today" patterns
    r"(sensex|nifty)\s*today\s*:",
    r"(sensex|nifty)\s*\d+.{0,10}(sensex|nifty)\s*today",

    # Corporate actions — dividends, record dates, ex-dates, buybacks, splits
    r"dividend.*(declared|announced|record\s+date|ex.?date|payout|per\s+share|next\s+week)",
    r"(record\s+date|ex.?date).*(dividend|bonus|split|buyback)",
    r"(fixes?|fixed|sets?)\s+.{0,30}(record\s+date|ex.?date)",
    r"stocks?\s*(to\s+)?go\s+ex.?date",
    r"dividend\s+stocks?\s+today",
    r"(stock|share)\s+split.*(announced|record|ratio)",
    r"bonus\s+shares?\s*(announced|record|ratio|issue)",
    r"(share|stock)\s+buyback.*(announced|opens?|closes?|record)",
    r"board\s+meet(ing)?.*(dividend|buyback|split|bonus)",
    r"corporate\s+announcement.*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",

    # Brokerage calls & share price targets
    r"share\s+price\s+target",
    r"target\s+price.*(rs|Rs|\u20b9|\$|\d)",
    r"(brokerage|broker)s?\s*(raise|hike|cut|slash|maintain|upgrade|downgrade)",
    r"\bBUY\s+call\b",
    r"\bSELL\s+call\b",
    r"reasons?\s+to\s+(BUY|SELL)\b",
    r"(check|see)\s+target\s+price",
    r"\d+%\s+upside",

    # Quarterly results — roundups/schedules only
    r"Q[1-4]\s*FY\s*\d{2,4}\s*results?",
    r"Q[1-4]FY\s*\d{2,4}\s*results?",
    r"Q[1-4]\s*results?\s*FY\s*\d{2,4}",
    r"Q[1-4]\s*results?\s*next\s*week",
    r"Q[1-4]\s*results?\s*preview",
    r"shares?\s*(surge|jump|rise|drop|fall|slip|climb)\s+.{0,30}(Q[1-4]\s*results?|strong\s+results?|weak\s+results?)",

    # Personal finance clickbait
    r"(SIP|PPF|NPS|FD|fixed deposit)\s+vs\s+(SIP|PPF|NPS|FD|fixed deposit)",
    r"(best|top|highest)\s+.{0,15}(FD|fixed deposit)\s+(rate|interest)",
    r"(best|top|highest)\s+.{0,15}savings?\s+account\s+.{0,15}(rate|interest)",
    r"how\s+(much|to)\s+.{0,30}(corpus|retire|retirement|pension|wealth\s+creat)",
    r"(tax\s+saving|save\s+tax).*(tips?|schemes?|options?|ways?)",
    r"(gold|silver)\s+.{0,15}(city.?wise|rate|price).*(check|today)",
    r"how\s+pure\s+is\s+your\s+(gold|silver)",
    r"(buying|buy)\s+gold.*(sell|selling).*(india|profit|return)",

    # Government salary / pay commission noise
    r"\d+(th|st|nd|rd)\s+pay\s+commission",
    r"(DA|dearness\s+allowance)\s+(hike|increase|announcement|calculation)",
    r"(salary|arrears?).*(central\s+govt|government\s+employee)",

    # Penny stocks & celebrity net worth
    r"penny\s+stock",
    r"here.?s?\s+(his|her|their)\s+net\s+worth",
    r"(net\s+worth).*(richest|billionaire|millionaire)",
    r"who\s+is\s+.{0,40}(owner|richest|net\s+worth)",

    # Event promotions
    r"(investment\s+summit|business\s+summit)\s*\d{4}",
    r"ETNow\s*.{0,5}\s*(summit|event)",
    r"Global\s+Business\s+Summit\s+\d{4}",

    # Video tags in titles (ET Now pattern)
    r"\|\s*Video\s*$",
    r"\bWatch\s+Video\s*$",

    # Gold/silver price movements
    r"(gold|silver)\s+(price|rate)\s+(falls?|rises?|drops?|surges?|crashes?|slips?|jumps?)",
    r"(gold|silver)\s+at\s+(rs|Rs|\u20b9)",
]

# URL patterns to filter (case-insensitive, substring match)
FILTER_URL_PATTERNS = [
    "/pr-release/",
    "/brandhub/",
    "/press-release/",
    "prnewswire.com",
    "businesswire.com",
    "/cartoon",
    "/cartoons",
    "/video",
    "/videos",
    "/podcast",
    "/travel",
    "/sports",
    "/weather",
    "/review",
    "/reviews",
    "/infographic",
    "/fashion",
    "/entertainment",
    "downtoearth.org.in/food",
    "etnownews.com/technology",
    "etnownews.com/personal-finance",
    "/personal-finance/",
    "/lifestyle",
    "/multimedia/audio/",
]

# Compile regex patterns for performance
COMPILED_TITLE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in FILTER_TITLE_PATTERNS]


def should_filter_article(article):
    """Check if an article should be filtered out."""
    title = article.get("title", "").lower()
    link = article.get("link", "").lower()

    # Check URL patterns
    for pattern in FILTER_URL_PATTERNS:
        if pattern.lower() in link:
            return True

    # Check title patterns
    for pattern in COMPILED_TITLE_PATTERNS:
        if pattern.search(title):
            return True

    return False
