"""Real-data tests of the W13 "done" criterion. They need the organizer
files in data/ (or in the folder named by LV_DATA_DIR) and Poppler's
pdftotext; they are skipped when one of the two is missing. Only counts,
item numbers and "equal / not equal" are asserted; no amount is printed."""
import json
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "pipeline", "pdf"))

import pytest  # noqa: E402

import pdfio  # noqa: E402
from pipeline.common import quotes  # noqa: E402
from pipeline.diff import pairs  # noqa: E402
from pipeline.diff import pdftext  # noqa: E402
from pipeline.diff import report  # noqa: E402
from pipeline.diff import run  # noqa: E402
from pipeline.diff import text as textcmp  # noqa: E402
from pipeline.lv import model  # noqa: E402

DATA = os.environ.get("LV_DATA_DIR") or os.path.join(REPO, "data")
RECORD = os.path.join(REPO, "docs", "TWINS.md")

pytestmark = [
    pytest.mark.skipif(bool(pairs.missing_files(DATA)), reason="organizer files missing in %s" % DATA),
    pytest.mark.skipif(not pdfio.pdftotext_is_poppler(), reason="Poppler's pdftotext is not on PATH"),
]


@pytest.fixture(scope="module")
def fresh():
    summary, items = pairs.run_all(DATA)
    return {"summary": summary, "items": items}


def pair(fresh, pair_id):
    entries = fresh["summary"]["pairs"] + fresh["summary"]["text_pairs"]
    return next(entry for entry in entries if entry["id"] == pair_id)


def equal_counts(result, names):
    return [(result["fields"][name]["compared"], result["fields"][name]["equal"]) for name in names]


def test_every_number_of_the_record_comes_from_a_fresh_run(fresh):
    with open(RECORD, encoding="utf-8") as handle:
        committed = handle.read()
    assert report.render(fresh["summary"]) == committed, \
        "docs/TWINS.md is not what `python -m pipeline.diff.pairs` writes now"


def test_t1_offer_pdf_against_d84(fresh):
    result = pair(fresh, "t1_offer_pdf_d84")["result"]
    assert (result["a"]["items"], result["b"]["items"], result["matching"]["both"]) == (274, 274, 274)
    assert result["matching"]["only_a"] == [] and result["matching"]["only_b"] == []
    assert equal_counts(result, ("quantity", "unit", "unit_price", "total")) == [(274, 274)] * 4
    assert result["fields"]["short_text"]["compared"] == 0 and result["b"]["with_short_text"] == 0


def test_t2_print_against_x83_uses_the_long_text(fresh):
    result = pair(fresh, "t2_print_pdf_x83")["result"]
    assert result["text_map"] == "a_all_to_b_long"
    assert (result["a"]["items"], result["b"]["items"], result["matching"]["both"]) == (50, 50, 50)
    assert equal_counts(result, ("quantity", "unit")) == [(50, 50)] * 2
    field = result["fields"]["text"]
    assert field["compared"] == 50 and field[textcmp.DIFFERS] == 0 and field[textcmp.START] == 0
    assert field["equal"] + field[textcmp.ANONYMIZED_ONE] + field[textcmp.ANONYMIZED_BOTH] == 50
    plain = pair(fresh, "t2_print_pdf_x83_fields")["result"]["fields"]
    assert plain["short_text"]["equal"] < 10 and plain["long_text"]["equal"] == 0


def test_t3_format_twin_matches_the_w12_check(fresh):
    result = pair(fresh, "t3_x83_d83")["result"]
    assert (result["a"]["items"], result["b"]["items"], result["matching"]["by_number"]) == (159, 159, 159)
    assert equal_counts(result, ("quantity", "unit")) == [(159, 159)] * 2
    short = result["fields"]["short_text"]
    assert (short["equal"], short[textcmp.ANONYMIZED_BOTH], short[textcmp.ANONYMIZED_ONE]) == (112, 32, 15)
    assert short[textcmp.DIFFERS] == 0 and result["fields"]["long_text"][textcmp.DIFFERS] == 0


def test_38_item_hypothesis_by_number_and_text(fresh):
    decision = fresh["summary"]["hypothesis_38"]
    assert decision["verdict"] == "confirmed" and len(decision["runs"]) == 2
    for decided in decision["runs"]:
        assert (decided["tendered"], decided["ordered"], decided["in_both"]) == (159, 197, 159)
        assert len(decided["added"]) == 38 and decided["removed"] == [] and decided["renumbered"] == []
        assert decided["changed"] == {"quantity": 0, "unit": 0, "text": 0, "price": 0}
        assert decided["order_items_quantity_zero_and_total_zero"] == 38
        assert decided["zero_items_are_the_added_items"] is True
        assert decided["added_with_a_title_of_the_tender"] == 0
        assert all(number.startswith("8.") for number in decided["added"])
    assert decision["runs"][0]["added"] == decision["runs"][1]["added"]
    order = fresh["items"]["hem_d86"]
    tender = set(model.item_no_key(entry["item_no"]) for entry in fresh["items"]["hem_d83"])
    by_hand = [entry["item_no"] for entry in order
               if model.is_position(entry) and model.item_no_key(entry["item_no"]) not in tender]
    assert by_hand == decision["runs"][0]["added"]


