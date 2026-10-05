"""RSS descriptions are stored as plain text, never raw HTML."""

import unittest

from feeds import _parse_feed_content


class TestRssDescriptionCleaning(unittest.TestCase):

    def test_strips_html_before_truncating(self):
        # Quarto feeds (e.g. Takshashila) embed the whole page, so the first
        # 300 raw chars are all <style>/<script> boilerplate.
        boilerplate = "<style>.x{color:red}</style><script>var a = 1;" + " " * 400 + "</script>"
        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><item>
  <title>Why and How India Should Accelerate AI Diffusion</title>
  <link>https://takshashila.org.in/content/publications/example.html</link>
  <description><![CDATA[{boilerplate}<h2>Executive Summary</h2><p>AI diffusion &amp; adoption.</p>]]></description>
  <pubDate>Tue, 29 Sep 2026 18:30:00 GMT</pubDate>
</item></channel></rss>"""
        cfg = {"id": "takshashila-publications", "name": "Takshashila",
               "url": "https://takshashila.org.in/pages/publications/",
               "feed": "https://takshashila.org.in/pages/publications/index.xml",
               "category": "News", "publisher": "Takshashila"}
        items = _parse_feed_content(xml.encode("utf-8"), cfg)
        self.assertEqual(items[0]["description"], "Executive Summary AI diffusion & adoption.")


if __name__ == "__main__":
    unittest.main()
