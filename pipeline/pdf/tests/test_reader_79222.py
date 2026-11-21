import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reader_79222 as r  # noqa: E402

DATA_DIR = os.environ.get("LV_TEXT_DIR", "")

QTY_DOTS = " " * 25 + "........................."


def header(lv_no="99", trade="Testgewerk"):
    return [
        " " * 80 + "[FIRMA_001]",
        " " * 80 + "[ADRESSE_001]",
        " " * 50 + "Anfrage",
        "",
        "Projekt:         11-111                Testprojekt Halle",
        "LV:              %s                    %s" % (lv_no, trade),
        "",
        "OZ               Leistungsbeschreibung        Menge ME     Einheitspreis       Gesamtbetrag",
        " " * 70 + "in EUR             in EUR",
        "",
    ]


def footer(page):
    return ["", "", "Druckdatum:   1.1.2026" + " " * 60 + "Seite: %d" % page,
            " " * 80 + "[FIRMA_001]"]


def qty(amount, unit, last="........................."):
    return " " * 50 + "%s %s     ........................." % (amount, unit) \
        + "   " + last


def build(pages):
    out = []
    for n, body in enumerate(pages, 1):
        out.append("=== PAGE %d ===" % n)
        out.extend(header())
        out.extend(body)
        out.extend(footer(n))
    out.append("=== PAGE %d ===" % (len(pages) + 1))
    return "\n".join(out) + "\n"


def parse(pages):
    records, n, warnings, unparsed = r.parse_text("LV_99", build(pages))
    return records, n, warnings, unparsed


def by_no(records, no, kind=None):
    for rec in records:
        if rec["item_no"] == no and (kind is None or rec["kind"] == kind):
            return rec
    raise AssertionError("no record %s %s" % (no, kind))


