"""W8: the three German export files on synthetic findings, items and reviews.

Only confirmed findings appear; both quotes of a finding between lists stand
word for word; the marked rows of the .xlsx are exactly the cited items; no
price of a priced items.json reaches a file; every fixed German text stands in
web/export/texte_de.py. The .docx and .xlsx are read back with python-docx and
openpyxl, the HTML as text.
"""
import html
import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402
from docx import Document  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from web.app import STATIC_DIR, create_app  # noqa: E402
from web.export import __main__ as command  # noqa: E402
from web.export import files, model  # noqa: E402
from web.export import texte_de as T  # noqa: E402

NOW = datetime(2026, 11, 21, 9, 5)
QUOTE_A1 = "Die Randdämmstreifen werden vom AN Estrich geliefert und eingebaut; Maß 8 mm, Fuge < 5 mm & \"dicht\" schließen."
QUOTE_A2 = "Randdämmstreifen an allen aufgehenden Bauteilen liefern und einbauen"
QUOTE_B1 = "schwimmender Estrich auf Wärmedämmung, Nenndicke 65 mm"
QUOTE_B2 = "Aufbauhöhe laut Planung:\nEstrich 50 mm, Größe <b>fett</b>"


def source(doc, item_no, page, quote):
    return {"doc": doc, "item_no": item_no, "page": page, "quote": quote}


def finding(fid, kind, severity, sources, question, explanation, skeptic="survived", layer="between_lists",
            agent_status=None):
    verdict = {"status": skeptic, "note": "synthetic"}
    if agent_status:
        verdict["agent_status"] = agent_status
    return {"id": fid, "check": fid.split("-")[0], "layer": layer, "type": kind, "severity": severity,
            "handover": sorted(set(s["doc"] for s in sources)), "sources": sources,
            "lists_searched": ["LV_91", "LV_92"], "search_terms": ["Estrich"],
            "explanation_de": explanation, "question_de": question,
            "exposure": {"quantity": None, "unit": None}, "quotes_verified": True, "origin": "model+code",
            "skeptic": verdict}


FINDINGS = [
    finding("X1-aaa111", "double_assignment", "medium",
            [source("LV_91", "1", 1, QUOTE_A1), source("LV_92", "2.10", 3, QUOTE_A2)],
            "Welches Gewerk liefert die Randdämmstreifen und schließt die Fuge?",
            "Die Randdämmstreifen stehen in der Vorbemerkung des Estrichs und als eigene Position beim Bodenbelag."),
    finding("X2-bbb222", "contradiction", "high",
            [source("LV_91", "1.10", 2, QUOTE_B1), source("LV_92", "2.20", 4, QUOTE_B2)],
            "Welche Estrichdicke gilt für die Aufbauhöhe: 65 mm oder 50 mm? <script>alert(1)</script>",
            "Der Estrich ist mit 65 mm ausgeschrieben, der Bodenbelag rechnet mit 50 mm.", skeptic="weakened"),
    finding("X3-ccc333", "gap", "high", [source("LV_92", "2.30", 5, "VERWORFENES ZITAT Sockelleiste")],
            "VERWORFENE FRAGE zur Sockelleiste?", "VERWORFENE ERKLÄRUNG."),
    finding("X2-ddd444", "contradiction", "medium",
            [source("LV_91", "1.20", 2, "UNKLARES ZITAT eins"), source("LV_92", "2.40", 5, "UNKLARES ZITAT zwei")],
            "UNKLARE FRAGE zum Belag?", "UNKLARE ERKLÄRUNG.", skeptic="weakened", agent_status="survived"),
    finding("X3-eee555", "gap", "info", [source("LV_91", "1.30", 3, "OFFENES ZITAT Trennlage")],
            "OFFENE FRAGE zur Trennlage?", "OFFENE ERKLÄRUNG.", skeptic="refuted"),
    finding("S-fff666", "eigene_art", "eigene_stufe", [source("LV_93", "9.9", 7, "=Zitat aus einer Liste ohne Positionen, Straße")],
            "Gilt die Fußnote zur Straße?", "Die Liste LV_93 steht nicht in items.json.", layer="single_list"),
]
CONFIRMED = ["X2-bbb222", "X1-aaa111", "S-fff666"]  # in the order of the files: high, medium, unknown level
NOT_CONFIRMED = ["X3-ccc333", "X2-ddd444", "X3-eee555"]
REVIEWS = {
    "X1-aaa111": {"status": "confirmed", "by": "Kalkulator (Mentor)", "comment": "Gehört zum Estrich, größte Mühe.",
                  "eur_estimate": 1500.5, "at": "2026-11-21T10:42"},
    "X2-bbb222": {"status": "confirmed", "by": "Bauleiterin (Team)", "comment": "", "eur_estimate": None,
                  "at": "2026-11-21T10:47"},
    "X3-ccc333": {"status": "rejected", "by": "VERWERFER", "comment": "VERWORFENER KOMMENTAR", "eur_estimate": 4321.0,
                  "at": "2026-11-21T10:50"},
    "X2-ddd444": {"status": "unclear", "by": "UNKLARER", "comment": "UNKLARER KOMMENTAR", "eur_estimate": None,
                  "at": "2026-11-21T10:51"},
    "S-fff666": {"status": "confirmed", "by": "", "comment": "", "eur_estimate": None, "at": ""},
    # A review of a finding that the findings file no longer holds.
    "X9-gone99": {"status": "confirmed", "by": "GEIST", "comment": "GEISTERKOMMENTAR", "eur_estimate": 8765.0,
                  "at": "2026-11-20T08:00"},
}


def item(doc, trade, item_no, kind, short_text, long_text, quantity, unit, page, number):
    """One priced record: every record has its own unit price and total, so a leak is found by value."""
    return {"doc": doc, "project": "P1", "trade": trade, "format": "pdf", "stage": "anfrage", "item_no": item_no,
            "kind": kind, "section": "", "short_text": short_text, "long_text": long_text, "quantity": quantity,
            "unit": unit, "unit_price": 9000.01 + number, "total": 700000.07 + number, "price_mode": "priced",
            "page": page, "line": None, "pre_trade_text": None, "post_trade_text": None}


ITEMS = [item(*values, number=number) for number, values in enumerate([
    ("LV_91", "Estrich", "1", "heading", "Estricharbeiten", "", None, None, 1),
    ("LV_91", "Estrich", "1", "preliminary_note", "Vorbemerkung", "Vorleistung: Rohdecke.\n" + QUOTE_A1, None, None, 1),
    ("LV_91", "Estrich", "1.10", "normal", "Zementestrich CT-C25-F4", QUOTE_B1, 120.0, "m2", 2),
    ("LV_91", "Estrich", "1.20", "normal", "=SUMME(A1:A2)", "Formeltext", 3.5, "m", 2),
    ("LV_91", "Estrich", "1.30", "optional", "Trennlage", "OFFENES ZITAT Trennlage", 85.0, "m2", 3),
    ("LV_92", "Bodenbelag", "2", "heading", "Bodenbelagsarbeiten", "", None, None, 3),
    ("LV_92", "Bodenbelag", "2.10", "normal", "Randdämmstreifen", QUOTE_A2, 85.5, "m", 3),
    ("LV_92", "Bodenbelag", "2.20", "normal", "Aufbauhöhe", "Planung", 1.0, "psch", 4),
    ("LV_92", "Bodenbelag", "2.30", "normal", "Sockelleiste", "VERWORFENES ZITAT Sockelleiste", 40.0, "m", 5),
    ("LV_92", "Bodenbelag", "2.40", "lump_sum", "Belag", "UNKLARES ZITAT zwei", 1.0, "psch", 5),
])]
# (list, item number, kind) of the rows that a confirmed finding cites and that stand in items.json.
CITED = {("LV_91", "1", "Vorbemerkung"), ("LV_92", "2.10", "Randdämmstreifen"),
         ("LV_91", "1.10", "Zementestrich CT-C25-F4"), ("LV_92", "2.20", "Aufbauhöhe")}
