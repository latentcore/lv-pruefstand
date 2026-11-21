"""The 38-item decision, the T4 and T5 rules and the written record, on
hand-written items (no organizer data)."""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from diff_items import heading, item, order, tender  # noqa: E402
from pipeline.diff import compare  # noqa: E402
from pipeline.diff import pairs  # noqa: E402
from pipeline.diff import pdftext  # noqa: E402
from pipeline.diff import report  # noqa: E402

PRICES = (1234.56, 7890.12, 4455.66)


def big_tender(count=159):
    out = [heading("01", "Rohre")]
    for n in range(1, count + 1):
        out.append(item("01.%04d" % n, "Rohr Typ %d liefern" % n, "Rohr Typ %d liefern und verlegen." % n,
                        float(n), "m"))
    return out


def big_order(count=159, added=38, drop=(), renumber=None):
    out = [heading("1", "Rohre", doc="B.D86")]
    for n in range(1, count + 1):
        if n in drop:
            continue
        number = "1.%d" % n if n != renumber else "9.%d" % n
        out.append(item(number, "Rohr Typ %d liefern" % n, "Rohr Typ %d liefern und verlegen." % n,
                        float(n), "m", doc="B.D86", unit_price=PRICES[0], total=PRICES[0] * n))
    out.append(heading("8", "Nachträge", doc="B.D86"))
    for n in range(1, added + 1):
        out.append(item("8.%d" % n, "Nachtrag Leistung %d" % n, "", 0.0, None, doc="B.D86",
                        unit_price=PRICES[1], total=0.0))
    return out


def decide(order_items):
    return pairs.hypothesis_38([("t3_tender_d83_order_d86",
                                 compare.compare(big_tender(), order_items, "stage"))])


def test_hypothesis_confirmed_when_38_are_added_and_none_removed_or_renumbered():
    result = decide(big_order())
    run = result["runs"][0]
    assert result["verdict"] == "confirmed"
    assert (run["tendered"], run["ordered"], run["in_both"]) == (159, 197, 159)
    assert run["added"] == ["8.%d" % n for n in range(1, 39)]
    assert run["zero_items_are_the_added_items"] is True
    assert run["added_with_quantity_zero"] == 38 and run["added_without_unit"] == 38
    assert run["added_sections"] == ["8"]
    assert run["sections_only_in_order"] == [{"item_no": "8", "title": "Nachträge"}]


def test_hypothesis_refuted_when_an_item_was_removed():
    result = decide(big_order(added=39, drop=(7,)))
    assert result["verdict"] == "refuted"
    assert result["runs"][0]["ordered"] == 197 and result["runs"][0]["removed"] == ["01.0007"]
    assert len(result["runs"][0]["added"]) == 39


def test_hypothesis_refuted_when_an_item_was_only_renumbered():
    result = decide(big_order(added=38, renumber=5))
    run = result["runs"][0]
    assert result["verdict"] == "refuted"
    assert run["renumbered"] == [{"a": "01.0005", "b": "9.5"}] and len(run["added"]) == 38


def test_hypothesis_refuted_when_the_counts_are_other_counts():
    assert decide(big_order(added=37))["verdict"] == "refuted"
    assert pairs.hypothesis_38([("x", compare.compare(tender(), order(), "stage"))])["verdict"] == "refuted"


def test_zero_quantity_items_that_are_not_the_added_ones_are_seen():
    b = big_order()
    b[3]["quantity"] = 0.0
    run = decide(b)["runs"][0]
    assert run["zero_items_are_the_added_items"] is False and run["order_items_quantity_zero"] == 39


def test_t4_rule():
    same = compare.compare(big_tender(20), big_order(20, added=0), "stage")
    assert pairs.t4_verdict(same) == pairs.HOLDS
    early = big_order(20, added=0)
    early[3]["quantity"] = 99.0
    assert pairs.t4_verdict(compare.compare(big_tender(20), early, "stage")) == pairs.DOES_NOT_HOLD
    bare = [item(entry["item_no"], "", "", None, None, doc="B.D84") for entry in big_order(20, added=0)[1:]]
    assert pairs.t4_verdict(compare.compare(big_tender(20), bare, "stage")) == pairs.UNDECIDED


def test_t5_rule():
    def found(total, searchable=100, in_order=None):
        return {"searchable": searchable, "found_total": total,
                "in_order": total if in_order is None else in_order}
    assert pairs.t5_verdict(found(95)) == pairs.HOLDS
    assert pairs.t5_verdict(found(90)) == pairs.HOLDS
    assert pairs.t5_verdict(found(89)) == pairs.UNDECIDED
    assert pairs.t5_verdict(found(95, in_order=60)) == pairs.UNDECIDED
    assert pairs.t5_verdict(found(49)) == pairs.DOES_NOT_HOLD
    assert pairs.t5_verdict(found(0, searchable=0)) == pairs.UNDECIDED


def synthetic_summary():
    """Every file key of pairs.FILES filled with hand-written lists."""
    offer = [dict(entry) for entry in big_order(20, added=0)]
    for entry in offer:
        entry["doc"] = "offer"
    priced = [dict(entry, unit_price=PRICES[2]) for entry in offer]
    items = {"an_pdf": offer, "an_d84": priced, "p4_pdf": big_tender(5), "p4_x83": big_tender(5),
             "hem_x83": big_tender(), "hem_d83": big_tender(), "hem_d86": big_order(),
             "stb_d84": offer, "stb_d86": priced, "n1_x83": big_tender(20)}
    text = "=== PAGE 1 ===\n" + "\n".join("%s  %s" % (entry["item_no"], entry["short_text"])
                                          for entry in big_tender()[1:])
    return pairs.summarize(items, {"leer_pdf": pdftext.pages_of_text(text),
                                   "hem_pdf": pdftext.pages_of_text(text)})


