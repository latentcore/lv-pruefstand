"""W6/W7 on the real project 79-222. These tests run only where the organizer
data was read into out/79-222/items.json (AGENTS.md "Data and items.json");
they are skipped elsewhere. No quote text and no price is printed."""
import json
import os
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from pipeline.common import contract  # noqa: E402
from web.app import create_app  # noqa: E402

REAL_ITEMS = os.path.join(ROOT, "out", "79-222", "items.json")
REAL_FINDINGS = os.path.join(ROOT, "out", "79-222", "findings.json")
COMMITTED_FINDINGS = os.path.join(ROOT, "pipeline", "cross", "results", "79-222", "findings.json")

needs_items = pytest.mark.skipif(not os.path.exists(REAL_ITEMS), reason="out/79-222/items.json is not built")
needs_run = pytest.mark.skipif(not (os.path.exists(REAL_ITEMS) and os.path.exists(REAL_FINDINGS)),
                               reason="out/79-222/findings.json is not built")


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


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


def check_answer(data, findings, items):
    """What must hold for any findings.json of 79-222 next to the real items.json."""
    assert (data["mode"], data["project"]) == ("real", "79-222")
    assert data["items_usable"] is True
    assert data["contract_errors"] == 0
    assert [f["id"] for f in data["findings"]] == [f["id"] for f in findings]
    assert not set(all_keys(data)) & {"unit_price", "total"}
    trades = {item["doc"]: item["trade"] for item in items}
    cited = set((item["doc"], item["item_no"]) for item in items)
    for shown, raw in zip(data["findings"], findings):
        assert len(shown["sources"]) == len(raw["sources"])
        for source, raw_source in zip(shown["sources"], raw["sources"]):
            for key in ("doc", "item_no", "page", "quote"):
                assert source[key] == raw_source[key]
            assert source["trade"] == trades.get(raw_source["doc"])
            if (raw_source["doc"], raw_source["item_no"]) in cited:
                assert source["short_text"]
        for key in ("type", "severity", "explanation_de", "question_de", "lists_searched", "search_terms"):
            assert shown[key] == raw[key]
        assert shown["skeptic"]["status"] == raw["skeptic"]["status"]
        expected = raw["skeptic"]["status"] == "survived" and raw["quotes_verified"] is True
        assert shown["k3_pass"] is expected
    passed = sum(1 for f in data["findings"] if f["k3_pass"])
    assert data["counters"]["k3"]["count"] == passed
    assert data["counters"]["held_back"] == len(findings) - passed
    assert data["counters"]["all"]["count"] == len(findings)


@needs_items
def test_committed_findings_with_the_real_items(tmp_path):
    folder = tmp_path / "out" / "79-222"
    os.makedirs(str(folder))
    shutil.copy(COMMITTED_FINDINGS, str(folder / "findings.json"))
    shutil.copy(REAL_ITEMS, str(folder / "items.json"))
    findings, items = load(COMMITTED_FINDINGS), load(REAL_ITEMS)
    client = TestClient(create_app(out_dir=str(tmp_path / "out"), reviews_dir=str(tmp_path / "reviews")))
    data = client.get("/api/findings").json()
    check_answer(data, findings, items)
    # Counted by code in AGENTS.md: 24 findings, 16 survived, 8 weakened; all 24 carry quotes_verified.
    assert data["counters"]["all"]["count"] == 24
    assert data["counters"]["k3"]["count"] == 16
    assert data["counters"]["held_back"] == 8
    # Every cited list and item of the committed findings stands in the real items.json.
    for finding in data["findings"]:
        for source in finding["sources"]:
            assert source["trade"] and source["short_text"]

    # One label per status, then a new run (file rewritten, one finding gone): the labels stay.
    queue = [f["id"] for f in data["findings"] if f["k3_pass"]]
    for finding_id, status in zip(queue, ("confirmed", "rejected", "unclear")):
        answer = client.post("/api/reviews/%s" % finding_id, json={"status": status})
        assert answer.status_code == 200
        assert not set(all_keys(answer.json())) & {"unit_price", "total"}
    assert answer.json()["counters"]["k3"] == {"count": 16, "open": 13, "confirmed": 1, "rejected": 1, "unclear": 1}
    stored = load(str(tmp_path / "reviews" / "79-222.json"))
    assert contract.errors("reviews", stored) == []
    with open(str(folder / "findings.json"), "w", encoding="utf-8") as handle:
        json.dump([f for f in findings if f["id"] != queue[2]], handle, ensure_ascii=False)
    restarted = TestClient(create_app(out_dir=str(tmp_path / "out"), reviews_dir=str(tmp_path / "reviews")))
    after = restarted.get("/api/findings").json()
    assert after["counters"]["k3"] == {"count": 15, "open": 13, "confirmed": 1, "rejected": 1, "unclear": 0}
    assert after["counters"]["reviews_without_finding"] == 1
    assert load(str(tmp_path / "reviews" / "79-222.json")) == stored


@needs_run
def test_merged_run_in_out_is_read_as_it_is(tmp_path):
    """The file the pipeline wrote on this machine (with the W5b verdict), read in place; reviews go to a temp folder."""
    client = TestClient(create_app(out_dir=os.path.join(ROOT, "out"), reviews_dir=str(tmp_path / "reviews"),
                                   project="79-222"))
    response = client.get("/api/findings")
    assert response.status_code == 200
    check_answer(response.json(), load(REAL_FINDINGS), load(REAL_ITEMS))
    assert "unit_price" not in response.text
