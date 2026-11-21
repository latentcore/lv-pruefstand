"""The runner: all twelve checks on one items.json, the printed lines, the written file."""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))

import base_samples as s  # noqa: E402
from pipeline.base import run  # noqa: E402
from pipeline.common import contract  # noqa: E402

CHECK_NAMES = ["B%d" % n for n in range(1, 13)]
PRICES = ("3.33", "3,33", "44.44", "44,44", "7.77", "7,77")


def tender_and_offer():
    """A tender list without prices and an offer with prices, one arithmetic error in the offer."""
    tender = [s.heading("1", "Mauerarbeiten", doc="LV_TENDER"),
              s.note("1", "Alle Arbeiten nach Angabe der Bauleitung.", doc="LV_TENDER"),
              s.item("1.10", "Wand mauern in Kalksandstein", doc="LV_TENDER"),
              s.item("1.20", "Zulage Bogen", unit="St", quantity=2.0, doc="LV_TENDER"),
              s.item("1.30", "Sturz liefern und einbauen", "Fabrikat: Musterwerk Typ 5", unit="St",
                     quantity=0.0, kind="optional", doc="LV_TENDER")]
    offer = [s.item("1.10", "Wand mauern in Kalksandstein", unit_price=3.33, total=44.44, doc="LV_OFFER"),
             s.item("1.20", "Tor einbauen mit Zarge", unit="St", quantity=2.0, unit_price=7.77, total=15.54,
                    doc="LV_OFFER")]
    return tender + offer


def test_the_runner_holds_the_twelve_checks_of_the_plan_in_order():
    assert [check for check, _, _ in run.CHECKS] == CHECK_NAMES
    assert len({function for _, _, function in run.CHECKS}) == 12


def test_run_all_runs_every_check_on_every_document():
    items = tender_and_offer()
    findings, summary = run.run_all(items)
    assert [entry["check"] for entry in summary] == CHECK_NAMES
    assert all(entry["documents"] == 2 and entry["dropped"] == 0 and entry["same_id"] == 0 for entry in summary)
    by_check = {entry["check"]: entry for entry in summary}
    assert by_check["B1"]["not_applicable"] == ["LV_TENDER"] and by_check["B1"]["findings"] == 1
    assert by_check["B2"]["not_applicable"] == ["LV_TENDER", "LV_OFFER"]
    assert by_check["B7"]["not_applicable"] == ["LV_TENDER"]
    for check in ("B3", "B4", "B5", "B6", "B8", "B9", "B10", "B11", "B12"):
        assert by_check[check]["not_applicable"] == [], check
    assert {f["check"] for f in findings} == {"B1", "B6", "B8", "B10", "B11", "B12"}
    assert [f["check"] for f in findings] == sorted((f["check"] for f in findings), key=CHECK_NAMES.index)
    assert sum(entry["findings"] for entry in summary) == len(findings)
    assert all(f["quotes_verified"] is True for f in findings)
    s.valid(findings, items)
    s.no_amount(findings, *PRICES)


def test_run_all_gives_the_same_result_twice_and_does_not_change_the_items():
    items = tender_and_offer()
    before = json.dumps(items, sort_keys=True)
    assert run.run_all(items) == run.run_all(items)
    assert json.dumps(items, sort_keys=True) == before


def test_unknown_keys_are_ignored():
    plain = tender_and_offer()
    extra = [dict(record, price_mode="unit", made_up_key={"a": 1}) for record in plain]
    assert run.run_all(extra) == run.run_all(plain)


