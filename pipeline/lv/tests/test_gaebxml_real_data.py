"""GAEB XML reader on the four organizer files. Skipped when data/ is not there.

The checks print and assert counts only; no text of a file and no price
appears in a test name, a message or the output.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import pytest  # noqa: E402

from pipeline.common import contract  # noqa: E402
from pipeline.lv import gaeb90, gaebxml, model  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DATA_DIR = os.environ.get("GAEBXML_DATA_DIR") or os.path.join(REPO, "data")
# file name -> (GAEB XML version, items)
FILES = {
    "501-24-01_GAEB-XML_sas.x83": ("3.1", 296),
    "8209.003_Leistungsverzeichnis_leer.X83": ("3.2", 159),
    "GAEB-[PROJEKT_004].X83": ("3.2", 50),
    "[NUMMER_001]_leer.X83": ("3.2", 248),
}
NAMESPACES = {"3.1": "http://www.gaeb.de/GAEB_DA_XML/200407", "3.2": "http://www.gaeb.de/GAEB_DA_XML/DA83/3.2"}
TWIN_XML = "8209.003_Leistungsverzeichnis_leer.X83"
TWIN_GAEB90 = "8209.003_Leistungsverzeichnis_leer.D83"
MISSING = [name for name in FILES if not os.path.isfile(os.path.join(DATA_DIR, name))]

pytestmark = pytest.mark.skipif(bool(MISSING), reason="organizer GAEB XML files not in %s" % DATA_DIR)
needs_twin = pytest.mark.skipif(not os.path.isfile(os.path.join(DATA_DIR, TWIN_GAEB90)),
                                reason="GAEB 90 twin not in %s" % DATA_DIR)


@pytest.fixture(scope="module")
def parsed():
    return dict((name, gaebxml.parse_file(os.path.join(DATA_DIR, name))) for name in FILES)


def positions(items):
    return [item for item in items if model.is_position(item)]


def test_the_four_counts_are_296_159_50_248(parsed):
    order = ["501-24-01_GAEB-XML_sas.x83", "8209.003_Leistungsverzeichnis_leer.X83",
             "GAEB-[PROJEKT_004].X83", "[NUMMER_001]_leer.X83"]
    assert [parsed[name][2]["items"] for name in order] == [296, 159, 50, 248]
    assert [len(positions(parsed[name][1])) for name in order] == [296, 159, 50, 248]


@pytest.mark.parametrize("name", sorted(FILES))
def test_item_count_stage_version_and_contract(name, parsed):
    version, count = FILES[name]
    _, items, entry = parsed[name]
    assert len(positions(items)) == count and entry["items"] == count
    assert entry["stage"] == "83" and entry["format"] == "gaebxml" and entry["pages"] is None
    assert entry["gaeb_version"] == version and entry["namespace"] == NAMESPACES[version]
    assert entry["sha256"] == model.sha256_file(os.path.join(DATA_DIR, name))
    assert entry["file"] == name
    assert all(i["stage"] == "83" and i["format"] == "gaebxml" and i["page"] is None for i in items)
    assert all(isinstance(i["line"], int) and i["line"] >= 1 for i in items)
    assert len(set(i["item_no"] for i in positions(items))) == count
    contract.check("items", items)
    contract.check("manifest", [entry])


@pytest.mark.parametrize("name", sorted(FILES))
def test_count_equals_the_item_start_tags_in_the_raw_file(name, parsed):
    """A count that does not use the reader: the "<Item" start tags in the bytes."""
    with open(os.path.join(DATA_DIR, name), "rb") as handle:
        raw = handle.read()
    assert len(re.findall(rb"<(?:\w+:)?Item[\s>]", raw)) == parsed[name][2]["items"]
    assert len(re.findall(rb"<(?:\w+:)?BoQCtgy[\s>]", raw)) == parsed[name][2]["headings"]


@pytest.mark.parametrize("name", sorted(FILES))
def test_nothing_is_left_unread_and_nothing_is_warned(name, parsed, capsys):
    entry = parsed[name][2]
    with capsys.disabled():
        print("\n%s: items %d, headings %d, notes %d, elements not read %d, warnings %d, "
              "elements skipped on purpose %d of %d kinds"
              % (name, entry["items"], entry["headings"], entry["preliminary_notes"], entry["unparsed_lines"],
                 len(entry["warnings"]), sum(entry["skipped_elements"].values()), len(entry["skipped_elements"])))
    assert entry["unparsed_lines"] == 0 and entry["unparsed_elements"] == {}
    assert entry["unparsed_element_lines"] == [] and entry["warnings"] == []


@pytest.mark.parametrize("name", sorted(FILES))
def test_texts_sections_quantities_and_units(name, parsed):
    _, items, entry = parsed[name]
    request = positions(items)
    assert all(i["short_text"] and i["long_text"] for i in request)
    assert all(i["quantity"] is not None and i["quantity"] > 0 and i["unit"] for i in request)
    assert all(i["section"] and i["item_no"].startswith(i["section"] + ".") for i in request)
    assert all("<" not in i["short_text"] and "\n" not in i["short_text"] for i in items)
    assert not any(re.search(r"</?(p|span|br|ul|li|div|TextComplement|Compl\w+)\b[^<>]*>", i["long_text"])
                   for i in items)
    headings = [i for i in items if i["kind"] == "heading"]
    sections = set(i["item_no"] for i in headings)
    assert headings and len(sections) == len(headings) and all(i["short_text"] for i in headings)
    assert all(i["section"] in sections for i in request)
    assert all(i["section"] == "" or i["section"] in sections for i in headings)
    assert entry["preliminary_notes"] > 0
    assert all(i["short_text"] or i["long_text"] for i in items)


def test_kinds_and_prices(parsed):
    kinds = dict((name, sorted(set(i["kind"] for i in positions(parsed[name][1])))) for name in FILES)
    assert kinds["501-24-01_GAEB-XML_sas.x83"] == ["lump_sum", "normal", "optional"]
    for name in ("8209.003_Leistungsverzeichnis_leer.X83", "GAEB-[PROJEKT_004].X83", "[NUMMER_001]_leer.X83"):
        assert kinds[name] == ["lump_sum", "normal"]
    for name in FILES:
        _, items, entry = parsed[name]
        assert entry["priced_items"] == 0
        assert all(i["unit_price"] is None and i["total"] is None for i in items)


def test_sub_descriptions_stay_with_their_item(parsed):
    _, items, entry = parsed["[NUMMER_001]_leer.X83"]
    assert entry["sub_descriptions"] > 0 and entry["description_references"] > 0
    assert entry["items"] == 248


@needs_twin
def test_twin_8209_item_numbers_are_the_same_set_in_both_readers(parsed, capsys):
    xml = dict((i["item_no"], i) for i in positions(parsed[TWIN_XML][1]))
    old = dict((i["item_no"], i) for i in positions(gaeb90.parse_file(os.path.join(DATA_DIR, TWIN_GAEB90))[1]))
    assert len(xml) == 159 and len(old) == 159
    assert set(xml) == set(old)
    assert [i["item_no"] for i in positions(parsed[TWIN_XML][1])] == list(old)
    equal = dict((field, sum(1 for number in xml if xml[number][field] == old[number][field]))
                 for field in ("short_text", "quantity", "unit", "kind", "section"))
    unequal = [number for number in xml if xml[number]["short_text"] != old[number]["short_text"]]
    # The organizers replaced names by placeholders, file by file; the mark
    # "PER" + digits (with or without "SON_" and brackets) is such a placeholder.
    placeholder = re.compile(r"PER(?:SON_)?\d+")
    with_placeholder = sum(1 for number in unequal
                           if placeholder.search(xml[number]["short_text"] + " " + old[number]["short_text"]))
    with capsys.disabled():
        print("\ntwin 8209.003 X83 / D83, 159 items: short texts equal %d, quantities equal %d, units equal %d, "
              "kinds equal %d, sections equal %d; of the %d short texts that differ, %d hold a name placeholder"
              % (equal["short_text"], equal["quantity"], equal["unit"], equal["kind"], equal["section"],
                 len(unequal), with_placeholder))
    assert equal["quantity"] == 159 and equal["unit"] == 159
    assert equal["kind"] == 159 and equal["section"] == 159
    assert 0 < equal["short_text"] <= 159
    assert with_placeholder == len(unequal)


def test_command_reads_all_gaeb_xml_files_of_data(tmp_path, capsys):
    out = str(tmp_path / "out")
    assert gaebxml.main([DATA_DIR, out]) == 0
    printed = capsys.readouterr().out
    entries = []
    for project in sorted(os.listdir(out)):
        assert sorted(os.listdir(os.path.join(out, project))) == ["items.json", "manifest.json"]
        with open(os.path.join(out, project, "manifest.json"), encoding="utf-8") as handle:
            manifest = json.load(handle)
        with open(os.path.join(out, project, "items.json"), encoding="utf-8") as handle:
            items = json.load(handle)
        contract.check("manifest", manifest)
        contract.check("items", items)
        assert all(i["project"] == project for i in items)
        assert sum(e["items"] for e in manifest) == len(positions(items))
        entries.extend(manifest)
    counts = dict((e["file"], e["items"]) for e in entries)
    for name, (_, count) in FILES.items():
        assert counts[name] == count
        assert "%s -> " % name in printed
    assert all(e["format"] == "gaebxml" for e in entries)
    assert printed.count("\n") == len(entries)


def test_command_reads_one_file(tmp_path):
    out = str(tmp_path / "out")
    assert gaebxml.main([os.path.join(DATA_DIR, "GAEB-[PROJEKT_004].X83"), out]) == 0
    (project,) = os.listdir(out)
    with open(os.path.join(out, project, "manifest.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)
    assert [(e["file"], e["items"]) for e in manifest] == [("GAEB-[PROJEKT_004].X83", 50)]


@needs_twin
def test_both_readers_write_the_twin_into_one_project_folder(tmp_path):
    out = str(tmp_path / "out")
    assert gaeb90.main([os.path.join(DATA_DIR, TWIN_GAEB90), out]) == 0
    assert gaebxml.main([os.path.join(DATA_DIR, TWIN_XML), out]) == 0
    (project,) = os.listdir(out)
    with open(os.path.join(out, project, "manifest.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)
    assert sorted((e["format"], e["items"]) for e in manifest) == [("gaeb90", 159), ("gaebxml", 159)]
    with open(os.path.join(out, project, "items.json"), encoding="utf-8") as handle:
        items = json.load(handle)
    assert len(positions(items)) == 318
    contract.check("items", items)
