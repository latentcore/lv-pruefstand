"""GAEB 90 reader on the five organizer files. Skipped when data/ is not there.

The checks print and assert counts only ("equal" / "not equal"); no price, no
total and no record line appears in a test name, a message or the output.
"""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import pytest  # noqa: E402

from pipeline.common import contract  # noqa: E402
from pipeline.lv import gaeb90, model  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DATA_DIR = os.environ.get("GAEB90_DATA_DIR") or os.path.join(REPO, "data")
# file name -> (stage, items, priced items, twin that holds the quantities or None)
FILES = {
    "8209.003_Leistungsverzeichnis_leer.D83": ("83", 159, 0, None),
    "[ORT_024] LV24069.D86": ("86", 197, 197, None),
    "Angebot AN24-0305.D84": ("84", 274, 274, None),
    "StBALV23040.D84": ("84", 249, 249, "StBALV23040.D86"),
    "StBALV23040.D86": ("86", 249, 249, None),
}
MISSING = [name for name in FILES if not os.path.isfile(os.path.join(DATA_DIR, name))]

pytestmark = pytest.mark.skipif(bool(MISSING), reason="organizer GAEB 90 files not in %s" % DATA_DIR)


@pytest.fixture(scope="module")
def parsed():
    return dict((name, gaeb90.parse_file(os.path.join(DATA_DIR, name))) for name in FILES)


def positions(items):
    return [item for item in items if model.is_position(item)]


def with_twin_quantities(items, twin_items):
    """Copies of the priced items with the quantity of the same item number in the twin."""
    quantities = dict((item["item_no"], item["quantity"]) for item in positions(twin_items))
    return [dict(item, quantity=quantities.get(item["item_no"])) for item in positions(items)]


def check_of(name, parsed):
    """Price check of one file; a file without quantities borrows them from its twin."""
    items = parsed[name][1]
    twin = FILES[name][3]
    if twin:
        items = with_twin_quantities(items, parsed[twin][1])
    return model.price_check(items)


@pytest.mark.parametrize("name", sorted(FILES))
def test_item_count_stage_and_contract(name, parsed):
    stage, count, _, _ = FILES[name]
    _, items, entry = parsed[name]
    assert len(positions(items)) == count
    assert entry["items"] == count and entry["declared_items"] == count
    assert entry["stage"] == stage and entry["format"] == "gaeb90" and entry["pages"] is None
    assert entry["unparsed_lines"] == 0 and entry["unparsed_line_numbers"] == []
    assert entry["sha256"] == model.sha256_file(os.path.join(DATA_DIR, name))
    assert all(i["stage"] == stage and i["format"] == "gaeb90" and i["page"] is None for i in items)
    assert all(isinstance(i["line"], int) and i["line"] >= 1 for i in items)
    assert len(set(i["item_no"] for i in positions(items))) == count
    contract.check("items", items)
    contract.check("manifest", [entry])


def test_the_five_counts_are_159_197_274_249_249(parsed):
    order = ["8209.003_Leistungsverzeichnis_leer.D83", "[ORT_024] LV24069.D86",
             "Angebot AN24-0305.D84", "StBALV23040.D84", "StBALV23040.D86"]
    assert [parsed[name][2]["items"] for name in order] == [159, 197, 274, 249, 249]


@pytest.mark.parametrize("name", sorted(FILES))
def test_quantity_times_unit_price_is_the_total_for_every_priced_item(name, parsed, capsys):
    priced = FILES[name][2]
    check = check_of(name, parsed)
    with capsys.disabled():
        print("\n%s: priced %d, equal %d, not equal %d, without quantity %d%s"
              % (name, check["priced"], check["equal"], check["not_equal"], check["no_quantity"],
                 " (quantities from %s)" % FILES[name][3] if FILES[name][3] else ""))
    assert check["priced"] == priced
    assert check["not_equal"] == 0, "not equal: %d items" % check["not_equal"]
    assert check["no_quantity"] == 0, "without quantity: %d items" % check["no_quantity"]
    assert check["equal"] == priced


