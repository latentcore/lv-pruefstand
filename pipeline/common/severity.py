"""Severity of a finding by fixed rules (MASTER_PLAN §7 "Şiddet", W15).

    python -m pipeline.common.severity <findings in> <items.json> <findings out>

The rules stand in docs/RISK_RULES.md; RULES below is the same table in the
same order, and a test compares the two. The first rule that fits decides.
The inputs are the ones the plan names and nothing else: the check of the
finding, the quantity concerned, the kind of the cited items, and whether the
matter stands only in a preliminary note. No rule reads a price or a total.

The rules are a proposal for the expert session; no expert has confirmed them.
"""
import argparse
import copy
import json
import math
import os
import sys
import tempfile

if __package__ in (None, ""):  # started as a file, not with -m
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pipeline.common import contract, quotes  # noqa: E402

LEVELS = ("high", "medium", "info")

# Check catalogue of MASTER_PLAN §7.
SIZED_CHECKS = ("X1", "X2", "X3", "S", "B4", "B5", "B6", "B8", "V1")
NOTE_CHECKS = ("B3", "B7", "B9", "B10", "B11", "B12", "V2")
SUM_CHECKS = ("B1", "B2")
KNOWN_CHECKS = SIZED_CHECKS + NOTE_CHECKS + SUM_CHECKS

# Quantity bands: large from, small below. Pieces have their own pair.
PIECE_UNITS = ("st", "stk", "stck", "stück")
LARGE_FROM = {"pieces": 10, "other": 100}
SMALL_BELOW = {"pieces": 2, "other": 10}

_NOT_IN_CONTRACT_SUM = ("optional", "alternative")


