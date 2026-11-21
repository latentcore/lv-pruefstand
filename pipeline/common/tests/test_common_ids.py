import hashlib
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from pipeline.common import ids  # noqa: E402

COMMITTED_FINDINGS = os.path.join(ROOT, "pipeline", "cross", "results", "79-222", "findings.json")


def src(doc, item_no, quote, page=1):
    return {"doc": doc, "item_no": item_no, "page": page, "quote": quote}


A = src("LV_91", "1.10", "Nenndicke 65 mm")
B = src("LV_92", "2.20", "Estrich 50 mm")


def test_id_is_check_dash_six_hex_digits():
    assert re.fullmatch(r"X2-[0-9a-f]{6}", ids.finding_id("X2", [A, B]))


def test_id_follows_the_written_rule():
    raw = "X2|LV_91:1.10,LV_92:2.20|Nenndicke 65 mm"
    expected = "X2-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6]
    assert ids.finding_id("X2", [A, B]) == expected


def test_same_finding_gets_the_same_id_again():
    assert ids.finding_id("X2", [A, B]) == ids.finding_id("X2", [dict(A), dict(B)])


def test_pairs_are_sorted_but_the_first_quote_is_the_first_listed():
    later_sources = [A, src("LV_90", "9.10", "Estrich 50 mm")]
    raw = "X2|LV_90:9.10,LV_91:1.10|Nenndicke 65 mm"
    assert ids.finding_id("X2", later_sources) == "X2-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6]
    assert ids.finding_id("X2", [A, B]) != ids.finding_id("X2", [B, A])


def test_quote_is_normalized_before_hashing():
    messy = src("LV_91", "1.10", "  Nenn\u00addicke\n 65\u00a0mm ")
    assert ids.finding_id("X2", [messy, B]) == ids.finding_id("X2", [A, B])


def test_page_and_other_fields_do_not_change_the_id():
    moved = dict(A, page=7, note="x")
    assert ids.finding_id("X2", [moved, B]) == ids.finding_id("X2", [A, B])


def test_check_doc_item_no_and_quote_each_change_the_id():
    base = ids.finding_id("X2", [A, B])
    assert ids.finding_id("X1", [A, B]) != base
    assert ids.finding_id("X2", [dict(A, doc="LV_93"), B]) != base
    assert ids.finding_id("X2", [dict(A, item_no="1.11"), B]) != base
    assert ids.finding_id("X2", [dict(A, quote="Nenndicke 66 mm"), B]) != base


def test_empty_check_or_no_sources_is_an_error():
    with pytest.raises(ValueError):
        ids.finding_id("", [A])
    with pytest.raises(ValueError):
        ids.finding_id("X2", [])


def test_has_stable_id():
    finding = {"id": ids.finding_id("X2", [A, B]), "check": "X2", "sources": [A, B]}
    assert ids.has_stable_id(finding)
    assert not ids.has_stable_id(dict(finding, id="X2-000000"))


def test_committed_findings_carry_ids_of_this_rule():
    with open(COMMITTED_FINDINGS, encoding="utf-8") as handle:
        findings = json.load(handle)
    assert len(findings) == 24
    assert [f["id"] for f in findings if not ids.has_stable_id(f)] == []
    assert len({f["id"] for f in findings}) == len(findings)
