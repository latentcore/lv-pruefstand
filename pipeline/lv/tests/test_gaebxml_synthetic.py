"""GAEB XML reader on small hand-written XML in both namespaces (no organizer text)."""
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import pytest  # noqa: E402

from pipeline.common import contract  # noqa: E402
from pipeline.lv import gaebxml, model  # noqa: E402

NS_31 = "http://www.gaeb.de/GAEB_DA_XML/200407"
NS_32 = "http://www.gaeb.de/GAEB_DA_XML/DA83/3.2"
VERSIONS = [("3.1", NS_31), ("3.2", NS_32)]


def text(short, long_text="<p><span>Long text.</span></p>"):
    return ("<Description><CompleteText><DetailTxt><Text>%s</Text></DetailTxt>"
            "<OutlineText><OutlTxt><TextOutlTxt><p><span>%s</span></p></TextOutlTxt></OutlTxt></OutlineText>"
            "</CompleteText></Description>" % (long_text, short))


def item(number, inner="<Qty>2.500</Qty><QU>m</QU>", short="Short", description=None, attributes=""):
    return '<Item ID="i%s" RNoPart="%s"%s>%s%s</Item>\n' % (
        number, number, attributes, inner, text(short) if description is None else description)


def section(number, label, inner):
    return ('<BoQCtgy ID="c%s" RNoPart="%s"><LblTx><p><span>%s</span></p></LblTx>\n<BoQBody>%s</BoQBody></BoQCtgy>\n'
            % (number, number, label, inner))


def items(*parts):
    return "<Itemlist>%s</Itemlist>" % "".join(parts)


def document(body, version="3.2", namespace=NS_32, project="P-XML-1", stage="83", award=""):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<GAEB xmlns="%s">\n'
            "<GAEBInfo><Version>%s</Version><VersDate>2000-01</VersDate><Date>2000-01-01</Date>"
            "<ProgSystem>hand</ProgSystem></GAEBInfo>\n"
            "<PrjInfo><NamePrj>%s</NamePrj><LblPrj>Test project</LblPrj><Cur>EUR</Cur></PrjInfo>\n"
            "<Award><DP>%s</DP><AwardInfo><Cur>EUR</Cur></AwardInfo>%s\n"
            "<BoQ><BoQInfo><Name>B1</Name><LblBoQ>Test trade</LblBoQ>"
            "<BoQBkdn><Type>BoQLevel</Type><Length>2</Length></BoQBkdn></BoQInfo>\n"
            "<BoQBody>%s</BoQBody></BoQ></Award></GAEB>\n"
            % (namespace, version, project, stage, award, body)).encode("utf-8")


def read(body, name="list.X83", **kwargs):
    project = kwargs.pop("read_project", None)
    return gaebxml.parse_bytes(document(body, **kwargs), name, project)


def positions(records):
    return [record for record in records if model.is_position(record)]


NESTED = section("01", "Outer", section("02", "Inner", items(
    item("0010"),
    item("0020", inner="<QU>psch</QU>", short="No quantity"),
    "<Remark><Description><CompleteText><DetailTxt><Text><p>Note text.</p></Text></DetailTxt>"
    "<OutlineText><OutlTxt><TextOutlTxt>Note</TextOutlTxt></OutlTxt></OutlineText></CompleteText>"
    "</Description></Remark>",
)) + items(item("0030", inner="<Qty>4</Qty><QU>St</QU>", short="Outer item")))


@pytest.mark.parametrize("version,namespace", VERSIONS)
def test_nested_sections_items_and_note_in_both_namespaces(version, namespace):
    project, records, entry = read(NESTED, version=version, namespace=namespace)
    assert project == "P-XML-1"
    assert [(r["kind"], r["item_no"], r["section"], r["short_text"]) for r in records] == [
        ("heading", "01", "", "Outer"),
        ("heading", "01.02", "01", "Inner"),
        ("normal", "01.02.0010", "01.02", "Short"),
        ("lump_sum", "01.02.0020", "01.02", "No quantity"),
        ("preliminary_note", "01.02", "01", "Note"),
        ("normal", "01.0030", "01", "Outer item"),
    ]
    first = records[2]
    assert (first["quantity"], first["unit"], first["long_text"]) == (2.5, "m", "Long text.")
    assert (first["format"], first["stage"], first["page"], first["trade"]) == ("gaebxml", "83", None, "Test trade")
    assert first["doc"] == "list.X83" and first["unit_price"] is None and first["total"] is None
    assert (records[5]["quantity"], records[5]["unit"]) == (4.0, "St")
    assert records[4]["long_text"] == "Note text."
    assert all(isinstance(r["line"], int) and r["line"] >= 1 for r in records)
    assert entry["gaeb_version"] == version and entry["namespace"] == namespace
    assert (entry["items"], entry["headings"], entry["preliminary_notes"]) == (3, 2, 1)
    assert entry["unparsed_lines"] == 0 and entry["unparsed_elements"] == {} and entry["warnings"] == []
    contract.check("items", records)
    contract.check("manifest", [entry])


