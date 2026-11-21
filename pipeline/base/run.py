"""Run the twelve base checks on one items.json.

    python -m pipeline.base.run <items.json> <findings out>

Writes the findings in contract v1 shape and prints one line per check:
check, number of findings, and "not applicable" where a document lacks the
field the check needs. No line and no finding holds a price or a total.
"""
import argparse
import json
import os
import sys

from pipeline.base import core, prices, structure, text
from pipeline.common import contract, quotes

CHECKS = (
    ("B1", "quantity x unit price = total", prices.b1),
    ("B2", "subtotals and grand total", prices.b2),
    ("B3", "item number order, gaps, duplicates", structure.b3),
    ("B4", "repeated item", structure.b4),
    ("B5", "unit missing, unknown, different", structure.b5),
    ("B6", "quantity missing, zero, negative, 10 times off", structure.b6),
    ("B7", "unusual unit price (question)", prices.b7),
    ("B8", "empty or very short description", text.b8),
    ("B9", "share of lump-sum items", prices.b9),
    ("B10", "optional and alternative items", structure.b10),
    ("B11", "vague phrases", text.b11),
    ("B12", "product name without 'oder gleichwertig'", text.b12),
)


def run_all(items):
    """Run B1 to B12 on items.json records of one or more documents.

    Returns (findings, summary). findings: contract v1 records whose quotes
    all stand in the cited item (quotes_verified true), in check order.
    summary: one dict per check with "check", "title", "findings",
    "documents", "not_applicable" (document names), "dropped" (findings whose
    quote was not found; they are not written), "same_id" (findings that got
    an id already taken; the first one stays) and "notes" (other counts).
    """
    records = [record for record in items if isinstance(record, dict)]
    docs = core.split_docs(records)
    findings, summary, seen = [], [], set()
    for check, title, function in CHECKS:
        found, not_applicable, notes = [], [], {}
        for doc in docs:
            outcome = function(doc)
            if not outcome.applicable:
                not_applicable.append(doc.name)
                continue
            found.extend(outcome.findings)
            for key, value in outcome.notes.items():
                notes[key] = notes.get(key, 0) + value
        kept, dropped = quotes.filter_findings(found, records)
        unique = []
        for finding in kept:
            if finding["id"] not in seen:
                seen.add(finding["id"])
                unique.append(finding)
        findings.extend(unique)
        summary.append({
            "check": check, "title": title, "findings": len(unique), "documents": len(docs),
            "not_applicable": not_applicable, "dropped": len(dropped),
            "same_id": len(kept) - len(unique), "notes": notes,
        })
    return findings, summary


def summary_line(entry):
    """One printed line for a check."""
    parts = ["%-3s" % entry["check"], "findings=%d" % entry["findings"]]
    missing, total = len(entry["not_applicable"]), entry["documents"]
    if not total:
        parts.append("not applicable (no documents)")
    elif missing == total:
        parts.append("not applicable (%d of %d documents)" % (missing, total))
    elif missing:
        parts.append("not applicable for %d of %d documents" % (missing, total))
    for key in ("dropped", "same_id"):
        if entry[key]:
            parts.append("%s=%d" % (key, entry[key]))
    for key in sorted(entry["notes"]):
        parts.append("%s=%d" % (key, entry["notes"][key]))
    return "  ".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pipeline.base.run", description=__doc__.split("\n")[0])
    parser.add_argument("items", help="items.json of one project (contract v1)")
    parser.add_argument("out", help="file to write the findings to (contract v1)")
    args = parser.parse_args(argv)
    try:
        with open(args.items, encoding="utf-8") as handle:
            items = json.load(handle)
    except (OSError, ValueError) as error:
        print("cannot read %s: %s" % (args.items, error), file=sys.stderr)
        return 2
    if not isinstance(items, list):
        print("%s does not hold a list" % args.items, file=sys.stderr)
        return 2
    findings, summary = run_all(items)
    contract.check("findings", findings)
    folder = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(folder, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(findings, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    for entry in summary:
        print(summary_line(entry))
    return 0


if __name__ == "__main__":
    sys.exit(main())
