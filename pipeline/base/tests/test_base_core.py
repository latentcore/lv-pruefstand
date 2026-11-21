"""Shared parts of the base checks: numbers, units, quotes, findings."""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402

import base_samples as s  # noqa: E402
from pipeline.base import core  # noqa: E402
from pipeline.common import quotes  # noqa: E402


@pytest.mark.parametrize("value, expected", [
    (12, "12"), (12.5, "12.5"), (0.1, "0.1"), (0, "0"), (-3.0, "-3.0"),
    ("12,5", "12.5"), ("1.234,56", "1234.56"), ("1,234.56", "1234.56"), ("1.234", "1234"),
    ("1.234.567", "1234567"), ("1234.5", "1234.5"), ("12.50", "12.50"), ("1 234,50", "1234.50"),
    ("-7,25", "-7.25"), ("+4", "4"), ("0,00", "0.00"),
])
def test_to_decimal_reads_numbers_and_printed_forms(value, expected):
    assert core.to_decimal(value) == Decimal(expected)


@pytest.mark.parametrize("value", [None, "", "  ", "n. A.", "1.2.3", "12,5,1", "abc", True, float("nan"), float("inf"), [1]])
def test_to_decimal_gives_none_for_what_is_not_a_number(value):
    assert core.to_decimal(value) is None


def test_float_prices_are_exact_decimals():
    assert core.to_decimal(0.1) + core.to_decimal(0.2) == Decimal("0.3")


@pytest.mark.parametrize("unit, expected", [
    ("St", "st"), ("Stk", "st"), ("Stck.", "st"), ("St.", "st"), ("m²", "m2"), ("m2", "m2"), ("qm", "m2"),
    ("m³", "m3"), ("cbm", "m3"), ("lfm", "m"), ("PSCH", "psch"), ("pau", "psch"), ("Psch.", "psch"),
    ("Std", "h"), ("h", "h"), ("TO", "t"), ("StWo", "st*wo"), ("m2Wo", "m2*wo"), ("m2d", "m2*d"),
])
def test_canonical_unit_knows_spelling_variants(unit, expected):
    assert core.canonical_unit(unit) == expected


@pytest.mark.parametrize("unit", [None, "", "  ", "xyz", "Gurke", 5])
def test_canonical_unit_is_none_for_missing_or_unknown(unit):
    assert core.canonical_unit(unit) is None


def test_quote_of_is_the_short_text_or_the_start_of_the_long_text():
    assert core.quote_of(s.item("1.10", "Estrich schwimmend", "Zementestrich CT-C25-F4, 65 mm")) == "Estrich schwimmend"
    long_text = "Wort " * 60
    quote = core.quote_of(s.item("1.20", "", long_text))
    assert len(quote) <= core.QUOTE_MAX and long_text.startswith(quote)
    assert core.quote_of(s.item("1.30", "", "")) is None
    assert core.quote_of(s.item("1.40", None, None)) is None


def test_snippet_is_a_part_of_the_text_around_the_phrase():
    text = "aaa " * 30 + "nach Erfordernis" + " bbb" * 30
    start = text.index("nach")
    part = core.snippet(text, start, start + len("nach Erfordernis"))
    assert "nach Erfordernis" in part and part in text and len(part) <= 2 * core.SNIPPET_CONTEXT + 20


def test_split_docs_keeps_file_order_and_ignores_what_is_not_a_record():
    items = [s.item("1.10", doc="B"), "noise", s.item("1.10", doc="A"), s.item("1.20", doc="B"), None]
    docs = core.split_docs(items)
    assert [d.name for d in docs] == ["B", "A"]
    assert [r["item_no"] for r in docs[0].records] == ["1.10", "1.20"]


