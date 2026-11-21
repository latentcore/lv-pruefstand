"""GAEB 90 reader on hand-written lines. Every text, number and price here is invented."""
import hashlib
import json
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402

from gaeb90_lines import build, end, header, item, prices  # noqa: E402
from pipeline.common import contract  # noqa: E402
from pipeline.lv import gaeb90, model  # noqa: E402

DETAILED = [
    header("83L", "P-TEST-1"),
    "01Test trade                              01.01.26",
    "02Some project",
    "08EUR   Euro",
    "110100",
    "12First section",
    "20",
    "26   Note title",
    "26   Note body line",
    "210100   1 ",
    "25Short text one",
    "26   Long text line one",
    "26",
    "26   Long text line two",
    "310100",
    "110200",
    "12Second section",
    item("0200   1 ", "00000002500", "m"),
    "25Pipe",
    "25with fitting",
    "26   Long text",
    item("0200   2A", "00000001000", "psch"),
    "25Site setup",
    "310200",
    end(3),
]
DETAILED[9] = item("0100   1 ", "00000012000", "St")


def read(records, name="list.D83", **kwargs):
    project, items, entry = gaeb90.parse_bytes(build(records, **kwargs), name)
    contract.check("items", items)
    contract.check("manifest", [entry])
    return project, items, entry


def positions(items):
    return [i for i in items if model.is_position(i)]


def test_detailed_layout_gives_headings_note_and_items():
    project, items, entry = read(DETAILED)
    assert project == "P-TEST-1"
    assert [(i["kind"], i["item_no"], i["section"]) for i in items] == [
        ("heading", "01.00", "01"),
        ("preliminary_note", "01.00", "01"),
        ("normal", "01.00.1", "01.00"),
        ("heading", "02.00", "02"),
        ("normal", "02.00.1", "02.00"),
        ("lump_sum", "02.00.2.A", "02.00"),
    ]
    assert [i["short_text"] for i in items] == [
        "First section", "Note title", "Short text one", "Second section",
        "Pipe with fitting", "Site setup"]
    assert items[1]["long_text"] == "Note body line"
    assert items[2]["long_text"] == "Long text line one\n\nLong text line two"
    assert (items[2]["quantity"], items[2]["unit"]) == (12.0, "St")
    assert (items[4]["quantity"], items[4]["unit"]) == (2.5, "m")
    assert [i["line"] for i in items] == [5, 7, 10, 16, 18, 22]
    for i in items:
        assert i["doc"] == "list.D83" and i["trade"] == "Test trade"
        assert i["format"] == "gaeb90" and i["stage"] == "83" and i["page"] is None
        assert i["unit_price"] is None and i["total"] is None
        assert i["pre_trade_text"] is None and i["post_trade_text"] is None


def test_manifest_entry_of_the_detailed_layout():
    raw = build(DETAILED)
    _, _, entry = gaeb90.parse_bytes(raw, "list.D83")
    assert entry["file"] == "list.D83" and entry["doc"] == "list.D83"
    assert entry["sha256"] == hashlib.sha256(raw).hexdigest()
    assert entry["format"] == "gaeb90" and entry["stage"] == "83" and entry["pages"] is None
    assert (entry["items"], entry["headings"], entry["preliminary_notes"]) == (3, 2, 1)
    assert entry["unparsed_lines"] == 0 and entry["warnings"] == []
    assert entry["lines"] == len(DETAILED) and entry["declared_items"] == 3
    assert entry["skipped_records"] == {"02": 1, "08": 1, "31": 2}
    assert entry["priced_items"] == 0 and entry["sum_check"] == "not_in_file"


@pytest.mark.parametrize("name,stage", [("a.D83", "83"), ("a.d84", "84"), ("a.D86", "86")])
def test_stage_comes_from_the_file_type(name, stage):
    _, items, entry = read(DETAILED, name)
    assert entry["stage"] == stage and set(i["stage"] for i in items) == {stage}
    assert any("header says stage" in w for w in entry["warnings"]) == (stage != "83")


