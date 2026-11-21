"""The table, the command and the README block, on a bench.json measured from hand-written items."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402

import bench_samples as samples  # noqa: E402
from bench import measure, prereg, readme, run, table, twins  # noqa: E402


@pytest.fixture
def data(monkeypatch, tmp_path):
    """A bench.json whose records come from the measurement code on hand-written items."""
    files = dict((name, [samples.item("01.%d" % n, "Leistung %d" % n) for n in range(count)])
                 for name, count in prereg.GAEB_FILES)
    for name in prereg.PRICED_FILES:
        files[name] = samples.clean_list()
    files[prereg.CLEAN_FILE] = samples.findable_list()
    files[prereg.M9_BUILT_FROM] = samples.findable_list(per_section=125)
    files[prereg.M9_AS_IS_FILE] = samples.findable_list(per_section=148)
    lists = {}
    for _twin, pdf, gaeb in prereg.M3_PAIRS:
        files[pdf] = files.setdefault(gaeb, samples.clean_list())
        lists[pdf], lists[gaeb] = files[pdf], files[gaeb]
    monkeypatch.setattr(twins, "read", lambda folder, name: lists[name])
    monkeypatch.setattr(measure, "read_gaeb", lambda path: [])
    ctx = samples.context_with(files, reviews=str(tmp_path))
    return {"bench": "test", "prereg": "docs/PREREG.md", "measured_at": "2026-11-21T12:00",
            "measurements": measure.run(ctx)}


def test_rows_are_the_nine_of_the_record_with_their_thresholds(data):
    rows = table.rows(data)
    assert [(r[0], r[1], r[3]) for r in rows] == list(prereg.ROWS)
    assert all(r[4] in prereg.MET_VALUES for r in rows)
    assert dict((r[0], r[4]) for r in rows)["M5"] == prereg.NOT_YET


def test_markdown_text_and_german_lines_come_from_the_same_records(data):
    lines = table.markdown(data).split("\n")
    assert lines[0] == "| # | Measurement | Result | Threshold | Threshold met |" and len(lines) == 11
    assert all(line.count(" | ") == 4 for line in lines[2:])
    printed = table.text(data).split("\n")
    assert len(printed) == 10 and "2026-11-21T12:00" in printed[0]
    german = table.lines_de(data)
    assert len(german) == 10 and german[0].startswith("Messlauf (bench), Stand 2026-11-21 12:00.")
    for row, md, de in zip(table.rows(data), lines[2:], german[1:]):
        assert md.startswith("| %s | %s |" % (row[0], row[1]))
        assert de.endswith("Schwelle eingehalten: %s." % table.MET_DE[row[4]])
    assert "B: %d of %d found" % (data["measurements"][6]["found"], data["measurements"][6]["planted"]) in printed[7]


def test_bench_json_of_the_samples_holds_no_price_and_no_em_dash(data):
    assert samples.price_leaks(data) == []
    em_dash = chr(0x2014)
    assert em_dash not in json.dumps(data, ensure_ascii=False)
    assert em_dash not in table.markdown(data) + "\n".join(table.lines_de(data))


def test_not_measured_rows_show_their_reason_in_both_languages(tmp_path):
    entries = measure.run(measure.Context(data=str(tmp_path), reviews=str(tmp_path), findings=str(tmp_path / "x")))
    data = {"measured_at": "2026-11-21T12:00", "measurements": entries}
    for row, de in zip(table.rows(data), table.lines_de(data)[1:]):
        assert row[4] == prereg.NOT_YET and row[2]
        assert "noch nicht gemessen" in de
    assert "Eingabe fehlt: " in table.lines_de(data)[1]


def test_command_writes_the_json_and_the_report_lines_then_prints_the_table_from_the_file(tmp_path, capsys):
    results, out = tmp_path / "bench.json", tmp_path / "out"
    code = run.main(["--data", str(tmp_path / "data"), "--out", str(out), "--reviews", str(tmp_path),
                     "--results", str(results)])
    assert code == 0
    data = json.loads(results.read_text(encoding="utf-8"))
    assert [e["id"] for e in data["measurements"]] == ["M%d" % n for n in range(1, 10)]
    report = json.loads((out / "79-222" / "bench.json").read_text(encoding="utf-8"))
    assert report == {"lines": table.lines_de(data)}
    assert capsys.readouterr().out.strip() == table.text(data)
    assert run.main(["--table", "--results", str(results)]) == 0
    assert capsys.readouterr().out.strip() == table.text(data)
    assert run.main(["--table", "--results", str(tmp_path / "none.json")]) == 2


def test_readme_block_is_added_once_and_replaced_in_place(data, tmp_path):
    text = "# Title\n\nText.\n"
    first = readme.rewrite(text, data)
    assert first.startswith(text) and first.count(readme.START) == 1 and readme.in_sync(first, data)
    changed = dict(data, measurements=[dict(e, met=prereg.NOT_YET) for e in data["measurements"]])
    second = readme.rewrite(first + "After.\n", changed)
    assert second.startswith(text) and second.endswith("After.\n") and readme.in_sync(second, changed)
    assert not readme.in_sync(second, data)
    with pytest.raises(readme.MarkerError):
        readme.current_table(first + readme.START)


def test_readme_command_checks_and_writes(data, tmp_path):
    results, page = tmp_path / "bench.json", tmp_path / "README.md"
    results.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    page.write_text("# Title\n", encoding="utf-8")
    assert readme.main(["--readme", str(page), "--results", str(results), "--check"]) == 1
    assert readme.main(["--readme", str(page), "--results", str(results)]) == 0
    assert readme.main(["--readme", str(page), "--results", str(results), "--check"]) == 0
    assert page.read_text(encoding="utf-8").startswith("# Title\n\n" + readme.START)
