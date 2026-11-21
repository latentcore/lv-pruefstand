"""The one command of the demo run (W9): python -m pipeline.run.

Checked here without the organizer data: the order of the steps, what a
failed, a skipped and a crashed step print and return, that a half-done
findings file is removed, what the run says without data/ and without
Poppler, that the screen then opens on its sample data, that no file of the
screen names an outside address, and the skip rule of one skeptic test.
The runs on the real lists are in test_run_demo_realdata.py.
"""
import importlib.util
import io
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from pipeline import run as demo  # noqa: E402

OUTSIDE = re.compile(r"(?:https?:)?//[A-Za-z0-9]", re.IGNORECASE)
LINE = re.compile(r"^ *(\d+)/(\d+)  (.+?)  +(ok|failed|skipped) +(\d+\.\d) s(?:  (.*))?$")


def step_lines(text):
    return [LINE.match(line).groups() for line in text.splitlines() if LINE.match(line)]


def run_fake(steps, tmp_path):
    stream = io.StringIO()
    code = demo.run(str(tmp_path / "data"), str(tmp_path / "out"), str(tmp_path / "cache"), stream=stream, steps=steps)
    return code, stream.getvalue()


def names(tmp_path):
    return [step.name for step in demo.build_steps(str(tmp_path / "d"), str(tmp_path / "o"), str(tmp_path / "c"))]


# ---- the order -----------------------------------------------------------

def test_the_steps_stand_in_the_order_the_screen_needs(tmp_path):
    order = names(tmp_path)
    assert len(order) == len(set(order)), "every step has its own name"
    position = {name: index for index, name in enumerate(order)}
    chain = [demo.TEXT, demo.READER, demo.MANIFEST]
    assert [position[name] for name in chain] == sorted(position[name] for name in chain)
    readers = [demo.READER, demo.PRINT_READER, demo.OFFER_READER, demo.GAEB90, demo.GAEBXML]
    assert all(position[name] < position[demo.BASE] for name in readers), "base checks run on every items.json"
    assert position[demo.PRINT_READER] < position[demo.GAEB90] and position[demo.OFFER_READER] < position[demo.GAEB90], \
        "the print and offer readers write a whole folder, the GAEB readers add to it"
    findings_chain = [demo.READER, demo.EVIDENCE, demo.RULES, demo.MERGE, demo.SEVERITY]
    assert [position[name] for name in findings_chain] == sorted(position[name] for name in findings_chain)
    assert order.index(demo.MERGE) < order.index(demo.SEVERITY), "severity works on the merged file"


def test_the_page_check_and_the_comparison_are_the_two_last_steps(tmp_path):
    order = names(tmp_path)
    assert order[-2:] == [demo.PAGES, demo.DIFF] and len(order) == 14
    by_name = {step.name: step for step in demo.build_steps(str(tmp_path / "d"), str(tmp_path / "o"), str(tmp_path / "c"))}
    assert by_name[demo.PAGES].needs == (demo.SEVERITY,), "the page images are those of the finished findings file"
    assert demo.PAGES not in demo.FINDINGS_CHAIN and demo.DIFF not in demo.FINDINGS_CHAIN


def test_the_page_check_reads_the_finished_findings_and_never_writes_that_file(tmp_path):
    out = str(tmp_path / "o")
    by_name = {step.name: step for step in demo.build_steps(str(tmp_path / "d"), out, str(tmp_path / "c"))}
    (command,) = by_name[demo.PAGES].commands
    project = os.path.join(out, "79-222")
    assert command[1:3] == ["-m", "pipeline.common.pagecheck"]
    assert command[3:6] == [os.path.join(project, "findings.json"), str(tmp_path / "d"), project]
    assert command[6] == os.path.join(project, "findings.pagecheck.json"), "its own copy, not the file of the screen"
    assert command[7:] == ["--items", os.path.join(project, "items.json")]


def test_the_comparison_writes_to_out_diff_and_leaves_the_committed_record_alone(tmp_path):
    out = str(tmp_path / "o")
    by_name = {step.name: step for step in demo.build_steps(str(tmp_path / "d"), out, str(tmp_path / "c"))}
    (command,) = by_name[demo.DIFF].commands
    assert command[1:] == ["-m", "pipeline.diff.pairs", "--data", str(tmp_path / "d"), "--out",
                           os.path.join(out, "diff"), "--doc", "-"]
    assert by_name[demo.DIFF].needs == ()


