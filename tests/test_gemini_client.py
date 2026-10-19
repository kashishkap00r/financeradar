import io
import json
import unittest
import urllib.error
from unittest.mock import patch

import gemini_client


def http_error(code, body=""):
    return urllib.error.HTTPError("https://example.test", code, "err", {}, io.BytesIO(body.encode()))


class GeminiClientTest(unittest.TestCase):
    def setUp(self):
        gemini_client._skipped_models.clear()
        gemini_client._listed_models = None
        gemini_client._listed_loaded = True  # no network: chains used as-is
        patcher_env = patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
        patcher_sleep = patch("gemini_client.time.sleep")
        patcher_env.start()
        self.sleep = patcher_sleep.start()
        self.addCleanup(patcher_env.stop)
        self.addCleanup(patcher_sleep.stop)

    def run_with(self, responses, chain=("model-a", "model-b"), parse=json.loads):
        """responses: list of str (reply text) or Exception, consumed in order."""
        calls = []

        def fake(prompt, model_id, timeout, thinking):
            calls.append((model_id, thinking))
            item = responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        with patch("gemini_client._generate_once", side_effect=fake):
            result = gemini_client.generate_json("p", list(chain), parse=parse)
        return result, calls

    def test_first_model_success(self):
        (result, model), calls = self.run_with(['[1]'])
        self.assertEqual((result, model), ([1], "model-a"))
        self.assertEqual(len(calls), 1)

    def test_retries_transient_error_on_same_model(self):
        (_, model), calls = self.run_with([http_error(503), '[1]'])
        self.assertEqual(model, "model-a")
        self.assertEqual([c[0] for c in calls], ["model-a", "model-a"])

    def test_404_falls_back_and_skips_model_for_rest_of_run(self):
        (_, model), _ = self.run_with([http_error(404), '[1]'])
        self.assertEqual(model, "model-b")
        (_, model), calls = self.run_with(['[2]'])
        self.assertEqual(model, "model-b")
        self.assertEqual([c[0] for c in calls], ["model-b"])

    def test_long_retry_delay_moves_to_next_model(self):
        body = json.dumps({"error": {"details": [{"retryDelay": "3600s"}]}})
        (_, model), calls = self.run_with([http_error(429, body), '[1]'])
        self.assertEqual(model, "model-b")
        self.assertIn("model-a", gemini_client._skipped_models)

    def test_timeout_moves_straight_to_next_model(self):
        timeout = urllib.error.URLError(TimeoutError("timed out"))
        (_, model), calls = self.run_with([timeout, '[1]'])
        self.assertEqual(model, "model-b")
        self.assertEqual([c[0] for c in calls], ["model-a", "model-b"])
        self.sleep.assert_not_called()

    def test_unparseable_output_is_retried(self):
        (result, _), calls = self.run_with(['not json', '[1]'])
        self.assertEqual(result, [1])
        self.assertEqual(len(calls), 2)

    def test_400_with_thinking_retries_without_it(self):
        (_, model), calls = self.run_with([http_error(400), '[1]'], chain=["gemini-2.5-flash"])
        self.assertEqual(model, "gemini-2.5-flash")
        self.assertEqual(calls[0][1], {"thinkingBudget": 0})
        self.assertIsNone(calls[1][1])

    def test_all_models_fail_raises(self):
        with self.assertRaises(RuntimeError):
            self.run_with([http_error(403), http_error(403)])

    def test_missing_key_raises(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            with self.assertRaises(RuntimeError):
                gemini_client.generate_json("p", ["m"], parse=json.loads)


class ResolveChainTest(unittest.TestCase):
    def setUp(self):
        gemini_client._skipped_models.clear()
        gemini_client._listed_loaded = True

    def test_unlisted_models_go_last_and_newest_flash_appended(self):
        gemini_client._listed_models = {
            "gemini-2.5-flash", "gemini-3-flash-preview", "gemini-3.5-flash",
            "gemini-2.5-flash-lite", "gemini-2.5-flash-image", "text-embedding-004",
        }
        chain = gemini_client.resolve_chain(["gemini-3-flash", "gemini-2.5-flash"])
        self.assertEqual(chain, ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-3-flash-preview", "gemini-3-flash"])

    def test_listing_unavailable_keeps_chain(self):
        gemini_client._listed_models = None
        self.assertEqual(gemini_client.resolve_chain(["a", "b", "a"]), ["a", "b"])


class HelpersTest(unittest.TestCase):
    def test_pretty_model_name(self):
        self.assertEqual(gemini_client.pretty_model_name("gemini-2.5-flash-lite"), "Gemini 2.5 Flash-Lite")
        self.assertEqual(gemini_client.pretty_model_name("gemini-3-flash-preview"), "Gemini 3 Flash Preview")

    def test_thinking_config(self):
        self.assertEqual(gemini_client.thinking_config("gemini-2.5-flash"), {"thinkingBudget": 0})
        self.assertIsNone(gemini_client.thinking_config("gemini-2.5-flash-lite"))
        self.assertEqual(gemini_client.thinking_config("gemini-3-flash-preview"), {"thinkingLevel": "low"})
        self.assertIsNone(gemini_client.thinking_config("gemini-flash-latest"))

    def test_sanitize_error_redacts_key(self):
        self.assertNotIn("AIzaSy", gemini_client.sanitize_error("bad key AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ"))


if __name__ == "__main__":
    unittest.main()
