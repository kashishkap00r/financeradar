#!/usr/bin/env python3
"""
RSS News Aggregator
Fetches news from multiple RSS feeds and generates a static HTML website.
"""

import json
from datetime import datetime, timedelta, timezone
from html import escape
import os


def sanitize_url(url):
    """Return url only if it uses http(s) scheme; empty string otherwise."""
    if not url:
        return ""
    trimmed = url.strip().lower()
    if trimmed.startswith("http://") or trimmed.startswith("https://"):
        return url
    return ""
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# Get script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "index.html")
REPORTS_CACHE_FILE = os.path.join(SCRIPT_DIR, "static", "reports_cache.json")

# Filters extracted to filters.py for independent editing and testing
from filters import should_filter_article, should_filter_video

# Article processing utilities
from articles import (group_similar_articles, clean_html, get_sort_timestamp,
                      to_local_datetime, export_articles_json, clean_twitter_title,
                      IST_TZ)

# Feed loading and fetching
from feeds import load_feeds, fetch_feed, fetch_careratings, fetch_the_ken, INVIDIOUS_INSTANCES

# Report scrapers
from reports_fetcher import get_report_fetcher
from config import (FEED_THREAD_WORKERS, MAX_ARTICLES_PER_FEED,
                    NEWS_FRESHNESS_DAYS, TWITTER_FRESHNESS_DAYS,
                    REPORTS_FRESHNESS_DAYS, FEED_FAILURE_ALERT_THRESHOLD)
from log_utils import FeedLogger


def generate_html(article_groups, video_articles=None, twitter_articles=None, report_articles=None):
    """Generate the static HTML website."""

    # Sort groups by date of primary article (newest first)
    def get_group_timestamp(group):
        return get_sort_timestamp(group["primary"])

    groups_with_date = [g for g in article_groups if g["primary"]["date"]]
    groups_without_date = [g for g in article_groups if not g["primary"]["date"]]

    groups_with_date.sort(key=get_group_timestamp, reverse=True)
    all_sorted_groups = groups_with_date + groups_without_date

    # Apply per-feed cap (max 50 articles per feed)
    MAX_PER_FEED = MAX_ARTICLES_PER_FEED
    source_counts = {}
    capped_groups = []

    for group in all_sorted_groups:
        source = group["primary"]["source"]
        count = source_counts.get(source, 0)
        if count < MAX_PER_FEED:
            capped_groups.append(group)
            source_counts[source] = count + 1

    # Re-sort after capping
    capped_groups.sort(key=get_group_timestamp, reverse=True)
    sorted_groups = capped_groups

    # Extract flat list of primary articles for counting
    sorted_articles = [g["primary"] for g in sorted_groups]

    # Group by date
    now_ist = datetime.now(IST_TZ)
    today = now_ist.date()
    yesterday = today - timedelta(days=1)
    today_iso = today.isoformat()

    # Get unique sources for filter dropdown
    sources = sorted(set(a['source'] for a in sorted_articles))

    # Get unique publishers for multi-select dropdown
    all_publishers = sorted(set(a['publisher'] for a in sorted_articles if a.get('publisher')))

    # Publisher presets
    publisher_presets = {
        "India Desk": ["ET", "The Hindu", "BusinessLine", "Business Standard", "Mint", "ThePrint", "Firstpost", "Indian Express", "The Core", "Financial Express"],
        "World Desk": ["BBC", "CNBC", "The Economist", "The Guardian", "Financial Times", "Reuters", "Bloomberg", "Rest of World", "Techmeme"],
        "Indie Voices": ["Finshots", "Filter Coffee", "SOIC", "The Ken", "The Morning Context", "India Dispatch", "Carbon Brief", "Our World in Data", "Data For India", "Down To Earth", "The LEAP Blog", "By the Numbers", "Musings on Markets", "A Wealth of Common Sense", "BS Number Wise", "AlphaEcon", "Market Bites", "Capital Quill", "This Week In Data", "Noah Smith", "Ideas For India", "The India Forum", "Neel Chhabra", "Ember"],
        "Official Channels": ["RBI", "SEBI", "ECB", "ADB", "FRED"]
    }

    # Twitter publisher presets
    twitter_presets = {
        "Money Managers": ["Deepak Shenoy", "Samit Vartak", "ContrariianEPS", "Unseen Value", "Murali Srinivasan", "Dhirendra Kumar"],
        "Stock Pickers": ["SOIC", "SOIC Research", "Finstor", "Yatin Mota", "TarH", "Aditya Kondawar", "Abhy Murarka", "Prashant Nair", "Shashank Udupa", "Ritu Singh", "Equity Value", "Beat The Street", "Equity Insights", "Mohit Ish", "Kobeissi Letter", "Pranay Kotas"],
        "Newsroom": ["Menaka Doshi", "CNBC-TV18", "ET Markets", "Nigel D'Souza", "Andy Mukherjee", "Ira Dugal", "Javier Blas", "FT Energy"],
        "Macro & Policy": ["Michael Pettis", "Sanjeev Sanyal", "Ila Patnaik", "Ideas For India", "Shruti Rajagopalan", "CareEdge"],
        "Data & Climate": ["Down To Earth", "Carbon Brief", "Ember Energy", "Our World in Data", "Data For India", "IndiaSpend", "India Data Hub"],
    }
    twitter_presets_json = json.dumps(twitter_presets)

    # JSON for injection into script
    all_publishers_json = json.dumps(all_publishers)
    publisher_presets_json = json.dumps(publisher_presets)

    # Load Telegram reports if available
    telegram_reports_file = os.path.join(SCRIPT_DIR, "static", "telegram_reports.json")
    try:
        with open(telegram_reports_file, "r", encoding="utf-8") as f:
            telegram_data = json.load(f)
        telegram_reports_json = json.dumps(telegram_data.get("reports", []))
        telegram_generated_at = telegram_data.get("generated_at", "")
        telegram_warnings = telegram_data.get("warnings", [])
    except (IOError, json.JSONDecodeError):
        telegram_data = {}
        telegram_reports_json = "[]"
        telegram_generated_at = ""
        telegram_warnings = []

    # Prepare video data
    if video_articles is None:
        video_articles = []
    video_articles_json = json.dumps([{
        "title": v["title"],
        "link": v["link"],
        "date": v["date"].isoformat() if v.get("date") else None,
        "source": v.get("source", ""),
        "publisher": v.get("publisher", ""),
        "video_id": v.get("video_id", ""),
        "thumbnail": v.get("thumbnail", ""),
    } for v in video_articles])
    video_count = len(video_articles)
    video_channel_count = len(set(v.get("publisher", "") for v in video_articles if v.get("publisher")))
    youtube_publishers = sorted(set(v.get("publisher", v.get("source", "")) for v in video_articles if v.get("publisher") or v.get("source")))
    youtube_publishers_json = json.dumps(youtube_publishers)

    # Prepare twitter data
    if twitter_articles is None:
        twitter_articles = []
    twitter_articles_json = json.dumps([{
        "title": clean_twitter_title(t["title"]),
        "link": t["link"],
        "date": t["date"].isoformat() if t.get("date") else None,
        "source": t.get("source", ""),
        "publisher": t.get("publisher", ""),
        "image": t.get("image", ""),
    } for t in twitter_articles])
    twitter_count = len(twitter_articles)
    twitter_publishers = sorted(set(t.get("publisher", t.get("source", "")) for t in twitter_articles if t.get("publisher") or t.get("source")))
    twitter_publishers_json = json.dumps(twitter_publishers)

    # Prepare research reports data
    if report_articles is None:
        report_articles = []
    research_reports_json = json.dumps([{
        "title": r["title"],
        "link": r["link"],
        "date": r["date"].isoformat() if r.get("date") else None,
        "source": r.get("source", ""),
        "publisher": r.get("publisher", ""),
        "description": r.get("description", ""),
        "region": r.get("region", "Indian"),
    } for r in report_articles])
    research_count = len(report_articles)
    research_publishers = sorted(set(r.get("publisher", "") for r in report_articles if r.get("publisher")))
    research_publishers_json = json.dumps(research_publishers)

    # Count in-focus articles (covered by multiple sources)
    in_focus_count = sum(1 for g in sorted_groups if g["related_sources"])

    # Telegram reports stats for tabs
    telegram_reports_list = telegram_data.get("reports", [])
    report_count = len(telegram_reports_list)
    channel_count = len(set(r.get("channel", "") for r in telegram_reports_list))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <script>try{{document.documentElement.setAttribute('data-theme',localStorage.getItem('theme')||'light')}}catch(e){{}}</script>
    <script>try{{if(localStorage.getItem('financeradar_filters_collapsed')!=='false')document.documentElement.classList.add('filters-collapsed')}}catch(e){{}}</script>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FinanceRadar</title>
    <link rel="icon" href="static/favicon.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700;900&family=Source+Sans+Pro:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
