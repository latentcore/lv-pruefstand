"""Unit tests of reader_ausdruck.py on synthetic text (invented numbers)."""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))

import reader_ausdruck as r  # noqa: E402
from pipeline.common import contract  # noqa: E402

DOTS = "..................."


def header(page, columns=True):
    out = ["           Ingenieurbuero Muster * Musterweg 1 * Musterstadt",
           "Projekt:           Testprojekt Kanal" + " " * 60 + "Seite %d" % page,
           "Bauherr:           Gemeinde Muster" + " " * 55 + "Datum 01.01.2026",
           "DV-Nr. AG:         1"]
    if columns:
        out += ["Pos                 Stl-Nr." + " " * 30 + "Menge / Einheit"
                "      Einheitspreis        Gesamtbetrag",
                " " * 90 + "in EUR              in EUR"]
    return out


def footer(page, of=3):
    return ["Alle Einzelbeträge Netto in EUR" + " " * 50
            + "01.01.2026 - Seite %d von %d" % (page, of)]


def qty(amount, unit, price=DOTS, total=DOTS):
    return " " * 55 + "%s %s      %s  %s" % (amount, unit, price, total)


def build(pages):
    out = []
    for i, lines in enumerate(pages, 1):
        out.append("=== PAGE %d ===" % i)
        out.extend(lines)
    return "\n".join(out) + "\n"


def by_no(records, no):
    hits = [x for x in records if x["item_no"] == no]
    assert len(hits) == 1, (no, len(hits))
    return hits[0]


TOC = (["           Ingenieurbuero Muster",
        "                    Inhaltsverzeichnis",
        "01                  LV       Testprojekt Kanal",
        "01                  Titel    Baustelleneinrichtung" + " " * 40 + "2",
        "02                  Titel    Erdarbeiten" + " " * 50 + "3"]
       + footer(1))
PAGE2 = (header(2) + [
    "01                  Baustelleneinrichtung",
    "",
    "01.0001             Baustelle einrichten",
    "                    Einrichten der Baustelle mit allen Geraeten.",
    "", qty("1,000", "psch"), "",
    "01.0002             Bauzaun stellen",
    "                    Hoehe 2,00 m, Laenge nach Aufmass,",
    "", " " * 60 + "Übertrag:       " + DOTS] + footer(2))
PAGE3 = (header(3) + [
    " " * 60 + "Übertrag:       " + DOTS,
    "                    standsicher aufstellen.",
    "", qty("1.250,500", "m"), "",
    "02                  Erdarbeiten",
    "",
    "02.0001             Boden loesen",
    "", qty("12", "m3"), ""] + footer(3))
SUMMARY = (header(4, columns=False) + [
    "OZ                 Abschnitt" + " " * 60 + "Gesamtbetrag",
    " " * 95 + "in EUR",
    "Zusammenstellung der Abschnitte",
    "01                  Baustelleneinrichtung" + " " * 40 + DOTS,
    "02                  Erdarbeiten" + " " * 50 + DOTS,
    "Gesamtsumme" + " " * 30 + "01 Testprojekt Kanal" + " " * 20 + DOTS,
    " " * 70 + "MWSt. 19,0 %" + " " * 10 + DOTS,
    " " * 55 + "Gesamtsumme inkl. MWSt." + " " * 10 + DOTS,
    " " * 55 + "." * 40,
    " " * 55 + "(Ort und Datum)"] + footer(4, 4))


def parse(pages):
    return r.parse_text("LV-Test", build(pages))