@pytest.mark.parametrize("name", ["a.X83", "a.pdf", "a", "a.D85"])
def test_other_file_types_are_refused(name):
    with pytest.raises(gaeb90.Gaeb90Error):
        gaeb90.parse_bytes(build(DETAILED), name)
    assert not gaeb90.is_gaeb90_name(name)


def priced(unit_price, total, quantity="00000002500", repeat_quantity=True):
    return [
        header("86L", "P-TEST-1"),
        item("0100   1 ", quantity, "m"),
        prices("0100   1 ", unit_price, total, quantity if repeat_quantity else ""),
        "25Pipe",
        end(1),
    ]


def test_unit_price_with_ten_digits_has_two_decimals():
    _, items, entry = read(priced("0000000420", "000000001050"), "o.D86")
    assert (items[0]["quantity"], items[0]["unit_price"], items[0]["total"]) == (2.5, 4.2, 10.5)
    assert entry["price_check"] == {"equal": 1, "not_equal": 0, "no_quantity": 0}
    assert entry["priced_items"] == 1 and entry["warnings"] == []


def test_unit_price_with_eleven_digits_has_three_decimals():
    _, items, entry = read(priced("00000004205", "000000001051"), "o.D86")
    assert (items[0]["unit_price"], items[0]["total"]) == (4.205, 10.51)
    assert entry["price_check"]["equal"] == 1


def test_both_digit_counts_give_the_same_price():
    _, ten, _ = read(priced("0000000420", "000000001050"), "o.D86")
    _, eleven, _ = read(priced("00000004200", "000000001050"), "o.D86")
    assert ten[0]["unit_price"] == eleven[0]["unit_price"] == 4.2


def test_total_that_does_not_fit_is_counted_and_named_without_a_price():
    _, items, entry = read(priced("0000000420", "000000010500"), "o.D86")
    assert entry["price_check"] == {"equal": 0, "not_equal": 1, "no_quantity": 0}
    warning = [w for w in entry["warnings"] if "not the total" in w]
    assert warning == ["quantity x unit price is not the total for 1 items: 01.00.1"]


@pytest.mark.parametrize("constant,value", [
    ("UNIT_PRICE_DECIMALS", 2), ("UNIT_PRICE_DECIMALS", 4),
    ("TOTAL_DECIMALS", 3), ("TOTAL_DECIMALS", 1), ("QUANTITY_DECIMALS", 2),
])
def test_wrong_decimal_place_makes_the_price_check_fail(monkeypatch, constant, value):
    monkeypatch.setattr(gaeb90, constant, value)
    _, _, entry = read(priced("0000000420", "000000001050"), "o.D86")
    assert entry["price_check"]["not_equal"] == 1 and entry["price_check"]["equal"] == 0


def test_quantity_of_the_price_record_is_used_and_a_difference_is_warned():
    records = priced("0000000420", "000000001050")
    records[1] = "210100   1 NNN"
    _, items, entry = read(records, "o.D86")
    assert items[0]["quantity"] == 2.5 and items[0]["unit"] is None
    assert entry["price_check"]["equal"] == 1
    records = priced("0000000420", "000000001050")
    records[2] = prices("0100   1 ", "0000000420", "000000001050", "00000009000")
    _, items, entry = read(records, "o.D86")
    assert items[0]["quantity"] == 2.5
    assert any("differs from the item record" in w for w in entry["warnings"])


COMPACT = [
    "T0",
    "T1Opening text title",
    "T1Opening text body",
    "T9",
    header("84L", "P-TEST-2"),
    "01Test trade",
    prices("01010001", "0000000420", "000000001050"),
    prices("01010002", "0000001000", "000000003000"),
    "320101",
    prices("02010001", "0000000100", "000000000100"),
    "320201",
    end(3),
]


