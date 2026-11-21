"""The committed verdicts of 79-222: all 24 findings filled, counts as reported. Needs no organizer data."""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

import skeptic_samples as samples  # noqa: E402
from pipeline.common import contract  # noqa: E402
from pipeline.skeptic import AGENT_ORIGIN, STATUSES, evidence, merge, rules  # noqa: E402

# The counts reported in the pull request and in pipeline/skeptic/README.md.
REPORTED = {"survived": 11, "weakened": 13, "refuted": 0}
REPORTED_BEFORE_RULES = {"survived": 17, "weakened": 7, "refuted": 0}


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def committed_findings():
    return load(samples.COMMITTED_FINDINGS)


def verdicts():
    return load(samples.VERDICTS)


def test_one_verdict_for_each_of_the_24_findings():
    ids = [f["id"] for f in evidence.load_findings(samples.COMMITTED_FINDINGS)]
    assert len(ids) == 24 and len(set(ids)) == 24
    assert list(verdicts()) == ids, "keyed by finding id, in the order of findings.json"


def test_every_verdict_is_filled_with_an_allowed_status():
    for finding_id, verdict in verdicts().items():
        assert verdict["status"] in STATUSES, finding_id
        assert verdict["agent_status"] in STATUSES, finding_id
        assert isinstance(verdict["note"], str) and len(verdict["note"].strip()) >= 40, finding_id


def test_every_verdict_says_where_it_comes_from():
    assert AGENT_ORIGIN == "agent session, independent context"
    assert {v["origin"] for v in verdicts().values()} == {AGENT_ORIGIN}
    assert load(samples.SUMMARY)["origin"] == AGENT_ORIGIN


def test_every_note_names_a_list_and_an_item_and_stays_short():
    for finding_id, verdict in verdicts().items():
        note = verdict["note"]
        assert re.search(r"\bLV \d+[a-z]?\b", note), "%s names no list" % finding_id
        assert re.search(r"(?<![\w,])(\d+(?:\.\d+)+|\.\d+)(?!\w)", note), "%s names no item" % finding_id
        sentences = [s for s in re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])", note) if s.strip()]
        assert len(sentences) <= 2, "%s: note has %d sentences" % (finding_id, len(sentences))
        assert len(note) <= 450, finding_id  # the German notes are longer than the English originals (max. 349)


def test_notes_name_only_lists_the_finding_had_searched():
    by_id = {f["id"]: f for f in evidence.load_findings(samples.COMMITTED_FINDINGS)}
    for finding_id, verdict in verdicts().items():
        named = {"LV_" + n for n in re.findall(r"\bLV (\d+[a-z]?)\b", verdict["note"])}
        assert named <= set(by_id[finding_id]["lists_searched"]), finding_id


def test_counts_in_the_file_equal_the_reported_counts():
    counts = collections.Counter(v["status"] for v in verdicts().values())
    assert {status: counts[status] for status in STATUSES} == REPORTED
    assert sum(REPORTED.values()) == 24
    before = collections.Counter(v["agent_status"] for v in verdicts().values())
    assert {status: before[status] for status in STATUSES} == REPORTED_BEFORE_RULES


def test_summary_file_and_readme_report_the_same_counts():
    summary = load(samples.SUMMARY)
    assert summary["project"] == "79-222" and summary["findings"] == 24
    assert summary["status_counts"] == REPORTED
    assert summary["agent_status_counts"] == REPORTED_BEFORE_RULES
    lowered = [i for i, v in verdicts().items() if v["status"] != v["agent_status"]]
    assert summary["lowered_by_rule"] == lowered and len(lowered) == 6
    with open(os.path.join(samples.ROOT, "pipeline", "skeptic", "README.md"), encoding="utf-8") as handle:
        readme = handle.read()
    assert "24 findings: 11 survived, 13 weakened, 0 refuted" in readme
    assert "17 survived, 7 weakened, 0 refuted" in readme


