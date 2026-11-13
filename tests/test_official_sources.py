"""Official sources without RSS (official_sources.py): one parser per regulator,
each keeping the policy signal and dropping procedure and noise."""

import unittest
from datetime import datetime

import official_sources as osrc
from articles import IST_TZ

DGTR_PAGE = """
<div class="view-display-id-block_5">
<div class="notifi_list_inner"> <span> 09 Nov 2026 </span> <span> <a href="/en/node/1839?blink=9401#9401">Suo-moto anti-dumping investigation concerning imports of "Aluminium Extrusions" originating in or exported from China PR, Malaysia</a> <p>Initiation Notification</p> <div class="file-details"><div class="file-details__link"><a href="/sites/a b.pdf">pdf</a></div></div>
</div>
<div class="view-display-id-block_6"> <div class="notifi_list_inner"> <span> 06 Nov 2026 - 3:30 PM </span> oral </div>
<div class="view-display-id-block_7">
<div class="notifi_list_inner"> <span> 04 Nov 2026 </span> <span> <a href="/en/node/1769?blink=9385#9385">Safeguard investigation concerning imports of Soda Ash into India</a> <p>Final Finding</p> <div class="file-details"></div>
<div class="notifi_list_inner"> <span> 23 Oct 2026 </span> <span> <a href="/en/node/1700?blink=9300#9300">Sunset review of anti-dumping duty on imports of Seamless Tubes originating in China PR</a> <p>SSR_Final Findings</p> <div class="file-details"></div>
<div class="notifi_list_inner"> <span> 22 Oct 2026 </span> <span> <a href="/en/node/1701?blink=9299#9299">Imports of Copper Tubes from Vietnam</a> <p>Extension of time for questionnaire</p> <div class="file-details"></div>
</div>
<div class="view-display-id-block_8"> <div class="notifi_list_inner"> <span> 11 Nov 2026 </span> others </div>
"""

CBIC_ITEMS = [
    {"id": 1010800, "notificationNo": "26/2026-Customs (ADD)", "notificationDt": "2026-10-24T05:30:00+05:30",
     "notificationName": "Seeks to impose Anti Dumping Duty on imports of 'Titanium Dioxide' from China PR."},
    {"id": 1010801, "notificationNo": "25/2026-Customs (ADD)", "notificationDt": "2026-10-24T05:30:00+05:30",
     "notificationName": "Seeks to rescind notification No. 12/2025-Customs (ADD)"},
    {"id": 1010802, "notificationNo": "Corrigendum", "notificationDt": "2026-10-25T05:30:00+05:30",
     "notificationName": "Corrigendum to notification 24/2026"},
    {"id": 1010803, "notificationNo": None, "notificationDt": None, "notificationName": None},
]

IRDAI_PAGE = """
<table><tr><th>x</th></tr>
<tr><td class="table-col-shortDesc">आईआरडीएआई / Press Release - Order in the matter of Canara HSBC Life Insurance.pdf</td>
<td><a href="/document-detail?documentId=7001">v</a></td><td class="table-col-lastUpdated"> 10-09-2026 </td></tr>
<tr><td class="table-col-shortDesc">IRDAI organizes Workshop on Aadhaar Authentication</td>
<td><a href="/document-detail?documentId=7002">v</a></td><td class="table-col-lastUpdated">02-11-2026</td></tr>
</table>"""

PFRDA_PAGE = """
<div class="basic-card"> <a href="/w/press-release-star-nps?p_l_back_url=%2Fsearch"> <h2 class="basic-title">PRESS Release - StAR NPS: Taking NPS Distribution Across Every Socioeconomic Stratum</h2>
<p><strong>Issue Date:</strong> 28-10-2026</p></a></div>
<div class="basic-card"> <a href="/w/advisory-tid"> <h2 class="basic-title">Advisory on mandatory capture of TID</h2>
<p><strong>Issue Date:</strong> 14-09-2026</p></a></div>"""

IFSCA_PAGE = """
<tr><td data-label="Date"><span style="display:none;">20261106</span> 06/11/2026</td>
<td class="x" data-label="Type">Press Release</td><td class="y" data-label="Title"> <a target="_blank" href="/CommonDirect/GetFileView?id=Z3 1qGE6eA=&amp;fileName=a.pdf">IFSCA notifies leasing of GPUs as a financial product</a></td></tr>
<tr><td data-label="Date"><span style="display:none;">20261030</span> 30/10/2026</td>
<td class="x" data-label="Type">Tender</td><td class="y" data-label="Title"> <a href="/t.pdf">Civil Works at IFSCA Building</a></td></tr>
<tr><td data-label="Date"><span style="display:none;">20261104</span> 04/11/2026</td>
<td class="x" data-label="Type">Notification</td><td class="y" data-label="Title"> <a href="/n.pdf">Notification regarding Central Tax rates</a></td></tr>"""