def test_layout_without_item_records_reads_items_from_price_records():
    project, items, entry = read(COMPACT, "offer.D84")
    assert project == "P-TEST-2"
    assert [(i["kind"], i["item_no"], i["section"], i["line"]) for i in items] == [
        ("preliminary_note", "", "", 1),
        ("normal", "01.01.0001", "01.01", 7),
        ("normal", "01.01.0002", "01.01", 8),
        ("normal", "02.01.0001", "02.01", 10),
    ]
    assert (items[0]["short_text"], items[0]["long_text"]) == ("Opening text title", "Opening text body")
    for i in positions(items):
        assert i["quantity"] is None and i["unit"] is None
        assert i["short_text"] == "" and i["long_text"] == ""
        assert i["unit_price"] is not None and i["total"] is not None
    assert items[1]["unit_price"] == 4.2 and items[1]["total"] == 10.5
    assert entry["items"] == 3 and entry["unparsed_lines"] == 0
    assert entry["price_check"] == {"equal": 0, "not_equal": 0, "no_quantity": 3}
    assert any("3 items come from price records" in w for w in entry["warnings"])
    assert any("3 priced items have no quantity" in w for w in entry["warnings"])
    assert entry["skipped_records"] == {"32": 2, "T9": 1}


def test_layout_without_short_text_keeps_the_text_lines_as_long_text():
    records = [
        header("84K", ""),
        item(" 1 1  10 ", "00000002500", "m"),
        prices(" 1 1  10 ", "00000004200", "000000001050", "00000002500"),
        "2601Bby 'our own method'",
        item(" 1 1  20 ", "00000001000", "psch"),
        prices(" 1 1  20 ", "00000007000", "000000000700", "00000001000"),
        "32 1 1",
        "32 1",
        "20",
        "26   @@",
        "26   Note for the next part",
        "26   with a body",
        end(2, "000000001750"),
    ]
    project, items, entry = read(records, "Angebot T-77.D84")
    assert project == "T-77"
    assert [(i["kind"], i["item_no"], i["short_text"], i["long_text"]) for i in items] == [
        ("normal", "1.1.10", "", "by 'our own method'"),
        ("lump_sum", "1.1.20", "", ""),
        ("preliminary_note", "", "Note for the next part", "with a body"),
    ]
    assert entry["text_supplement_lines"] == 1
    assert entry["skipped_records"] == {"26 with only @@": 1, "32": 2}
    assert entry["price_check"] == {"equal": 2, "not_equal": 0, "no_quantity": 0}
    assert entry["sum_check"] == "equal" and entry["warnings"] == []


def test_sum_of_the_end_record_is_compared_with_the_totals():
    records = priced("0000000420", "000000001050")
    records[-1] = end(1, "000000001050")
    assert read(records, "o.D86")[2]["sum_check"] == "equal"
    records[-1] = end(1, "000000010500")
    entry = read(records, "o.D86")[2]
    assert entry["sum_check"] == "not_equal"
    assert "the sum in the end record is not the sum of the item totals" in entry["warnings"]
    records[-1] = end(1, "000000000000")
    assert read(records, "o.D86")[2]["sum_check"] == "not_in_file"


@pytest.mark.parametrize("flags,unit,kind,warned", [
    ("NNN", "St", "normal", False), ("NNN", "psch", "lump_sum", False),
    ("WNN", "St", "alternative", False), ("NEN", "psch", "optional", False),
    ("WEN", "St", "alternative", False), ("   ", "St", "normal", False),
    ("NNL", "St", "normal", True), ("XNN", "psch", "lump_sum", True),
])
def test_kind_from_flags_and_unit(flags, unit, kind, warned):
    records = [header(), item("0100   1 ", "00000001000", unit, flags), "25Thing", end(1)]
    _, items, entry = read(records)
    assert items[0]["kind"] == kind
    assert any("item flags the reader does not know" in w and "01.00.1" in w
               for w in entry["warnings"]) == warned