def test_both_namespaces_give_the_same_records():
    old = read(NESTED, version="3.1", namespace=NS_31)[1]
    new = read(NESTED, version="3.2", namespace=NS_32)[1]
    assert old == new


def test_tags_are_read_by_local_name_with_a_prefix_and_without_a_namespace():
    plain = document(NESTED)
    prefixed = re.sub(rb"<(/?)(?=[A-Za-z])", rb"<\1g:", plain).replace(b" xmlns=", b" xmlns:g=")
    assert b"<g:Item " in prefixed and b"</g:GAEB>" in prefixed
    bare = plain.replace(b' xmlns="%s"' % NS_32.encode(), b"")
    expected = gaebxml.parse_bytes(plain, "list.X83")[1]
    assert gaebxml.parse_bytes(prefixed, "list.X83")[1] == expected
    assert gaebxml.parse_bytes(bare, "list.X83")[1] == expected
    assert gaebxml.parse_bytes(bare, "list.X83")[2]["namespace"] is None


def test_item_without_quantity_has_null_quantity_and_is_still_an_item():
    _, records, entry = read(items(item("1", inner="<QU>St</QU>"), item("2", inner="<Qty></Qty>"),
                                   item("3", inner="")))
    assert [(r["item_no"], r["quantity"], r["unit"], r["kind"]) for r in records] == [
        ("1", None, "St", "normal"), ("2", None, None, "normal"), ("3", None, None, "normal")]
    assert entry["items"] == 3 and entry["unparsed_lines"] == 0
    contract.check("items", records)


def test_inline_markup_becomes_plain_text_with_line_breaks():
    long_text = ("<p><span>First </span><span style=\"font-weight:bold\">bold</span><span> part</span></p>\n"
                 "    <p><span>Second<br/>third</span></p>\n"
                 "    <p/>\n"
                 "    <ul><li><span>one</span></li><li>two</li></ul>\n"
                 "    <p><span>a &amp; b &lt; c</span></p>\n"
                 "    <table><tr><td>cell 1</td><td>cell 2</td></tr></table>tail")
    _, records, entry = read(items(item("1", description=text("Two  <span>words</span>\n here", long_text))))
    assert records[0]["long_text"] == ("First bold part\nSecond\nthird\n\none\ntwo\na & b < c\ncell 1\ncell 2\ntail")
    assert records[0]["short_text"] == "Two words here"
    assert entry["unparsed_lines"] == 0


def test_text_complement_stays_in_the_running_text():
    long_text = ("<p><span>Make: </span></p>")
    complement = ('<TextComplement Kind="Bidder" MarkLbl="1"><ComplCaption><p><span>Maker </span></p></ComplCaption>'
                  "<ComplBody><p><span>'....'</span></p></ComplBody><ComplTail><p><span> (or equal)</span></p>"
                  "</ComplTail></TextComplement>")
    description = ("<Description><CompleteText><ComplTSB>1</ComplTSB><DetailTxt><Text>%s</Text>%s"
                   "<Text><p>After.</p></Text></DetailTxt><OutlineText><OutlTxt><TextOutlTxt>Pump</TextOutlTxt>"
                   "</OutlTxt></OutlineText></CompleteText></Description>" % (long_text, complement))
    _, records, entry = read(items(item("1", description=description)))
    assert records[0]["long_text"] == "Make:\nMaker\n'....'\n (or equal)\nAfter."
    assert entry["text_complements"] == 1 and entry["skipped_elements"]["ComplTSB"] == 1
    assert entry["unparsed_lines"] == 0


