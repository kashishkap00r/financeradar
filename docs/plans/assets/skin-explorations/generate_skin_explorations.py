#!/usr/bin/env python3
"""Generate 4 CSS-only visual skin explorations for FinanceRadar.

Reads the existing index.html and creates 4 variants by replacing
only the <style> block and Google Fonts <link> tags. HTML and JS
remain byte-identical, so all features work unchanged.
"""

import os
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parents[3]  # financeradar root
INDEX = PROJECT / "index.html"


def read_index():
    if not INDEX.exists():
        print(f"ERROR: {INDEX} not found. Run aggregator.py first.")
        sys.exit(1)
    return INDEX.read_text(encoding="utf-8")


def read_original_css():
    css_path = PROJECT / "templates" / "style.css"
    return css_path.read_text(encoding="utf-8")


def replace_skin(html, skin_name, font_links, css_content):
    """Replace fonts, CSS, and title in the HTML."""
    # Replace Google Fonts links (3 link tags: preconnect x2 + stylesheet)
    html = re.sub(
        r'<link[^>]*preconnect[^>]*href="https://fonts\.googleapis\.com"[^>]*>\s*'
        r'<link[^>]*preconnect[^>]*href="https://fonts\.gstatic\.com"[^>]*>\s*'
        r'<link[^>]*fonts\.googleapis\.com/css2[^>]*>',
        font_links,
        html,
        count=1,
    )
    # Replace <style>...</style>
    html = re.sub(
        r'<style>.*?</style>',
        f'<style>\n{css_content}\n</style>',
        html,
        count=1,
        flags=re.DOTALL,
    )
    # Replace title
    html = re.sub(
        r'<title>[^<]*</title>',
        f'<title>FinanceRadar — {skin_name}</title>',
        html,
        count=1,
    )
    return html


# ─── Skin CSS Generators ─────────────────────────────────────────────────────
# Each returns (font_links_html, css_string)
# Strategy: start from original CSS, then prepend override block

