"""Write the findings with the skeptic field replaced by the independent verdict.

    python -m pipeline.skeptic.merge <findings in> <verdicts> <findings out>

Only the `skeptic` field of each finding changes; no finding is dropped, added
or reordered, and no other key is touched (§8: the skeptic writes only the
skeptic field). The verdicts file is an object keyed by finding id; each
verdict needs `status` (survived, weakened or refuted) and a `note`. The
result must pass the findings schema of contract/.
"""
import argparse
import copy
import sys

from pipeline.common import contract
from pipeline.skeptic import STATUSES
from pipeline.skeptic.evidence import read_json, write_json
from pipeline.skeptic.rules import RANK


class MergeError(ValueError):
    """Findings and verdicts do not fit together."""


def verdict_errors(finding_id, verdict):
    errors = []
    if not isinstance(verdict, dict):
        return ["%s: verdict is not an object" % finding_id]
    status = verdict.get("status")
    if status not in STATUSES:
        errors.append("%s: status %r is not one of %s" % (finding_id, status, ", ".join(STATUSES)))
    note = verdict.get("note")
    if not isinstance(note, str) or not note.strip():
        errors.append("%s: note is empty" % finding_id)
    agent_status = verdict.get("agent_status")
    if agent_status is not None:
        if agent_status not in STATUSES:
            errors.append("%s: agent_status %r is not one of %s" % (finding_id, agent_status, ", ".join(STATUSES)))
        elif status in STATUSES and RANK[status] < RANK[agent_status]:
            errors.append("%s: status %s is better than agent_status %s; a rule may only lower"
                          % (finding_id, status, agent_status))
    return errors


def merge(findings, verdicts):
    """Copies of the findings with `skeptic` set to the verdict of the same id.

    Raises MergeError when a finding has no verdict, a verdict has no finding,
    an id stands twice, or a verdict is not filled with an allowed status.
    """
    if not isinstance(findings, list) or not isinstance(verdicts, dict):
        raise MergeError("findings must be a list and verdicts an object keyed by finding id")
    ids = [finding.get("id") for finding in findings]
    errors = ["%s: id stands twice in the findings" % i for i in sorted({i for i in ids if ids.count(i) > 1})]
    errors += ["%s: finding has no verdict" % i for i in ids if i not in verdicts]
    errors += ["%s: verdict has no finding" % i for i in sorted(set(verdicts) - set(ids))]
    for finding_id in ids:
        if finding_id in verdicts:
            errors += verdict_errors(finding_id, verdicts[finding_id])
    if errors:
        raise MergeError("; ".join(errors))
    merged = []
    for finding in findings:
        out = copy.deepcopy(finding)
        out["skeptic"] = copy.deepcopy(verdicts[finding["id"]])
        merged.append(out)
    return merged


def status_counts(findings):
    """Number of findings per skeptic status, every allowed status listed."""
    counts = {status: 0 for status in STATUSES}
    for finding in findings:
        counts[finding["skeptic"]["status"]] += 1
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pipeline.skeptic.merge",
                                     description="Replace the skeptic field of each finding by the verdict.")
    parser.add_argument("findings_in", help="findings.json of the finder")
    parser.add_argument("verdicts", help="verdicts keyed by finding id")
    parser.add_argument("findings_out", help="findings.json to write, e.g. out/<project>/findings.json")
    args = parser.parse_args(argv)
    try:
        merged = merge(read_json(args.findings_in), read_json(args.verdicts))
        contract.check("findings", merged)
    except (MergeError, contract.ContractError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 1
    write_json(args.findings_out, merged)
    counts = status_counts(merged)
    print("%d findings written to %s: %s" % (
        len(merged), args.findings_out, ", ".join("%d %s" % (counts[s], s) for s in STATUSES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
