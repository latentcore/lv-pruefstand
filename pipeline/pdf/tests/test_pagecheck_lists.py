"""Unit tests of pagecheck_lists.py on synthetic page words."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pagecheck_lists as pc  # noqa: E402

OZ_X, TEXT_X, QTY_X1, UNIT_X = 54.0, 125.0, 410.0, 415.0


def word(x0, y, text, x1=None):
    return (x0, y, x1 if x1 is not None else x0 + 5.0 * len(text), y + 9.0, text)


def head(oz="OZ"):
    return [word(420, 20, "[FIRMA_001]"), word(54, 60, "Projekt:"),
            word(OZ_X, 90, oz), word(TEXT_X, 90, "Leistungsbeschreibung"),
            word(380, 90, "Menge", QTY_X1), word(UNIT_X, 90, "ME"),
            word(450, 90, "Einheitspreis")]


def foot(page):
    return [word(55, 780, "Druckdatum:"), word(110, 780, "1.1.2026"),
            word(532, 780, "Seite:"), word(555, 780, str(page))]


def number(y, no, title="Titel"):
    return [word(OZ_X, y, no), word(TEXT_X, y, title)]


def quantity(y, amount, unit="m2"):
    out = [word(QTY_X1 - 30, y, amount, QTY_X1)]
    if unit is not None:
        out.append(word(UNIT_X, y, unit))
    out.append(word(450, y, "........................."))
    return out


def page(page_no, *parts, header=True):
    words = head() if header else []
    for p in parts:
        words += p
    return words + foot(page_no)


def rec(no, page_no, qty=None, unit=None, kind=None):
    return {"doc": "LV_99", "item_no": no, "page": page_no, "quantity": qty,
            "unit": unit, "kind": kind or ("normal" if qty is not None else "heading")}


def check(pages, records):
    return pc.check_document("LV_99", pc.read_document(pages), records, len(pages))


def differences(result):
    return [(d["page"], d["item_no"], d["difference"])
            for p in result["pages"] for d in p["differences"]]


PAGE1 = page(1, number(110, "1.1."), number(130, "1.1.10."),
             [word(TEXT_X, 145, "Langtext"), word(170, 145, "12,500")],
             quantity(160, "5,000"), number(200, "1.1.20."),
             quantity(230, "1.250,500", "St"))
RECORDS = [rec("1.1", 1), rec("1.1.10", 1, 5.0, "m2"),
           rec("1.1.20", 1, 1250.5, "St")]


class Reading(unittest.TestCase):
    def test_columns_come_from_the_header_row(self):
        c = pc.find_columns(PAGE1)
        self.assertEqual((c["oz_x0"], c["qty_x1"], c["unit_x0"]),
                         (OZ_X, QTY_X1, UNIT_X))
        self.assertIsNone(pc.find_columns(foot(1)))

    def test_items_numbers_and_quantities(self):
        shown = pc.read_document([PAGE1])
        self.assertEqual(
            [(i["item_no"], i["page"], i["quantity"], i["unit"]) for i in shown["items"]],
            [("1.1.10", 1, 5.0, "m2"), ("1.1.20", 1, 1250.5, "St")])
        self.assertEqual(shown["numbers"], [{"item_no": "1.1", "page": 1}])
        self.assertEqual(shown["loose_quantities"], [])

    def test_number_in_the_text_column_is_no_item(self):
        p = page(1, number(110, "1.1.10."),
                 [word(TEXT_X, 125, "1.1.20."), word(170, 125, "siehe")],
                 quantity(140, "5,000"))
        shown = pc.read_document([p])
        self.assertEqual([i["item_no"] for i in shown["items"]], ["1.1.10"])
        self.assertEqual(shown["numbers"], [])

    def test_number_alone_at_the_column_edge_is_text(self):
        p = page(1, number(110, "1.1.10."),
                 [word(TEXT_X, 125, "Breite"), word(QTY_X1 - 30, 125, "2,500", QTY_X1)],
                 quantity(140, "5,000"))
        shown = pc.read_document([p])
        self.assertEqual([(i["item_no"], i["quantity"]) for i in shown["items"]],
                         [("1.1.10", 5.0)])

    def test_words_below_the_footer_and_above_the_header_are_skipped(self):
        p = head() + [word(OZ_X, 40, "9.9.")] + number(110, "1.1.10.") \
            + quantity(140, "5,000") + foot(1) + [word(OZ_X, 800, "8.8.")]
        shown = pc.read_document([p])
        self.assertEqual([i["item_no"] for i in shown["items"]], ["1.1.10"])
        self.assertEqual(shown["numbers"], [])

    def test_summary_page_shows_no_items(self):
        summary = [word(264, 50, "Zusammenstellung"), word(OZ_X, 90, "Ordnungszahl"),
                   word(TEXT_X, 90, "Kurztext"), word(OZ_X, 110, "1.1."),
                   word(TEXT_X, 110, "Titel")] + foot(2)
        shown = pc.read_document([PAGE1, summary])
        self.assertEqual(shown["summary_pages"], [2])
        self.assertEqual(shown["pages_without_header"], [2])
        self.assertEqual(len(shown["items"]), 2)
        self.assertEqual(differences(check([PAGE1, summary], RECORDS)), [])


class Checking(unittest.TestCase):
    def test_equal_pages_give_no_difference(self):
        result = check([PAGE1], RECORDS)
        self.assertEqual(differences(result), [])
        self.assertEqual((result["pages_checked"], result["items_on_page"],
                          result["items_in_reader"], result["items_matched"],
                          result["quantity_unit_equal"],
                          result["other_numbers_on_page"],
                          result["other_numbers_matched"], result["continued"]),
                         (1, 2, 2, 2, 2, 1, 1, 0))

    def test_item_on_the_page_missing_in_items_json(self):
        result = check([PAGE1], RECORDS[:2])
        self.assertEqual(differences(result),
                         [(1, "1.1.20", "item on the page, not in items.json")])
        self.assertEqual(result["items_matched"], 1)

    def test_item_of_items_json_missing_on_the_page(self):
        result = check([PAGE1], RECORDS + [rec("1.1.30", 1, 2.0, "St")])
        self.assertEqual(differences(result),
                         [(1, "1.1.30", "item in items.json, not on the page")])

    def test_item_with_another_page_in_items_json(self):
        page2 = page(2, number(110, "1.1.30."), quantity(140, "2,000", "St"))
        result = check([PAGE1, page2], RECORDS + [rec("1.1.30", 1, 2.0, "St")])
        self.assertEqual(sorted(differences(result)), [
            (1, "1.1.30", "item in items.json, not on the page"),
            (2, "1.1.30", "item on the page, in items.json with another page")])

    def test_quantity_and_unit_differences(self):
        records = [RECORDS[0], rec("1.1.10", 1, 6.0, "m2"),
                   rec("1.1.20", 1, 1250.5, "m")]
        result = check([PAGE1], records)
        self.assertEqual(differences(result), [(1, "1.1.10", "quantity differs"),
                                               (1, "1.1.20", "unit differs")])
        self.assertEqual((result["items_matched"], result["quantity_unit_equal"]),
                         (2, 0))

    def test_quantity_without_unit_differs_from_a_unit(self):
        p = page(1, number(110, "1.1.10."), quantity(140, "5,000", None))
        result = check([p], [rec("1.1.10", 1, 5.0, "m2")])
        self.assertEqual(differences(result), [(1, "1.1.10", "unit differs")])

    def test_item_over_a_page_break_is_listed_as_continued(self):
        page1 = page(1, number(110, "1.1.10."))
        page2 = page(2, quantity(110, "5,000"), number(150, "1.1.20."),
                     quantity(180, "1,000", "St"))
        result = check([page1, page2], [rec("1.1.10", 1, 5.0, "m2"),
                                        rec("1.1.20", 2, 1.0, "St")])
        self.assertEqual(differences(result), [])
        self.assertEqual(result["pages"][0]["continued"],
                         [{"doc": "LV_99", "page": 1, "item_no": "1.1.10",
                           "quantity_page": 2}])
        self.assertEqual(result["continued"], 1)

    def test_quantity_without_item_number(self):
        p = page(1, quantity(110, "5,000"))
        self.assertEqual(differences(check([p], [])),
                         [(1, None, "quantity on the page without an item number")])

    def test_heading_differences(self):
        result = check([PAGE1], RECORDS[1:] + [rec("1.2", 1)])
        self.assertEqual(sorted(differences(result)), [
            (1, "1.1", "number on the page, not in items.json with that page"),
            (1, "1.2", "heading in items.json, not on the page")])

    def test_numbered_note_counts_as_a_number_on_the_page(self):
        records = [rec("1.1", 1, kind="preliminary_note")] + RECORDS[1:]
        self.assertEqual(differences(check([PAGE1], records)), [])

    def test_number_without_quantity_is_not_matched_by_a_priced_item(self):
        p = page(1, number(110, "1.1.10."))
        result = check([p], [rec("1.1.10", 1, 5.0, "m2")])
        self.assertEqual(sorted(differences(result)), [
            (1, "1.1.10", "item in items.json, not on the page"),
            (1, "1.1.10", "number on the page, not in items.json with that page")])
        self.assertEqual(result["other_numbers_matched"], 0)

    def test_number_printed_twice_needs_two_records(self):
        p = page(1, number(110, "1.1."), number(130, "1.1."),
                 number(150, "1.1.10."), quantity(180, "5,000"))
        result = check([p], RECORDS[:2])
        self.assertEqual(differences(result), [
            (1, "1.1", "number on the page, not in items.json with that page")])
        self.assertEqual((result["other_numbers_on_page"],
                          result["other_numbers_matched"]), (2, 1))

    def test_number_printed_twice_with_two_records(self):
        p = page(1, number(110, "1.1."), number(130, "1.1."),
                 number(150, "1.1.10."), quantity(180, "5,000"))
        records = [rec("1.1", 1), rec("1.1", 1, kind="preliminary_note"),
                   rec("1.1", 1), rec("1.1.10", 1, 5.0, "m2")]
        result = check([p], records)
        self.assertEqual(differences(result), [])
        self.assertEqual((result["other_numbers_on_page"],
                          result["other_numbers_matched"]), (2, 2))

    def test_heading_record_without_a_printed_number(self):
        records = [rec("1.1", 1), rec("1.1", 1)] + RECORDS[1:]
        self.assertEqual(differences(check([PAGE1], records)),
                         [(1, "1.1", "heading in items.json, not on the page")])

    def test_heading_and_its_note_stand_for_one_printed_number(self):
        records = RECORDS + [rec("1.1", 1, kind="preliminary_note")]
        self.assertEqual(differences(check([PAGE1], records)), [])

    def test_item_on_a_page_the_pdf_does_not_have(self):
        result = check([PAGE1], RECORDS + [rec("1.1.30", 7, 2.0, "St")])
        self.assertEqual([d["difference"] for d in result["pages"][0]["differences"]],
                         ["item in items.json on a page the PDF does not have"])

    def test_same_number_twice_on_a_page(self):
        p = page(1, number(110, "1.1.10."), quantity(140, "5,000"),
                 number(170, "1.1.10."), quantity(200, "5,000"))
        result = check([p], [rec("1.1.10", 1, 5.0, "m2")])
        self.assertEqual(differences(result),
                         [(1, "1.1.10", "item on the page, not in items.json")])


class Summary(unittest.TestCase):
    def test_summary_lists_every_difference_and_no_price(self):
        result = check([PAGE1], RECORDS[:2] + [rec("1.1.30", 1, 2.0, "St")])
        result["file"], result["sha256"] = "LV_99_Test.pdf", "0" * 64
        summary = pc.summarize([result])
        self.assertEqual(summary["lists_checked"], ["LV_99"])
        self.assertEqual(summary["totals"]["pages_checked"], 1)
        self.assertEqual(summary["totals"]["differences"], 2)
        entry = summary["lists"][0]
        self.assertNotIn("pages", entry)
        self.assertEqual(
            sorted((d["doc"], d["page"], d["item_no"]) for d in entry["difference_list"]),
            [("LV_99", 1, "1.1.20"), ("LV_99", 1, "1.1.30")])
        text = repr(summary)
        for key in ("unit_price", "total'", "Einheitspreis", "EUR"):
            self.assertNotIn(key, text)


if __name__ == "__main__":
    unittest.main()