def test_unreadable_lines_are_counted_with_their_line_numbers():
    records = [
        header(),
        "26   Text before any item",
        "25Short before any item",
        "12Name without section",
        item("0100   1 ", "0000000X000", "St"),
        "25Thing",
        "77Unknown record",
        "28content in a record seen only empty",
        "24",
        item("0100   2 ", "00000001000", "St"),
        "25Other",
        prices("0100   2 ", "00000X0420", "000000001050", "00000001000"),
        "X" * 90,
        end(2),
        "26   Text after the end",
    ]
    _, items, entry = read(records)
    assert entry["unparsed_line_numbers"] == [2, 3, 4, 5, 7, 8, 9, 12, 13, 15]
    assert entry["unparsed_lines"] == 10
    assert "10 lines not read" in entry["warnings"]
    assert [(i["item_no"], i["quantity"], i["unit_price"]) for i in positions(items)] == [
        ("01.00.1", None, None), ("01.00.2", 1.0, None)]
    assert entry["items"] == 2


@pytest.mark.parametrize("broken", [item("0100   2 ", "00000001000", "St") + " " * 60, "77Unknown start"])
def test_text_after_an_unreadable_line_does_not_go_to_the_item_before(broken):
    records = [header(), item("0100   1 ", "00000001000", "St"), "25One", "26   Long one",
               broken, "25Two", "26   Long two", item("0100   3 ", "00000001000", "St"), "25Three", end(2)]
    _, items, entry = read(records)
    assert [(i["item_no"], i["short_text"], i["long_text"]) for i in items] == [
        ("01.00.1", "One", "Long one"), ("01.00.3", "Three", "")]
    assert entry["unparsed_line_numbers"] == [5, 6, 7]


@pytest.mark.parametrize("broken", ["26   Long" + " " * 80, "77Unknown"])
def test_unreadable_line_inside_an_item_keeps_its_price_on_that_item(broken):
    records = [header("86L"), item("0100   1 ", "00000002000", "St"), "25One", broken,
               prices("0100   1 ", "0000000300", "000000000600"), end(1)]
    _, items, entry = read(records, name="order.D86")
    assert [i["item_no"] for i in items] == ["01.00.1"]
    assert entry["priced_items"] == 1 and entry["price_check"]["equal"] == 1
    assert entry["unparsed_line_numbers"] == [4]


def test_overlong_price_record_of_another_item_closes_the_item_before():
    records = [header("84K"), item("0100   1 ", "00000002000", "St"),
               prices("0100   1 ", "0000000300", "000000000600"), "26   One",
               prices("0100   2 ", "0000000300", "000000000600") + " " * 60, "26   Two", end(1)]
    _, items, entry = read(records, name="offer.D84")
    assert [(i["item_no"], i["long_text"]) for i in items] == [("01.00.1", "One")]
    assert entry["unparsed_line_numbers"] == [5, 6]


def test_text_after_a_price_goes_to_its_item_after_an_unreadable_line():
    records = [header("84K"), item("0100   1 ", "00000002000", "St"), "77Unknown",
               prices("0100   1 ", "0000000300", "000000000600"), "26   One", end(1)]
    _, items, entry = read(records, name="offer.D84")
    assert [(i["item_no"], i["long_text"]) for i in items] == [("01.00.1", "One")]
    assert entry["price_check"]["equal"] == 1 and entry["unparsed_line_numbers"] == [3]


def test_overlong_text_line_does_not_lose_the_text_lines_after_it():
    records = [header(), item("0100   1 ", "00000001000", "St"), "25One",
               "26   Lost" + " " * 80, "26   Kept", end(1)]
    _, items, entry = read(records)
    assert [(i["item_no"], i["long_text"]) for i in items] == [("01.00.1", "Kept")]
    assert entry["unparsed_line_numbers"] == [4]


