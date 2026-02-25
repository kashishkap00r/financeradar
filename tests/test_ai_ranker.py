"""Tests for AI ranker utility functions."""

import sys
import os
import json
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_ranker import parse_json_response, sanitize_headline


class TestParseJsonResponse(unittest.TestCase):
    """Tests for parse_json_response()."""

    def test_valid_json_array(self):
        result = parse_json_response('[{"rank": 1}]')
        self.assertEqual(result, [{"rank": 1}])

    def test_json_in_markdown_code_block(self):
        text = '```json\n[{"rank": 1}]\n```'
        result = parse_json_response(text)
        self.assertEqual(result, [{"rank": 1}])

    def test_json_in_bare_code_block(self):
        text = '```\n[{"rank": 1}]\n```'
        result = parse_json_response(text)
        self.assertEqual(result, [{"rank": 1}])

    def test_trailing_comma_cleaned(self):
        text = '[{"rank": 1},]'
        result = parse_json_response(text)
        self.assertEqual(result, [{"rank": 1}])

    def test_trailing_comma_in_object(self):
        text = '[{"rank": 1, "title": "test",}]'
        result = parse_json_response(text)
        self.assertEqual(result, [{"rank": 1, "title": "test"}])

    def test_prefix_text_before_array(self):
        text = 'Here are the rankings:\n[{"rank": 1}]'
        result = parse_json_response(text)
        self.assertEqual(result, [{"rank": 1}])

    def test_empty_string_raises(self):
        with self.assertRaises((json.JSONDecodeError, ValueError)):
            parse_json_response("")

    def test_no_json_raises(self):
        with self.assertRaises((json.JSONDecodeError, ValueError)):
            parse_json_response("no json here at all")


class TestSanitizeHeadline(unittest.TestCase):
    """Tests for sanitize_headline()."""

    def test_double_quotes_replaced(self):
        result = sanitize_headline('He said "hello" to them')
        self.assertNotIn('"', result)
        self.assertIn("'", result)

    def test_newlines_replaced(self):
        result = sanitize_headline("Line one\nLine two\rLine three")
        self.assertNotIn("\n", result)
        self.assertNotIn("\r", result)

    def test_whitespace_stripped(self):
        result = sanitize_headline("  hello world  ")
        self.assertEqual(result, "hello world")

    def test_empty_string(self):
        result = sanitize_headline("")
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
