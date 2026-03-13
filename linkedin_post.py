#!/usr/bin/env python3
"""
LinkedIn Post Scaffolder.

Takes a topic number from today's brief and generates a Jayant-style
post skeleton for you to fill in.

Usage:
    python3 linkedin_post.py 1              # scaffold topic 1 from today's brief
    python3 linkedin_post.py 3 --date 2026-03-14
    python3 linkedin_post.py --list         # show today's topics
    python3 linkedin_post.py --blank hot_take  # blank template without a topic
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BRIEFS_DIR = os.path.join(SCRIPT_DIR, "linkedin_briefs")
DRAFTS_DIR = os.path.join(SCRIPT_DIR, "linkedin_drafts")
IST_TZ = timezone(timedelta(hours=5, minutes=30))

# Character limit for LinkedIn posts (before "see more" truncation)
LINKEDIN_VISIBLE_CHARS = 210  # chars visible before "see more"
LINKEDIN_MAX_CHARS = 3000

# ── Post templates (Jayant Mundhra format) ──────────────────────────

TEMPLATES = {
    "hot_take": {
        "label": "🔥 Hot Take",
        "description": "Contrarian angle on trending news",
        "structure": """{hook}

..

Here's what's actually happening:

- {data_1}
- {data_2}
- {data_3}

..

But here's what most people are missing:

{non_obvious_angle}

..

{your_take}

..

This is a personal analysis, not investment advice.

..

PS: {cta}""",
    },
    "explainer": {
        "label": "📊 Explainer",
        "description": "Break down a sector/concept/mechanism",
        "structure": """{hook}

..

Let me break this down:

{data_1}

{data_2}

{data_3}

..

Why does this matter?

{non_obvious_angle}

..

My read on this:

{your_take}

..

This is a personal analysis, not investment advice.

..

PS: {cta}""",
    },
    "deep_dive": {
        "label": "🔍 Deep Dive",
        "description": "Multi-layered analysis connecting dots",
        "structure": """{hook}

..

The surface story:

{data_1}

..

Dig one layer deeper:

{data_2}

{data_3}

..

The connection nobody's making:

{non_obvious_angle}

..

Here's what I think:

{your_take}

..

This is a personal analysis, not investment advice.

..

PS: {cta}""",
    },
    "myth_buster": {
        "label": "💥 Myth Buster",
        "description": "Debunk a viral narrative with data",
        "structure": """Everyone's saying {hook}

Except... that's not quite right.

..

The actual numbers:

- {data_1}
- {data_2}
- {data_3}

..

So what's really going on?

{non_obvious_angle}

..

{your_take}

..

This is a personal analysis, not investment advice.

..

PS: {cta}""",
    },
    "sector_analysis": {
        "label": "📈 Sector Analysis",
        "description": "Compare companies/sectors with data",
        "structure": """{hook}

..

The numbers tell an interesting story:

{data_1}

{data_2}

..

But compare that with:

{data_3}

..

Here's the non-obvious takeaway:

{non_obvious_angle}

..

My take:

{your_take}

..

This is a personal analysis, not investment advice.

..

PS: {cta}""",
    },
}


# ── Load today's brief ──────────────────────────────────────────────


def load_brief(date_str):
    """Load the JSON brief for a given date."""
    json_path = os.path.join(BRIEFS_DIR, f"{date_str}.json")
    if not os.path.exists(json_path):
        return None
    with open(json_path, "r") as f:
        return json.load(f)


def list_topics(brief):
    """Print a quick summary of today's topics."""
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    themes = brief.get("themes", [])
    print(f"\n{BOLD}Today's topics ({brief.get('date', '?')}):{RESET}\n")
    for i, t in enumerate(themes, 1):
        strength = t.get("estimated_strength", "?")
        bucket = t.get("bucket_type", "?").replace("_", " ").title()
        print(f"  {BOLD}{i}.{RESET} {t.get('theme', 'Untitled')}  [{bucket}] [{strength}]")
        hook = t.get("hook", "")
        if len(hook) > 80:
            hook = hook[:77] + "..."
        print(f"     {DIM}{hook}{RESET}")
    print()


# ── Scaffold a post ─────────────────────────────────────────────────


