"""Share links + the utm_source=financeradar.news tag on outbound links (templates/app.js)."""

import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ReferralUrlTests(unittest.TestCase):
    CASES = {
        "https://www.livemint.com/x/abc.html":
            "https://www.livemint.com/x/abc.html?utm_source=financeradar.news&utm_medium=referral",
        "https://a.com/p?id=1#frag":
            "https://a.com/p?id=1&utm_source=financeradar.news&utm_medium=referral#frag",
        # Left alone: files, Google News redirects, social, signed links, already tagged, own site.
        "https://a.com/r.pdf": "https://a.com/r.pdf",
        "https://a.com/R.PDF": "https://a.com/R.PDF",
        "https://news.google.com/rss/articles/x": "https://news.google.com/rss/articles/x",
        "https://x.com/a/status/1": "https://x.com/a/status/1",
        "https://t.me/channel/42": "https://t.me/channel/42",
        "https://www.youtube.com/watch?v=abc": "https://www.youtube.com/watch?v=abc",
        "https://s3.amazonaws.com/f?X-Amz-Signature=1": "https://s3.amazonaws.com/f?X-Amz-Signature=1",
        "https://a.com/?utm_source=foo": "https://a.com/?utm_source=foo",
        "https://financeradar.news/about": "https://financeradar.news/about",
    }

    def test_referral_url(self):
        src = _read("templates/app.js")
        block = src[src.index("var REF_SOURCE"):src.index("function tagOutboundLink")]
        script = ("global.location={hostname:'financeradar.news'};" + block
                  + "console.log(JSON.stringify(" + json.dumps(list(self.CASES))
                  + ".map(function(u){return referralUrl(u,'referral');})));")
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), list(self.CASES.values()))


class ShareWiringTests(unittest.TestCase):
    def test_share_word_is_css_so_search_never_matches_it(self):
        css = _read("templates/style.css")
        self.assertIn('.share-link::after { content: "Share"; }', css)
        self.assertIn('.bs-share::after { content: "Share story"; }', css)
        js = _read("templates/app.js")
        helper = js[js.index("function shareLinkHtml"):js.index("function bsShareStoryHtml")]
        self.assertNotIn(">Share<", helper)

    def test_about_page_explains_the_tag(self):
        self.assertIn("utm_source=financeradar.news", _read("about.html"))


if __name__ == "__main__":
    unittest.main()