def write_findings(tmp_path, findings):
    folder = tmp_path / "out" / "79-222"
    folder.mkdir(parents=True, exist_ok=True)
    import json
    (folder / "findings.json").write_text(json.dumps(findings), encoding="utf-8")
    return folder


def real_step(tmp_path, name):
    steps = demo.build_steps(str(tmp_path / "data"), str(tmp_path / "out"), str(tmp_path / "cache"))
    return [step for step in steps if step.name == name][0]


def test_a_page_image_that_was_not_written_fails_the_page_check_by_name(tmp_path):
    folder = write_findings(tmp_path, [{"id": "X2-aaaaaa", "sources": [{"doc": "LV_01"}, {"doc": "LV_02"}]},
                                       {"id": "X3-bbbbbb", "sources": [{"doc": "LV_03"}]}])
    (folder / "pages").mkdir()
    (folder / "pages" / "X2-aaaaaa_0.png").write_bytes(b"png")
    real = real_step(tmp_path, demo.PAGES)
    steps = [demo.Step(demo.SEVERITY, call=lambda: None),
             demo.Step(demo.PAGES, call=lambda: None, needs=real.needs, verify=real.verify)]
    code, text = run_fake(steps, tmp_path)
    line = {line[2]: line for line in step_lines(text)}[demo.PAGES]
    assert code == demo.EXIT_FAILED and "FAILED: %s\n" % demo.PAGES in text
    assert line[3] == "failed" and line[5].startswith("2 of 3 page images were not written to ")
    assert line[5].endswith("(first: X2-aaaaaa_1.png)")
    for name in ("X2-aaaaaa_1.png", "X3-bbbbbb_0.png"):
        (folder / "pages" / name).write_bytes(b"png")
    assert real.verify() is None


def test_findings_without_sources_need_no_page_image(tmp_path):
    write_findings(tmp_path, [{"id": "X3-cccccc", "sources": []}, {"id": "X3-dddddd"}])
    assert real_step(tmp_path, demo.PAGES).verify() is None


def test_the_page_check_command_that_cannot_read_its_input_fails_the_step_by_name(tmp_path):
    (tmp_path / "data").mkdir()
    write_findings(tmp_path, {"not": "a list"})
    steps = [demo.Step(demo.SEVERITY, call=lambda: None), real_step(tmp_path, demo.PAGES)]
    code, text = run_fake(steps, tmp_path)
    line = {line[2]: line for line in step_lines(text)}[demo.PAGES]
    assert code == demo.EXIT_FAILED and line[3] == "failed" and "FAILED: %s\n" % demo.PAGES in text


def test_the_page_check_does_not_run_when_severity_failed(tmp_path):
    steps = [demo.Step(demo.SEVERITY, call=lambda: "the rules file is missing"), real_step(tmp_path, demo.PAGES)]
    code, text = run_fake(steps, tmp_path)
    line = {line[2]: line for line in step_lines(text)}[demo.PAGES]
    assert code == demo.EXIT_FAILED
    assert line[3] == "skipped" and line[5] == 'needs the step "%s", which failed' % demo.SEVERITY
    assert not (tmp_path / "out").exists()


def test_the_comparison_names_the_first_file_it_misses(tmp_path):
    from pipeline.diff import pairs
    step = real_step(tmp_path, demo.DIFF)
    assert step.missing().startswith("no folder ")
    (tmp_path / "data").mkdir()
    absent = pairs.missing_files(str(tmp_path / "data"))
    assert step.missing() == 'no file "%s" in %s (and %d more)' % (absent[0], tmp_path / "data", len(absent) - 1)
    code, text = run_fake([step], tmp_path)
    assert code == demo.EXIT_INPUT_MISSING and step_lines(text)[0][3] == "skipped"
    assert not (tmp_path / "out").exists()


@pytest.mark.skipif(demo.poppler_missing() is not None, reason="Poppler's pdftotext is missing")
def test_a_comparison_that_cannot_read_its_files_fails_the_step_by_name(tmp_path):
    from pipeline.diff import pairs
    (tmp_path / "data").mkdir()
    for name in pairs.missing_files(str(tmp_path / "data")):
        (tmp_path / "data" / name).write_bytes(b"")
    step = real_step(tmp_path, demo.DIFF)
    assert step.missing() is None
    code, text = run_fake([step], tmp_path)
    assert code == demo.EXIT_FAILED and step_lines(text)[0][3] == "failed"
    assert "FAILED: %s\n" % demo.DIFF in text