class Synthetic(unittest.TestCase):
    def test_items_headings_and_fields(self):
        recs, pages, warnings, unparsed = parse([TOC, PAGE2, PAGE3, SUMMARY])
        self.assertEqual((pages, warnings, unparsed), (4, [], 0))
        priced = [x for x in recs if x["quantity"] is not None]
        self.assertEqual([x["item_no"] for x in priced],
                         ["01.0001", "01.0002", "02.0001"])
        self.assertEqual([x["item_no"] for x in recs if x["kind"] == "heading"],
                         ["01", "02"])
        a = by_no(recs, "01.0001")
        self.assertEqual((a["kind"], a["section"], a["quantity"], a["unit"],
                          a["page"], a["format"], a["stage"], a["project"]),
                         ("lump_sum", "01", 1.0, "psch", 2, "pdf", "83",
                          "Testprojekt Kanal"))
        self.assertEqual(a["short_text"], "Baustelle einrichten")
        self.assertEqual(a["long_text"],
                         "Einrichten der Baustelle mit allen Geraeten.")
        self.assertIsNone(a["unit_price"])
        self.assertIsNone(a["total"])
        self.assertEqual(contract.errors("items", recs), [])

    def test_item_over_a_page_break(self):
        recs, _, warnings, unparsed = parse([TOC, PAGE2, PAGE3, SUMMARY])
        b = by_no(recs, "01.0002")
        self.assertEqual((b["page"], b["quantity"], b["unit"], b["kind"]),
                         (2, 1250.5, "m", "normal"))
        self.assertEqual(b["long_text"], "Hoehe 2,00 m, Laenge nach Aufmass,\n"
                                         "standsicher aufstellen.")
        self.assertNotIn("Übertrag", b["long_text"])

    def test_quantity_without_decimals(self):
        recs, _, _, _ = parse([PAGE2, PAGE3])
        self.assertEqual(by_no(recs, "02.0001")["quantity"], 12.0)

    def test_filled_price_fields_are_read(self):
        page = header(1) + [
            "01.0001             Posten", "",
            qty("2,000", "St", "3,50", "7,00"), ""] + footer(1, 1)
        recs, _, warnings, unparsed = parse([page])
        a = by_no(recs, "01.0001")
        self.assertEqual((a["unit_price"], a["total"]), (3.5, 7.0))
        self.assertEqual((warnings, unparsed), ([], 0))

    def test_summary_page_gives_no_items(self):
        recs, _, _, unparsed = parse([SUMMARY])
        self.assertEqual(recs, [])
        self.assertEqual(unparsed, 0)

    def test_unknown_line_on_summary_page_is_counted(self):
        page = SUMMARY[:-1] + ["Ein Satz, den der Leser nicht kennt"] + SUMMARY[-1:]
        _, _, warnings, unparsed = parse([page])
        self.assertEqual(unparsed, 1)
        self.assertEqual(warnings, ["unread line on page 1 (summary page)"])

    def test_quantity_without_item_is_counted(self):
        page = header(1) + ["", qty("2,000", "St")] + footer(1, 1)
        recs, _, warnings, unparsed = parse([page])
        self.assertEqual(unparsed, 1)
        self.assertEqual([x for x in recs if x["quantity"] is not None], [])
        self.assertIn("quantity line without item on page 1", warnings)

    def test_price_field_without_quantity_is_counted(self):
        page = header(1) + [
            "01.0001             Posten",
            " " * 55 + "St      " + DOTS + "  " + DOTS,
            ""] + footer(1, 1)
        recs, _, warnings, unparsed = parse([page])
        self.assertEqual(unparsed, 1)
        self.assertIn("unread line on page 1 (price field without quantity)",
                      warnings)
        self.assertEqual([x for x in recs if x["quantity"] is not None], [])

    def test_table_of_contents_is_checked(self):
        toc = list(TOC)
        toc[4] = "02                  Titel    Erdarbeiten" + " " * 50 + "9"
        toc.insert(5, "03                  Titel    Fehlt" + " " * 50 + "9")
        _, _, warnings, unparsed = parse([toc, PAGE2, PAGE3])
        self.assertEqual(unparsed, 0)
        self.assertIn("section 02 differs from the table of contents "
                      "(page or title)", warnings)
        self.assertIn("table of contents names section 03, no such heading "
                      "was read", warnings)

    def test_unknown_line_in_table_of_contents_is_counted(self):
        toc = TOC[:-1] + ["ein fremder Satz"] + TOC[-1:]
        _, _, warnings, unparsed = parse([toc, PAGE2, PAGE3])
        self.assertEqual(unparsed, 1)

    def test_page_without_footer_warns(self):
        _, _, warnings, _ = parse([PAGE2[:-1], PAGE3])
        self.assertIn("no footer on page 1", warnings)

    def test_missing_project_line_gives_an_empty_string_and_a_warning(self):
        page = [l for l in PAGE2 if not l.startswith("Projekt:")]
        recs, _, warnings, _ = parse([page])
        self.assertEqual(set(x["project"] for x in recs), {""})
        self.assertEqual(warnings.count("no Projekt line found"), 1)
        self.assertEqual(contract.errors("items", recs), [])

    def test_two_runs_give_the_same_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "LV-Test.txt")
            with open(src, "w", encoding="utf-8") as f:
                f.write(build([TOC, PAGE2, PAGE3, SUMMARY]))
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
                              m["items"], m["headings"], m["unparsed_lines"]),
                             ("LV-Test", "pdf", "83", 4, 3, 2, 0))


if __name__ == "__main__":
    unittest.main()
