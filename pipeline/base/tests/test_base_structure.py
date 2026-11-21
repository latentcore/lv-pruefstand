"""B3, B4, B5, B6, B10: numbers, repeats, units, quantities, item kinds."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402

import base_samples as s  # noqa: E402
from pipeline.base import core, structure  # noqa: E402


def _row(numbers, **extra):
    return [s.item(number, "Leistung %s ausführen laut Plan" % number, **extra) for number in numbers]


# --- B3 ---------------------------------------------------------------------
def test_b3_fires_on_a_number_given_twice():
    items = _row(["1.10", "1.20", "1.20", "1.30"])
    findings = s.found(structure.b3, items)
    assert s.types(findings) == ["duplicate_number"]
    assert [x["item_no"] for x in findings[0]["sources"]] == ["1.20"]  # the two records have the same text
    assert "1.20" in findings[0]["explanation_de"] and "2-mal" in findings[0]["explanation_de"]
    assert findings[0]["severity"] == "medium"


def test_b3_duplicate_number_cites_both_texts_when_they_differ():
    items = [s.item("1.10", "Wand mauern in Kalksandstein"), s.item("1.10", "Decke betonieren in Ortbeton")]
    findings = s.found(structure.b3, items)
    assert [x["quote"] for x in findings[0]["sources"]] == ["Wand mauern in Kalksandstein",
                                                           "Decke betonieren in Ortbeton"]


def test_b3_fires_when_the_numbers_do_not_rise():
    findings = s.found(structure.b3, _row(["1.10", "1.30", "1.20", "1.40"]))
    assert s.types(findings) == ["number_out_of_order"]
    assert [x["item_no"] for x in findings[0]["sources"]] == ["1.20", "1.30"]
    assert findings[0]["severity"] == "info"


def test_b3_fires_on_a_gap_in_the_row():
    findings = s.found(structure.b3, _row(["1.10", "1.20", "1.30", "1.40", "1.60", "1.70", "1.80"]))
    assert s.types(findings) == ["number_gap"]
    assert [x["item_no"] for x in findings[0]["sources"]] == ["1.40", "1.60"]
    assert "Schritt 10" in findings[0]["explanation_de"]


def test_b3_does_not_fire_on_a_steady_row():
    assert s.found(structure.b3, _row(["1.10", "1.20", "1.30", "1.40", "1.50", "1.60", "1.70"])) == []
    assert s.found(structure.b3, _row(["1.1", "1.2", "1.3", "2.1", "2.2", "2.3", "3.1", "3.2"])) == []
    assert s.found(structure.b3, _row(["01.01.0001", "01.01.0002", "01.02.0001", "02.01.0001"])) == []


def test_b3_makes_no_gap_claim_when_the_document_has_no_clear_step():
    assert s.found(structure.b3, _row(["1.10", "1.30"])) == []                       # too few steps
    assert s.found(structure.b3, _row(["1.1", "1.3", "1.4", "1.9", "1.15", "1.16", "1.30"])) == []  # mixed steps


def test_b3_is_not_applicable_without_item_numbers():
    assert not s.run(structure.b3, [s.item("", "Wand mauern in Kalksandstein"), s.heading("1")]).applicable


def test_b3_leaves_numbers_with_letters_out_of_the_order_check_but_sees_them_twice():
    assert s.found(structure.b3, _row(["1.10", "1.10a", "1.20", "N1", "1.30"])) == []
    assert s.types(s.found(structure.b3, _row(["1.10", "N1", "N1"]))) == ["duplicate_number"]


def test_b3_looks_at_positions_only():
    items = [s.heading("2"), s.heading("1"), s.note("1", "Hinweise zur Ausführung"), s.item("1.10"), s.heading("1")]
    assert s.found(structure.b3, items) == []


@pytest.mark.parametrize("item_no, key", [("1.2.30", (1, 2, 30)), ("01.02.0003", (1, 2, 3)), ("7", (7,)),
                                          (".9", (-1, 9)), ("2.6..5", (2, 6, -1, 5)), ("1.10a", None), ("N1", None)])
def test_number_key(item_no, key):
    assert structure.number_key(item_no) == key


# --- B4 ---------------------------------------------------------------------
def test_b4_fires_on_the_same_text_and_unit():
    items = [s.item("1.10", "Schutzlage, Vlies, 0,3 mm", unit="m2"),
             s.item("2.10", "schutzlage,  Vlies, 0,3 mm", unit="m²"),
             s.item("3.10", "Schutzlage, Vlies, 0,5 mm", unit="m2")]
    findings = s.found(structure.b4, items)
    assert s.types(findings) == ["repeated_item"]
    assert [x["item_no"] for x in findings[0]["sources"]] == ["1.10", "2.10"]
    assert "1.10, 2.10" in findings[0]["explanation_de"]


def test_b4_does_not_fire_on_another_unit_or_another_long_text():
    items = [s.item("1.10", "Abdeckung mit PE-Folie", unit="m2"), s.item("2.10", "Abdeckung mit PE-Folie", unit="m"),
             s.item("3.10", "Abdeckung mit PE-Folie", "Dicke 0,5 mm", unit="m2")]
    assert s.found(structure.b4, items) == []


def test_b4_is_not_applicable_without_text_and_does_not_compare_rows_of_dots():
    assert not s.run(structure.b4, [s.item("1.10", "", ""), s.item("1.20", None, None)]).applicable
    items = [s.item("1.10", "", "........"), s.item("1.20", "", "........"), s.item("1.30")]
    assert s.found(structure.b4, items) == []


def test_b4_names_three_repeats_in_one_finding():
    items = [s.item(number, "Gerüst umsetzen je Abschnitt") for number in ("1.10", "2.10", "3.10")]
    findings = s.found(structure.b4, items)
    assert len(findings) == 1 and len(findings[0]["sources"]) == 3


# --- B5 ---------------------------------------------------------------------
def test_b5_fires_on_a_missing_unit():
    items = [s.item("1.10"), s.item("1.20", "Sockel abdichten gegen Feuchte", unit=None),
             s.item("1.30", "Fuge schließen mit Dichtstoff", unit="  ")]
    findings = s.found(structure.b5, items)
    assert s.types(findings) == ["unit_missing", "unit_missing"]
    assert [f["sources"][0]["item_no"] for f in findings] == ["1.20", "1.30"]
    assert findings[0]["severity"] == "high" and findings[0]["exposure"] == {"quantity": 10.0, "unit": None}


def test_b5_fires_on_an_unknown_unit_and_quotes_it_in_the_text():
    findings = s.found(structure.b5, [s.item("1.10"), s.item("1.20", "Sockel abdichten gegen Feuchte", unit="Gurke")])
    assert s.types(findings) == ["unit_unknown"]
    assert "«Gurke»" in findings[0]["explanation_de"] and findings[0]["severity"] == "info"


def test_b5_fires_when_the_same_short_text_has_different_units():
    items = [s.item("1.10", "Gerüst vorhalten", unit="StWo"), s.item("2.10", "Gerüst vorhalten", unit="Std"),
             s.item("3.10", "Gerüst vorhalten", "über die Grundstandzeit hinaus", unit="StWo")]
    findings = s.found(structure.b5, items)
    assert s.types(findings) == ["unit_differs"]
    assert [x["item_no"] for x in findings[0]["sources"]] == ["1.10", "2.10", "3.10"]
    assert "(StWo, Std)" in findings[0]["explanation_de"]


def test_b5_does_not_fire_on_known_units_and_their_spellings():
    items = [s.item("1.10", "Fliesen verlegen im Dünnbett", unit="m2"),
             s.item("2.10", "Fliesen verlegen im Dünnbett", unit="m²"),
             s.item("3.10", "Fliesen verlegen im Dünnbett", unit="qm"),
             s.item("4.10", "Tür einbauen", unit="Stk"), s.item("5.10", "Tür einbauen", unit="St."),
             s.item("6.10", "Baustelle einrichten", kind="lump_sum", unit="PSCH")]
    assert s.found(structure.b5, items) == []


def test_b5_is_not_applicable_when_the_document_has_no_units():
    assert not s.run(structure.b5, [s.item("1.10", unit=None), s.item("1.20", unit="")]).applicable


def test_b5_a_lump_sum_item_needs_no_unit():
    items = [s.item("1.10"), s.item("1.20", "Baustelle einrichten", kind="lump_sum", unit=None)]
    assert s.found(structure.b5, items) == []


# --- B6 ---------------------------------------------------------------------
def test_b6_fires_on_a_missing_zero_or_negative_quantity():
    items = [s.item("1.10"), s.item("1.20", "Sockel abdichten gegen Feuchte", quantity=None),
             s.item("1.30", "Fuge schließen mit Dichtstoff", quantity=0.0),
             s.item("1.40", "Putz ausbessern in Teilflächen", quantity=-2.0)]
    findings = s.found(structure.b6, items)
    assert s.types(findings) == ["quantity_missing", "quantity_negative", "quantity_zero"]
    assert all(f["severity"] == "high" for f in findings)
    assert [f["sources"][0]["item_no"] for f in findings] == ["1.20", "1.30", "1.40"]


def test_b6_does_not_fire_on_usual_quantities():
    items = [s.item("1.10", quantity=10.0), s.item("1.20", quantity=0.5), s.item("1.30", quantity="1.200,5")]
    assert s.found(structure.b6, items) == []


def test_b6_is_not_applicable_when_the_document_has_no_quantities():
    assert not s.run(structure.b6, [s.item("1.10", quantity=None), s.item("1.20", quantity=None)]).applicable


def test_b6_a_lump_sum_without_quantity_counts_once():
    items = [s.item("1.10"), s.item("1.20", "Baustelle einrichten", kind="lump_sum", quantity=None, unit="psch"),
             s.item("1.30", "Baustelle räumen", quantity=None, unit="pauschal")]
    assert s.found(structure.b6, items) == []


def test_b6_zero_quantity_of_an_optional_item_is_one_level_lower():
    items = [s.item("1.10"), s.item("1.20", "Mehraushub auf Anordnung", kind="optional", quantity=0.0)]
    findings = s.found(structure.b6, items)
    assert s.types(findings) == ["quantity_zero"] and findings[0]["severity"] == "medium"


def test_b6_fires_on_a_quantity_ten_times_off_its_siblings():
    def items(last):
        return [s.item("1.%d" % (10 * (i + 1)), "Wand Typ %d mauern" % (i + 1), quantity=q)
                for i, q in enumerate([10.0, 12.0, 11.0, last])]

    high = s.found(structure.b6, items(150.0))
    assert s.types(high) == ["quantity_outlier"] and high[0]["sources"][0]["item_no"] == "1.40"
    assert high[0]["severity"] == "info" and "Faktor 10 über" in high[0]["explanation_de"]
    assert "Faktor 10 unter" in s.found(structure.b6, items(1.0))[0]["explanation_de"]
    assert s.found(structure.b6, items(109.0)) == []
    assert len(s.found(structure.b6, items("1.100,00"))) == 1     # thousands separator
    assert len(s.found(structure.b6, items("1,1"))) == 1          # decimal comma; exactly a tenth of 11
    assert s.found(structure.b6, items("1,2")) == []


def test_b6_ten_times_off_needs_three_siblings():
    items = [s.item("1.10", quantity=10.0), s.item("1.20", quantity=12.0), s.item("1.30", quantity=500.0)]
    assert s.found(structure.b6, items) == []


# --- B10 --------------------------------------------------------------------
def test_b10_flags_optional_and_alternative_items():
    items = [s.item("1.10"), s.item("1.20", "Mehraushub auf Anordnung", kind="optional"),
             s.item("1.30", "Pflaster statt Asphalt", kind="alternative")]
    findings = s.found(structure.b10, items)
    assert s.types(findings) == ["alternative_item", "optional_item"]
    assert all(f["severity"] == "info" for f in findings)
    by_type = {f["type"]: f for f in findings}
    assert "Bedarfsposition" in by_type["optional_item"]["explanation_de"]
    assert "Wahlposition" in by_type["alternative_item"]["explanation_de"]
    assert by_type["optional_item"]["sources"][0]["item_no"] == "1.20"


def test_b10_does_not_flag_base_items():
    items = [s.item("1.10"), s.item("1.20", "Baustelle einrichten", kind="lump_sum", unit="psch"),
             s.item("1.30", "Aushub wie Bedarfsposition 1.20, jedoch von Hand")]
    assert s.found(structure.b10, items) == []


def test_b10_is_not_applicable_without_positions():
    assert not s.run(structure.b10, [s.heading("1"), s.note("", "Hinweise zur Ausführung")]).applicable


@pytest.mark.parametrize("text, word", [
    ("Bedarfsposition\nMehraushub von Hand", "Bedarfsposition"),
    ("*** Eventualposition\nMehraushub von Hand", "Bedarfsposition"),
    ("Wahlposition zu 1.10\nPflaster statt Asphalt", "Wahlposition"),
    ("Alternativpos. zu 1.10\nPflaster statt Asphalt", "Wahlposition"),
])
def test_b10_fires_when_the_text_names_a_flag_the_kind_does_not_carry(text, word):
    items = [s.item("1.10"), s.item("1.20", "Aushub von Hand", text, kind="normal")]
    findings = s.found(structure.b10, items)
    assert s.types(findings) == ["flag_missing"]
    assert word in findings[0]["explanation_de"] and findings[0]["severity"] == "medium"
    assert "pos" in findings[0]["sources"][0]["quote"].lower()


def test_b10_missing_kind_is_a_base_item():
    record = s.item("1.10")
    del record["kind"]
    assert s.found(structure.b10, [record]) == []
    assert core.split_docs([record])[0].positions == [record]