def test_only_the_first_fifty_unreadable_line_numbers_are_listed():
    records = [header()] + ["77Unknown"] * 60 + [end(0)]
    entry = read(records)[2]
    assert entry["unparsed_lines"] == 60 and len(entry["unparsed_line_numbers"]) == 50


def test_empty_helper_records_are_skipped_and_counted():
    records = [
        header("86L"), "110100", "12Section", "41001", "42", "25General title", "26   General body",
        item("0100   1 ", "00000001000", "St", repeat="W"), "28", "25As item 2, but", "25blue",
        "26   Long", "24 1  00000001000", "25Sub title", "26   Sub body",
        "30          0000000420", "310100", "320100", end(1),
    ]
    _, items, entry = read(records, "o.D86")
    assert entry["skipped_records"] == {"28": 1, "30": 1, "31": 1, "32": 1, "42": 1}
    assert entry["unparsed_lines"] == 0
    assert (entry["sub_descriptions"], entry["repeat_descriptions"]) == (1, 1)
    note, thing = items[1], items[2]
    assert (note["kind"], note["item_no"], note["short_text"], note["long_text"]) == (
        "preliminary_note", "01.00", "General title", "General body")
    assert thing["short_text"] == "As item 2, but blue"
    assert thing["long_text"] == "Long\n\nSub title\nSub body"


def test_number_that_names_no_section_is_kept_as_written():
    records = [
        header(), "110100", "12Section", item("0100   1 ", "00000001000", "St"), "25One",
        item("ABC00009 ", "00000001000", "St"), "25Two", "310100", end(2),
    ]
    _, items, entry = read(records)
    assert [(i["item_no"], i["section"]) for i in positions(items)] == [
        ("01.00.1", "01.00"), ("ABC00009", "01.00")]
    assert any("ABC00009" in w and "names no section" in w for w in entry["warnings"])


def test_section_records_that_are_not_read_do_not_change_item_numbers():
    records = [header(), item("0100   1 ", "00000001000", "St"), "25One",
               "110900" + " " * 80, end(1), "110900"]
    _, items, entry = read(records)
    assert [i["item_no"] for i in items] == ["01.00.1"]
    assert entry["unparsed_line_numbers"] == [4, 6]
    assert not any("names no section" in w for w in entry["warnings"])


def test_overlong_end_record_does_not_hide_the_sections_after_it():
    records = [header(), "110100", item("0100   1 ", "00000001000", "St"), "25One", "310100",
               end(1) + " " * 20, "110200", item("0200   1 ", "00000001000", "St"), "25Two", "310200", end(2)]
    _, items, entry = read(records)
    assert [i["item_no"] for i in items if i["kind"] == "normal"] == ["01.00.1", "02.00.1"]
    assert entry["unparsed_line_numbers"] == [6]


def test_end_record_count_missing_end_record_and_missing_header():
    records = [header(), item("0100   1 ", "00000001000", "St"), "25One", end(5)]
    assert "the end record names 5 items, the reader found 1" in read(records)[2]["warnings"]
    entry = read(records[:-1])[2]
    assert entry["declared_items"] is None
    assert any("no end record" in w for w in entry["warnings"])
    project, items, entry = read(records[1:], "plain name.D83")
    assert project == "plain_name" and items[0]["item_no"] == "01.00.1"
    assert any("no number mask" in w for w in entry["warnings"])


def test_item_number_that_stands_twice_is_warned():
    records = [header(), item("0100   1 ", "00000001000", "St"), "25One",
               item("0100   1 ", "00000002000", "St"), "25Two", end(2)]
    _, items, entry = read(records)
    assert len(positions(items)) == 2
    assert "item number 01.00.1 stands twice (lines 2 and 4)" in entry["warnings"]


