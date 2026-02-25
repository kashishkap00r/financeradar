"""Tests for TelegramHTMLParser from telegram_fetcher.py."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from telegram_fetcher import TelegramHTMLParser


SAMPLE_HTML = """
<div class="tgme_widget_message_wrap js-widget_message_wrap">
  <div class="tgme_widget_message js-widget_message tgme_widget_message " data-post="TestChannel/123">
    <div class="tgme_widget_message_user">
      <a href="https://t.me/TestChannel">
        <img src="avatar.jpg">
      </a>
    </div>
    <div class="tgme_widget_message_bubble">
      <a class="tgme_widget_message_owner_name" href="https://t.me/TestChannel">
        Test Channel Name
      </a>
      <div class="tgme_widget_message_text js-message_text">
        This is a sample report message with important content.
      </div>
      <div class="tgme_widget_message_document_wrap">
        <div class="tgme_widget_message_document">
          <div class="tgme_widget_message_document_title" dir="auto">
            Research_Report_Feb2026.pdf
          </div>
          <div class="tgme_widget_message_document_extra">
            1.2 MB
          </div>
        </div>
      </div>
      <div class="tgme_widget_message_info">
        <span class="tgme_widget_message_views">4.2K</span>
        <a class="tgme_widget_message_date" href="https://t.me/TestChannel/123">
          <time datetime="2026-02-23T10:30:00+00:00"></time>
        </a>
      </div>
    </div>
  </div>
</div>
"""


class TestTelegramHTMLParser(unittest.TestCase):
    """Tests for TelegramHTMLParser."""

    def setUp(self):
        self.parser = TelegramHTMLParser()
        self.parser.feed(SAMPLE_HTML)
        self.parser.close()

    def test_extracts_one_message(self):
        self.assertEqual(len(self.parser.messages), 1)

    def test_extracts_text(self):
        msg = self.parser.messages[0]
        self.assertIn("sample report message", msg["text"])

    def test_extracts_date(self):
        msg = self.parser.messages[0]
        self.assertEqual(msg["date"], "2026-02-23T10:30:00+00:00")

    def test_extracts_url(self):
        msg = self.parser.messages[0]
        self.assertEqual(msg["url"], "https://t.me/TestChannel/123")

    def test_extracts_channel(self):
        msg = self.parser.messages[0]
        self.assertEqual(msg["channel"], "Test Channel Name")

    def test_extracts_document(self):
        msg = self.parser.messages[0]
        self.assertEqual(len(msg["documents"]), 1)
        doc = msg["documents"][0]
        self.assertIn("Research_Report", doc["title"])
        self.assertIn("1.2 MB", doc["size"])

    def test_extracts_views(self):
        msg = self.parser.messages[0]
        self.assertEqual(msg["views"], "4.2K")

    def test_empty_html(self):
        parser = TelegramHTMLParser()
        parser.feed("")
        parser.close()
        self.assertEqual(parser.messages, [])

    def test_html_without_messages(self):
        parser = TelegramHTMLParser()
        parser.feed("<html><body><p>No messages here</p></body></html>")
        parser.close()
        self.assertEqual(parser.messages, [])


if __name__ == "__main__":
    unittest.main()
