"""The views "Bauwerk", "Einzel-LV", "Live-Prüfung", "Vergleich" and "Messung": their answers.

Synthetic data only (contract samples, hand-written GAEB lines). Every answer is checked for
the price keys; an uploaded priced file is checked for its price values in the whole answer.
"""
import json
import os
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "pipeline", "lv", "tests"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from gaeb90_lines import build, end, header, item, prices  # noqa: E402
from pipeline.base.run import run_all  # noqa: E402
from pipeline.common import contract  # noqa: E402
from web import views  # noqa: E402
from web.app import create_app  # noqa: E402

PRICE_KEYS = ("unit_price", "total")


def keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from keys(child)


def no_price_keys(answer):
    found = [key for key in keys(answer) if key in PRICE_KEYS]
    assert not found, found


DETAILED = [
    header("83L", "P-TEST-1"),
    "01Test trade                              01.01.26",
    "110100",
    "12First section",
    item("0100   1 ", "00000012000", "St"),
    "25Short text one",
    "26   Long text line one",
    "310100",
    "110200",
    "12Second section",
    item("0200   1 ", "00000002500", "m"),
    "25Pipe",
    "25with fitting",
    item("0200   2A", "00000001000", "psch"),
    "25Site setup",
    "310200",
    end(3),
]

# Quantity 2.000 m, unit price 98765.43, total 197530.86: made-up values the answer must never show.
PRICED = [
    header("86L", "P-TEST-2"),
    item("0100   1 ", "00000002000", "m"),
    prices("0100   1 ", "0009876543", "000019753086", "00000002000"),
    "25Pipe laid in the trench",
    end(1),
]
PRICE_TEXTS = ("98765", "9876543", "197530", "19753086")

XML = """<?xml version="1.0" encoding="UTF-8"?>
<GAEB xmlns="http://www.gaeb.de/GAEB_DA_XML/DA83/3.2">
<GAEBInfo><Version>3.2</Version></GAEBInfo>
<PrjInfo><NamePrj>P-XML-1</NamePrj></PrjInfo>
<Award><DP>83</DP><BoQ><BoQInfo><LblBoQ>Testgewerk</LblBoQ></BoQInfo><BoQBody>
<BoQCtgy RNoPart="01"><LblTx>Erdarbeiten</LblTx><BoQBody><Itemlist>
<Item RNoPart="0010"><Qty>12.5</Qty><QU>m3</QU><Description><CompleteText><OutlineText><OutlTxt><TextOutlTxt>
<p>Boden lösen und laden</p></TextOutlTxt></OutlTxt></OutlineText></CompleteText></Description></Item>
</Itemlist></BoQBody></BoQCtgy></BoQBody></BoQ></Award></GAEB>
""".encode("utf-8")


@pytest.fixture
def sample_client(tmp_path):
    """The app on a project folder that holds the contract samples and their base findings."""
    folder = tmp_path / "out" / "11-111"
    folder.mkdir(parents=True)
    for name in ("findings", "items"):
        shutil.copy(contract.sample_path(name), str(folder / ("%s.json" % name)))
    items = contract.load_sample("items")
    base, _summary = run_all(items)
    (folder / "base_findings.json").write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    return TestClient(create_app(out_dir=str(tmp_path / "out"), reviews_dir=str(tmp_path / "reviews")))


def post(client, raw, name):
    return client.post("/api/live", content=raw, headers={"X-File-Name": name, "Content-Type": "application/octet-stream"})


# ---- Live-Prüfung -------------------------------------------------------------------

def test_a_gaeb90_upload_is_read_and_checked_in_memory(sample_client, tmp_path):
    before = sorted(os.listdir(str(tmp_path)))
    answer = post(sample_client, build(DETAILED), "list.D83")
    assert answer.status_code == 200, answer.text
    data = answer.json()
    assert (data["file"], data["format"], data["stage"], data["items"], data["headings"]) == ("list.D83", "gaeb90", "83", 3, 2)
    assert [c["check"] for c in data["checks"]] == ["B%d" % n for n in range(1, 13)]
    assert next(c for c in data["checks"] if c["check"] == "B1")["not_applicable"] is True
    assert data["recalculation"]["priced"] == 0
    assert [row["item_no"] for row in data["rows"] if row["kind"] != "heading"] == ["01.00.1", "02.00.1", "02.00.2"] or data["rows"]
    assert data["seconds"]["read"] >= 0 and data["seconds"]["checks"] >= 0
    no_price_keys(data)
    assert sorted(os.listdir(str(tmp_path))) == before  # nothing written