NEVER = ["VERWORFEN", "VERWERFER", "UNKLARE", "OFFENE", "GEIST", "X3-ccc333", "X2-ddd444", "X3-eee555", "X9-gone99",
         "4321", "4.321", "8765", "8.765"]


def export_data(findings=FINDINGS, items=ITEMS, reviews=REVIEWS, **more):
    return model.build(findings, items, reviews, "P1", now=NOW, **more)


def docx_text(content):
    document = Document(io.BytesIO(content))
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        parts += [cell.text for row in table.rows for cell in row.cells]
    properties = document.core_properties
    parts += [properties.title or "", properties.author or "", properties.last_modified_by or "",
              properties.comments or "", properties.subject or "", properties.keywords or ""]
    for section in document.sections:
        parts += [paragraph.text for paragraph in section.header.paragraphs + section.footer.paragraphs]
    return "\n".join(parts)


def xlsx_cells(content):
    """Every cell of every sheet as (sheet, row, column, value, marked)."""
    book = load_workbook(io.BytesIO(content))
    cells = []
    for sheet in book.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                marked = cell.fill.fill_type == "solid" and str(cell.fill.start_color.rgb).endswith(files.MARK_COLOUR)
                if cell.value is not None or marked:
                    cells.append((sheet.title, cell.row, cell.column, cell.value, marked))
    return book, cells


def xlsx_text(content):
    book, cells = xlsx_cells(content)
    parts = list(book.sheetnames) + [book.properties.title or "", book.properties.creator or ""]
    return "\n".join(parts + [str(value) for _, _, _, value, _ in cells if value is not None])


def html_text(page):
    """The text a reader sees: no style block, no tags, entities resolved."""
    body = re.sub(r"<style>.*?</style>", " ", page, flags=re.S)
    return html.unescape(re.sub(r"<[^>]+>", "\n", body))


def all_three(data):
    return {"docx": docx_text(files.fragenliste_docx(data)), "xlsx": xlsx_text(files.lv_markiert_xlsx(data)),
            "html": html_text(files.risikobericht_html(data))}


@pytest.fixture(scope="module")
def texts():
    return all_three(export_data())


# ---- only confirmed findings, both quotes word for word ----------------------------

def test_model_holds_the_confirmed_findings_in_the_order_of_their_level():
    data = export_data()
    assert [entry["id"] for entry in data["confirmed"]] == CONFIRMED
    assert [entry["nr"] for entry in data["confirmed"]] == [1, 2, 3]
    assert data["confirmed_by"] == ["Bauleiterin (Team)", "Kalkulator (Mentor)"] and data["by_missing"] is True
    counts = data["counts"]
    assert (counts["findings"], counts["confirmed"], counts["rejected"], counts["unclear"], counts["open"]) == (6, 3, 1, 1, 1)
    assert (counts["lists"], counts["positions"], counts["headings"], counts["preliminary_notes"]) == (2, 7, 2, 1)
    assert counts["reviews_without_finding"] == 1
    assert data["skeptic"] == [("survived", 3), ("weakened", 2), ("refuted", 1)]
    assert data["weakened_split"] == (1, 1)


def test_weakened_split_reads_agent_status():
    def verdict(status, agent_status=None):
        skeptic = {"status": status}
        if agent_status is not None:
            skeptic["agent_status"] = agent_status
        return {"skeptic": skeptic}

    findings = [verdict("weakened", "weakened"), verdict("weakened", "survived"), verdict("weakened", "survived"),
                verdict("weakened"), verdict("survived", "survived"), verdict("refuted", "refuted"), {"skeptic": None}]
    assert model.weakened_split(findings) == (2, 2)
    assert model.weakened_split([]) == (0, 0)


@pytest.mark.parametrize("kind", ["docx", "xlsx", "html"])
def test_only_confirmed_findings_appear(texts, kind):
    text = texts[kind]
    for fid in CONFIRMED:
        assert fid in text, fid
    for entry in FINDINGS:
        shown = entry["id"] in CONFIRMED
        assert (entry["question_de"] in text) is shown, entry["id"]
        assert (entry["explanation_de"] in text) is shown, entry["id"]
        for cited in entry["sources"]:
            assert (cited["quote"] in text) is shown, entry["id"]
    for word in NEVER:
        assert word not in text, word


@pytest.mark.parametrize("kind", ["docx", "xlsx", "html"])
def test_both_quotes_of_a_finding_between_lists_stand_word_for_word(texts, kind):
    for quote in (QUOTE_A1, QUOTE_A2, QUOTE_B1, QUOTE_B2):
        assert texts[kind].count(quote) == 1, quote


@pytest.mark.parametrize("kind", ["docx", "xlsx", "html"])
def test_umlauts_and_sharp_s_survive(texts, kind):
    for word in ("Randdämmstreifen", "Maß", "schließen", "Aufbauhöhe", "Größe", "Straße", "Fußnote", "Wärmedämmung",
                 "Lücke" if kind == "nothing" else "Widerspruch", "bestätigt" if kind == "html" else "Bestätigt"):
        assert word in texts[kind], word
    assert "Ã" not in texts[kind] and "\ufffd" not in texts[kind]


@pytest.mark.parametrize("kind", ["docx", "xlsx", "html"])
def test_type_is_named_as_the_screen_names_it(texts, kind):
    assert "Doppelt ausgeschrieben" in texts[kind] and "Widerspruch" in texts[kind]
    assert "eigene_art" in texts[kind]  # a type without a German word is shown as the file has it
    for raw in ("double_assignment", "contradiction", "confirmed", "between_lists"):
        assert raw not in texts[kind], raw
    script = open(os.path.join(STATIC_DIR, "app.js"), encoding="utf-8").read()
    for name, pairs in (("TYPE", T.ART), ("SEVERITY", T.SCHWERE), ("STATUS", T.STATUS)):
        on_screen = dict(re.findall(r'(\w+): "([^"]+)"', re.search(r"const %s = \{(.*?)\};" % name, script).group(1)))
        assert on_screen == pairs, name
    on_screen = dict(re.findall(r'(\w+): "([^"]+)"', re.search(r"const SKEPTIC = \{(.*?)\};", script).group(1)))
    assert all(T.GEGENPRUEFUNG[key] == word for key, word in on_screen.items())


# ---- no price ------------------------------------------------------------------------

def price_forms(number):
    whole, cents = ("%.2f" % number).split(".")
    grouped = re.sub(r"\B(?=(\d{3})+$)", ".", whole)
    return {"%s.%s" % (whole, cents), "%s,%s" % (whole, cents), "%s,%s" % (grouped, cents), whole, grouped}


@pytest.mark.parametrize("kind", ["docx", "xlsx", "html"])
def test_no_price_key_and_no_price_value_in_any_file(texts, kind):
    text = texts[kind]
    for key in ("unit_price", "total", "price_mode", "priced", "Einheitspreis", "Gesamtpreis"):
        assert key not in text, key
    for record in ITEMS:
        for form in price_forms(record["unit_price"]) | price_forms(record["total"]):
            assert form not in text, form


