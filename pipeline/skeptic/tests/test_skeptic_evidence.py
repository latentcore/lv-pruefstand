"""Evidence gathering: skeptic key removed, prices removed, every list searched."""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402

import skeptic_samples as samples  # noqa: E402
from pipeline.skeptic import evidence  # noqa: E402


def write(path, data):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)
    return str(path)


def test_without_skeptic_removes_the_key_and_keeps_the_rest():
    findings = [samples.finding(), samples.second_finding()]
    before = copy.deepcopy(findings)
    result = evidence.without_skeptic(findings)
    assert all("skeptic" not in f for f in result)
    assert [{k: v for k, v in f.items() if k != "skeptic"} for f in before] == result
    assert findings == before, "the input must not change"


def test_without_skeptic_accepts_findings_that_have_no_skeptic_key():
    finding = samples.finding()
    del finding["skeptic"]
    assert evidence.without_skeptic([finding]) == [finding]


def test_load_findings_never_returns_the_finder_note(tmp_path):
    path = write(tmp_path / "findings.json", [samples.finding(), samples.second_finding()])
    loaded = evidence.load_findings(path)
    assert len(loaded) == 2
    assert "FINDER NOTE" not in json.dumps(loaded, ensure_ascii=False)


def test_without_prices_removes_unit_price_and_total_only():
    items = samples.items()
    before = copy.deepcopy(items)
    result = evidence.without_prices(items)
    for old, new in zip(before, result):
        assert "unit_price" not in new and "total" not in new
        assert new == {k: v for k, v in old.items() if k not in ("unit_price", "total")}
    assert items == before, "the input must not change"


def test_load_items_drops_the_prices(tmp_path):
    loaded = evidence.load_items(write(tmp_path / "items.json", samples.items()))
    assert len(loaded) == len(samples.items())
    assert all("unit_price" not in item and "total" not in item for item in loaded)


def test_finding_terms_adds_terms_once_and_skips_empty_ones():
    finding = samples.finding(search_terms=["Estrich", "Nenndicke", "estrich", ""])
    assert evidence.finding_terms(finding, ["Anstrich", "NENNDICKE", "  ", None]) == [
        "Estrich", "Nenndicke", "Anstrich"]


def test_finding_terms_without_search_terms():
    assert evidence.finding_terms(samples.finding(search_terms=None)) == []
    assert evidence.finding_terms({}, ["Estrich"]) == ["Estrich"]


def test_match_ignores_case_and_line_end_hyphens():
    item = samples.items()[2]
    matches = evidence.match_item(item, ["wärmedämmung", "NENNDICKE", "Vinyl"])
    assert [m["term"] for m in matches] == ["wärmedämmung", "NENNDICKE"]
    assert "Wärmedämmung" in matches[0]["snippet"]


def test_match_reads_short_text_long_text_and_trade_lines():
    item = samples.item("LV_91", "9", "Kurztext Alpha", "Langtext Beta",
                        pre_trade_text="Vorzeile Gamma", post_trade_text="Nachzeile Delta")
    found = [m["term"] for m in evidence.match_item(item, ["Alpha", "Beta", "Gamma", "Delta", "Omega"])]
    assert found == ["Alpha", "Beta", "Gamma", "Delta"]


def test_match_handles_sharp_s_and_missing_texts():
    item = samples.item("LV_91", "9", "Anstrich Fußboden", None)
    assert [m["term"] for m in evidence.match_item(item, ["FUSSBODEN"])] == ["FUSSBODEN"]
    assert evidence.match_item({"doc": "LV_91"}, ["Estrich"]) == []
    assert evidence.match_item(item, []) == []


def test_snippet_marks_cuts():
    text = "a" * 200 + "TERM" + "b" * 200
    cut = evidence.snippet(text, 200, 4, radius=10)
    assert cut == "..." + "a" * 10 + "TERM" + "b" * 10 + "..."
    assert evidence.snippet("TERM", 0, 4, radius=10) == "TERM"


