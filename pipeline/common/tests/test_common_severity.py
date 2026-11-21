"""W15: fixed severity rules (docs/RISK_RULES.md, pipeline/common/severity.py)."""
import copy
import inspect
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from pipeline.common import contract, severity  # noqa: E402

RULES_PAGE = os.path.join(ROOT, "docs", "RISK_RULES.md")


def make_finding(check="X2", quantity=None, unit=None, sources=None, **changes):
    finding = {
        "id": "%s-aaaaaa" % check, "check": check, "layer": "between_lists", "type": "contradiction",
        "severity": "medium", "handover": ["LV_91", "LV_92"],
        "sources": sources if sources is not None else [
            {"doc": "LV_91", "item_no": "1.10", "page": 2, "quote": "Nenndicke 65 mm"},
            {"doc": "LV_92", "item_no": "2.20", "page": 4, "quote": "Estrich 50 mm"},
        ],
        "lists_searched": ["LV_91", "LV_92"], "search_terms": ["Estrich"],
        "explanation_de": "Zwei Dicken.", "question_de": "Welche Dicke gilt?",
        "exposure": {"quantity": quantity, "unit": unit}, "quotes_verified": True, "origin": "model+code",
        "skeptic": {"status": "survived", "note": "synthetic"},
    }
    finding.update(changes)
    return finding


def make_item(kind="normal", quantity=50.0, unit="m2", doc="LV_91", item_no="1.10", **changes):
    item = {
        "doc": doc, "project": "11-111", "trade": "Estrich", "format": "pdf", "stage": "anfrage",
        "item_no": item_no, "kind": kind, "section": "1", "short_text": "Zementestrich",
        "long_text": "schwimmender Estrich, Nenndicke 65 mm", "quantity": quantity, "unit": unit,
        "unit_price": None, "total": None, "page": 2, "line": None,
        "pre_trade_text": None, "post_trade_text": None,
    }
    item.update(changes)
    return item


NORMAL = make_item()
NOTE = make_item("preliminary_note", None, None, item_no="1", short_text="Vorbemerkung")
OPTIONAL = make_item("optional", 500.0, "m2", item_no="1.20")
ALTERNATIVE = make_item("alternative", 500.0, "m2", item_no="1.30")
LUMP_SUM = make_item("lump_sum", 1.0, "psch", item_no="1.40")
HEADING = make_item("heading", None, None, item_no="1", short_text="Estricharbeiten")


# ---- one test per rule: a finding that must hit it, one that must not -------

def test_rule_1_unknown_check_is_info():
    assert severity.severity(make_finding("Q9", 500.0, "m2"), [NORMAL]) == ("info", 1)
    assert severity.severity(make_finding("X2", 500.0, "m2"), [NORMAL])[1] != 1


def test_rule_2_note_checks_are_info():
    for check in ("B3", "B7", "B9", "B10", "B11", "B12", "V2"):
        assert severity.severity(make_finding(check, 500.0, "m2"), [NORMAL]) == ("info", 2), check
    for check in ("B4", "B5", "B6", "B8", "V1", "X1", "X2", "X3", "S"):
        assert severity.severity(make_finding(check, 500.0, "m2"), [NORMAL])[1] != 2, check


def test_rule_3_arithmetic_checks_are_high():
    for check in ("B1", "B2"):
        assert severity.severity(make_finding(check, 1.0, "St"), [OPTIONAL]) == ("high", 3), check
    assert severity.severity(make_finding("B4", 1.0, "St"), [OPTIONAL])[1] != 3


def test_rule_4_only_in_a_preliminary_note_is_medium():
    assert severity.severity(make_finding("X2", 500.0, "m2"), [NOTE, NOTE]) == ("medium", 4)
    assert severity.severity(make_finding("X2", 1.0, "St"), [NOTE]) == ("medium", 4)
    # One source that is a preliminary note beside a normal item: not "only".
    assert severity.severity(make_finding("X2", 500.0, "m2"), [NOTE, NORMAL]) == ("high", 6)