def _number(value):
    """value as a float when it is a finite number above 0, else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def band(quantity, unit):
    """"large", "small" or "middle" for one quantity with its unit; None without a quantity above 0."""
    number = _number(quantity)
    if number is None:
        return None
    name = unit.strip().lower().rstrip(".") if isinstance(unit, str) else ""
    group = "pieces" if name in PIECE_UNITS else "other"
    if number >= LARGE_FROM[group]:
        return "large"
    if number < SMALL_BELOW[group]:
        return "small"
    return "middle"


def facts(finding, cited_items):
    """The inputs of the rules: check, kinds of the cited items, band of the quantity concerned."""
    check = finding.get("check") if isinstance(finding, dict) else None
    items = [item for item in (cited_items or []) if isinstance(item, dict) and item.get("kind") != "heading"]
    kinds = [item.get("kind") for item in items]
    exposure = finding.get("exposure") if isinstance(finding, dict) else None
    exposure = exposure if isinstance(exposure, dict) else {}
    size = band(exposure.get("quantity"), exposure.get("unit"))
    if size is None:
        bands = [band(item.get("quantity"), item.get("unit")) for item in items if item.get("kind") == "normal"]
        bands = [entry for entry in bands if entry is not None]
        if "large" in bands:
            size = "large"
        elif bands and all(entry == "small" for entry in bands):
            size = "small"
        elif bands:
            size = "middle"
    return {"check": check, "kinds": kinds, "size": size}


def _only_preliminary_note(found):
    return bool(found["kinds"]) and all(kind == "preliminary_note" for kind in found["kinds"])


def _only_optional(found):
    others = [kind for kind in found["kinds"] if kind != "preliminary_note"]
    return bool(others) and all(kind in _NOT_IN_CONTRACT_SUM for kind in others)


# (number, level, the rule as docs/RISK_RULES.md words it, test on the facts)
RULES = (
    (1, "info", "the check is not in the catalogue (X1, X2, X3, S, B1 to B12, V1, V2)",
     lambda found: found["check"] not in KNOWN_CHECKS),
    (2, "info", "the check is B3, B7, B9, B10, B11, B12 or V2",
     lambda found: found["check"] in NOTE_CHECKS),
    (3, "high", "the check is B1 or B2",
     lambda found: found["check"] in SUM_CHECKS),
    (4, "medium", "at least one item is cited and every cited item is a Vorbemerkung (preliminary_note)",
     _only_preliminary_note),
    (5, "info", "at least one cited item is not a Vorbemerkung, and every such item is a Bedarfsposition "
                "or Wahlposition (optional, alternative)",
     _only_optional),
    (6, "high", "the quantity concerned is large",
     lambda found: found["size"] == "large"),
    (7, "medium", "a cited item is a Pauschale (lump_sum)",
     lambda found: "lump_sum" in found["kinds"]),
    (8, "medium", "the quantity concerned is unknown",
     lambda found: found["size"] is None),
    (9, "info", "the quantity concerned is small",
     lambda found: found["size"] == "small"),
    (10, "medium", "no rule above fits (the quantity concerned is between small and large)",
     lambda found: True),
)


def severity(finding, cited_items):
    """Return (level, number of the rule that decided it).

    finding: one record of findings.json. cited_items: the items.json records
    its sources cite (None entries and headings are skipped). Pure: nothing is
    read from disk and neither argument is changed.
    """
    found = facts(finding, cited_items)
    for number, level, _text, fits in RULES:
        if fits(found):
            return level, number
    raise AssertionError("the last rule fits every finding")


def index_items(items):
    """items.json records by (doc, item_no); one key may hold several records."""
    by_key = {}
    for item in items:
        if isinstance(item, dict):
            by_key.setdefault((item.get("doc"), item.get("item_no")), []).append(item)
    return by_key


def cited_items(finding, by_key):
    """One items.json record or None per source: the record whose text holds
    the quote, else the first that is not a heading, else the first."""
    cited = []
    sources = finding.get("sources") if isinstance(finding, dict) else None
    for source in sources if isinstance(sources, list) else []:
        if not isinstance(source, dict):
            cited.append(None)
            continue
        candidates = by_key.get((source.get("doc"), source.get("item_no")), [])
        quote = source.get("quote") if isinstance(source.get("quote"), str) else ""
        chosen = next((item for item in candidates
                       if quotes.quote_in_text(quote, quotes.item_text(item))), None)
        if chosen is None:
            chosen = next((item for item in candidates if item.get("kind") != "heading"), None)
        if chosen is None and candidates:
            chosen = candidates[0]
        cited.append(chosen)
    return cited


def apply(findings, items):
    """Copies of the findings with `severity` set by the rules; nothing else changes.

    Returns (new findings, list of (level, rule number) in the same order).
    """
    by_key = index_items(items)
    result, decided = [], []
    for finding in findings:
        level, number = severity(finding, cited_items(finding, by_key))
        changed = copy.deepcopy(finding)
        changed["severity"] = level
        result.append(changed)
        decided.append((level, number))
    return result, decided


def _read_json(path):
    with open(path, encoding="utf-8-sig") as handle:
        return json.load(handle)


def _write_json(path, data):
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    handle, temp_path = tempfile.mkstemp(dir=folder, prefix=".severity.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.write("\n")
        os.replace(temp_path, path)
    except BaseException:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.common.severity",
        description="Set `severity` of every finding by the fixed rules of docs/RISK_RULES.md.")
    parser.add_argument("findings_in", help="findings.json to read")
    parser.add_argument("items", help="items.json of the same project")
    parser.add_argument("findings_out", help="findings.json to write (may be the input file)")
    args = parser.parse_args(argv)
    try:
        findings = _read_json(args.findings_in)
        items = _read_json(args.items)
    except (OSError, ValueError) as error:
        print("cannot read the input: %s" % error, file=sys.stderr)
        return 2
    if not isinstance(findings, list) or not all(isinstance(entry, dict) for entry in findings):
        print("%s is not a list of findings" % args.findings_in, file=sys.stderr)
        return 2
    if not isinstance(items, list):
        print("%s is not a list of items" % args.items, file=sys.stderr)
        return 2
    result, decided = apply(findings, items)
    problems = contract.errors("findings", result)
    if problems:
        print("nothing written: the result breaks contract v1 (%d places), first: %s"
              % (len(problems), "; ".join(problems[:3])), file=sys.stderr)
        return 1
    _write_json(args.findings_out, result)
    levels = [level for level, _number_ in decided]
    changed = [(old, new, rule) for old, new, (_level, rule) in zip(findings, result, decided)
               if old.get("severity") != new["severity"]]
    print("findings: %d" % len(result))
    print(", ".join("%s: %d" % (level, levels.count(level)) for level in LEVELS))
    print("changed level against the input: %d of %d" % (len(changed), len(result)))
    for old, new, rule in changed:
        print("  %s: %s -> %s (rule %d)" % (new.get("id"), old.get("severity"), new["severity"], rule))
    return 0


if __name__ == "__main__":
    sys.exit(main())
