"""The lock: docs/PREREG.md is locked and holds every fixed choice the code uses."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))

import bench_samples  # noqa: E402,F401  (puts the repository root on the path)
from bench import measure, prereg, seeded  # noqa: E402

with open(prereg.PREREG_PATH, encoding="utf-8") as _handle:
    TEXT = _handle.read()


def _table_rows():
    rows = {}
    for line in TEXT.split("\n"):
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 4 and re.fullmatch(r"M[1-9]", cells[0]):
            rows[cells[0]] = (cells[1].replace("*", ""), cells[3])
    return rows


def test_status_line_is_locked_with_date_and_time():
    status = next(line for line in TEXT.split("\n") if line.startswith("**Status:"))
    assert re.match(r"\*\*Status: LOCKED, 2026-11-2[12] \d\d:\d\d \(Europe/Berlin\)", status)
    assert "DRAFT" not in status


def test_nothing_is_left_open():
    assert "to be filled" not in TEXT.lower()
    assert "## Open before the lock: fixed choices (filled at the lock)" in TEXT


def test_thresholds_and_names_of_the_code_are_the_ones_of_the_table():
    rows = _table_rows()
    assert sorted(rows) == ["M%d" % n for n in range(1, 10)]
    for row_id, name, threshold in prereg.ROWS:
        assert rows[row_id] == (name, threshold)


def test_threshold_numbers_of_the_code_stand_in_the_table():
    rows = _table_rows()
    assert rows["M1"][1] == "%d/%d" % (prereg.M1_NEEDED, len(prereg.GAEB_FILES))
    assert "≥ %d %% of items" % prereg.M3_ITEMS_PERCENT in rows["M3"][1]
    assert "≥ %d %% of prices" % prereg.M3_PRICES_PERCENT in rows["M3"][1]
    assert "B ≥ %d %%" % prereg.M7_PERCENT in rows["M7"][1]
    assert rows["M8"][1] == "≤ %d" % prereg.M8_PER_100
    assert rows["M9"][1] == "≤ %d s" % prereg.M9_SECONDS


def test_seed_stands_in_the_record():
    assert "**Seed value:** %d" % prereg.SEED in TEXT
    assert "random.Random(%d)" % prereg.SEED in TEXT


def test_nine_gaeb_files_with_their_counts_stand_in_the_record():
    assert len(prereg.GAEB_FILES) == 9
    assert sorted(count for _name, count in prereg.GAEB_FILES) == sorted([159, 197, 274, 249, 249, 296, 159, 50, 248])
    for name, count in prereg.GAEB_FILES:
        assert "`%s` %d" % (name, count) in TEXT


def test_four_priced_files_stand_in_the_record_and_are_gaeb_files():
    line = next(line for line in TEXT.split("\n") if line.startswith("- **M2, the 4 priced GAEB files:**"))
    assert len(prereg.PRICED_FILES) == 4
    for name in prereg.PRICED_FILES:
        assert "`%s`" % name in line
        assert name in dict(prereg.GAEB_FILES)


def test_twin_pairs_stand_in_the_record():
    line = next(line for line in TEXT.split("\n") if line.startswith("- **M3, the pairs:**"))
    assert [twin for twin, _pdf, _gaeb in prereg.M3_PAIRS] == ["T1", "T2"]
    for twin, pdf, gaeb in prereg.M3_PAIRS:
        assert "%s `%s` against `%s`" % (twin, pdf, gaeb) in line


def test_five_lists_are_the_ones_of_the_page_check():
    line = next(line for line in TEXT.split("\n") if line.startswith("- **M4:**"))
    assert list(prereg.M4_PAGECHECK_LISTS) == measure.pagecheck_lists.DEFAULT_DOCS
    assert ", ".join("`%s`" % name for name in prereg.M4_PAGECHECK_LISTS) in line


def test_expert_session_and_review_file_stand_in_the_record():
    line = next(line for line in TEXT.split("\n") if line.startswith("- **M5:**"))
    assert "`reviews/%s.json`" % prereg.M5_PROJECT in line
    assert "2026-11-21 10:00 to 14:00" in line
    assert prereg.M5_SESSION == ("2026-11-21T10:00", "2026-11-21T14:00")
    assert prereg.M5_NOT_YET == "not measured: no expert session took place during the event"


def test_committed_findings_file_stands_in_the_record():
    assert "`%s`" % prereg.M6_FINDINGS.replace(os.sep, "/") in TEXT
    assert os.path.isfile(os.path.join(prereg.REPO_ROOT, prereg.M6_FINDINGS))


def test_seeded_error_counts_and_types_stand_in_the_record():
    line = next(line for line in TEXT.split("\n") if line.startswith("- **M7, seeded errors:**"))
    assert "%d errors per type, %d types, %d in all" % (
        prereg.M7_PER_TYPE, len(seeded.TYPES), prereg.M7_PER_TYPE * len(seeded.TYPES)) in line
    fitting = {"quantity_x10": "B6 `quantity_outlier`", "unit_change": "B5, any type",
               "corrupted_amount": "B1 `arithmetic_error`", "corrupted_total": "B2 `sum_mismatch`",
               "deleted_item": "B3 `number_gap`", "duplicated_item": "B3 `duplicate_number` or B4 `repeated_item`"}
    numbered = [line for line in TEXT.split("\n") if re.match(r"\s+[1-6]\. ", line)]
    assert len(numbered) == len(seeded.TYPES) == 6
    for (key, _name, pairs), line in zip(seeded.TYPES, numbered):
        assert "Fitting: %s" % fitting[key] in line
        for check, type_ in pairs:
            assert check in fitting[key] and (type_ is None or type_ in fitting[key])


def test_clean_file_and_speed_inputs_stand_in_the_record():
    clean = next(line for line in TEXT.split("\n") if line.startswith("- **M8, the clean file:**"))
    speed = next(line for line in TEXT.split("\n") if line.startswith("- **M9, file and machine:**"))
    assert clean.startswith("- **M8, the clean file:** `%s` (249 items)" % prereg.CLEAN_FILE)
    assert "`%s`" % prereg.M8_OTHER_FILE in clean
    assert "a %d-item list built from `%s`" % (prereg.M9_ITEMS, prereg.M9_BUILT_FROM) in speed
    assert "`%s` as it is" % prereg.M9_AS_IS_FILE in speed
    assert "median of %d runs" % prereg.M9_RUNS in speed
    assert "Machine:" in speed


def test_met_column_values():
    assert prereg.MET_VALUES == ("yes", "no", "not measurable", "not measured yet")