def test_rule_5_only_optional_or_alternative_items_is_info():
    assert severity.severity(make_finding("X1", 500.0, "m2"), [OPTIONAL]) == ("info", 5)
    assert severity.severity(make_finding("X1", 500.0, "m2"), [ALTERNATIVE, OPTIONAL]) == ("info", 5)
    assert severity.severity(make_finding("X1", 500.0, "m2"), [NOTE, OPTIONAL]) == ("info", 5)
    assert severity.severity(make_finding("X1", 500.0, "m2"), [OPTIONAL, NORMAL]) == ("high", 6)


def test_rule_6_large_quantity_is_high():
    assert severity.severity(make_finding("X3", 100.0, "m2"), [NORMAL]) == ("high", 6)
    assert severity.severity(make_finding("X3", 10.0, "St"), [NORMAL]) == ("high", 6)
    assert severity.severity(make_finding("X3", 99.99, "m2"), [NORMAL])[1] != 6
    assert severity.severity(make_finding("X3", 9.0, "St"), [NORMAL])[1] != 6
    # Large beats the lump-sum rule below it.
    assert severity.severity(make_finding("X3", 100.0, "m2"), [LUMP_SUM]) == ("high", 6)


def test_rule_7_lump_sum_is_medium():
    assert severity.severity(make_finding("X2", 1.0, "St"), [LUMP_SUM, NORMAL]) == ("medium", 7)
    assert severity.severity(make_finding("X2", None, None), [LUMP_SUM]) == ("medium", 7)
    assert severity.severity(make_finding("X2", 1.0, "St"), [NORMAL]) == ("info", 9)


def test_rule_8_unknown_quantity_is_medium():
    no_quantity = make_item(quantity=None, unit=None)
    assert severity.severity(make_finding("X2", None, None), [no_quantity]) == ("medium", 8)
    assert severity.severity(make_finding("X2", 0.0, "m2"), [make_item(quantity=0.0)]) == ("medium", 8)
    assert severity.severity(make_finding("X2", -3.0, "m2"), [make_item(quantity=-3.0)]) == ("medium", 8)
    assert severity.severity(make_finding("X2", 50.0, "m2"), [no_quantity])[1] != 8


def test_rule_9_small_quantity_is_info():
    assert severity.severity(make_finding("X3", 1.0, "St"), [NORMAL]) == ("info", 9)
    assert severity.severity(make_finding("X3", 9.99, "m"), [NORMAL]) == ("info", 9)
    assert severity.severity(make_finding("X3", 2.0, "St"), [NORMAL])[1] != 9
    assert severity.severity(make_finding("X3", 10.0, "m"), [NORMAL])[1] != 9


def test_rule_10_middle_quantity_is_medium():
    assert severity.severity(make_finding("X2", 35.0, "m2"), [NORMAL]) == ("medium", 10)
    assert severity.severity(make_finding("X2", 5.0, "St"), [NORMAL]) == ("medium", 10)
    assert severity.severity(make_finding("X2", 500.0, "m2"), [NORMAL])[1] != 10
    assert severity.severity(make_finding("X2", 1.0, "m2"), [NORMAL])[1] != 10


# ---- quantity concerned -------------------------------------------------------

@pytest.mark.parametrize("quantity,unit,expected", [
    (10, "St", "large"), (9.5, "St", "middle"), (2, "Stk", "middle"), (1.99, "Stck", "small"),
    (10, "Stück", "large"), (10, " st. ", "large"), (10, "ST", "large"),
    (100, "m2", "large"), (99, "m", "middle"), (10, "m3", "middle"), (9, "kg", "small"),
    (10, None, "middle"), (100, "", "large"), (10, "psch", "middle"),
    (None, "m2", None), (0, "m2", None), (-1, "St", None), (True, "St", None), ("12", "St", None),
    (float("nan"), "m", None), (float("inf"), "m", None),
])
def test_band_of_one_quantity(quantity, unit, expected):
    assert severity.band(quantity, unit) == expected