def make_skin_bloomberg(original_css):
    """Bloomberg Terminal: Dense, monospace, dark-first, electric blue."""
    font_links = (
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">'
    )
    overrides = """
    /* ═══════════════════════════════════════════════════════
       SKIN: Bloomberg Terminal
       Dense, professional, monospace-driven information density
       ═══════════════════════════════════════════════════════ */

    :root {
        --bg-primary: #f0f2f5;
        --bg-secondary: #e4e7ec;
        --bg-hover: #d8dce3;
        --text-primary: #0f172a;
        --text-secondary: #334155;
        --text-muted: #64748b;
        --accent: #2563eb;
        --accent-hover: #1d4ed8;
        --accent-soft: rgba(37, 99, 235, 0.1);
        --border: #cbd5e1;
        --border-light: #94a3b8;
        --card-shadow: none;
        --danger: #dc2626;
        --top-bar-height: 48px;
    }
    [data-theme="light"] {
        --bg-primary: #f0f2f5;
        --bg-secondary: #e4e7ec;
        --bg-hover: #d8dce3;
        --text-primary: #0f172a;
        --text-secondary: #334155;
        --text-muted: #64748b;
        --accent: #2563eb;
        --accent-hover: #1d4ed8;
        --accent-soft: rgba(37, 99, 235, 0.1);
        --border: #cbd5e1;
        --border-light: #94a3b8;
        --card-shadow: none;
        --danger: #dc2626;
    }
    [data-theme="dark"] {
        --bg-primary: #09090b;
        --bg-secondary: #111113;
        --bg-hover: #1a1a1f;
        --text-primary: #e2e8f0;
        --text-secondary: #94a3b8;
        --text-muted: #64748b;
        --accent: #60a5fa;
        --accent-hover: #93c5fd;
        --accent-soft: rgba(96, 165, 250, 0.12);
        --border: #1e293b;
        --border-light: #334155;
        --card-shadow: none;
        --danger: #ef4444;
    }

    /* Typography: Everything becomes Inter/JetBrains Mono */
    body {
        font-family: 'Inter', -apple-system, sans-serif !important;
        font-size: 13px !important;
        line-height: 1.45 !important;
    }
    .logo {
        font-family: 'JetBrains Mono', monospace !important;
        font-weight: 700 !important;
        font-size: 13px !important;
        letter-spacing: 0.08em !important;
        text-transform: uppercase !important;
        border-bottom: 2px solid var(--accent) !important;
        padding-bottom: 1px !important;
    }
    .article-title, .report-title, .video-title, .tweet-card-body,
    .sidebar-title, .sidebar-article-title, .home-hero-title,
    .spotlight-title, .rank-content a, .rank-title-nolink {
        font-family: 'Inter', -apple-system, sans-serif !important;
    }
    .article-title {
        font-size: 14px !important;
        font-weight: 600 !important;
        line-height: 1.35 !important;
    }
    .report-title {
        font-size: 14px !important;
        font-weight: 600 !important;
    }
    .video-title {
        font-size: 13px !important;
        font-weight: 600 !important;
    }
    .tweet-card-body {
        font-size: 13px !important;
        font-weight: 400 !important;
    }
    .home-hero-title {
        font-size: 18px !important;
        font-weight: 700 !important;
        text-decoration: none !important;
    }
    .sidebar-title {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 13px !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
    }
    .date-header {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 11px !important;
        letter-spacing: 0.12em !important;
    }
    .rank-content a, .rank-title-nolink {
        font-size: 12px !important;
    }

    /* Dense spacing */
    .top-bar { padding: 8px 12px !important; }
    .container { padding: 10px 12px !important; }
    .article { padding: 10px 12px !important; margin-bottom: 4px !important; }
    .report-card { padding: 10px 12px !important; margin-bottom: 4px !important; }
    .video-card { padding: 8px 10px !important; margin-bottom: 4px !important; gap: 10px !important; }
    .tweet-card { padding: 10px 12px !important; margin-bottom: 4px !important; }
    .filter-card { padding: 8px 12px !important; margin-bottom: 8px !important; }
    .home-card { padding: 8px 10px !important; gap: 4px !important; }

    /* Zero border-radius everywhere */
    .article, .report-card, .video-card, .tweet-card, .filter-card,
    .home-card, .home-hero-card, .spotlight-item, .spotlight-link,
    .preset-btn, .page-btn, .publisher-dropdown-panel,
    .publisher-dropdown-trigger, .report-doc-item,
    .video-thumb, .tweet-card-image, .report-images,
    #search, .mobile-menu-panel, .bookmarks-sidebar, .ai-sidebar,
    .theme-toggle, .bookmarks-toggle, .ai-toggle, .wsw-toggle,
    .in-focus-toggle, .mobile-menu-toggle {
        border-radius: 0px !important;
    }
    .spotlight-thumb { border-radius: 0 !important; }
    .spotlight-lane { border-radius: 2px !important; }
    .ai-source-pill, .wsw-view-pill { border-radius: 2px !important; }
    .bookmark-count, .in-focus-count { border-radius: 2px !important; }

    /* No shadows, no hover transforms */
    .article:hover, .report-card:hover, .video-card:hover, .tweet-card:hover,
    .home-card:hover, .spotlight-item:hover {
        box-shadow: none !important;
        transform: none !important;
    }

    /* Tabs: underline only */
    .content-tab {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 11px !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
        border-radius: 0 !important;
        background: transparent !important;
        border-bottom: 2px solid transparent !important;
        padding: 8px 12px !important;
    }
    .content-tab:hover {
        background: transparent !important;
        border-bottom-color: var(--border-light) !important;
    }
    .content-tab.active {
        background: transparent !important;
        border-bottom-color: var(--accent) !important;
        color: var(--accent) !important;
    }

    /* Filter pills: square, uppercase */
    .preset-btn {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 10px !important;
        text-transform: uppercase !important;
        letter-spacing: 0.06em !important;
        padding: 4px 10px !important;
    }

    /* Source tag */
    .source-tag { border-bottom-color: rgba(37, 99, 235, 0.3) !important; }
    .card-source-link { border-bottom-color: rgba(37, 99, 235, 0.3) !important; }
    [data-theme="dark"] .source-tag { border-bottom-color: rgba(96, 165, 250, 0.3) !important; }

    /* Meta text: monospace */
    .article-meta, .report-meta, .video-meta, .report-card-date,
    .tweet-card-date, .update-time, .stats {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 11px !important;
    }

    /* Video thumb smaller */
    .video-thumb { width: 140px !important; }

    /* Home hero */
    .home-hero-card {
        background: var(--bg-secondary) !important;
    }
    .spotlight-item {
        background: var(--bg-secondary) !important;
    }
    """
    return font_links, overrides + "\n" + original_css


