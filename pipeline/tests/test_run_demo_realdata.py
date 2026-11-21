"""The one command on the organizer data (W9). Skips when data/ or Poppler is missing.

One run into a temporary folder, then a second run into the same folder:
every step is ok, the second run leaves every file byte-equal, and the
findings file the screen reads carries the independent verdict and the
rule-based severity (the two things a forgotten step would leave wrong
without any error on the screen).
"""
import hashlib
import io
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from pipeline import run as demo  # noqa: E402
from pipeline.common import contract, severity  # noqa: E402

DATA = os.path.join(ROOT, "data")
HAVE_DATA = os.path.isdir(DATA) and len([n for n in os.listdir(DATA) if n.startswith("LV_") and n.endswith(".pdf")]) == 27
pytestmark = pytest.mark.skipif(not HAVE_DATA or demo.poppler_missing() is not None,
                                reason="the organizer data (data/, 27 LV_*.pdf) or Poppler's pdftotext is missing")

LINE = re.compile(r"^ *(\d+)/(\d+)  (.+?)  +(ok|failed|skipped) +(\d+\.\d) s(?:  (.*))?$")
MONEY = re.compile(r"€|EUR|\d,\d\d(?!\d)")


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def hashes(*folders):
    found = {}
    for folder in folders:
        for base, _dirs, files in os.walk(folder):
            for name in files:
                path = os.path.join(base, name)
                with open(path, "rb") as handle:
                    found[os.path.relpath(path, os.path.dirname(folder))] = hashlib.sha256(handle.read()).hexdigest()
    return found


def run_once(out, cache, data=DATA, verbose=False):
    stream = io.StringIO()
    code = demo.run(data, out, cache, stream=stream, verbose=verbose)
    return code, stream.getvalue()


@pytest.fixture(scope="module")
def two_runs(tmp_path_factory):
    base = tmp_path_factory.mktemp("w9")
    out, cache = str(base / "out"), str(base / "cache")
    first_code, first_text = run_once(out, cache)
    first = hashes(out, cache)
    second_code, second_text = run_once(out, cache, verbose=True)
    return {"out": out, "cache": cache, "codes": (first_code, second_code), "text": first_text,
            "verbose_text": second_text, "first": first, "second": hashes(out, cache)}


def test_every_step_is_ok_on_the_organizer_data(two_runs):
    assert two_runs["codes"] == (0, 0), two_runs["text"]
    lines = [LINE.match(line).groups() for line in two_runs["text"].splitlines() if LINE.match(line)]
    assert [line[2] for line in lines] == [step.name for step in demo.build_steps(DATA, two_runs["out"], two_runs["cache"])]
    assert all(line[3] == "ok" for line in lines)
    assert "FAILED" not in two_runs["text"] and "skipped:" not in two_runs["text"]
    assert "Screen:  python -m web --project 79-222" in two_runs["text"]


def test_the_second_run_leaves_every_file_byte_equal(two_runs):
    assert two_runs["first"] == two_runs["second"]
    assert len(two_runs["first"]) > 40
    for name in ("items.json", "manifest.json", "findings.json", "base_findings.json"):
        assert os.path.join("out", "79-222", name) in two_runs["first"]


def test_the_manifest_is_the_committed_one(two_runs):
    assert load(os.path.join(two_runs["out"], "79-222", "manifest.json")) == load(demo.COMMITTED_MANIFEST)
    assert len(load(demo.COMMITTED_MANIFEST)) == 27


def test_every_project_has_its_items_and_its_base_findings(two_runs):
    folders = sorted(name for name in os.listdir(two_runs["out"]) if name != "diff")
    assert "79-222" in folders and "PROJEKT_004" in folders and "AN24-0305" in folders and len(folders) >= 8
    for folder in folders:
        assert os.path.isfile(os.path.join(two_runs["out"], folder, "items.json")), folder
        assert isinstance(load(os.path.join(two_runs["out"], folder, "base_findings.json")), list), folder
    offer_docs = {item["doc"] for item in load(os.path.join(two_runs["out"], "AN24-0305", "items.json"))}
    assert len(offer_docs) == 2, "the offer PDF and its D84 twin stand in one project folder"


