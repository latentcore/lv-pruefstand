"""Saturday night additions: "Treffer anzeigen" (GET /api/evidence/<id>), the GAEB 90 record lines of a base
finding in "Live-Prüfung", and an Excel list dropped into "Live-Prüfung". Synthetic data only."""
import io
import json
import os
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "pipeline", "lv", "tests"))

import openpyxl  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from gaeb90_lines import build, end, header, item, prices  # noqa: E402
from pipeline.common import contract  # noqa: E402
from web import views  # noqa: E402
from web.app import create_app  # noqa: E402

# Made-up prices the answers must never show: unit price 98765.43, total 197530.86.
PRICE_TEXTS = ("98765", "9876543", "197530", "19753086")
TWICE = [
    header("86L", "P-TEST-3"),
    item("0100   1 ", "00000002000", "m"),
    prices("0100   1 ", "0009876543", "000019753086", "00000002000"),
    "25Pipe laid in the trench",
    item("0100   1 ", "00000002000", "m"),
    prices("0100   1 ", "0009876543", "000019753086", "00000002000"),
    "25Pipe laid in the trench",
    end(2),
]


@pytest.fixture
def real(tmp_path):
    """The app on a project folder with the contract samples; returns (client, project folder)."""
    folder = tmp_path / "out" / "11-111"
    folder.mkdir(parents=True)
    for name in ("findings", "items"):
        shutil.copy(contract.sample_path(name), str(folder / ("%s.json" % name)))
    return TestClient(create_app(out_dir=str(tmp_path / "out"), reviews_dir=str(tmp_path / "reviews"))), folder


def post(client, raw, name):
    return client.post("/api/live", content=raw, headers={"X-File-Name": name, "Content-Type": "application/octet-stream"})


# ---- GAEB 90 record lines ----------------------------------------------------------------

def test_a_base_finding_of_a_gaeb90_upload_carries_its_record_lines_with_the_prices_masked(real):
    client, _folder = real
    answer = post(client, build(TWICE), "twice.D86")
    assert answer.status_code == 200, answer.text
    data = answer.json()
    duplicate = next(f for f in data["findings"] if f["check"] == "B3")
    assert [(entry["item_no"], entry["line"]) for entry in duplicate["raw"]] == [("01.00.1", 2), ("01.00.1", 5)]
    lines = duplicate["raw"][0]["lines"]
    assert [line["no"] for line in lines] == [2, 3, 4]
    assert lines[0]["text"].startswith("210100   1 NNN") and lines[0]["masked"] is False
    assert lines[1] == {"no": 3, "text": "23  " + views.RAW_MASK, "masked": True}
    assert lines[2]["text"].startswith("25Pipe laid in the trench")
    for text in PRICE_TEXTS:
        assert text not in answer.text


def test_a_record_ends_where_the_next_record_starts():
    lines = ["00 header", "21item", "25short", "26 long", "21next", "25other"]
    assert [line["no"] for line in views.raw_record(lines, 2)] == [2, 3, 4]
    assert views.raw_record(lines, 99) == []


def test_an_xml_upload_carries_no_record_lines(real):
    client, _folder = real
    raw = (b'<?xml version="1.0"?><GAEB xmlns="http://www.gaeb.de/GAEB_DA_XML/DA83/3.2"><Award><DP>83</DP><BoQ>'
           b'<BoQBody><Itemlist><Item RNoPart="0010"><Qty>1</Qty><QU>St</QU></Item><Item RNoPart="0010"><Qty>1</Qty>'
           b'<QU>St</QU></Item></Itemlist></BoQBody></BoQ></Award></GAEB>')
    data = post(client, raw, "x.X83").json()
    assert all("raw" not in finding for finding in data["findings"])


# ---- Excel in Live-Pruefung --------------------------------------------------------------

def test_an_excel_list_is_read_and_checked_and_no_price_goes_back(real):
    client, _folder = real
    book = openpyxl.Workbook()
    for row in (["Pos", "Kurztext", "Menge", "Einheit", "EP", "GP"], ["1", "Abschnitt", None, None, None, None],
                ["1.10", "Rohr verlegen", 2, "m", 98765.43, 197530.86], ["1.20", "", 3, "m", None, None]):
        book.active.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    answer = post(client, buffer.getvalue(), "liste.xlsx")
    assert answer.status_code == 200, answer.text
    data = answer.json()
    assert (data["format"], data["stage"], data["items"], data["headings"]) == ("xlsx", "anfrage", 2, 1)
    assert data["recalculation"] == {"priced": 1, "equal": 1, "not_equal": 0, "no_quantity": 0}
    assert any(finding["check"] == "B8" for finding in data["findings"])  # the empty short text
    for text in PRICE_TEXTS:
        assert text not in answer.text


def test_a_broken_excel_file_is_refused_in_german(real):
    client, _folder = real
    answer = post(client, b"no zip at all", "liste.xlsx")
    assert answer.status_code == 422
    assert "kann nicht als GAEB gelesen werden" in answer.json()["error"] or "Excel" in answer.json()["error"]