def test_unknown_element_is_counted_named_and_not_read():
    body = section("01", "S", items(
        item("1", inner="<Qty>1</Qty><QU>m</QU><Mystery><Qty>9</Qty>hidden words</Mystery>"),
        "<Strange>x</Strange>",
        item("2", description=text("Two", "<p>a<blink>b</blink>c</p>")),
    ) + "<Odd/>")
    _, records, entry = read(body, award="<Extra>1</Extra>")
    assert [(r["item_no"], r["quantity"], r["long_text"]) for r in positions(records)] == [
        ("01.1", 1.0, "Long text."), ("01.2", 2.5, "ac")]
    assert entry["items"] == 2
    assert entry["unparsed_lines"] == 5
    assert entry["unparsed_elements"] == {"Extra": 1, "Mystery": 1, "Odd": 1, "Strange": 1, "blink": 1}
    assert len(entry["unparsed_element_lines"]) == 5
    warnings = "\n".join(entry["warnings"])
    assert "Mystery (line" in warnings and "item 01.1" in warnings
    assert "blink (line" in warnings and "item 01.2" in warnings
    assert "5 elements not read" in warnings
    assert "hidden words" not in json.dumps(records)
    contract.check("manifest", [entry])


def test_unknown_element_at_every_level_is_counted():
    raw = document(items(item("1"))).replace(b"<PrjInfo>", b"<Top/><PrjInfo><Inside/>") \
        .replace(b"<GAEBInfo>", b"<GAEBInfo><New/>").replace(b"<BoQInfo>", b"<BoQInfo><More/>") \
        .replace(b"<BoQ>", b"<BoQ><Side/>").replace(b"<CompleteText>", b"<CompleteText><Part/>") \
        .replace(b"<OutlTxt>", b"<OutlTxt><In/>").replace(b"<DetailTxt>", b"<DetailTxt><Deep/>") \
        .replace(b"<Description>", b"<Description><Else/>").replace(b"<OutlineText>", b"<OutlineText><Out/>")
    _, records, entry = gaebxml.parse_bytes(raw, "list.X83")
    assert entry["unparsed_elements"] == dict((name, 1) for name in (
        "Deep", "Else", "In", "Inside", "More", "New", "Out", "Part", "Side", "Top"))
    assert entry["unparsed_lines"] == 10 and entry["items"] == 1
    assert (records[0]["short_text"], records[0]["long_text"]) == ("Short", "Long text.")


def test_only_the_first_fifty_unread_element_lines_are_listed():
    _, _, entry = read(items(*[item(str(n), inner="<Qty>1</Qty><Nope/>\n") for n in range(1, 61)]))
    assert entry["unparsed_lines"] == 60 and entry["unparsed_elements"] == {"Nope": 60}
    assert len(entry["unparsed_element_lines"]) == 50


def test_quantity_that_is_not_a_number_is_counted_and_left_empty():
    _, records, entry = read(items(item("1", inner="<Qty>about ten</Qty><QU>m</QU>"),
                                   item("2", inner="<Qty>NaN</Qty><QU>m</QU>"),
                                   item("3", inner="<Qty>1,5</Qty><QU>m</QU>")))
    assert [r["quantity"] for r in records] == [None, None, None]
    assert entry["unparsed_lines"] == 3 and entry["unparsed_elements"] == {"Qty": 3}
    assert sum("the quantity is not a number" in w for w in entry["warnings"]) == 3
    assert "about ten" not in "\n".join(entry["warnings"])


def test_entity_is_not_resolved_and_is_counted():
    raw = document(items(item("1", description=text("Short", "<p>a&secret;b</p>"))))
    raw = raw.replace(b"?>\n", b'?>\n<!DOCTYPE GAEB [<!ENTITY secret SYSTEM "file:///etc/hostname">'
                                b'<!ENTITY big "xxxxxxxxxx">]>\n', 1)
    _, records, entry = gaebxml.parse_bytes(raw, "list.X83")
    assert records[0]["long_text"] == "ab"
    assert entry["unparsed_elements"] == {"#entity": 1} and entry["unparsed_lines"] == 1


def test_comments_and_processing_instructions_are_passed_over():
    body = "<!-- c -->" + items("<!-- c -->", item("1", inner="<?pi x?><Qty>3</Qty><!-- c --><QU>m</QU>",
                                                   description=text("A<!-- c -->B", "<p>x<!-- c -->y<?pi z?>z</p>")))
    _, records, entry = read(body)
    assert (records[0]["short_text"], records[0]["long_text"], records[0]["quantity"]) == ("AB", "xyz", 3.0)
    assert entry["unparsed_lines"] == 0 and entry["warnings"] == []


