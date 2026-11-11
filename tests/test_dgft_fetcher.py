"""DGFT notifications scraper: the listing page is a server-rendered table."""

import unittest
from datetime import datetime

from articles import IST_TZ
from feeds import parse_dgft_table

PAGE = """
<table><tbody>
<tr> <td>1</td> <td>49/2026-27</td> <td>2026-27</td>
 <td>Amendment in Export Policy of Waste and Scrap of Primary Cells, Primary Batteries and Electric Accumulators (Lithium-Ion Battery Black Mass) under ITC (HS) 85491400 - regarding.</td>
 <td>10/11/2026</td> <td style="display:none">10/11/2026 21:32:54</td>
 <td> <a title="Download" class="attachmentBtn" href="https://content.dgft.gov.in/Website/dgftprod/58145d8f/Notification No. 49 of 2026-2027.pdf" target="_blank" download> Download</a> </td> </tr>
<tr> <td>2</td> <td>48</td> <td>2026-27</td>
 <td>Streamlining of Halal Certification Process for Meat and Meat Products- reg.</td>
 <td>09/11/2026</td> <td style="display:none">09/11/2026 18:05:00</td>
 <td> <a href="https://content.dgft.gov.in/Website/dgftprod/b798/Halal English Notification.pdf">Download</a> </td> </tr>
<tr> <td>3</td> <td>12/2026-27</td> <td>2026-27</td>
 <td>Something old &amp; settled</td>
 <td>01/06/2026</td> <td style="display:none">01/06/2026 10:00:00</td>
 <td> <a href="https://content.dgft.gov.in/x/old.pdf">Download</a> </td> </tr>
</tbody></table>
"""

CFG = {"id": "dgft-notifications", "name": "DGFT — Notifications", "url": "https://www.dgft.gov.in/CP/?opt=notification",
       "category": "News", "publisher": "DGFT", "source_tier": "official"}


class DgftTests(unittest.TestCase):
    def setUp(self):
        self.items = parse_dgft_table(PAGE, CFG, now=datetime(2026, 11, 12, 9, 0, tzinfo=IST_TZ))

    def test_rows_inside_the_window(self):
        self.assertEqual(len(self.items), 2)

    def test_title_drops_regarding_tail(self):
        self.assertEqual(self.items[0]["title"],
                         "Amendment in Export Policy of Waste and Scrap of Primary Cells, Primary Batteries and "
                         "Electric Accumulators (Lithium-Ion Battery Black Mass) under ITC (HS) 85491400")
        self.assertEqual(self.items[1]["title"], "Streamlining of Halal Certification Process for Meat and Meat Products")

    def test_date_uses_the_hidden_timestamp(self):
        self.assertEqual(self.items[0]["date"], datetime(2026, 11, 10, 21, 32, 54, tzinfo=IST_TZ))

    def test_pdf_link_is_url_encoded(self):
        self.assertEqual(self.items[0]["link"],
                         "https://content.dgft.gov.in/Website/dgftprod/58145d8f/Notification%20No.%2049%20of%202026-2027.pdf")

    def test_official_fields(self):
        it = self.items[0]
        self.assertEqual((it["publisher"], it["source_tier"], it["category"]), ("DGFT", "official", "News"))
        self.assertEqual(it["description"], "DGFT 49/2026-27")


if __name__ == "__main__":
    unittest.main()