def test_trap_1_the_findings_carry_the_independent_verdict_not_the_finders(two_runs):
    findings = load(os.path.join(two_runs["out"], "79-222", "findings.json"))
    stored = {finding["id"]: finding for finding in load(demo.STORED_FINDINGS)}
    verdicts = load(demo.STORED_VERDICTS)
    verdicts = {v["id"]: v for v in verdicts} if isinstance(verdicts, list) else verdicts
    assert len(findings) == 24 and {finding["id"] for finding in findings} == set(stored) == set(verdicts)
    counts = {}
    for finding in findings:
        assert finding["skeptic"]["status"] == verdicts[finding["id"]]["status"]
        assert finding["skeptic"]["note"] == verdicts[finding["id"]]["note"]
        counts[finding["skeptic"]["status"]] = counts.get(finding["skeptic"]["status"], 0) + 1
    assert counts == {"survived": 11, "weakened": 13}
    finder_counts = {}
    for finding in stored.values():
        finder_counts[finding["skeptic"]["status"]] = finder_counts.get(finding["skeptic"]["status"], 0) + 1
    assert finder_counts == {"survived": 16, "weakened": 8}, "the stored file still holds the finder's own pass"
    changed = [f["id"] for f in findings if f["skeptic"]["status"] != stored[f["id"]]["skeptic"]["status"]]
    assert changed, "the merge changed verdicts; a run without it would be seen here"


def test_trap_2_the_findings_carry_the_rule_based_severity_not_the_finders(two_runs):
    folder = os.path.join(two_runs["out"], "79-222")
    findings = load(os.path.join(folder, "findings.json"))
    stored = {finding["id"]: finding for finding in load(demo.STORED_FINDINGS)}
    by_rule, _rules = severity.apply(findings, load(os.path.join(folder, "items.json")))
    assert [f["severity"] for f in by_rule] == [f["severity"] for f in findings], "severity ran, and ran last"
    assert by_rule == findings
    changed = [f["id"] for f in findings if f["severity"] != stored[f["id"]]["severity"]]
    assert len(changed) == 10, "the rules moved 10 of 24 levels; a run without the step would be seen here"


def test_the_review_queue_of_the_screen_is_built_from_these_findings(two_runs):
    from fastapi.testclient import TestClient
    from web.app import create_app
    client = TestClient(create_app(out_dir=two_runs["out"], reviews_dir=os.path.join(two_runs["out"], "..", "reviews"),
                                   project="79-222"))
    data = client.get("/api/findings").json()
    assert data["mode"] == "real" and data["contract_errors"] == 0 and len(data["findings"]) == 24
    survived = [f for f in data["findings"] if f["skeptic"]["status"] == "survived"]
    assert len(survived) == 11, "11 findings left standing by the independent pass, not the finder's 16"


def test_the_findings_file_meets_the_contract(two_runs):
    findings = load(os.path.join(two_runs["out"], "79-222", "findings.json"))
    assert contract.errors("findings", findings) == []
    assert contract.errors("items", load(os.path.join(two_runs["out"], "79-222", "items.json"))) == []


def test_no_line_of_the_run_holds_a_price_or_an_amount(two_runs):
    for text in (two_runs["text"], two_runs["verbose_text"]):
        assert not MONEY.findall(text)
    assert two_runs["verbose_text"].count("| ") > 50, "the verbose run shows what the steps print"


def link_data(folder, leave_out=()):
    folder.mkdir()
    for name in os.listdir(DATA):
        if name not in leave_out:
            os.symlink(os.path.join(DATA, name), str(folder / name))
    return str(folder)


@pytest.mark.skipif(os.name == "nt", reason="uses links to the data files")
def test_a_list_missing_from_data_fails_the_manifest_check_by_name(tmp_path):
    missing = sorted(n for n in os.listdir(DATA) if n.startswith("LV_") and n.endswith(".pdf"))[0]
    code, text = run_once(str(tmp_path / "out"), str(tmp_path / "cache"), data=link_data(tmp_path / "data", [missing]))
    assert code == 1
    assert ("FAILED: %s" % demo.MANIFEST) in text
    line = [l for l in text.splitlines() if demo.MANIFEST in l and "failed" in l][0]
    assert "not equal" in line and "not read" in line


