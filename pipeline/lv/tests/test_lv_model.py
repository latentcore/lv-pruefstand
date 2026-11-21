import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import pytest  # noqa: E402

from pipeline.common import contract  # noqa: E402
from pipeline.lv import model  # noqa: E402


def make(**changes):
    values = dict(doc="A.D83", project="P1", trade="Trade", format="gaeb90", stage="83",
                  item_no="01.02.3", kind="normal", short_text="Short", long_text="Long",
                  quantity=2, unit="St")
    values.update(changes)
    return model.make_item(**values)


def test_item_has_exactly_the_contract_keys_in_contract_order():
    item = make()
    schema = contract.load_schema("items")
    assert list(item) == schema["items"]["required"]
    assert list(item) == list(model.ITEM_KEYS)
    assert contract.errors("items", [item]) == []


def test_item_defaults_are_null_and_section_comes_from_the_number():
    item = make()
    assert item["section"] == "01.02"
    assert item["quantity"] == 2.0 and isinstance(item["quantity"], float)
    for key in ("unit_price", "total", "page", "line", "pre_trade_text", "post_trade_text"):
        assert item[key] is None
    assert make(section="X")["section"] == "X"
    assert make(section="")["section"] == ""


@pytest.mark.parametrize("changes", [
    {"format": "gaeb"}, {"stage": "85"}, {"kind": "position"}, {"doc": ""},
    {"quantity": "2"}, {"quantity": True}, {"unit": 5}, {"short_text": None},
    {"item_no": None}, {"page": 1.5}, {"line": "7"},
])
def test_item_with_a_wrong_value_is_refused(changes):
    with pytest.raises(ValueError):
        make(**changes)


def test_section_of_and_item_no_key():
    assert model.section_of("01.02.3") == "01.02"
    assert model.section_of("01") == ""
    assert model.section_of("") == ""
    assert model.item_no_key("01.01.0010") == "1.1.10"
    assert model.item_no_key("1.1.10") == "1.1.10"
    assert model.item_no_key("01.00.0100") == "1.0.100"
    assert model.item_no_key("AB12") == "AB12"


def test_kind_of():
    assert model.kind_of() == "normal"
    assert model.kind_of(unit="St") == "normal"
    assert model.kind_of(unit="psch") == "lump_sum"
    assert model.kind_of(unit="Psch.") == "lump_sum"
    assert model.kind_of(optional=True, unit="psch") == "optional"
    assert model.kind_of(alternative=True, optional=True) == "alternative"


def test_doc_id_and_project_id():
    assert model.doc_id("dir/[X_1] List 7.D86") == "X_1_List_7.D86"
    assert model.doc_id("a.X83") != model.doc_id("a.D83")
    with pytest.raises(ValueError):
        model.doc_id("///")
    assert model.project_id("List 7.D83", " 12.5 ") == "12.5"
    assert model.project_id("Angebot AB-1.D84") == "AB-1"
    assert model.project_id("[X_1] List 7.D86", "") == "X_1_List_7"
    with pytest.raises(ValueError):
        model.project_id("x.D83", "..")


def test_price_check_counts_equal_not_equal_and_no_quantity():
    items = [
        make(item_no="1", quantity=3, unit_price=1.5, total=4.5),
        make(item_no="2", quantity=0.333, unit_price=10.0, total=3.33),
        make(item_no="3", quantity=3, unit_price=1.5, total=45.0),
        make(item_no="4", quantity=None, unit_price=1.5, total=4.5),
        make(item_no="5", quantity=3),
        make(item_no="6", kind="heading", quantity=3, unit_price=1.0, total=9.0),
    ]
    result = model.price_check(items)
    assert result == {"priced": 4, "equal": 2, "not_equal": 1, "no_quantity": 1,
                      "not_equal_items": ["3"]}


def test_price_check_allows_half_a_cent_and_no_more():
    assert model.price_check([make(quantity=1, unit_price=2.005, total=2.0)])["equal"] == 1
    assert model.price_check([make(quantity=1, unit_price=2.005, total=2.01)])["equal"] == 1
    assert model.price_check([make(quantity=1, unit_price=2.006, total=2.0)])["not_equal"] == 1
    assert model.price_check([make(quantity=1, unit_price=2.0, total=2.01)])["not_equal"] == 1