def test_file_without_quantities_says_so_in_its_manifest(parsed):
    _, items, entry = parsed["StBALV23040.D84"]
    assert all(i["quantity"] is None and i["unit"] is None for i in positions(items))
    assert entry["price_check"] == {"equal": 0, "not_equal": 0, "no_quantity": 249}
    assert any("249 priced items have no quantity" in w for w in entry["warnings"])
    assert any("249 items come from price records" in w for w in entry["warnings"])


@pytest.mark.parametrize("name", sorted(n for n in FILES if FILES[n][2]))
@pytest.mark.parametrize("constant,value", [
    ("UNIT_PRICE_DECIMALS", 2), ("UNIT_PRICE_DECIMALS", 4), ("TOTAL_DECIMALS", 3), ("TOTAL_DECIMALS", 1),
])
def test_wrong_decimal_place_fails_the_price_check(name, constant, value, monkeypatch):
    """Proof that the check above has teeth: the same file read with the
    decimal point one place off must give 'not equal' items."""
    monkeypatch.setattr(gaeb90, constant, value)
    wrong = dict((n, gaeb90.parse_file(os.path.join(DATA_DIR, n)))
                 for n in (name, FILES[name][3]) if n)
    monkeypatch.undo()
    if FILES[name][3]:
        wrong[FILES[name][3]] = gaeb90.parse_file(os.path.join(DATA_DIR, FILES[name][3]))
    check = check_of(name, wrong)
    assert check["not_equal"] > 0
    assert check["equal"] < FILES[name][2]


def test_sum_of_the_end_record_where_the_file_has_one(parsed):
    checks = dict((name, parsed[name][2]["sum_check"]) for name in FILES)
    assert "not_equal" not in checks.values()
    assert checks["Angebot AN24-0305.D84"] == "equal"


def test_texts_units_and_kinds(parsed):
    for name in ("8209.003_Leistungsverzeichnis_leer.D83", "[ORT_024] LV24069.D86", "StBALV23040.D86"):
        _, items, entry = parsed[name]
        assert all(i["short_text"] for i in items), name
        assert entry["headings"] > 0 and entry["preliminary_notes"] > 0
        assert set(i["kind"] for i in positions(items)) == {"normal", "lump_sum"}
        assert all(i["quantity"] is not None for i in positions(items))
        assert all(i["section"] for i in positions(items))
    request = positions(parsed["8209.003_Leistungsverzeichnis_leer.D83"][1])
    assert all(i["long_text"] and i["unit"] for i in request)
    assert all(i["unit_price"] is None and i["total"] is None for i in request)
    offer = positions(parsed["Angebot AN24-0305.D84"][1])
    assert all(i["short_text"] == "" and i["unit"] for i in offer)
    assert sum(1 for i in offer if i["long_text"]) > 0


def test_request_and_order_of_one_project_share_the_items(parsed):
    request = dict((i["item_no"], i) for i in positions(parsed["8209.003_Leistungsverzeichnis_leer.D83"][1]))
    order = dict((i["item_no"], i) for i in positions(parsed["[ORT_024] LV24069.D86"][1]))
    assert parsed["8209.003_Leistungsverzeichnis_leer.D83"][0] == parsed["[ORT_024] LV24069.D86"][0]
    assert set(request) <= set(order)
    assert all(request[no]["short_text"] == order[no]["short_text"] for no in request)


def test_offer_and_order_twins_have_the_same_item_numbers(parsed):
    offer = set(i["item_no"] for i in positions(parsed["StBALV23040.D84"][1]))
    order = set(i["item_no"] for i in positions(parsed["StBALV23040.D86"][1]))
    assert offer == order and len(offer) == 249


def test_command_writes_the_project_folders(tmp_path, capsys):
    out = str(tmp_path / "out")
    assert gaeb90.main([DATA_DIR, out]) == 0
    capsys.readouterr()
    report = gaeb90.run(DATA_DIR, out)
    assert sorted(entry["file"] for entry in report if entry["file"] in FILES) == sorted(FILES)
    by_file = dict((entry["file"], entry) for entry in report)
    total = Decimal(0)
    for name in FILES:
        folder = os.path.join(out, by_file[name]["project"])
        assert os.path.isfile(os.path.join(folder, "items.json"))
        assert os.path.isfile(os.path.join(folder, "manifest.json"))
        total += by_file[name]["items"]
    assert total == 159 + 197 + 274 + 249 + 249