def test_a_record_without_text_is_cited_through_its_neighbour_and_the_text_says_so():
    items = [s.item("1.10", "Erste Position mit Text"), s.item("1.20", "", "")]
    doc = core.split_docs(items)[0]
    finding = core.make_finding("B6", "quantity_zero", "high", [doc.source(items[1])],
                                "Die Menge der Position 1.20 ist null.", "Welche Menge gilt?", record=items[1])
    assert finding["sources"] == [{"doc": s.DOC, "item_no": "1.10", "page": 1, "quote": "Erste Position mit Text"}]
    assert finding["explanation_de"].endswith(core.NO_TEXT_NOTE)
    assert quotes.finding_verified(finding, items)


def test_no_finding_without_a_quotable_source():
    items = [s.item("1.10", "", "")]
    doc = core.split_docs(items)[0]
    assert doc.source(items[0]) is None
    assert core.make_finding("B6", "quantity_zero", "high", [doc.source(items[0])], "x", "y?") is None
    outcome = core.collect([None])
    assert outcome.findings == [] and outcome.notes == {"no_quote": 1}


def test_findings_with_the_same_id_are_merged_and_none_is_lost():
    items = [s.item("1.10", "Position mit Text"), s.item("1.20", "", "", quantity=0.0),
             s.item("1.30", "", "", quantity=0.0, kind="optional")]
    doc = core.split_docs(items)[0]
    made = [core.make_finding("B6", "quantity_zero", level, [doc.source(r)],
                              "Die Menge der Position %s ist null." % r["item_no"],
                              "Welche Menge gilt für die Position %s?" % r["item_no"], record=r)
            for r, level in ((items[2], "medium"), (items[1], "high"))]
    outcome = core.collect(made)
    assert len(outcome.findings) == 1 and outcome.notes == {"merged": 1}
    merged = outcome.findings[0]
    assert merged["severity"] == "high"
    assert merged["explanation_de"] == ("Die Menge der Position 1.30 ist null. Die Menge der Position 1.20 ist null."
                                        + core.NO_TEXT_NOTE)
    assert merged["question_de"].count("?") == 2
    s.valid(outcome.findings, items)


def test_exposure_is_quantity_and_unit_never_a_price():
    items = [s.item("1.10", quantity=12.5, unit="m2", unit_price=3.33, total=41.63)]
    doc = core.split_docs(items)[0]
    finding = core.make_finding("B6", "x", "info", [doc.source(items[0])], "a", "b?", record=items[0])
    assert finding["exposure"] == {"quantity": 12.5, "unit": "m2"}
    s.no_amount([finding], "3.33", "3,33", "41.63", "41,63")


def test_an_optional_item_lowers_the_severity_by_one_level():
    items = [s.item("1.10", kind="optional"), s.item("1.20", kind="alternative"), s.item("1.30")]
    doc = core.split_docs(items)[0]
    levels = [core.make_finding("B6", "x", "high", [doc.source(r)], "a", "b?", record=r)["severity"] for r in items]
    assert levels == ["medium", "medium", "high"]


def test_outliers_need_three_siblings_of_the_same_section_and_unit():
    def quantities(values, **extra):
        return [s.item("1.%d" % (10 * (i + 1)), quantity=v, **extra) for i, v in enumerate(values)]

    def hits(items):
        return [(r["item_no"], side) for r, side in core.outliers(core.split_docs(items)[0],
                                                                 lambda r: core.number(r, "quantity"))]

    assert hits(quantities([10, 12, 11, 150])) == [("1.40", "high")]
    assert hits(quantities([10, 12, 11, 109])) == []
    assert hits(quantities([10, 10, 10, 100])) == [("1.40", "high")]      # exactly 10 times
    assert hits(quantities([100, 120, 110, 11])) == [("1.40", "low")]
    assert hits(quantities([100, 120, 110, 12])) == []
    assert hits(quantities([10, 12, 150])) == []                          # two siblings only
    other_unit = quantities([10, 12, 11]) + [s.item("1.40", quantity=150, unit="m")]
    assert hits(other_unit) == []
    other_section = quantities([10, 12, 11]) + [s.item("2.10", quantity=150)]
    assert hits(other_section) == []
    assert hits(quantities([10, 12, 11, 150], unit="psch")) == []         # lump sums are not compared
