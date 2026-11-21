"""W6/W7: the app reads the sample first, then the real files; a click is
persistent; the label is still there after a new pipeline run; K3 filter;
no price field reaches the page."""
import json
import os
import re
import sys
import threading

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from pipeline.common import contract  # noqa: E402
from web.app import STATUSES, create_app, k3_pass, parse_eur, safe_name  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic test bytes, not a real picture"


def make_finding(finding_id, skeptic="survived", verified=True, **changes):
    finding = {
        "id": finding_id, "check": finding_id.split("-")[0], "layer": "between_lists",
        "type": "contradiction", "severity": "medium", "handover": ["LV_91", "LV_92"],
        "sources": [
            {"doc": "LV_91", "item_no": "1.10", "page": 2, "quote": "Nenndicke 65 mm"},
            {"doc": "LV_92", "item_no": "2.20", "page": 4, "quote": "Estrich 50 mm"},
        ],
        "lists_searched": ["LV_91", "LV_92"], "search_terms": ["Nenndicke", "Estrich"],
        "explanation_de": "Zwei Dicken für denselben Estrich.", "question_de": "Welche Dicke gilt?",
        "exposure": {"quantity": 120.0, "unit": "m2"}, "quotes_verified": verified, "origin": "model+code",
        "skeptic": {"status": skeptic, "note": "Testnotiz"},
    }
    finding.update(changes)
    return finding


def make_item(doc, item_no, trade, short_text, long_text="", kind="normal", **changes):
    item = {
        "doc": doc, "project": "P1", "trade": trade, "format": "pdf", "stage": "anfrage",
        "item_no": item_no, "kind": kind, "section": "", "short_text": short_text, "long_text": long_text,
        "quantity": 1.0, "unit": "m2", "unit_price": None, "total": None, "page": 1, "line": None,
        "pre_trade_text": None, "post_trade_text": None,
    }
    item.update(changes)
    return item


ITEMS = [
    make_item("LV_91", "1.10", "Estrich", "Zementestrich", "schwimmender Estrich, Nenndicke 65 mm"),
    make_item("LV_92", "2.20", "Bodenbelag", "Bodenbelag Büro", "Aufbauhöhe: Estrich 50 mm"),
]


def write_json(path, data):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)


def read_bytes(path):
    with open(str(path), "rb") as handle:
        return handle.read()


def read_json(path):
    with open(str(path), encoding="utf-8") as handle:
        return json.load(handle)


class Place:
    """A temporary out/ and reviews/ folder with one app on top."""

    def __init__(self, tmp_path):
        self.out = tmp_path / "out"
        self.reviews = tmp_path / "reviews"

    def project(self, name, findings, items=ITEMS):
        write_json(self.out / name / "findings.json", findings)
        if items is not None:
            write_json(self.out / name / "items.json", items)

    def client(self, project=None):
        return TestClient(create_app(out_dir=str(self.out), reviews_dir=str(self.reviews), project=project))

    def reviews_file(self, name):
        return self.reviews / ("%s.json" % name)


@pytest.fixture
def place(tmp_path):
    return Place(tmp_path)


def get(client):
    response = client.get("/api/findings")
    assert response.status_code == 200, response.text
    return response.json()


def by_id(data):
    return {finding["id"]: finding for finding in data["findings"]}


def all_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            for found in all_keys(child):
                yield found
    elif isinstance(value, list):
        for child in value:
            for found in all_keys(child):
                yield found


# ---- W6: sample first -------------------------------------------------------

def test_sample_mode_when_out_is_absent(place):
    data = get(place.client())
    assert data["mode"] == "sample"
    assert data["project"] == "11-111"
    assert data["source"] == "contract/samples/findings.json"
    assert data["missing"] == "out/<Projekt>/findings.json"
    assert [f["id"] for f in data["findings"]] == [f["id"] for f in contract.load_sample("findings")]
    assert data["contract_errors"] == 0
    assert data["items_usable"] is True


def test_sample_mode_when_out_holds_no_findings_file(place):
    write_json(place.out / "P1" / "items.json", ITEMS)
    data = get(place.client())
    assert data["mode"] == "sample"
    assert data["project"] == "11-111"


def test_named_project_without_findings_falls_back_to_sample_and_names_the_path(place):
    place.project("P1", [make_finding("X2-aaaaaa")])
    data = get(place.client(project="P9"))
    assert data["mode"] == "sample"
    assert data["missing"] == "out/P9/findings.json"
    assert data["project"] == "11-111"


