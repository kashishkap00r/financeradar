"""Tests for ING feed parsing behavior."""

import unittest

from feeds import _parse_feed_content


class TestIngFeedParser(unittest.TestCase):
    """Validate ING-specific parsing logic."""

    def _ing_feed_cfg(self):
        return {
            "id": "ing-think-rss",
            "name": "ING THINK",
            "url": "https://think.ing.com/",
            "feed": "https://think.ing.com/rss/",
            "category": "Reports",
            "publisher": "ING",
        }

    def test_parses_dc_date_when_pubdate_missing(self):
        xml = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <item>
      <title>Europeans fear government spending</title>
      <link>https://think.ing.com/articles/europeans-fear-government-spending/</link>
      <description>desc</description>
      <dc:date>2026-02-26T08:45:00+00:00</dc:date>
    </item>
  </channel>
</rss>
"""
        items = _parse_feed_content(xml.encode("utf-8"), self._ing_feed_cfg())
        self.assertEqual(len(items), 1)
        self.assertIsNotNone(items[0]["date"])
        self.assertEqual(items[0]["date"].isoformat(), "2026-02-26T08:45:00+00:00")

    def test_ing_scope_includes_articles_and_snaps_only(self):
        xml = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Article</title>
      <link>https://think.ing.com/articles/a1/</link>
      <pubDate>Thu, 26 Feb 2026 10:30:00 +0000</pubDate>
      <description>desc</description>
    </item>
    <item>
      <title>Snap</title>
      <link>https://think.ing.com/snaps/s1/</link>
      <pubDate>Thu, 26 Feb 2026 09:30:00 +0000</pubDate>
      <description>desc</description>
    </item>
    <item>
      <title>Forecast</title>
      <link>https://think.ing.com/forecasts/f1/</link>
      <pubDate>Thu, 26 Feb 2026 08:30:00 +0000</pubDate>
      <description>desc</description>
    </item>
  </channel>
</rss>
"""
        items = _parse_feed_content(xml.encode("utf-8"), self._ing_feed_cfg())
        self.assertEqual(len(items), 2)
        links = {item["link"] for item in items}
        self.assertIn("https://think.ing.com/articles/a1/", links)
        self.assertIn("https://think.ing.com/snaps/s1/", links)
        self.assertNotIn("https://think.ing.com/forecasts/f1/", links)


if __name__ == "__main__":
    unittest.main()
