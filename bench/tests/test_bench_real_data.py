"""The committed bench/results/bench.json and the README table, and a fresh run on the organizer data.

The first part needs only the committed files. The second part runs where the
organizer files are in data/ (AGENTS.md "Data and items.json") and is skipped
elsewhere: the measurements that do not depend on the clock (M1, M2, M3, M7,
M8) must give the committed records again. A failing check names a
measurement or a file, never a price.
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402

import bench_samples as samples  # noqa: E402
from bench import measure, prereg, readme, run  # noqa: E402

DATA = os.path.join(prereg.REPO_ROOT, "data")
COMMITTED = os.path.exists(run.RESULTS_PATH)
HAS_DATA = all(os.path.isfile(os.path.join(DATA, name)) for name, _count in prereg.GAEB_FILES)

needs_results = pytest.mark.skipif(not COMMITTED, reason="bench/results/bench.json is not measured yet")
needs_data = pytest.mark.skipif(not (COMMITTED and HAS_DATA), reason="the organizer files are not in data/")


def committed():
    return run.read_json(run.RESULTS_PATH)


@needs_results
def test_committed_results_hold_the_nine_rows_and_no_price():
    data = committed()
    assert [(e["id"], e["name"], e["threshold"]) for e in data["measurements"]] == list(prereg.ROWS)
    assert all(e["met"] in prereg.MET_VALUES for e in data["measurements"])
    assert samples.price_leaks(data) == []
    assert data["prereg"] == "docs/PREREG.md" and data["measured_at"]


@needs_results
def test_readme_table_is_made_from_the_committed_results():
    with open(readme.README_PATH, encoding="utf-8") as handle:
        assert readme.in_sync(handle.read(), committed())


@needs_data
@pytest.mark.parametrize("row_id", ["M1", "M2", "M3", "M7", "M8"])
def test_a_fresh_run_gives_the_committed_record(row_id):
    if row_id == "M3" and not shutil.which("pdftotext"):
        pytest.skip("pdftotext is not installed")
    ctx = measure.Context(data=DATA)
    fresh = getattr(measure, row_id.lower())(ctx)
    entry = next(e for e in committed()["measurements"] if e["id"] == row_id)
    assert fresh == entry, "%s differs from bench/results/bench.json" % row_id