def test_sample_finding_carries_every_field_of_the_fund_view(place):
    sample = contract.load_sample("findings")[0]
    shown = by_id(get(place.client()))[sample["id"]]
    assert len(shown["sources"]) == 2
    for index, (source, raw) in enumerate(zip(shown["sources"], sample["sources"])):
        assert source["index"] == index
        for key in ("doc", "item_no", "page", "quote"):
            assert source[key] == raw[key]
    assert [s["trade"] for s in shown["sources"]] == ["Estrich", "Bodenbelag"]
    for key in ("type", "severity", "explanation_de", "question_de", "lists_searched", "search_terms",
                "quotes_verified", "check", "layer", "handover", "origin"):
        assert shown[key] == sample[key]
    assert shown["skeptic"] == {"status": sample["skeptic"]["status"], "note": sample["skeptic"]["note"]}
    assert shown["review"] is None  # status "offen"


def test_sample_mode_writes_reviews_to_reviews_folder_and_leaves_contract_alone(place):
    before = read_bytes(contract.sample_path("reviews"))
    sample_id = contract.load_sample("findings")[0]["id"]
    client = place.client()
    assert client.post("/api/reviews/%s" % sample_id, json={"status": "unclear"}).status_code == 200
    assert read_bytes(contract.sample_path("reviews")) == before
    assert list(read_json(place.reviews_file("11-111"))) == [sample_id]
    assert by_id(get(client))[sample_id]["review"]["status"] == "unclear"


# ---- W6: then the real files ------------------------------------------------

def test_real_files_win_over_the_samples(place):
    place.project("P1", [make_finding("X2-aaaaaa"), make_finding("X3-bbbbbb", type="gap", severity="high")])
    data = get(place.client())
    assert data["mode"] == "real"
    assert data["project"] == "P1"
    assert data["source"] == "out/P1/findings.json"
    assert data["missing"] is None
    assert [f["id"] for f in data["findings"]] == ["X2-aaaaaa", "X3-bbbbbb"]
    assert by_id(data)["X3-bbbbbb"]["type"] == "gap"
    assert by_id(data)["X3-bbbbbb"]["severity"] == "high"


def test_real_mode_takes_trade_and_short_text_from_items_json(place):
    place.project("P1", [make_finding("X2-aaaaaa")])
    sources = by_id(get(place.client()))["X2-aaaaaa"]["sources"]
    assert [(s["doc"], s["trade"], s["item_no"], s["page"], s["short_text"]) for s in sources] == [
        ("LV_91", "Estrich", "1.10", 2, "Zementestrich"),
        ("LV_92", "Bodenbelag", "2.20", 4, "Bodenbelag Büro"),
    ]


def test_cited_item_is_the_record_that_holds_the_quote(place):
    items = [
        make_item("LV_91", "1", "Estrich", "Estricharbeiten", kind="heading"),
        make_item("LV_91", "1", "Estrich", "Vorbemerkung", "Der AN liefert die Rand-\nstreifen.", kind="preliminary_note"),
        make_item("LV_91", "2", "Estrich", "Titel zwei", kind="heading"),
        make_item("LV_91", "2", "Estrich", "Position zwei"),
    ]
    sources = [{"doc": "LV_91", "item_no": "1", "page": 1, "quote": "Der AN liefert die Randstreifen."},
               {"doc": "LV_91", "item_no": "2", "page": 1, "quote": "steht nur auf der Seite"},
               {"doc": "LV_91", "item_no": "9", "page": 1, "quote": "keine solche Position"}]
    place.project("P1", [make_finding("X2-aaaaaa", sources=sources)], items)
    shown = by_id(get(place.client()))["X2-aaaaaa"]["sources"]
    assert [s["short_text"] for s in shown] == ["Vorbemerkung", "Position zwei", None]
    assert [s["trade"] for s in shown] == ["Estrich"] * 3


def test_one_and_three_sources_are_all_sent(place):
    one = [{"doc": "LV_91", "item_no": "1.10", "page": 2, "quote": "Nenndicke 65 mm"}]
    three = one + [{"doc": "LV_92", "item_no": "2.20", "page": 4, "quote": "Estrich 50 mm"},
                   {"doc": "LV_93", "item_no": "3", "page": None, "quote": "ohne Seite"}]
    place.project("P1", [make_finding("X2-aaaaaa", sources=one), make_finding("X3-bbbbbb", sources=three)])
    shown = by_id(get(place.client()))
    assert [s["index"] for s in shown["X2-aaaaaa"]["sources"]] == [0]
    assert [s["index"] for s in shown["X3-bbbbbb"]["sources"]] == [0, 1, 2]
    assert shown["X3-bbbbbb"]["sources"][2]["page"] is None
    assert shown["X3-bbbbbb"]["sources"][2]["trade"] is None


def test_unknown_keys_are_ignored(place):
    finding = make_finding("X2-aaaaaa", future_key={"a": 1})
    finding["sources"][0]["bbox"] = [1, 2, 3, 4]
    finding["skeptic"]["model"] = "x"
    place.project("P1", [finding], [dict(item, price_mode="none", other=1) for item in ITEMS])
    data = get(place.client())
    assert data["contract_errors"] == 0
    keys = set(all_keys(data))
    assert not keys & {"future_key", "bbox", "model", "price_mode", "other"}
    assert by_id(data)["X2-aaaaaa"]["sources"][0]["trade"] == "Estrich"


