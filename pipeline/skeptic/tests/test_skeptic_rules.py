"""Rule checks on synthetic input: numbers, one-quote contradictions, quotes, lowering."""
import copy
import itertools
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402

import skeptic_samples as samples  # noqa: E402
from pipeline.skeptic import STATUSES, rules  # noqa: E402
from pipeline.skeptic.evidence import without_prices  # noqa: E402

ITEMS = without_prices(samples.items())


def numbers(explanation="", question="", **changes):
    return rules.unsupported_numbers(
        samples.finding(explanation_de=explanation, question_de=question, **changes), ITEMS)


# --- rule 1: numbers -------------------------------------------------------

def test_number_from_a_quote_is_supported():
    assert numbers("Der Estrich ist 65 mm dick, der Belag rechnet mit 50 mm.") == []


def test_number_from_the_cited_item_is_supported():
    # 2,5 stands only in the long text of LV_92 2.20, not in its quote
    assert numbers("Der Belag ist 2,5 mm dick.") == []


def test_quantity_and_item_number_of_the_cited_item_are_supported():
    assert numbers("Pos. 1.10 hat 35 m2, Pos. 2.20 hat 26 m2.") == []


def test_number_in_neither_is_reported():
    assert numbers("Es fehlen 9 m2.") == ["9"]


def test_number_of_an_item_that_is_not_cited_is_reported():
    # 85 is the quantity of LV_92 2.10 and 9 that of LV_93 3.10; the finding cites neither
    assert numbers("LV 92 hat 85 m Randstreifen.", "Wer streicht die 9 m2?") == ["85", "9"]


def test_computed_sum_is_reported():
    assert numbers("Zusammen sind es 61 m2 (35 + 26).") == ["61"]


def test_question_is_checked_too_and_each_number_stands_once():
    assert numbers("Es fehlen 9 m2.", "Wer liefert die 9 m2 und die 77 m?") == ["9", "77"]


def test_item_number_named_but_not_cited_is_reported():
    assert numbers("Auch Pos. 2.10 nennt den Estrich.") == ["2.10"]


def test_decimal_comma_and_trailing_zeros_compare_by_value():
    assert numbers("35,000 m2 und 65,0 mm") == []
    assert numbers("35,5 m2") == ["35,5"]


def test_dotted_token_is_an_identifier_not_a_decimal():
    # "1.1" is not the item "1.10" and not the value 1,1
    assert numbers("Pos. 1.1") == ["1.1"]


def test_item_number_with_leading_dot_is_one_token():
    items = ITEMS + without_prices([samples.item("LV_94", ".48", "Rohrdurchführung", "DN 100")])
    finding = samples.finding(
        explanation_de="Pos. .48 setzt eine Bohrung voraus, Pos. .49 nicht.",
        sources=[{"doc": "LV_94", "item_no": ".48", "page": 1, "quote": "DN 100"},
                 {"doc": "LV_91", "item_no": "1.10", "page": 2, "quote": "Nenndicke 65 mm"}])
    assert rules.unsupported_numbers(finding, items) == [".49"]


def test_code_words_are_not_numbers():
    assert numbers("m2, m3, T30, C35, DN100 und F90 sind Kennwörter.") == []


def test_times_sign_separates_two_numbers():
    assert numbers("Leuchte 300x1200 mm") == ["300", "1200"]
    assert numbers("Belag 65x50") == []


def test_list_names_are_not_numbers():
    assert numbers("LV 91 und LV 92 widersprechen sich, LV 93 schweigt.") == []
    assert numbers("In den Listen 091 und 92 steht nichts.",
                   lists_searched=["LV_091", "LV_92"]) == ["92"]


def test_name_of_a_list_that_was_not_searched_stays_a_number():
    assert numbers("LV 99 fehlt.") == ["99"]


def test_count_of_searched_lists_is_supported():
    assert numbers("In den 3 vorliegenden Listen steht kein Anstrich.") == []
    assert numbers("In den 4 vorliegenden Listen steht kein Anstrich.") == ["4"]


def test_anonymization_marks_support_nothing_and_are_not_reported():
    items = without_prices([samples.item("LV_91", "1.10", "Estrich [PERSON_169]", "Nenndicke 65 mm")])
    finding = samples.finding(
        explanation_de="[FIRMA_071] liefert 169 Stück.",
        sources=[{"doc": "LV_91", "item_no": "1.10", "page": 2, "quote": "Estrich [PERSON_169]"},
                 {"doc": "LV_91", "item_no": "1.10", "page": 2, "quote": "Nenndicke 65 mm"}])
    assert rules.unsupported_numbers(finding, items) == ["169"]


