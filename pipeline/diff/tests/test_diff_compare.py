import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

from diff_items import heading, item, order, tender  # noqa: E402
from pipeline.diff import compare  # noqa: E402
from pipeline.diff import text as t  # noqa: E402


def stage(b, a=None):
    return compare.compare(a or tender(), b, "stage")


def test_same_list_in_another_number_writing_is_all_equal():
    result = compare.compare(tender(), order())
    assert result["matching"]["both"] == 3 and result["matching"]["by_number"] == 3
    assert result["matching"]["only_a"] == [] and result["matching"]["only_b"] == []
    for name in ("short_text", "long_text", "quantity", "unit"):
        assert result["fields"][name]["equal"] == 3 and result["fields"][name]["not_equal"] == 0
    assert result["sections"]["both"] == 1 and result["sections"]["titles"]["equal"] == 1
    assert "stage" not in result
    assert result["from_start"]["same_from_start"] == 3


def test_added_item():
    new = item("1.40", "Hydrant DN 80", "Hydrant setzen.", 0.0, None, doc="B.D86")
    result = stage(order(extra=[new]))
    assert result["stage"]["added"] == ["1.40"] and result["stage"]["removed"] == []
    assert result["matching"]["only_b"] == ["1.40"] and result["matching"]["both"] == 3
    assert result["stage"]["added_with_quantity_zero"] == ["1.40"]
    assert result["stage"]["added_without_unit"] == ["1.40"]
    assert result["stage"]["added_with_a_title_of_a"] == []
    assert result["b"]["quantity_zero"] == ["1.40"]


def test_removed_item():
    result = stage(order(drop=["01.0020"]))
    assert result["stage"]["removed"] == ["01.0020"] and result["stage"]["added"] == []
    assert result["matching"]["only_a"] == ["01.0020"] and result["matching"]["both"] == 2


def test_changed_quantity():
    result = stage(order({"01.0010": {"quantity": 12.5}}))
    assert result["fields"]["quantity"]["not_equal_items"] == ["01.0010"]
    assert result["stage"]["changed"]["quantity"] == [{"item_no": "01.0010", "a": 10.0, "b": 12.5}]
    assert result["stage"]["changed"]["unit"] == [] and result["stage"]["changed"]["text"] == []


def test_changed_unit():
    result = stage(order({"01.0020": {"unit": "Stück"}}))
    assert result["fields"]["unit"]["not_equal_items"] == ["01.0020"]
    assert result["stage"]["changed"]["unit"] == [{"item_no": "01.0020", "a": "St", "b": "Stück"}]
    assert result["fields"]["quantity"]["not_equal"] == 0


def test_changed_text():
    result = stage(order({"01.0030": {"long": "Schieber mit Elektroantrieb liefern."}}))
    assert result["fields"]["long_text"]["differs_items"] == ["01.0030"]
    assert result["fields"]["short_text"]["not_equal"] == 0
    assert result["stage"]["changed"]["text"] == ["01.0030"]
    assert result["stage"]["renumbered"] == []


def test_text_that_differs_only_by_anonymization_is_its_own_class_and_no_change():
    result = stage(order({"01.0010": {"short": "Rohr DN 100 liefern", "long": "Rohr DN 100 [PERSON_7] und verlegen."},
                          "01.0020": {"long": "Bogen 90 Grad [PERSON_0012]."}}),
                   a=[tender()[0], tender()[1],
                      item("01.0020", "Bogen DN 100", "Bogen 90 Grad [PERSON_12].", 4.0, "St"),
                      tender()[3]])
    field = result["fields"]["long_text"]
    assert field["equal"] == 1 and field["not_equal"] == 2
    assert field[t.ANONYMIZED_ONE + "_items"] == ["01.0010"]
    assert field[t.ANONYMIZED_BOTH + "_items"] == ["01.0020"]
    assert field[t.DIFFERS] == 0
    assert result["stage"]["changed"]["text"] == []


def test_renumbered_item_is_found_by_its_text():
    moved = item("2.10", "Schieber DN 100", "Schieber mit Handrad liefern.", 1.0, "St", doc="B.D86")
    result = stage(order(drop=["01.0030"], extra=[moved]))
    assert result["stage"]["renumbered"] == [{"a": "01.0030", "b": "2.10"}]
    assert result["stage"]["added"] == [] and result["stage"]["removed"] == []
    assert result["matching"]["both"] == 3 and result["matching"]["by_number"] == 2


