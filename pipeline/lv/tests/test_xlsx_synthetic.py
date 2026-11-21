"""W16: the Excel reader on made-up workbooks (no organizer file is an Excel list)."""
import io
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

import openpyxl  # noqa: E402
import pytest  # noqa: E402

from pipeline.common import contract  # noqa: E402
from pipeline.lv import model, xlsx  # noqa: E402


def workbook(rows, title="LV", before=None):
    """Bytes of an .xlsx with one sheet: optional rows above, then the given rows."""
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = title
    for row in (before or []) + rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


HEAD = ["Pos.-Nr.", "Kurztext", "Langtext", "Menge", "ME", "EP (€)", "GP in €", "Art"]
ROWS = [
    HEAD,
    ["01", "Erdarbeiten", None, None, None, None, None, None],
    ["01.0010", "Oberboden abtragen", "Oberboden 30 cm abtragen und seitlich lagern.", 120.5, "m2", 4.2, 506.1, None],
    [None, "einschließlich Entsorgung von Wurzeln", None, None, None, None, None, None],
    ["01.0020", "Baugrube ausheben", None, "35,5", "m3", "18,40", "653,20", None],
    ["01.0030", "Wasserhaltung", None, 1, "psch", None, None, None],
    ["01.0040", "Felsabtrag", None, 10, "m3", None, None, "Bedarf"],
    ["01.0050", "Verbau als Alternative", None, 20, "m2", None, None, "Wahl"],
    [None, "Zwischensumme 01", None, None, None, None, 1159.3, None],
    ["02", "Beton", None, None, None, None, None, None],
    ["02.0010", "Fundament C25/30", None, "1.250", "m3", None, None, None],
    ["02.0020", "Stütze", None, "zehn", "St", None, None, None],
]


def test_a_list_is_read_into_the_contract_shape():
    project, records, entry = xlsx.parse_bytes(workbook(ROWS, before=[["Rohbauarbeiten Testhaus"], []]), "Test LV.xlsx")
    contract.check("items", records)
    contract.check("manifest", [entry])
    assert project == "Test_LV"
    assert {record["doc"] for record in records} == {"Test_LV.xlsx"}
    assert {(record["format"], record["stage"], record["trade"]) for record in records} == {("xlsx", "anfrage", "Rohbauarbeiten Testhaus")}
    assert [(r["item_no"], r["kind"]) for r in records] == [
        ("01", "heading"), ("01.0010", "normal"), ("01.0020", "normal"), ("01.0030", "lump_sum"),
        ("01.0040", "optional"), ("01.0050", "alternative"), ("02", "heading"), ("02.0010", "normal"),
        ("02.0020", "normal")]
    first = records[1]
    assert (first["quantity"], first["unit"], first["section"], first["line"]) == (120.5, "m2", "01", 5)
    assert first["long_text"] == "Oberboden 30 cm abtragen und seitlich lagern.\neinschließlich Entsorgung von Wurzeln"
    assert records[2]["quantity"] == 35.5 and records[2]["unit_price"] == 18.4 and records[2]["total"] == 653.2
    assert records[7]["quantity"] == 1250.0  # "1.250": the dot is a thousands mark
    assert records[8]["quantity"] is None
    assert entry["items"] == 7 and entry["headings"] == 2 and entry["sum_rows"] == 1
    assert entry["unparsed_lines"] == 1 and entry["unparsed_line_numbers"] == [14]
    assert any("row 14" in warning and "quantity" in warning for warning in entry["warnings"])
    assert entry["priced_items"] == 2 and entry["price_check"] == {"equal": 2, "not_equal": 0, "no_quantity": 0}
    assert entry["sheet"] == "LV" and "item_no" in entry["columns"]


def test_a_wrong_total_is_named_by_its_item_number_and_no_price_is_printed():
    rows = [["OZ", "Bezeichnung", "Menge", "Einheit", "Einheitspreis", "Gesamtpreis"],
            ["1.1", "Mauerwerk", 10, "m2", 55.5, 999.99]]
    _project, records, entry = xlsx.parse_bytes(workbook(rows), "mauer.xlsx")
    assert entry["price_check"]["not_equal"] == 1
    warning = next(w for w in entry["warnings"] if "not the total" in w)
    assert "1.1" in warning and "999" not in warning and "55" not in warning


def test_the_first_sheet_with_a_heading_row_is_read():
    book = openpyxl.Workbook()
    book.active.title = "Deckblatt"
    book.active.append(["Projekt 4711"])
    sheet = book.create_sheet("Positionen")
    for row in ([], ["Titel"], ["Position", "Leistung", "Menge", "EH"], ["10", "Estrich", 50, "m2"]):
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    _project, records, entry = xlsx.parse_bytes(buffer.getvalue(), "estrich.xlsx", project="P9")
    assert entry["sheet"] == "Positionen"
    assert [(r["project"], r["trade"], r["item_no"], r["quantity"], r["unit"]) for r in records] == [
        ("P9", "Titel", "10", 50.0, "m2")]