def test_every_needed_step_stands_before_the_step_that_needs_it(tmp_path):
    steps = demo.build_steps(str(tmp_path / "d"), str(tmp_path / "o"), str(tmp_path / "c"))
    seen = set()
    for step in steps:
        assert set(step.needs) <= seen, "%s needs a step that comes later" % step.name
        seen.add(step.name)


def test_merge_and_severity_cannot_run_without_the_step_before(tmp_path):
    by_name = {step.name: step for step in demo.build_steps(str(tmp_path / "d"), str(tmp_path / "o"), str(tmp_path / "c"))}
    assert demo.RULES in by_name[demo.MERGE].needs
    assert demo.MERGE in by_name[demo.SEVERITY].needs
    assert demo.FINDINGS_CHAIN[:2] == (demo.MERGE, demo.SEVERITY)


def test_the_findings_commands_read_the_stored_results_and_write_in_place(tmp_path):
    out = str(tmp_path / "o")
    by_name = {step.name: step for step in demo.build_steps(str(tmp_path / "d"), out, str(tmp_path / "c"))}
    findings = os.path.join(out, "79-222", "findings.json")
    merge = by_name[demo.MERGE].commands[0]
    assert merge[-3] == demo.STORED_FINDINGS and merge[-1] == findings
    assert merge[-2] == os.path.join(out, "79-222", "skeptic", "verdicts.json"), "the verdicts after the rule checks"
    severity = by_name[demo.SEVERITY].commands[0]
    assert severity[-3] == findings and severity[-1] == findings, "severity runs in place"
    rules = by_name[demo.RULES].commands[0]
    assert demo.STORED_VERDICTS in rules and "--text-dir" in rules
    for path in (demo.STORED_FINDINGS, demo.STORED_VERDICTS, demo.STORED_TERMS, demo.COMMITTED_MANIFEST):
        assert os.path.isfile(path), "%s is in the repository" % path


def test_no_step_calls_a_model_or_the_network(tmp_path):
    text = open(demo.__file__, encoding="utf-8").read()
    for word in ("anthropic", "openai", "requests", "urllib", "http.client", "socket", "api_key", "API_KEY"):
        assert word not in text, word
    for step in demo.build_steps(str(tmp_path / "d"), str(tmp_path / "o"), str(tmp_path / "c")):
        commands = step.commands if isinstance(step.commands, list) else []
        for command in commands:
            assert command[0] == sys.executable, "every step is a Python command of this repository"
            assert not [part for part in command if OUTSIDE.search(part.replace(os.sep, "/").replace("//", "/"))]


# ---- what a run prints and returns ---------------------------------------

def test_all_ok_gives_exit_0_and_one_line_per_step(tmp_path):
    steps = [demo.Step("first", call=lambda: None), demo.Step("second", call=lambda: None, needs=["first"],
                                                                detail=lambda: "3 lists")]
    code, text = run_fake(steps, tmp_path)
    assert code == demo.EXIT_OK == 0
    lines = step_lines(text)
    assert [(line[0], line[1], line[2], line[3]) for line in lines] == [("1", "2", "first", "ok"), ("2", "2", "second", "ok")]
    assert lines[1][5] == "3 lists"
    assert "2 steps: 2 ok, 0 failed, 0 skipped" in text and "FAILED" not in text


def test_a_failed_step_is_named_and_gives_exit_1(tmp_path):
    ran = []
    steps = [
        demo.Step("reads", call=lambda: ran.append("reads")),
        demo.Step("breaks", call=lambda: "the file is not a list"),
        demo.Step("needs the broken one", call=lambda: ran.append("no"), needs=["breaks"]),
        demo.Step("stands alone", call=lambda: ran.append("alone") and None),
    ]
    code, text = run_fake(steps, tmp_path)
    assert code == demo.EXIT_FAILED == 1
    lines = {line[2]: line for line in step_lines(text)}
    assert lines["breaks"][3] == "failed" and lines["breaks"][5] == "the file is not a list"
    assert lines["needs the broken one"][3] == "skipped"
    assert lines["needs the broken one"][5] == 'needs the step "breaks", which failed'
    assert lines["stands alone"][3] == "ok", "a step that does not need the failed one still runs"
    assert ran == ["reads", "alone"]
    assert "FAILED: breaks\n" in text and "Not complete, skipped: needs the broken one" in text