def test_first_project_is_the_default_and_a_named_project_is_used(place):
    place.project("B2", [make_finding("X2-bbbbbb")])
    place.project("A1", [make_finding("X2-aaaaaa")])
    assert get(place.client())["project"] == "A1"
    data = get(place.client(project="B2"))
    assert data["project"] == "B2"
    assert [f["id"] for f in data["findings"]] == ["X2-bbbbbb"]


def test_out_written_after_the_start_is_read_without_a_restart(place):
    client = place.client()
    assert get(client)["mode"] == "sample"
    place.project("P1", [make_finding("X2-aaaaaa")])
    data = get(client)
    assert (data["mode"], data["project"]) == ("real", "P1")
    place.project("P1", [make_finding("X2-aaaaaa"), make_finding("X2-cccccc")])
    assert len(get(client)["findings"]) == 2


def test_missing_or_broken_items_json_is_reported_and_not_fatal(place):
    place.project("P1", [make_finding("X2-aaaaaa")], items=None)
    data = get(place.client())
    assert data["items_usable"] is False
    assert [s["trade"] for s in data["findings"][0]["sources"]] == [None, None]
    with open(str(place.out / "P1" / "items.json"), "w", encoding="utf-8") as handle:
        handle.write("[{")
    assert get(place.client())["items_usable"] is False
    write_json(place.out / "P1" / "items.json", {"not": "a list"})
    assert get(place.client())["items_usable"] is False


@pytest.mark.parametrize("content", ["[{", "", '{"id": "X2-aaaaaa"}', '"text"'])
def test_broken_findings_json_is_an_error_and_never_replaced_by_the_samples(place, content):
    os.makedirs(str(place.out / "P1"))
    with open(str(place.out / "P1" / "findings.json"), "w", encoding="utf-8") as handle:
        handle.write(content)
    client = place.client()
    response = client.get("/api/findings")
    assert response.status_code == 500
    assert "out/P1/findings.json" in response.json()["error"]
    assert client.post("/api/reviews/X2-aaaaaa", json={"status": "confirmed"}).status_code == 500
    assert not os.path.exists(str(place.reviews))


def test_findings_that_break_the_contract_are_counted_and_still_shown(place):
    broken = make_finding("X2-bbbbbb")
    del broken["severity"]
    broken["sources"] = "none"
    broken["skeptic"] = None
    place.project("P1", [make_finding("X2-aaaaaa"), broken, "not an object", {"no": "id"}])
    data = get(place.client())
    assert data["contract_errors"] >= 4
    assert 1 <= len(data["contract_error_examples"]) <= 3
    assert [f["id"] for f in data["findings"]] == ["X2-aaaaaa", "X2-bbbbbb"]
    shown = by_id(data)["X2-bbbbbb"]
    assert shown["severity"] is None and shown["sources"] == []
    assert shown["skeptic"] == {"status": None, "note": None}
    assert shown["k3_pass"] is False


def test_a_repeated_id_is_shown_once_and_counted(place):
    place.project("P1", [make_finding("X2-aaaaaa"), make_finding("X2-aaaaaa", severity="high")])
    data = get(place.client())
    assert [f["severity"] for f in data["findings"]] == ["medium"]
    assert data["contract_errors"] == 1
    assert data["counters"]["all"]["count"] == 1


def test_empty_findings_list(place):
    place.project("P1", [])
    data = get(place.client())
    assert data["mode"] == "real" and data["findings"] == []
    assert data["counters"]["all"] == {"count": 0, "open": 0, "confirmed": 0, "rejected": 0, "unclear": 0}
    assert data["counters"]["held_back"] == 0


def test_findings_file_with_a_byte_order_mark_is_read(place):
    os.makedirs(str(place.out / "P1"))
    with open(str(place.out / "P1" / "findings.json"), "w", encoding="utf-8-sig") as handle:
        json.dump([make_finding("X2-aaaaaa")], handle)
    assert [f["id"] for f in get(place.client())["findings"]] == ["X2-aaaaaa"]


@pytest.mark.parametrize("name", ["../x", "a/b", "", ".", "..", "a..b", ".hidden", "a b"])
def test_project_name_must_be_a_plain_folder_name(place, name):
    assert not safe_name(name)
    with pytest.raises(ValueError):
        place.client(project=name)


def test_folders_with_unsafe_names_are_not_projects(place):
    place.project("a b", [make_finding("X2-aaaaaa")])
    assert get(place.client())["mode"] == "sample"


# ---- K3 filter ----------------------------------------------------------------