def test_gather_finds_items_headings_and_preliminary_notes_in_all_lists():
    result = evidence.gather(samples.finding(), samples.items())
    assert result["id"] == "X2-aaaaaa"
    assert result["lists_searched"] == ["LV_91", "LV_92", "LV_93"]
    assert result["lists_without_hit"] == ["LV_93"]
    assert result["hits_per_list"] == {"LV_91": 3, "LV_92": 1}
    hits = {(h["doc"], h["item_no"], h["kind"]): h for h in result["hits"]}
    assert set(hits) == {("LV_91", "1", "heading"), ("LV_91", "", "preliminary_note"),
                         ("LV_91", "1.10", "normal"), ("LV_92", "2.20", "normal")}
    cited = hits[("LV_91", "1.10", "normal")]
    assert cited["cited"] is True and cited["page"] == 2
    assert cited["quantity"] == 35.0 and cited["unit"] == "m2"
    assert cited["terms"] == ["Nenndicke", "Estrich"] and len(cited["snippets"]) == 2
    assert hits[("LV_91", "1", "heading")]["cited"] is False


def test_gather_uses_added_terms_and_names_them():
    plain = evidence.gather(samples.finding(), samples.items())
    more = evidence.gather(samples.finding(), samples.items(), ["Anstrich", "Estrich"])
    assert plain["added_terms"] == [] and more["added_terms"] == ["Anstrich"]
    assert more["terms"] == ["Nenndicke", "Aufbauhöhe", "Estrich", "Anstrich"]
    assert more["lists_without_hit"] == []
    assert [h["item_no"] for h in more["hits"] if h["doc"] == "LV_93"] == ["3.10"]


def test_gather_never_carries_a_price():
    items = samples.items()  # still with unit_price and total
    result = evidence.gather(samples.finding(), items, ["Anstrich"])
    text = json.dumps(result, ensure_ascii=False)
    assert "unit_price" not in text and "total" not in text
    assert "12.5" not in text and "437.5" not in text


def test_gather_does_not_search_the_explanation_or_the_old_skeptic_note():
    finding = samples.finding(search_terms=["Technikraum"],
                              skeptic={"status": "survived", "note": "Vinyl"})
    result = evidence.gather(finding, samples.items())
    assert [(h["doc"], h["item_no"]) for h in result["hits"]] == [("LV_93", "3.10")]


def test_gather_with_no_term_and_no_item():
    assert evidence.gather(samples.finding(search_terms=[]), samples.items())["hits"] == []
    empty = evidence.gather(samples.finding(), [])
    assert empty["hits"] == [] and empty["lists_searched"] == []


def test_gather_all_keys_by_id_and_rejects_terms_for_unknown_ids():
    findings = [samples.finding(), samples.second_finding()]
    result = evidence.gather_all(findings, samples.items(), {"X1-bbbbbb": ["Anstrich"]})
    assert list(result) == ["X2-aaaaaa", "X1-bbbbbb"]
    assert result["X1-bbbbbb"]["added_terms"] == ["Anstrich"]
    assert result["X2-aaaaaa"]["added_terms"] == []
    with pytest.raises(ValueError, match="X9-zzzzzz"):
        evidence.gather_all(findings, samples.items(), {"X9-zzzzzz": ["Estrich"]})


def test_command_writes_the_evidence_without_prices_or_finder_notes(tmp_path, capsys):
    findings = write(tmp_path / "findings.json", [samples.finding(), samples.second_finding()])
    items = write(tmp_path / "items.json", samples.items())
    terms = write(tmp_path / "terms.json", {"X2-aaaaaa": ["Anstrich"]})
    out = tmp_path / "new" / "folder" / "evidence.json"
    assert evidence.main([findings, items, str(out), "--terms", terms]) == 0
    stored = out.read_text(encoding="utf-8")
    printed = capsys.readouterr().out
    for text in (stored, printed):
        assert "unit_price" not in text and "437.5" not in text and "FINDER NOTE" not in text
    data = json.loads(stored)
    assert list(data) == ["X2-aaaaaa", "X1-bbbbbb"]
    assert data["X2-aaaaaa"]["added_terms"] == ["Anstrich"]
    assert "2 findings, 6 entries searched" in printed
    assert "in 3 of 3 lists" in printed


def test_command_works_without_added_terms(tmp_path):
    findings = write(tmp_path / "findings.json", [samples.finding()])
    items = write(tmp_path / "items.json", samples.items())
    out = tmp_path / "evidence.json"
    assert evidence.main([findings, items, str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["X2-aaaaaa"]["added_terms"] == []