@pytest.mark.skipif(os.name == "nt", reason="uses links to the data files")
def test_without_poppler_the_gaeb_files_are_still_read_and_no_findings_file_is_written(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    out = tmp_path / "out"
    code, text = run_once(str(out), str(tmp_path / "cache"), data=link_data(tmp_path / "data"))
    assert code == demo.EXIT_INPUT_MISSING
    status = {m.group(3): m.group(4) for m in (LINE.match(line) for line in text.splitlines()) if m}
    assert status[demo.TEXT] == status[demo.OFFER_READER] == status[demo.MERGE] == status[demo.SEVERITY] == "skipped"
    assert status[demo.GAEB90] == status[demo.GAEBXML] == status[demo.BASE] == "ok"
    assert status[demo.PAGES] == status[demo.DIFF] == "skipped", "both read PDFs with Poppler"
    assert not (out / "79-222").exists() and (out / "8209.003" / "items.json").is_file()
    assert "No findings.json for 79-222 was written" in text


# ---- the page check and the comparison (the two last steps) ----------------

def test_the_page_check_writes_one_page_image_per_source_of_the_findings(two_runs):
    folder = os.path.join(two_runs["out"], "79-222")
    findings = load(os.path.join(folder, "findings.json"))
    wanted = sorted("%s_%d.png" % (f["id"], i) for f in findings for i, _source in enumerate(f["sources"]))
    assert sorted(os.listdir(os.path.join(folder, "pages"))) == wanted and len(wanted) == 51
    for name in wanted:
        with open(os.path.join(folder, "pages", name), "rb") as handle:
            assert handle.read(8) == b"\x89PNG\r\n\x1a\n", name
    summary = load(os.path.join(folder, "pagecheck.json"))["summary"]
    assert summary["findings"] == 24 and summary["sources"] == summary["found_on_stated_page"] == 51
    line = [l for l in two_runs["text"].splitlines() if demo.PAGES in l][0]
    assert "51 of 51 quotes on the stated page" in line and "51 page images" in line


def test_the_page_check_leaves_the_findings_file_of_the_screen_as_severity_wrote_it(two_runs):
    folder = os.path.join(two_runs["out"], "79-222")
    findings, checked = load(os.path.join(folder, "findings.json")), load(os.path.join(folder, "findings.pagecheck.json"))
    strip = lambda rows: [{k: v for k, v in row.items() if k != "quotes_verified"} for row in rows]  # noqa: E731
    assert strip(findings) == strip(checked), "the copy differs in quotes_verified at most"
    assert sum(1 for f in findings if f["skeptic"]["status"] == "survived") == 11


def test_the_screen_serves_the_page_image_behind_quelle_zeigen(two_runs):
    from fastapi.testclient import TestClient
    from web.app import create_app
    client = TestClient(create_app(out_dir=two_runs["out"], reviews_dir=os.path.join(two_runs["out"], "..", "reviews"),
                                   project="79-222"))
    for finding in client.get("/api/findings").json()["findings"]:
        answer = client.get("/api/page-image/%s/0" % finding["id"])
        assert answer.status_code == 200 and answer.content[:4] == b"\x89PNG", finding["id"]


def test_the_comparison_writes_every_twin_and_stage_pair(two_runs):
    summary = load(os.path.join(two_runs["out"], "diff", "summary.json"))
    ids = [entry["id"] for entry in summary["pairs"] + summary["text_pairs"]]
    assert len(ids) == len(set(ids)) == 15
    for name in ids:
        assert os.path.isfile(os.path.join(two_runs["out"], "diff", name + ".json")), name
    stage = load(os.path.join(two_runs["out"], "diff", "t3_tender_d83_order_d86.json"))
    assert (stage["mode"], stage["a"]["items"], stage["b"]["items"]) == ("stage", 159, 197)
    assert len(stage["matching"]["only_b"]) == 38 and stage["matching"]["only_a"] == [] and len(stage["stage"]["added"]) == 38
    twin = load(os.path.join(two_runs["out"], "diff", "t1_offer_pdf_d84.json"))
    assert twin["mode"] == "twin" and twin["matching"]["both"] == 274
    assert [l for l in two_runs["text"].splitlines() if demo.DIFF in l][0].endswith("15 comparisons")


def test_the_comparison_does_not_rewrite_the_committed_record(two_runs):
    import subprocess
    done = subprocess.run(["git", "status", "--porcelain", "--", "docs/TWINS.md"], cwd=ROOT, capture_output=True)
    if done.returncode != 0:
        pytest.skip("not a git checkout")
    assert done.stdout.strip() == b""