K3_FINDINGS = [
    make_finding("X1-aaaaaa", "survived", True),
    make_finding("X2-bbbbbb", "weakened", True),
    make_finding("X2-cccccc", "survived", False),
    make_finding("X3-dddddd", "survived", "true"),
    make_finding("X3-eeeeee", "Survived", True),
    make_finding("X3-ffffff", "survived", True),
]


def test_k3_marks_only_survived_and_verified_findings(place):
    place.project("P1", K3_FINDINGS)
    data = get(place.client())
    assert [f["id"] for f in data["findings"] if f["k3_pass"]] == ["X1-aaaaaa", "X3-ffffff"]
    assert len(data["findings"]) == 6  # the filter hides nothing from the view "Fund"
    counters = data["counters"]
    assert counters["k3"]["count"] == 2
    assert counters["all"]["count"] == 6
    assert counters["held_back"] == 4


def test_k3_counters_follow_the_reviews(place):
    place.project("P1", K3_FINDINGS)
    client = place.client()
    answer = client.post("/api/reviews/X1-aaaaaa", json={"status": "confirmed"}).json()
    assert answer["counters"]["k3"] == {"count": 2, "open": 1, "confirmed": 1, "rejected": 0, "unclear": 0}
    assert answer["counters"]["all"] == {"count": 6, "open": 5, "confirmed": 1, "rejected": 0, "unclear": 0}
    answer = client.post("/api/reviews/X2-bbbbbb", json={"status": "rejected"}).json()  # held back by the filter
    assert answer["counters"]["k3"] == {"count": 2, "open": 1, "confirmed": 1, "rejected": 0, "unclear": 0}
    assert answer["counters"]["all"] == {"count": 6, "open": 4, "confirmed": 1, "rejected": 1, "unclear": 0}
    assert answer["counters"]["held_back"] == 4
    assert get(client)["counters"] == answer["counters"]


@pytest.mark.parametrize("finding,expected", [
    ({"skeptic": {"status": "survived"}, "quotes_verified": True}, True),
    ({"skeptic": {"status": "survived"}, "quotes_verified": False}, False),
    ({"skeptic": {"status": "survived"}}, False),
    ({"skeptic": {"status": "survived"}, "quotes_verified": 1}, False),
    ({"skeptic": {"status": "weakened"}, "quotes_verified": True}, False),
    ({"skeptic": {}, "quotes_verified": True}, False),
    ({"skeptic": None, "quotes_verified": True}, False),
    ({"skeptic": "survived", "quotes_verified": True}, False),
    ({"quotes_verified": True}, False),
])
def test_k3_pass(finding, expected):
    assert k3_pass(finding) is expected


def test_sample_counters_show_what_the_filter_holds_back(place):
    sample = contract.load_sample("findings")
    passed = [f for f in sample if f["skeptic"]["status"] == "survived" and f["quotes_verified"] is True]
    counters = get(place.client())["counters"]
    assert 0 < len(passed) < len(sample)
    assert counters["k3"]["count"] == len(passed)
    assert counters["held_back"] == len(sample) - len(passed)


# ---- no price reaches the page ---------------------------------------------------

def test_no_unit_price_or_total_in_any_answer(place):
    priced = [dict(item, unit_price=7654.32, total=98765.43) for item in ITEMS]
    finding = make_finding("X2-aaaaaa", unit_price=7654.32, total=98765.43)
    finding["sources"][0].update(unit_price=7654.32, total=98765.43)
    finding["exposure"].update(unit_price=7654.32, total=98765.43)
    finding["skeptic"].update(unit_price=7654.32, total=98765.43)
    place.project("P1", [finding], priced)
    write_json(place.reviews_file("P1"), {"X2-aaaaaa": {
        "status": "confirmed", "by": "", "comment": "", "eur_estimate": None, "at": "2026-11-21T10:00",
        "unit_price": 7654.32, "total": 98765.43}})
    client = place.client()
    answers = [client.get("/api/findings"),
               client.post("/api/reviews/X2-aaaaaa", json={"status": "rejected", "comment": "x"})]
    for response in answers:
        assert response.status_code == 200
        assert not set(all_keys(response.json())) & {"unit_price", "total"}
        for forbidden in ("unit_price", "7654", "98765"):
            assert forbidden not in response.text
    assert get(client)["findings"][0]["sources"][0]["short_text"] == "Zementestrich"  # items were read


def test_sample_answers_carry_no_price_keys(place):
    client = place.client()
    sample_id = contract.load_sample("findings")[0]["id"]
    for response in (client.get("/api/findings"), client.post("/api/reviews/%s" % sample_id, json={"status": "confirmed"})):
        assert not set(all_keys(response.json())) & {"unit_price", "total"}
        assert "unit_price" not in response.text


# ---- W7: a click is persistent ----------------------------------------------------