def scaffold_post(theme, template_key=None):
    """Generate a post skeleton from a theme and template."""
    if not template_key:
        template_key = theme.get("bucket_type", "explainer")
    if template_key not in TEMPLATES:
        template_key = "explainer"

    template = TEMPLATES[template_key]
    data_points = theme.get("key_data_points", [])

    # Pad data points to at least 3
    while len(data_points) < 3:
        data_points.append("[ADD DATA POINT]")

    fields = {
        "hook": theme.get("hook", "[WRITE YOUR HOOK]"),
        "data_1": data_points[0],
        "data_2": data_points[1],
        "data_3": data_points[2],
        "non_obvious_angle": theme.get("non_obvious_angle", "[WRITE THE NON-OBVIOUS ANGLE]"),
        "your_take": f"[YOUR TAKE — {theme.get('your_take_prompt', 'What do you think?')}]",
        "cta": "[Your CTA — newsletter link, follow prompt, etc.]",
    }

    post_body = template["structure"].format(**fields)
    return post_body, template


def format_draft_file(theme, post_body, template, date_str, topic_num):
    """Format the full draft file with metadata and instructions."""
    sources = theme.get("source_articles", [])
    source_lines = "\n".join(
        f"- {s.get('title', 'Untitled')}: {s.get('url', '')}"
        for s in sources
    )

    char_count = len(post_body)
    hook_end = post_body.find("\n")
    hook_text = post_body[:hook_end] if hook_end > 0 else post_body[:LINKEDIN_VISIBLE_CHARS]
    hook_chars = len(hook_text)

    return f"""# LinkedIn Draft — {date_str} — Topic {topic_num}
# Theme: {theme.get('theme', 'Untitled')}
# Template: {template['label']}
#
# INSTRUCTIONS:
# 1. Replace all [BRACKETED PLACEHOLDERS] with your content
# 2. The hook ({hook_chars} chars) must grab attention in {LINKEDIN_VISIBLE_CHARS} chars (before "see more")
# 3. Data points should be SPECIFIC numbers — not vague claims
# 4. The "non-obvious angle" is the core of the post — spend time here
# 5. Your take should be a CLEAR STANCE, not "time will tell"
# 6. Total post: {char_count} chars (LinkedIn max: ~{LINKEDIN_MAX_CHARS})
#
# SOURCES (for your reference):
{chr(35)} {source_lines.replace(chr(10), chr(10) + chr(35) + ' ')}
#
# When done, run: python3 linkedin_post.py --format {topic_num} --date {date_str}
# ─────────────────────────────────────────────────────────────

{post_body}
"""


# ── Format for LinkedIn ─────────────────────────────────────────────


def format_for_linkedin(draft_path):
    """Read a draft file and output LinkedIn-ready text."""
    with open(draft_path, "r") as f:
        content = f.read()

    # Strip comment lines
    lines = []
    for line in content.split("\n"):
        if line.startswith("#"):
            continue
        lines.append(line)
    post_text = "\n".join(lines).strip()

    # Check for remaining placeholders
    import re
    placeholders = re.findall(r"\[([A-Z][A-Z _\-'?]+)\]", post_text)
    if placeholders:
        print(f"\n⚠️  WARNING: {len(placeholders)} unfilled placeholders found:")
        for p in placeholders:
            print(f"   - [{p}]")
        print()

    char_count = len(post_text)
    hook_end = post_text.find("\n")
    hook_len = hook_end if hook_end > 0 else len(post_text)

    print(f"\n{'═' * 60}")
    print(f"  LinkedIn-ready post ({char_count} chars)")
    print(f"  Hook length: {hook_len} chars (visible: {LINKEDIN_VISIBLE_CHARS})")
    if char_count > LINKEDIN_MAX_CHARS:
        print(f"  ⚠️  OVER LIMIT by {char_count - LINKEDIN_MAX_CHARS} chars — trim needed")
    print(f"{'═' * 60}\n")
    print(post_text)
    print(f"\n{'═' * 60}")
    print(f"  📋 Copy the text above and paste into LinkedIn")
    print(f"{'═' * 60}\n")

    return post_text


# ── Blank template mode ─────────────────────────────────────────────


def blank_template(template_key):
    """Generate a blank template without a topic brief."""
    if template_key not in TEMPLATES:
        print(f"Unknown template: {template_key}")
        print(f"Available: {', '.join(TEMPLATES.keys())}")
        sys.exit(1)

    template = TEMPLATES[template_key]
    fields = {
        "hook": "[WRITE YOUR HOOK — 1-2 provocative lines]",
        "data_1": "[DATA POINT 1 — specific number or fact]",
        "data_2": "[DATA POINT 2 — specific number or fact]",
        "data_3": "[DATA POINT 3 — specific number or fact]",
        "non_obvious_angle": "[THE NON-OBVIOUS ANGLE — what most people miss]",
        "your_take": "[YOUR TAKE — clear stance, not wishy-washy]",
        "cta": "[Your CTA]",
    }

    post_body = template["structure"].format(**fields)
    date_str = datetime.now(IST_TZ).strftime("%Y-%m-%d")
    print(f"\n{template['label']}: {template['description']}\n")
    print(post_body)

    # Save blank draft
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    draft_path = os.path.join(DRAFTS_DIR, f"{date_str}-blank-{template_key}.md")
    with open(draft_path, "w") as f:
        f.write(f"# Blank {template['label']} — {date_str}\n\n{post_body}\n")
    print(f"\nSaved: {draft_path}")