# ---- Treffer anzeigen ----------------------------------------------------------------------

def test_without_an_evidence_file_the_button_says_what_to_run(real):
    client, _folder = real
    answer = client.get("/api/evidence/X1-f0a30d")
    assert answer.status_code == 404 and "python -m pipeline.run" in answer.json()["error"]


def test_the_samples_have_no_hits(tmp_path):
    client = TestClient(create_app(out_dir=str(tmp_path / "out"), reviews_dir=str(tmp_path / "reviews")))
    answer = client.get("/api/evidence/X1-f0a30d")
    assert answer.status_code == 404 and "Beispieldaten" in answer.json()["error"]


def test_the_hits_of_a_finding_with_fixed_keys_and_no_price(real):
    client, folder = real
    hit = {"doc": "LV_92", "item_no": "2.10", "page": 25, "kind": "normal", "short_text": "Verguss", "quantity": 12.0,
           "unit": "St", "cited": True, "terms": ["Verguss"], "snippets": ["...a...", "...b...", "...c..."],
           "unit_price": 98765.43, "total": 197530.86, "secret": "x"}
    evidence = {"X1-f0a30d": {"id": "X1-f0a30d", "terms": ["Verguss", "Köcher"], "added_terms": [],
                              "lists_searched": ["LV_91", "LV_92", "AN_93"], "hits_per_list": {"LV_92": 1},
                              "lists_without_hit": ["LV_91", "AN_93"], "hits": [hit] * 100}}
    (folder / "skeptic").mkdir()
    (folder / "skeptic" / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    answer = client.get("/api/evidence/X1-f0a30d")
    assert answer.status_code == 200
    data = answer.json()
    assert data["terms"] == ["Verguss", "Köcher"] and data["hits_per_list"] == [{"doc": "LV_92", "hits": 1}]
    assert data["lists_without_hit"] == ["LV_91", "AN_93"] and data["hits_total"] == 100
    assert len(data["hits"]) == views.MAX_HITS
    assert sorted(data["hits"][0]) == ["cited", "doc", "item_no", "kind", "page", "quantity", "short_text",
                                       "snippets", "terms", "unit"]
    assert data["hits"][0]["snippets"] == ["...a...", "...b..."]
    for text in PRICE_TEXTS + ("secret",):
        assert text not in answer.text
    missing = client.get("/api/evidence/X9-000000")
    assert missing.status_code == 404 and "X9-000000" in missing.json()["error"]


def test_the_page_has_the_button_and_the_record_lines():
    with open(os.path.join(ROOT, "web", "static", "app.js"), encoding="utf-8") as handle:
        script = handle.read()
    assert '"Treffer anzeigen"' in script and "/api/evidence/" in script
    with open(os.path.join(ROOT, "web", "static", "views.js"), encoding="utf-8") as handle:
        script = handle.read()
    assert '"GAEB-Satz zeigen"' in script and ".xlsx" in script


# ---- the findings of the second review (Saturday night) ----

def test_a_record_block_ends_at_the_price_record_of_the_next_item():
    lines = ["2301001 0000012345   000000123450", "25text one", "2301002 0000067890   000000678900", "25text two"]
    block = views.raw_record(lines, 1)
    assert [line["no"] for line in block] == [1, 2]
    assert block[0] == {"no": 1, "text": "23  " + views.RAW_MASK, "masked": True}


def test_every_record_type_but_item_and_text_lines_is_masked():
    lines = ["210100   1 NNN         00000002000m", "28 something with 12345", "25text"]
    block = views.raw_record(lines, 1)
    assert block[1] == {"no": 2, "text": "28  " + views.RAW_MASK_OTHER, "masked": True}
    assert block[2]["text"] == "25text" and block[2]["masked"] is False


def test_a_note_is_shown_for_a_number_only_when_no_other_record_has_it():
    records = [{"item_no": "2", "line": 1, "kind": "preliminary_note"}, {"item_no": "2", "line": 3, "kind": "heading"},
               {"item_no": "5", "line": 5, "kind": "preliminary_note"}]
    found = [{"item_nos": ["2"]}, {"item_nos": ["5"]}]
    views.attach_raw(found, records, b"20note\r\n26 text\r\n11 2\r\n12Title\r\n20other\r\n")
    assert [entry["line"] for entry in found[0]["raw"]] == [3]
    assert [entry["line"] for entry in found[1]["raw"]] == [5]


def test_a_broken_excel_upload_says_why_in_german(real):
    client, _folder = real
    answer = post(client, b"PK\x03\x04 broken", "liste.xlsx")
    assert answer.status_code == 422
    assert answer.json()["error"] == ("Die Datei liste.xlsx kann nicht als Excel-Liste gelesen werden "
                                      "(keine Excel-Arbeitsmappe (.xlsx)).")