def test_records_with_missing_or_odd_fields_do_not_break_a_check():
    items = [{"doc": "LV_ODD"}, {"doc": "LV_ODD", "item_no": None, "kind": None, "short_text": None},
             {"doc": "LV_ODD", "item_no": "1.10", "short_text": "Wand mauern in Kalksandstein", "quantity": "viel",
              "unit": 5, "unit_price": "n. A.", "total": [], "page": "3"},
             {"doc": "LV_ODD", "item_no": 7, "kind": "normal", "long_text": "Decke betonieren ca. 20 cm",
              "quantity": True, "unit": "m2", "page": 2.5},
             {"item_no": "9.9", "short_text": "ohne Dokument"}, "noise", None, 5]
    findings, summary = run.run_all(items)
    assert [entry["check"] for entry in summary] == CHECK_NAMES and summary[0]["documents"] == 1
    contract.check("findings", findings)
    assert all(source["doc"] == "LV_ODD" and source["page"] is None for f in findings for source in f["sources"])


def test_an_empty_list_is_not_applicable_everywhere():
    findings, summary = run.run_all([])
    assert findings == []
    assert all(run.summary_line(entry).endswith("not applicable (no documents)") for entry in summary)


def test_the_contract_sample_runs():
    items = contract.load_sample("items")
    findings, summary = run.run_all(items)
    contract.check("findings", findings)
    assert len(summary) == 12 and all(entry["dropped"] == 0 for entry in summary)


def test_summary_line_names_the_check_the_count_and_not_applicable():
    entry = {"check": "B1", "title": "t", "findings": 0, "documents": 1, "not_applicable": ["A"],
             "dropped": 0, "same_id": 0, "notes": {}}
    assert run.summary_line(entry) == "B1   findings=0  not applicable (1 of 1 documents)"
    entry.update(check="B10", findings=3, documents=2, notes={"merged": 2, "covered_by_note": 1})
    assert run.summary_line(entry) == ("B10  findings=3  not applicable for 1 of 2 documents"
                                       "  covered_by_note=1  merged=2")
    entry.update(not_applicable=[], notes={}, dropped=1)
    assert run.summary_line(entry) == "B10  findings=3  dropped=1"


def test_main_writes_the_findings_and_prints_one_line_per_check(tmp_path, capsys):
    source, out = tmp_path / "items.json", tmp_path / "deep" / "folder" / "base_findings.json"
    source.write_text(json.dumps(tender_and_offer(), ensure_ascii=False), encoding="utf-8")
    assert run.main([str(source), str(out)]) == 0
    printed = capsys.readouterr().out
    lines = printed.strip().split("\n")
    assert [line.split()[0] for line in lines] == CHECK_NAMES
    assert all("findings=" in line for line in lines)
    assert "not applicable for 1 of 2 documents" in lines[0]
    assert "not applicable (2 of 2 documents)" in lines[1]
    written = json.loads(out.read_text(encoding="utf-8"))
    contract.check("findings", written)
    assert written == run.run_all(tender_and_offer())[0]
    assert sum(int(line.split("findings=")[1].split()[0]) for line in lines) == len(written)
    for amount in PRICES:
        assert amount not in printed and amount not in out.read_text(encoding="utf-8")


def test_main_says_what_is_wrong_with_the_input(tmp_path, capsys):
    out = tmp_path / "out.json"
    assert run.main([str(tmp_path / "missing.json"), str(out)]) == 2
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert run.main([str(broken), str(out)]) == 2
    not_a_list = tmp_path / "object.json"
    not_a_list.write_text('{"doc": "LV_T1"}', encoding="utf-8")
    assert run.main([str(not_a_list), str(out)]) == 2
    assert not out.exists()
    assert capsys.readouterr().out == ""


def test_the_command_runs_as_a_module(tmp_path):
    source, out = tmp_path / "items.json", tmp_path / "base_findings.json"
    source.write_text(json.dumps(tender_and_offer(), ensure_ascii=False), encoding="utf-8")
    done = subprocess.run([sys.executable, "-m", "pipeline.base.run", str(source), str(out)],
                          cwd=s.ROOT, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    assert [line.split()[0] for line in done.stdout.strip().split("\n")] == CHECK_NAMES
    contract.check("findings", json.loads(out.read_text(encoding="utf-8")))