"""
    # Read CSS from external file
    css_path = os.path.join(SCRIPT_DIR, "templates", "style.css")
    with open(css_path, "r", encoding="utf-8") as f:
        css_content = f.read()
    html += css_content
    html += f"""    </style>
    <script>
    (function(){{
      if (document.fonts && document.fonts.ready) {{
        document.fonts.ready.then(function(){{ document.body.style.opacity='1'; }});
      }} else {{
        window.addEventListener('load', function(){{ document.body.style.opacity='1'; }});
      }}
      setTimeout(function(){{ document.body.style.opacity='1'; }}, 500);
    }})();
    </script>
</head>
<body>
    <div class="top-bar">
        <div class="top-bar-inner">
            <div class="brand">
                <a href="/" class="logo" style="text-decoration:none;color:inherit;cursor:pointer;">FinanceRadar</a>
            </div>
            <div class="search-box">
                <span class="search-icon">&#128269;</span>
                <input type="text" id="search" placeholder="Search articles..." oninput="onSearchInput()">
            </div>
            <button id="ai-toggle" class="ai-toggle" type="button" aria-label="Top AI stories" data-tooltip="Top AI stories" onclick="openAiSidebar()">
                <span style="font-size: 16px;">🤖</span>
            </button>
            <button id="wsw-toggle" class="wsw-toggle" type="button"
                    aria-label="Who Said What story ideas"
                    data-tooltip="Who Said What"
                    onclick="openWswSidebar()">
                <span style="font-size: 16px;">🗣</span>
            </button>
            <button id="bookmarks-toggle" class="bookmarks-toggle" type="button" aria-label="Your bookmarks" data-tooltip="Your bookmarks">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>
                </svg>
                <span id="bookmark-count" class="bookmark-count hidden">0</span>
            </button>
            <button id="in-focus-toggle" class="in-focus-toggle" type="button" aria-label="Stories in focus" data-tooltip="Stories in focus" onclick="toggleInFocus()">
                <span class="pulse-dot"></span>
                <span class="in-focus-count">{in_focus_count}</span>
            </button>
            <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Toggle theme" data-tooltip="Toggle theme">
                <svg class="icon-moon feather feather-moon" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
                </svg>
                <svg class="icon-sun feather feather-sun" viewBox="0 0 24 24" aria-hidden="true">
                    <circle cx="12" cy="12" r="5"></circle>
                    <line x1="12" y1="1" x2="12" y2="3"></line>
                    <line x1="12" y1="21" x2="12" y2="23"></line>
                    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
                    <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
                    <line x1="1" y1="12" x2="3" y2="12"></line>
                    <line x1="21" y1="12" x2="23" y2="12"></line>
                    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
                    <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
                </svg>
            </button>
        </div>
    </div>

    <!-- Bookmarks Sidebar -->
    <div id="sidebar-overlay" class="sidebar-overlay">
        <div class="bookmarks-sidebar">
            <div class="sidebar-header">
                <div class="sidebar-title">
                    <svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" fill="none" stroke-width="2">
                        <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>
                    </svg>
                    Bookmarks
                </div>
                <button class="sidebar-close" onclick="closeSidebar()" aria-label="Close sidebar">
                    <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                </button>
            </div>
            <div id="sidebar-content" class="sidebar-content">
                <div class="sidebar-empty">No bookmarks yet.<br>Click the bookmark icon on articles to save them.</div>
            </div>
            <div class="sidebar-footer">
                <button class="sidebar-btn copy-btn" onclick="copyBookmarks()">
                    <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" fill="none" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                    </svg>
                    <span>Copy All</span>
                </button>
                <button class="sidebar-btn danger" onclick="clearAllBookmarks()">Clear All</button>
            </div>
        </div>
    </div>

    <!-- AI Rankings Sidebar -->
    <div id="ai-sidebar-overlay" class="sidebar-overlay">
        <div class="ai-sidebar">
            <div class="sidebar-header">
                <div class="sidebar-title"><span style="font-size: 18px;">🤖</span> AI Picks</div>
                <button class="sidebar-close" onclick="closeAiSidebar()" aria-label="Close sidebar">
                    <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                </button>
            </div>
            <div class="ai-provider-select">
                <label for="ai-provider">Model:</label>
                <select id="ai-provider" onchange="switchAiProvider()">
                    <option value="">Loading...</option>
                </select>
            </div>
            <div id="ai-rankings-content" class="sidebar-content">
                <div class="sidebar-empty">Loading AI rankings...</div>
            </div>
            <div class="sidebar-footer">
                <span id="ai-updated" class="ai-updated-time">Updated: --</span>
            </div>
        </div>
    </div>

    <!-- WSW Sidebar -->
    <div id="wsw-sidebar-overlay" class="sidebar-overlay">
      <div class="ai-sidebar">
        <div class="sidebar-header">
          <div class="sidebar-title"><span style="font-size:18px;">🗣</span> Who Said What</div>
          <button class="sidebar-close" onclick="closeWswSidebar()" aria-label="Close">
            <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </div>
        <div class="ai-provider-select">
          <label for="wsw-provider">Model:</label>
          <select id="wsw-provider" onchange="switchWswProvider()">
            <option value="">Loading...</option>
          </select>
        </div>
        <div id="wsw-content" class="sidebar-content">
          <div class="sidebar-empty">Loading WSW ideas...</div>
        </div>
        <div class="sidebar-footer">
          <span id="wsw-updated" class="ai-updated-time">Updated: --</span>
        </div>
      </div>
    </div>

    <div class="container">
        <div class="content-tabs">
            <button class="content-tab active" data-tab="news" onclick="switchTab('news')">
                News <span class="tab-count">{len(sorted_articles)}</span>
            </button>
            <button class="content-tab" data-tab="reports" onclick="switchTab('reports')">
                Telegram <span class="tab-count">{report_count}</span>
            </button>
            <button class="content-tab" data-tab="research" onclick="switchTab('research')">
                Reports <span class="tab-count">{research_count}</span>
            </button>
            <button class="content-tab" data-tab="youtube" onclick="switchTab('youtube')">
                YouTube <span class="tab-count">{video_count}</span>
            </button>
            <button class="content-tab" data-tab="twitter" onclick="switchTab('twitter')">
                Twitter <span class="tab-count">{twitter_count}</span>
            </button>
        </div>

        <div id="tab-news" class="tab-content active">
        <div class="filter-card">
            <div class="stats-bar">
                <div class="stats">
                    <span><strong>{len(sorted_articles)}</strong> articles</span>
                    <span><strong>{len(all_publishers)}</strong> publishers</span>
                </div>
                <div style="display:flex;align-items:center;">
                    <span class="update-time" id="update-time" data-time="{now_ist.isoformat()}">Updated {now_ist.strftime("%b %d, %I:%M %p")} IST</span>
                    <script>
                    (function(){{
                        var el=document.getElementById('update-time'),t=el&&el.getAttribute('data-time');
                        if(!t)return;
                        var d=Math.floor((new Date()-new Date(t))/60000);
                        el.textContent='Updated '+(d<1?'just now':d<60?d+' min ago':d<1440?Math.floor(d/60)+' hr ago':Math.floor(d/1440)+' day ago');
                    }})();
                    </script>
                    <button class="filter-toggle" type="button" onclick="toggleFilterCollapse()" aria-label="Toggle filters">
                        <svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
                    </button>
                </div>
            </div>

            <div class="filter-row" id="filter-row">
                <button class="preset-btn" data-preset="India Desk" onclick="togglePreset('India Desk')">India Desk</button>
                <button class="preset-btn" data-preset="World Desk" onclick="togglePreset('World Desk')">World Desk</button>
                <button class="preset-btn" data-preset="Indie Voices" onclick="togglePreset('Indie Voices')">Indie Voices</button>
                <button class="preset-btn" data-preset="Official Channels" onclick="togglePreset('Official Channels')">Official Channels</button>
                <div class="publisher-dropdown" id="publisher-dropdown">
                    <button class="publisher-dropdown-trigger" id="publisher-trigger" onclick="toggleDropdown()">
                        <span id="publisher-summary">All publishers</span>
                        <span class="dropdown-arrow">▼</span>
                    </button>
                    <div class="publisher-dropdown-panel" id="publisher-panel">
                        <input type="text" class="dropdown-search" id="dropdown-search" placeholder="Search publishers..." oninput="filterPublisherList()">
                        <div class="dropdown-actions">
                            <button class="dropdown-action" onclick="selectAllPublishers()">Select All</button>
                            <button class="dropdown-action" onclick="clearAllPublishers()">Clear All</button>
                        </div>
                        <div class="dropdown-list" id="dropdown-list"></div>
                    </div>
                </div>
            </div>

        </div>

        <div id="articles">
