"""W8 on the real project 79-222: with a synthetic reviews file that confirms
three real findings, the command writes the three files and they hold those
three findings and no other. Runs only where out/79-222/items.json is built
(AGENTS.md "Data and items.json"); skipped elsewhere. No quote text and no
price is printed: a failing check names the finding id only.
"""
import html
import io
import json
import os
import re
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402
from docx import Document  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from web.export import __main__ as command  # noqa: E402
from web.export import files, model  # noqa: E402

REAL_ITEMS = os.path.join(ROOT, "out", "79-222", "items.json")
COMMITTED_FINDINGS = os.path.join(ROOT, "pipeline", "cross", "results", "79-222", "findings.json")

pytestmark = pytest.mark.skipif(not os.path.exists(REAL_ITEMS), reason="out/79-222/items.json is not built")


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    """Run the command on a copy of the real project with three confirmed findings."""
    folder = tmp_path_factory.mktemp("w8real")
    project = folder / "out" / "79-222"
    os.makedirs(str(project))
    os.makedirs(str(folder / "reviews"))
    shutil.copy(COMMITTED_FINDINGS, str(project / "findings.json"))
    shutil.copy(REAL_ITEMS, str(project / "items.json"))
    findings, items = load(COMMITTED_FINDINGS), load(REAL_ITEMS)
    between = [entry for entry in findings if entry["layer"] == "between_lists"]
    chosen = [next(entry for entry in between if len(entry["sources"]) == 3),
              next(entry for entry in between if len(entry["sources"]) == 2),
              next(entry for entry in findings if entry["layer"] == "single_list")]
    reviews = {entry["id"]: {"status": "confirmed", "by": "Kalkulator (Test)", "comment": "", "eur_estimate": None,
                             "at": "2026-11-21T10:%02d" % number} for number, entry in enumerate(chosen)}
    others = [entry for entry in findings if entry["id"] not in reviews]
    reviews[others[0]["id"]] = {"status": "rejected", "by": "Kalkulator (Test)", "comment": "", "eur_estimate": None,
                                "at": "2026-11-21T11:00"}
    reviews[others[1]["id"]] = {"status": "unclear", "by": "Kalkulator (Test)", "comment": "", "eur_estimate": None,
                                "at": "2026-11-21T11:01"}
    with open(str(folder / "reviews" / "79-222.json"), "w", encoding="utf-8") as handle:
        json.dump(reviews, handle, ensure_ascii=False)
    code = command.main(["--project", "79-222", "--data", str(folder / "out"), "--reviews", str(folder / "reviews")])
    return {"code": code, "folder": str(project / "export"), "findings": findings, "items": items,
            "chosen": chosen, "others": others}


def docx_text(path):
    document = Document(path)
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        parts += [cell.text for row in table.rows for cell in row.cells]
    return "\n".join(parts)


def check_holds_the_three_and_no_other(text, run):
    for entry in run["chosen"]:
        assert entry["id"] in text, entry["id"]
        assert entry["question_de"] in text, entry["id"]
        for source in entry["sources"]:
            assert source["quote"] in text, entry["id"]  # word for word
    chosen_texts = set(entry["question_de"] for entry in run["chosen"])
    chosen_texts |= set(source["quote"] for entry in run["chosen"] for source in entry["sources"])
    for entry in run["others"]:
        assert entry["id"] not in text, entry["id"]
        assert entry["question_de"] not in text, entry["id"]
        assert entry["explanation_de"] not in text, entry["id"]
        for source in entry["sources"]:
            if source["quote"] not in chosen_texts:
                assert source["quote"] not in text, entry["id"]
    assert set(re.findall(r"\b(?:X\d|S|B\d+|V\d)-[0-9a-f]{6}\b", text)) == set(entry["id"] for entry in run["chosen"])


def test_command_writes_the_files(run):
    assert run["code"] == 0
    names = sorted(os.listdir(run["folder"]))
    wanted = ["Fragen_und_Klaerungsliste.docx", "LV_markiert.xlsx", "Risikobericht.html"]
    assert names == sorted(wanted + (["Risikobericht.pdf"] if files.browser() else []))
    assert len(run["chosen"]) == 3 and len(run["findings"]) - len(run["others"]) == 3


def test_docx_holds_the_three_confirmed_findings_and_no_other(run):
    text = docx_text(os.path.join(run["folder"], "Fragen_und_Klaerungsliste.docx"))
    check_holds_the_three_and_no_other(text, run)
    document = Document(os.path.join(run["folder"], "Fragen_und_Klaerungsliste.docx"))
    assert [cell.text for cell in document.tables[0].column_cells(1)][0::2] == ["79-222", "3"]
    assert document.tables[0].cell(3, 1).text == "Kalkulator (Test)"
    assert len(document.tables) == 4
    assert sorted(len(table.rows) - 1 for table in document.tables[1:]) == sorted(
        len(entry["sources"]) for entry in run["chosen"])