def test_value_around_a_comment_is_read_whole():
    inner = "<Qty>1<!-- c -->2<?pi x?>.5</Qty><QU>m<!-- c -->2</QU><LumpSumItem>Y<!-- c -->es</LumpSumItem>"
    raw = document(items(item("1", inner=inner))).replace(b"<DP>83</DP>", b"<DP>8<!-- c -->3</DP>")
    _, records, entry = gaebxml.parse_bytes(raw, "list.X83")
    assert (records[0]["quantity"], records[0]["unit"], records[0]["kind"]) == (12.5, "m2", "lump_sum")
    assert entry["unparsed_lines"] == 0 and entry["warnings"] == []


def test_element_inside_a_value_is_counted():
    _, records, entry = read(items(item("1", inner="<Qty>1<Odd>7</Odd>2</Qty><QU>m</QU>")))
    assert records[0]["quantity"] == 12.0
    assert entry["unparsed_lines"] == 1 and entry["unparsed_elements"] == {"Odd": 1}


@pytest.mark.parametrize("inner,unit,kind", [
    ("", "m", "normal"),
    ("<LumpSumItem>Yes</LumpSumItem>", "St", "lump_sum"),
    ("<LumpSumItem>No</LumpSumItem>", "St", "normal"),
    ("", "psch", "lump_sum"),
    ("<Provis>WithoutTotal</Provis>", "m", "optional"),
    ("<Provis>WithTotal</Provis><LumpSumItem>Yes</LumpSumItem>", "psch", "optional"),
    ("<ALNGroupNo>1</ALNGroupNo><ALNSerNo>1</ALNSerNo>", "m", "alternative"),
    ("<ALNGroupNo>1</ALNGroupNo><ALNSerNo>0</ALNSerNo>", "m", "normal"),
    ("<ALNSerNo>2</ALNSerNo><Provis>WithoutTotal</Provis>", "m", "alternative"),
])
def test_kind_from_the_item_flags_and_the_unit(inner, unit, kind):
    _, records, entry = read(items(item("1", inner="%s<Qty>1</Qty><QU>%s</QU>" % (inner, unit))))
    assert records[0]["kind"] == kind
    assert entry["unparsed_lines"] == 0 and entry["warnings"] == []


def test_flag_with_a_value_the_reader_does_not_know_is_warned():
    _, records, entry = read(items(item("1", inner="<LumpSumItem>Maybe</LumpSumItem><Qty>1</Qty><QU>m</QU>"),
                                   item("2", inner="<Provis>Other</Provis><Qty>1</Qty><QU>m</QU>")))
    assert [r["kind"] for r in records] == ["normal", "optional"]
    assert any("1 (LumpSumItem Maybe)" in w and "2 (Provis Other)" in w for w in entry["warnings"])


def test_prices_are_read_by_code_and_checked_without_showing_one():
    body = items(item("1", inner="<Qty>2.500</Qty><QU>m</QU><UP>4.20</UP><IT>10.50</IT>"),
                 item("2", inner="<Qty>2</Qty><QU>m</QU><UP>3.00</UP><IT>7.77</IT>"),
                 item("3", inner="<QU>m</QU><UP>3.00</UP><IT>6.00</IT>"))
    _, records, entry = read(body, name="offer.X84")
    assert [(r["unit_price"], r["total"]) for r in records] == [(4.2, 10.5), (3.0, 7.77), (3.0, 6.0)]
    assert entry["stage"] == "84" and entry["priced_items"] == 3
    assert entry["price_check"] == {"equal": 1, "not_equal": 1, "no_quantity": 1}
    warnings = "\n".join(entry["warnings"])
    assert "not the total for 1 items: 2" in warnings and "1 priced items have no quantity" in warnings
    for price in ("4.2", "10.5", "7.77", "3.0", "6.0"):
        assert price not in warnings


@pytest.mark.parametrize("name,stage", [("a.X83", "83"), ("a.x83", "83"), ("a.X84", "84"), ("a.x86", "86")])
def test_stage_comes_from_the_file_type(name, stage):
    _, records, entry = read(items(item("1")), name=name, stage=stage)
    assert entry["stage"] == stage and records[0]["stage"] == stage and entry["warnings"] == []


def test_stage_in_the_file_that_differs_from_the_file_type_is_warned():
    _, records, entry = read(items(item("1")), name="a.X83", stage="84")
    assert records[0]["stage"] == "83"
    assert any("stage 84 (DP)" in w for w in entry["warnings"])


@pytest.mark.parametrize("name", ["a.D83", "a.xml", "a.X81", "a"])
def test_other_file_types_are_refused(name):
    with pytest.raises(gaebxml.GaebXmlError):
        gaebxml.parse_bytes(document(items(item("1"))), name)