"""

    current_date = None

    for group in sorted_groups:
        article = group["primary"]
        related_sources = group["related_sources"]

        # Convert to local time for display
        local_dt = to_local_datetime(article["date"])

        # Add date header if new date
        if local_dt:
            article_date = local_dt.date()
            if article_date != current_date:
                current_date = article_date
                if article_date == today:
                    date_label = "Today"
                elif article_date == yesterday:
                    date_label = "Yesterday"
                else:
                    date_label = article_date.strftime("%A, %B %d")
                html += f'            <h2 class="date-header">{date_label}</h2>\n'

        title = escape(clean_html(article["title"]))
        link = escape(sanitize_url(article["link"]))
        source = escape(article["source"])
        source_url = escape(sanitize_url(article["source_url"]))
        description = escape(clean_html(article["description"]))
        time_str = local_dt.strftime("%I:%M %p").lstrip("0") if local_dt else ""
        article_date_iso = local_dt.date().isoformat() if local_dt else ""

        # Truncate long source names for display
        source_display = source[:35] + "..." if len(source) > 35 else source

        # Build "Also covered by" HTML and source badge if there are related sources
        also_covered_html = ""
        source_badge_html = ""
        is_in_focus = "true" if related_sources else "false"
        if related_sources:
            total_sources = len(related_sources) + 1  # +1 for the primary source
            source_badge_html = f'<span class="source-badge">{total_sources} sources</span>'
            source_links = []
            for rs in related_sources[:5]:  # Limit to 5 additional sources
                rs_name = escape(rs["name"])
                rs_link = escape(sanitize_url(rs["link"]))
                # Truncate source name for display
                rs_display = rs_name[:25] + "..." if len(rs_name) > 25 else rs_name
                source_links.append(f'<a href="{rs_link}" target="_blank" rel="noopener" title="{rs_name}">{rs_display}</a>')
            also_covered_html = f'\n                <div class="also-covered">Also covered by: {", ".join(source_links)}</div>'

        publisher = escape(article.get("publisher", ""))
        html += f"""            <article class="article" data-source="{source.lower()}" data-date="{article_date_iso}" data-url="{link}" data-title="{title}" data-in-focus="{is_in_focus}" data-publisher="{publisher}">
                <h3 class="article-title"><a href="{link}" target="_blank" rel="noopener">{title}</a>{source_badge_html}</h3>
                <div class="article-meta">
                    <a href="{source_url}" target="_blank" class="source-tag" title="{source}">{source_display}</a>
                    {f'<span class="meta-dot">·</span><span class="article-time">{time_str}</span>' if time_str else ''}
                    <span class="meta-dot">·</span>
                    <button class="bookmark-btn" onclick="toggleBookmark(this)" aria-label="Bookmark article" title="Bookmark">
                        <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                    </button>
                </div>{also_covered_html}
            </article>
