"""getMergedClusters() in templates/app.js: one Big Story per event across models."""

import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _merge(providers):
    with open(os.path.join(ROOT, "templates/app.js"), encoding="utf-8") as f:
        src = f.read()
    block = src[src.index("        function getMergedClusters()"):src.index("        function getClusteredUrls(")]
    script = ("var aiRankings=" + json.dumps({"providers": providers}) + ";" + block
              + "console.log(JSON.stringify(getMergedClusters().map(function(c){"
              + "return {label:c.story_label, summary:c.story_summary, models:c._providerCount, n:1+c.related.length};})));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def _c(label, urls, group=None, summary=""):
    c = {"story_label": label, "story_summary": summary,
         "lead": {"title": label + " lead", "url": urls[0]},
         "related": [{"title": f"{label} piece {u}", "url": u} for u in urls[1:]]}
    if group:
        c["story_group"] = group
    return c


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BigStoryMergeTests(unittest.TestCase):
    def test_story_group_joins_clusters_with_no_shared_url(self):
        out = _merge({
            "a": {"status": "ok", "clusters": [_c("Nvidia CEO exits", ["u1", "u2"], "s1", "Huang quit.")]},
            "b": {"status": "ok", "clusters": [_c("Huang steps down", ["u3", "u4"], "s1")]},
            "c": {"status": "ok", "clusters": [_c("Tata Motors loss", ["u5", "u6"], "s3")]},
        })
        self.assertEqual([o["label"] for o in out], ["Nvidia CEO exits", "Tata Motors loss"])
        self.assertEqual(out[0]["models"], 2)
        self.assertEqual(out[0]["summary"], "Huang quit.")

    def test_one_model_twice_on_a_story_counts_once(self):
        out = _merge({
            "a": {"status": "ok", "clusters": [_c("X one", ["u1", "u2"], "s1"),
                                               _c("X again", ["u9", "u8"], "s1")]},
            "b": {"status": "ok", "clusters": [_c("X two", ["u3", "u4"], "s1")]},
        })
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["models"], 2)

    def test_shared_roundup_video_does_not_fuse_different_stories(self):
        # 14 Nov 2026: "Global Lens | Microsoft Outage, Huang Summoned…" sat in both a
        # Nvidia and a Microsoft cluster and swallowed the Microsoft story.
        roundup = "https://youtube.com/watch?v=roundup"
        out = _merge({
            "a": {"status": "ok", "clusters": [_c("Nvidia CEO exits", ["n1", roundup], "s1"),
                                               _c("Microsoft outage", ["m1", "m2"], "s2")]},
            "b": {"status": "ok", "clusters": [_c("Huang resigns", ["n2", "n3"], "s1"),
                                               _c("Global outage", ["m3", roundup], "s2")]},
        })
        self.assertEqual([(o["label"], o["models"]) for o in out],
                         [("Nvidia CEO exits", 2), ("Microsoft outage", 2)])

    def test_old_files_bridge_cluster_folds_two_entries(self):
        # No story_group (files from before Nov 2026): c overlaps both a and b.
        out = _merge({
            "a": {"status": "ok", "clusters": [_c("X one", ["u1", "u2"])]},
            "b": {"status": "ok", "clusters": [_c("X two", ["u3", "u4"])]},
            "c": {"status": "ok", "clusters": [_c("X three", ["u1", "u3"])]},
        })
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["models"], 3)

    def test_without_groups_url_overlap_still_merges(self):
        out = _merge({
            "a": {"status": "ok", "clusters": [_c("A", ["u1", "u2"])]},
            "b": {"status": "ok", "clusters": [_c("B", ["u2", "u3"]), _c("C", ["u7", "u8"])]},
        })
        self.assertEqual([(o["label"], o["models"]) for o in out], [("A", 2), ("C", 1)])


class PageCodeVersionTests(unittest.TestCase):
    """Cloudflare keeps .js/.css in browsers for 4 hours; the data is never cached.
    The page must link app.js/style.css by content hash so code and data match."""

    def test_asset_url_changes_with_the_file(self):
        import sys
        sys.path.insert(0, ROOT)
        from aggregator import asset_url
        url = asset_url("templates/app.js")
        self.assertRegex(url, r"^templates/app\.js\?v=[0-9a-f]{10}$")
        self.assertEqual(asset_url("no/such/file.js"), "no/such/file.js")

    def test_page_links_assets_by_version(self):
        with open(os.path.join(ROOT, "aggregator.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("src=\"{asset_url('templates/app.js')}\"", src)
        self.assertIn("href=\"{asset_url('templates/style.css')}\"", src)
        self.assertNotIn('src="templates/app.js"', src)


if __name__ == "__main__":
    unittest.main()