def test_report_holds_the_three_confirmed_findings_and_no_other(run):
    with open(os.path.join(run["folder"], "Risikobericht.html"), encoding="utf-8") as handle:
        page = handle.read()
    text = html.unescape(re.sub(r"<[^>]+>", "\n", re.sub(r"<style>.*?</style>", " ", page, flags=re.S)))
    check_holds_the_three_and_no_other(text, run)
    shown = re.findall(r'<article class="finding" data-id="([^"]+)">', page)
    rank = {"high": 0, "medium": 1, "info": 2}
    by_id = {entry["id"]: entry for entry in run["chosen"]}
    assert sorted(shown) == sorted(by_id)
    assert [rank[by_id[fid]["severity"]] for fid in shown] == sorted(rank[by_id[fid]["severity"]] for fid in shown)
    numbers = dict((name, value) for value, name in re.findall(r'<div class="number[^"]*"><b>([^<]*)</b>([^<]*)</div>', page))
    lists = len(set(item["doc"] for item in run["items"]))
    positions = sum(1 for item in run["items"] if item["kind"] not in ("heading", "preliminary_note"))
    assert numbers == {"Leistungsverzeichnisse (Listen)": str(lists), "Positionen": str(positions),
                       "Funde": str(len(run["findings"])), "bestätigt": "3", "verworfen": "1", "unklar": "1",
                       "offen": str(len(run["findings"]) - 5)}
    assert (lists, positions, len(run["findings"])) == (27, 1131, 24)
    assert "€" not in text
    from bench import run as bench_run
    from bench import table as bench_table
    if os.path.exists(bench_run.RESULTS_PATH):  # no out/79-222/bench.json here: the committed run is shown
        lines = bench_table.lines_de(bench_run.read_json(bench_run.RESULTS_PATH))
        assert "Die Messung ist noch nicht gelaufen." not in text
        assert "Gespeicherter Messlauf aus dem Repository, nicht auf diesem Rechner gemessen." in text
        assert [line.split(" ")[0] for line in lines[1:]] == ["M%d" % number for number in range(1, 10)]
        assert len(lines) == 10 and all(line in text for line in lines)
        met = {line.split(" ")[0]: line.rsplit("Schwelle eingehalten: ", 1)[1] for line in lines[1:]}
        assert met["M7"] == met["M8"] == "nicht erfüllt."
    else:
        assert "Die Messung ist noch nicht gelaufen." in text


def test_report_pdf_holds_the_three_questions(run):
    path = os.path.join(run["folder"], "Risikobericht.pdf")
    if not files.browser():
        pytest.skip("no Chrome or Chromium on this machine")
    fitz = pytest.importorskip("fitz")
    with open(path, "rb") as handle:
        content = handle.read()
    assert content.startswith(b"%PDF-")
    text = " ".join(" ".join(page.get_text().split()) for page in fitz.open(stream=content, filetype="pdf"))
    for entry in run["chosen"]:
        assert entry["id"] in text, entry["id"]
    for entry in run["others"]:
        assert entry["id"] not in text, entry["id"]


def test_xlsx_marks_exactly_the_cited_items_and_has_no_price_column(run):
    book = load_workbook(os.path.join(run["folder"], "LV_markiert.xlsx"))
    docs = []
    for item in run["items"]:
        if item["doc"] not in docs:
            docs.append(item["doc"])
    assert book.sheetnames == ["Bestätigte Funde"] + docs  # one sheet per list
    cited = {}
    for entry in run["chosen"]:
        for source in entry["sources"]:
            index = model.cited_index(source, run["items"])
            assert index is not None, entry["id"]
            item = run["items"][index]
            cited.setdefault((item["doc"], item["item_no"], item["short_text"], item["page"]), set()).add(entry["id"])
    marked, rows = {}, 0
    for doc in docs:
        sheet = book[doc]
        head = [cell.value for cell in sheet[1]]
        assert head == ["Liste", "Position", "Kurztext", "Menge", "Einheit", "Seite", "Fund", "Art", "Frage"]
        rows += sheet.max_row - 1
        for row in sheet.iter_rows(min_row=2):
            filled = row[0].fill.fill_type == "solid" and str(row[0].fill.start_color.rgb).endswith(files.MARK_COLOUR)
            if filled:
                marked[(row[0].value, row[1].value, row[2].value, row[5].value)] = set(row[6].value.split("\n"))
            else:
                assert row[6].value is None and row[7].value is None and row[8].value is None
    assert rows == len(run["items"])
    assert marked == cited
    text = "\n".join(str(cell.value) for sheet in book.worksheets for row in sheet.iter_rows() for cell in row
                     if cell.value is not None)
    check_holds_the_three_and_no_other(text, run)
    heads = set(cell.value for sheet in book.worksheets for row in sheet.iter_rows(max_row=8) for cell in row)
    assert not heads & {"unit_price", "total", "price_mode", "Einheitspreis", "Gesamtpreis", "EP", "GP"}


def test_no_price_key_reaches_the_export_data(run):
    data = model.load_project("79-222", out_dir=os.path.dirname(os.path.dirname(run["folder"])),
                              reviews_dir=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(run["folder"]))), "reviews"))
    assert len(data["items"]) == len(run["items"]) and len(data["confirmed"]) == 3
    for row in data["items"]:
        assert sorted(row) == ["doc", "item_no", "kind", "page", "quantity", "short_text", "trade", "unit"]
    assert io.BytesIO(files.lv_markiert_xlsx(data)).getvalue()[:2] == b"PK"
