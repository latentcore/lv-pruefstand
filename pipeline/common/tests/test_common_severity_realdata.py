"""W15 on the real project 79-222. Skipped where out/79-222/items.json is not built."""
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from pipeline.common import contract, severity  # noqa: E402

FINDINGS = os.path.join(ROOT, "pipeline", "cross", "results", "79-222", "findings.json")
ITEMS = os.path.join(ROOT, "out", "79-222", "items.json")

pytestmark = pytest.mark.skipif(not (os.path.isfile(ITEMS) and os.path.isfile(FINDINGS)),
                                reason="out/79-222/items.json is not built (see AGENTS.md)")


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def test_command_on_79_222_changes_only_severity(tmp_path, capsys):
    out = str(tmp_path / "findings.json")
    done = subprocess.run([sys.executable, "-m", "pipeline.common.severity", FINDINGS, ITEMS, out],
                          cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    before, after = read_json(FINDINGS), read_json(out)
    assert contract.errors("findings", after) == []
    assert len(after) == len(before)
    changed = 0
    for old, new in zip(before, after):
        assert list(new) == list(old)
        assert new["severity"] in severity.LEVELS
        changed += old["severity"] != new["severity"]
        old["severity"] = new["severity"]
    assert after == before  # nothing but severity differs
    counts = dict((level, sum(1 for finding in after if finding["severity"] == level)) for level in severity.LEVELS)
    lines = done.stdout.splitlines()
    assert lines[0] == "findings: %d" % len(after)
    assert lines[1] == ", ".join("%s: %d" % (level, counts[level]) for level in severity.LEVELS)
    assert lines[2] == "changed level against the input: %d of %d" % (changed, len(after))
    assert len(lines) == 3 + changed
    with capsys.disabled():
        print("\n[W15 79-222] " + " | ".join(lines[:3]))


def test_every_source_of_79_222_has_its_item_and_the_function_agrees_with_the_command():
    findings, items = read_json(FINDINGS), read_json(ITEMS)
    by_key = severity.index_items(items)
    result, decided = severity.apply(findings, items)
    for finding, new, (level, number) in zip(findings, result, decided):
        cited = severity.cited_items(finding, by_key)
        assert len(cited) == len(finding["sources"]) and all(item is not None for item in cited), finding["id"]
        assert severity.severity(finding, cited) == (level, number)
        assert new["severity"] == level
    # By hand: X1-bd7aef cites a Vorbemerkung of LV_18 and a Bedarfsposition of LV_20 -> rule 5.
    by_id = dict((finding["id"], pair) for finding, pair in zip(findings, decided))
    assert by_id["X1-bd7aef"] == ("info", 5)