def test_a_step_that_raises_is_a_failed_step_with_its_line(tmp_path):
    def crash():
        raise ValueError("bad\nlast line of the message")
    code, text = run_fake([demo.Step("crashes", call=crash), demo.Step("after", call=lambda: None)], tmp_path)
    assert code == 1
    lines = step_lines(text)
    assert lines[0][3] == "failed" and lines[0][5] == "ValueError: last line of the message"
    assert lines[1][3] == "ok"


def test_a_command_that_ends_with_an_error_code_fails_the_step_with_its_last_line(tmp_path):
    bad = [sys.executable, "-c", "import sys; print('counted 3'); sys.stderr.write('first\\nno such list\\n'); sys.exit(2)"]
    good = [sys.executable, "-c", "print('fine')"]
    code, text = run_fake([demo.Step("two commands", [good, bad, good])], tmp_path)
    assert code == 1
    assert step_lines(text)[0][5] == "exit code 2: no such list"


def test_a_command_that_cannot_be_started_fails_the_step(tmp_path):
    code, text = run_fake([demo.Step("no program", [[str(tmp_path / "not-there"), "x"]])], tmp_path)
    assert code == 1 and "cannot start" in step_lines(text)[0][5]


def test_the_verify_function_can_fail_a_step_whose_commands_were_fine(tmp_path):
    good = [sys.executable, "-c", "pass"]
    code, text = run_fake([demo.Step("checked", [good], verify=lambda: "result differs from the committed one")], tmp_path)
    assert code == 1 and step_lines(text)[0][3] == "failed"
    assert step_lines(text)[0][5] == "result differs from the committed one"


def test_missing_input_skips_with_the_reason_and_gives_its_own_exit_code(tmp_path):
    ran = []
    steps = [
        demo.Step("wants a file", call=lambda: ran.append(1), missing=lambda: "no file \"x.pdf\" in data"),
        demo.Step("after it", call=lambda: ran.append(2), needs=["wants a file"]),
    ]
    code, text = run_fake(steps, tmp_path)
    assert code == demo.EXIT_INPUT_MISSING == 3 and code not in (0, 1)
    lines = step_lines(text)
    assert lines[0][3] == "skipped" and lines[0][5] == 'no file "x.pdf" in data'
    assert lines[1][5] == 'needs the step "wants a file", which was skipped'
    assert ran == [], "a skipped step does not run"
    assert "FAILED" not in text


def test_a_failed_step_wins_over_a_skipped_one_in_the_exit_code(tmp_path):
    steps = [demo.Step("skipped", call=lambda: None, missing=lambda: "nothing there"),
             demo.Step("failed", call=lambda: "broken")]
    assert run_fake(steps, tmp_path)[0] == 1


def test_verbose_prints_the_lines_of_the_commands_and_the_default_does_not(tmp_path):
    command = [sys.executable, "-c", "print('read 4 lists')"]
    quiet, loud = io.StringIO(), io.StringIO()
    demo.run_steps([demo.Step("talks", [command])], quiet)
    demo.run_steps([demo.Step("talks", [command])], loud, verbose=True)
    assert "read 4 lists" not in quiet.getvalue() and "| read 4 lists" in loud.getvalue()


def test_the_seconds_are_measured_and_printed_with_one_decimal(tmp_path):
    results = demo.run_steps([demo.Step("quick", call=lambda: None)], io.StringIO())
    name, status, note, seconds = results[0]
    assert (name, status, note) == ("quick", "ok", "") and 0 <= seconds < 5


# ---- the findings file after the run ---------------------------------------

def findings_file(tmp_path, text="[]"):
    folder = tmp_path / "out" / demo.PROJECT
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "findings.json").write_text(text, encoding="utf-8")
    return folder / "findings.json"


def test_a_findings_file_that_severity_did_not_finish_is_removed(tmp_path):
    def write():
        findings_file(tmp_path, '[{"half": "done"}]')
    steps = [demo.Step(demo.MERGE, call=write), demo.Step(demo.SEVERITY, call=lambda: "items.json is not a list", needs=[demo.MERGE])]
    code, text = run_fake(steps, tmp_path)
    assert code == 1
    assert not (tmp_path / "out" / demo.PROJECT / "findings.json").exists(), \
        "the screen must not show a file with the finder's levels"
    assert "Removed" in text and "No findings.json for 79-222 was written" in text
    assert "Screen:" not in text


