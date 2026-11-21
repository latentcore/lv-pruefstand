"""The skeptic pass on the real lists of 79-222. Skipped when out/79-222/items.json is not built.

Build it with the two reader commands of AGENTS.md ("Data and items.json").
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402

import skeptic_samples as samples  # noqa: E402
from pipeline.common import contract  # noqa: E402
from pipeline.skeptic import evidence, merge, rules  # noqa: E402

HAVE_ITEMS = os.path.exists(samples.REAL_ITEMS)
HAVE_TEXT = os.path.isdir(samples.REAL_TEXT_DIR)
needs_items = pytest.mark.skipif(not HAVE_ITEMS, reason="out/79-222/items.json not built")
needs_text = pytest.mark.skipif(not (HAVE_ITEMS and HAVE_TEXT),
                                reason="out/79-222/items.json or cache/79-222_text not built")


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def findings():
    return evidence.load_findings(samples.COMMITTED_FINDINGS)


@pytest.fixture(scope="module")
def items():
    return evidence.load_items(samples.REAL_ITEMS)


@pytest.fixture(scope="module")
def gathered(findings, items):
    return evidence.gather_all(findings, items, load(samples.TERMS))


@needs_items
def test_items_are_loaded_without_prices_from_27_lists(items):
    assert len({item["doc"] for item in items}) == 27
    assert all("unit_price" not in item and "total" not in item for item in items)
    raw = load(samples.REAL_ITEMS)
    assert len(raw) == len(items) and "unit_price" in raw[0]


@needs_items
def test_evidence_searches_all_27_lists_for_each_of_the_24_findings(findings, gathered):
    assert list(gathered) == [f["id"] for f in findings] and len(gathered) == 24
    for finding_id, entry in gathered.items():
        assert len(entry["lists_searched"]) == 27, finding_id
        assert set(entry["hits_per_list"]) | set(entry["lists_without_hit"]) == set(entry["lists_searched"])
        assert entry["hits"], "%s: no entry matches any term" % finding_id
        assert entry["added_terms"], "%s: no added term" % finding_id
        assert sum(entry["hits_per_list"].values()) == len(entry["hits"])


@needs_items
def test_every_hit_carries_doc_item_number_and_page_and_stands_in_items(gathered, items):
    known = {(item["doc"], item["item_no"], item["page"]) for item in items}
    for finding_id, entry in gathered.items():
        for hit in entry["hits"]:
            assert (hit["doc"], hit["item_no"], hit["page"]) in known, finding_id
            assert isinstance(hit["page"], int) and hit["page"] >= 1, finding_id
            assert hit["terms"] and len(hit["terms"]) == len(hit["snippets"]), finding_id


@needs_items
def test_evidence_reaches_preliminary_notes_and_lists_outside_the_sources(findings, gathered):
    kinds = {hit["kind"] for entry in gathered.values() for hit in entry["hits"]}
    assert "preliminary_note" in kinds and "normal" in kinds
    for finding in findings:
        cited_docs = {s["doc"] for s in finding["sources"]}
        hit_docs = set(gathered[finding["id"]]["hits_per_list"])
        assert hit_docs - cited_docs, "%s: evidence only from the cited lists" % finding["id"]


@needs_items
def test_cited_items_are_part_of_the_evidence_when_a_term_stands_in_them(findings, gathered, items):
    for finding in findings:
        terms = evidence.finding_terms(finding, load(samples.TERMS)[finding["id"]])
        cited = {(s["doc"], s["item_no"]) for s in finding["sources"]}
        expected = {(i["doc"], i["item_no"]) for i in items
                    if (i["doc"], i["item_no"]) in cited and evidence.match_item(i, terms)}
        marked = {(h["doc"], h["item_no"]) for h in gathered[finding["id"]]["hits"] if h["cited"]}
        assert marked == expected, finding["id"]
        assert marked, "%s: no cited item in the evidence" % finding["id"]


@needs_items
def test_evidence_file_holds_no_price_and_no_finder_note(tmp_path, capsys):
    out = tmp_path / "evidence.json"
    assert evidence.main([samples.COMMITTED_FINDINGS, samples.REAL_ITEMS, str(out),
                          "--terms", samples.TERMS]) == 0
    printed = capsys.readouterr().out
    assert "24 findings, 1347 entries searched" in printed
    stored = load(str(out))
    assert len(stored) == 24

    def keys(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from keys(value)
        elif isinstance(node, list):
            for value in node:
                yield from keys(value)

    assert not {"unit_price", "total", "skeptic"} & set(keys(stored))
    assert "unit_price" not in printed and "skeptic" not in printed


@needs_items
def test_items_named_in_the_verdict_notes_exist(items):
    known = {(item["doc"], item["item_no"]) for item in items}
    token = re.compile(r"\bLV (\d+[a-z]?)\b|(?<![\w,])(\d+(?:\.\d+)+|\.\d+)(?!\w)")
    for finding_id, verdict in load(samples.VERDICTS).items():
        note = re.sub(r"\bRäume \d+\.\d+(?: und \d+\.\d+)*", "", verdict["note"])
        doc, named = None, []
        for match in token.finditer(note):
            if match.group(1):
                doc = "LV_" + match.group(1)
            elif doc:
                named.append((doc, match.group(2)))
        assert named, "%s names no item" % finding_id
        missing = [ref for ref in named if ref not in known]
        assert not missing, "%s names items that are not in items.json: %s" % (finding_id, missing)


@needs_text
def test_rule_checks_give_the_committed_verdicts_again(findings, items):
    committed = load(samples.VERDICTS)
    pages = rules.load_pages(samples.REAL_TEXT_DIR)
    assert rules.apply_rules(findings, items, committed, pages) == committed


@needs_text
def test_every_committed_quote_stands_in_its_item_or_on_its_page(findings, items):
    pages = rules.load_pages(samples.REAL_TEXT_DIR)
    assert len({doc for doc, _ in pages}) == 27
    for finding in findings:
        assert rules.quotes_not_found(finding, items, pages) == [], finding["id"]
    without_pages = [f["id"] for f in findings if rules.quotes_not_found(f, items)]
    assert without_pages, "some quotes stand only in the page text (W17)"


@needs_items
def test_number_rule_on_the_real_findings(findings, items):
    fired = {f["id"]: rules.unsupported_numbers(f, items) for f in findings}
    fired = {finding_id: numbers for finding_id, numbers in fired.items() if numbers}
    committed = {i: v["rules"]["unsupported_numbers"] for i, v in load(samples.VERDICTS).items()
                 if v["rules"]["unsupported_numbers"]}
    assert fired == committed
    # numbers that stand in the cited items do not fire: 26 m2 in LV 03 15.3.190, 200 mm in LV 14b .48
    assert "26" not in fired.get("X2-d84c10", []) and "200" not in fired.get("X3-153652", [])
    # a sum and a number from an item that is not cited do
    assert fired["X2-4e2312"][0] == "77" and fired["X3-153652"] == ["250"]


@needs_items
def test_rules_command_and_merge_command_end_to_end(tmp_path, capsys):
    verdicts_out = tmp_path / "verdicts.json"
    arguments = [samples.COMMITTED_FINDINGS, samples.REAL_ITEMS, samples.VERDICTS, str(verdicts_out)]
    if HAVE_TEXT:
        arguments += ["--text-dir", samples.REAL_TEXT_DIR]
    assert rules.main(arguments) == 0
    assert "24 verdicts, 6 lowered by a rule" in capsys.readouterr().out
    findings_out = tmp_path / "findings.json"
    assert merge.main([samples.COMMITTED_FINDINGS, str(verdicts_out), str(findings_out)]) == 0
    merged = load(str(findings_out))
    assert len(merged) == 24 and contract.errors("findings", merged) == []
    assert merge.status_counts(merged) == {"survived": 11, "weakened": 13, "refuted": 0}
    text = findings_out.read_text(encoding="utf-8")
    assert "unit_price" not in text