class GermanNumbers(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(r.parse_german_number("1.234,500"), 1234.5)
        self.assertEqual(r.parse_german_number("35,000"), 35.0)
        self.assertEqual(r.parse_german_number("0,000"), 0.0)
        self.assertEqual(r.parse_german_number("12.345.678,9"), 12345678.9)


class Synthetic(unittest.TestCase):
    PAGE1 = [
        "",
        "1.               Hauptabschnitt",
        "",
        "1.1.             Vorbemerkung",
        "",
        "                 Allgemeine Hinweise zum Gewerk.",
        "                 Zweite Zeile der Hinweise.",
        "",
        "1.2.             Abschnitt Boden",
        "",
        "1.2.10.          Estrich verlegen, 50mm",
        "                 Estrich auf Trennlage einbauen.",
        "                 Vorleistung:          Rohdecke gereinigt",
        "                 Folgeleistung:        Bodenbelag elastisch,",
        "                                       verklebt",
        "                 Einbauort:            EG",
        "",
        qty("1.234,500", "m2"),
        "",
        "1.2.20.          *** Bedarfsposition ohne GB",
        "                 Zulage Schnellestrich",
        "                 Zusatzmittel fuer schnelle Belegreife.",
        "",
        qty("85,000", "m2", "    Nur Einh.-Pr."),
        "",
        "1.2.30.          Baustelleneinrichtung",
        "                 Einrichten und Raeumen der Baustelle.",
        "",
        qty("1,000", "psch"),
        "",
        "1.2.40.          *** Bedarfsposition mit GB",
        "                 Risse schliessen",
        "",
        qty("20,000", "m"),
        "",
        "1.2.50.          Trennschiene einbauen",
        "                 Erste Zeile der langen Beschreibung,",
        "                 die auf der naechsten Seite",
        " " * 70 + "Übertrag:",
    ]
    PAGE2 = [
        " " * 70 + "Übertrag:",
        "",
        "                 weitergeht und dort endet.",
        "",
        qty("7,000", "m"),
        "",
        "1.2.60.          *** Wahlposition 1.1 zu 1.0",
        "                 Alternativer Belag",
        "",
        qty("3,000", "St"),
        "",
        " Summe 1.2.       Abschnitt Boden" + " " * 40 + ".........................",
    ]

    @classmethod
    def setUpClass(cls):
        cls.records, cls.pages, cls.warnings, cls.unparsed = parse(
            [cls.PAGE1, cls.PAGE2])

    def test_pages_ignore_trailing_empty_marker(self):
        self.assertEqual(self.pages, 2)
        self.assertEqual(self.unparsed, 0)

    def test_heading(self):
        h = by_no(self.records, "1.2", "heading")
        self.assertEqual(h["short_text"], "Abschnitt Boden")
        self.assertEqual(h["section"], "1")
        self.assertIsNone(h["quantity"])
        self.assertEqual(by_no(self.records, "1", "heading")["section"], "")

    def test_preliminary_note(self):
        n = by_no(self.records, "1.1", "preliminary_note")
        self.assertEqual(n["short_text"], "Vorbemerkung")
        self.assertEqual(n["long_text"],
                         "Allgemeine Hinweise zum Gewerk.\nZweite Zeile der Hinweise.")
        self.assertIsNone(n["quantity"])

    def test_normal_item(self):
        it = by_no(self.records, "1.2.10")
        self.assertEqual(list(it.keys()), r.KEYS)
        self.assertEqual(it["kind"], "normal")
        self.assertEqual(it["section"], "1.2")
        self.assertEqual(it["short_text"], "Estrich verlegen, 50mm")
        self.assertEqual(it["quantity"], 1234.5)
        self.assertEqual(it["unit"], "m2")
        self.assertEqual(it["page"], 1)
        self.assertEqual(it["trade"], "Testgewerk")
        self.assertEqual(it["project"], "11-111")
        self.assertEqual(it["pre_trade_text"], "Rohdecke gereinigt")
        self.assertEqual(it["post_trade_text"], "Bodenbelag elastisch, verklebt")
        self.assertIn("Einbauort: EG", it["long_text"])

    def test_optional_unit_price_only(self):
        it = by_no(self.records, "1.2.20")
        self.assertEqual(it["kind"], "optional")
        self.assertEqual(it["short_text"], "Zulage Schnellestrich")
        self.assertEqual(it["price_mode"], "unit_price_only")
        self.assertNotIn("***", it["long_text"])

    def test_optional_in_total(self):
        it = by_no(self.records, "1.2.40")
        self.assertEqual(it["kind"], "optional")
        self.assertEqual(it["price_mode"], "in_total")
        self.assertEqual(it["quantity"], 20.0)

    def test_lump_sum(self):
        it = by_no(self.records, "1.2.30")
        self.assertEqual(it["kind"], "lump_sum")
        self.assertEqual(it["unit"], "psch")
        self.assertNotIn("price_mode", it)

    def test_alternative(self):
        self.assertEqual(by_no(self.records, "1.2.60")["kind"], "alternative")

    def test_page_break_continuation(self):
        it = by_no(self.records, "1.2.50")
        self.assertEqual(it["page"], 1)
        self.assertEqual(it["quantity"], 7.0)
        self.assertEqual(it["long_text"],
                         "Erste Zeile der langen Beschreibung,\n"
                         "die auf der naechsten Seite\nweitergeht und dort endet.")
        for bad in ("Projekt:", "Druckdatum", "Übertrag", "FIRMA_001", "in EUR"):
            self.assertNotIn(bad, it["long_text"])

    def test_dot_numbering(self):
        page = [
            "",
            "                 Einleitender Text ohne Nummer.",
            "",
            ".5               Rohr 20 x 2 mm",
            "                 Rohr liefern und verlegen.",
            "",
            qty("1.010,000", "m"),
            "",
            ".6               Messstellenmarkierung",
            "                 Markierung der Messstelle.",
            "",
            qty("5,000", "St"),
        ]
        recs, _, _, _ = parse([page])
        it = by_no(recs, ".6")
        self.assertEqual(it["section"], "")
        self.assertEqual(it["quantity"], 5.0)
        self.assertEqual(by_no(recs, ".5")["quantity"], 1010.0)
        note = recs[0]
        self.assertEqual(note["kind"], "preliminary_note")
        self.assertEqual(note["item_no"], "")

    def test_trade_text_bullet_and_colonless(self):
        recs, _, _, _ = parse([[
            "1.1.10.          Bulletposten",
            "                 - Folgeleistung:         Bodenbelag",
            "                 - Untergrund/Vorleistung:Estrich",
            "                 - Einbauort:             UG",
            "", qty("1,000", "m2"), "",
            "1.1.20.          Ohne Doppelpunkt",
            "                 Folgeleistung (baus.)     Endbeschichtung",
            "                 Wandstaerke:              125 mm",
            "", qty("2,000", "St"), ""]])
        a = by_no(recs, "1.1.10")
        self.assertEqual((a["pre_trade_text"], a["post_trade_text"]),
                         ("Estrich", "Bodenbelag"))
        b = by_no(recs, "1.1.20")
        self.assertEqual(b["post_trade_text"], "Endbeschichtung")

    def test_quantity_without_item_warns(self):
        recs, _, warnings, unparsed = parse([["", qty("2,000", "St")]])
        self.assertEqual(unparsed, 1)
        self.assertIn("quantity line without item on page 1", warnings)

    def test_deterministic_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "txt")
            os.makedirs(src)
            with open(os.path.join(src, "LV_99.txt"), "w", encoding="utf-8") as f:
                f.write(build([self.PAGE1, self.PAGE2]))
            outs = []
            for k in range(2):
                out = os.path.join(tmp, "out%d" % k)
                r.run(src, out)
                blobs = []
                for n in ("items.json", "manifest.json"):
                    with open(os.path.join(out, n), "rb") as f:
                        blobs.append(f.read())
                outs.append(tuple(blobs))
            self.assertEqual(outs[0], outs[1])
            man = json.loads(outs[0][1])
            self.assertEqual(man[0]["doc"], "LV_99")
            self.assertEqual(man[0]["items"], 6)