def test_no_text_and_no_numbers_give_nothing():
    assert numbers() == []
    assert numbers(None, None) == []
    assert numbers("Der Estrich widerspricht dem Belag.") == []


def test_cited_item_missing_in_items_leaves_only_the_quotes():
    finding = samples.finding(explanation_de="65 mm gegen 50 mm, Menge 35 m2.")
    assert rules.unsupported_numbers(finding, []) == ["35"]


def test_price_fields_never_support_a_number():
    # 437,5 is the `total` of the synthetic items; load_items drops it, and the rule ignores it anyway
    finding = samples.finding(explanation_de="Der Betrag ist 437,5.")
    assert rules.unsupported_numbers(finding, samples.items()) == ["437,5"]


@pytest.mark.parametrize("token,key", [
    ("35", "35"), ("35,0", "35"), ("35,000", "35"), ("16,50", "16,5"), ("0,000", "0"),
    ("007", "007"), ("02", "02"), ("0", "0"), ("11.4.60", "11.4.60"), (".48", ".48"),
    ("50.000", "50.000"),
])
def test_number_key(token, key):
    assert rules.number_key(token) == key


@pytest.mark.parametrize("quantity,token", [
    (35.0, "35"), (2.5, "2,5"), (17.226, "17,226"), (0, "0"), (None, ""), (True, ""),
])
def test_quantity_token(quantity, token):
    assert rules.quantity_token(quantity) == token


# --- rule 2: contradiction with one quote ----------------------------------

def test_contradiction_with_two_different_quotes_passes():
    assert rules.single_quote_contradiction(samples.finding()) is False


def test_contradiction_with_one_quote_is_caught():
    finding = samples.finding(sources=samples.finding()["sources"][:1])
    assert rules.single_quote_contradiction(finding) is True


def test_contradiction_with_the_same_quote_twice_is_caught():
    source = samples.finding()["sources"][0]
    other = dict(source, doc="LV_92", quote="  schwimmender   Estrich auf Wärme-\ndämmung, Nenndicke 65 mm ")
    assert rules.single_quote_contradiction(samples.finding(sources=[source, other])) is True


def test_contradiction_without_sources_or_with_empty_quotes_is_caught():
    assert rules.single_quote_contradiction(samples.finding(sources=[])) is True
    empty = [{"doc": "LV_91", "item_no": "1.10", "page": 2, "quote": ""},
             {"doc": "LV_92", "item_no": "2.20", "page": 4, "quote": None}]
    assert rules.single_quote_contradiction(samples.finding(sources=empty)) is True


def test_one_quote_is_enough_for_a_gap_or_a_double_assignment():
    one = samples.finding()["sources"][:1]
    assert rules.single_quote_contradiction(samples.finding(check="X3", type="gap", sources=one)) is False
    assert rules.single_quote_contradiction(
        samples.finding(check="X1", type="double_assignment", sources=one)) is False


def test_contradiction_is_known_by_check_or_by_type():
    one = samples.finding()["sources"][:1]
    assert rules.single_quote_contradiction(samples.finding(check="X2", type="gap", sources=one)) is True
    assert rules.single_quote_contradiction(samples.finding(check="S", type="contradiction", sources=one)) is True


# --- rule 3: quotes ----------------------------------------------------------

def test_quotes_that_stand_in_the_cited_items_are_not_recorded():
    assert rules.quotes_not_found(samples.finding(), ITEMS) == []


def test_quote_that_stands_nowhere_is_recorded_with_doc_item_and_page():
    sources = [samples.finding()["sources"][0],
               {"doc": "LV_92", "item_no": "2.20", "page": 4, "quote": "Estrich 55 mm"}]
    finding = samples.finding(sources=sources)
    assert rules.quotes_not_found(finding, ITEMS) == [{"doc": "LV_92", "item_no": "2.20", "page": 4}]
    result = rules.check(finding, ITEMS)
    assert result["quotes_not_found"] == [{"doc": "LV_92", "item_no": "2.20", "page": 4}]
    assert result["lowers_to"] is None, "a missing quote is recorded, it does not lower"


def test_quote_from_another_item_of_the_same_list_is_recorded():
    sources = [samples.finding()["sources"][0],
               {"doc": "LV_92", "item_no": "2.20", "page": 4, "quote": "Randdämmstreifen an allen"}]
    assert rules.quotes_not_found(samples.finding(sources=sources), ITEMS) == [
        {"doc": "LV_92", "item_no": "2.20", "page": 4}]


