## Finance Radar

I write the Daily Brief and The Chatter at Markets by Zerodha. Every morning I'd open 15-20 different tabs — from Reuters to Moneycontrol — scroll through all of them, then check 5-6 Twitter accounts for market takes, skim a couple of Telegram groups for broker reports, and then do a few Google News searches to make sure I hadn't missed something. Also spend some time on RBI, SEBI, or PIB websites for any official announcements.

On a good day this took 40 minutes. On most days I'd still miss something.

Used Claude Code to build Finance Radar instead. One page, 220+ sources, updates every hour. I open it in the morning and I'm caught up.

### The problem it solves

The issue isn't that information is hard to find. It's that it's scattered across too many places. Plus it's very noisy at times. Most of the time I'd end up skimming fast, because I know these feeds are filled with stock price movement news or fluffy predictions, or just simply badly done stories which don't qualify for what we would want to cover at the Daily Brief.

I just wanted one place where all of this shows up. Filtered, deduplicated, and with the important stuff surfaced to the top — so I built Finance Radar and have been refining it for some time now.

[📸 01-homepage-header.png]

### The big stories view

This is probably the most useful part. 4x a day, two LLMs (Gemini and DeepSeek) go through all ~1000 articles that I fetch and figure out what the major stories are. Related coverage gets grouped — so instead of seeing the Hormuz blockade story six times from six outlets, you see one cluster with all the sources underneath.

It's surprisingly good at this and makes my life easy because now I don't have to see the same story from different sources again and again.

[📸 02-homepage-clusters-mid.png]

Below the big stories, the rest of the AI-picked articles show up in a newspaper-style grid. This is what I actually scan most mornings.

[📸 03-homepage-feed.png]

There are also sections for AI-picked reports/tweets/YouTube videos that come in handy.

### Going deeper

The homepage is AI-curated, but sometimes I want to just browse everything chronologically. Each source type has its own tab.

**News** — the full firehose. 1300+ articles from 80+ publishers. I can filter by desk — India Markets, World, Indie (smaller publications I like, such as The Ken or Swarajya), and Official (RBI, SEBI, PIB, government sources).

[📸 04-news-tab.png]

**Reports** — this one took the most work. Institutional research from ING, HDFC Securities, CareEdge, CRISIL, SBI Research — each site has its own HTML structure, so there are 16 different scrapers. But once they're set up, new reports just appear here every day. Previously I would have to visit all these sites separately every day. If I miss a day, I would never know they published a report.

[📸 05-reports-tab.png]

**Twitter** — the data comes from a local RSSHub instance running on my laptop that fetches directly from Twitter, with Google News RSS as a fallback when that's down. This is important because here I have added some really smart people who end up tweeting about interesting things that I would definitely have missed out on.

[📸 06-twitter-tab.png]

**Telegram** — 7 channels joined through a Telegram bot, which then scrapes them. Here I get a goldmine — it's really high value for someone into equity analysis.

[📸 07-telegram-tab.png]

There's also a YouTube tab and a Papers tab for academic research, but I use those less frequently.

### It just runs

The whole thing is a static site on Cloudflare Pages. Python scripts fetch everything, generate HTML and JSON files, and GitHub Actions deploys it hourly. No server to maintain, no database, loads in under a second.

A systemd service on my laptop fetches fresh Twitter data via RSSHub and pushes it to GitHub. If I open my laptop after it's been asleep for a few hours, it detects that data is stale and catches up immediately instead of waiting for the next hourly cycle.

I haven't touched the pipeline in weeks. It just runs. Also, there's an AI layer on top for ranking.

### Works on mobile too

[📸 08-mobile-view.png]

### Other things

- 126 filters automatically strip out clickbait, duplicate wire copy, and irrelevant filler
- Deduplication catches near-identical articles across sources
- Consensus scoring — articles that both LLMs agree on rank higher
- Costs about $5/month for the AI ranking APIs. Hosting and everything else is free

Built entirely with Claude Code. About 8,900 lines of Python across 19 modules.