@unittest.skipUnless(DATA_DIR and os.path.isdir(DATA_DIR),
                     "set LV_TEXT_DIR to the real text directory")
class RealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = tempfile.TemporaryDirectory()
        cls.items, cls.manifest = r.run(DATA_DIR, cls.out.name)

    @classmethod
    def tearDownClass(cls):
        cls.out.cleanup()

    def get(self, doc, no):
        hits = [i for i in self.items if i["doc"] == doc and i["item_no"] == no
                and i["quantity"] is not None]
        self.assertEqual(len(hits), 1, (doc, no))
        return hits[0]

    def test_manifest(self):
        self.assertEqual(len(self.manifest), 27)
        self.assertEqual(sum(m["pages"] for m in self.manifest), 397)

    def test_known_items(self):
        cases = [("LV_17", "10.2.130", 32, "St"), ("LV_13", "1.4.1.8", 98, "St"),
                 ("LV_18", "11.4.60", 35, "m2"), ("LV_14c", ".6", 5, "St"),
                 ("LV_20", "14.2.10", 140, "m2"), ("LV_00", "3.2.70", 0, "m"),
                 ("LV_10", "1.1.80", 24, "St"), ("LV_12", "6.1.130", 1, "St")]
        for doc, no, q, unit in cases:
            it = self.get(doc, no)
            self.assertEqual((it["quantity"], it["unit"]), (q, unit), (doc, no))
        self.assertIn("Staubbindender Anstrich",
                      self.get("LV_18", "11.4.60")["post_trade_text"])
        self.assertIn("Laibung Gipskarton",
                      self.get("LV_12", "6.1.130")["post_trade_text"])
        a = self.get("LV_02", "14.1.30")
        self.assertEqual((a["kind"], a.get("price_mode")), ("optional", "unit_price_only"))
        b = self.get("LV_20", "14.1.30")
        self.assertEqual((b["kind"], b.get("price_mode"), b["quantity"]),
                         ("optional", "in_total", 20))


if __name__ == "__main__":
    unittest.main()