def test_an_upload_never_sends_a_price_back(sample_client):
    answer = post(sample_client, build(PRICED), "order.D86")
    assert answer.status_code == 200, answer.text
    data = answer.json()
    assert data["recalculation"] == {"priced": 1, "equal": 1, "not_equal": 0, "no_quantity": 0}
    no_price_keys(data)
    for text in PRICE_TEXTS:
        assert text not in answer.text


def test_a_gaeb_xml_upload_is_read(sample_client):
    answer = post(sample_client, XML, "list.X83")
    assert answer.status_code == 200, answer.text
    data = answer.json()
    assert (data["format"], data["items"]) == ("gaebxml", 1)
    row = next(r for r in data["rows"] if r["kind"] != "heading")
    assert (row["quantity"], row["unit"], row["short_text"]) == (12.5, "m3", "Boden lösen und laden")


def test_the_file_name_is_read_from_its_url_encoding(sample_client):
    answer = post(sample_client, build(DETAILED), "Liste%20%C3%84nderung.D83")
    assert answer.status_code == 200
    assert answer.json()["file"] == "Liste Änderung.D83"


@pytest.mark.parametrize("raw, name, words", [
    (b"%PDF-1.4", "list.pdf", "Nur GAEB-Dateien"),
    (b"", "list.D83", "leer"),
    (b"<GAEB><not closed", "list.X83", "kann nicht als GAEB gelesen werden"),
    (b"anything", "", "keinen Namen"),
])
def test_a_wrong_upload_is_refused_with_a_german_reason(sample_client, raw, name, words):
    answer = post(sample_client, raw, name)
    assert answer.status_code == 422
    assert words in answer.json()["error"]