def test_inserted_item_that_shifts_the_numbers():
    b = [item("1.10", "Aushub", "Boden ausheben.", 5.0, "m3", doc="B.D86")]
    for number, source in zip(("1.20", "1.30", "1.40"), tender()[1:]):
        b.append(item(number, source["short_text"], source["long_text"], source["quantity"],
                      source["unit"], doc="B.D86"))
    result = stage(b)
    assert result["stage"]["added"] == ["1.10"] and result["stage"]["removed"] == []
    assert result["stage"]["renumbered"] == [{"a": "01.0010", "b": "1.20"}, {"a": "01.0020", "b": "1.30"},
                                            {"a": "01.0030", "b": "1.40"}]
    assert result["fields"]["quantity"]["not_equal"] == 0


def test_text_that_moved_between_short_and_long_text_is_not_a_renumbering():
    a = [item("1.1", "Rohr DN 100", "liefern und verlegen."), item("1.2", "Bogen", "Bogen liefern.")]
    b = [item("1.1", "Rohr DN 100 liefern", "und verlegen.", doc="B"),
         item("1.2", "Bogen", "Bogen liefern.", doc="B")]
    result = compare.compare(a, b, "stage")
    assert result["matching"]["by_number"] == 2 and result["matching"]["renumbered"] == []
    assert result["stage"]["renumbered"] == []
    assert result["stage"]["changed"]["text"] == ["1.1"]


def test_a_number_pair_with_the_same_text_is_not_taken_by_another_item():
    a = [item("1.1", "Rohr DN 100", "liefern."), item("1.2", "Rohr", "DN 100 liefern.")]
    b = [item("1.1", "Muffe", "Muffe setzen.", doc="B"), item("1.2", "Rohr DN 100", "liefern.", doc="B")]
    result = compare.compare(a, b, "stage")
    assert result["matching"]["renumbered"] == []
    assert result["matching"]["by_number"] == 2


def test_shifted_numbers_are_seen_when_one_title_is_the_start_of_the_next():
    a = [item("1.1", "Rohr", "Rohr."), item("1.2", "Rohr DN 100", "Rohr. Mit Muffe.")]
    b = [item("1.1", "Aushub", "Boden ausheben.", doc="B"), item("1.2", "Rohr", "Rohr.", doc="B"),
         item("1.3", "Rohr DN 100", "Rohr. Mit Muffe.", doc="B")]
    result = compare.compare(a, b, "stage")
    assert result["stage"]["added"] == ["1.1"]
    assert result["stage"]["renumbered"] == [{"a": "1.1", "b": "1.2"}, {"a": "1.2", "b": "1.3"}]


def test_numbers_pair_only_when_item_no_key_says_so():
    a = [item("01.01.0010", "Rohr"), item("01.01.1", "Bogen", "Bogen liefern.")]
    b = [item("1.1.10", "Rohr", doc="B"), item("1.1.100", "Muffe", "Muffe liefern.", doc="B")]
    result = compare.compare(a, b)
    assert result["matching"]["both"] == 1 and result["matching"]["by_number"] == 1
    assert result["matching"]["only_a"] == ["01.01.1"]
    assert result["matching"]["only_b"] == ["1.1.100"]


def test_number_replaced_by_a_placeholder_is_kept_and_paired_by_position():
    b = order()
    b[2]["item_no"] = "TEL00009"
    result = stage(b)
    assert result["b"]["placeholder_numbers"] == ["TEL00009"]
    assert result["matching"]["by_position"] == [{"a": "01.0020", "b": "TEL00009"}]
    assert result["matching"]["both"] == 3 and result["matching"]["by_number"] == 2
    assert result["stage"]["added"] == [] and result["stage"]["removed"] == []
    assert result["fields"]["quantity"]["equal"] == 3


def test_same_placeholder_number_in_both_files_pairs_by_number():
    a, b = tender(), order()
    a[2]["item_no"] = "TEL00009"
    b[2]["item_no"] = "TEL00009"
    result = compare.compare(a, b)
    assert result["matching"]["by_number"] == 3 and result["matching"]["by_position"] == []


def test_placeholder_number_is_not_guessed_when_two_items_could_be_meant():
    a = [item("1.1", "Rohr A", "A."), item("1.2", "Rohr B", "B."), item("1.3", "Rohr C", "C."),
         item("1.4", "Rohr D", "D.")]
    b = [item("1.1", "Rohr A", "A.", doc="B"), item("TEL00009", "", "", doc="B"),
         item("1.4", "Rohr D", "D.", doc="B")]
    result = compare.compare(a, b)
    assert result["matching"]["by_position"] == []
    assert result["matching"]["only_a"] == ["1.2", "1.3"] and result["matching"]["only_b"] == ["TEL00009"]