def make_skin_broadsheet(original_css):
    """FT Broadsheet: Salmon warmth, serif authority, newspaper gravitas."""
    font_links = (
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '    <link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,300;6..72,400;6..72,500;6..72,600;6..72,700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&family=Public+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">'
    )
    overrides = """
    /* ═══════════════════════════════════════════════════════
       SKIN: FT Broadsheet
       Financial Times salmon warmth, serif authority, newspaper gravitas
       ═══════════════════════════════════════════════════════ */

    :root {
        --bg-primary: #fff1e5;
        --bg-secondary: #fff7f0;
        --bg-hover: #ffe9d6;
        --text-primary: #1a1a1a;
        --text-secondary: #4a4235;
        --text-muted: #7d7168;
        --accent: #990f3d;
        --accent-hover: #7d0a30;
        --accent-soft: rgba(153, 15, 61, 0.08);
        --border: #e0d4c8;
        --border-light: #ccc1b7;
        --card-shadow: none;
        --danger: #990f3d;
        --top-bar-height: 60px;
    }
    [data-theme="light"] {
        --bg-primary: #fff1e5;
        --bg-secondary: #fff7f0;
        --bg-hover: #ffe9d6;
        --text-primary: #1a1a1a;
        --text-secondary: #4a4235;
        --text-muted: #7d7168;
        --accent: #990f3d;
        --accent-hover: #7d0a30;
        --accent-soft: rgba(153, 15, 61, 0.08);
        --border: #e0d4c8;
        --border-light: #ccc1b7;
        --card-shadow: none;
        --danger: #990f3d;
    }
    [data-theme="dark"] {
        --bg-primary: #1a1410;
        --bg-secondary: #221b15;
        --bg-hover: #2d241c;
        --text-primary: #e8ddd0;
        --text-secondary: #b8a99a;
        --text-muted: #8a7e72;
        --accent: #d4774b;
        --accent-hover: #e8956a;
        --accent-soft: rgba(212, 119, 75, 0.12);
        --border: #352c24;
        --border-light: #4a3f35;
        --card-shadow: none;
        --danger: #d4774b;
    }

    /* Typography: Serif-forward newspaper feel */
    body {
        font-family: 'Public Sans', -apple-system, sans-serif !important;
        font-size: 15px !important;
        line-height: 1.55 !important;
    }
    .logo {
        font-family: 'Newsreader', Georgia, serif !important;
        font-weight: 700 !important;
        font-size: 1.25em !important;
        letter-spacing: -0.02em !important;
        border-bottom: 2px double var(--accent) !important;
        padding-bottom: 2px !important;
    }
    .article-title {
        font-family: 'Newsreader', Georgia, serif !important;
        font-size: 17px !important;
        font-weight: 600 !important;
        line-height: 1.32 !important;
        letter-spacing: -0.01em !important;
    }
    .report-title {
        font-family: 'Newsreader', Georgia, serif !important;
        font-size: 17px !important;
        font-weight: 600 !important;
        line-height: 1.32 !important;
    }
    .video-title {
        font-family: 'Newsreader', Georgia, serif !important;
        font-size: 16px !important;
        font-weight: 600 !important;
    }
    .tweet-card-body {
        font-family: 'Source Serif 4', Georgia, serif !important;
        font-size: 14.5px !important;
        line-height: 1.55 !important;
    }
    .home-hero-title {
        font-family: 'Newsreader', Georgia, serif !important;
        font-size: 28px !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
        text-decoration-color: rgba(153, 15, 61, 0.5) !important;
    }
    .sidebar-title {
        font-family: 'Newsreader', Georgia, serif !important;
        font-size: 17px !important;
    }
    .sidebar-article-title {
        font-family: 'Newsreader', Georgia, serif !important;
    }
    .rank-content a, .rank-title-nolink {
        font-family: 'Newsreader', Georgia, serif !important;
        font-size: 13.5px !important;
    }
    .report-text {
        font-family: 'Source Serif 4', Georgia, serif !important;
        font-size: 14.5px !important;
        line-height: 1.6 !important;
    }
    .article-description {
        font-family: 'Source Serif 4', Georgia, serif !important;
        font-size: 14.5px !important;
    }
    .spotlight-title {
        font-family: 'Newsreader', Georgia, serif !important;
        font-size: 12.5px !important;
        font-weight: 600 !important;
    }

    /* Cards: No visible border, hairline bottom rule only */
    .article {
        border: none !important;
        border-bottom: 1px solid var(--border) !important;
        border-radius: 0 !important;
        background: transparent !important;
        padding: 16px 4px !important;
        margin-bottom: 0 !important;
    }
    .article:hover {
        box-shadow: none !important;
        background: transparent !important;
    }
    .report-card {
        border: none !important;
        border-bottom: 1px solid var(--border) !important;
        border-radius: 0 !important;
        background: transparent !important;
        padding: 16px 4px !important;
        margin-bottom: 0 !important;
    }
    .report-card:hover { box-shadow: none !important; }
    .video-card {
        border: none !important;
        border-bottom: 1px solid var(--border) !important;
        border-radius: 0 !important;
        background: transparent !important;
        padding: 14px 4px !important;
        margin-bottom: 0 !important;
    }
    .video-card:hover { box-shadow: none !important; }
    .tweet-card {
        border: none !important;
        border-bottom: 1px solid var(--border) !important;
        border-radius: 0 !important;
        background: transparent !important;
        padding: 14px 4px !important;
        margin-bottom: 0 !important;
    }
    .tweet-card:hover { box-shadow: none !important; }

    /* Top bar: Centered brand, double rule */
    .top-bar {
        border-bottom: 3px double var(--border-light) !important;
        box-shadow: none !important;
        padding: 12px 16px !important;
    }

    /* Filter card: subtle */
    .filter-card {
        background: transparent !important;
        border: none !important;
        border-bottom: 1px solid var(--border) !important;
        border-radius: 0 !important;
    }

    /* Tabs: Serif, text-only, bottom rule */
    .content-tab {
        font-family: 'Newsreader', Georgia, serif !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        letter-spacing: 0.02em !important;
        border-radius: 0 !important;
        background: transparent !important;
        border-bottom: 2px solid transparent !important;
    }
    .content-tab.active {
        background: transparent !important;
        border-bottom-color: var(--accent) !important;
        font-weight: 700 !important;
    }
    .content-tab:hover {
        background: transparent !important;
    }

    /* Filter pills: text-only underline */
    .preset-btn {
        font-family: 'Public Sans', sans-serif !important;
        border: none !important;
        border-radius: 0 !important;
        background: transparent !important;
        padding: 4px 8px !important;
        border-bottom: 1px solid transparent !important;
    }
    .preset-btn:hover { border-bottom-color: var(--text-muted) !important; }
    .preset-btn.active {
        background: transparent !important;
        border-bottom-color: var(--accent) !important;
        color: var(--accent) !important;
    }

    /* Date header */
    .date-header {
        font-family: 'Public Sans', sans-serif !important;
        border-bottom: 1px solid var(--border) !important;
        padding-bottom: 6px !important;
    }

    /* Source link: muted underline */
    .source-tag { border-bottom-color: rgba(153, 15, 61, 0.25) !important; }
    .card-source-link { border-bottom-color: rgba(153, 15, 61, 0.25) !important; }

    /* Home hero: pure type hierarchy */
    .home-hero-card {
        background: var(--bg-primary) !important;
        border: none !important;
        border-bottom: 3px double var(--border-light) !important;
        border-radius: 0 !important;
    }
    .home-card {
        border-radius: 0 !important;
        background: transparent !important;
        border: none !important;
        border-bottom: 1px solid var(--border) !important;
    }
    .home-card:hover { box-shadow: none !important; }
    .spotlight-item {
        border-radius: 0 !important;
        background: transparent !important;
    }
    .spotlight-link { border-radius: 0 !important; }
    .spotlight-thumb { border-radius: 0 !important; }

    /* Action buttons: round warm */
    .theme-toggle, .bookmarks-toggle, .ai-toggle, .wsw-toggle,
    .in-focus-toggle, .mobile-menu-toggle {
        border-radius: 50% !important;
    }
    #search { border-radius: 0 !important; }
    .publisher-dropdown-trigger { border-radius: 0 !important; }
    .publisher-dropdown-panel { border-radius: 0 !important; }
    .page-btn { border-radius: 0 !important; }
    .video-thumb { border-radius: 0 !important; }
    .report-images { border-radius: 0 !important; }
    .tweet-card-image { border-radius: 0 !important; }
    .report-doc-item { border-radius: 0 !important; }

    /* Sidebar */
    .bookmarks-sidebar, .ai-sidebar { border-radius: 0 !important; }
    .ai-source-pill, .wsw-view-pill { border-radius: 0 !important; }
    """
    return font_links, overrides + "\n" + original_css