def test_a_click_writes_the_review_as_section_8_says(place):
    place.project("P1", [make_finding("X2-aaaaaa"), make_finding("X2-bbbbbb")])
    client = place.client()
    response = client.post("/api/reviews/X2-aaaaaa", json={
        "status": "confirmed", "by": "Kalkulator (Mentor)", "comment": "Kostet eine Woche.", "eur_estimate": 1500})
    assert response.status_code == 200
    stored = read_json(place.reviews_file("P1"))
    assert list(stored) == ["X2-aaaaaa"]
    entry = stored["X2-aaaaaa"]
    assert sorted(entry) == ["at", "by", "comment", "eur_estimate", "status"]
    assert entry["status"] == "confirmed"
    assert entry["by"] == "Kalkulator (Mentor)"
    assert entry["comment"] == "Kostet eine Woche."
    assert entry["eur_estimate"] == 1500.0
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$", entry["at"])
    assert contract.errors("reviews", stored) == []
    assert response.json()["review"] == entry
    assert response.json()["id"] == "X2-aaaaaa"


@pytest.mark.parametrize("status", STATUSES)
def test_each_status_is_stored_and_counted_at_once(place, status):
    place.project("P1", [make_finding("X2-aaaaaa"), make_finding("X2-bbbbbb")])
    client = place.client()
    answer = client.post("/api/reviews/X2-aaaaaa", json={"status": status}).json()
    expected = {"count": 2, "open": 1, "confirmed": 0, "rejected": 0, "unclear": 0}
    expected[status] = 1
    assert answer["counters"]["all"] == expected
    assert read_json(place.reviews_file("P1"))["X2-aaaaaa"]["status"] == status
    entry = read_json(place.reviews_file("P1"))["X2-aaaaaa"]
    assert (entry["by"], entry["comment"], entry["eur_estimate"]) == ("", "", None)
    assert by_id(get(client))["X2-aaaaaa"]["review"]["status"] == status
    assert by_id(get(client))["X2-bbbbbb"]["review"] is None


def test_statuses_are_the_three_of_the_brief():
    assert STATUSES == ("confirmed", "rejected", "unclear")


def test_review_is_still_there_after_an_app_restart(place):
    place.project("P1", [make_finding("X2-aaaaaa")])
    place.client().post("/api/reviews/X2-aaaaaa", json={"status": "rejected", "comment": "Ist geregelt.", "by": "M"})
    restarted = place.client()
    review = by_id(get(restarted))["X2-aaaaaa"]["review"]
    assert (review["status"], review["comment"], review["by"]) == ("rejected", "Ist geregelt.", "M")
    assert get(restarted)["counters"]["all"]["rejected"] == 1


def test_review_is_still_there_after_a_new_pipeline_run(place):
    place.project("P1", [make_finding("X2-aaaaaa"), make_finding("X2-bbbbbb")])
    client = place.client()
    client.post("/api/reviews/X2-aaaaaa", json={"status": "confirmed", "comment": "Stimmt."})
    client.post("/api/reviews/X2-bbbbbb", json={"status": "unclear"})
    before = read_bytes(place.reviews_file("P1"))

    # New run: one finding rewritten with other texts, one gone, one new.
    rerun = [make_finding("X2-aaaaaa", explanation_de="Neuer Text.", severity="high", skeptic="weakened"),
             make_finding("X3-cccccc")]
    place.project("P1", rerun)
    for current in (client, place.client()):  # the running app and a restarted one
        data = get(current)
        shown = by_id(data)
        assert shown["X2-aaaaaa"]["explanation_de"] == "Neuer Text."
        assert shown["X2-aaaaaa"]["review"]["status"] == "confirmed"
        assert shown["X2-aaaaaa"]["review"]["comment"] == "Stimmt."
        assert shown["X3-cccccc"]["review"] is None
        assert data["counters"]["all"] == {"count": 2, "open": 1, "confirmed": 1, "rejected": 0, "unclear": 0}
        assert data["counters"]["reviews_without_finding"] == 1
    assert read_bytes(place.reviews_file("P1")) == before  # reading never rewrites the file

    # A click after the new run keeps the label of the finding that is gone.
    client.post("/api/reviews/X3-cccccc", json={"status": "rejected"})
    stored = read_json(place.reviews_file("P1"))
    assert sorted(stored) == ["X2-aaaaaa", "X2-bbbbbb", "X3-cccccc"]
    assert stored["X2-bbbbbb"]["status"] == "unclear"

    # The finding comes back in a later run: its label is shown again.
    place.project("P1", [make_finding("X2-bbbbbb")])
    assert by_id(get(client))["X2-bbbbbb"]["review"]["status"] == "unclear"