"""

    html += f"""        </div>

        <div id="pagination-bottom" class="pagination bottom" aria-label="Pagination"></div>
        </div><!-- /tab-news -->

        <div id="tab-reports" class="tab-content">
            <div class="filter-card">
                <div class="tg-filter-top">
                    <div class="tg-view-toggle">
                        <button class="tg-view-btn active" id="reports-view-all" onclick="setReportsView('all')">All</button>
                        <button class="tg-view-btn" id="reports-view-pdf" onclick="setReportsView('pdf')">Reports</button>
                        <button class="tg-view-btn" id="reports-view-nopdf" onclick="setReportsView('nopdf')">Posts</button>
                    </div>
                    <div class="tg-filter-meta">
                        <strong id="reports-visible-count">{report_count}</strong>
                        <span>·</span>
                        <span id="reports-update-time" data-time="{telegram_generated_at}">--</span>
                        <script>
                        (function(){{
                            var el=document.getElementById('reports-update-time'),t=el&&el.getAttribute('data-time');
                            if(!t)return;
                            var d=Math.floor((new Date()-new Date(t))/60000);
                            el.textContent='Updated '+(d<1?'just now':d<60?d+' min ago':d<1440?Math.floor(d/60)+' hr ago':Math.floor(d/1440)+' day ago');
                        }})();
                        </script>
                    </div>
                </div>
                <div class="tg-filter-bottom">
                    <div class="publisher-dropdown" id="tg-channel-dropdown">
                        <button class="publisher-dropdown-trigger" id="tg-channel-trigger" onclick="toggleTgDropdown()">
                            <span id="tg-channel-summary">All channels</span>
                            <span class="dropdown-arrow">&#9660;</span>
                        </button>
                        <div class="publisher-dropdown-panel" id="tg-channel-panel">
                            <input type="text" class="dropdown-search" id="tg-dropdown-search" placeholder="Search channels..." oninput="filterTgChannelList()">
                            <div class="dropdown-actions">
                                <button class="dropdown-action" onclick="selectAllTgChannels()">Select All</button>
                                <button class="dropdown-action" onclick="clearAllTgChannels()">Clear All</button>
                            </div>
                            <div class="dropdown-list" id="tg-dropdown-list"></div>
                        </div>
                    </div>
                    <button class="tg-chip" id="reports-notarget-filter" onclick="toggleNoTargetFilter()">No price targets</button>
                </div>
            </div>
            <div id="reports-warning" class="reports-warning" style="display:none"></div>
            <div id="reports-container"></div>
            <div id="reports-pagination-bottom" class="pagination bottom"></div>
        </div><!-- /tab-reports -->

        <div id="tab-research" class="tab-content">
            <div class="filter-card">
                <div class="tg-filter-top">
                    <div class="tg-view-toggle">
                        <button class="tg-view-btn active" id="research-region-all" onclick="setResearchRegion('all')">All</button>
                        <button class="tg-view-btn" id="research-region-indian" onclick="setResearchRegion('indian')">Indian</button>
                        <button class="tg-view-btn" id="research-region-international" onclick="setResearchRegion('international')">International</button>
                    </div>
                    <div class="tg-filter-meta">
                        <strong id="research-visible-count">{research_count}</strong>
                        <span>&middot;</span>
                        <span class="update-time" id="research-update-time" data-time="{now_ist.isoformat()}">Updated {now_ist.strftime("%b %d, %I:%M %p")} IST</span>
                        <script>
                        (function(){{
                            var el=document.getElementById('research-update-time'),t=el&&el.getAttribute('data-time');
                            if(!t)return;
                            var d=Math.floor((new Date()-new Date(t))/60000);
                            el.textContent='Updated '+(d<1?'just now':d<60?d+' min ago':d<1440?Math.floor(d/60)+' hr ago':Math.floor(d/1440)+' day ago');
                        }})();
                        </script>
                    </div>
                </div>
                <div class="tg-filter-bottom">
                    <div class="publisher-dropdown" id="research-publisher-dropdown">
                        <button class="publisher-dropdown-trigger" id="research-publisher-trigger" onclick="toggleResearchDropdown()">
                            <span id="research-publisher-summary">All publishers</span>
                            <span class="dropdown-arrow">&#9660;</span>
                        </button>
                        <div class="publisher-dropdown-panel" id="research-publisher-panel">
                            <input type="text" class="dropdown-search" id="research-dropdown-search" placeholder="Search publishers..." oninput="filterResearchPublisherList()">
                            <div class="dropdown-actions">
                                <button class="dropdown-action" onclick="selectAllResearchPublishers()">Select All</button>
                                <button class="dropdown-action" onclick="clearAllResearchPublishers()">Clear All</button>
                            </div>
                            <div class="dropdown-list" id="research-dropdown-list"></div>
                        </div>
                    </div>
                </div>
            </div>
            <div id="research-container"></div>
            <div id="research-pagination-bottom" class="pagination bottom"></div>
        </div><!-- /tab-research -->

        <div id="tab-youtube" class="tab-content">
            <div class="filter-card">
                <div class="stats-bar">
                    <div class="stats">
                        <span><strong id="youtube-visible-count">{video_count}</strong> videos</span>
                        <span id="youtube-publisher-count-label"><strong>{video_channel_count}</strong> channels</span>
                    </div>
                    <div style="display:flex;align-items:center;">
                        <span class="update-time" id="youtube-update-time" data-time="{now_ist.isoformat()}">Updated {now_ist.strftime("%b %d, %I:%M %p")} IST</span>
                        <script>
                        (function(){{
                            var el=document.getElementById('youtube-update-time'),t=el&&el.getAttribute('data-time');
                            if(!t)return;
                            var d=Math.floor((new Date()-new Date(t))/60000);
                            el.textContent='Updated '+(d<1?'just now':d<60?d+' min ago':d<1440?Math.floor(d/60)+' hr ago':Math.floor(d/1440)+' day ago');
                        }})();
                        </script>
                        <button class="filter-toggle" type="button" onclick="toggleFilterCollapse()" aria-label="Toggle filters">
                            <svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
                        </button>
                    </div>
                </div>
                <div class="filter-row" id="youtube-filter-row">
                    <div class="publisher-dropdown" id="youtube-publisher-dropdown">
                        <button class="publisher-dropdown-trigger" id="youtube-publisher-trigger" onclick="toggleYoutubeDropdown()">
                            <span id="youtube-publisher-summary">All channels</span>
                            <span class="dropdown-arrow">&#9660;</span>
                        </button>
                        <div class="publisher-dropdown-panel" id="youtube-publisher-panel">
                            <input type="text" class="dropdown-search" id="youtube-dropdown-search" placeholder="Search channels..." oninput="filterYoutubePublisherList()">
                            <div class="dropdown-actions">
                                <button class="dropdown-action" onclick="selectAllYoutubePublishers()">Select All</button>
                                <button class="dropdown-action" onclick="clearAllYoutubePublishers()">Clear All</button>
                            </div>
                            <div class="dropdown-list" id="youtube-dropdown-list"></div>
                        </div>
                    </div>
                </div>
            </div>
            <div id="youtube-container"></div>
            <div id="youtube-pagination-bottom" class="pagination bottom"></div>
        </div><!-- /tab-youtube -->

        <div id="tab-twitter" class="tab-content">
            <div class="filter-card">
                <div class="stats-bar">
                    <div class="stats">
                        <span><strong id="twitter-visible-count">{twitter_count}</strong> tweets</span>
                        <span id="twitter-publisher-count-label"></span>
                    </div>
                    <div style="display:flex;align-items:center;">
                        <span class="update-time" id="twitter-update-time" data-time="{now_ist.isoformat()}">Updated {now_ist.strftime("%b %d, %I:%M %p")} IST</span>
                        <script>
                        (function(){{
                            var el=document.getElementById('twitter-update-time'),t=el&&el.getAttribute('data-time');
                            if(!t)return;
                            var d=Math.floor((new Date()-new Date(t))/60000);
                            el.textContent='Updated '+(d<1?'just now':d<60?d+' min ago':d<1440?Math.floor(d/60)+' hr ago':Math.floor(d/1440)+' day ago');
                        }})();
                        </script>
                        <button class="filter-toggle" type="button" onclick="toggleFilterCollapse()" aria-label="Toggle filters">
                            <svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
                        </button>
                    </div>
                </div>
                <div class="filter-row" id="twitter-filter-row">
                    <div class="publisher-dropdown" id="twitter-publisher-dropdown">
                        <button class="publisher-dropdown-trigger" id="twitter-publisher-trigger" onclick="toggleTwitterDropdown()">
                            <span id="twitter-publisher-summary">All publishers</span>
                            <span class="dropdown-arrow">&#9660;</span>
                        </button>
                        <div class="publisher-dropdown-panel" id="twitter-publisher-panel">
                            <input type="text" class="dropdown-search" id="twitter-dropdown-search" placeholder="Search publishers..." oninput="filterTwitterPublisherList()">
                            <div class="dropdown-actions">
                                <button class="dropdown-action" onclick="selectAllTwitterPublishers()">Select All</button>
                                <button class="dropdown-action" onclick="clearAllTwitterPublishers()">Clear All</button>
                            </div>
                            <div class="dropdown-list" id="twitter-dropdown-list"></div>
                        </div>
                    </div>
                </div>
            </div>
            <div id="twitter-container"></div>
            <div id="twitter-pagination-bottom" class="pagination bottom"></div>
        </div><!-- /tab-twitter -->