def test_other_number_mask():
    records = [header(mask="112233PPP"), "11010203", "12Deep", item("010203  7", "00000001000", "St"),
               "25One", end(1)]
    _, items, _ = read(records)
    assert [(i["item_no"], i["section"]) for i in items] == [("01.02.03", "01.02"), ("01.02.03.7", "01.02.03")]
    assert gaeb90.split_mask("1122PPPPI") == [("level", 0, 2), ("level", 2, 4), ("position", 4, 8), ("index", 8, 9)]


@pytest.mark.parametrize("encoding", ["cp850", "cp1252"])
def test_german_letters_in_both_code_pages(encoding):
    records = [header(), item("0100   1 ", "00000001000", "m²"), "25Größe prüfen, Maß ändern",
               "26   Öl und Übergänge", end(1)]
    _, items, entry = read(records, encoding=encoding)
    assert entry["encoding"] == encoding
    assert items[0]["short_text"] == "Größe prüfen, Maß ändern"
    assert items[0]["long_text"] == "Öl und Übergänge"
    if encoding == "cp1252":
        assert items[0]["unit"] == "m²"


@pytest.mark.parametrize("encoding", ["cp850", "cp1252"])
def test_square_metre_without_any_german_letter(encoding):
    records = [header(), item("0100   1 ", "00000001000", "m²"), "25Floor", end(1)]
    _, items, entry = read(records, encoding=encoding)
    assert entry["encoding"] == encoding and items[0]["unit"] == "m²"
    assert entry["warnings"] == []


def test_raised_two_does_not_outvote_the_german_letters():
    records = [header(), item("0100   1 ", "00000001000", "St"), "25Tür mit Beschlag ý", end(1)]
    _, items, entry = read(records, encoding="cp1252")
    assert entry["encoding"] == "cp1252" and items[0]["short_text"] == "Tür mit Beschlag ý"
    records[2] = "25Tür 2 m² groß"
    _, items, entry = read(records, encoding="cp850")
    assert entry["encoding"] == "cp850" and items[0]["short_text"] == "Tür 2 m² groß"


def test_unit_that_shows_a_wrong_code_page_is_warned():
    records = [header(), item("0100   1 ", "00000001000", "m³"), "25Größe", "26   Tür", "26   Maß",
               item("0100   2 ", "00000001000", "St"), "25Other", end(2)]
    raw = build(records, encoding="cp1252").replace("Größe".encode("cp1252"), "Größe".encode("cp850"))
    _, items, entry = gaeb90.parse_bytes(raw, "list.D83")
    assert entry["encoding"] == "cp850" and items[0]["unit"] != "m³"
    assert any("01.00.1" in w and "box drawing character" in w for w in entry["warnings"])


def test_byte_outside_the_code_page_is_warned_and_the_file_is_still_read():
    records = [header(), item("0100   1 ", "00000001000", "St"), "25Größe prüfen", "26   Maß ändern", end(1)]
    raw = build(records, encoding="cp1252").replace(b"Ma\xdf", b"Ma\x81")
    _, items, entry = gaeb90.parse_bytes(raw, "list.D83")
    assert entry["encoding"] == "cp1252" and entry["items"] == 1
    assert items[0]["long_text"] == "Ma\ufffd ändern"
    assert any("1 lines hold a byte that is not in code page cp1252" in w and "first line 4" in w
               for w in entry["warnings"])


def test_line_ends_and_cut_lines():
    plain = read(DETAILED)[1]
    assert read(DETAILED, newline="\n")[1] == plain
    cut = b"\r\n".join(r.rstrip().encode("cp850") for r in DETAILED) + b"\r\n\r\n"
    _, items, entry = gaeb90.parse_bytes(cut, "list.D83")
    assert items == plain and entry["unparsed_lines"] == 0 and entry["lines"] == len(DETAILED)