def test_no_price_in_the_raw_files_and_no_price_number_in_a_cell():
    data = export_data()
    assert not any("price" in key or key == "total" for row in data["items"] for key in row)
    page = files.risikobericht_html(data)
    book, cells = xlsx_cells(files.lv_markiert_xlsx(data))
    prices = set(record["unit_price"] for record in ITEMS) | set(record["total"] for record in ITEMS)
    for _, _, _, value, _ in cells:
        assert not (isinstance(value, (int, float)) and value in prices)
    for record in ITEMS:
        for form in price_forms(record["unit_price"]) | price_forms(record["total"]):
            assert form not in page
    heads = set(value for sheet in book.worksheets for value in next(sheet.iter_rows(min_row=1, max_row=1, values_only=True)))
    assert not heads & {"unit_price", "total", "Einheitspreis", "Gesamtpreis", "EP", "GP", "Preis", "Betrag"}


def test_estimate_of_the_reviewer_stands_only_next_to_its_finding_in_the_report():
    data = export_data()
    page = files.risikobericht_html(data)
    text = html_text(page)
    assert text.count("€") == 1 and "Schätzung des Prüfers: 1.500,50 €" in text
    article = re.search(r'<article class="finding" data-id="X1-aaa111">.*?</article>', page, re.S).group(0)
    assert "1.500,50 €" in article and "Kommentar des Prüfers: Gehört zum Estrich, größte Mühe." in html.unescape(article)
    for other in (docx_text(files.fragenliste_docx(data)), xlsx_text(files.lv_markiert_xlsx(data))):
        assert "€" not in other and "1.500,50" not in other and "1500.5" not in other
    assert files.euro_text(0) == "0,00" and files.euro_text(1234567.891) == "1.234.567,89"


# ---- Fragen_und_Klaerungsliste.docx ----------------------------------------------------

def test_docx_head_and_blocks():
    document = Document(io.BytesIO(files.fragenliste_docx(export_data())))
    assert document.paragraphs[0].text == "Fragen- und Klärungsliste"
    head = [[cell.text for cell in row.cells] for row in document.tables[0].rows]
    assert head == [["Projekt", "P1"], ["Datum", "21.11.2026"], ["Anzahl der Fragen", "3"],
                    ["Bestätigt von", "Bauleiterin (Team), Kalkulator (Mentor), ohne Angabe"]]
    lines = [paragraph.text for paragraph in document.paragraphs]
    assert T.FRAGENLISTE_EINLEITUNG in lines and T.FRAGENLISTE_SCHLUSS in lines and T.FRAGENLISTE_LEER not in lines
    assert [line for line in lines if line.startswith("Frage ")] == ["Frage 1", "Frage 2", "Frage 3"]
    assert lines.index("Frage 1") < lines.index(FINDINGS[1]["question_de"]) < lines.index("Frage 2")
    assert "Art: Widerspruch · Fund X2-bbb222" in lines and "Art: Doppelt ausgeschrieben · Fund X1-aaa111" in lines
    assert "Erläuterung: " + FINDINGS[0]["explanation_de"] in lines
    assert "Bestätigt von Kalkulator (Mentor) (am 21.11.2026, 10:42 Uhr)" in lines
    assert "Bestätigt; die Rolle des Prüfers ist nicht eingetragen" in lines  # no role in the review: none is made up
    assert len(document.tables) == 4
    block = [[cell.text for cell in row.cells] for row in document.tables[2].rows]  # second block: X1-aaa111
    assert block == [["Liste", "Gewerk", "Position", "Seite", "Zitat"],
                     ["LV_91", "Estrich", "1", "1", QUOTE_A1], ["LV_92", "Bodenbelag", "2.10", "3", QUOTE_A2]]
    assert [cell.text for cell in document.tables[3].rows[1].cells] == [
        "LV_93", "", "9.9", "7", "=Zitat aus einer Liste ohne Positionen, Straße"]
    section = document.sections[0]
    assert (round(section.page_width.mm), round(section.page_height.mm)) == (210, 297)
    assert document.core_properties.author == "LV-Prüfstand"


# ---- LV_markiert.xlsx -------------------------------------------------------------------

def test_xlsx_sheets_columns_and_marked_rows():
    book, cells = xlsx_cells(files.lv_markiert_xlsx(export_data()))
    assert book.sheetnames == ["Bestätigte Funde", "LV_91", "LV_92"]  # one sheet per list, the findings first
    for name in ("LV_91", "LV_92"):
        rows = list(book[name].iter_rows(values_only=True))
        assert rows[0] == ("Liste", "Position", "Kurztext", "Menge", "Einheit", "Seite", "Fund", "Art", "Frage")
        wanted = [record for record in ITEMS if record["doc"] == name]
        assert [row[:6] for row in rows[1:]] == [
            (r["doc"], r["item_no"], r["short_text"], r["quantity"], r["unit"], r["page"]) for r in wanted]
    marked_rows = set((sheet, row) for sheet, row, _, _, marked in cells if marked)
    marked = set()
    for sheet, row in marked_rows:
        values = [cell.value for cell in book[sheet][row]]
        marked.add((values[0], values[1], values[2]))
        assert all(cell.fill.fill_type == "solid" for cell in book[sheet][row])  # the whole row is filled
        assert values[6] and values[7] and values[8]
    assert marked == CITED
    assert all(sheet != "Bestätigte Funde" for sheet, _ in marked_rows)
    for sheet in ("LV_91", "LV_92"):  # a row that is not marked carries no finding
        for row in book[sheet].iter_rows(min_row=2):
            if (sheet, row[0].row) not in marked_rows:
                assert [cell.value for cell in row[6:9]] == [None, None, None]
    note = [cell.value for cell in book["LV_91"][3]]
    assert note[:3] == ["LV_91", "1", "Vorbemerkung"]  # the note that holds the quote, not the heading "1" above it
    assert note[6:] == ["X1-aaa111", "Doppelt ausgeschrieben", FINDINGS[0]["question_de"]]


def test_xlsx_first_sheet_lists_the_confirmed_findings_with_their_sources():
    book, _ = xlsx_cells(files.lv_markiert_xlsx(export_data()))
    rows = list(book["Bestätigte Funde"].iter_rows(values_only=True))
    assert rows[0][0] == "LV markiert"
    assert rows[1][0] == "Projekt: P1 · Datum: 21.11.2026 · Bestätigte Funde: 3"
    assert rows[2][0] == T.LV_HINWEIS
    start = rows.index(("Nr.", "Fund", "Art", "Schwere", "Frage", "Erläuterung", "Liste", "Position", "Seite", "Zitat",
                        "Blatt", "Zeile"))
    table = rows[start + 1:]
    assert [(row[0], row[1], row[6], row[7], row[8]) for row in table] == [
        (1, "X2-bbb222", "LV_91", "1.10", 2), (1, "X2-bbb222", "LV_92", "2.20", 4),
        (2, "X1-aaa111", "LV_91", "1", 1), (2, "X1-aaa111", "LV_92", "2.10", 3), (3, "S-fff666", "LV_93", "9.9", 7)]
    assert table[0][2:5] == ("Widerspruch", "hoch", FINDINGS[1]["question_de"])
    assert table[2][9] == QUOTE_A1 and table[3][9] == QUOTE_A2
    assert (table[2][10], table[2][11]) == ("LV_91", 3) and (table[3][10], table[3][11]) == ("LV_92", 3)
    assert table[4][10] == table[4][11] == "steht nicht in items.json"  # LV_93 has no item in items.json
    assert table[4][2:4] == ("eigene_art", "eigene_stufe")