def test_quote_that_stands_only_on_the_cited_page_is_found_with_page_text():
    sources = [samples.finding()["sources"][0],
               {"doc": "LV_92", "item_no": "2.20", "page": 4, "quote": "Seitentext nur hier 50 mm"}]
    finding = samples.finding(sources=sources)
    pages = {("LV_92", 4): "Kopfzeile\nSeiten-\ntext nur   hier 50 mm\n", ("LV_92", 5): "anderes"}
    assert rules.quotes_not_found(finding, ITEMS, pages) == []
    assert rules.quotes_not_found(finding, ITEMS) == [{"doc": "LV_92", "item_no": "2.20", "page": 4}]
    wrong_page = {("LV_92", 5): "Seitentext nur hier 50 mm"}
    assert len(rules.quotes_not_found(finding, ITEMS, wrong_page)) == 1


def test_quote_check_uses_the_normalization_of_quotes_py():
    # line-end hyphen and whitespace runs in the item; the quote is in normalized form
    sources = [{"doc": "LV_91", "item_no": "1.10", "page": 2,
                "quote": "Estrich   auf Wärmedämmung,\nNenndicke"},
               samples.finding()["sources"][1]]
    assert rules.quotes_not_found(samples.finding(sources=sources), ITEMS) == []
    case = [dict(sources[0], quote="estrich auf wärmedämmung"), sources[1]]
    assert len(rules.quotes_not_found(samples.finding(sources=case), ITEMS)) == 1, "the check is case-sensitive"


def test_check_says_whether_page_text_was_used():
    assert rules.check(samples.finding(), ITEMS)["page_text_checked"] is False
    assert rules.check(samples.finding(), ITEMS, {})["page_text_checked"] is True