def test_note_without_text_is_not_written_but_warned():
    records = [header(), "20", item("0100   1 ", "00000001000", "St"), "25One", end(1)]
    _, items, entry = read(records)
    assert [i["kind"] for i in items] == ["normal"]
    assert "note at line 2 has no text; not written" in entry["warnings"]


def test_fixed_number():
    assert gaeb90.fixed_number("00000002500", 3) == Decimal("2.5")
    assert gaeb90.fixed_number("  000000001050 ", 2) == Decimal("10.5")
    assert gaeb90.fixed_number("-0000001050", 2) == Decimal("-10.5")
    assert gaeb90.fixed_number("           ", 3) is None
    assert gaeb90.fixed_number(" 0000000420 ", 3, left_aligned=True) == Decimal("4.2")
    assert gaeb90.fixed_number(" 00000004205", 3, left_aligned=True) == Decimal("4.205")
    for bad in ("00000X02500", "0000 002500", "1.5", "--5"):
        with pytest.raises(ValueError):
            gaeb90.fixed_number(bad, 3)
    with pytest.raises(ValueError):
        gaeb90.fixed_number("000 0000420 ", 3, left_aligned=True)


def write(folder, name, records):
    path = os.path.join(str(folder), name)
    with open(path, "wb") as handle:
        handle.write(build(records))
    return path


def load(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as handle:
        return json.load(handle)


def test_command_reads_a_folder_and_writes_one_folder_per_project(tmp_path, capsys):
    data, out = tmp_path / "data", str(tmp_path / "out")
    data.mkdir()
    write(data, "list.D83", DETAILED)
    write(data, "order.D86", priced("0000000420", "000000001050"))
    write(data, "offer.d84", COMPACT)
    write(data, "notes.txt", ["not a list"])
    write(data, "twin.X83", ["not read by this reader"])
    assert gaeb90.main([str(data), out]) == 0
    assert sorted(os.listdir(out)) == ["P-TEST-1", "P-TEST-2"]
    manifest = load(out, "P-TEST-1", "manifest.json")
    items = load(out, "P-TEST-1", "items.json")
    assert [(e["doc"], e["stage"], e["items"]) for e in manifest] == [("list.D83", "83", 3), ("order.D86", "86", 1)]
    assert [i["doc"] for i in items] == ["list.D83"] * 6 + ["order.D86"]
    assert [e["doc"] for e in load(out, "P-TEST-2", "manifest.json")] == ["offer.d84"]
    contract.check("items", items)
    contract.check("manifest", manifest)
    printed = capsys.readouterr().out
    assert printed.count("\n") == 3
    assert "order.D86 -> %s: 1 items" % os.path.join(out, "P-TEST-1") in printed
    assert "priced 1: equal 1, not equal 0, no quantity 0" in printed
    assert "4.2" not in printed and "10.5" not in printed and "420" not in printed


def test_command_reads_one_file_and_takes_a_project_name(tmp_path):
    out = str(tmp_path / "out")
    path = write(tmp_path, "order.D86", priced("0000000420", "000000001050"))
    assert gaeb90.main([path, out, "--project", "other"]) == 0
    assert os.listdir(out) == ["other"]
    items = load(out, "other", "items.json")
    assert items[0]["project"] == "other" and items[0]["total"] == 10.5
    assert gaeb90.main([path, out, "--project", "other"]) == 0
    assert len(load(out, "other", "items.json")) == 1
    assert len(load(out, "other", "manifest.json")) == 1


def test_command_says_so_when_there_is_nothing_to_read(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert gaeb90.main([str(empty), str(tmp_path / "out")]) == 1
    assert gaeb90.main([str(tmp_path / "missing.D83"), str(tmp_path / "out")]) == 2
    other = tmp_path / "a.pdf"
    other.write_bytes(b"x")
    assert gaeb90.main([str(other), str(tmp_path / "out")]) == 2
    assert not os.path.exists(str(tmp_path / "out"))
    assert "error:" in capsys.readouterr().err