def test_xlsx_text_that_starts_like_a_formula_stays_text():
    book = load_workbook(io.BytesIO(files.lv_markiert_xlsx(export_data())))
    cell = book["LV_91"]["C5"]
    assert cell.value == "=SUMME(A1:A2)" and cell.data_type == "s"
    quote = [cell for row in book["Bestätigte Funde"].iter_rows() for cell in row
             if cell.value == "=Zitat aus einer Liste ohne Positionen, Straße"]
    assert len(quote) == 1 and quote[0].data_type == "s"
    for sheet in book.worksheets:
        assert not any(cell.data_type == "f" for row in sheet.iter_rows() for cell in row)


def test_xlsx_sheet_names_are_valid_and_unique():
    names = files.sheet_names(["LV/1:a", "lv_1_a", "LV_1_A", "x" * 40, "x" * 40 + "y", "Bestätigte Funde", "[a]*?", ""],
                              ["Bestätigte Funde"])
    values = list(names.values())
    assert len(set(value.lower() for value in values)) == len(values) == 8
    for value in values:
        assert 1 <= len(value) <= 31 and not re.search(r"[\\/?*\[\]:]", value)
    items = [item("LV/1:a", "A", "1", "normal", "eins", "", 1.0, "m", 1, 0), item("lv_1_a", "B", "1", "normal", "zwei", "", 1.0, "m", 1, 1)]
    book = load_workbook(io.BytesIO(files.lv_markiert_xlsx(export_data(findings=[], items=items, reviews={}))))
    assert len(book.sheetnames) == 3


# ---- Risikobericht.html -----------------------------------------------------------------

def test_report_summary_findings_and_boxes():
    data = export_data()
    page = files.risikobericht_html(data)
    text = html_text(page)
    assert page.startswith('<!DOCTYPE html>\n<html lang="de">') and '<meta charset="utf-8">' in page
    summary = re.search(r'<section id="zusammenfassung">(.*?)</section>', page, re.S).group(1)
    numbers = re.findall(r'<div class="number[^"]*"><b>([^<]*)</b>([^<]*)</div>', summary)
    assert numbers == [("2", "Leistungsverzeichnisse (Listen)"), ("7", "Positionen"), ("6", "Funde"),
                       ("3", "bestätigt"), ("1", "verworfen"), ("1", "unklar"), ("1", "offen")]
    assert "Nicht als Positionen gezählt: Überschriften 2, Vorbemerkungen 1." in summary
    assert T.BERICHT_BEWERTUNG_OHNE_FUND.format(anzahl=1) in html.unescape(summary)
    # The confirmed findings, the most severe first, each with its question and both quotes.
    articles = re.findall(r'<article class="finding" data-id="([^"]+)">(.*?)</article>', page, re.S)
    assert [fid for fid, _ in articles] == CONFIRMED
    first = html_text(articles[0][1])
    assert "1. " + FINDINGS[1]["question_de"] in first and QUOTE_B1 in first and QUOTE_B2 in first
    assert "Schwere: hoch" in first and "Art: Widerspruch" in first and "Position 1.10 · Seite 2" in first
    assert "Liste: LV_91 · Estrich" in first and "Bestätigt von Bauleiterin (Team) (am 21.11.2026, 10:47 Uhr)" in first
    assert "Schwere: eigene_stufe" in html_text(articles[2][1])
    assert "Bestätigt; die Rolle des Prüfers ist nicht eingetragen" in html_text(articles[2][1])
    method = re.search(r'<section class="box" id="methode">(.*?)</section>', page, re.S).group(1)
    assert re.findall(r"<p>(.*?)</p>", method) == [html.escape(sentence) for sentence in T.BERICHT_METHODE_SAETZE]
    assert 3 <= len(T.BERICHT_METHODE_SAETZE) <= 4
    box = " ".join(html_text(re.search(r'<section class="box" id="messung">(.*?)</section>', page, re.S).group(1)).split())
    assert "Gelesen: Leistungsverzeichnisse (Listen): 2 · Positionen: 7 · Funde: 6" in box
    assert "Bewertung: 3 bestätigt · 1 verworfen · 1 unklar · 1 offen" in box
    assert ("Gegenprüfung (zweiter Durchgang und Zahlenregel): 3 bestanden · 2 abgeschwächt "
            "(1 vom zweiten Durchgang abgeschwächt, 1 von der Zahlenregel herabgestuft) · 1 widerlegt") in box
    assert "Die Messung ist noch nicht gelaufen." in box
    assert T.BERICHT_SCHLUSS in text


def test_report_is_built_for_print_and_needs_no_outside_resource():
    page = files.risikobericht_html(export_data())
    assert re.search(r"@page\s*\{\s*size:\s*A4;", page) and "@media print" in page and "break-inside: avoid" in page
    assert not re.search(r"https?:|//[a-z0-9.-]+\.[a-z]{2,}/|@import|url\(|<script|<img|<link|<iframe|\son\w+=", page, re.I)
    assert page.count("<style>") == 1 and "color-scheme: light" in page


def test_a_quote_with_angle_brackets_or_an_ampersand_does_not_break_the_html():
    page = files.risikobericht_html(export_data())
    assert "Fuge &lt; 5 mm &amp; &quot;dicht&quot; schließen." in page
    assert "Größe &lt;b&gt;fett&lt;/b&gt;" in page and "<b>fett</b>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page and "<script" not in page
    from html.parser import HTMLParser

    class Quotes(HTMLParser):
        def __init__(self):
            HTMLParser.__init__(self)
            self.open, self.found, self.depth = False, [], 0

        def handle_starttag(self, tag, attrs):
            self.depth += 1
            if tag == "blockquote":
                self.open = True
                self.found.append("")
            elif self.open:
                raise AssertionError("a tag inside a quote: %s" % tag)

        def handle_endtag(self, tag):
            self.depth -= 1
            if tag == "blockquote":
                self.open = False

        def handle_data(self, data):
            if self.open:
                self.found[-1] += data

    parser = Quotes()
    parser.feed(page)
    parser.close()
    assert parser.found == [QUOTE_B1, QUOTE_B2, QUOTE_A1, QUOTE_A2, "=Zitat aus einer Liste ohne Positionen, Straße"]


def test_measurement_box_shows_the_lines_of_bench_json_as_they_are(tmp_path):
    lines = ["Zwillingsvergleich: 157 von 159 Positionen gleich", "Eingebaute Fehler: 9 von 10 <gefunden> & gezählt"]
    for content in (json.dumps({"lines": lines}), json.dumps(lines)):
        path = tmp_path / "bench.json"
        path.write_text(content, encoding="utf-8")
        page = files.risikobericht_html(export_data(bench=model._bench(str(path))))
        box = re.search(r'<section class="box" id="messung">(.*?)</section>', page, re.S).group(1)
        assert re.findall(r"<li>([^<]*)</li>", box.split('class="bench"')[1]) == [html.escape(line) for line in lines]
        assert T.BERICHT_MESSUNG_FEHLT not in page
    (tmp_path / "bench.json").write_text(json.dumps({"M1": "157 von 159", "M3": {"gefunden": 9}}), encoding="utf-8")
    assert model._bench(str(tmp_path / "bench.json")) == ("ok", ["M1: 157 von 159", 'M3: {"gefunden": 9}'])
    (tmp_path / "bench.json").write_text("{ not json", encoding="utf-8")
    page = files.risikobericht_html(export_data(bench=model._bench(str(tmp_path / "bench.json"))))
    assert html.escape(T.BERICHT_MESSUNG_UNLESBAR) in page and T.BERICHT_MESSUNG_FEHLT not in page
    assert model._bench(str(tmp_path / "none.json")) == ("missing", [])