CCI_DATA = {"data": [
    {"id": "719", "order_date": "10/11/2026",
     "title": '<span class="blue">Commission approves acquisition of  certain shareholding of Yatharth Hospital &amp; Trauma Care</span>'},
    {"id": "700", "order_date": "08/08/2026", "title": "CCI hosted the BRICS Competition Conference"},
]}

MCA_DATA = {"data": [
    {"shortDescription": "General Circular No.06/2026-Relaxation of additional fee for filing CRA-4.",
     "UploadDate": "10/30/2026 18:05:00", "link": "12345", "docGroup": "The Companies Act, 2013"},
    {"shortDescription": "S.O. 600(E)-Delegation of powers to Regional Director",
     "UploadDate": "10/29/2026 10:00:00", "link": "12346", "docGroup": "The Companies Act, 2013"},
]}


RBI_BULLETIN_PAGE = """<table class="tablebg" width="100%"><tr><td align="Left" class="tableheader" colspan="4" nowrap><b>Date &nbsp;:&nbsp;Oct 23, 2026</b></td></tr><tr><td style='word-wrap:break-word;width:450;'>Reserve Bank of India Bulletin - October 2026</td><td nowrap>&nbsp;</td><td  nowrap><a id='APDF_0B' target='_blank' href='https://rbidocs.rbi.org.in/rdocs/Bulletin/PDFs/0BULLETIN25102026AB.PDF'><img alt='PDF'></a></td></tr>
<tr><td style='word-wrap:break-word;width:450;'><a class='link2' href=BS_ViewBulletin.aspx?Id=24508>Contents</a></td></tr>
<tr><td align="Left" class="tableheader" colspan="4" nowrap><b>Speeches</b></td></tr><tr><td style='word-wrap:break-word;width:450;'><a class='link2' href=BS_ViewBulletin.aspx?Id=24514>Preserving Financial Stability - Shri Sanjay Malhotra</a></td></tr>
<tr><td align="Left" class="tableheader" colspan="4" nowrap><b>Article</b></td></tr><tr><td style='word-wrap:break-word;width:450;'><a class='link2' href=BS_ViewBulletin.aspx?Id=24516>State of the Economy</a></td></tr>
<tr><td style='word-wrap:break-word;width:450;'><a class='link2' href=BS_ViewBulletin.aspx?Id=24518>Performance of the NBFC Sector: Review for 2025</a></td></tr>
<tr><td align="Left" class="tableheader" colspan="4" nowrap><b>Current Statistics General</b></td></tr><tr><td style='word-wrap:break-word;width:450;'><a class='link2' href=BS_ViewBulletin.aspx?Id=24520>1. Select Economic Indicators</a></td></tr></table>"""