def test_stbalv_offer_against_order(fresh):
    result = pair(fresh, "stbalv_offer_d84_order_d86")["result"]
    assert (result["a"]["items"], result["b"]["items"], result["matching"]["by_number"]) == (249, 249, 249)
    assert result["stage"]["added"] == [] and result["stage"]["removed"] == []
    assert equal_counts(result, ("unit_price", "total")) == [(249, 249)] * 2
    assert result["a"]["placeholder_numbers"] == result["b"]["placeholder_numbers"]
    assert len(result["a"]["placeholder_numbers"]) == 1


def test_t4_nummer001_against_stbalv(fresh):
    d86 = pair(fresh, "t4_nummer001_x83_stbalv_d86")
    result = d86["result"]
    assert d86["verdict"] == pairs.HOLDS
    assert (result["a"]["items"], result["b"]["items"], result["matching"]["both"]) == (248, 249, 248)
    assert result["matching"]["by_number"] == 247 and len(result["matching"]["by_position"]) == 1
    assert result["matching"]["by_position"][0]["b"] == result["b"]["placeholder_numbers"][0]
    assert len(result["matching"]["only_b"]) == 1 and result["matching"]["only_a"] == []
    assert equal_counts(result, ("quantity", "unit")) == [(248, 248)] * 2
    assert result["from_start"]["same_from_start"] >= pairs.T4_FIRST_ITEMS
    d84 = pair(fresh, "t4_nummer001_x83_stbalv_d84")
    assert d84["verdict"] == pairs.UNDECIDED
    assert d84["result"]["from_start"]["pairs_with_text_or_quantity"] == 0


def test_t5_titles_in_the_pdf_text(fresh):
    leer = pair(fresh, "t5_leer_pdf_nummer001_x83")
    assert leer["verdict"] == pairs.HOLDS and leer["result"]["items"] == 248
    assert leer["result"]["found_total"] >= 0.9 * leer["result"]["searchable"]
    hem = pair(fresh, "t5_hem_pdf_8209_d83")
    assert hem["verdict"] == pairs.HOLDS and hem["result"]["items"] == 159
    for control in ("t5_control_leer_pdf_8209_x83", "t5_control_hem_pdf_nummer001_x83"):
        found = pair(fresh, control)["result"]
        assert found["found_total"] < 0.05 * found["searchable"]
    added = pair(fresh, "t5_hem_pdf_lv24069_d86")["added_items"]
    assert sum(added.values()) == 38 and added[pdftext.FOUND_AS_WRITTEN] == 0
    for entry in fresh["summary"]["text_pairs"]:
        found = entry["result"]
        assert found["found_total"] == sum(found["counts"][cls] for cls in pdftext.FOUND)
        assert found["items"] == sum(found["counts"].values())
        assert found["searchable"] == found["items"] - found["counts"][pdftext.NOT_SEARCHABLE]
        assert found["in_order"] <= found["found_total"]


def test_t5_titles_found_only_with_anonymization(fresh):
    """05.01.38 to 05.01.40 are found as 05.01.41 is: the PDF holds one
    placeholder for the placeholder the title begins with and its word."""
    for pair_id, only in (("t5_hem_pdf_8209_x83", 25), ("t5_hem_pdf_8209_d83", 43),
                          ("t5_hem_pdf_lv24069_d86", 44)):
        found = pair(fresh, pair_id)["result"]
        assert found["counts"][pdftext.FOUND_ANONYMIZED] == only
        for number in ("05.01.38", "05.01.39", "05.01.40", "05.01.41"):
            assert number in found["numbers"][pdftext.FOUND_ANONYMIZED]
            assert number in found["placeholder_title"]
        assert set(found["placeholder_title"]) <= set(found["numbers"][pdftext.FOUND_ANONYMIZED])
    # a plain first word (X83) against a placeholder of the PDF is not found;
    # the D83 holds a placeholder in that word and is found
    assert "05.01.1" in pair(fresh, "t5_hem_pdf_8209_x83")["result"]["numbers"][pdftext.NOT_FOUND]
    d83 = pair(fresh, "t5_hem_pdf_8209_d83")
    assert "05.01.1" in d83["result"]["placeholder_title"]
    assert d83["verdict"] == pairs.HOLDS and pair(fresh, "t5_hem_pdf_8209_x83")["verdict"] == pairs.UNDECIDED
    assert len(d83["result"]["placeholder_title"]) == 40 and d83["result"]["found_total"] == 154
    with open(RECORD, encoding="utf-8") as handle:
        record = handle.read()
    assert ("rests on the 43 titles found only with anonymization allowed (43 of the 154 found titles; "
            "without them 111 of 155 searchable titles, 71.6 percent") in record
    assert "in 40 of these 43 the title in the PDF begins with a placeholder" in record
    assert record.count("How strong the answer is:") == 1