"""

    html += """        <footer>
            Aggregated from {source_count} sources · Built with Python · Made by <a href="https://kashishkapoor.com/" target="_blank" rel="noopener">Kashish Kapoor</a> · Built for <a href="https://thedailybrief.zerodha.com/" target="_blank" rel="noopener">The Daily Brief by Zerodha</a>
        </footer>
    </div>

    <button class="back-to-top" onclick="window.scrollTo({top:0,behavior:'smooth'})" title="Back to top">↑</button>

    <div class="keyboard-hint">
        <kbd>1</kbd> <kbd>2</kbd> <kbd>3</kbd> <kbd>4</kbd> <kbd>5</kbd> tabs · <kbd>J</kbd> <kbd>K</kbd> navigate · <kbd>/</kbd> search
    </div>

    <script>
"""
    # Inject publisher data as JSON
    html += f"""        const ALL_PUBLISHERS = {all_publishers_json};
        const PUBLISHER_PRESETS = {publisher_presets_json};
        const TELEGRAM_REPORTS = {telegram_reports_json};
        const TELEGRAM_GENERATED_AT = "{telegram_generated_at}";
        const TELEGRAM_WARNINGS = {json.dumps(telegram_warnings)};
        const YOUTUBE_VIDEOS = {video_articles_json};
        const YOUTUBE_PUBLISHERS = {youtube_publishers_json};
        const TWITTER_ARTICLES = {twitter_articles_json};
        const TWITTER_PUBLISHERS = {twitter_publishers_json};
        const TWITTER_PRESETS = {twitter_presets_json};
        const RESEARCH_REPORTS = {research_reports_json};
        const RESEARCH_PUBLISHERS = {research_publishers_json};