def test_a_findings_file_of_an_earlier_run_is_kept_and_named_when_the_merge_did_not_run(tmp_path):
    path = findings_file(tmp_path, '[{"earlier": "run"}]')
    steps = [demo.Step(demo.RULES, call=lambda: "verdicts differ"),
             demo.Step(demo.MERGE, call=lambda: None, needs=[demo.RULES]),
             demo.Step(demo.SEVERITY, call=lambda: None, needs=[demo.MERGE])]
    code, text = run_fake(steps, tmp_path)
    assert code == 1 and path.read_text(encoding="utf-8") == '[{"earlier": "run"}]'
    assert "is from an earlier run; this run did not write it" in text
    assert "Screen:" not in text


def test_the_screen_command_is_printed_only_after_merge_and_severity_are_ok(tmp_path):
    steps = [demo.Step(demo.MERGE, call=lambda: findings_file(tmp_path) and None),
             demo.Step(demo.SEVERITY, call=lambda: None, needs=[demo.MERGE])]
    code, text = run_fake(steps, tmp_path)
    assert code == 0
    last = text.strip().splitlines()[-2:]
    assert last[0].startswith("Screen:  python -m web --project 79-222 --out ") and "http://127.0.0.1:8000" in last[0]
    assert last[1].startswith("Export:  python -m web.export --project 79-222 --data ")
    assert str(tmp_path / "out") in last[0]


def test_the_screen_command_needs_no_folder_when_the_output_is_out_of_the_repository():
    stream = io.StringIO()
    steps = [demo.Step("nothing", call=lambda: None, missing=lambda: "test")]
    demo.run(os.path.join(ROOT, "data"), os.path.join(ROOT, "out"), os.path.join(ROOT, "cache"), stream=stream, steps=steps)
    assert "python -m web" in stream.getvalue().splitlines()[-1]


# ---- without data, without Poppler -----------------------------------------

def test_without_the_data_folder_every_step_says_so_and_nothing_is_written(tmp_path, capsys):
    data, out, cache = tmp_path / "data", tmp_path / "out", tmp_path / "cache"
    code = demo.main([str(data), str(out), "--cache", str(cache)])
    text = capsys.readouterr().out
    assert code == demo.EXIT_INPUT_MISSING
    lines = step_lines(text)
    assert len(lines) == len(names(tmp_path)) and all(line[3] == "skipped" for line in lines)
    wanted = "no folder %s (put the organizer files there)" % data
    by_name = {line[2]: line[5] for line in lines}
    for name in (demo.TEXT, demo.PRINT_READER, demo.OFFER_READER, demo.GAEB90, demo.GAEBXML):
        assert by_name[name] == wanted
    assert by_name[demo.BASE] == "no items.json in %s" % out
    assert by_name[demo.SEVERITY] == 'needs the step "%s", which was skipped' % demo.MERGE
    assert not out.exists() and not cache.exists()
    assert "Beispieldaten" in text and text.strip().endswith("python -m web")
    assert "FAILED" not in text


def test_an_empty_data_folder_names_the_files_that_are_missing(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    code = demo.main([str(tmp_path / "data"), str(tmp_path / "out"), "--cache", str(tmp_path / "cache")])
    by_name = {line[2]: line[5] for line in step_lines(capsys.readouterr().out)}
    assert code == demo.EXIT_INPUT_MISSING
    assert by_name[demo.TEXT].startswith("no LV_*.pdf in ")
    assert by_name[demo.PRINT_READER].startswith('no file "%s" in ' % demo.PRINT_PDF)
    assert by_name[demo.OFFER_READER].startswith('no file "%s" in ' % demo.OFFER_PDF)
    assert by_name[demo.GAEB90].startswith("no .D83/.D84/.D86 file in ")
    assert by_name[demo.GAEBXML].startswith("no .X83/.X84/.X86 file in ")
    assert by_name[demo.DIFF].startswith('no file "') and by_name[demo.PAGES].startswith("needs the step ")


def test_without_poppler_the_pdf_steps_say_so(tmp_path, monkeypatch, capsys):
    data = tmp_path / "data"
    data.mkdir()
    for name in ("LV_01_Test.pdf", demo.PRINT_PDF, demo.OFFER_PDF):
        (data / name).write_bytes(b"%PDF-1.4\n")
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert demo.poppler_missing() == "no pdftotext on PATH (install Poppler)"
    code = demo.main([str(data), str(tmp_path / "out"), "--cache", str(tmp_path / "cache")])
    by_name = {line[2]: line for line in step_lines(capsys.readouterr().out)}
    assert code == demo.EXIT_INPUT_MISSING
    for name in (demo.TEXT, demo.PRINT_READER, demo.OFFER_READER):
        assert by_name[name][3] == "skipped" and "Poppler" in by_name[name][5]
    assert by_name[demo.READER][5] == 'needs the step "%s", which was skipped' % demo.TEXT


def test_a_pdftotext_that_is_not_poppler_is_named(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("the stand-in program is a shell script")
    fake = tmp_path / "bin" / "pdftotext"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\necho 'pdftotext version 4.04 Copyright Glyph and Cog' >&2\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake.parent))
    assert "not Poppler" in demo.poppler_missing()