def test_headings_and_notes_are_not_items():
    a = tender() + [item("", "Vorbemerkung", "Text.", None, None, kind="preliminary_note")]
    b = order() + [heading("2", "Neu", doc="B.D86")]
    result = compare.compare(a, b)
    assert result["a"]["items"] == 3 and result["a"]["notes"] == 1 and result["b"]["sections"] == 2
    assert result["matching"]["both"] == 3
    assert result["sections"]["only_b"] == [{"item_no": "2", "title": "Neu"}]


def test_a_field_that_one_file_lacks_is_not_compared():
    b = order({"01.0010": {"short": "", "long": "", "quantity": None, "unit": None}})
    result = compare.compare(tender(), b)
    for name in ("short_text", "long_text", "quantity", "unit"):
        assert result["fields"][name]["compared"] == 2 and result["fields"][name]["missing_b"] == 1
        assert result["fields"][name]["not_equal"] == 0
    assert result["fields"]["unit_price"]["compared"] == 0
    assert result["fields"]["unit_price"]["missing_both"] == 3


def test_prices_are_compared_and_never_written():
    a = [item("1.1", unit_price=123.45, total=246.9), item("1.2", "Bogen", "B.", unit_price=777.77, total=1555.54)]
    b = [item("1.1", unit_price=123.45, total=246.9, doc="B"),
         item("1.2", "Bogen", "B.", unit_price=888.88, total=1777.76, doc="B")]
    result = compare.compare(a, b, "stage")
    assert result["fields"]["unit_price"]["equal"] == 1
    assert result["fields"]["unit_price"]["not_equal_items"] == ["1.2"]
    assert result["fields"]["total"]["not_equal_items"] == ["1.2"]
    assert result["stage"]["changed"]["price"] == ["1.2"]
    written = json.dumps(result)
    for value in ("123.45", "246.9", "777.77", "1555.54", "888.88", "1777.76", "111.11"):
        assert value not in written


def test_print_text_against_long_text():
    a = [item("1.1", "Rohr DN 100 liefern", "und verlegen, Tiefe 2 m.", doc="print")]
    b = [item("1.1", "Rohr", "Rohr DN 100 liefern\nund verlegen, Tiefe 2 m.", doc="B")]
    plain = compare.compare(a, b)
    assert plain["fields"]["short_text"]["equal"] == 0 and plain["fields"]["long_text"]["differs"] == 1
    mapped = compare.compare(a, b, text_map="a_all_to_b_long")
    assert list(mapped["fields"])[0] == "text" and mapped["fields"]["text"]["equal"] == 1
    swapped = compare.compare(b, a, text_map="b_all_to_a_long")
    assert swapped["fields"]["text"]["equal"] == 1


def test_duplicate_numbers_are_named_and_paired_in_file_order():
    a = [item("1.1", "Rohr A", "A."), item("1.1", "Rohr B", "B.")]
    b = [item("1.1", "Rohr A", "A.", doc="B"), item("1.1", "Rohr B", "B.", doc="B")]
    result = compare.compare(a, b)
    assert result["matching"]["duplicate_numbers"] == {"a": ["1.1"], "b": ["1.1"]}
    assert result["matching"]["both"] == 2 and result["fields"]["short_text"]["equal"] == 2


def test_changed_values_of_a_number_that_stands_twice_come_from_the_right_pair():
    a = [item("1.1", "Rohr A", "A.", 1.0), item("1.1", "Rohr B", "B.", 2.0)]
    b = [item("1.1", "Rohr A", "A.", 1.0, doc="B"), item("1.1", "Rohr B", "B.", 5.0, "St", doc="B")]
    stage = compare.compare(a, b, "stage")["stage"]
    assert stage["changed"]["quantity"] == [{"item_no": "1.1", "a": 2.0, "b": 5.0}]
    assert stage["changed"]["unit"] == [{"item_no": "1.1", "a": "m", "b": "St"}]


def test_xml_line_is_not_used_for_matching():
    a, b = tender(), order()
    for entry in a + b:
        entry["line"] = 1
    assert compare.compare(a, b)["matching"]["by_number"] == 3


def test_leading_run_stops_at_the_first_item_that_differs():
    result = stage(order({"01.0020": {"quantity": 9.0}}))
    start = result["from_start"]
    assert start["same_from_start"] == 1 and start["stopped_at"] == "01.0020"
    assert start["first"][0] == {"a": "01.0010", "b": "1.10", "matched": "number",
                                 "title": "Rohr DN 100 liefern", "short_text": "equal",
                                 "quantity": "equal", "unit": "equal"}
    assert start["first"][1]["quantity"] == "not equal"


def test_bad_mode_and_text_map():
    with pytest.raises(ValueError):
        compare.compare([], [], "other")
    with pytest.raises(ValueError):
        compare.compare([], [], "twin", "other")