# ── Main ────────────────────────────────────────────────────────────


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scaffold LinkedIn posts from daily briefs")
    parser.add_argument("topic", nargs="?", type=int, help="Topic number from today's brief")
    parser.add_argument("--date", default=None, help="Date of the brief (YYYY-MM-DD)")
    parser.add_argument("--list", action="store_true", help="List today's topics")
    parser.add_argument("--blank", metavar="TEMPLATE", help="Generate blank template (hot_take, explainer, deep_dive, myth_buster, sector_analysis)")
    parser.add_argument("--format", metavar="TOPIC_NUM", type=int, help="Format a draft for LinkedIn posting")
    parser.add_argument("--templates", action="store_true", help="List available templates")
    parser.add_argument("--edit", "-e", action="store_true", help="Open draft in editor after scaffolding")
    args = parser.parse_args()

    date_str = args.date or datetime.now(IST_TZ).strftime("%Y-%m-%d")

    # List templates
    if args.templates:
        print("\nAvailable templates:\n")
        for key, t in TEMPLATES.items():
            print(f"  {t['label']}  ({key})")
            print(f"    {t['description']}\n")
        return

    # Blank template mode
    if args.blank:
        blank_template(args.blank)
        return

    # Format mode — convert draft to LinkedIn-ready text
    if args.format is not None:
        draft_path = os.path.join(DRAFTS_DIR, f"{date_str}-topic-{args.format}.md")
        if not os.path.exists(draft_path):
            print(f"Draft not found: {draft_path}")
            print(f"Available drafts:")
            if os.path.exists(DRAFTS_DIR):
                for f in sorted(os.listdir(DRAFTS_DIR)):
                    if f.endswith(".md"):
                        print(f"  {f}")
            sys.exit(1)
        post_text = format_for_linkedin(draft_path)

        # Save clean .txt for easy copy
        txt_path = os.path.join(DRAFTS_DIR, f"{date_str}-topic-{args.format}-READY.txt")
        with open(txt_path, "w") as f:
            f.write(post_text)
        print(f"  📄 Clean text saved: {txt_path}")

        # Try clipboard copy
        try:
            import subprocess
            subprocess.run(["xclip", "-selection", "clipboard"], input=post_text.encode(), check=True)
            print(f"  ✅ Copied to clipboard! Paste directly into LinkedIn.")
        except (FileNotFoundError, subprocess.CalledProcessError):
            print(f"  💡 Open the .txt file above and copy-paste to LinkedIn.")

        print()
        return

    # Load brief
    brief = load_brief(date_str)
    if not brief:
        print(f"No brief found for {date_str}")
        print(f"Run: GEMINI_API_KEY=... python3 linkedin_brief.py --date {date_str}")
        sys.exit(1)

    # List mode
    if args.list:
        list_topics(brief)
        return

    # Scaffold mode
    if args.topic is None:
        list_topics(brief)
        print("Pick a topic number: python3 linkedin_post.py <number>")
        return

    themes = brief.get("themes", [])
    if args.topic < 1 or args.topic > len(themes):
        print(f"Invalid topic number. Valid range: 1-{len(themes)}")
        sys.exit(1)

    theme = themes[args.topic - 1]
    post_body, template = scaffold_post(theme)

    # Print to terminal
    BOLD = "\033[1m"
    RESET = "\033[0m"
    print(f"\n{BOLD}Scaffolding: {theme.get('theme', 'Untitled')} ({template['label']}){RESET}\n")
    print(post_body)

    # Save draft
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    draft_path = os.path.join(DRAFTS_DIR, f"{date_str}-topic-{args.topic}.md")
    draft_content = format_draft_file(theme, post_body, template, date_str, args.topic)
    with open(draft_path, "w") as f:
        f.write(draft_content)

    print(f"\n{'─' * 50}")
    print(f"Draft saved: {draft_path}")
    print(f"\nNext steps:")
    print(f"  1. Edit:   nano {draft_path}")
    print(f"  2. Format: python3 linkedin_post.py --format {args.topic} --date {date_str}")
    print(f"{'─' * 50}\n")

    # Auto-open in editor if requested
    if args.edit:
        editor = os.environ.get("EDITOR", "nano")
        os.execvp(editor, [editor, draft_path])


if __name__ == "__main__":
    main()