def test_exposure_quantity_comes_before_the_item_quantities():
    big_item = make_item(quantity=900.0, unit="m2")
    assert severity.severity(make_finding("X2", 1.0, "St"), [big_item]) == ("info", 9)
    assert severity.severity(make_finding("X2", None, None), [big_item]) == ("high", 6)


def test_item_quantities_stand_in_when_exposure_has_none():
    small, middle, large = make_item(quantity=1.0, unit="St"), make_item(quantity=50.0), make_item(quantity=12.0, unit="St")
    finding = make_finding("X2", None, None)
    assert severity.severity(finding, [small, large]) == ("high", 6)      # one large is enough
    assert severity.severity(finding, [small, small]) == ("info", 9)       # small only if all are small
    assert severity.severity(finding, [small, middle]) == ("medium", 10)
    # Only normal items stand in: a Bedarfsposition or a Pauschale beside a normal item gives no quantity.
    assert severity.severity(finding, [small, OPTIONAL]) == ("info", 9)
    assert severity.severity(finding, [small, LUMP_SUM]) == ("medium", 7)
    assert severity.severity(finding, [make_item(quantity=None), OPTIONAL]) == ("medium", 8)


# ---- edge cases ---------------------------------------------------------------

def test_finding_with_no_cited_item():
    assert severity.severity(make_finding("X2", None, None), []) == ("medium", 8)
    assert severity.severity(make_finding("X2", None, None), [None, None]) == ("medium", 8)
    assert severity.severity(make_finding("X2", None, None), None) == ("medium", 8)
    assert severity.severity(make_finding("X2", 250.0, "m2"), []) == ("high", 6)
    assert severity.severity(make_finding("X2", 1.0, "St", sources=[]), []) == ("info", 9)


def test_heading_is_never_a_cited_item():
    assert severity.severity(make_finding("X2", None, None), [HEADING]) == ("medium", 8)
    assert severity.severity(make_finding("X2", None, None), [HEADING, NOTE]) == ("medium", 4)
    assert severity.severity(make_finding("X2", None, None), [HEADING, OPTIONAL]) == ("info", 5)


def test_broken_findings_get_a_level_and_do_not_crash():
    assert severity.severity({}, []) == ("info", 1)
    assert severity.severity({"check": None, "exposure": None}, [NORMAL]) == ("info", 1)
    assert severity.severity({"check": "x2"}, [NORMAL]) == ("info", 1)  # the catalogue is case-sensitive
    assert severity.severity({"check": "X2", "exposure": "viel"}, [{"kind": "normal"}]) == ("medium", 8)
    assert severity.severity({"check": "X2"}, ["no item", 7]) == ("medium", 8)


def test_every_catalogue_check_gets_one_of_the_three_levels():
    catalogue = ["X1", "X2", "X3", "S", "V1", "V2"] + ["B%d" % n for n in range(1, 13)]
    assert sorted(catalogue) == sorted(severity.KNOWN_CHECKS)
    for check in catalogue:
        for cited in ([], [NORMAL], [NOTE], [OPTIONAL], [LUMP_SUM]):
            level, number = severity.severity(make_finding(check, None, None), cited)
            assert level in severity.LEVELS and 1 <= number <= len(severity.RULES)


def test_function_is_pure_and_reads_no_price():
    class NoPrice(dict):
        def _stop(self, key):
            if key in ("unit_price", "total"):
                raise AssertionError("a rule read %s" % key)

        def __getitem__(self, key):
            self._stop(key)
            return dict.__getitem__(self, key)

        def get(self, key, default=None):
            self._stop(key)
            return dict.get(self, key, default)

    finding = make_finding("X2", None, None)
    for cited in ([NORMAL], [NOTE], [OPTIONAL], [LUMP_SUM, NORMAL], [HEADING]):
        priced = [NoPrice(item, unit_price=7654.32, total=98765.43) for item in cited]
        before = (copy.deepcopy(finding), copy.deepcopy(priced))
        assert severity.severity(finding, priced) == severity.severity(finding, cited)
        assert (finding, priced) == before
    source = inspect.getsource(severity)
    assert "unit_price" not in source and '"total"' not in source and "price_mode" not in source


# ---- the table in the code and the page -----------------------------------------

