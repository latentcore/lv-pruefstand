"""merge: only the skeptic field changes, and the result follows the findings schema."""
import copy
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402

import skeptic_samples as samples  # noqa: E402
from pipeline.common import contract  # noqa: E402
from pipeline.skeptic import AGENT_ORIGIN, STATUSES, merge  # noqa: E402


def findings():
    return [samples.finding(), samples.second_finding()]


def verdicts():
    return {"X1-bbbbbb": samples.verdict("refuted", "LV 92 2.10 decides it."),
            "X2-aaaaaa": samples.verdict("weakened", "LV 91 1.10 decides it.")}


def without_skeptic(finding):
    return {key: value for key, value in finding.items() if key != "skeptic"}


def test_merge_replaces_the_skeptic_field_and_nothing_else():
    old = findings()
    before = copy.deepcopy(old)
    merged = merge.merge(old, verdicts())
    assert old == before, "the input must not change"
    assert [f["id"] for f in merged] == [f["id"] for f in old], "same findings, same order"
    assert [without_skeptic(f) for f in merged] == [without_skeptic(f) for f in old]
    assert [list(f) for f in merged] == [list(f) for f in old], "same keys, same key order"
    assert merged[0]["skeptic"] == verdicts()["X2-aaaaaa"]
    assert merged[1]["skeptic"] == verdicts()["X1-bbbbbb"]
    assert "FINDER NOTE" not in json.dumps(merged, ensure_ascii=False)


def test_merge_keeps_refuted_findings_in_the_file():
    merged = merge.merge(findings(), verdicts())
    assert len(merged) == 2 and merged[1]["skeptic"]["status"] == "refuted"


def test_merge_keeps_unknown_keys_of_a_finding():
    old = [samples.finding(review={"status": "confirmed"}, extra_key=[1, 2])]
    merged = merge.merge(old, {"X2-aaaaaa": samples.verdict()})
    assert merged[0]["review"] == {"status": "confirmed"} and merged[0]["extra_key"] == [1, 2]


def test_merge_adds_the_field_to_a_finding_that_had_none():
    finding = without_skeptic(samples.finding())
    merged = merge.merge([finding], {"X2-aaaaaa": samples.verdict()})
    assert merged[0]["skeptic"]["status"] == "survived"


def test_merged_copies_do_not_share_objects_with_the_input():
    old, new = findings(), verdicts()
    merged = merge.merge(old, new)
    merged[0]["sources"][0]["quote"] = "changed"
    merged[0]["skeptic"]["note"] = "changed"
    assert old[0]["sources"][0]["quote"] != "changed"
    assert new["X2-aaaaaa"]["note"] != "changed"


def test_result_follows_the_findings_schema():
    merged = merge.merge(findings(), verdicts())
    assert contract.errors("findings", merged) == []
    with_rules = dict(samples.verdict("weakened"), agent_status="survived",
                      rules={"unsupported_numbers": ["9"]}, rule_note="Regelprüfung: x.")
    assert contract.errors("findings", merge.merge([samples.finding()], {"X2-aaaaaa": with_rules})) == []


def test_missing_verdict_is_an_error():
    with pytest.raises(merge.MergeError, match="X1-bbbbbb: finding has no verdict"):
        merge.merge(findings(), {"X2-aaaaaa": samples.verdict()})


def test_verdict_for_an_unknown_finding_is_an_error():
    more = dict(verdicts(), **{"X9-zzzzzz": samples.verdict()})
    with pytest.raises(merge.MergeError, match="X9-zzzzzz: verdict has no finding"):
        merge.merge(findings(), more)


def test_finding_id_twice_is_an_error():
    with pytest.raises(merge.MergeError, match="stands twice"):
        merge.merge([samples.finding(), samples.finding()], {"X2-aaaaaa": samples.verdict()})