def make_skin_muji(original_css):
    """Muji Minimal: Japanese restraint, maximum whitespace, zero chromatic accent."""
    font_links = (
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">'
    )
    overrides = """
    /* ═══════════════════════════════════════════════════════
       SKIN: Muji Minimal
       Japanese minimalism. Maximum whitespace, invisible UI,
       content breathes. No chromatic accent — black is the accent.
       ═══════════════════════════════════════════════════════ */

    :root {
        --bg-primary: #ffffff;
        --bg-secondary: #ffffff;
        --bg-hover: #f8f8f8;
        --text-primary: #333333;
        --text-secondary: #666666;
        --text-muted: #aaaaaa;
        --accent: #333333;
        --accent-hover: #111111;
        --accent-soft: rgba(0, 0, 0, 0.04);
        --border: #f0f0f0;
        --border-light: #e0e0e0;
        --card-shadow: none;
        --danger: #333333;
        --top-bar-height: 72px;
    }
    [data-theme="light"] {
        --bg-primary: #ffffff;
        --bg-secondary: #ffffff;
        --bg-hover: #f8f8f8;
        --text-primary: #333333;
        --text-secondary: #666666;
        --text-muted: #aaaaaa;
        --accent: #333333;
        --accent-hover: #111111;
        --accent-soft: rgba(0, 0, 0, 0.04);
        --border: #f0f0f0;
        --border-light: #e0e0e0;
        --card-shadow: none;
        --danger: #333333;
    }
    [data-theme="dark"] {
        --bg-primary: #111111;
        --bg-secondary: #111111;
        --bg-hover: #1a1a1a;
        --text-primary: #e0e0e0;
        --text-secondary: #999999;
        --text-muted: #555555;
        --accent: #e0e0e0;
        --accent-hover: #ffffff;
        --accent-soft: rgba(255, 255, 255, 0.04);
        --border: #222222;
        --border-light: #333333;
        --card-shadow: none;
        --danger: #e0e0e0;
    }

    /* Typography: Noto Sans — clean, neutral, universal */
    body {
        font-family: 'Noto Sans', -apple-system, sans-serif !important;
        font-size: 14px !important;
        line-height: 1.7 !important;
    }
    .logo {
        font-family: 'Noto Sans', sans-serif !important;
        font-weight: 300 !important;
        font-size: 15px !important;
        letter-spacing: 0.15em !important;
        text-transform: uppercase !important;
        border-bottom: none !important;
        padding-bottom: 0 !important;
    }
    .article-title {
        font-family: 'Noto Sans', sans-serif !important;
        font-size: 15px !important;
        font-weight: 500 !important;
        line-height: 1.55 !important;
    }
    .report-title {
        font-family: 'Noto Sans', sans-serif !important;
        font-size: 15px !important;
        font-weight: 500 !important;
    }
    .video-title {
        font-family: 'Noto Sans', sans-serif !important;
        font-size: 14px !important;
        font-weight: 500 !important;
    }
    .tweet-card-body {
        font-family: 'Noto Sans', sans-serif !important;
        font-size: 14px !important;
        font-weight: 400 !important;
        line-height: 1.65 !important;
    }
    .home-hero-title {
        font-family: 'Noto Sans', sans-serif !important;
        font-size: 22px !important;
        font-weight: 500 !important;
        text-decoration: none !important;
    }
    .sidebar-title {
        font-family: 'Noto Sans', sans-serif !important;
        font-weight: 500 !important;
        font-size: 15px !important;
    }
    .sidebar-article-title {
        font-family: 'Noto Sans', sans-serif !important;
        font-weight: 500 !important;
    }
    .rank-content a, .rank-title-nolink {
        font-family: 'Noto Sans', sans-serif !important;
    }
    .report-text {
        font-family: 'Noto Sans', sans-serif !important;
        line-height: 1.7 !important;
    }
    .article-description {
        font-family: 'Noto Sans', sans-serif !important;
    }
    .date-header {
        font-family: 'Noto Sans', sans-serif !important;
        font-weight: 300 !important;
        letter-spacing: 0.2em !important;
        font-size: 11px !important;
        color: var(--text-muted) !important;
    }

    /* Generous spacing — content breathes */
    .top-bar { padding: 20px 24px !important; }
    .container { padding: 24px !important; max-width: 960px !important; }
    .article { padding: 20px 0 !important; margin-bottom: 0 !important; }
    .report-card { padding: 20px 0 !important; margin-bottom: 0 !important; }
    .video-card { padding: 16px 0 !important; margin-bottom: 0 !important; }
    .tweet-card { padding: 18px 0 !important; margin-bottom: 0 !important; }
    .filter-card { padding: 16px 0 !important; margin-bottom: 16px !important; }

    /* Cards: No border, no shadow, no bg — just hairline separators */
    .article {
        border: none !important;
        border-bottom: 1px solid var(--border) !important;
        border-radius: 0 !important;
        background: transparent !important;
    }
    .article:hover { box-shadow: none !important; background: transparent !important; }
    .report-card {
        border: none !important;
        border-bottom: 1px solid var(--border) !important;
        border-radius: 0 !important;
        background: transparent !important;
    }
    .report-card:hover { box-shadow: none !important; }
    .video-card {
        border: none !important;
        border-bottom: 1px solid var(--border) !important;
        border-radius: 0 !important;
        background: transparent !important;
    }
    .video-card:hover { box-shadow: none !important; }
    .tweet-card {
        border: none !important;
        border-bottom: 1px solid var(--border) !important;
        border-radius: 0 !important;
        background: transparent !important;
    }
    .tweet-card:hover { box-shadow: none !important; }

    /* Tabs: Text only, opacity change */
    .content-tab {
        font-family: 'Noto Sans', sans-serif !important;
        font-size: 12px !important;
        font-weight: 400 !important;
        letter-spacing: 0.08em !important;
        text-transform: uppercase !important;
        opacity: 0.4 !important;
        border-radius: 0 !important;
        background: transparent !important;
        transition: opacity 0.2s !important;
        border-bottom: 1px solid transparent !important;
    }
    .content-tab:hover {
        opacity: 0.7 !important;
        background: transparent !important;
    }
    .content-tab.active {
        opacity: 1 !important;
        font-weight: 600 !important;
        background: transparent !important;
        border-bottom-color: var(--text-primary) !important;
    }

    /* Filter pills: ghost buttons, generous padding */
    .preset-btn {
        font-family: 'Noto Sans', sans-serif !important;
        font-size: 11px !important;
        letter-spacing: 0.04em !important;
        padding: 6px 16px !important;
        border-radius: 24px !important;
        border-color: var(--border) !important;
    }
    .preset-btn.active {
        border-color: var(--text-primary) !important;
        background: transparent !important;
        color: var(--text-primary) !important;
    }

    /* Filter card: invisible */
    .filter-card {
        background: transparent !important;
        border: none !important;
        border-radius: 0 !important;
        border-bottom: 1px solid var(--border) !important;
    }

    /* Top bar: clean */
    .top-bar {
        border-bottom: 1px solid var(--border) !important;
        box-shadow: none !important;
    }

    /* Action buttons: rounded, minimal */
    .theme-toggle, .bookmarks-toggle, .ai-toggle, .wsw-toggle,
    .in-focus-toggle, .mobile-menu-toggle {
        border-radius: 50% !important;
        border-color: var(--border) !important;
        background: transparent !important;
    }
    #search {
        border-radius: 24px !important;
        background: transparent !important;
        border-color: var(--border) !important;
    }
    .publisher-dropdown-trigger { border-radius: 24px !important; }
    .publisher-dropdown-panel { border-radius: 12px !important; }
    .page-btn { border-radius: 24px !important; }

    /* Home: quiet */
    .home-hero-card {
        background: transparent !important;
        border: none !important;
        border-bottom: 1px solid var(--border) !important;
        border-radius: 0 !important;
    }
    .home-card {
        border-radius: 8px !important;
        background: transparent !important;
        border: 1px solid var(--border) !important;
    }
    .home-card:hover { box-shadow: none !important; }
    .spotlight-item {
        border-radius: 8px !important;
        background: transparent !important;
    }
    .spotlight-link { border-radius: 8px !important; }
    .spotlight-thumb { border-radius: 6px !important; }
    .video-thumb { border-radius: 6px !important; }
    .report-images { border-radius: 6px !important; }
    .tweet-card-image { border-radius: 6px !important; }
    .report-doc-item { border-radius: 6px !important; }

    /* Sidebar */
    .bookmarks-sidebar, .ai-sidebar { border-radius: 0 !important; }
    .ai-source-pill, .wsw-view-pill { border-radius: 24px !important; }
    .sidebar-btn { border-radius: 24px !important; }

    /* Source tag: no decorative underline */
    .source-tag { border-bottom: none !important; }
    .card-source-link { border-bottom: none !important; }

    /* Pulse dot: muted */
    .pulse-dot { background: var(--text-muted) !important; }
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(170, 170, 170, 0.4); }
        70% { box-shadow: 0 0 0 8px rgba(170, 170, 170, 0); }
        100% { box-shadow: 0 0 0 0 rgba(170, 170, 170, 0); }
    }

    /* Bookmark badge: black/white */
    .bookmark-count, .in-focus-count {
        background: var(--text-primary) !important;
        border-radius: 10px !important;
    }
    """
    return font_links, overrides + "\n" + original_css


