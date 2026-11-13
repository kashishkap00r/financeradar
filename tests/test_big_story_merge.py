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

    def test_bridge_cluster_folds_two_entries_and_counts_models_once(self):
        # a and b don't overlap; c shares a URL with a and the group of b.
        out = _merge({
            "a": {"status": "ok", "clusters": [_c("X one", ["u1", "u2"], "s1"),
                                               _c("X again", ["u9", "u8"], "s1")]},
            "b": {"status": "ok", "clusters": [_c("X two", ["u3", "u4"], "s2")]},
            "c": {"status": "ok", "clusters": [_c("X three", ["u1", "u5"], "s2")]},
        })
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["models"], 3)

    def test_without_groups_url_overlap_still_merges(self):
        out = _merge({
            "a": {"status": "ok", "clusters": [_c("A", ["u1", "u2"])]},
            "b": {"status": "ok", "clusters": [_c("B", ["u2", "u3"]), _c("C", ["u7", "u8"])]},
        })
        self.assertEqual([(o["label"], o["models"]) for o in out], [("A", 2), ("C", 1)])


if __name__ == "__main__":
    unittest.main()