def test_a_click_changes_only_its_own_entry(place):
    place.project("P1", [make_finding("X2-aaaaaa"), make_finding("X2-bbbbbb")])
    other = {"status": "confirmed", "by": "Team", "comment": "früher", "eur_estimate": 12.5,
             "at": "2026-11-20T09:00", "extra": {"kept": True}}
    gone = {"status": "rejected", "by": "", "comment": "", "eur_estimate": None, "at": "2026-11-20T09:01"}
    write_json(place.reviews_file("P1"), {"X2-bbbbbb": other, "X9-gone00": gone})
    client = place.client()
    client.post("/api/reviews/X2-aaaaaa", json={"status": "unclear"})
    stored = read_json(place.reviews_file("P1"))
    assert stored["X2-bbbbbb"] == other
    assert stored["X9-gone00"] == gone
    assert list(stored) == ["X2-bbbbbb", "X9-gone00", "X2-aaaaaa"]


def test_a_second_click_replaces_the_five_keys_and_keeps_other_keys_of_the_entry(place):
    place.project("P1", [make_finding("X2-aaaaaa")])
    write_json(place.reviews_file("P1"), {"X2-aaaaaa": {
        "status": "confirmed", "by": "A", "comment": "alt", "eur_estimate": 10, "at": "2026-11-20T09:00",
        "note_from_export": "kept"}})
    client = place.client()
    client.post("/api/reviews/X2-aaaaaa", json={"status": "rejected", "by": "B", "comment": "neu"})
    entry = read_json(place.reviews_file("P1"))["X2-aaaaaa"]
    assert (entry["status"], entry["by"], entry["comment"], entry["eur_estimate"]) == ("rejected", "B", "neu", None)
    assert entry["note_from_export"] == "kept"
    assert entry["at"] != "2026-11-20T09:00"
    assert "note_from_export" not in client.get("/api/findings").text


def test_reviews_file_holds_plain_utf8_text(place):
    place.project("P1", [make_finding("X2-aaaaaa")])
    place.client().post("/api/reviews/X2-aaaaaa", json={"status": "confirmed", "comment": "Größe prüfen – 5 €"})
    assert "Größe prüfen – 5 €".encode("utf-8") in read_bytes(place.reviews_file("P1"))


def test_no_temporary_file_stays_in_the_reviews_folder(place):
    place.project("P1", [make_finding("X2-aaaaaa")])
    client = place.client()
    for status in STATUSES:
        client.post("/api/reviews/X2-aaaaaa", json={"status": status})
    assert os.listdir(str(place.reviews)) == ["P1.json"]


def test_reading_does_not_create_the_reviews_folder(place):
    place.project("P1", [make_finding("X2-aaaaaa")])
    get(place.client())
    assert not os.path.exists(str(place.reviews))


