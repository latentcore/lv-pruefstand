"""Unit tests of reader_angebot.py on synthetic text. All amounts here are
invented; no number comes from the organizer data."""

import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))

import reader_angebot as r  # noqa: E402
from pipeline.common import contract  # noqa: E402

COLUMNS = "  Pos-Nr.                Menge ME          EP / EUR          GP / EUR"


def header(page, columns=True):
    out = [" " * 40 + "Musterbau GmbH",
           "  Gemeinde Muster" + " " * 30 + "Angebot-Nr.:    AN99-0001",
           " " * 47 + "Seite:          %d" % page, ""]
    if columns:
        out.append(COLUMNS)
    return out


def footer():
    return ["", "  Musterbank   IBAN: DE00 0000 0000 0000 0000 00   BIC: MUSTERXX"]


def item(no, amount, unit, price, total):
    return "  %-14s %12s %-6s %12s %16s" % (no, amount, unit, price, total)


def text(line):
    return " " * 10 + line


def build(pages):
    out = []
    for i, lines in enumerate(pages, 1):
        out.append("=== PAGE %d ===" % i)
        out.extend(lines)
    return "\n".join(out) + "\n"


def by_no(records, no):
    hits = [x for x in records if x["item_no"] == no and x["quantity"] is not None]
    assert len(hits) == 1, (no, len(hits))
    return hits[0]


PAGE1 = (header(1) + [
    "  Bereich 1.     Erdarbeiten",
    "  Abschnitt 1.1.     Aushub",
    "  Hinweistext",
    item("1.1.10", "1,000", "psch", "10,00", "10,00"),
    text("Baustelle einrichten"),
    "",
    item("1.1.20", "1.250,500", "m³", "2,00", "2.501,00"),
    text("Boden loesen"),
    text("Boden der Klasse 3 loesen und"),
    " " * 40 + "Übertrag:           2.511,00"] + footer())
PAGE2 = (header(2) + [
    " " * 40 + "Übertrag:           2.511,00",
    text("seitlich lagern."),
    "",
    "  Summe Abschnitt 1.1. Aushub" + " " * 30 + "2.511,00",
    "  Abschnitt 1.2.     Verbau",
    "  Hinweistext Verbauarbeiten",
    item("1.2.10", "3,500", "h", "4,00", "14,00"),
    text("Verbau stellen"),
    "",
    "  Summe Abschnitt 1.2. Verbau mit einem langen Namen, der",
    " " * 60 + "14,00",
    "  Summe Bereich 1. Erdarbeiten" + " " * 30 + "2.525,00"] + footer())
LAST = (header(3) + [
    "  Gesamtzusammenstellung",
    "  Zusammenstellung Bereich 1. Erdarbeiten" + " " * 20 + "2.525,00",
    "  Summe netto" + " " * 40 + "2.525,00",
    "  zzgl. Mehrwertsteuer 19 %" + " " * 30 + "479,75",
    "  Gesamtsumme:" + " " * 40 + "3.004,75",
    "  Mit freundlichen Grüßen",
    "  Datum:                    Unterschrift:"] + footer())

PRICE_LIKE = re.compile(r"\d,\d\d")


def parse(pages):
    return r.parse_text("Angebot-Test", build(pages))