def test_broken_xml_and_another_root_are_refused_without_showing_content():
    with pytest.raises(gaebxml.GaebXmlError) as broken:
        gaebxml.parse_bytes(b"<GAEB><Award>secret words", "a.X83")
    assert "secret" not in str(broken.value) and "not well-formed" in str(broken.value)
    with pytest.raises(gaebxml.GaebXmlError) as other:
        gaebxml.parse_bytes(b"<Other/>", "a.X83")
    assert "root element is Other" in str(other.value)


def test_text_before_the_list_is_a_note_without_a_number():
    award = ("<AddText><OutlineAddText><p>Before</p></OutlineAddText>"
             "<DetailAddText><p>General <span>terms</span>.</p></DetailAddText></AddText>"
             "<AddText><OutlineAddText/><DetailAddText/></AddText>")
    _, records, entry = read(items(item("1")), award=award)
    assert [(r["kind"], r["item_no"], r["section"], r["short_text"], r["long_text"]) for r in records[:1]] == [
        ("preliminary_note", "", "", "Before", "General terms.")]
    assert len(records) == 2 and entry["preliminary_notes"] == 1
    assert any("has no text; not written" in w for w in entry["warnings"])


def test_sub_descriptions_and_shared_description():
    sub = "<SubDescr><SubDNo>%s</SubDNo><UPBkdn>No</UPBkdn>%s</SubDescr>"
    inner = ("<RefDescr>Ref</RefDescr><RefPerfNo>7</RefPerfNo><SumDescr>Yes</SumDescr><UPBkdn>No</UPBkdn>"
             "<Qty>1</Qty><QU>St</QU>" + sub % ("1", text("Part A", "<p>Text A</p>"))
             + sub % ("2", text("Part B", "<p>Text B</p>")))
    shared = "<PerfDescr><PerfNo>7</PerfNo><PerfLbl>Shared</PerfLbl>%s</PerfDescr>" % text("", "<p>For all.</p>")
    _, records, entry = read(section("01", "S", items(shared, item("1", inner=inner),
                                                      item("2", inner="<RefDescr>Rep</RefDescr><Qty>1</Qty><QU>m</QU>"))))
    note, first = records[1], records[2]
    assert (note["kind"], note["item_no"], note["short_text"], note["long_text"]) == (
        "preliminary_note", "01", "Shared", "For all.")
    assert first["long_text"] == "Long text.\n\n1 Part A\nText A\n\n2 Part B\nText B"
    assert (entry["sub_descriptions"], entry["description_references"], entry["repeat_descriptions"]) == (2, 1, 1)
    assert entry["items"] == 2 and entry["unparsed_lines"] == 0 and entry["warnings"] == []


def test_item_index_number_twice_and_missing_number_are_handled_in_the_open():
    body = section("01", "S", items(item("5"), item("5", attributes=' RNoIndex="a"'), item("5"),
                                    '<Item ID="x"><Qty>1</Qty><QU>m</QU></Item>',
                                    item("6", attributes=' Odd="1"')))
    _, records, entry = read(body)
    assert [r["item_no"] for r in positions(records)] == ["01.5", "01.5.a", "01.5", "01", "01.6"]
    warnings = "\n".join(entry["warnings"])
    assert "item number 01.5 stands twice" in warnings
    assert "has no number (RNoPart)" in warnings
    assert "attributes the reader does not use: Odd" in warnings
    assert entry["items"] == 5


def test_images_and_page_breaks_in_a_text_are_skipped_and_counted():
    long_text = '<p>before<image Name="a.jpg" Type="jpg">QUJDRA==</image>after</p><page/><p>next</p>'
    _, records, entry = read(items(item("1", description=text("Short", long_text))))
    assert records[0]["long_text"] == "beforeafter\nnext"
    assert entry["skipped_elements"]["image"] == 1 and entry["skipped_elements"]["page"] == 1
    assert entry["unparsed_lines"] == 0


def test_missing_project_and_missing_list_are_warned():
    raw = document(items(item("1"))).replace(b"<NamePrj>P-XML-1</NamePrj>", b"")
    project, _, entry = gaebxml.parse_bytes(raw, "list 7.X83")
    assert project and any("no project number in the file" in w for w in entry["warnings"])
    empty = b'<GAEB xmlns="%s"><GAEBInfo><Version>3.2</Version></GAEBInfo></GAEB>' % NS_32.encode()
    _, records, entry = gaebxml.parse_bytes(empty, "a.X83")
    assert records == [] and entry["items"] == 0
    assert any("no Award element" in w for w in entry["warnings"])


