"""Tests for the per-feed `link_contains` filter in feeds.json."""

import unittest

from feeds import _parse_feed_content

XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Newsletter issue</title>
      <link>https://www.bloomberg.com/news/newsletters/2026-10-20/issue</link>
      <pubDate>Tue, 20 Oct 2026 11:00:02 GMT</pubDate>
    </item>
    <item>
      <title>Regular article</title>
      <link>https://www.bloomberg.com/news/articles/2026-10-20/story</link>
      <pubDate>Tue, 20 Oct 2026 09:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Opinion newsletter issue</title>
      <link>https://www.bloomberg.com/opinion/newsletters/2026-10-19/levine</link>
      <pubDate>Mon, 19 Oct 2026 18:31:14 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def cfg(**extra):
    return {"id": "bloomberg-writer", "name": "Bloomberg — Writer", "url": "https://www.bloomberg.com",
            "feed": "https://www.bloomberg.com/authors/X/writer.rss", "category": "News",
            "publisher": "Bloomberg", **extra}


class TestLinkContainsFilter(unittest.TestCase):

    def test_keeps_only_matching_links(self):
        items = _parse_feed_content(XML.encode("utf-8"), cfg(link_contains="/newsletters/"))
        self.assertEqual([i["title"] for i in items], ["Newsletter issue", "Opinion newsletter issue"])

    def test_no_filter_keeps_everything(self):
        items = _parse_feed_content(XML.encode("utf-8"), cfg())
        self.assertEqual(len(items), 3)


if __name__ == "__main__":
    unittest.main()
