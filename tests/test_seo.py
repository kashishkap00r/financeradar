"""seo.py: head tags, crawler digest, and the wiring that keeps the digest invisible to readers."""

import json
import os
import re
import unittest
import xml.etree.ElementTree as ET

import seo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def _provider(items, status="ok"):
    return {"status": status, "buckets": {"news": items}}


class HeadTagsTests(unittest.TestCase):
    def test_has_title_description_canonical(self):
        html = seo.head_tags()
        self.assertEqual(html.count("<title>"), 1)
        self.assertIn('<meta name="description"', html)
        self.assertIn('<link rel="canonical" href="https://financeradar.news/">', html)
        self.assertIn('property="og:title"', html)

    def test_json_ld_parses_and_names_the_site(self):
        html = seo.head_tags()
        block = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
        graph = json.loads(block)["@graph"]
        site = next(n for n in graph if n["@type"] == "WebSite")
        self.assertEqual(site["name"], "Finance Radar")
        self.assertEqual(site["url"], "https://financeradar.news/")

    def test_description_fits_google_snippet(self):
        self.assertLessEqual(len(seo.DESCRIPTION), 160)


class TopHeadlinesTests(unittest.TestCase):
    def test_consensus_first_then_average_rank(self):
        rankings = {"providers": {
            "a": _provider([{"rank": 1, "title": "Solo", "url": "https://x/solo"},
                            {"rank": 5, "title": "Shared", "url": "https://x/shared"}]),
            "b": _provider([{"rank": 3, "title": "Shared", "url": "https://X/shared"}]),
        }}
        titles = [i["title"] for i in seo.top_headlines(rankings)]
        self.assertEqual(titles, ["Shared", "Solo"])

    def test_skips_failed_providers_and_bad_input(self):
        rankings = {"providers": {"a": _provider([{"rank": 1, "title": "X", "url": "https://x"}], "error")}}
        self.assertEqual(seo.top_headlines(rankings), [])
        self.assertEqual(seo.top_headlines(None), [])
        self.assertEqual(seo.top_headlines({"providers": {}}), [])

    def test_limit(self):
        items = [{"rank": i, "title": f"T{i}", "url": f"https://x/{i}"} for i in range(1, 40)]
        self.assertEqual(len(seo.top_headlines({"providers": {"a": _provider(items)}})), seo.DIGEST_SIZE)


class DigestHtmlTests(unittest.TestCase):
    def test_escapes_titles_and_drops_unsafe_links(self):
        rankings = {"providers": {"a": _provider([
            {"rank": 1, "title": "<script>alert(1)</script> & co", "url": "javascript:alert(1)", "source": "Mint"},
            {"rank": 2, "title": "Fine", "url": 'https://x/"onmouseover="y', "source": "ET"},
        ])}}
        html = seo.crawler_digest_html(rankings, "Friday, 13 November")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("javascript:", html)
        self.assertNotIn('"onmouseover="', html)
        self.assertIn("— Mint", html)
        self.assertEqual(html.count("<li>"), 2)

    def test_without_rankings_still_describes_the_site(self):
        html = seo.crawler_digest_html(None, "Friday, 13 November")
        self.assertIn("<h1>Finance Radar</h1>", html)
        self.assertNotIn("<ol>", html)


class WiringTests(unittest.TestCase):
    """The digest must never show for readers with JavaScript."""

    def test_digest_sits_inside_the_box_app_js_replaces(self):
        src = _read("aggregator.py")
        self.assertIn('<div id="home-newspaper">{seo.crawler_digest_html(', src)
        self.assertIn("container.innerHTML", _read("templates/app.js"))

    def test_js_class_set_before_paint_and_css_hides_digest(self):
        self.assertIn("document.documentElement.classList.add('js')", _read("aggregator.py"))
        self.assertIn("html.js .crawler-digest { display: none; }", _read("templates/style.css"))


class StaticFilesTests(unittest.TestCase):
    def test_robots_allows_all_and_points_to_sitemap(self):
        robots = _read("robots.txt")
        self.assertIn("User-agent: *", robots)
        self.assertIn("Allow: /", robots)
        self.assertIn("Sitemap: https://financeradar.news/sitemap.xml", robots)
        self.assertNotRegex(robots, r"(?m)^Disallow: /\s*$")

    def test_sitemap_is_valid_xml(self):
        root = ET.fromstring(_read("sitemap.xml"))
        locs = [e.text for e in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
        self.assertEqual(locs, ["https://financeradar.news/", "https://financeradar.news/about"])

    def test_404_and_llms_exist(self):
        self.assertIn('content="noindex"', _read("404.html"))
        self.assertTrue(_read("llms.txt").startswith("# Finance Radar"))


if __name__ == "__main__":
    unittest.main()