def test_committed_bench_gives_the_german_lines_of_bench_table(tmp_path):
    from bench import run as bench_run
    from bench import table as bench_table
    data = {"measured_at": "2026-11-21T11:50", "measurements": [
        {"id": "M8", "name": "False alarms", "threshold": "≤ 5", "met": "no",
         "clean": {"file": "CLEAN.D86", "items": 200, "high_medium": 30, "per_100_hundredths": 1500}, "other": None},
        {"id": "M5", "name": "Expert verdict", "threshold": "x", "met": "not measured yet",
         "reason": "not measured yet: the expert session is Saturday 10:00 to 14:00", "file": "reviews/79-222.json",
         "file_found": False}]}
    path = tmp_path / "bench.json"
    write_json(path, data)
    state, lines = model.committed_bench(bench_run.REPORT_PROJECT, str(path))
    assert state == "committed" and lines == bench_table.lines_de(data)
    assert any(line.startswith("M8 ") and line.endswith("Schwelle eingehalten: nicht erfüllt.") for line in lines)
    assert model.committed_bench("P1", str(path)) == ("missing", [])
    assert model.committed_bench(bench_run.REPORT_PROJECT, str(tmp_path / "none.json")) == ("missing", [])
    path.write_text("{ not json", encoding="utf-8")
    assert model.committed_bench(bench_run.REPORT_PROJECT, str(path)) == ("unreadable", [])


def test_report_of_the_bench_project_falls_back_to_the_committed_bench(tmp_path, monkeypatch):
    from bench import run as bench_run
    from bench import table as bench_table
    committed = tmp_path / "committed.json"
    data = {"measured_at": "2026-11-21T11:50", "measurements": [
        {"id": "M8", "name": "False alarms", "threshold": "≤ 5", "met": "no",
         "clean": {"file": "CLEAN.D86", "items": 200, "high_medium": 30, "per_100_hundredths": 1500}, "other": None}]}
    write_json(committed, data)
    monkeypatch.setattr(bench_run, "RESULTS_PATH", str(committed))
    monkeypatch.setattr(files, "browser", lambda: None)
    arguments = project(tmp_path, name=bench_run.REPORT_PROJECT)
    out = tmp_path / "out" / bench_run.REPORT_PROJECT
    assert command.main(arguments) == 0
    page = read_files(out / "export")["html"]
    assert T.BERICHT_MESSUNG_FEHLT not in page
    assert T.BERICHT_MESSUNG_GESPEICHERT == "Gespeicherter Messlauf aus dem Repository, nicht auf diesem Rechner gemessen."
    assert T.BERICHT_MESSUNG_GESPEICHERT in page
    for line in bench_table.lines_de(data):
        assert line in page
    write_json(out / "bench.json", {"lines": ["Messlauf dieses Rechners"]})
    assert command.main(arguments) == 0
    page = read_files(out / "export")["html"]
    assert T.BERICHT_MESSUNG_GESPEICHERT not in page
    assert "Messlauf dieses Rechners" in page and bench_table.lines_de(data)[1] not in page


def test_every_number_of_the_report_comes_from_a_file():
    """K12: a number in the report is a count over the files, a date, or stands in the data itself."""
    data = export_data()
    text = html_text(files.risikobericht_html(data))
    allowed = set(str(value) for value in data["counts"].values())
    allowed |= set(str(amount) for _, amount in data["skeptic"]) | {"21", "11", "2026"} | {"1", "2", "3"}  # date, Nr.
    for entry in FINDINGS:
        if entry["id"] in CONFIRMED:
            texts = [entry["id"], entry["question_de"], entry["explanation_de"]]
            texts += [str(value) for cited in entry["sources"] for value in cited.values()]
            review = REVIEWS[entry["id"]]
            texts += [review["at"], review["by"], review["comment"]]
            if review["eur_estimate"] is not None:
                texts.append(files.euro_text(review["eur_estimate"]))
            for part in texts:
                allowed |= set(re.findall(r"\d+", part))
    assert set(re.findall(r"\d+", text)) <= allowed


# ---- edge cases ---------------------------------------------------------------------------

def test_zero_confirmed_findings_still_gives_three_files_that_say_so():
    reviews = {key: value for key, value in REVIEWS.items() if value["status"] != "confirmed" or key == "X9-gone99"}
    data = export_data(reviews=reviews)
    assert data["confirmed"] == []
    document = Document(io.BytesIO(files.fragenliste_docx(data)))
    lines = [paragraph.text for paragraph in document.paragraphs]
    assert "Es gibt noch keinen bestätigten Fund. Diese Liste enthält deshalb keine Fragen." in lines
    assert [cell.text for cell in document.tables[0].column_cells(1)] == ["P1", "21.11.2026", "0", "noch kein Fund bestätigt"]
    assert len(document.tables) == 1 and not any(line.startswith("Frage ") for line in lines)
    book, cells = xlsx_cells(files.lv_markiert_xlsx(data))
    assert book.sheetnames == ["Bestätigte Funde", "LV_91", "LV_92"] and not any(marked for *_, marked in cells)
    first = [row[0] for row in book["Bestätigte Funde"].iter_rows(values_only=True)]
    assert "Projekt: P1 · Datum: 21.11.2026 · Bestätigte Funde: 0" in first and T.LV_LEER in first
    assert book["LV_91"].max_row == 6
    page = files.risikobericht_html(data)
    assert "Es gibt noch keinen bestätigten Fund." in page and "<article" not in page
    for text in all_three(data).values():
        for entry in FINDINGS:
            assert entry["question_de"] not in text
        assert "GEIST" not in text and "X9-gone99" not in text


@pytest.mark.parametrize("findings,items,reviews", [
    ([], [], {}),
    (FINDINGS, [], REVIEWS),
    ([{"id": "X1-000001"}], ITEMS, {"X1-000001": {"status": "confirmed"}}),
    ([{"id": "X1-000002", "sources": [None, {}, {"doc": 5, "page": "x", "quote": None}], "type": None,
       "severity": 3, "skeptic": "x"}], ITEMS, {"X1-000002": {"status": "confirmed", "by": None, "eur_estimate": "12"}}),
    (FINDINGS, ITEMS, {"X1-aaa111": "confirmed", "X2-bbb222": {"status": 1}, "X3-ccc333": None}),
])
def test_thin_or_odd_data_gives_files_and_no_crash(findings, items, reviews):
    data = export_data(findings=findings, items=items, reviews=reviews, items_usable=bool(items))
    Document(io.BytesIO(files.fragenliste_docx(data)))
    book = load_workbook(io.BytesIO(files.lv_markiert_xlsx(data)))
    page = files.risikobericht_html(data)
    assert book.sheetnames[0] == "Bestätigte Funde" and page.rstrip().endswith("</html>")
    if not items:
        assert book.sheetnames == ["Bestätigte Funde"]
        assert T.LV_OHNE_POSITIONEN in xlsx_text(files.lv_markiert_xlsx(data)) and html.escape(T.BERICHT_OHNE_POSITIONEN) in page
        assert "nicht bekannt" in page