def test_the_module_runs_as_a_command_without_data(tmp_path):
    import subprocess
    done = subprocess.run([sys.executable, "-m", "pipeline.run", str(tmp_path / "none"), str(tmp_path / "out"),
                           "--cache", str(tmp_path / "cache")], cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == demo.EXIT_INPUT_MISSING, done.stderr
    assert "no folder" in done.stdout and done.stderr == ""


def test_the_screen_opens_on_the_sample_data_when_no_findings_file_is_there(tmp_path):
    from fastapi.testclient import TestClient
    from web.app import create_app
    client = TestClient(create_app(out_dir=str(tmp_path / "out"), reviews_dir=str(tmp_path / "reviews")))
    assert client.get("/").status_code == 200
    data = client.get("/api/findings").json()
    assert data["mode"] == "sample" and data["missing"] and data["findings"]
    script = open(os.path.join(ROOT, "web", "static", "app.js"), encoding="utf-8").read()
    assert "Beispieldaten" in script, "the yellow line of the page"


# ---- no outside address ------------------------------------------------------

def test_no_file_of_the_screen_names_an_outside_address():
    folder = os.path.join(ROOT, "web", "static")
    files = sorted(os.listdir(folder))
    assert "index.html" in files
    for name in files:
        text = open(os.path.join(folder, name), encoding="utf-8").read()
        assert not OUTSIDE.findall(text), "%s names an outside address" % name
        assert "@import" not in text and "url(" not in text.replace("url(#", ""), name


def test_the_outside_address_search_finds_what_it_must():
    for text in ('<script src="https://cdn.example/x.js">', "url(http://fonts.example/a.woff)", 'href="//cdn.example/a.css"'):
        assert OUTSIDE.search(text)
    for text in ("a // a comment", "/api/findings", "'/static/app.js'"):
        assert not OUTSIDE.search(text)


# ---- the skip rule of one skeptic test ----------------------------------------

def load_notes_test(monkeypatch, have_items, have_text):
    folder = os.path.join(ROOT, "pipeline", "skeptic", "tests")
    monkeypatch.syspath_prepend(folder)
    import skeptic_samples as samples
    real_exists, real_isdir = os.path.exists, os.path.isdir
    monkeypatch.setattr(os.path, "exists", lambda path: have_items if path == samples.REAL_ITEMS else real_exists(path))
    monkeypatch.setattr(os.path, "isdir", lambda path: have_text if path == samples.REAL_TEXT_DIR else real_isdir(path))
    spec = importlib.util.spec_from_file_location("w9_copy_of_test_skeptic_notes_de",
                                                  os.path.join(folder, "test_skeptic_notes_de.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def skipped(function):
    return any(mark.name == "skipif" and mark.args[0] for mark in getattr(function, "pytestmark", []))


@pytest.mark.parametrize("have_items, have_text, expected", [
    (True, False, True),      # the case that failed: out/79-222 there, cache/79-222_text not
    (True, True, False),
    (False, True, True),
    (False, False, True),
])
def test_the_real_list_test_of_the_notes_skips_without_the_page_texts(monkeypatch, have_items, have_text, expected):
    module = load_notes_test(monkeypatch, have_items, have_text)
    target = module.test_rules_and_merge_on_the_real_lists_give_24_findings_with_german_notes
    assert skipped(target) is expected


def test_the_other_tests_of_that_file_keep_their_skip_rule(monkeypatch):
    module = load_notes_test(monkeypatch, True, False)
    target = module.test_rules_and_merge_on_the_real_lists_give_24_findings_with_german_notes
    others = [value for name, value in vars(module).items()
              if name.startswith("test_") and callable(value) and value is not target]
    assert len(others) > 20
    assert not [function.__name__ for function in others if skipped(function)], \
        "with items.json there, only the one test that needs the page texts skips"