def test_text_before_the_first_item_is_a_preliminary_note():
    rows = [["Pos", "Text", "Menge", "ME"], [None, "Vorbemerkung: Alle Arbeiten nach DIN 18300.", None, None],
            ["1", "Aushub", 5, "m3"]]
    _project, records, _entry = xlsx.parse_bytes(workbook(rows), "a.xlsx")
    assert [(r["kind"], r["short_text"]) for r in records] == [
        ("preliminary_note", "Vorbemerkung: Alle Arbeiten nach DIN 18300."), ("normal", "Aushub")]


@pytest.mark.parametrize("raw, words", [
    (b"not a zip", "not an Excel workbook"),
])
def test_a_file_that_is_no_workbook_is_refused(raw, words):
    with pytest.raises(xlsx.XlsxError, match=words):
        xlsx.parse_bytes(raw, "x.xlsx")


def test_a_sheet_without_a_heading_row_is_refused():
    with pytest.raises(xlsx.XlsxError, match="no sheet has a heading row"):
        xlsx.parse_bytes(workbook([["a", "b"], [1, 2]]), "x.xlsx")


def test_heading_names_and_numbers():
    assert [xlsx.heading_key(name) for name in ("Pos.-Nr.", "OZ", "Kurztext", "EP (€)", "GP in €", "Menge", "ME", "foo", None)] == [
        "item_no", "item_no", "short_text", "unit_price", "total", "quantity", "unit", None, None]
    assert xlsx.cell_number("1.250,50") == (1250.5, True)
    assert xlsx.cell_number("12.5") == (12.5, True)
    assert xlsx.cell_number("1.250") == (1250.0, True)
    assert xlsx.cell_number(" 3 ") == (3.0, True)
    assert xlsx.cell_number("") == (None, True)
    assert xlsx.cell_number("ca. 5") == (None, False)
    assert xlsx.cell_text(10.0) == "10" and xlsx.cell_text(None) == ""


def test_the_command_writes_the_project_and_prints_no_price(tmp_path):
    source = tmp_path / "Liste.xlsx"
    source.write_bytes(workbook(ROWS))
    out = tmp_path / "out"
    done = subprocess.run([sys.executable, "-m", "pipeline.lv.xlsx", str(source), str(out)], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    assert "7 items" in done.stdout and "653" not in done.stdout and "18,4" not in done.stdout
    items = json.loads((out / "Liste" / "items.json").read_text(encoding="utf-8"))
    assert len([i for i in items if model.is_position(i)]) == 7


# ---- the findings of the second review (Saturday night) ----

def test_a_decimal_below_one_is_no_thousands_group():
    assert xlsx.cell_number("0.125") == (0.125, True)
    assert xlsx.cell_number("-0.500") == (-0.5, True)
    assert xlsx.cell_number("12.500") == (12500.0, True)


def test_title_totals_sum_rows_repeated_headings_and_text_lines():
    rows = [["Pos", "Kurztext", "Menge", "ME", "EP", "GP"],
            ["01", "Erdarbeiten", None, None, None, 506.1],
            ["01.10", "Oberboden abtragen", 120.5, "m2", 4.2, 506.1],
            [None, "Gesamthöhe der Wand 3,00 m", None, None, None, None],
            ["Summe 01", None, None, None, None, 506.1],
            ["Pos", "Kurztext", "Menge", "ME", "EP", "GP"],
            ["02", "Beton", None, None, None, None]]
    _project, records, entry = xlsx.parse_bytes(workbook(rows, before=[[125000.0], ["Rohbau"]]), "t.xlsx")
    assert [(r["item_no"], r["kind"]) for r in records] == [("01", "heading"), ("01.10", "normal"), ("02", "heading")]
    assert records[1]["long_text"] == "Gesamthöhe der Wand 3,00 m"
    assert (entry["sum_rows"], entry["repeated_heading_rows"], entry["unparsed_lines"]) == (1, 1, 0)
    assert records[0]["trade"] == "Rohbau"  # a number cell above the heading row is no trade


def test_a_broken_workbook_is_refused_with_a_german_reason():
    with pytest.raises(xlsx.XlsxError) as caught:
        xlsx.parse_bytes(b"PK\x03\x04 broken", "x.xlsx")
    assert caught.value.german == "keine Excel-Arbeitsmappe (.xlsx)"
    with pytest.raises(xlsx.XlsxError) as caught:
        xlsx.parse_bytes(workbook([["a", "b"]]), "x.xlsx")
    assert caught.value.german.startswith("keine Tabelle hat eine Kopfzeile")