"""
    # Read JS from external file
    js_path = os.path.join(SCRIPT_DIR, "templates", "app.js")
    with open(js_path, "r", encoding="utf-8") as f:
        js_content = f.read()
    html += "\n" + js_content
    html += """    </script>
</body>
</html>
"""
    # Apply template replacements
    html = html.replace("{source_count}", str(len(sources)))
    html = html.replace("{in_focus_count}", str(in_focus_count))
    html = html.replace("{today_iso}", today_iso)

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\nGenerated: {OUTPUT_FILE}")
        print(f"Total articles: {len(sorted_articles)}")
    except IOError as e:
        print(f"\nERROR: Could not write to {OUTPUT_FILE}: {e}")


def main():
    logger = FeedLogger()

    logger.info("=" * 50)
    logger.info("RSS News Aggregator")
    logger.info("=" * 50)

    feeds = load_feeds()
    if not feeds:
        logger.warn("feeds", "No feeds to fetch. Check your feeds.json file.")
        return

    logger.info(f"Fetching {len(feeds)} feeds...")

    all_articles = []

    # Fetch feeds in parallel (10 at a time)
    with ThreadPoolExecutor(max_workers=FEED_THREAD_WORKERS) as executor:
        futures = {}
        for feed in feeds:
            feed_field = feed.get("feed", "")
            if feed.get("id") == "the-ken":
                futures[executor.submit(fetch_the_ken, feed)] = feed
            elif feed_field.startswith("careratings:"):
                futures[executor.submit(fetch_careratings, feed)] = feed
            else:
                report_fetcher = get_report_fetcher(feed_field)
                if report_fetcher:
                    futures[executor.submit(report_fetcher, feed)] = feed
                else:
                    futures[executor.submit(fetch_feed, feed)] = feed

        for future in as_completed(futures):
            feed_cfg = futures[future]
            feed_name = feed_cfg.get("name", "?")
            try:
                articles = future.result()
                all_articles.extend(articles)
                if articles:
                    logger.ok(feed_name, f"{len(articles)} articles")
                    logger.add_articles(len(articles))
                else:
                    if feed_cfg.get("id") == "the-ken":
                        logger.warn(feed_name, "No articles returned after RSS/HTML/Google fallback (auto-skipped this run)")
                    elif feed_cfg.get("category") == "Reports":
                        logger.warn(feed_name, "No live reports returned; checking cache fallback")
                    else:
                        logger.fail(feed_name, "0 articles returned")
            except Exception as e:
                if feed_cfg.get("category") == "Reports":
                    logger.warn(feed_name, f"Live fetch error ({str(e)[:80]}); checking cache fallback")
                else:
                    logger.fail(feed_name, str(e))

    total_feeds = logger._ok + logger._fail
    logger.info(f"Total articles collected: {len(all_articles)}")
    logger.info(f"Feed results: {logger._ok}/{total_feeds} succeeded, {logger._fail} failed")
    if total_feeds > 0 and logger._fail / total_feeds > FEED_FAILURE_ALERT_THRESHOLD:
        logger.warn("aggregator", f"High failure rate: {logger._fail}/{total_feeds} feeds failed ({logger._fail*100//total_feeds}%)")

    # Invidious fallback: retry failed YouTube channel_id feeds
    video_feed_ids_fetched = set(
        a.get("feed_id") for a in all_articles if a.get("category") == "Videos"
    )
    for feed in feeds:
        if feed.get("category") != "Videos":
            continue
        if feed["id"] in video_feed_ids_fetched:
            continue  # already fetched successfully
        feed_url = feed.get("feed", "")
        if "channel_id=" not in feed_url:
            continue  # playlist_id feeds — Invidious format differs, skip
        channel_id = feed_url.split("channel_id=")[-1].strip()
        for instance in INVIDIOUS_INSTANCES:
            fallback_url = f"https://{instance}/feed/channel/{channel_id}"
            try:
                articles = fetch_feed({**feed, "feed": fallback_url})
                if articles:
                    all_articles.extend(articles)
                    logger.ok(f"Invidious:{instance} {feed['name']}", f"{len(articles)} videos")
                    break
            except Exception:
                continue

    # Separate video, twitter, and report articles from regular articles
    video_articles = [a for a in all_articles if a.get("category") == "Videos"]
    twitter_articles = [a for a in all_articles if a.get("category") == "Twitter"]
    report_articles = [a for a in all_articles if a.get("category") == "Reports"]
    regular_articles = [a for a in all_articles if a.get("category") not in ("Videos", "Twitter", "Reports")]
    logger.info(f"Videos: {len(video_articles)}, Twitter: {len(twitter_articles)}, Reports: {len(report_articles)}, Regular: {len(regular_articles)}")

    # Filter noisy videos (LIVE streams, market tickers, etc.)
    pre_filter_count = len(video_articles)
    video_articles = [v for v in video_articles if not should_filter_video(v)]
    filtered_video_count = pre_filter_count - len(video_articles)
    if filtered_video_count:
        logger.info(f"Videos: filtered {filtered_video_count} noisy titles")

    # Sort videos, twitter, and reports by date (newest first), no filtering/grouping needed
    video_articles.sort(key=get_sort_timestamp, reverse=True)
    twitter_articles.sort(key=get_sort_timestamp, reverse=True)

    # Reports cache: persist last successful per-feed report payloads
    def serialize_report_item(item):
        return {**item, "date": item["date"].isoformat() if item.get("date") else None}

    def deserialize_report_item(item):
        out = dict(item)
        if out.get("date"):
            try:
                out["date"] = datetime.fromisoformat(out["date"])
                if out["date"].tzinfo is None:
                    out["date"] = out["date"].replace(tzinfo=IST_TZ)
            except Exception:
                out["date"] = None
        else:
            out["date"] = None
        return out

    try:
        with open(REPORTS_CACHE_FILE, "r", encoding="utf-8") as f:
            report_cache = json.load(f)
        if isinstance(report_cache, list):
            report_cache = {}  # old format — discard, rebuild
    except (FileNotFoundError, json.JSONDecodeError):
        report_cache = {}

    report_feeds = {feed["id"]: feed for feed in feeds if feed.get("category") == "Reports"}
    live_reports_by_id = {}
    for report in report_articles:
        feed_id = report.get("feed_id", "")
        if feed_id:
            live_reports_by_id.setdefault(feed_id, []).append(report)

    # Refresh cache for report feeds that succeeded live
    for feed_id, items in live_reports_by_id.items():
        report_cache[feed_id] = [serialize_report_item(item) for item in items]

    # Fill missing report feeds from cache (especially useful for transient timeouts)
    for feed_id, feed_cfg in report_feeds.items():
        if live_reports_by_id.get(feed_id):
            continue
        cached_items = [deserialize_report_item(item) for item in report_cache.get(feed_id, []) if isinstance(item, dict)]
        if cached_items:
            report_articles.extend(cached_items)
            if feed_id.startswith("baroda-etrade"):
                logger.warn(feed_cfg["name"], f"Live fetch timed out; loaded {len(cached_items)} cached reports")
            else:
                logger.info(f"[cache] {feed_cfg['name']}: {len(cached_items)} reports")
            logger.add_articles(len(cached_items))
        elif feed_id.startswith("baroda-etrade"):
            logger.warn(feed_cfg["name"], "Live fetch timed out and no cache exists yet; skipped this run")

    try:
        with open(REPORTS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(report_cache, f)
        total_cached_reports = sum(len(v) for v in report_cache.values() if isinstance(v, list))
        logger.info(f"Reports cache: {total_cached_reports} items across {len(report_cache)} feeds")
    except Exception as e:
        logger.warn("Reports cache", f"could not write: {e}")

    # Deduplicate report articles by URL
    seen_report_urls = set()
    unique_reports = []
    for r in report_articles:
        url = (r.get("link") or "").lower().strip().rstrip("/")
        if url and url not in seen_report_urls:
            seen_report_urls.add(url)
            unique_reports.append(r)
    report_articles = unique_reports

    # Filter out reports older than 30 days (keep undated ones)
    report_cutoff = datetime.now(timezone.utc) - timedelta(days=REPORTS_FRESHNESS_DAYS)
    fresh_reports = []
    stale_count = 0
    for r in report_articles:
        rd = r.get("date")
        if rd is None:
            fresh_reports.append(r)
        else:
            if rd.tzinfo is None:
                rd = rd.replace(tzinfo=timezone.utc)
            if rd >= report_cutoff:
                fresh_reports.append(r)
            else:
                stale_count += 1
    report_articles = fresh_reports
    if stale_count:
        logger.info(f"Reports: removed {stale_count} stale (>30 days)")

    report_articles.sort(key=get_sort_timestamp, reverse=True)

    # YouTube cache: persist last successful fetch so CI failures don't wipe the tab
    YOUTUBE_CACHE_FILE = os.path.join(SCRIPT_DIR, "static", "youtube_cache.json")

    def serialize_video(v):
        return {**v, "date": v["date"].isoformat() if v.get("date") else None}

    def deserialize_video(v):
        if v.get("date"):
            from datetime import timezone
            try:
                v["date"] = datetime.fromisoformat(v["date"])
                if v["date"].tzinfo is None:
                    v["date"] = v["date"].replace(tzinfo=IST_TZ)
            except Exception:
                v["date"] = None
        return v

    # Load existing cache (handle old flat-list format by discarding it)
    try:
        with open(YOUTUBE_CACHE_FILE, "r", encoding="utf-8") as f:
            channel_cache = json.load(f)
        if isinstance(channel_cache, list):
            channel_cache = {}  # old format — discard, rebuild
    except (FileNotFoundError, json.JSONDecodeError):
        channel_cache = {}

    # Group freshly fetched videos by feed_id
    fresh_by_id = {}
    for v in video_articles:
        fid = v.get("feed_id", "unknown")
        fresh_by_id.setdefault(fid, []).append(v)

    # Update cache for channels that succeeded
    for fid, videos in fresh_by_id.items():
        channel_cache[fid] = [serialize_video(v) for v in videos]

    # Fill missing channels from cache
    video_feed_ids = {feed["id"] for feed in feeds if feed.get("category") == "Videos"}
    for fid in video_feed_ids:
        if fid not in fresh_by_id and fid in channel_cache:
            cached = [deserialize_video(v) for v in channel_cache[fid]]
            video_articles.extend(cached)
            feed_name = next((f["name"] for f in feeds if f["id"] == fid), fid)
            logger.info(f"[cache] {feed_name}: {len(cached)} videos")

    # Write updated cache
    try:
        with open(YOUTUBE_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(channel_cache, f)
        total = sum(len(v) for v in channel_cache.values())
        logger.info(f"YouTube cache: {total} videos across {len(channel_cache)} channels")
    except Exception as e:
        logger.warn("YouTube cache", f"could not write: {e}")

    # Re-sort after extending with cached videos
    video_articles.sort(key=get_sort_timestamp, reverse=True)

    # Filter out twitter articles older than configured days
    twitter_cutoff = datetime.now(IST_TZ) - timedelta(days=TWITTER_FRESHNESS_DAYS)
    twitter_articles = [t for t in twitter_articles
                        if t.get("date") is None or
                        (t["date"] if t["date"].tzinfo else t["date"].replace(tzinfo=IST_TZ)) >= twitter_cutoff]

    # Remove duplicates based on URL only (not title - to preserve source diversity)
    seen_urls = set()
    unique_articles = []

    for article in regular_articles:
        # Skip articles with no URL
        if not article["link"] or not article["link"].strip():
            continue

        # Normalize URL for comparison
        url = article["link"].lower().strip().rstrip('/')
        url = url.replace('http://', 'https://')

        # Skip if we've seen this exact URL before (within this run)
        if url in seen_urls:
            continue

        seen_urls.add(url)
        unique_articles.append(article)

    logger.info(f"After removing duplicates: {len(unique_articles)}")

    # Apply content filters to remove irrelevant/routine articles
    filtered_articles = []
    filtered_count = 0

    for article in unique_articles:
        if should_filter_article(article):
            filtered_count += 1
        else:
            filtered_articles.append(article)

    logger.info(f"After content filtering: {len(filtered_articles)} ({filtered_count} filtered out)")

    # Filter out articles older than configured days
    now = datetime.now(IST_TZ)
    cutoff_date = now - timedelta(days=NEWS_FRESHNESS_DAYS)
    recent_articles = []
    old_count = 0

    for article in filtered_articles:
        article_date = article.get("date")
        if article_date is None:
            # Keep articles without dates (will be sorted to end)
            recent_articles.append(article)
        else:
            # Ensure timezone-aware comparison
            if article_date.tzinfo is None:
                article_date = article_date.replace(tzinfo=IST_TZ)
            if article_date >= cutoff_date:
                recent_articles.append(article)
            else:
                old_count += 1

    filtered_articles = recent_articles
    logger.info(f"After removing old articles (>{NEWS_FRESHNESS_DAYS} days): {len(filtered_articles)} ({old_count} removed)")

    # Group similar articles by headline
    article_groups = group_similar_articles(filtered_articles)
    grouped_count = len(filtered_articles) - len(article_groups)
    logger.info(f"After grouping similar headlines: {len(article_groups)} groups ({grouped_count} articles merged)")

    generate_html(article_groups, video_articles, twitter_articles, report_articles)
    export_articles_json(article_groups)

    logger.summary()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
