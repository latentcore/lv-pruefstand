"""B1, B2, B7, B9: the checks that use prices. Prices in these tests are invented."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402

import base_samples as s  # noqa: E402
from pipeline.base import prices  # noqa: E402


# --- B1 ---------------------------------------------------------------------
def test_b1_fires_when_the_product_is_not_the_total_and_names_no_amount():
    items = [s.item("1.10", quantity=10.0, unit_price=3.33, total=44.44),
             s.item("1.20", "Putz innen", quantity=2.0, unit_price=3.33, total=6.66)]
    findings = s.found(prices.b1, items)
    assert s.types(findings) == ["arithmetic_error"]
    finding = findings[0]
    assert finding["check"] == "B1" and finding["severity"] == "high"
    assert finding["sources"] == [{"doc": s.DOC, "item_no": "1.10", "page": 1, "quote": s.TEXT}]
    assert "Position 1.10" in finding["explanation_de"] and "nicht" in finding["explanation_de"]
    assert finding["exposure"] == {"quantity": 10.0, "unit": "m2"}
    s.no_amount(findings, "3.33", "3,33", "44.44", "44,44", "33.3", "33,3")


def test_b1_does_not_fire_when_the_product_is_the_total():
    items = [s.item("1.10", quantity=10.0, unit_price=2.5, total=25.0),
             s.item("1.20", quantity=0.1, unit_price=0.2, total=0.02)]
    assert s.found(prices.b1, items) == []


@pytest.mark.parametrize("total, fires", [(3.35, False), (3.34, False), (3.345, False), (3.36, True), (3.33, True)])
def test_b1_rounding_at_the_cent(total, fires):
    # 3 x 1.115 = 3.345: both cent roundings pass, one cent further does not
    findings = s.found(prices.b1, [s.item("1.10", quantity=3.0, unit_price=1.115, total=total)])
    assert bool(findings) is fires


@pytest.mark.parametrize("total, fires", [("2.469,00", False), ("2,469.00", False), ("2.468,00", True)])
def test_b1_reads_numbers_with_a_thousands_separator(total, fires):
    findings = s.found(prices.b1, [s.item("1.10", quantity="1.234,5", unit_price="2,00", total=total)])
    assert bool(findings) is fires


def test_b1_is_not_applicable_without_prices():
    assert not s.run(prices.b1, [s.item("1.10"), s.item("1.20")]).applicable
    assert not s.run(prices.b1, [s.item("1.10", unit_price=2.0)]).applicable  # no total
    assert not s.run(prices.b1, [s.item("1.10", total=20.0)]).applicable      # no unit price


def test_b1_is_not_applicable_when_no_priced_item_has_a_quantity():
    items = [s.item("1.10", quantity=None, unit_price=2.0, total=20.0),
             s.item("1.20", quantity=None, unit_price=3.0, total=30.0)]
    assert not s.run(prices.b1, items).applicable


def test_b1_skips_and_counts_a_priced_item_without_quantity():
    items = [s.item("1.10", quantity=None, unit_price=2.0, total=20.0),
             s.item("1.20", quantity=10.0, unit_price=3.0, total=30.0)]
    outcome = s.run(prices.b1, items)
    assert outcome.applicable and outcome.findings == [] and outcome.notes == {"priced_without_quantity": 1}


def test_b1_zero_quantity():
    assert s.found(prices.b1, [s.item("1.10", quantity=0.0, unit_price=5.0, total=0.0)]) == []
    assert len(s.found(prices.b1, [s.item("1.10", quantity=0.0, unit_price=5.0, total=5.0)])) == 1


def test_b1_a_lump_sum_without_quantity_counts_once():
    ok = [s.item("1.10", kind="lump_sum", quantity=None, unit="psch", unit_price=500.0, total=500.0)]
    bad = [s.item("1.10", kind="normal", quantity=None, unit="Psch", unit_price=500.0, total=501.0)]
    assert s.found(prices.b1, ok) == []
    assert len(s.found(prices.b1, bad)) == 1


def test_b1_an_optional_item_with_a_unit_price_only_is_in_order():
    items = [s.item("1.10", kind="optional", quantity=10.0, unit_price=5.0, total=0.0),
             s.item("1.20", kind="alternative", quantity=10.0, unit_price=5.0, total=0.0),
             s.item("1.30", kind="optional", quantity=10.0, unit_price=5.0, total=49.0)]
    findings = s.found(prices.b1, items)
    assert [f["sources"][0]["item_no"] for f in findings] == ["1.30"]
    assert findings[0]["severity"] == "medium"  # an optional item is not part of the sum


# --- B2 ---------------------------------------------------------------------
def _section(total_1, total_all=None):
    return [s.heading("", "Leistungsverzeichnis Rohbau", total=total_all),
            s.heading("1", "Erdarbeiten", total=total_1),
            s.item("1.10", "Boden lösen und laden", unit_price=10.0, total=100.0),
            s.item("1.20", "Boden einbauen und verdichten", unit_price=20.0, total=200.0),
            s.heading("2", "Betonarbeiten"),
            s.item("2.10", "Sauberkeitsschicht aus Beton", unit_price=5.0, total=50.0)]


def test_b2_fires_on_a_wrong_section_sum_and_names_no_amount():
    findings = s.found(prices.b2, _section(301.0))
    assert s.types(findings) == ["sum_mismatch"]
    assert findings[0]["sources"] == [{"doc": s.DOC, "item_no": "1", "page": 1, "quote": "Erdarbeiten"}]
    assert "im Abschnitt 1" in findings[0]["explanation_de"]
    s.no_amount(findings, "301", "300", "100", "200")


def test_b2_does_not_fire_on_right_sums():
    assert s.found(prices.b2, _section(300.0, 350.0)) == []


def test_b2_fires_on_a_wrong_grand_total():
    findings = s.found(prices.b2, _section(300.0, 349.0))
    assert len(findings) == 1 and findings[0]["sources"][0]["item_no"] == ""
    assert "Gesamtsumme" in findings[0]["explanation_de"]
    s.no_amount(findings, "349", "350")


def test_b2_is_not_applicable_without_a_stated_sum():
    assert not s.run(prices.b2, _section(None)).applicable
    assert not s.run(prices.b2, [s.item("1.10"), s.item("1.20")]).applicable


def test_b2_sums_floats_exactly_and_to_the_cent():
    def items(total):
        return [s.heading("1", "Erdarbeiten", total=total),
                s.item("1.10", "Boden lösen und laden", total=0.1),
                s.item("1.20", "Boden einbauen und verdichten", total=0.2)]

    assert s.found(prices.b2, items(0.3)) == []
    assert s.found(prices.b2, items(0.305)) == []       # half a cent
    assert len(s.found(prices.b2, items(0.31))) == 1    # one cent


def test_b2_reads_numbers_with_a_thousands_separator():
    def items(total):
        return [s.heading("1", "Erdarbeiten", total=total),
                s.item("1.10", "Boden lösen und laden", total="12.000,00"),
                s.item("1.20", "Boden einbauen und verdichten", total="345,67")]

    assert s.found(prices.b2, items("12.345,67")) == []
    assert s.found(prices.b2, items("12,345.67")) == []
    assert len(s.found(prices.b2, items("12.345,76"))) == 1


def test_b2_a_sum_may_hold_the_optional_items_but_never_the_alternative_ones():
    def items(total):
        return [s.heading("1", "Erdarbeiten", total=total),
                s.item("1.10", "Boden lösen und laden", total=100.0),
                s.item("1.20", "Boden abfahren auf Anordnung", kind="optional", total=40.0),
                s.item("1.30", "Boden lösen von Hand", kind="alternative", total=7.0)]

    assert s.found(prices.b2, items(100.0)) == []
    assert s.found(prices.b2, items(140.0)) == []
    assert len(s.found(prices.b2, items(147.0))) == 1
    assert len(s.found(prices.b2, items(107.0))) == 1


def test_b2_a_section_sum_holds_the_sections_below_it():
    items = [s.heading("1", "Rohbau", total=300.0),
             s.heading("1.1", "Erdarbeiten", total=100.0),
             s.item("1.1.10", "Boden lösen und laden", total=100.0),
             s.heading("1.2", "Betonarbeiten", total=200.0),
             s.item("1.2.10", "Sauberkeitsschicht aus Beton", total=200.0),
             s.heading("2", "Ausbau", total=0.0)]
    assert s.found(prices.b2, items) == []
    items[0]["total"] = 100.0
    assert [f["sources"][0]["item_no"] for f in s.found(prices.b2, items)] == ["1"]


def test_b2_zero_sum_of_an_empty_section():
    assert s.found(prices.b2, [s.heading("1", "Erdarbeiten", total=0.0), s.item("2.10", total=5.0)]) == []


def test_b2_does_not_judge_a_sum_over_an_item_without_total():
    items = [s.heading("1", "Erdarbeiten", total=300.0),
             s.item("1.10", "Boden lösen und laden", total=100.0),
             s.item("1.20", "Boden einbauen und verdichten", total=None),
             s.item("1.30", "Boden abfahren auf Anordnung", kind="optional", total=None),
             s.heading("2", "Betonarbeiten", total=51.0),
             s.item("2.10", "Sauberkeitsschicht aus Beton", total=50.0)]
    outcome = s.run(prices.b2, items)
    assert [f["sources"][0]["item_no"] for f in outcome.findings] == ["2"]
    assert outcome.notes == {"sum_not_checkable": 1}
    items[2]["total"] = 200.0   # an optional item without total does not block the check
    assert [f["sources"][0]["item_no"] for f in s.found(prices.b2, items)] == ["2"]


# --- B7 ---------------------------------------------------------------------
def _priced(values, unit="m2"):
    return [s.item("1.%d" % (10 * (i + 1)), "Leistung Nummer %d herstellen" % (i + 1), unit=unit,
                   unit_price=value, total=None) for i, value in enumerate(values)]


def test_b7_asks_about_a_unit_price_ten_times_above_its_siblings():
    findings = s.found(prices.b7, _priced([10.0, 12.0, 11.0, 150.0]))
    assert s.types(findings) == ["unit_price_outlier"]
    finding = findings[0]
    assert finding["severity"] == "info" and finding["sources"][0]["item_no"] == "1.40"
    assert "über" in finding["explanation_de"] and finding["question_de"].endswith("?")
    assert "falsch" not in finding["explanation_de"] + finding["question_de"]
    s.no_amount(findings, "150", "11.0", "12.0")


def test_b7_asks_about_a_unit_price_ten_times_below_its_siblings():
    findings = s.found(prices.b7, _priced([100.0, 120.0, 110.0, 11.0]))
    assert len(findings) == 1 and "unter" in findings[0]["explanation_de"]


def test_b7_does_not_fire_on_usual_prices_or_with_too_few_siblings():
    assert s.found(prices.b7, _priced([10.0, 12.0, 11.0, 109.0])) == []
    assert s.found(prices.b7, _priced([10.0, 12.0, 150.0])) == []


def test_b7_is_not_applicable_without_unit_prices():
    assert not s.run(prices.b7, [s.item("1.10"), s.item("1.20", total=5.0)]).applicable


def test_b7_asks_about_a_zero_or_negative_unit_price():
    findings = s.found(prices.b7, _priced([0.0, 12.0, -1.0]))
    assert s.types(findings) == ["unit_price_not_positive"] * 2
    assert [f["sources"][0]["item_no"] for f in findings] == ["1.10", "1.30"]
    assert all(f["severity"] == "info" for f in findings)


def test_b7_reads_numbers_with_a_thousands_separator():
    findings = s.found(prices.b7, _priced(["100,00", "120,00", "110,00", "1.100,00"]))
    assert [f["sources"][0]["item_no"] for f in findings] == ["1.40"]
    s.no_amount(findings, "1.100", "1100")
    assert s.found(prices.b7, _priced(["100,00", "120,00", "110,00", "1.099,99"])) == []


def test_b7_compares_only_the_same_unit():
    items = _priced([10.0, 12.0, 11.0]) + [s.item("1.40", "Kran vorhalten", unit="Wo", unit_price=900.0)]
    assert s.found(prices.b7, items) == []


# --- B9 ---------------------------------------------------------------------
def _lump(count, others, **extra):
    items = [s.item("1.%d" % (10 * (i + 1)), "Baustelle einrichten Teil %d" % (i + 1), kind="lump_sum",
                    quantity=1.0, unit="psch", **extra) for i in range(count)]
    return items + [s.item("2.%d" % (10 * (i + 1)), "Wand mauern Typ %d" % (i + 1)) for i in range(others)]


def test_b9_fires_at_the_threshold_by_count():
    findings = s.found(prices.b9, _lump(1, 4))
    assert s.types(findings) == ["lump_sum_share"]
    assert "1 von 5 Positionen" in findings[0]["explanation_de"] and "nach Anzahl" in findings[0]["explanation_de"]
    assert findings[0]["sources"][0]["item_no"] == "1.10" and findings[0]["severity"] == "medium"


def test_b9_does_not_fire_below_the_threshold_or_without_lump_sums():
    outcome = s.run(prices.b9, _lump(1, 5))
    assert outcome.applicable and outcome.findings == [] and outcome.notes == {"no_totals": 1}
    assert s.found(prices.b9, _lump(0, 5)) == []


def test_b9_is_not_applicable_without_positions():
    assert not s.run(prices.b9, [s.heading("1"), s.note("", "Allgemeine Hinweise zur Ausführung")]).applicable


def test_b9_counts_the_kind_and_the_unit_spellings():
    items = [s.item("1.10", "Baustelle einrichten", kind="lump_sum", quantity=None, unit=None),
             s.item("1.20", "Baustelle räumen", kind="normal", unit="Pauschal"),
             s.item("1.30", "Wand mauern"), s.item("1.40", "Decke betonieren")]
    findings = s.found(prices.b9, items)
    assert "2 von 4 Positionen" in findings[0]["explanation_de"]
    assert [x["item_no"] for x in findings[0]["sources"]] == ["1.10", "1.20"]


def test_b9_fires_by_value_and_names_no_amount():
    items = _lump(1, 9, unit_price=5000.0, total=5000.0)
    for record in items[1:]:
        record["unit_price"], record["total"] = 55.5, 555.0
    findings = s.found(prices.b9, items)  # 1 of 10 by count, half the sum by value
    assert len(findings) == 1
    assert "Summe der Gesamtbeträge" in findings[0]["explanation_de"]
    assert "nach Anzahl" not in findings[0]["explanation_de"]
    s.no_amount(findings, "5000", "555", "55.5", "9995", "50 %")


def test_b9_value_share_leaves_optional_items_out_and_reads_thousands_separators():
    items = _lump(1, 9, unit_price="1.000,00", total="1.000,00")
    for record in items[1:]:
        record["total"] = "1.000,00"
    assert s.found(prices.b9, items) == []            # a tenth by count and by value
    items[0]["total"] = "2.250,00"
    assert len(s.found(prices.b9, items)) == 1        # a fifth of the sum
    items[0]["kind"], items[0]["unit"] = "optional", "psch"
    findings = s.found(prices.b9, items)              # optional: not in the sum, still a tenth by count
    assert findings == []


def test_b9_takes_no_share_by_value_when_a_base_item_has_no_total():
    items = _lump(1, 9, unit_price=5000.0, total=5000.0)   # the other nine have no total
    outcome = s.run(prices.b9, items)
    assert outcome.findings == [] and outcome.notes == {"no_totals": 1}
    for record in items[1:]:
        record["total"] = 100.0
    assert len(s.found(prices.b9, items)) == 1


def test_b9_quotes_at_most_five_lump_sum_items():
    findings = s.found(prices.b9, _lump(7, 3))
    assert len(findings[0]["sources"]) == 5