def test_manifest_entry_counts_positions_headings_and_notes():
    items = [make(), make(kind="lump_sum"), make(kind="heading"), make(kind="preliminary_note")]
    entry = model.make_manifest_entry("A.D83", "A.D83", "0" * 64, "gaeb90", "83", items,
                                      unparsed_lines=2, warnings=["w"], lines=9)
    assert entry["items"] == 2 and entry["headings"] == 1 and entry["preliminary_notes"] == 1
    assert entry["pages"] is None and entry["unparsed_lines"] == 2 and entry["lines"] == 9
    assert contract.errors("manifest", [entry]) == []
    with pytest.raises(ValueError):
        model.make_manifest_entry("A", "A", "0" * 64, "gaeb", "83", [])
    with pytest.raises(ValueError):
        model.make_manifest_entry("A", "A", "0" * 64, "gaeb90", "", [])


def test_sha256_file(tmp_path):
    path = tmp_path / "f.bin"
    path.write_bytes(b"abc")
    assert model.sha256_file(str(path)) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def read(folder, name):
    with open(os.path.join(folder, name), encoding="utf-8") as handle:
        return json.load(handle)


def test_write_project_keeps_other_documents_and_replaces_its_own(tmp_path):
    out = str(tmp_path)

    def entry(doc, items):
        return model.make_manifest_entry(doc, doc, "0" * 64, "gaeb90", "83", items)

    first = [make(doc="A.D83", item_no="1"), make(doc="A.D83", item_no="2")]
    folder = model.write_project(out, "P1", first, [entry("A.D83", first)])
    assert folder == os.path.join(out, "P1")
    second = [make(doc="B.D84", stage="84", item_no="1")]
    model.write_project(out, "P1", second, [entry("B.D84", second)])
    again = [make(doc="A.D83", item_no="9", short_text="Ärger")]
    model.write_project(out, "P1", again, [entry("A.D83", again)])
    items, manifest = read(folder, "items.json"), read(folder, "manifest.json")
    assert [(i["doc"], i["item_no"]) for i in items] == [("A.D83", "9"), ("B.D84", "1")]
    assert [(e["doc"], e["items"]) for e in manifest] == [("A.D83", 1), ("B.D84", 1)]
    with open(os.path.join(folder, "items.json"), encoding="utf-8") as handle:
        assert "Ärger" in handle.read()
    contract.check("items", items)
    contract.check("manifest", manifest)


def test_write_project_refuses_two_files_with_one_document_id(tmp_path):
    out = str(tmp_path)
    assert model.doc_id("list a.D83") == model.doc_id("list_a.D83")

    def entry(file):
        return model.make_manifest_entry(model.doc_id(file), file, "0" * 64, "gaeb90", "83", [])

    with pytest.raises(ValueError, match="two files give the document id"):
        model.write_project(out, "P1", [], [entry("list a.D83"), entry("list_a.D83")])
    assert not os.path.exists(os.path.join(out, "P1"))
    first = [make(doc="list_a.D83", item_no="1")]
    folder = model.write_project(out, "P1", first, [entry("list a.D83")])
    with pytest.raises(ValueError, match="already used by the file 'list a.D83'"):
        model.write_project(out, "P1", [], [entry("list_a.D83")])
    assert [i["item_no"] for i in read(folder, "items.json")] == ["1"]
    model.write_project(out, "P1", [], [entry("list a.D83")])
    assert read(folder, "items.json") == []


def test_write_project_refuses_items_without_manifest_entry_and_bad_records(tmp_path):
    out = str(tmp_path)
    items = [make(doc="A.D83")]
    with pytest.raises(ValueError):
        model.write_project(out, "P1", items, [])
    broken = dict(make(doc="A.D83"))
    del broken["unit"]
    entry = model.make_manifest_entry("A.D83", "A.D83", "0" * 64, "gaeb90", "83", items)
    with pytest.raises(contract.ContractError):
        model.write_project(out, "P1", [broken], [entry])
    assert not os.path.exists(os.path.join(out, "P1"))