def test_characters_that_no_xml_file_can_hold_are_dropped_and_the_rest_stays():
    odd = finding("X1-0dd001", "gap", "info", [source("LV_91", "1.10", 2, "Zitat\x00 mit\x0b Steuer\x1fzeichen\tund Tab")],
                  "Frage\x07?", "Erklärung\x08.")
    data = export_data(findings=[odd], reviews={"X1-0dd001": {"status": "confirmed", "by": "Rolle\x01", "at": "gestern"}})
    for kind, text in all_three(data).items():
        assert "Zitat mit Steuerzeichen\tund Tab" in text and "Frage?" in text and "\x00" not in text, kind
        assert ("Rolle" in text) is (kind != "xlsx")  # LV_markiert names no reviewer
    assert "Bestätigt von Rolle (am gestern)" in docx_text(files.fragenliste_docx(data))  # a date in another form stays


def test_cited_item_rule():
    items = [{"doc": "A", "item_no": "1", "kind": "heading", "page": 1},
             {"doc": "A", "item_no": "1", "kind": "preliminary_note", "page": 1, "long_text": "erstes"},
             {"doc": "A", "item_no": "1", "kind": "preliminary_note", "page": 4, "long_text": "Das Zitat steht hier."},
             {"doc": "A", "item_no": "1", "kind": "preliminary_note", "page": 6, "long_text": "drittes"},
             {"doc": "B", "item_no": "1", "kind": "heading", "page": 1}]
    assert model.cited_index({"doc": "A", "item_no": "1", "page": 9, "quote": "Das Zitat steht hier."}, items) == 2
    assert model.cited_index({"doc": "A", "item_no": "1", "page": 6, "quote": "steht nirgends"}, items) == 3
    assert model.cited_index({"doc": "A", "item_no": "1", "page": 9, "quote": "steht nirgends"}, items) == 1
    assert model.cited_index({"doc": "A", "item_no": "1", "page": 1, "quote": ""}, items) == 1
    assert model.cited_index({"doc": "B", "item_no": "1", "page": 1, "quote": "x"}, items) == 4
    assert model.cited_index({"doc": "C", "item_no": "1", "page": 1, "quote": "x"}, items) is None


def test_sample_data_is_named_as_sample_data_in_all_three_files():
    for text in all_three(export_data(mode="sample")).values():
        assert "Beispieldaten (synthetisch, keine echten Listen)" in text
    for text in all_three(export_data()).values():
        assert "Beispieldaten" not in text


# ---- the German texts stand in one file ------------------------------------------------------

def fixed_texts():
    for name in dir(T):
        value = getattr(T, name)
        if not name.isupper():
            continue
        if isinstance(value, str):
            yield name, value
        elif isinstance(value, dict):
            for key, text in value.items():
                yield "%s[%s]" % (name, key), text
        else:
            for index, text in enumerate(value):
                yield "%s[%d]" % (name, index), text


def test_fixed_texts_hold_no_number_no_english_word_and_keep_umlauts():
    names = [name for name, _ in fixed_texts()]
    assert len(names) > 80
    english = re.compile(r"\b(review|reviews|finding|findings|item|items|report|summary|check|export|file|page|quote|"
                         r"code|sheet|list|trade|confirmed|rejected|unclear|open|sample|legal|expert|the|and|of)\b", re.I)
    for name, text in fixed_texts():
        assert isinstance(text, str) and text.strip() == text and text, name
        plain = re.sub(r"\{\w+\}|\b\w+\.json\b", "", text)
        assert not re.search(r"\d", plain), name
        assert not english.search(plain), name
        assert not re.search(r"fuer|ueber|pruef|bestaetig|erlaeuter|schaetz|luecke|klaer|groess|gemaess|strasse|"
                             r"ausser|zaehl|enthaelt|eintraeg|blaett|saetz|waehr", plain, re.I), name
        assert not re.search(r"Experte|Fachmann|Sachverständig|geprüft|rechtlich (zulässig|unzulässig)|haftet|VOB", text), name
    everything = " ".join(text for _, text in fixed_texts())
    for word in ("Leistungsverzeichnisse", "Position", "Vorbemerkungen", "Gewerk", "Klärungsliste", "bestätigt",
                 "Lücke", "Prüfer", "Schätzung", "Erläuterung", "abgeschwächt", "Überschriften", "„bestätigt“"):
        assert word in everything, word
    assert "keine Rechtsberatung" in T.BERICHT_SCHLUSS and "nicht rechtlich" in T.FRAGENLISTE_SCHLUSS


def test_every_fixed_text_of_the_three_files_stands_in_texte_de(monkeypatch):
    """Replace every letter of texte_de.py by '#': with data made of digits only, no letter may be left in a file."""
    def mask(text):
        return re.sub(r"\{\w+\}|[^\W\d_]", lambda found: found.group(0) if found.group(0).startswith("{") else "#", text)

    for name in dir(T):
        value = getattr(T, name)
        if not name.isupper():
            continue
        if isinstance(value, str):
            monkeypatch.setattr(T, name, mask(value))
        elif isinstance(value, dict):
            monkeypatch.setattr(T, name, {key: mask(text) for key, text in value.items()})
        else:
            monkeypatch.setattr(T, name, tuple(mask(text) for text in value))
    findings = [
        {"id": "1-1", "type": "gap", "severity": "high", "question_de": "7?", "explanation_de": "8.",
         "sources": [{"doc": "91", "item_no": "1.10", "page": 2, "quote": "123 456"},
                     {"doc": "93", "item_no": "3", "page": None, "quote": ""}], "skeptic": {"status": "survived"}},
        {"id": "1-2", "type": "", "severity": "", "question_de": "", "explanation_de": "", "sources": [],
         "skeptic": {"status": "weakened"}},
        {"id": "1-3", "type": "contradiction", "severity": "info", "question_de": "9?", "explanation_de": "10.",
         "sources": [{"doc": "92", "item_no": "2", "page": 1, "quote": "5"}]},
    ]
    items = [{"doc": "91", "trade": "55", "item_no": "1.10", "kind": "normal", "short_text": "4711", "quantity": 2.0,
              "unit": "2", "page": 2, "unit_price": 1.0, "total": 2.0},
             {"doc": "92", "trade": "56", "item_no": "2", "kind": "heading", "short_text": "12", "page": 1},
             {"doc": "92", "trade": "56", "item_no": "2", "kind": "preliminary_note", "short_text": "13", "page": 1}]
    reviews = {"1-1": {"status": "confirmed", "by": "66", "comment": "77", "eur_estimate": 5.0, "at": "2026-11-21T10:42"},
               "1-2": {"status": "confirmed", "by": "", "comment": "", "eur_estimate": None, "at": ""},
               "1-3": {"status": "confirmed", "by": "67", "comment": "", "eur_estimate": None, "at": "88"},
               "1-9": {"status": "confirmed"}}
    for more in ({"bench": ("ok", ["1 = 2"])}, {"bench": ("committed", ["1 = 2"])}, {"bench": ("unreadable", [])},
                 {"mode": "sample"},
                 {"items_usable": False}):
        data = model.build(findings, [] if "items_usable" in more else items, reviews, "11-111", now=NOW, **more)
        for kind, text in all_three(data).items():
            assert "#" in text
            left = re.findall(r"[^\W\d_]+", text)
            assert left == [], "%s holds fixed text that is not in texte_de.py: %s" % (kind, left[:5])
    empty = model.build(findings, items, {}, "11-111", now=NOW)
    for kind, text in all_three(empty).items():
        assert re.findall(r"[^\W\d_]+", text) == [], kind


def test_other_export_modules_hold_no_german_sentence():
    folder = os.path.join(ROOT, "web", "export")
    for name in sorted(os.listdir(folder)):
        if name.endswith(".py") and name != "texte_de.py":
            source_text = open(os.path.join(folder, name), encoding="utf-8").read()
            assert not re.search(r"[äöüÄÖÜß„“]", source_text), name