def test_summary_and_record_hold_no_price():
    summary = synthetic_summary()
    record = report.render(summary)
    written = json.dumps(summary) + record
    for price in PRICES:
        assert "%.2f" % price not in written and str(price) not in written
    pair = next(entry for entry in summary["pairs"] if entry["id"] == "t1_offer_pdf_d84")
    assert len(pair["result"]["fields"]["unit_price"]["not_equal_items"]) == 20
    assert pair["result"]["fields"]["total"]["equal"] == 20
    assert "| unit price | 20 | 0 | 20 |" in record


def test_record_states_the_answers_of_the_summary():
    summary = synthetic_summary()
    record = report.render(summary)
    assert summary["hypothesis_38"]["verdict"] == "confirmed"
    assert "- 38-item hypothesis: **confirmed**" in record
    assert "What holds: 38 added, 0 removed, 0 renumbered." in record
    assert "The added items (38): 8.1, 8.2, " in record and "8.38." in record
    assert "These are the added items: yes, the same set of numbers." in record
    assert record.count("**holds**") >= 2 and record.endswith("\n")
    in_pdf = summary["hypothesis_38"]["added_titles_in_tender_pdf"]
    assert in_pdf[pdftext.NOT_FOUND] == 38 and in_pdf[pdftext.FOUND_AS_WRITTEN] == 0
    row = next(line for line in record.split("\n") if line.startswith("| `HEM2301-2_Gesamt-LV.pdf` | `8209.003_Leistungsverzeichnis_leer.X83`"))
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    assert cells[3:14] == ["1", "159", "159", "159", "0", "0", "159", "100.0", "0", "159", "100.0"]
    for entry in summary["pairs"] + summary["text_pairs"]:
        assert "out/diff/%s.json" % entry["id"] in record or entry.get("role") == "control"


def test_record_says_refuted_and_what_holds_instead():
    summary = synthetic_summary()
    summary["hypothesis_38"] = decide(big_order(added=39, drop=(7,)))
    summary["hypothesis_38"]["added_titles_in_tender_pdf"] = dict((cls, 0) for cls in pdftext.CLASSES)
    record = report.render(summary)
    assert "**Answer: refuted.**" in record
    assert "What holds: 39 added, 1 removed, 0 renumbered." in record
    assert "the hypothesis does not hold as stated" in record


def test_percent_is_cut_off_so_that_it_never_shows_a_rule_as_met_too_early():
    assert report.percent(136, 155) == "87.7" and report.percent(245, 245) == "100.0"
    assert report.percent(8999, 10000) == "89.9" and report.percent(1, 3) == "33.3"
    assert report.percent(0, 0) == "-"


def test_long_number_lists_are_cut_and_say_so():
    assert report.numbers([]) == "none"
    assert report.numbers(["1", "2"]) == "1, 2"
    assert report.numbers([str(n) for n in range(70)], limit=3) == "0, 1, 2 and 67 more (all in the result file)"


def test_missing_data_is_reported(tmp_path, capsys):
    assert pairs.main(["--data", str(tmp_path), "--out", str(tmp_path / "out"), "--doc", "-"]) == 2
    assert "missing in" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def strength(verdict, as_written, only, placeholder_title, searchable=155):
    counts = dict((cls, 0) for cls in pdftext.CLASSES)
    counts[pdftext.FOUND_AS_WRITTEN], counts[pdftext.FOUND_ANONYMIZED] = as_written, only
    entry = {"pdf": "hem_pdf", "list": "hem_d83", "verdict": verdict,
             "result": {"counts": counts, "found_total": as_written + only, "searchable": searchable,
                        "placeholder_title": ["1.%d" % n for n in range(placeholder_title)]}}
    return report.t5_strength(synthetic_summary(), entry)


def test_record_says_what_a_holds_rests_on():
    lines = strength(pairs.HOLDS, 111, 43, 40)
    assert len(lines) == 2 and lines[1] == ""
    assert "\"holds\" for `HEM2301-2_Gesamt-LV.pdf` against `8209.003_Leistungsverzeichnis_leer.D83`" in lines[0]
    assert "rests on the 43 titles found only with anonymization allowed (43 of the 154 found" in lines[0]
    assert "without them 111 of 155 searchable titles, 71.6 percent" in lines[0]
    assert "in 40 of these 43 the title in the PDF begins with a placeholder" in lines[0]
    # no sentence when the titles found without anonymization meet the rule
    # alone, or when the answer is not "holds"
    assert strength(pairs.HOLDS, 140, 10, 3) == []
    assert strength(pairs.UNDECIDED, 111, 25, 24) == []


def test_record_states_the_placeholder_rule_as_the_code_applies_it():
    record = report.render(synthetic_summary())
    assert "A title whose first or last word is a placeholder in the PDF is not counted here" not in record
    assert ("So a title whose first or last word is plain is not found where the PDF holds a "
            "placeholder for that word; a title whose first or last word is or holds a placeholder "
            "is found also where the PDF holds a placeholder there.") in record
    assert "for 1 to %d characters" % pairs.textcmp.MAX_SPAN in record
