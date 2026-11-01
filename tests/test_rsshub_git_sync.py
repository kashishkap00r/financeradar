"""Tests for rsshub_local_fetch.sync_cache_to_github — the hourly Twitter push.

Each test builds a throwaway bare "GitHub" repo plus two clones: `local`
(the laptop running the timer) and `actions` (stands in for GitHub Actions
pushing generated files). This recreates the 26 Oct 2026 failure, where a
conflict on static/news_cache.json left the laptop stuck mid-merge for a week.
"""

import os
import subprocess
import tempfile
import unittest

from rsshub_local_fetch import sync_cache_to_github

CACHE_REL = "static/rsshub_twitter_cache.json"


def git(repo, *args, check=True):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=check
    ).stdout.strip()


def write(repo, rel, text):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def read_remote(repo, rel):
    git(repo, "fetch", "-q", "origin")
    return git(repo, "show", f"origin/main:{rel}")


class SyncCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.remote = os.path.join(root, "remote.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.remote], check=True)

        self.local = os.path.join(root, "local")
        self.actions = os.path.join(root, "actions")
        for clone in (self.local, self.actions):
            subprocess.run(["git", "clone", "-q", self.remote, clone], check=True, capture_output=True)
            git(clone, "config", "user.email", "test@example.com")
            git(clone, "config", "user.name", "Test")
            git(clone, "checkout", "-q", "-B", "main")

        for rel, text in {
            CACHE_REL: "tweets v0\n",
            "static/news_cache.json": "news v0\n",
            "index.html": "<html>v0</html>\n",
            "feeds.py": "FEEDS = 0\n",
        }.items():
            write(self.local, rel, text)
        git(self.local, "add", "-A")
        git(self.local, "commit", "-q", "-m", "init")
        git(self.local, "push", "-q", "-u", "origin", "main")
        git(self.actions, "pull", "-q", "origin", "main")
        git(self.actions, "branch", "-q", "--set-upstream-to=origin/main", "main")

        self.cache = os.path.join(self.local, CACHE_REL)

    def tearDown(self):
        self.tmp.cleanup()

    def actions_push(self, rel, text):
        write(self.actions, rel, text)
        git(self.actions, "add", rel)
        git(self.actions, "commit", "-q", "-m", f"actions: {rel}")
        git(self.actions, "push", "-q", "origin", "main")

    def sync(self):
        return sync_cache_to_github(
            self.local, self.cache, "chore: update RSSHub twitter cache",
            lock_path=os.path.join(self.tmp.name, "git.lock"), lock_wait=0,
        )

    def assert_not_mid_merge(self):
        self.assertFalse(os.path.exists(os.path.join(self.local, ".git", "MERGE_HEAD")))

    def test_plain_push(self):
        write(self.local, CACHE_REL, "tweets v1\n")
        self.assertTrue(self.sync())
        self.assertEqual(read_remote(self.local, CACHE_REL), "tweets v1")

    def test_generated_file_conflict_takes_github_copy(self):
        # Both sides edit news_cache.json — exactly what broke on 26 Oct.
        self.actions_push("static/news_cache.json", "news from actions\n")
        write(self.local, "static/news_cache.json", "news local\n")
        git(self.local, "add", "static/news_cache.json")
        git(self.local, "commit", "-q", "-m", "local generated edit")
        write(self.local, CACHE_REL, "tweets v1\n")

        self.assertTrue(self.sync())
        self.assert_not_mid_merge()
        self.assertEqual(read_remote(self.local, CACHE_REL), "tweets v1")
        self.assertEqual(read_remote(self.local, "static/news_cache.json"), "news from actions")

    def test_twitter_cache_conflict_keeps_fresh_local_copy(self):
        self.actions_push(CACHE_REL, "tweets from somewhere else\n")
        write(self.local, CACHE_REL, "tweets fresh\n")

        self.assertTrue(self.sync())
        self.assert_not_mid_merge()
        self.assertEqual(read_remote(self.local, CACHE_REL), "tweets fresh")

    def test_other_staged_work_is_not_swept_into_commit(self):
        write(self.local, "feeds.py", "FEEDS = 'unfinished work'\n")
        git(self.local, "add", "feeds.py")
        write(self.local, CACHE_REL, "tweets v1\n")

        self.assertTrue(self.sync())
        self.assertEqual(read_remote(self.local, "feeds.py"), "FEEDS = 0")
        # ...and the unfinished work is still waiting locally, untouched.
        self.assertIn("feeds.py", git(self.local, "diff", "--cached", "--name-only"))

    def test_recovers_repo_already_stuck_mid_merge(self):
        self.actions_push("static/news_cache.json", "news from actions\n")
        write(self.local, "static/news_cache.json", "news local\n")
        git(self.local, "commit", "-q", "-am", "local generated edit")
        git(self.local, "pull", "-q", "--no-rebase", "--no-edit", "origin", "main", check=False)
        self.assertTrue(os.path.exists(os.path.join(self.local, ".git", "MERGE_HEAD")))

        write(self.local, CACHE_REL, "tweets v1\n")
        self.assertTrue(self.sync())
        self.assert_not_mid_merge()
        self.assertEqual(read_remote(self.local, CACHE_REL), "tweets v1")

    def test_source_conflict_aborts_instead_of_getting_stuck(self):
        self.actions_push("feeds.py", "FEEDS = 'remote'\n")
        write(self.local, "feeds.py", "FEEDS = 'local'\n")
        git(self.local, "commit", "-q", "-am", "local source edit")
        write(self.local, CACHE_REL, "tweets v1\n")

        self.assertFalse(self.sync())
        self.assert_not_mid_merge()
        self.assertEqual(git(self.local, "diff", "--name-only", "--diff-filter=U"), "")


if __name__ == "__main__":
    unittest.main()