# ---- the command ---------------------------------------------------------------------------------

def write_json(path, data):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)


def project(tmp_path, reviews=REVIEWS, name="P1"):
    write_json(tmp_path / "out" / name / "findings.json", FINDINGS)
    write_json(tmp_path / "out" / name / "items.json", ITEMS)
    if reviews is not None:
        write_json(tmp_path / "reviews" / ("%s.json" % name), reviews)
    return ["--project", name, "--data", str(tmp_path / "out"), "--reviews", str(tmp_path / "reviews")]


def read_files(folder):
    with open(os.path.join(str(folder), "Fragen_und_Klaerungsliste.docx"), "rb") as handle:
        document = docx_text(handle.read())
    with open(os.path.join(str(folder), "LV_markiert.xlsx"), "rb") as handle:
        book = xlsx_text(handle.read())
    with open(os.path.join(str(folder), "Risikobericht.html"), encoding="utf-8") as handle:
        page = html_text(handle.read())
    return {"docx": document, "xlsx": book, "html": page}


def test_command_writes_the_files_into_the_export_folder_of_the_project(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(files, "browser", lambda: None)  # a machine without Chrome
    arguments = project(tmp_path)
    assert command.main(arguments) == 0
    folder = tmp_path / "out" / "P1" / "export"
    assert sorted(os.listdir(str(folder))) == ["Fragen_und_Klaerungsliste.docx", "LV_markiert.xlsx", "Risikobericht.html"]
    out = capsys.readouterr().out
    assert "confirmed findings in the files: 3 of 6" in out
    assert "no Chrome or Chromium on this machine" in out and "Risikobericht.pdf was not written" in out
    for text in read_files(folder).values():
        for fid in CONFIRMED:
            assert fid in text
        for word in NEVER:
            assert word not in text
    other = tmp_path / "elsewhere" / "deep"
    assert command.main(arguments + ["--out", str(other)]) == 0
    assert len(os.listdir(str(other))) == 3
    # The command writes nothing but its files: the inputs are as they were.
    assert json.load(open(str(tmp_path / "reviews" / "P1.json"), encoding="utf-8")) == REVIEWS


def test_command_prints_the_pdf_with_chrome(tmp_path, capsys):
    if not files.browser():
        pytest.skip("no Chrome or Chromium on this machine; the HTML is tested above")
    assert command.main(project(tmp_path)) == 0
    path = tmp_path / "out" / "P1" / "export" / "Risikobericht.pdf"
    with open(str(path), "rb") as handle:
        content = handle.read()
    assert content.startswith(b"%PDF-") and len(content) > 5000
    assert "Risikobericht.pdf" in capsys.readouterr().out
    fitz = pytest.importorskip("fitz")
    pages = fitz.open(stream=content, filetype="pdf")
    text = " ".join(" ".join(page.get_text().split()) for page in pages)
    assert abs(pages[0].rect.width - 595) < 2 and abs(pages[0].rect.height - 842) < 2  # A4
    for part in ("Risikobericht", "Zusammenfassung", "Die wichtigsten Funde", "Methode", "Messung", "Welche Estrichdicke",
                 "Nenndicke 65 mm", "Schätzung des Prüfers: 1.500,50 €", "Die Messung ist noch nicht gelaufen."):
        assert part in text, part
    for word in NEVER:
        assert word not in text


def test_command_fails_when_chrome_is_there_but_prints_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(files, "browser", lambda: sys.executable)  # a "browser" that prints no PDF
    assert command.main(project(tmp_path)) == 1
    assert "Risikobericht.pdf was not written" in capsys.readouterr().err
    assert len(os.listdir(str(tmp_path / "out" / "P1" / "export"))) == 3


def test_a_pdf_of_an_earlier_run_does_not_stay_next_to_newer_files(tmp_path, capsys, monkeypatch):
    arguments = project(tmp_path)
    folder = tmp_path / "out" / "P1" / "export"
    monkeypatch.setattr(files, "print_pdf", lambda report: (b"%PDF-1.7 old", None))
    assert command.main(arguments) == 0 and (folder / "Risikobericht.pdf").read_bytes() == b"%PDF-1.7 old"
    monkeypatch.setattr(files, "print_pdf", lambda report: (None, "no Chrome or Chromium on this machine"))
    monkeypatch.setattr(files, "browser", lambda: None)
    assert command.main(arguments) == 0
    assert sorted(os.listdir(str(folder))) == ["Fragen_und_Klaerungsliste.docx", "LV_markiert.xlsx", "Risikobericht.html"]
    assert "Risikobericht.pdf was not written" in capsys.readouterr().out


def test_command_with_zero_confirmed_and_without_a_reviews_file(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "browser", lambda: None)
    assert command.main(project(tmp_path, reviews=None)) == 0
    texts = read_files(tmp_path / "out" / "P1" / "export")
    assert T.FRAGENLISTE_LEER in texts["docx"] and T.LV_LEER in texts["xlsx"] and T.BERICHT_LEER in texts["html"]
    assert not os.path.exists(str(tmp_path / "reviews"))


def test_command_reads_bench_json_of_the_project(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "browser", lambda: None)
    arguments = project(tmp_path)
    write_json(tmp_path / "out" / "P1" / "bench.json", {"lines": ["Zwillingsvergleich: 157 von 159 gleich"]})
    assert command.main(arguments) == 0
    page = read_files(tmp_path / "out" / "P1" / "export")["html"]
    assert "Zwillingsvergleich: 157 von 159 gleich" in page and T.BERICHT_MESSUNG_FEHLT not in page


def test_command_says_what_is_wrong_and_writes_nothing(tmp_path, capsys):
    arguments = project(tmp_path)
    assert command.main(["--project", "P2"] + arguments[2:]) == 2
    assert "findings.json was not found" in capsys.readouterr().err
    assert command.main(["--project", "../P1"] + arguments[2:]) == 2
    (tmp_path / "reviews" / "P1.json").write_text("{ broken", encoding="utf-8")
    assert command.main(arguments) == 2
    assert "kein gültiges JSON" in capsys.readouterr().err
    assert not os.path.exists(str(tmp_path / "out" / "P1" / "export"))
    assert (tmp_path / "reviews" / "P1.json").read_text(encoding="utf-8") == "{ broken"


def test_command_runs_as_python_m_web_export(tmp_path):
    arguments = project(tmp_path)
    done = subprocess.run([sys.executable, "-m", "web.export"] + arguments, cwd=ROOT, capture_output=True, timeout=180)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")[-500:]
    names = os.listdir(str(tmp_path / "out" / "P1" / "export"))
    assert {"Fragen_und_Klaerungsliste.docx", "LV_markiert.xlsx", "Risikobericht.html"} <= set(names)
    assert ("Risikobericht.pdf" in names) is bool(files.browser())


# ---- the download endpoints and the buttons ---------------------------------------------------------

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def client_for(tmp_path, reviews=REVIEWS):
    project(tmp_path, reviews=reviews)
    return TestClient(create_app(out_dir=str(tmp_path / "out"), reviews_dir=str(tmp_path / "reviews")))


def test_endpoints_return_the_files_with_the_right_content_type(tmp_path, monkeypatch):
    client = client_for(tmp_path)
    answer = client.get("/api/export/fragenliste")
    assert answer.status_code == 200 and answer.headers["content-type"] == DOCX_TYPE
    assert answer.headers["content-disposition"] == 'attachment; filename="Fragen_und_Klaerungsliste.docx"'
    assert answer.headers["cache-control"] == "no-store"
    assert FINDINGS[0]["question_de"] in docx_text(answer.content)
    answer = client.get("/api/export/lv-markiert")
    assert answer.status_code == 200 and answer.headers["content-type"] == XLSX_TYPE
    assert answer.headers["content-disposition"] == 'attachment; filename="LV_markiert.xlsx"'
    assert QUOTE_A2 in xlsx_text(answer.content)
    answer = client.get("/api/export/risikobericht?format=html")
    assert answer.status_code == 200 and answer.headers["content-type"] == "text/html; charset=utf-8"
    assert answer.headers["content-disposition"] == 'attachment; filename="Risikobericht.html"'
    assert QUOTE_B1 in html_text(answer.text) and "Größe" in answer.text
    assert client.get("/api/export/risikobericht?format=exe").status_code == 422
    monkeypatch.setattr(files, "print_pdf", lambda report: (b"%PDF-1.7 test", None))
    answer = client.get("/api/export/risikobericht")
    assert answer.headers["content-type"] == "application/pdf" and answer.content == b"%PDF-1.7 test"
    assert answer.headers["content-disposition"] == 'attachment; filename="Risikobericht.pdf"'
    monkeypatch.setattr(files, "print_pdf", lambda report: (None, "no Chrome"))  # no Chrome: the HTML is sent
    answer = client.get("/api/export/risikobericht")
    assert answer.headers["content-type"] == "text/html; charset=utf-8"
    assert answer.headers["content-disposition"] == 'attachment; filename="Risikobericht.html"'
    for path in ("/api/export/fragenliste", "/api/export/lv-markiert", "/api/export/risikobericht"):
        assert client.post(path).status_code == 405


def test_endpoint_prints_the_report_as_pdf_with_chrome(tmp_path):
    if not files.browser():
        pytest.skip("no Chrome or Chromium on this machine")
    answer = client_for(tmp_path).get("/api/export/risikobericht")
    assert answer.status_code == 200 and answer.headers["content-type"] == "application/pdf"
    assert answer.content.startswith(b"%PDF-")


def test_download_is_built_at_that_moment_from_the_current_reviews(tmp_path):
    client = client_for(tmp_path, reviews=None)
    question = FINDINGS[4]["question_de"]
    before = {"docx": docx_text(client.get("/api/export/fragenliste").content),
              "xlsx": xlsx_text(client.get("/api/export/lv-markiert").content),
              "html": html_text(client.get("/api/export/risikobericht?format=html").text)}
    assert all(question not in text for text in before.values()) and T.FRAGENLISTE_LEER in before["docx"]
    posted = client.post("/api/reviews/X3-eee555", json={"status": "confirmed", "by": "Polier (Test)", "comment": "",
                                                         "eur_estimate": "", "project": "P1"})
    assert posted.status_code == 200
    after = {"docx": docx_text(client.get("/api/export/fragenliste").content),
             "xlsx": xlsx_text(client.get("/api/export/lv-markiert").content),
             "html": html_text(client.get("/api/export/risikobericht?format=html").text)}
    for text in after.values():
        assert question in text and "OFFENES ZITAT Trennlage" in text and "X3-eee555" in text
    assert "Polier (Test)" in after["docx"] and "Polier (Test)" in after["html"]
    client.post("/api/reviews/X3-eee555", json={"status": "rejected", "by": "Polier (Test)", "project": "P1"})
    assert question not in docx_text(client.get("/api/export/fragenliste").content)
    # An export reads only: the reviews file holds what the clicks wrote, and out/ holds no new file.
    stored = json.load(open(str(tmp_path / "reviews" / "P1.json"), encoding="utf-8"))
    assert list(stored) == ["X3-eee555"] and stored["X3-eee555"]["status"] == "rejected"
    assert sorted(os.listdir(str(tmp_path / "out" / "P1"))) == ["findings.json", "items.json"]


def test_export_for_another_project_than_the_page_shows_is_refused(tmp_path):
    """The page still shows the samples (or an older project) while out/ holds another project by now."""
    client = client_for(tmp_path)
    for path in ("/api/export/fragenliste", "/api/export/lv-markiert", "/api/export/risikobericht?format=html"):
        mark = "&" if "?" in path else "?"
        assert client.get(path + mark + "project=P1").status_code == 200
        refused = client.get(path + mark + "project=11-111")
        assert refused.status_code == 409 and refused.headers["content-type"] == "application/json"
        assert refused.json()["error"] == ("Die Seite zeigt Projekt 11-111, gelesen wird jetzt Projekt P1. "
                                           "Bitte die Seite neu laden.")
        assert client.get(path).status_code == 200  # a plain address, without a page, gets the file


def test_export_does_not_use_the_k3_filter_and_leaves_the_other_endpoints_as_they_are(tmp_path):
    client = client_for(tmp_path)
    data = client.get("/api/findings").json()
    held = [entry["id"] for entry in data["findings"] if not entry["k3_pass"]]
    assert "X2-bbb222" in held  # weakened, so the K3 queue holds it back; it is confirmed, so the export has it
    assert "X2-bbb222" in docx_text(client.get("/api/export/fragenliste").content)
    assert data["counters"]["all"]["confirmed"] == 3 and data["counters"]["reviews_without_finding"] == 1


def test_endpoints_report_a_broken_reviews_file_and_do_not_touch_it(tmp_path):
    client = client_for(tmp_path)
    (tmp_path / "reviews" / "P1.json").write_text("{ broken", encoding="utf-8")
    for path in ("/api/export/fragenliste", "/api/export/lv-markiert", "/api/export/risikobericht"):
        answer = client.get(path)
        assert answer.status_code == 500 and "kein gültiges JSON" in answer.json()["error"]
    assert (tmp_path / "reviews" / "P1.json").read_text(encoding="utf-8") == "{ broken"


def test_endpoints_work_on_the_sample_data_and_say_that_it_is_sample_data(tmp_path):
    client = TestClient(create_app(out_dir=str(tmp_path / "out"), reviews_dir=str(tmp_path / "reviews")))
    assert client.get("/api/findings").json()["mode"] == "sample"
    assert "Beispieldaten (synthetisch, keine echten Listen)" in docx_text(client.get("/api/export/fragenliste").content)
    assert "Beispieldaten" in xlsx_text(client.get("/api/export/lv-markiert").content)
    assert "Beispieldaten" in client.get("/api/export/risikobericht?format=html").text


def test_both_views_have_the_three_export_buttons():
    page = open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8").read()
    fund = page[page.index('id="view-fund"'):page.index('id="view-pruefen"')]
    pruefen = page[page.index('id="view-pruefen"'):]
    wanted = [("/api/export/fragenliste", "Fragen_und_Klaerungsliste.docx", "Fragenliste exportieren"),
              ("/api/export/lv-markiert", "LV_markiert.xlsx", "LV markiert exportieren"),
              ("/api/export/risikobericht", "Risikobericht.pdf", "Risikobericht exportieren")]
    for view in (fund, pruefen):
        found = re.findall(r'<button type="button" class="export-button" data-export="([^"]+)" data-name="([^"]+)">'
                           r"([^<]+)</button>", view)
        assert found == wanted
        assert view.count('class="export-note"') == 1
    script = open(os.path.join(STATIC_DIR, "app.js"), encoding="utf-8").read()
    assert 'document.querySelectorAll(".export-button")' in script and "await state.saving;" in script
    assert "Export fehlgeschlagen: " in script and "Exportiert: " in script
