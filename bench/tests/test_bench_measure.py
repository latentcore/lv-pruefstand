"""M1, M2, M5, M7, M8, M9 and the shared helpers, on hand-written items and files."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402

import bench_samples as samples  # noqa: E402
from bench import measure, prereg  # noqa: E402


def test_record_takes_name_and_threshold_from_the_record_and_rejects_unknown_values():
    entry = measure.record("M8", prereg.YES, clean={"items": 1})
    assert entry == {"id": "M8", "name": "False alarms", "threshold": "≤ 5", "met": "yes", "clean": {"items": 1}}
    with pytest.raises(ValueError):
        measure.record("M8", "almost")


def test_percent_is_cut_and_the_threshold_is_compared_on_the_counts():
    assert measure.tenths(979, 1000) == 979 and measure.tenths(2, 3) == 666 and measure.tenths(1, 0) is None
    assert measure.at_least(49, 50, 98) and not measure.at_least(48, 50, 98)
    assert measure.at_least(18, 20, 90) and not measure.at_least(17, 20, 90) and not measure.at_least(0, 0, 90)


def test_every_measurement_without_its_input_is_not_measured_yet(tmp_path):
    ctx = measure.Context(data=str(tmp_path / "data"), reviews=str(tmp_path / "reviews"),
                          findings=str(tmp_path / "none.json"))
    entries = measure.run(ctx)
    assert [e["id"] for e in entries] == ["M%d" % n for n in range(1, 10)]
    assert all(e["met"] == prereg.NOT_YET and e["reason"] for e in entries)


def test_m1_counts_files_with_exactly_the_expected_items():
    files = dict((name, [samples.item("01.%d" % n, "Leistung %d" % n) for n in range(count)])
                 for name, count in prereg.GAEB_FILES)
    entry = measure.m1(samples.context_with(files))
    assert (entry["met"], entry["files_equal"], entry["files_expected"]) == (prereg.YES, 9, 9)
    first = prereg.GAEB_FILES[0][0]
    files[first] = files[first][:-1] + [samples.heading("99", "Abschnitt")]
    entry = measure.m1(samples.context_with(files))
    assert (entry["met"], entry["files_equal"]) == (prereg.NO, 8)
    assert entry["files"][0]["read"] == prereg.GAEB_FILES[0][1] - 1


def test_m2_lists_deviations_by_item_number_and_counts_the_unchecked():
    records = samples.clean_list()
    records[2]["total"] = records[2]["total"] + 1
    records.append(samples.item("02.70", "Leistung ohne Menge", quantity=None, unit_price=2.0, total=4.0))
    files = dict((name, samples.clean_list()) for name in prereg.PRICED_FILES)
    files[prereg.PRICED_FILES[1]] = records
    entry = measure.m2(samples.context_with(files))
    assert entry["met"] == prereg.YES and entry["deviating"] == 1 and entry["not_checkable_no_quantity"] == 1
    assert entry["files"][1]["deviating_items"] == [records[2]["item_no"]]
    assert entry["checked"] == 4 * 12
    assert samples.price_leaks(entry) == []


def _reviews(tmp_path, entries):
    folder = tmp_path / "reviews"
    folder.mkdir()
    (folder / "79-222.json").write_text(json.dumps(entries), encoding="utf-8")
    return str(folder)


def test_m5_counts_only_decisions_of_a_role_without_test_inside_the_session(tmp_path):
    reviews = _reviews(tmp_path, {
        "X1": {"status": "confirmed", "by": "Kalkulator", "at": "2026-11-21T10:05:00"},
        "X2": {"status": "rejected", "by": "Kalkulator", "at": "2026-11-21T13:59"},
        "X3": {"status": "unclear", "by": "Bauleiter", "at": "2026-11-21T14:00"},
        "X4": {"status": "confirmed", "by": "Kalkulator (Test)", "at": "2026-11-21T11:00"},
        "X5": {"status": "confirmed", "by": "", "at": "2026-11-21T11:00"},
        "X6": {"status": "confirmed", "by": "Kalkulator", "at": "2026-11-21T09:59"},
        "X7": {"status": "open", "by": "Kalkulator", "at": "2026-11-21T11:00"},
        "X8": "confirmed",
    })
    entry = measure.m5(samples.context_with({}, reviews=reviews))
    assert entry["met"] == prereg.YES
    assert (entry["entries"], entry["counted"]) == (8, 3)
    assert (entry["confirmed"], entry["rejected"], entry["unclear"]) == (1, 1, 1)
    assert entry["by_role"] == [{"role": "Bauleiter", "confirmed": 0, "rejected": 0, "unclear": 1},
                                {"role": "Kalkulator", "confirmed": 1, "rejected": 1, "unclear": 0}]
    assert entry["not_counted"] == {"no decision": 1, "no role given": 1, "not a review record": 1,
                                    "outside the expert session": 1, "role holds 'test'": 1}
    assert entry["roles_found"] == ["Bauleiter", "Kalkulator", "Kalkulator (Test)"]


def test_m5_without_a_counted_decision_is_not_measured_yet(tmp_path):
    entry = measure.m5(samples.context_with({}, reviews=str(tmp_path)))
    assert (entry["met"], entry["file_found"]) == (prereg.NOT_YET, False)
    reviews = _reviews(tmp_path, {"X1": {"status": "confirmed", "by": "Test", "at": "2026-11-21T10:30"}})
    entry = measure.m5(samples.context_with({}, reviews=reviews))
    assert (entry["met"], entry["counted"], entry["reason"]) == (prereg.NOT_YET, 0, prereg.M5_NOT_YET)


def test_m7_and_m8_on_the_clean_file():
    files = {prereg.CLEAN_FILE: samples.findable_list()}
    entry = measure.m7(samples.context_with(files))
    # found: quantity, amount and duplicate 16 each, both section totals, 12 of 16 deletions, no unit change
    assert entry["planted"] == 16 * 5 + 2 and entry["found"] == 16 * 3 + 2 + 12
    assert entry["percent_tenths"] == measure.tenths(entry["found"], entry["planted"])
    assert entry["met"] == prereg.NO and entry["x"].startswith("not measured")
    assert entry["seed"] == prereg.SEED
    entry = measure.m8(samples.context_with(files))
    assert entry["met"] == prereg.YES and entry["clean"]["high_medium"] == 0 and entry["other"] is None


def test_false_alarms_count_high_and_medium_per_100_items():
    records = samples.findable_list()
    records.append(samples.item("02.90", "Leistung 1 im Abschnitt 02", quantity=10.0, unit="m", unit_price=3.0))
    result = measure.false_alarms(records)
    assert result["items"] == 17 and result["high_medium"] >= 1
    assert result["per_100_hundredths"] == (10000 * result["high_medium"]) // 17
    assert result["within"] == (100 * result["high_medium"] <= 5 * 17)


def test_build_300_appends_copies_in_a_new_section_99():
    records = samples.findable_list(per_section=125)
    built = measure.build_300(records)
    added = samples.positions(built)[250:]
    assert len(samples.positions(built)) == 300 and len(added) == 50
    assert [r["item_no"] for r in added[:3]] == ["99.10", "99.20", "99.30"] and added[-1]["item_no"] == "99.500"
    assert all(r["section"] == "99" for r in added)
    assert added[0]["short_text"] == samples.positions(records)[0]["short_text"]
    assert built[:len(records)] == records
    with pytest.raises(ValueError):
        measure.build_300(samples.findable_list(per_section=151))
    with pytest.raises(ValueError):
        measure.build_300(samples.findable_list(per_section=10))


def test_median_of_five_runs_without_a_warm_up():
    ticks = iter([0, 1, 10, 12, 20, 25, 30, 33, 40, 44])
    calls = []
    assert measure.median_seconds(lambda: calls.append(1), clock=lambda: next(ticks)) == 3
    assert len(calls) == 5


def test_m9_times_both_inputs_and_names_the_machine(monkeypatch):
    files = {prereg.M9_BUILT_FROM: samples.findable_list(per_section=125),
             prereg.M9_AS_IS_FILE: samples.findable_list(per_section=148)}
    monkeypatch.setattr(measure, "read_gaeb", lambda path: [])
    entry = measure.m9(samples.context_with(files))
    assert [(i["input"], i["items"]) for i in entry["inputs"]] == [("built", 300), ("as it is", 296)]
    assert entry["met"] in (prereg.YES, prereg.NO) and entry["runs"] == 5
    assert "Python" in entry["machine"] and "cores" in entry["machine"]
    assert samples.price_leaks(entry) == []
