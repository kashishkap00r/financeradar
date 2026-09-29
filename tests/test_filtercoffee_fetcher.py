"""Unit tests for the Filter Coffee (filtercoffee.co) fetcher."""

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from reports_fetcher import fetch_filtercoffee, get_report_fetcher


CFG = {
    "id": "filtercoffee-site",
    "name": "Filter Coffee — News & Stories",
    "url": "https://www.filtercoffee.co/news",
    "feed": "filtercoffee:site",
    "category": "News",
    "publisher": "Filter Coffee",
}

ACTION_ID = "4029541fdd61fc13b4835593bf03a36a588a0d3b92"

LISTING_PAGE = (
    '<html><head>'
    '<script src="/_next/static/chunks/app/layout-abc.js" async=""></script>'
    '<script src="/_next/static/chunks/app/(blog)/%5Bslug%5D/page-f76.js" async=""></script>'
    '</head><body></body></html>'
).encode("utf-8")

PAGE_CHUNK = (
    'var n=(0,a.createServerReference)("' + ACTION_ID + '",a.callServer,'
    'void 0,a.findSourceMapURL,"ghostPosts")'
).encode("utf-8")


def _iso(days_ago=1):
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000+00:00")


def _post(title, tag, slug=None, days_ago=1, excerpt="Summary."):
    return {
        "title": title,
        "slug": slug or title.lower().replace(" ", "-"),
        "published_at": _iso(days_ago),
        "custom_excerpt": excerpt,
        "tags": [{"name": tag.title(), "slug": tag}],
    }


def _action_response(posts):
    """React Server Components wire format: line 1 is [result, error]."""
    result = [{"posts": posts, "meta": {"pagination": {"page": 1}}}, None]
    return (
        '0:{"a":"$@1","f":"","b":"build"}\n1:' + json.dumps(result) + "\n"
    ).encode("utf-8")


def _blog_page(posts):
    """The /blog page streams its six newest posts inside self.__next_f."""
    payload = '9:["$","$L17",null,{"data":{"posts":' + json.dumps(posts) + '}}]\n'
    return (
        "<html><body><script>self.__next_f.push([1,"
        + json.dumps(payload)
        + "])</script></body></html>"
    ).encode("utf-8")


class TestFilterCoffee(unittest.TestCase):

    def _run(self, action_posts=None, action_error=None, blog_posts=()):
        def fake_fetch(url, *args, data=None, extra_headers=None, **kwargs):
            if url.endswith(".js"):
                return PAGE_CHUNK
            if data is not None:
                if action_error:
                    raise action_error
                self.assertEqual(extra_headers["Next-Action"], ACTION_ID)
                self.sent_query = json.loads(data)[0]
                return _action_response(action_posts or [])
            if url.endswith("/blog"):
                return _blog_page(list(blog_posts))
            return LISTING_PAGE

        with patch("reports_fetcher._fetch_url", side_effect=fake_fetch):
            return fetch_filtercoffee(CFG)

    def test_dispatcher_routes_prefix(self):
        self.assertIs(get_report_fetcher("filtercoffee:site"), fetch_filtercoffee)

    def test_maps_every_segment_with_its_own_url(self):
        articles = self._run(action_posts=[
            _post("Why is Fortis facing a forensic audit", "news"),
            _post("Gen Z is changing career growth", "stories-2"),
            _post("Pets are having their moment", "stories"),
            _post("Who fixes your broken phone", "this-is-business"),
        ])
        links = sorted(a["link"] for a in articles)
        self.assertEqual(links, [
            "https://www.filtercoffee.co/news/why-is-fortis-facing-a-forensic-audit",
            "https://www.filtercoffee.co/stories-2/gen-z-is-changing-career-growth",
            "https://www.filtercoffee.co/stories/pets-are-having-their-moment",
            "https://www.filtercoffee.co/this-is-business/who-fixes-your-broken-phone",
        ])
        art = articles[0]
        self.assertEqual(art["publisher"], "Filter Coffee")
        self.assertEqual(art["category"], "News")
        self.assertEqual(art["region"], "Indian")
        self.assertEqual(art["description"], "Summary.")

    def test_asks_ghost_to_leave_out_the_newsletter(self):
        """The daily newsletter already arrives through the Substack RSS feed."""
        self._run(action_posts=[])
        self.assertIn("filter=primary_tag:-newsletter-2", self.sent_query)

    def test_skips_newsletter_posts_even_if_returned(self):
        articles = self._run(action_posts=[
            _post("Media moguls back in the Fight Club", "newsletter-2"),
            _post("Sun Pharma bets on cholesterol", "news"),
        ])
        self.assertEqual([a["title"] for a in articles], ["Sun Pharma bets on cholesterol"])

    def test_newest_first_and_stale_dropped(self):
        articles = self._run(action_posts=[
            _post("Older story", "stories-2", days_ago=5),
            _post("Newest news", "news", days_ago=0),
            _post("Ancient news", "news", days_ago=90),
        ])
        self.assertEqual([a["title"] for a in articles], ["Newest news", "Older story"])

    def test_falls_back_to_blog_page_when_action_fails(self):
        """A redeploy can retire the action ID; /blog still carries the newest posts."""
        articles = self._run(
            action_error=RuntimeError("HTTP 404"),
            blog_posts=[
                _post("Newsletter issue", "newsletter-2"),
                _post("Fallback news", "news"),
            ],
        )
        self.assertEqual([a["title"] for a in articles], ["Fallback news"])


if __name__ == "__main__":
    unittest.main()
