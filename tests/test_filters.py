"""Tests for content filtering in filters.py."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from filters import should_filter_article, should_filter_video, should_filter_political


class TestShouldFilterArticle(unittest.TestCase):
    """Tests for should_filter_article()."""

    def test_filters_quarterly_results(self):
        article = {"title": "Stock XYZ: Q3 Results Today Live", "link": ""}
        self.assertTrue(should_filter_article(article))

    def test_filters_penny_stocks(self):
        article = {"title": "Top 5 penny stocks to buy this week", "link": ""}
        self.assertTrue(should_filter_article(article))

    def test_filters_sensex_movement(self):
        article = {"title": "Sensex surges 500 points amid rally", "link": ""}
        self.assertTrue(should_filter_article(article))

    def test_filters_stock_tips(self):
        article = {"title": "Buy or sell: best intraday tips for today", "link": ""}
        self.assertTrue(should_filter_article(article))

    def test_filters_stock_to_buy_phrase(self):
        article = {"title": "Stock to buy today: analysts pick one winner", "link": ""}
        self.assertTrue(should_filter_article(article))

    def test_filters_top_stock_picks_today_permutations(self):
        article = {"title": "Today top stock picks for short term momentum", "link": ""}
        self.assertTrue(should_filter_article(article))

    def test_passes_legitimate_policy_article(self):
        article = {
            "title": "RBI announces new monetary policy framework",
            "link": "https://example.com/rbi-policy",
        }
        self.assertFalse(should_filter_article(article))

    def test_passes_economic_analysis(self):
        article = {
            "title": "India GDP growth slows to 6.1% in Q3 on weak manufacturing",
            "link": "https://example.com/gdp",
        }
        self.assertFalse(should_filter_article(article))

    def test_filters_url_pattern_press_release(self):
        article = {
            "title": "Some company announcement",
            "link": "https://example.com/pr-release/12345",
        }
        self.assertTrue(should_filter_article(article))

    def test_filters_url_pattern_personal_finance(self):
        article = {
            "title": "How to save more money",
            "link": "https://example.com/personal-finance/savings-tips",
        }
        self.assertTrue(should_filter_article(article))

    def test_empty_title_does_not_crash(self):
        article = {"title": "", "link": ""}
        # Should not raise; result can be True or False
        result = should_filter_article(article)
        self.assertIsInstance(result, bool)

    def test_missing_title_key_does_not_crash(self):
        article = {"link": ""}
        result = should_filter_article(article)
        self.assertIsInstance(result, bool)

    def test_missing_link_key_does_not_crash(self):
        article = {"title": "Some title"}
        result = should_filter_article(article)
        self.assertIsInstance(result, bool)


class TestPoliticalKeywordFiltering(unittest.TestCase):
    """Tests for explicit political keyword blocking."""

    def test_filters_modi_name_variants(self):
        blocked_titles = [
            "PM Modi speaks at business summit",
            "Narendra Modi to visit state",
            "Prime Minister Modi gives address",
            "Narendra Damodardas Modi in parliament",
            "Modi government announces scheme",
            "Modi govt response to opposition",
            "Modi administration faces questions",
        ]
        for title in blocked_titles:
            self.assertTrue(should_filter_political({"title": title}))
            self.assertTrue(should_filter_article({"title": title, "link": "https://example.com"}))

    def test_filters_other_confirmed_political_names(self):
        blocked_titles = [
            "Amit Shah on policy rollout",
            "Rahul Gandhi comments on budget",
            "Arvind Kejriwal press conference",
            "Yogi Adityanath campaign update",
        ]
        for title in blocked_titles:
            self.assertTrue(should_filter_political({"title": title}))
            self.assertTrue(should_filter_article({"title": title, "link": "https://example.com"}))
            self.assertTrue(should_filter_video({"title": title}))

    def test_political_filter_does_not_overmatch_unrelated_titles(self):
        allowed_titles = [
            "RBI monetary policy committee update",
            "Corporate governance trends in Indian banks",
            "Commodity outlook for Q2",
        ]
        for title in allowed_titles:
            self.assertFalse(should_filter_political({"title": title}))


class TestOfficialSourceFiltering(unittest.TestCase):
    """Tests for official source blacklist+whitelist filtering."""

    def _official(self, title):
        return {"title": title, "link": "", "source_tier": "official"}

    def _media(self, title):
        return {"title": title, "link": ""}

    # --- Blacklist: always dropped ---
    def test_official_recovery_certificate_filtered(self):
        self.assertTrue(should_filter_article(self._official(
            "Completion of Recovery Certificate No. 123/2025")))

    def test_official_monetary_penalty_filtered(self):
        self.assertTrue(should_filter_article(self._official(
            "RBI imposes monetary penalty on ABC Bank")))

    def test_official_penalty_imposed_filtered(self):
        self.assertTrue(should_filter_article(self._official(
            "Penalty imposed on XYZ Co-operative Bank for non-compliance")))

    def test_official_weekly_supplement_filtered(self):
        self.assertTrue(should_filter_article(self._official(
            "Weekly Statistical Supplement")))

    def test_official_auction_result_filtered(self):
        self.assertTrue(should_filter_article(self._official(
            "Auction Result for Treasury Bills dated March 25")))

    def test_official_sebi_adjudication_filtered(self):
        self.assertTrue(should_filter_article(self._official(
            "Adjudication order in the matter of ABC Ltd")))

    def test_official_tender_filtered(self):
        self.assertTrue(should_filter_article(self._official(
            "Tender Invitation for IT Services")))

    # --- Whitelist: high-signal passes ---
    def test_official_rbi_rate_decision_passes(self):
        self.assertFalse(should_filter_article(self._official(
            "RBI keeps repo rate unchanged at 6.5%")))

    def test_official_mpc_decision_passes(self):
        self.assertFalse(should_filter_article(self._official(
            "Monetary Policy Committee decision: status quo on rates")))

    def test_official_sebi_new_norms_passes(self):
        self.assertFalse(should_filter_article(self._official(
            "SEBI issues new disclosure norms for AIFs")))

    def test_official_gdp_data_passes(self):
        self.assertFalse(should_filter_article(self._official(
            "India's GDP growth at 6.7% in Q3 FY26")))

    def test_official_cpi_inflation_passes(self):
        self.assertFalse(should_filter_article(self._official(
            "India's CPI inflation eases to 3.61% in February 2026")))

    def test_official_cabinet_approval_passes(self):
        self.assertFalse(should_filter_article(self._official(
            "Cabinet approves Production-Linked Incentive scheme for toys")))

    def test_official_governor_speech_passes(self):
        self.assertFalse(should_filter_article(self._official(
            "Governor's statement on developmental and regulatory policies")))

    def test_official_forex_reserves_passes(self):
        self.assertFalse(should_filter_article(self._official(
            "India's forex reserves rise to $640 billion")))

    def test_official_fpi_norms_passes(self):
        self.assertFalse(should_filter_article(self._official(
            "New FPI investment norms for debt markets")))

    def test_official_ecb_rate_passes(self):
        self.assertFalse(should_filter_article(self._official(
            "ECB cuts deposit facility rate to 2.50%")))

    # --- Whitelist miss: generic official content dropped ---
    def test_official_generic_notification_filtered(self):
        self.assertTrue(should_filter_article(self._official(
            "Notification regarding office timings")))

    def test_official_appointment_letter_filtered(self):
        self.assertTrue(should_filter_article(self._official(
            "Appointment of new deputy secretary")))

    # --- Media source unchanged by official filters ---
    def test_media_source_still_uses_blacklist(self):
        # This title matches media blacklist patterns
        self.assertTrue(should_filter_article(self._media(
            "Sensex closes at 75000, Nifty at 22500")))

    def test_media_source_not_affected_by_official_whitelist(self):
        # Normal media article should pass (not subject to whitelist)
        self.assertFalse(should_filter_article(self._media(
            "India's trade deficit narrows in February")))


class TestVideoFilterPatterns(unittest.TestCase):
    """Tests for title-only video filtering patterns."""

    def test_filters_top_stock_picks_today_video(self):
        video = {"title": "Top stock picks today | market opening strategy"}
        self.assertTrue(should_filter_video(video))


if __name__ == "__main__":
    unittest.main()