def test_no_rule_raised_a_verdict():
    rank = {status: n for n, status in enumerate(STATUSES)}
    for finding_id, verdict in verdicts().items():
        assert rank[verdict["status"]] >= rank[verdict["agent_status"]], finding_id
        assert verdict["status"] == rules.lower(verdict["agent_status"], verdict["rules"]), finding_id
        assert verdict["rule_note"] == rules.rule_note(verdict["rules"]), finding_id
        if verdict["rules"]["lowers_to"]:
            assert verdict["status"] != "survived", finding_id
            assert verdict["rule_note"], finding_id


def test_stored_rule_results_are_complete():
    for finding_id, verdict in verdicts().items():
        result = verdict["rules"]
        assert set(result) == {"unsupported_numbers", "single_quote_contradiction", "quotes_not_found",
                               "page_text_checked", "lowers_to"}, finding_id
        assert result["page_text_checked"] is True, finding_id
        fired = bool(result["unsupported_numbers"] or result["single_quote_contradiction"])
        assert result["lowers_to"] == ("weakened" if fired else None), finding_id


def test_one_quote_rule_on_the_committed_findings():
    findings = evidence.load_findings(samples.COMMITTED_FINDINGS)
    single = [f["id"] for f in findings if rules.single_quote_contradiction(f)]
    assert single == ["X2-e710ee"]
    stored = [i for i, v in verdicts().items() if v["rules"]["single_quote_contradiction"]]
    assert stored == single and verdicts()["X2-e710ee"]["status"] == "weakened"


def test_merge_fills_the_skeptic_field_of_all_24_findings():
    old = committed_findings()
    merged = merge.merge(old, verdicts())
    assert len(merged) == 24
    assert [f["id"] for f in merged] == [f["id"] for f in old]
    for before, after in zip(old, merged):
        assert {k: v for k, v in after.items() if k != "skeptic"} == \
               {k: v for k, v in before.items() if k != "skeptic"}, after["id"]
        assert after["skeptic"]["status"] in STATUSES and after["skeptic"]["note"].strip(), after["id"]
        assert after["skeptic"]["origin"] == AGENT_ORIGIN, after["id"]
    cross = [f for f in merged if f["check"].startswith("X")]
    assert len(cross) == 22 and all(f["skeptic"]["note"].strip() for f in cross)
    assert merge.status_counts(merged) == REPORTED
    assert contract.errors("findings", merged) == []


def test_merge_command_on_the_committed_files(tmp_path, capsys):
    out = tmp_path / "findings.json"
    assert merge.main([samples.COMMITTED_FINDINGS, samples.VERDICTS, str(out)]) == 0
    assert "11 survived, 13 weakened, 0 refuted" in capsys.readouterr().out
    merged = load(str(out))
    assert merged == merge.merge(committed_findings(), verdicts())
    assert contract.errors("findings", merged) == []


def test_verdict_notes_are_not_the_notes_of_the_finder():
    # compared by code only; the finder's notes are not read by the skeptic pass
    finder = {f["id"]: (f.get("skeptic") or {}).get("note") for f in committed_findings()}
    for finding_id, verdict in verdicts().items():
        assert verdict["note"] != finder[finding_id], finding_id


def test_added_terms_belong_to_known_findings():
    terms = load(samples.TERMS)
    ids = {f["id"] for f in evidence.load_findings(samples.COMMITTED_FINDINGS)}
    assert set(terms) == ids, "the skeptic added terms for every finding"
    for finding_id, added in terms.items():
        assert added and all(isinstance(t, str) and t.strip() for t in added), finding_id


def test_result_files_hold_no_price():
    for path in (samples.VERDICTS, samples.SUMMARY, samples.TERMS):
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        for word in ("unit_price", '"total"', "€", "EUR", "Einheitspreis:", "Gesamtbetrag:"):
            assert word not in text, "%s holds %s" % (os.path.basename(path), word)