def test_t5_page_count_is_the_page_count_of_the_pdf(fresh):
    """The page count comes from the PDF itself (PyMuPDF), not from the text."""
    pymupdf = pytest.importorskip("pymupdf")
    for entry in fresh["summary"]["text_pairs"]:
        path = os.path.join(DATA, pairs.PDFS[entry["pdf"]])
        with pymupdf.open(path) as document:
            assert entry["result"]["pages"] == document.page_count
            assert entry["result"]["last_page"] is None or entry["result"]["last_page"] <= document.page_count
    assert pair(fresh, "t5_leer_pdf_nummer001_x83")["result"]["pages"] == 78
    assert pair(fresh, "t5_hem_pdf_8209_x83")["result"]["pages"] == 136


def test_t5_found_as_written_is_letter_for_letter(fresh):
    """Recount "found as written" with plain string search on the page text
    of pdfio, without pdftext's page strings."""
    for pair_id, expected in (("t5_leer_pdf_nummer001_x83", 236), ("t5_hem_pdf_8209_x83", 114),
                              ("t5_hem_pdf_8209_d83", 111)):
        entry = pair(fresh, pair_id)
        text = pdfio.extract_text(os.path.join(DATA, pairs.PDFS[entry["pdf"]]))
        whole = "".join(quotes.normalize(text).split())
        count = 0
        for record in fresh["items"][entry["list"]]:
            title = "".join(quotes.normalize(record.get("short_text")).split())
            if model.is_position(record) and title in whole \
                    and len(pdftext.search_string(title).replace(pdftext.WILD, "")) >= pdftext.MIN_LENGTH:
                count += 1
        assert entry["result"]["counts"][pdftext.FOUND_AS_WRITTEN] == count == expected


def test_nothing_written_holds_a_price(fresh):
    """No float at all in the summary (counts are whole numbers; no quantity
    changed in these pairs), and no unit price or total of any file in the
    record."""
    def floats(node):
        if isinstance(node, float):
            yield node
        elif isinstance(node, dict):
            for value in node.values():
                yield from floats(value)
        elif isinstance(node, list):
            for value in node:
                yield from floats(value)
    assert list(floats(fresh["summary"])) == []
    with open(RECORD, encoding="utf-8") as handle:
        record = handle.read()
    tokens = set(re.findall(r"(?<![\d.,])\d+[.,]\d{2}(?![\d.,])", record))
    prices = set()
    for entries in fresh["items"].values():
        for entry in entries:
            for name in ("unit_price", "total"):
                if entry.get(name):
                    prices.add("%.2f" % entry[name])
                    prices.add(("%.2f" % entry[name]).replace(".", ","))
    assert len(prices) > 500
    assert tokens & prices == set()


def test_both_commands_on_the_real_files(tmp_path, capsys):
    out = tmp_path / "diff"
    record = tmp_path / "TWINS.md"
    assert pairs.main(["--data", DATA, "--out", str(out), "--doc", str(record)]) == 0
    with open(RECORD, encoding="utf-8") as handle:
        assert record.read_text(encoding="utf-8") == handle.read()
    names = sorted(name for name in os.listdir(out) if name.endswith(".json"))
    assert names == sorted([entry[0] + ".json" for entry in pairs.PAIRS + pairs.TEXT_PAIRS]
                           + ["summary.json"])
    single = tmp_path / "single.json"
    assert run.main([str(out / "items" / "hem_d83.json"), str(out / "items" / "hem_d86.json"),
                     str(single), "--mode", "stage"]) == 0
    with open(single, encoding="utf-8") as handle:
        result = json.load(handle)
    with open(out / "t3_tender_d83_order_d86.json", encoding="utf-8") as handle:
        assert result == json.load(handle)
    assert len(result["stage"]["added"]) == 38
    printed = capsys.readouterr().out
    assert "38-item hypothesis: confirmed" in printed and not re.search(r"\d[.,]\d{2}\b", printed)
