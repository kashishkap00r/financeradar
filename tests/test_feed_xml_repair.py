"""Feeds with small XML mistakes should still parse.

Rest of World's RSS puts raw "&" in image URLs
(`...jpg?width=380&dpr=2&crop=16:9`), which XML forbids, so the strict parser
rejected the whole feed and the source silently dropped off the site.
"""

import unittest

from feeds import _escape_bare_ampersands, _parse_feed_content

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
<channel>
  <title>Rest of World</title>
  <item>
    <title>Who controls the AI off switch &amp; why</title>
    <link>https://restofworld.org/2026/ai-off-switch/</link>
    <pubDate>Fri, 30 Oct 2026 08:00:00 +0000</pubDate>
    <description><![CDATA[Markets & merchants in Nairobi]]></description>
    <media:content url="https://fastly.restofworld.org/a.jpg?width=380&dpr=2&crop=16:9" />
  </item>
</channel>
</rss>
"""

CFG = {"id": "rest-of-world", "name": "Rest of World", "url": "https://restofworld.org", "category": "News"}


class XmlRepairTests(unittest.TestCase):
    def test_feed_with_bare_ampersands_parses(self):
        items = _parse_feed_content(FEED, CFG)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Who controls the AI off switch & why")
        self.assertEqual(items[0]["link"], "https://restofworld.org/2026/ai-off-switch/")

    def test_escape_leaves_entities_and_cdata_alone(self):
        fixed = _escape_bare_ampersands(FEED)
        self.assertIn(b"width=380&amp;dpr=2&amp;crop=16:9", fixed)
        self.assertIn(b"off switch &amp; why", fixed)          # not double-escaped
        self.assertIn(b"<![CDATA[Markets & merchants", fixed)  # CDATA untouched

    def test_numeric_and_named_entities_kept(self):
        self.assertEqual(_escape_bare_ampersands(b"a &#8217; &#x2019; &lt; & b"),
                         b"a &#8217; &#x2019; &lt; &amp; b")

    def test_valid_feed_is_unchanged(self):
        valid = FEED.replace(b"width=380&dpr=2&crop", b"width=380&amp;dpr=2&amp;crop")
        self.assertEqual(_escape_bare_ampersands(valid), valid)


if __name__ == "__main__":
    unittest.main()