def test_load_pages_reads_the_text_cache_layout(tmp_path):
    (tmp_path / "LV_91.txt").write_text("=== PAGE 1 ===\nerste Seite\n=== PAGE 2 ===\nzweite Seite\n",
                                        encoding="utf-8")
    (tmp_path / "LV_92.txt").write_text("=== PAGE 1 ===\nandere Liste\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("=== PAGE 1 ===\nkein Seitentext\n", encoding="utf-8")
    pages = rules.load_pages(str(tmp_path))
    assert sorted(pages) == [("LV_91", 1), ("LV_91", 2), ("LV_92", 1)]
    assert "zweite Seite" in pages[("LV_91", 2)]


# --- check() and lowering -----------------------------------------------------

def test_check_of_a_clean_finding_lowers_nothing():
    assert rules.check(samples.finding(), ITEMS) == {
        "unsupported_numbers": [], "single_quote_contradiction": False, "quotes_not_found": [],
        "page_text_checked": False, "lowers_to": None}


def test_check_lowers_for_a_number_and_for_one_quote():
    assert rules.check(samples.finding(explanation_de="Es fehlen 9 m2."), ITEMS)["lowers_to"] == "weakened"
    one = samples.finding(sources=samples.finding()["sources"][:1],
                          explanation_de="Der Estrich ist 65 mm dick.")
    result = rules.check(one, ITEMS)
    assert result["unsupported_numbers"] == [] and result["single_quote_contradiction"] is True
    assert result["lowers_to"] == "weakened"


def test_lower_never_raises_a_status():
    rank = {status: n for n, status in enumerate(STATUSES)}
    for status, floor in itertools.product(STATUSES, [None, "weakened", "refuted"]):
        result = rules.lower(status, {"lowers_to": floor})
        assert rank[result] >= rank[status], (status, floor, result)
        if floor is None:
            assert result == status


def test_lower_table():
    fired, quiet = {"lowers_to": "weakened"}, {"lowers_to": None}
    assert rules.lower("survived", fired) == "weakened"
    assert rules.lower("weakened", fired) == "weakened"
    assert rules.lower("refuted", fired) == "refuted"
    assert [rules.lower(s, quiet) for s in STATUSES] == list(STATUSES)


def test_lower_rejects_unknown_statuses():
    with pytest.raises(ValueError):
        rules.lower("confirmed", {"lowers_to": None})
    with pytest.raises(ValueError):
        rules.lower("survived", {"lowers_to": "survivd"})


def test_rule_note_names_the_rule_that_fired():
    clean = rules.check(samples.finding(), ITEMS)
    assert rules.rule_note(clean) == ""
    fired = rules.check(samples.finding(explanation_de="Es fehlen 9 m2.",
                                        sources=[{"doc": "LV_91", "item_no": "1.10", "page": 2,
                                                  "quote": "steht nicht da"}]), ITEMS)
    note = rules.rule_note(fired)
    assert note.startswith("Regelprüfung: ") and note.endswith(".")
    assert "9" in note and "nur einem Zitat" in note and "LV_91 1.10 S. 2" in note


def test_apply_rules_lowers_and_keeps_the_agent_verdict():
    findings = [samples.finding(explanation_de="Es fehlen 9 m2."), samples.second_finding()]
    verdicts = {"X2-aaaaaa": samples.verdict("survived", "note a"),
                "X1-bbbbbb": samples.verdict("survived", "note b")}
    before = copy.deepcopy(verdicts)
    result = rules.apply_rules(findings, ITEMS, verdicts)
    assert verdicts == before, "the input must not change"
    assert list(result) == ["X2-aaaaaa", "X1-bbbbbb"]
    lowered, kept = result["X2-aaaaaa"], result["X1-bbbbbb"]
    assert (lowered["agent_status"], lowered["status"]) == ("survived", "weakened")
    assert lowered["note"] == "note a" and lowered["origin"] == "agent session, independent context"
    assert lowered["rules"]["unsupported_numbers"] == ["9"] and "9" in lowered["rule_note"]
    assert (kept["agent_status"], kept["status"], kept["rule_note"]) == ("survived", "survived", "")


def test_apply_rules_never_improves_a_verdict():
    findings = [samples.finding(), samples.second_finding(explanation_de="Es fehlen 9 m.")]
    for status in STATUSES:
        verdicts = {"X2-aaaaaa": samples.verdict(status), "X1-bbbbbb": samples.verdict(status)}
        result = rules.apply_rules(findings, ITEMS, verdicts)
        assert result["X2-aaaaaa"]["status"] == status, "no rule fired, the verdict stays"
        assert result["X1-bbbbbb"]["status"] == ("weakened" if status == "survived" else status)


def test_apply_rules_twice_gives_the_same_result():
    findings = [samples.finding(explanation_de="Es fehlen 9 m2.")]
    once = rules.apply_rules(findings, ITEMS, {"X2-aaaaaa": samples.verdict("survived")})
    assert rules.apply_rules(findings, ITEMS, once) == once
    # a hand-edited status cannot undo the rule: the agent verdict is the base
    edited = copy.deepcopy(once)
    edited["X2-aaaaaa"]["status"] = "survived"
    assert rules.apply_rules(findings, ITEMS, edited)["X2-aaaaaa"]["status"] == "weakened"


def test_apply_rules_needs_one_verdict_per_finding():
    findings = [samples.finding(), samples.second_finding()]
    with pytest.raises(ValueError, match="X1-bbbbbb"):
        rules.apply_rules(findings, ITEMS, {"X2-aaaaaa": samples.verdict()})
    with pytest.raises(ValueError, match="X9-zzzzzz"):
        rules.apply_rules(findings[:1], ITEMS, {"X2-aaaaaa": samples.verdict(),
                                                "X9-zzzzzz": samples.verdict()})
    with pytest.raises(ValueError):
        rules.apply_rules(findings[:1], ITEMS, {"X2-aaaaaa": samples.verdict("confirmed")})


def test_command_writes_the_lowered_verdicts(tmp_path, capsys):
    def write(name, data):
        path = tmp_path / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(path)

    findings = write("findings.json", [samples.finding(explanation_de="Es fehlen 9 m2."),
                                       samples.second_finding()])
    items = write("items.json", samples.items())
    verdicts = write("verdicts.json", {"X2-aaaaaa": samples.verdict(), "X1-bbbbbb": samples.verdict()})
    text_dir = tmp_path / "text"
    text_dir.mkdir()
    (text_dir / "LV_91.txt").write_text("=== PAGE 2 ===\nNenndicke 65 mm\n", encoding="utf-8")
    out = tmp_path / "out.json"
    assert rules.main([findings, items, verdicts, str(out), "--text-dir", str(text_dir)]) == 0
    printed = capsys.readouterr().out
    assert "X2-aaaaaa: survived -> weakened" in printed
    assert "2 verdicts, 1 lowered by a rule" in printed
    stored = out.read_text(encoding="utf-8")
    assert "unit_price" not in stored and "FINDER NOTE" not in stored
    data = json.loads(stored)
    assert data["X2-aaaaaa"]["status"] == "weakened" and data["X1-bbbbbb"]["status"] == "survived"
    assert data["X2-aaaaaa"]["rules"]["page_text_checked"] is True


def test_command_fails_when_a_verdict_is_missing(tmp_path, capsys):
    def write(name, data):
        path = tmp_path / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(path)

    out = tmp_path / "out.json"
    code = rules.main([write("findings.json", [samples.finding()]), write("items.json", samples.items()),
                       write("verdicts.json", {}), str(out)])
    assert code == 1 and not out.exists()
    assert "X2-aaaaaa" in capsys.readouterr().err