class ParserTests(unittest.TestCase):

    def test_rbi_bulletin_keeps_issue_and_articles_only(self):
        rows = osrc.parse_rbi_bulletin(RBI_BULLETIN_PAGE)
        self.assertEqual([r[0] for r in rows], [
            "RBI Bulletin – October 2026",
            "RBI Bulletin: State of the Economy",
            "RBI Bulletin: Performance of the NBFC Sector: Review for 2025",
        ])
        self.assertTrue(rows[0][1].endswith("0BULLETIN25102026AB.PDF"))
        self.assertEqual(rows[1][1], "https://www.rbi.org.in/Scripts/BS_ViewBulletin.aspx?Id=24516")
        self.assertTrue(all(r[2] == datetime(2026, 10, 23, tzinfo=IST_TZ) for r in rows))

    def test_rbi_bulletin_without_date_header_returns_nothing(self):
        self.assertEqual(osrc.parse_rbi_bulletin("<html>maintenance</html>"), [])

    def test_dgtr_keeps_initiations_and_findings_only(self):
        rows = osrc.parse_dgtr(DGTR_PAGE)
        titles = [r[0] for r in rows]
        self.assertEqual(titles, [
            "Initiation Notification: Aluminium Extrusions from China PR, Malaysia",
            "Final Finding: Soda Ash",
            "Sunset review Final Findings: Seamless Tubes from China PR",
        ])
        self.assertEqual(rows[0][1], "https://www.dgtr.gov.in/en/node/1839?blink=9401#9401")
        self.assertEqual(rows[0][2], datetime(2026, 11, 9, tzinfo=IST_TZ))

    def test_cbic_drops_rescinds_and_corrigenda(self):
        rows = osrc.parse_cbic(CBIC_ITEMS)
        self.assertEqual(len(rows), 1)
        title, link, dt, desc = rows[0]
        self.assertEqual(title, "Impose Anti Dumping Duty on imports of 'Titanium Dioxide' from China PR")
        self.assertEqual(link, "https://taxinformation.cbic.gov.in/view-pdf/1010800/ENG/Notifications")
        self.assertEqual(desc, "Customs notification 26/2026-Customs (ADD)")
        self.assertEqual(dt, datetime(2026, 10, 24, tzinfo=IST_TZ))

    def test_irdai_english_half_and_noise(self):
        rows = osrc.parse_irdai(IRDAI_PAGE, "press-releases")
        self.assertEqual([r[0] for r in rows], ["Order in the matter of Canara HSBC Life Insurance"])
        self.assertEqual(rows[0][1], "https://irdai.gov.in/document-detail?documentId=7001")

    def test_pfrda_strips_prefix_and_drops_advisories(self):
        rows = osrc.parse_pfrda(PFRDA_PAGE, "regulatory-framework/circulars/active-circulars")
        self.assertEqual([r[0] for r in rows], ["StAR NPS: Taking NPS Distribution Across Every Socioeconomic Stratum"])
        self.assertEqual(rows[0][1], "https://www.pfrda.org.in/w/press-release-star-nps")

    def test_ifsca_types_and_link_fix(self):
        rows = osrc.parse_ifsca(IFSCA_PAGE)
        self.assertEqual([r[0] for r in rows], ["IFSCA notifies leasing of GPUs as a financial product"])
        self.assertEqual(rows[0][1], "https://ifsca.gov.in/CommonDirect/GetFileView?id=Z3%2B1qGE6eA=&fileName=a.pdf")

    def test_cci_cleans_titles_and_drops_events(self):
        rows = osrc.parse_cci(CCI_DATA)
        self.assertEqual([r[0] for r in rows],
                         ["Commission approves acquisition of certain shareholding of Yatharth Hospital & Trauma Care"])

    def test_mca_uses_upload_time_and_drops_admin(self):
        rows = osrc.parse_mca(MCA_DATA, "Notifications")
        self.assertEqual([r[0] for r in rows], ["General Circular No.06/2026-Relaxation of additional fee for filing CRA-4"])
        self.assertEqual(rows[0][2], datetime(2026, 10, 30, 18, 5, tzinfo=IST_TZ))
        self.assertIn("doc=MTIzNDU%3D", rows[0][1])


class FetchOfficialTests(unittest.TestCase):
    def test_window_dedupe_and_article_shape(self):
        now = datetime(2026, 11, 12, 9, 0, tzinfo=IST_TZ)
        rows = [
            ("New rule", "https://x/1", datetime(2026, 11, 10, tzinfo=IST_TZ), "d"),
            ("Same link again", "https://x/1", datetime(2026, 11, 10, tzinfo=IST_TZ), ""),
            ("Too old", "https://x/2", datetime(2026, 9, 1, tzinfo=IST_TZ), ""),
        ]
        osrc.SOURCES["_test"] = (lambda cfg: rows, lambda t: True)
        try:
            cfg = {"id": "t", "name": "T — Test", "feed": "official:_test", "publisher": "T", "url": "https://x"}
            got = osrc.fetch_official(cfg, now=now)
        finally:
            del osrc.SOURCES["_test"]
        self.assertEqual([a["title"] for a in got], ["New rule"])
        self.assertEqual((got[0]["source_tier"], got[0]["category"], got[0]["publisher"]), ("official", "News", "T"))

    def test_failing_source_returns_nothing(self):
        def boom(cfg):
            raise RuntimeError("site down")
        osrc.SOURCES["_boom"] = (boom, lambda t: True)
        try:
            self.assertEqual(osrc.fetch_official({"id": "b", "name": "B", "feed": "official:_boom"}), [])
        finally:
            del osrc.SOURCES["_boom"]


if __name__ == "__main__":
    unittest.main()


class ProxyFallbackTests(unittest.TestCase):
    def test_blocked_site_goes_through_the_relay(self):
        import os
        import urllib.error
        from unittest.mock import patch
        blocked = urllib.error.HTTPError("https://www.dgft.gov.in/x", 403, "Forbidden", {}, None)
        with patch.dict(os.environ, {"RSS_PROXY_URL": "https://relay.example/"}), \
                patch.object(osrc, "http_get", side_effect=blocked), \
                patch.object(osrc, "via_proxy", return_value="<html>ok</html>") as relay:
            self.assertEqual(osrc.get_or_proxy("https://www.dgft.gov.in/x"), "<html>ok</html>")
            relay.assert_called_once()

    def test_no_relay_configured_raises(self):
        import os
        import urllib.error
        from unittest.mock import patch
        blocked = urllib.error.HTTPError("https://x", 403, "Forbidden", {}, None)
        with patch.dict(os.environ, {"RSS_PROXY_URL": ""}), patch.object(osrc, "http_get", side_effect=blocked):
            with self.assertRaises(urllib.error.HTTPError):
                osrc.get_or_proxy("https://x")
