"""B8, B11, B12: description length, vague phrases, product names."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402

import base_samples as s  # noqa: E402
from pipeline.base import core, text  # noqa: E402


# --- B8 ---------------------------------------------------------------------
def test_b8_fires_on_a_very_short_description():
    items = [s.item("1.10"), s.item("1.20", "Zulage Bogen"), s.item("1.30", "Leiter")]
    findings = s.found(text.b8, items)
    assert s.types(findings) == ["description_short", "description_short"]
    assert findings[0]["sources"] == [{"doc": s.DOC, "item_no": "1.20", "page": 1, "quote": "Zulage Bogen"}]
    assert findings[0]["severity"] == "medium" and "weniger als 3 Wörtern" in findings[0]["explanation_de"]


def test_b8_does_not_fire_from_three_words_on_and_counts_the_long_text():
    items = [s.item("1.10", "Estrich schwimmend verlegen"), s.item("1.20", "Tür", "Stahltür T30 einbauen"),
             s.item("1.30", "PE-Folie 0,2 mm")]
    assert s.found(text.b8, items) == []


def test_b8_counts_distinct_words_not_signs_or_single_letters():
    items = [s.item("1.10"), s.item("1.20", "Tor Tor Tor"), s.item("1.30", "d = 5 cm")]
    assert [f["sources"][0]["item_no"] for f in s.found(text.b8, items)] == ["1.20", "1.30"]


def test_b8_fires_on_an_empty_description_and_cites_the_neighbour():
    items = [s.item("1.10", "Stundenlohn Facharbeiter nach Aufwand"), s.item("1.20", "", ""),
             s.item("1.30", None, None)]
    findings = s.found(text.b8, [items[0], items[1]])
    assert s.types(findings) == ["description_empty"]
    finding = findings[0]
    assert finding["severity"] == "high" and "Position 1.20" in finding["explanation_de"]
    assert finding["explanation_de"].endswith(core.NO_TEXT_NOTE)
    assert finding["sources"][0]["item_no"] == "1.10"
    # two empty items next to the same neighbour: one finding that names both
    outcome = s.run(text.b8, items + [s.item("1.40"), s.item("1.50")])
    assert len(outcome.findings) == 1 and outcome.notes == {"merged": 1}
    assert "Position 1.20" in outcome.findings[0]["explanation_de"]
    assert "Position 1.30" in outcome.findings[0]["explanation_de"]
    s.valid(outcome.findings, items)


def test_b8_a_row_of_dots_is_an_empty_description_with_its_own_quote():
    items = [s.item("1.10"), s.item("1.20", "", "........")]
    findings = s.found(text.b8, items)
    assert s.types(findings) == ["description_empty"]
    assert findings[0]["sources"][0] == {"doc": s.DOC, "item_no": "1.20", "page": 1, "quote": "........"}
    assert not findings[0]["explanation_de"].endswith(core.NO_TEXT_NOTE)


def test_b8_is_not_applicable_to_a_document_that_carries_no_descriptions():
    assert not s.run(text.b8, [s.item("1.10", "", ""), s.item("1.20", None, None)]).applicable
    # an offer file: prices, and a bidder remark on one item in three
    offer = [s.item("1.10", "", ""), s.item("1.20", "", "Lieferzeit vier Wochen ab Auftrag"), s.item("1.30", "", "")]
    assert not s.run(text.b8, offer).applicable
    assert not s.run(text.b8, [s.heading("1"), s.note("", "Hinweise zur Ausführung")]).applicable


def test_b8_applies_when_half_the_positions_have_text():
    items = [s.item("1.10"), s.item("1.20", "", "")]
    assert len(s.found(text.b8, items)) == 1


# --- B11 --------------------------------------------------------------------
PHRASES = [
    ("nach Angabe der Bauleitung", "Lage der Aussparungen nach Angabe der Bauleitung herstellen", "medium"),
    ("nach Angabe der Bauleitung", "Farbton nach Angaben der\nBauleitung", "medium"),
    ("nach Erfordernis", "Gerüst nach Erfordernis umsetzen und sichern", "medium"),
    ("ggf.", "Untergrund prüfen und ggf. grundieren", "info"),
    ("ggf.", "Untergrund gegebenenfalls grundieren und spachteln", "info"),
    ("ca.", "Wanddicke ca. 24 cm in Kalksandstein", "info"),
    ("ca.", "Aushubtiefe circa 80 cm ab Gelände", "info"),
    ("soweit erforderlich", "Bewehrung einbauen, soweit erforderlich, und abnehmen lassen", "medium"),
    ("bauseits", "Anschluss an die bauseits vorhandene Leitung", "medium"),
    ("bauseits", "Befestigung an bauseitiger Unterkonstruktion aus Stahl", "medium"),
    ("komplett", "Türanlage komplett liefern und einbauen", "info"),
    ("komplett", "Liefern der kompletten Anlage frei Baustelle", "info"),
    ("komplett", "Heizkreisverteiler kpl. montieren und anschließen", "info"),
    ("einschl. aller Nebenleistungen", "Bodenplatte herstellen einschl. aller Nebenleistungen", "medium"),
    ("einschl. aller Nebenleistungen", "Bodenplatte herstellen einschließlich aller Nebenleistungen", "medium"),
    ("einschl. aller Nebenleistungen", "Bodenplatte herstellen inkl. aller Nebenleistungen", "medium"),
]


def test_b11_holds_exactly_the_eight_phrases_of_the_plan():
    assert [label for label, _, _ in text.VAGUE_PHRASES] == [
        "nach Angabe der Bauleitung", "nach Erfordernis", "ggf.", "ca.", "soweit erforderlich",
        "bauseits", "komplett", "einschl. aller Nebenleistungen"]
    assert {label for label, _, _ in PHRASES} == {label for label, _, _ in text.VAGUE_PHRASES}


@pytest.mark.parametrize("label, long_text, severity", PHRASES)
def test_b11_fires_on_each_phrase_of_the_plan(label, long_text, severity):
    items = [s.item("1.10"), s.item("1.20", "Leistung nach Plan", long_text)]
    findings = s.found(text.b11, items)
    assert s.types(findings) == ["vague_phrase"]
    finding = findings[0]
    assert finding["search_terms"] == [label] and finding["severity"] == severity
    assert "«%s»" % label in finding["explanation_de"] and "Position 1.20" in finding["explanation_de"]
    assert finding["sources"][0]["item_no"] == "1.20"


@pytest.mark.parametrize("long_text", [
    "Wand mauern in Kalksandstein, Dicke 24 cm",
    "Komplettpreis je Element, Lieferung frei Baustelle",
    "Material: Calcium-Silikat-Platte, Dicke 20 mm",
    "Baustellenseitige Lagerung ist nicht zulässig",
    "Erforderliche Nachweise sind vorzulegen, einschl. Statik",
    "Angabe des Herstellers ist einzutragen",
    "Farbe nach Wahl des Auftraggebers aus der Standardkarte",
])
def test_b11_does_not_fire_on_other_wording(long_text):
    assert s.found(text.b11, [s.item("1.10"), s.item("1.20", "Leistung nach Plan", long_text)]) == []


def test_b11_names_every_phrase_of_an_item_once_and_quotes_each():
    long_text = ("Türanlage komplett liefern. " + "Füllwort " * 30 + "Anschluss ggf. an bauseits vorhandene Zarge.")
    findings = s.found(text.b11, [s.item("1.10", "Türanlage aus Stahl", long_text)])
    assert len(findings) == 1
    finding = findings[0]
    assert finding["search_terms"] == ["ggf.", "bauseits", "komplett"] and finding["severity"] == "medium"
    # one quote per place: "ggf." and "bauseits" stand in the same one
    assert len(finding["sources"]) == 2 and {x["item_no"] for x in finding["sources"]} == {"1.10"}
    assert "ggf. an bauseits" in finding["sources"][0]["quote"] and "komplett" in finding["sources"][1]["quote"]


def test_b11_reads_preliminary_notes_but_not_headings():
    items = [s.heading("1", "Arbeiten nach Erfordernis"),
             s.note("1", "Alle Leistungen verstehen sich einschl. aller Nebenleistungen."),
             s.item("1.10")]
    findings = s.found(text.b11, items)
    assert len(findings) == 1 and "Vorbemerkung 1" in findings[0]["explanation_de"]
    assert findings[0]["exposure"] == {"quantity": None, "unit": None}


def test_b11_is_not_applicable_without_text():
    assert not s.run(text.b11, [s.item("1.10", "", ""), s.heading("1", "Arbeiten nach Erfordernis")]).applicable


def test_b11_quote_holds_across_a_line_end_hyphen():
    items = [s.item("1.10", "Abdichtung der Fuge", "Fugenband ein-\nbauen und ggf. ver-\nschweißen nach Plan")]
    findings = s.found(text.b11, items)
    assert "ggf." in findings[0]["sources"][0]["quote"]


# --- B12 --------------------------------------------------------------------
@pytest.mark.parametrize("long_text", [
    "WC-Element für Trockenbau\nFabrikat: Geberit Duofix",
    "Richtfabrikat: Musterwerk, Typ Alpha",
    "Hersteller: Knauf\nTyp: W112",
    "Fabrikat/Typ: Schöck Isokorb",
    "Fabr. Hilti, Dübel HST3",
    "Fabrikat Sika, Dichtstoff grau",
    "Erzeugnis = Nordwolle Platte",
    "Trockenestrich aus Fermacell® Platten, zweilagig",
    "Dämmung mit Styrodur(R) 3000 CS",
    "Abdichtung mit Dichtol™ Bahn, einlagig",
    "Fabrikat: 3M, Klebeband grau",
    'Fabrikat: "Musterwerk" Typ 5',
    "Fabrikat: „Musterwerk“ Typ 5",
    "Abdichtung mit Dichtol ™ Bahn, einlagig",
    "Richtfabrikat: z.B. Musterwerk Alpha oder Nordwerk Beta",
    "Richtfabrikat: z. B. Musterwerk Alpha",
    "Fabrikat: z.B Musterwerk Alpha",
    "Fabrikat: zB. Musterwerk Alpha",
    "Fabrikat: zum Beispiel Musterwerk Alpha",
    "Fabrikat z.B. Musterwerk Alpha",
    "Hersteller: bspw. Musterwerk",
    "Richtfabrikat: z.B. Musterwerk Alpha\nAngebotenes Fabrikat: ...............",
    "Fabr.: [PERSON_7] gelasert",
    "Richtfabrikat: [PERSON_12] 20/50",
    "Fabrikat: [FIRMA_3] Art.: 5502",
    "Fabrikat [FIRMA_3] Typ 5",
    "Hersteller: z.B. [FIRMA_3]",
    "Fabrikat: „[FIRMA_3]“",
])
def test_b12_fires_on_a_product_name_without_the_clause(long_text):
    items = [s.item("1.10"), s.item("1.20", "Einbauteil liefern und montieren", long_text)]
    findings = s.found(text.b12, items)
    assert s.types(findings) == ["product_without_equivalent"]
    finding = findings[0]
    assert finding["sources"][0]["item_no"] == "1.20" and finding["severity"] == "medium"
    assert finding["search_terms"] == ["oder gleichwertig"] and "«oder gleichwertig»" in finding["explanation_de"]


@pytest.mark.parametrize("long_text", [
    "Fabrikat: Geberit Duofix oder gleichwertig",
    "Fabrikat: Geberit Duofix o. glw.",
    "Fabrikat: Geberit Duofix od. gleichw.",
    "Leitfabrikat: Musterwerk Alpha\noder gleichwertiger Art",
    "Fabrikat: ........................",
    "Fabrikat: '.......'",
    "Fabrikat: 2 ......",
    "Fabrikat: ____________",
    "angebotenes Fabrikat: Musterwerk",
    "gew. Fabrikat: Musterwerk",
    "Fabrikat nach Wahl des Auftragnehmers",
    "Fabrikat: nach Wahl des AN",
    "Hersteller und Typ sind vom Bieter anzugeben",
    "Der Hersteller liefert die Werkstattpläne",
    "Verarbeitung nach Vorschrift des Herstellers",
    "Wand mauern in Kalksandstein, Dicke 24 cm",
    "Anschluss an die Leitung der TM Anlage, Typ ATM",
    "Richtfabrikat: z.B. Musterwerk Alpha, o. glw.",
    "Fabrikat: z. B. Musterwerk Alpha oder gleichwertig",
    "Fabrikat: z.B. ........................",
    "Fabrikat: z.B. nach Wahl des Bieters",
    "Angebotenes Fabrikat: z.B. Musterwerk",
    "Fabrikat: Bieterangabe",
    "Fabrikat: Bieterangabe ............",
    "Fabrikat: [FIRMA_3] oder gleichwertig",
    "Fabr.: [PERSON_7] gelasert, o. glw.",
    "Fabrikat: [PERSON_9] ........................",
    "Hersteller / [PERSON_9] ........................",
    "Angebotenes Fabrikat: [FIRMA_3]",
    "Hersteller [FIRMA_3] liefert die Werkstattpläne",
    "Fabrikat: [ORT_4]",
    "Montage durch [FIRMA_3] nach Angabe",
])
def test_b12_does_not_fire_with_the_clause_or_without_a_product(long_text):
    assert s.found(text.b12, [s.item("1.10"), s.item("1.20", "Einbauteil liefern und montieren", long_text)]) == []


@pytest.mark.parametrize("with_example, plain", [
    ("Richtfabrikat: z.B. Musterwerk Alpha", "Richtfabrikat: Musterwerk Alpha"),
    ("Fabrikat: [FIRMA_3] Art.: 5502", "Fabrikat: Musterwerk Art.: 5502"),
])
def test_b12_an_example_mark_or_a_token_gives_the_same_finding_as_a_plain_name(with_example, plain):
    def one(long_text):
        return s.found(text.b12, [s.item("1.20", "Einbauteil liefern und montieren", long_text)])
    first, second = one(with_example), one(plain)
    assert len(first) == len(second) == 1
    assert first[0]["explanation_de"] == second[0]["explanation_de"]
    assert with_example in first[0]["sources"][0]["quote"]


def test_b12_is_not_applicable_without_text():
    assert not s.run(text.b12, [s.item("1.10", "", ""), s.item("1.20", None, None)]).applicable


def test_b12_a_preliminary_note_with_the_clause_covers_the_items_below_it():
    product = "Fabrikat: Geberit Duofix"
    top = [s.note("", "Genannte Fabrikate gelten als Leitfabrikate; es gilt stets oder gleichwertig."),
           s.item("1.10", "WC-Element einbauen", product), s.item("2.10", "Waschtisch einbauen", product)]
    outcome = s.run(text.b12, top)
    assert outcome.findings == [] and outcome.notes == {"covered_by_note": 2}
    section = [s.note("2", "In diesem Abschnitt gilt für alle Fabrikate: oder gleichwertig."),
               s.item("1.10", "WC-Element einbauen", product), s.item("2.10", "Waschtisch einbauen", product),
               s.item("2.1.10", "Armatur einbauen", product), s.item("20.10", "Spiegel anbringen", product)]
    outcome = s.run(text.b12, section)
    assert [f["sources"][0]["item_no"] for f in outcome.findings] == ["1.10", "20.10"]
    assert outcome.notes == {"covered_by_note": 2}
    s.valid(outcome.findings, section)


def test_b12_reads_a_preliminary_note_that_names_a_product_itself():
    items = [s.note("1", "Alle Rohre: Fabrikat: Wavin Tegra"), s.item("1.10")]
    findings = s.found(text.b12, items)
    assert len(findings) == 1 and "Vorbemerkung 1" in findings[0]["explanation_de"]


def test_b12_the_quote_shows_the_product_name():
    long_text = "Füllwort " * 40 + "Fabrikat: Geberit Duofix " + "Füllwort " * 40
    findings = s.found(text.b12, [s.item("1.10", "WC-Element einbauen", long_text)])
    assert "Fabrikat: Geberit" in findings[0]["sources"][0]["quote"]
    assert len(findings[0]["sources"][0]["quote"]) < 200