def test_many_clicks_at_the_same_time_all_reach_the_file(place):
    ids = ["X2-%06d" % number for number in range(24)]
    place.project("P1", [make_finding(finding_id) for finding_id in ids])
    client = place.client()
    codes = []

    def click(finding_id):
        codes.append(client.post("/api/reviews/%s" % finding_id, json={"status": "confirmed"}).status_code)

    threads = [threading.Thread(target=click, args=(finding_id,)) for finding_id in ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert codes == [200] * 24
    assert sorted(read_json(place.reviews_file("P1"))) == ids
    assert get(client)["counters"]["all"]["confirmed"] == 24


# ---- W7: what a click may carry ---------------------------------------------------

@pytest.mark.parametrize("body", [
    {"status": "bestätigt"}, {"status": "open"}, {"status": ""}, {"status": None}, {}, {"status": "Confirmed"},
    {"status": ["confirmed"]},
    {"status": "confirmed", "comment": 5}, {"status": "confirmed", "by": ["x"]},
    {"status": "confirmed", "comment": "x" * 501}, {"status": "confirmed", "by": "x" * 101},
    {"status": "confirmed", "eur_estimate": "viel"}, {"status": "confirmed", "eur_estimate": -1},
    {"status": "confirmed", "eur_estimate": True}, {"status": "confirmed", "eur_estimate": [1]},
    {"status": "confirmed", "eur_estimate": "1,2,3"}, {"status": "confirmed", "eur_estimate": "1e5"},
])
def test_a_click_with_a_wrong_value_is_refused_and_writes_nothing(place, body):
    place.project("P1", [make_finding("X2-aaaaaa")])
    client = place.client()
    response = client.post("/api/reviews/X2-aaaaaa", json=body)
    assert response.status_code == 422
    assert response.json()["error"]
    assert not os.path.exists(str(place.reviews))
    assert get(client)["counters"]["all"]["open"] == 1


@pytest.mark.parametrize("body", [["confirmed"], "confirmed", None])
def test_a_click_that_is_no_object_is_refused(place, body):
    place.project("P1", [make_finding("X2-aaaaaa")])
    assert place.client().post("/api/reviews/X2-aaaaaa", json=body).status_code == 422
    assert not os.path.exists(str(place.reviews))


def test_a_click_on_an_unknown_finding_is_refused(place):
    place.project("P1", [make_finding("X2-aaaaaa")])
    response = place.client().post("/api/reviews/X2-zzzzzz", json={"status": "confirmed"})
    assert response.status_code == 404
    assert not os.path.exists(str(place.reviews))


def test_a_click_from_a_page_that_shows_another_project_is_refused(place):
    place.project("P2", [make_finding("X2-aaaaaa")])
    client = place.client()  # no project named: the first folder in out/ is read
    shown = get(client)["project"]
    assert shown == "P2"
    place.project("P1", [make_finding("X2-aaaaaa")])  # a folder that sorts first appears while the page is open
    response = client.post("/api/reviews/X2-aaaaaa", json={"status": "confirmed", "project": shown})
    assert response.status_code == 409
    assert "P2" in response.json()["error"] and "P1" in response.json()["error"]
    assert not os.path.exists(str(place.reviews))
    # After a reload the page shows P1 and the click goes to P1 only.
    shown = get(client)["project"]
    assert client.post("/api/reviews/X2-aaaaaa", json={"status": "confirmed", "project": shown}).status_code == 200
    assert os.listdir(str(place.reviews)) == ["P1.json"]


def test_a_click_from_the_sample_page_is_refused_once_real_files_exist(place):
    client = place.client()
    sample = get(client)
    place.project("P1", [make_finding(sample["findings"][0]["id"])])
    response = client.post("/api/reviews/%s" % sample["findings"][0]["id"],
                           json={"status": "confirmed", "project": sample["project"]})
    assert response.status_code == 409
    assert not os.path.exists(str(place.reviews))


def test_comment_is_stored_as_one_line(place):
    place.project("P1", [make_finding("X2-aaaaaa")])
    client = place.client()
    client.post("/api/reviews/X2-aaaaaa", json={"status": "unclear", "comment": "  erste Zeile\n zweite\tZeile  ",
                                               "by": "  Kalkulator \n (Mentor) "})
    entry = read_json(place.reviews_file("P1"))["X2-aaaaaa"]
    assert entry["comment"] == "erste Zeile zweite Zeile"
    assert entry["by"] == "Kalkulator (Mentor)"
    assert client.post("/api/reviews/X2-aaaaaa", json={"status": "unclear", "comment": "x" * 500}).status_code == 200
    assert client.post("/api/reviews/X2-aaaaaa", json={"status": "unclear", "comment": None, "by": None}).status_code == 200
    assert read_json(place.reviews_file("P1"))["X2-aaaaaa"]["comment"] == ""


@pytest.mark.parametrize("given,expected", [
    (None, None), ("", None), ("   ", None), (0, 0.0), (1500, 1500.0), (12.5, 12.5),
    ("1500", 1500.0), ("1500,5", 1500.5), ("1500.5", 1500.5), ("1.500", 1500.0), ("1.500,50", 1500.5),
    ("1.234.567", 1234567.0), ("1.234.567,89", 1234567.89), ("1 500 €", 1500.0), ("250 EUR", 250.0),
    ("0,5", 0.5), ("12.34", 12.34), ("1.5", 1.5),
])
def test_parse_eur_reads_german_and_plain_numbers(given, expected):
    assert parse_eur(given) == expected


@pytest.mark.parametrize("given", [
    "abc", "1,2,3", "1.2.3", "-5", -5, -0.01, "1e5", "12,", ",5", "1.50,5", True, False, [1], {"a": 1},
    float("nan"), float("inf"), "NaN", "Infinity", "€", "1.500.5",
])
def test_parse_eur_refuses_what_is_no_amount(given):
    if given == "€":
        assert parse_eur(given) is None  # only the sign: no estimate
        return
    with pytest.raises(ValueError):
        parse_eur(given)


def test_eur_estimate_text_from_the_page_is_stored_as_a_number(place):
    place.project("P1", [make_finding("X2-aaaaaa")])
    client = place.client()
    for given, expected in (("1.500,50", 1500.5), ("", None), (300, 300.0), (None, None)):
        answer = client.post("/api/reviews/X2-aaaaaa", json={"status": "confirmed", "eur_estimate": given})
        assert answer.status_code == 200
        assert read_json(place.reviews_file("P1"))["X2-aaaaaa"]["eur_estimate"] == expected
        assert answer.json()["review"]["eur_estimate"] == expected


# ---- W7: a damaged reviews file is never overwritten -----------------------------

@pytest.mark.parametrize("content", ['{"X2-aaaaaa": {"status": "confirmed"', "[]", '"text"', ""])
def test_a_damaged_reviews_file_is_reported_and_left_as_it_is(place, content):
    place.project("P1", [make_finding("X2-aaaaaa")])
    os.makedirs(str(place.reviews))
    with open(str(place.reviews_file("P1")), "w", encoding="utf-8") as handle:
        handle.write(content)
    client = place.client()
    response = client.get("/api/findings")
    assert response.status_code == 500
    assert "reviews/P1.json" in response.json()["error"]
    response = client.post("/api/reviews/X2-aaaaaa", json={"status": "rejected"})
    assert response.status_code == 500
    assert read_bytes(place.reviews_file("P1")) == content.encode("utf-8")
    assert os.listdir(str(place.reviews)) == ["P1.json"]


def test_review_entries_the_app_cannot_use_count_as_open_and_stay_in_the_file(place):
    place.project("P1", [make_finding("X2-aaaaaa"), make_finding("X2-bbbbbb"), make_finding("X2-cccccc")])
    odd = {"X2-aaaaaa": {"status": "vielleicht", "by": "", "comment": "", "eur_estimate": None, "at": "2026-11-21T10:00"},
           "X2-bbbbbb": "confirmed",
           "X2-cccccc": {"status": "confirmed", "by": None, "comment": 7, "eur_estimate": "viel", "at": None}}
    write_json(place.reviews_file("P1"), odd)
    client = place.client()
    data = get(client)
    assert data["counters"]["all"] == {"count": 3, "open": 2, "confirmed": 1, "rejected": 0, "unclear": 0}
    shown = by_id(data)
    assert shown["X2-aaaaaa"]["review"]["status"] == "vielleicht"
    assert shown["X2-bbbbbb"]["review"] is None
    assert shown["X2-cccccc"]["review"] == {"status": "confirmed", "by": "", "comment": "7", "eur_estimate": None, "at": ""}
    assert read_json(place.reviews_file("P1")) == odd
    assert client.post("/api/reviews/X2-bbbbbb", json={"status": "unclear"}).status_code == 200
    stored = read_json(place.reviews_file("P1"))
    assert stored["X2-bbbbbb"]["status"] == "unclear"
    assert stored["X2-aaaaaa"] == odd["X2-aaaaaa"] and stored["X2-cccccc"] == odd["X2-cccccc"]


# ---- "Quelle zeigen" -----------------------------------------------------------------

def test_page_image_is_sent_when_the_file_exists(place):
    place.project("P1", [make_finding("X2-aaaaaa")])
    os.makedirs(str(place.out / "P1" / "pages"))
    with open(str(place.out / "P1" / "pages" / "X2-aaaaaa_1.png"), "wb") as handle:
        handle.write(PNG)
    client = place.client()
    response = client.get("/api/page-image/X2-aaaaaa/1")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == PNG


def test_page_image_that_is_missing_is_named(place):
    place.project("P1", [make_finding("X2-aaaaaa")])
    client = place.client()
    response = client.get("/api/page-image/X2-aaaaaa/0")
    assert response.status_code == 404
    assert response.json()["expected"] == "out/P1/pages/X2-aaaaaa_0.png"
    os.makedirs(str(place.out / "P1" / "pages"))
    with open(str(place.out / "P1" / "pages" / "X2-aaaaaa_0.png"), "wb") as handle:
        handle.write(PNG)  # the other package writes the image later: no restart needed
    assert client.get("/api/page-image/X2-aaaaaa/0").status_code == 200


def test_page_image_in_sample_mode_says_there_is_none(place):
    sample_id = contract.load_sample("findings")[0]["id"]
    response = place.client().get("/api/page-image/%s/0" % sample_id)
    assert response.status_code == 404
    assert response.json()["expected"] is None
    assert "Beispieldaten" in response.json()["error"]


@pytest.mark.parametrize("path,code", [
    ("/api/page-image/X2-aaaaaa/2", 404), ("/api/page-image/X2-aaaaaa/-1", 404),
    ("/api/page-image/X2-zzzzzz/0", 404), ("/api/page-image/X2-aaaaaa/x", 422),
    ("/api/page-image/X2-aaaaaa/0.5", 422), ("/api/page-image/..%2F..%2Fitems/0", 404),
])
def test_page_image_for_a_source_that_does_not_exist(place, path, code):
    place.project("P1", [make_finding("X2-aaaaaa")])
    os.makedirs(str(place.out / "P1" / "pages"))
    for name in ("X2-aaaaaa_2.png", "X2-aaaaaa_-1.png", "X2-zzzzzz_0.png"):
        with open(str(place.out / "P1" / "pages" / name), "wb") as handle:
            handle.write(PNG)
    assert place.client().get(path).status_code == code


def test_page_image_never_leaves_the_pages_folder(place):
    place.project("P1", [make_finding("x..y"), make_finding("..")])
    os.makedirs(str(place.out / "P1" / "pages"))
    for name in ("x..y_0.png", ".._0.png"):
        with open(str(place.out / "P1" / "pages" / name), "wb") as handle:
            handle.write(PNG)
    client = place.client()
    assert client.get("/api/page-image/x..y/0").status_code == 404
    assert client.get("/api/page-image/%2E%2E/0").status_code == 404