def make_skin_notion(original_css):
    """Notion Clean: Warm gray, friendly rounded, modern SaaS aesthetic."""
    font_links = (
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&display=swap" rel="stylesheet">'
    )
    overrides = """
    /* ═══════════════════════════════════════════════════════
       SKIN: Notion Clean
       Notion/Linear-inspired SaaS. Friendly, rounded, warm gray.
       ═══════════════════════════════════════════════════════ */

    :root {
        --bg-primary: #ffffff;
        --bg-secondary: #f7f7f5;
        --bg-hover: #efefed;
        --text-primary: #37352f;
        --text-secondary: #6b6b64;
        --text-muted: #9b9a97;
        --accent: #2383e2;
        --accent-hover: #1b6ec2;
        --accent-soft: rgba(35, 131, 226, 0.08);
        --border: #e9e9e7;
        --border-light: #ddddd8;
        --card-shadow: 0 1px 2px rgba(0,0,0,0.04);
        --danger: #eb5757;
        --top-bar-height: 56px;
    }
    [data-theme="light"] {
        --bg-primary: #ffffff;
        --bg-secondary: #f7f7f5;
        --bg-hover: #efefed;
        --text-primary: #37352f;
        --text-secondary: #6b6b64;
        --text-muted: #9b9a97;
        --accent: #2383e2;
        --accent-hover: #1b6ec2;
        --accent-soft: rgba(35, 131, 226, 0.08);
        --border: #e9e9e7;
        --border-light: #ddddd8;
        --card-shadow: 0 1px 2px rgba(0,0,0,0.04);
        --danger: #eb5757;
    }
    [data-theme="dark"] {
        --bg-primary: #191919;
        --bg-secondary: #202020;
        --bg-hover: #2a2a2a;
        --text-primary: #e3e3e3;
        --text-secondary: #9b9b9b;
        --text-muted: #6b6b6b;
        --accent: #529cca;
        --accent-hover: #6bb3de;
        --accent-soft: rgba(82, 156, 202, 0.12);
        --border: #2f2f2f;
        --border-light: #3a3a3a;
        --card-shadow: 0 1px 2px rgba(0,0,0,0.2);
        --danger: #eb5757;
    }

    /* Typography: DM Sans everywhere — friendly, geometric */
    body {
        font-family: 'DM Sans', -apple-system, sans-serif !important;
        font-size: 15px !important;
        line-height: 1.6 !important;
    }
    .logo {
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 700 !important;
        font-size: 1.1em !important;
        letter-spacing: -0.02em !important;
        border-bottom: 2px solid var(--accent) !important;
    }
    .article-title {
        font-family: 'DM Sans', sans-serif !important;
        font-size: 15px !important;
        font-weight: 600 !important;
        line-height: 1.4 !important;
    }
    .report-title {
        font-family: 'DM Sans', sans-serif !important;
        font-size: 15px !important;
        font-weight: 600 !important;
    }
    .video-title {
        font-family: 'DM Sans', sans-serif !important;
        font-size: 14px !important;
        font-weight: 600 !important;
    }
    .tweet-card-body {
        font-family: 'DM Sans', sans-serif !important;
        font-size: 14px !important;
        line-height: 1.55 !important;
    }
    .home-hero-title {
        font-family: 'DM Sans', sans-serif !important;
        font-size: 24px !important;
        font-weight: 700 !important;
        text-decoration: none !important;
    }
    .sidebar-title {
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 600 !important;
    }
    .sidebar-article-title {
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 500 !important;
    }
    .rank-content a, .rank-title-nolink {
        font-family: 'DM Sans', sans-serif !important;
    }
    .report-text {
        font-family: 'DM Sans', sans-serif !important;
    }
    .article-description {
        font-family: 'DM Sans', sans-serif !important;
    }
    .date-header {
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 600 !important;
        font-size: 12px !important;
    }

    /* Cards: Notion-style warm gray, rounded, subtle hover */
    .article {
        border-radius: 8px !important;
        transition: background 0.15s, border-color 0.15s !important;
    }
    .article:hover {
        background: var(--bg-hover) !important;
        border-color: var(--border-light) !important;
        box-shadow: none !important;
        transform: none !important;
    }
    .report-card {
        border-radius: 8px !important;
    }
    .report-card:hover {
        background: var(--bg-hover) !important;
        box-shadow: none !important;
    }
    .video-card {
        border-radius: 8px !important;
    }
    .video-card:hover {
        background: var(--bg-hover) !important;
        box-shadow: none !important;
    }
    .tweet-card {
        border-radius: 8px !important;
    }
    .tweet-card:hover {
        background: var(--bg-hover) !important;
        box-shadow: none !important;
    }

    /* Tabs: Pill-shaped active background (like Notion sidebar) */
    .content-tab {
        font-family: 'DM Sans', sans-serif !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        border-radius: 6px !important;
        padding: 6px 12px !important;
        transition: all 0.15s !important;
    }
    .content-tab:hover {
        background: var(--bg-hover) !important;
    }
    .content-tab.active {
        background: var(--accent-soft) !important;
        color: var(--accent) !important;
        font-weight: 600 !important;
    }

    /* Filter pills: Full pill shape */
    .preset-btn {
        font-family: 'DM Sans', sans-serif !important;
        border-radius: 999px !important;
        font-size: 12px !important;
        padding: 5px 14px !important;
    }
    .preset-btn.active {
        background: var(--accent-soft) !important;
        border-color: rgba(35, 131, 226, 0.2) !important;
        color: var(--accent) !important;
    }

    /* Filter card */
    .filter-card {
        border-radius: 10px !important;
    }

    /* Top bar */
    .top-bar {
        box-shadow: none !important;
        border-bottom: 1px solid var(--border) !important;
    }

    /* Search: rounded with subtle bg */
    #search {
        border-radius: 8px !important;
        background: var(--bg-secondary) !important;
    }

    /* Action buttons: slightly rounded squares */
    .theme-toggle, .bookmarks-toggle, .ai-toggle, .wsw-toggle,
    .in-focus-toggle, .mobile-menu-toggle {
        border-radius: 8px !important;
    }
    .publisher-dropdown-trigger { border-radius: 999px !important; }
    .publisher-dropdown-panel { border-radius: 10px !important; }
    .page-btn { border-radius: 6px !important; }

    /* Home: Notion warm */
    .home-hero-card {
        border-radius: 12px !important;
        background: var(--bg-secondary) !important;
        border: 1px solid var(--border) !important;
    }
    .home-card {
        border-radius: 10px !important;
    }
    .home-card:hover {
        box-shadow: 0 2px 8px rgba(0,0,0,0.04) !important;
    }
    .spotlight-item { border-radius: 8px !important; }
    .spotlight-link { border-radius: 8px !important; }
    .spotlight-thumb { border-radius: 6px !important; }
    .video-thumb { border-radius: 8px !important; }
    .report-images { border-radius: 8px !important; }
    .tweet-card-image { border-radius: 8px !important; }
    .report-doc-item { border-radius: 6px !important; }

    /* Source tag */
    .source-tag { border-bottom-color: rgba(35, 131, 226, 0.2) !important; }
    .card-source-link { border-bottom-color: rgba(35, 131, 226, 0.2) !important; }

    /* Sidebar */
    .bookmarks-sidebar, .ai-sidebar { border-radius: 0 !important; }
    .ai-source-pill, .wsw-view-pill { border-radius: 999px !important; }
    .sidebar-btn { border-radius: 8px !important; }

    /* Bookmark badge */
    .bookmark-count, .in-focus-count {
        border-radius: 999px !important;
    }
    """
    return font_links, overrides + "\n" + original_css


