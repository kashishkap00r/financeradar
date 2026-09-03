"""Unit tests for the beehiiv post extractor.

beehiiv publications on custom domains expose no RSS, so the fetcher scrapes
the post list out of the archive page's embedded SSR payload. These tests pin
that extraction against network calls.
"""

import unittest

from feeds import _beehiiv_extract_posts


def _post_blob(uuid, title, slug, scheduled, extra=""):
    return (
        '{"id":"' + uuid + '","web_title":"' + title + '",'
        '"web_subtitle":"","featured":false,"hide_from_feed":false,'
        '"override_scheduled_at":"' + scheduled + '","slug":"' + slug + '"'
        + extra + "}"
    )


class TestBeehiivExtractPosts(unittest.TestCase):
    def test_extracts_title_slug_and_date(self):
        html = (
            '<html><body><script>window.__DATA={"posts":['
            + _post_blob(
                "70315cea-3ed7-4dbc-b6e6-5408ab72000e",
                "The Data Moat Is Finally Real | The Public Ledger",
                "new-post-2ec6",
                "2026-09-02T20:30:00.000Z",
            )
            + "]}</script></body></html>"
        )
        posts = _beehiiv_extract_posts(html)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["web_title"],
                         "The Data Moat Is Finally Real | The Public Ledger")
        self.assertEqual(posts[0]["slug"], "new-post-2ec6")
        self.assertEqual(posts[0]["override_scheduled_at"], "2026-09-02T20:30:00.000Z")

    def test_handles_nested_objects_in_post(self):
        """content_tags nest braces — the brace matcher has to survive them."""
        nested = (
            ',"content_tags":[{"id":"380a10b0-e826-42bf-8e37-0b465a721224",'
            '"name":"public fintechs","display":"Public Fintechs"}]'
        )
        html = (
            '{"posts":['
            + _post_blob(
                "11111111-2222-3333-4444-555555555555",
                "Nested Tags Post",
                "nested-tags-post",
                "2026-09-01T10:00:00.000Z",
                extra=nested,
            )
            + "]}"
        )
        posts = _beehiiv_extract_posts(html)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["slug"], "nested-tags-post")
        self.assertEqual(posts[0]["content_tags"][0]["name"], "public fintechs")

    def test_skips_hidden_and_duplicate_slugs(self):
        hidden = _post_blob(
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "Hidden Post", "hidden-post", "2026-09-02T09:00:00.000Z",
        ).replace('"hide_from_feed":false', '"hide_from_feed":true')
        dup = _post_blob(
            "ffffffff-0000-1111-2222-333333333333",
            "Repeat Post", "repeat-post", "2026-08-30T09:00:00.000Z",
        )
        html = "[" + ",".join([hidden, dup, dup]) + "]"
        posts = _beehiiv_extract_posts(html)
        self.assertEqual([p["slug"] for p in posts], ["repeat-post"])

    def test_ignores_entries_without_title_or_slug(self):
        html = (
            '{"id":"99999999-8888-7777-6666-555555555555","web_title":"No Slug",'
            '"override_scheduled_at":"2026-09-02T20:30:00.000Z"}'
        )
        self.assertEqual(_beehiiv_extract_posts(html), [])

    def test_returns_empty_on_unrelated_html(self):
        self.assertEqual(_beehiiv_extract_posts("<html><body>nope</body></html>"), [])

    def test_ignores_unterminated_blob(self):
        """A truncated payload must not raise or return junk."""
        html = '{"id":"70315cea-3ed7-4dbc-b6e6-5408ab72000e","web_title":"Cut off'
        self.assertEqual(_beehiiv_extract_posts(html), [])


if __name__ == "__main__":
    unittest.main()