class Synthetic(unittest.TestCase):
    def test_items_and_fields(self):
        recs, pages, warnings, unparsed = parse([PAGE1, PAGE2, LAST])
        self.assertEqual((pages, warnings, unparsed), (3, [], 0))
        priced = [x for x in recs if x["quantity"] is not None]
        self.assertEqual([x["item_no"] for x in priced],
                         ["1.1.10", "1.1.20", "1.2.10"])
        a = by_no(recs, "1.1.10")
        self.assertEqual((a["kind"], a["section"], a["quantity"], a["unit"],
                          a["unit_price"], a["total"], a["page"], a["format"],
                          a["stage"], a["project"], a["short_text"],
                          a["long_text"]),
                         ("lump_sum", "1.1", 1.0, "psch", 10.0, 10.0, 1, "pdf",
                          "84", "AN99-0001", "Baustelle einrichten", ""))
        self.assertEqual(contract.errors("items", recs), [])

    def test_headings_and_notes(self):
        recs, _, _, _ = parse([PAGE1, PAGE2, LAST])
        self.assertEqual(
            [(x["item_no"], x["short_text"]) for x in recs if x["kind"] == "heading"],
            [("1", "Erdarbeiten"), ("1.1", "Aushub"), ("1.2", "Verbau")])
        notes = [x for x in recs if x["kind"] == "preliminary_note"]
        self.assertEqual([(x["item_no"], x["short_text"], x["page"]) for x in notes],
                         [("1.1", "Hinweistext", 1),
                          ("1.2", "Hinweistext Verbauarbeiten", 2)])

    def test_item_text_over_a_page_break(self):
        recs, _, _, _ = parse([PAGE1, PAGE2, LAST])
        b = by_no(recs, "1.1.20")
        self.assertEqual((b["page"], b["quantity"], b["unit"], b["kind"]),
                         (1, 1250.5, "m³", "normal"))
        self.assertEqual(b["short_text"], "Boden loesen")
        self.assertEqual(b["long_text"],
                         "Boden der Klasse 3 loesen und\nseitlich lagern.")

    def test_sum_lines_are_no_items_and_no_text(self):
        recs, _, _, _ = parse([PAGE1, PAGE2, LAST])
        for x in recs:
            self.assertNotIn("Summe", x["short_text"] + x["long_text"])
            self.assertNotIn("Übertrag", x["short_text"] + x["long_text"])
        c = by_no(recs, "1.2.10")
        self.assertEqual((c["short_text"], c["long_text"]), ("Verbau stellen", ""))

    def test_last_page_gives_no_items(self):
        recs, _, warnings, unparsed = parse([LAST])
        self.assertEqual([x for x in recs if x["quantity"] is not None], [])
        self.assertEqual(unparsed, 0)

    def test_unknown_line_after_the_last_sum_is_counted(self):
        page = LAST[:-2] + ["  Ein Satz, den der Leser nicht kennt"] + LAST[-2:]
        _, _, warnings, unparsed = parse([page])
        self.assertEqual(unparsed, 1)
        self.assertEqual(warnings, ["unread line on page 1 (after the last sum)"])

    def test_item_line_without_unit_is_counted_not_guessed(self):
        page = header(1) + [
            "  1.1.10               1,000              10,00            10,00",
            text("Posten ohne Einheit"),
            item("1.1.20", "2,000", "St", "3,00", "6,00"),
            text("Posten")] + footer()
        recs, _, warnings, unparsed = parse([page])
        self.assertEqual(unparsed, 1)
        self.assertEqual([x["item_no"] for x in recs if x["quantity"] is not None],
                         ["1.1.20"])
        self.assertEqual(warnings,
                         ["unread line on page 1 (line with an item number)"])

    def test_warnings_carry_no_amount_and_no_source_line(self):
        page = header(1) + [
            "  1.1.10               1,000              10,00            10,00",
            "  Fremder Satz 12,34",
            item("1.1.20", "2,000", "St", "3,00", "6,00")] + footer()
        _, _, warnings, unparsed = parse([page, header(2, columns=False)
                                          + ["  1.1.30  5,000 St 7,77 38,85"]])
        # 2 lines on page 1; page 2 is not read: its 4 lines with text count
        self.assertEqual(unparsed, 6)
        self.assertEqual(warnings, [
            "unread line on page 1 (line with an item number)",
            "unread line on page 1 (text in the Pos-Nr. column)",
            "no column header on page 2, page not read",
            "item 1.1.20 on page 1 has no short text"])
        for w in warnings:
            self.assertIsNone(PRICE_LIKE.search(w), w)
            self.assertNotIn("Fremder", w)

    def test_page_without_column_header_is_not_read(self):
        page = header(1, columns=False) + [item("1.1.10", "1,000", "St", "1,00", "1,00")]
        recs, _, warnings, unparsed = parse([page])
        self.assertEqual(recs, [])
        self.assertIn("no column header on page 1, page not read", warnings)
        self.assertGreater(unparsed, 0)

    def test_item_without_text_warns(self):
        page = header(1) + [item("1.1.10", "1,000", "St", "1,00", "1,00")] + footer()
        recs, _, warnings, _ = parse([page])
        self.assertEqual(by_no(recs, "1.1.10")["short_text"], "")
        self.assertIn("item 1.1.10 on page 1 has no short text", warnings)

    def test_number_inside_item_text_is_text(self):
        page = header(1) + [
            item("1.1.10", "1,000", "St", "1,00", "1,00"),
            text("Rohr DN 100"),
            text("1.1.20 ist die Zulageposition, 2,500 m tief")] + footer()
        recs, _, warnings, unparsed = parse([page])
        self.assertEqual((len(recs), unparsed), (1, 0))
        self.assertIn("1.1.20 ist die Zulageposition", recs[0]["long_text"])

    def test_sum_words_inside_item_text_are_text(self):
        page = header(1) + [
            item("1.1.10", "1,000", "St", "1,00", "1,00"),
            text("Dokumentation"),
            text("Gesamtzusammenstellung"),
            text("Summe aller Laengen"),
            item("1.1.20", "2,000", "St", "3,00", "6,00"),
            text("Posten")] + footer()
        recs, _, warnings, unparsed = parse([page])
        self.assertEqual([x["item_no"] for x in recs if x["quantity"] is not None],
                         ["1.1.10", "1.1.20"])
        self.assertEqual(by_no(recs, "1.1.10")["long_text"],
                         "Gesamtzusammenstellung\nSumme aller Laengen")
        self.assertEqual((warnings, unparsed), ([], 0))

    def test_two_runs_give_the_same_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "Angebot-Test.txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write(build([PAGE1, PAGE2, LAST]))
            outs = []
            for k in range(2):
                out = os.path.join(tmp, "out%d" % k)
                r.run(src, out)
                blobs = []
                for n in ("items.json", "manifest.json"):
                    with open(os.path.join(out, n), "rb") as f:
                        blobs.append(f.read())
                outs.append(blobs)
            self.assertEqual(outs[0], outs[1])
            manifest = json.loads(outs[0][1])
            self.assertEqual(contract.errors("manifest", manifest), [])
            m = manifest[0]
            self.assertEqual((m["doc"], m["format"], m["stage"], m["pages"],
                              m["items"], m["headings"], m["preliminary_notes"],
                              m["unparsed_lines"], m["warnings"]),
                             ("Angebot-Test", "pdf", "84", 3, 3, 3, 2, 0, []))


if __name__ == "__main__":
    unittest.main()