# ─── Gallery Index ────────────────────────────────────────────────────────────

GALLERY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Skin Explorations — FinanceRadar</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&display=swap" rel="stylesheet">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'DM Sans', -apple-system, sans-serif; background: #fafafa; color: #1a1a1a;
    max-width: 760px; margin: 0 auto; padding: 48px 24px; }
  h1 { font-size: 28px; font-weight: 700; margin-bottom: 6px; letter-spacing: -0.02em; }
  .subtitle { font-size: 14px; color: #666; margin-bottom: 36px; line-height: 1.5; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 600px) { .grid { grid-template-columns: 1fr; } }
  .card { display: flex; flex-direction: column; background: #fff; border: 1px solid #e5e5e5;
    border-radius: 12px; overflow: hidden; text-decoration: none; color: inherit;
    transition: box-shadow 0.2s, border-color 0.2s, transform 0.15s; }
  .card:hover { box-shadow: 0 8px 24px rgba(0,0,0,0.08); border-color: #ccc; transform: translateY(-2px); }
  .card-swatch { height: 80px; display: flex; align-items: center; justify-content: center; }
  .card-swatch span { font-size: 32px; filter: grayscale(0.3); }
  .card-body { padding: 16px 18px 18px; }
  .card-body h2 { font-size: 16px; font-weight: 600; margin-bottom: 4px; letter-spacing: -0.01em; }
  .card-body .desc { font-size: 12.5px; color: #555; line-height: 1.55; margin-bottom: 10px; }
  .tags { display: flex; flex-wrap: wrap; gap: 4px; }
  .tag { font-size: 10px; background: #f0f0f0; color: #666; padding: 2px 8px; border-radius: 999px;
    letter-spacing: 0.03em; }

  /* Swatch backgrounds */
  .sw-bloomberg { background: linear-gradient(135deg, #0a1628 0%, #1e293b 100%); }
  .sw-broadsheet { background: linear-gradient(135deg, #fff1e5 0%, #ffe9d6 100%); }
  .sw-muji { background: #ffffff; border-bottom: 1px solid #f0f0f0; }
  .sw-notion { background: linear-gradient(135deg, #f7f7f5 0%, #efefed 100%); }
</style>
</head>
<body>
<h1>Skin Explorations</h1>
<p class="subtitle">4 CSS-only visual skins for FinanceRadar. Same structure, same features, same data — different personality. Every tab, sidebar, filter, and keyboard shortcut works identically.</p>

<div class="grid">
  <a class="card" href="s1-bloomberg-terminal.html">
    <div class="card-swatch sw-bloomberg"><span>📊</span></div>
    <div class="card-body">
      <h2>Bloomberg Terminal</h2>
      <p class="desc">Dense, professional, monospace-driven. Zero border-radius, electric blue accent, terminal-grade information density.</p>
      <div class="tags">
        <span class="tag">JetBrains Mono</span>
        <span class="tag">Inter</span>
        <span class="tag">Dense</span>
        <span class="tag">Dark-first</span>
      </div>
    </div>
  </a>

  <a class="card" href="s2-ft-broadsheet.html">
    <div class="card-swatch sw-broadsheet"><span>📰</span></div>
    <div class="card-body">
      <h2>FT Broadsheet</h2>
      <p class="desc">Financial Times salmon warmth. Serif authority, newspaper gravitas, double-rule borders, hairline card separators.</p>
      <div class="tags">
        <span class="tag">Newsreader</span>
        <span class="tag">Source Serif 4</span>
        <span class="tag">Warm</span>
        <span class="tag">Editorial</span>
      </div>
    </div>
  </a>

  <a class="card" href="s3-muji-minimal.html">
    <div class="card-swatch sw-muji"><span>🍃</span></div>
    <div class="card-body">
      <h2>Muji Minimal</h2>
      <p class="desc">Japanese restraint. Maximum whitespace, invisible UI, no chromatic accent. The content is the design.</p>
      <div class="tags">
        <span class="tag">Noto Sans</span>
        <span class="tag">Monochrome</span>
        <span class="tag">Spacious</span>
        <span class="tag">960px</span>
      </div>
    </div>
  </a>

  <a class="card" href="s4-notion-clean.html">
    <div class="card-swatch sw-notion"><span>📝</span></div>
    <div class="card-body">
      <h2>Notion Clean</h2>
      <p class="desc">Notion/Linear-inspired warm gray SaaS aesthetic. Friendly, rounded, pill tabs, hover-to-highlight cards.</p>
      <div class="tags">
        <span class="tag">DM Sans</span>
        <span class="tag">Notion gray</span>
        <span class="tag">Pill tabs</span>
        <span class="tag">Friendly</span>
      </div>
    </div>
  </a>
</div>
</body>
</html>"""


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("Loading index.html and original CSS...")
    html = read_index()
    original_css = read_original_css()
    print(f"  index.html: {len(html):,} chars")
    print(f"  style.css: {len(original_css):,} chars")

    skins = [
        ("s1-bloomberg-terminal.html", "Bloomberg Terminal", make_skin_bloomberg),
        ("s2-ft-broadsheet.html", "FT Broadsheet", make_skin_broadsheet),
        ("s3-muji-minimal.html", "Muji Minimal", make_skin_muji),
        ("s4-notion-clean.html", "Notion Clean", make_skin_notion),
    ]

    for fname, name, gen_fn in skins:
        font_links, css = gen_fn(original_css)
        skinned = replace_skin(html, name, font_links, css)
        out = BASE / fname
        out.write_text(skinned, encoding="utf-8")
        print(f"  Wrote {fname} ({len(skinned):,} chars)")

    # Gallery
    (BASE / "index.html").write_text(GALLERY_HTML, encoding="utf-8")
    print("  Wrote index.html (gallery)")
    print("Done! Open index.html to browse all skins.")


if __name__ == "__main__":
    main()