@pytest.mark.parametrize("bad", [
    {"status": "confirmed", "note": "x"},
    {"status": "", "note": "x"},
    {"note": "x"},
    {"status": "survived", "note": ""},
    {"status": "survived", "note": "   "},
    {"status": "survived"},
    {"status": "survived", "note": 7},
    "survived",
    None,
])
def test_verdict_that_is_not_filled_is_an_error(bad):
    with pytest.raises(merge.MergeError, match="X2-aaaaaa"):
        merge.merge([samples.finding()], {"X2-aaaaaa": bad})


def test_status_better_than_the_agent_status_is_an_error():
    raised = dict(samples.verdict("survived"), agent_status="weakened")
    with pytest.raises(merge.MergeError, match="may only lower"):
        merge.merge([samples.finding()], {"X2-aaaaaa": raised})
    lowered = dict(samples.verdict("weakened"), agent_status="survived")
    assert merge.merge([samples.finding()], {"X2-aaaaaa": lowered})[0]["skeptic"]["status"] == "weakened"
    with pytest.raises(merge.MergeError, match="agent_status"):
        merge.merge([samples.finding()], {"X2-aaaaaa": dict(samples.verdict(), agent_status="ok")})


def test_wrong_containers_are_an_error():
    with pytest.raises(merge.MergeError):
        merge.merge({"X2-aaaaaa": samples.finding()}, verdicts())
    with pytest.raises(merge.MergeError):
        merge.merge(findings(), [samples.verdict()])


def test_empty_findings_and_empty_verdicts_merge_to_nothing():
    assert merge.merge([], {}) == []


def test_status_counts_lists_every_status():
    assert merge.status_counts(merge.merge(findings(), verdicts())) == {
        "survived": 0, "weakened": 1, "refuted": 1}
    assert list(merge.status_counts([])) == list(STATUSES)


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_command_writes_the_merged_findings(tmp_path, capsys):
    out = tmp_path / "new" / "findings.json"
    code = merge.main([write(tmp_path / "in.json", findings()), write(tmp_path / "v.json", verdicts()),
                       str(out)])
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == merge.merge(findings(), verdicts())
    assert contract.errors("findings", data) == []
    assert "2 findings written" in capsys.readouterr().out
    assert "Wärmedämmung" in out.read_text(encoding="utf-8"), "umlauts are written as they are"


def test_command_leaves_the_input_file_alone(tmp_path):
    source = tmp_path / "in.json"
    write(source, findings())
    before = source.read_bytes()
    assert merge.main([str(source), write(tmp_path / "v.json", verdicts()), str(tmp_path / "out.json")]) == 0
    assert source.read_bytes() == before


def test_command_fails_and_writes_nothing_on_a_missing_verdict(tmp_path, capsys):
    out = tmp_path / "out.json"
    code = merge.main([write(tmp_path / "in.json", findings()),
                       write(tmp_path / "v.json", {"X2-aaaaaa": samples.verdict()}), str(out)])
    assert code == 1 and not out.exists()
    assert "X1-bbbbbb" in capsys.readouterr().err


def test_command_fails_when_the_result_breaks_the_schema(tmp_path, capsys):
    broken = without_skeptic(samples.finding())
    del broken["sources"]
    out = tmp_path / "out.json"
    code = merge.main([write(tmp_path / "in.json", [broken]),
                       write(tmp_path / "v.json", {"X2-aaaaaa": samples.verdict()}), str(out)])
    assert code == 1 and not out.exists()
    assert "sources" in capsys.readouterr().err


def test_command_runs_as_a_module(tmp_path):
    out = tmp_path / "out.json"
    done = subprocess.run(
        [sys.executable, "-m", "pipeline.skeptic.merge", write(tmp_path / "in.json", findings()),
         write(tmp_path / "v.json", verdicts()), str(out)],
        cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert [f["skeptic"]["origin"] for f in json.loads(out.read_text(encoding="utf-8"))] == [AGENT_ORIGIN] * 2