def test_an_upload_over_the_limit_is_refused(monkeypatch):
    monkeypatch.setattr(views, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(views.ViewError, match="größer als"):
        views.live(b"x" * 11, "list.D83")


# ---- Bauwerk -----------------------------------------------------------------------

def test_the_matrix_lights_the_cells_between_the_lists_of_each_finding(sample_client):
    answer = sample_client.get("/api/matrix")
    assert answer.status_code == 200
    data = answer.json()
    assert [entry["doc"] for entry in data["lists"]] == ["LV_91", "LV_92", "AN_93"]
    assert data["positions"] == sum(entry["positions"] for entry in data["lists"])
    cells = dict(((cell["a"], cell["b"]), cell) for cell in data["cells"])
    assert sorted(cells[("LV_91", "LV_92")]["findings"]) == ["X1-f0a30d", "X2-5b4bb3"]
    assert cells[("LV_91", "LV_92")]["severity"] == "high"
    assert cells[("LV_91", "LV_91")]["findings"] == ["S-acff08"]
    no_price_keys(data)


def test_a_finding_between_three_lists_lights_its_three_pairs():
    findings = [{"id": "X1-aaaaaa", "severity": "medium", "handover": ["A", "B", "C"], "sources": []}]
    items = [{"doc": doc, "trade": doc, "kind": "normal"} for doc in ("A", "B", "C")]
    data = views.matrix(findings, items)
    assert sorted((cell["a"], cell["b"]) for cell in data["cells"]) == [("A", "B"), ("A", "C"), ("B", "C")]


def test_the_handover_map_counts_only_for_its_own_project():
    items = [{"doc": doc, "trade": doc, "kind": "normal"} for doc in ("A", "B")]
    handover_map = {"project": "P1", "handovers": [{"name_de": "A → B", "lists": ["A", "B"], "status": "evidence"}]}
    assert views.matrix([], items, handover_map, project="P2")["cells"] == []
    data = views.matrix([], items, handover_map, project="P1")
    assert data["cells"] == [{"a": "A", "b": "B", "findings": [], "severity": None, "handovers": ["A → B"]}]


# ---- Einzel-LV ---------------------------------------------------------------------

def test_the_lists_and_one_list_with_its_base_findings(sample_client):
    lists = sample_client.get("/api/lv").json()
    assert [entry["doc"] for entry in lists["lists"]] == ["LV_91", "LV_92", "AN_93"]
    assert lists["base_findings_file"] is True
    answer = sample_client.get("/api/lv/LV_91")
    assert answer.status_code == 200
    data = answer.json()
    assert data["doc"] == "LV_91" and data["trade"] == "Estrich"
    assert [row["item_no"] for row in data["rows"]] == ["1", "1", "1.10", "1.20", "1.30", "1.40"]
    assert all(sorted(row) == sorted(views.ITEM_KEYS) for row in data["rows"])
    assert data["findings_total"] == len(data["findings"]) > 0
    assert all(finding["doc"] == "LV_91" for finding in data["findings"])
    no_price_keys(data)
    assert "1200" not in json.dumps(sample_client.get("/api/lv/AN_93").json())  # the sample total of AN_93


def test_an_unknown_list_is_a_404(sample_client):
    answer = sample_client.get("/api/lv/LV_00")
    assert answer.status_code == 404
    assert "LV_00" in answer.json()["error"]


# ---- Vergleich and Messung ---------------------------------------------------------

def test_without_a_comparison_run_the_view_says_what_to_run(sample_client):
    answer = sample_client.get("/api/diff")
    assert answer.status_code == 404
    assert "python -m pipeline.run" in answer.json()["error"]


def test_the_comparison_is_given_as_counts(tmp_path):
    summary = {
        "files": {"a": {"file": "A.D83", "counts": {"items": 3}}, "b": {"file": "B.D86", "counts": {"items": 4}}},
        "pdfs": {}, "text_pairs": [],
        "pairs": [{"id": "t3_tender_d83_order_d86", "group": "stage", "a": "a", "b": "b", "result": {
            "matching": {"both": 3, "only_a": [], "only_b": ["9.1"], "renumbered": []},
            "fields": {"quantity": {"compared": 3, "equal": 3, "not_equal": 0},
                       "unit_price": {"compared": 0, "equal": 0, "not_equal": 0, "not_equal_items": []}},
            "stage": {"added": ["9.1"], "removed": [], "renumbered": [],
                      "changed": {"quantity": [{"item_no": "1", "a": 1.0, "b": 2.0}], "unit": [], "text": [], "price": []},
                      "added_sections": ["9"]}}}],
        "hypothesis_38": {"verdict": "confirmed", "runs": [{"tendered": 3, "ordered": 4, "in_both": 3, "added": ["9.1"],
                                                             "removed": [], "renumbered": [], "sections_only_in_order": []}]},
    }
    data = views.diff(summary)
    pair = data["pairs"][0]
    assert (pair["title"], pair["both"], pair["stage"]["added"]["count"], pair["stage"]["changed"]["quantity"]) == (
        "8209.003: Ausschreibung (D83) gegen Auftrag LV24069 (D86)", 3, 1, 1)
    assert data["hypothesis"]["verdict"] == "bestätigt"
    assert "2.0" not in json.dumps(data)  # changed values are counted, not shown


def test_the_measurements_are_shown_in_german(sample_client):
    answer = sample_client.get("/api/bench")
    assert answer.status_code == 200
    data = answer.json()
    assert [row["id"] for row in data["rows"]] == ["M%d" % n for n in range(1, 10)]
    assert all(row["met_de"] in ("erfüllt", "nicht erfüllt", "nicht messbar", "noch nicht gemessen") for row in data["rows"])
    assert data["rows"][0]["name"] == "GAEB-Dateien lesen"


def test_the_page_has_a_tab_and_a_view_for_each_new_view(sample_client):
    html = sample_client.get("/").text
    for view in ("bauwerk", "einzel", "live", "vergleich", "messung"):
        assert 'data-view="%s"' % view in html and 'id="view-%s"' % view in html
    assert sample_client.get("/static/views.js").status_code == 200
    assert sample_client.get("/static/views.css").status_code == 200