def test_manifest_entry_has_the_hash_of_the_bytes():
    raw = document(NESTED)
    entry = gaebxml.parse_bytes(raw, "list.X83")[2]
    assert entry["sha256"] == hashlib.sha256(raw).hexdigest()
    assert (entry["doc"], entry["file"], entry["format"], entry["pages"]) == ("list.X83", "list.X83", "gaebxml", None)


def write(folder, name, raw):
    path = os.path.join(str(folder), name)
    with open(path, "wb") as handle:
        handle.write(raw)
    return path


def load(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as handle:
        return json.load(handle)


def test_command_reads_a_folder_and_writes_one_folder_per_project(tmp_path, capsys):
    data, out = tmp_path / "data", str(tmp_path / "out")
    data.mkdir()
    priced = items(item("1", inner="<Qty>2.500</Qty><QU>m</QU><UP>4.20</UP><IT>10.50</IT>"))
    write(data, "list.X83", document(NESTED, version="3.1", namespace=NS_31))
    write(data, "offer.x84", document(priced, stage="84"))
    write(data, "other.X83", document(items(item("1")), project="P-XML-2"))
    write(data, "twin.D83", b"not read by this reader")
    write(data, "notes.xml", b"<notes/>")
    assert gaebxml.main([str(data), out]) == 0
    assert sorted(os.listdir(out)) == ["P-XML-1", "P-XML-2"]
    manifest = load(out, "P-XML-1", "manifest.json")
    records = load(out, "P-XML-1", "items.json")
    assert [(e["doc"], e["stage"], e["items"]) for e in manifest] == [("list.X83", "83", 3), ("offer.x84", "84", 1)]
    assert [r["doc"] for r in records] == ["list.X83"] * 6 + ["offer.x84"]
    assert [e["doc"] for e in load(out, "P-XML-2", "manifest.json")] == ["other.X83"]
    contract.check("items", records)
    contract.check("manifest", manifest)
    printed = capsys.readouterr().out
    assert printed.count("\n") == 3
    assert "offer.x84 -> %s: 1 items" % os.path.join(out, "P-XML-1") in printed
    assert "priced 1: equal 1, not equal 0, no quantity 0" in printed
    assert "4.2" not in printed and "10.5" not in printed


def test_command_reads_one_file_and_takes_a_project_name(tmp_path):
    out = str(tmp_path / "out")
    path = write(tmp_path, "list.X83", document(NESTED))
    assert gaebxml.main([path, out, "--project", "other"]) == 0
    assert os.listdir(out) == ["other"]
    records = load(out, "other", "items.json")
    assert records[0]["project"] == "other" and len(records) == 6
    assert gaebxml.main([path, out, "--project", "other"]) == 0
    assert len(load(out, "other", "items.json")) == 6
    assert len(load(out, "other", "manifest.json")) == 1


def test_command_keeps_the_gaeb90_twin_already_in_the_project_folder(tmp_path):
    out = str(tmp_path / "out")
    twin = model.make_item(doc="list.D83", project="P-XML-1", trade="", format="gaeb90", stage="83",
                           item_no="01.02.0010", kind="normal", short_text="Short", line=3)
    entry = model.make_manifest_entry(doc="list.D83", file="list.D83", sha256="0" * 64, format="gaeb90",
                                      stage="83", items=[twin])
    model.write_project(out, "P-XML-1", [twin], [entry])
    assert gaebxml.main([write(tmp_path, "list.X83", document(NESTED)), out]) == 0
    assert [e["doc"] for e in load(out, "P-XML-1", "manifest.json")] == ["list.D83", "list.X83"]
    assert [r["doc"] for r in load(out, "P-XML-1", "items.json")] == ["list.D83"] + ["list.X83"] * 6


def test_command_says_so_when_there_is_nothing_to_read(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert gaebxml.main([str(empty), str(tmp_path / "out")]) == 1
    assert gaebxml.main([str(tmp_path / "missing.X83"), str(tmp_path / "out")]) == 2
    other = write(tmp_path, "a.pdf", b"x")
    assert gaebxml.main([other, str(tmp_path / "out")]) == 2
    broken = write(tmp_path, "b.X83", b"<GAEB>")
    assert gaebxml.main([broken, str(tmp_path / "out")]) == 2
    assert not os.path.exists(str(tmp_path / "out"))
    assert "error:" in capsys.readouterr().err