def page_rules():
    with open(RULES_PAGE, encoding="utf-8") as handle:
        page = handle.read()
    rows = re.findall(r"^\|\s*(\d+)\s*\|([^|]*)\|\s*`(\w+)`\s*\|[^|]*\|\s*$", page, re.M)
    return page, [(int(number), level, " ".join(text.split())) for number, text, level in rows]


def test_code_table_and_page_have_the_same_rules_in_the_same_order():
    _page, rows = page_rules()
    code = [(number, level, text) for number, level, text, _fits in severity.RULES]
    assert len(rows) == len(code)
    assert rows == code
    assert [number for number, _level, _text in code] == list(range(1, len(code) + 1))
    assert set(level for _number, level, _text in code) == set(severity.LEVELS)


def test_page_states_thresholds_of_the_code_and_that_no_expert_confirmed_it():
    page, _rows = page_rules()
    assert "No expert has confirmed these rules" in page and "proposal for the expert session" in page
    assert "No rule uses a price" in page
    assert "%d or more for pieces" % severity.LARGE_FROM["pieces"] in page
    assert "%d or more for every other unit" % severity.LARGE_FROM["other"] in page
    assert "below %d for pieces" % severity.SMALL_BELOW["pieces"] in page
    assert "below %d for every other unit" % severity.SMALL_BELOW["other"] in page
    for word in ("hoch", "mittel", "Hinweis", "Bedarfsposition", "Wahlposition", "Pauschale", "Vorbemerkung"):
        assert word in page, word
    assert len(page.split()) <= 750 and len(page.splitlines()) <= 45  # one page


def test_no_rule_text_names_a_price():
    for _number, _level, text, _fits in severity.RULES:
        assert not re.search(r"price|preis|total|EP\b|GP\b|€|EUR", text, re.I), text


# ---- cited items ----------------------------------------------------------------

def test_cited_item_is_the_record_that_holds_the_quote():
    items = [
        make_item("heading", None, None, item_no="1", short_text="Estricharbeiten", long_text=""),
        make_item("preliminary_note", None, None, item_no="1", short_text="Vorbemerkung",
                  long_text="Der AN liefert die Rand-\nstreifen."),
        make_item("heading", None, None, item_no="2", short_text="Titel zwei", long_text=""),
        make_item("optional", 3.0, "St", item_no="2", short_text="Position zwei", long_text=""),
        make_item("heading", None, None, item_no="3", short_text="Nur Titel", long_text=""),
    ]
    sources = [{"doc": "LV_91", "item_no": "1", "page": 1, "quote": "Der AN liefert die Randstreifen."},
               {"doc": "LV_91", "item_no": "2", "page": 1, "quote": "steht nur auf der Seite"},
               {"doc": "LV_91", "item_no": "3", "page": 1, "quote": "steht nirgends"},
               {"doc": "LV_91", "item_no": "9", "page": 1, "quote": "keine solche Position"},
               "kein Objekt"]
    cited = severity.cited_items(make_finding(sources=sources), severity.index_items(items + ["kein Objekt"]))
    assert [item and item["short_text"] for item in cited] == ["Vorbemerkung", "Position zwei", "Nur Titel", None, None]
    assert severity.cited_items({"sources": "none"}, {}) == []
    assert severity.cited_items({}, {}) == []


def test_contract_samples_get_their_levels_by_hand():
    findings, items = contract.load_sample("findings"), contract.load_sample("items")
    result, decided = severity.apply(findings, items)
    # X1-f0a30d: 85 m, a Vorbemerkung and a normal item -> middle quantity, rule 10.
    # X2-5b4bb3: 120 m2, two normal items -> large, rule 6.
    # S-acff08: quantity null, both sources cite the Pauschale 1.40 -> rule 7.
    assert decided == [("medium", 10), ("high", 6), ("medium", 7)]
    assert [finding["severity"] for finding in result] == ["medium", "high", "medium"]
    assert contract.errors("findings", result) == []


def test_apply_changes_only_severity_and_not_its_input():
    findings = contract.load_sample("findings")
    for finding in findings:
        finding["future_key"] = {"kept": [1, 2.5, None]}
    before = copy.deepcopy(findings)
    result, _decided = severity.apply(findings, contract.load_sample("items"))
    assert findings == before
    for old, new in zip(before, result):
        assert list(new) == list(old)  # same keys in the same order
        assert {key: value for key, value in new.items() if key != "severity"} == \
               {key: value for key, value in old.items() if key != "severity"}


# ---- the command ------------------------------------------------------------------

def run(*args):
    return subprocess.run([sys.executable, "-m", "pipeline.common.severity"] + [str(arg) for arg in args],
                          cwd=ROOT, capture_output=True, text=True)


def write_json(path, data):
    with open(str(path), "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)


def read_json(path):
    with open(str(path), encoding="utf-8") as handle:
        return json.load(handle)


def test_command_writes_the_levels_and_prints_the_counts(tmp_path):
    out = tmp_path / "sub" / "findings.json"
    done = run(contract.sample_path("findings"), contract.sample_path("items"), out)
    assert done.returncode == 0, done.stderr
    result, before = read_json(out), contract.load_sample("findings")
    assert [finding["severity"] for finding in result] == ["medium", "high", "medium"]
    for old, new in zip(before, result):
        old["severity"] = new["severity"]
    assert result == before
    assert contract.errors("findings", result) == []
    lines = done.stdout.splitlines()
    assert lines[:3] == ["findings: 3", "high: 1, medium: 2, info: 0", "changed level against the input: 3 of 3"]
    assert lines[3:] == ["  X1-f0a30d: high -> medium (rule 10)", "  X2-5b4bb3: medium -> high (rule 6)",
                         "  S-acff08: info -> medium (rule 7)"]


def test_command_twice_changes_nothing_and_may_write_onto_its_input(tmp_path):
    path = tmp_path / "findings.json"
    assert run(contract.sample_path("findings"), contract.sample_path("items"), path).returncode == 0
    first = read_json(path)
    done = run(path, contract.sample_path("items"), path)
    assert done.returncode == 0, done.stderr
    assert read_json(path) == first
    assert "changed level against the input: 0 of 3" in done.stdout
    assert os.listdir(str(tmp_path)) == ["findings.json"]  # no temporary file is left


def test_command_keeps_german_text_and_sets_a_missing_severity(tmp_path):
    finding = make_finding("X3", 250.0, "m2", explanation_de="Die Dämmung fehlt – größer als 26 m².")
    del finding["severity"]
    source, out = tmp_path / "in.json", tmp_path / "out.json"
    write_json(source, [finding])
    write_json(tmp_path / "items.json", [])
    done = run(source, tmp_path / "items.json", out)
    assert done.returncode == 0, done.stderr
    assert "  X3-aaaaaa: None -> high (rule 6)" in done.stdout
    with open(str(out), encoding="utf-8") as handle:
        assert "Die Dämmung fehlt – größer als 26 m²." in handle.read()
    assert read_json(out)[0]["severity"] == "high"


def test_command_refuses_broken_input_and_writes_nothing(tmp_path):
    items = contract.sample_path("items")
    out = tmp_path / "out.json"
    write_json(tmp_path / "object.json", {"X1-aaaaaa": {}})
    with open(str(tmp_path / "broken.json"), "w", encoding="utf-8") as handle:
        handle.write("[{")
    no_id = make_finding("X2", 5.0, "St")
    del no_id["id"]
    write_json(tmp_path / "no_id.json", [no_id])
    write_json(tmp_path / "items_object.json", {})
    for args, code in (((tmp_path / "object.json", items, out), 2), ((tmp_path / "broken.json", items, out), 2),
                       ((tmp_path / "missing.json", items, out), 2),
                       ((contract.sample_path("findings"), tmp_path / "items_object.json", out), 2),
                       ((tmp_path / "no_id.json", items, out), 1)):
        done = run(*args)
        assert done.returncode == code, (args, done.stdout, done.stderr)
        assert done.stderr.strip() and not out.exists()
    assert run().returncode == 2
