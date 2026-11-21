"""M7: plant errors in the records of a clean GAEB file and see which ones the base checks name.

The rule is docs/PREREG.md ("M7, seeded errors"). Each error is planted alone
in its own copy of the records; the 12 base checks run on the copy; a planted
error counts as found only when a finding of the fitting check and type names
the item and the unchanged records have no such finding for it.

Prices are touched by code only. What leaves this module: per type the number
planted and found, and the item numbers. Never a price, a total or a sum.
"""
import copy
import random
from decimal import ROUND_DOWN, Decimal

from pipeline.base import core, structure
from pipeline.base.run import run_all

from bench import prereg

CENT = Decimal("0.01")
ONE = Decimal("1.00")
TEN_PERCENT_UP = Decimal("1.1")

# key, name in the table, fitting (check, type) pairs; type None = any type of the check.
TYPES = (
    ("quantity_x10", "quantity ×10", (("B6", "quantity_outlier"),)),
    ("unit_change", "unit change", (("B5", None),)),
    ("corrupted_amount", "corrupted amount", (("B1", "arithmetic_error"),)),
    ("corrupted_total", "corrupted total", (("B2", "sum_mismatch"),)),
    ("deleted_item", "deleted item", (("B3", "number_gap"),)),
    ("duplicated_item", "duplicated item", (("B3", "duplicate_number"), ("B4", "repeated_item"))),
)
X_NOT_MEASURED = ("not measured: finding a deleted or changed item of a cross-list finding again "
                  "needs a new model run, and the bench never runs a model")


def _position(record):
    return record.get("kind") not in core.NOT_A_POSITION


def _has_text(value):
    return isinstance(value, str) and bool(value.strip())


def _cut_to_cents(value):
    return float((value * TEN_PERCENT_UP).quantize(CENT, rounding=ROUND_DOWN))


def _in_sum(records, heading):
    """The base items below a heading (not optional, not alternative), as B2 takes them."""
    section = core.item_no(heading)
    below = [r for r in records if _position(r) and core.in_section(r, section)]
    return [r for r in below if r.get("kind") not in core.NOT_IN_SUM]


def _section_sum(records, heading):
    """Sum of the totals below a heading, or None when it cannot be built."""
    members = _in_sum(records, heading)
    if not members or any(core.number(r, "total") is None for r in members):
        return None
    return sum((core.number(r, "total") for r in members), Decimal(0))


def _units(records):
    """The units of the positions as written, sorted, each once."""
    return sorted(set(r["unit"].strip() for r in records if _position(r) and _has_text(r.get("unit"))))


def _next_unit(records, unit):
    """The next unit after this one in the sorted list that is a different unit; None when there is none."""
    units = _units(records)
    if unit.strip() not in units:
        return None
    start = units.index(unit.strip())
    for step in range(1, len(units)):
        other = units[(start + step) % len(units)]
        if core.unit_key(other) != core.unit_key(unit):
            return other
    return None


def eligible(records, type_key):
    """Indexes of the records an error of this type can be planted in, in file order."""
    found = []
    for index, record in enumerate(records):
        kind = record.get("kind")
        quantity, price, total = (core.number(record, key) for key in ("quantity", "unit_price", "total"))
        if type_key == "quantity_x10":
            fits = kind == "normal" and quantity is not None and quantity > 0 and None not in (price, total)
        elif type_key == "unit_change":
            fits = (kind == "normal" and _has_text(record.get("unit"))
                    and _next_unit(records, record["unit"]) is not None)
        elif type_key == "corrupted_amount":
            fits = kind == "normal" and None not in (quantity, price, total) and total >= ONE
        elif type_key == "corrupted_total":
            fits = False
            if kind == "heading" and core.item_no(record).strip():
                section_sum = _section_sum(records, record)
                fits = section_sum is not None and section_sum >= ONE
        elif type_key in ("deleted_item", "duplicated_item"):
            fits = _position(record)
        else:
            raise ValueError("unknown error type %r" % type_key)
        if fits:
            found.append(index)
    return found


def plant(records, type_key, index):
    """A copy of the records with one error of this type planted in the record at index."""
    changed = copy.deepcopy(records)
    record = changed[index]
    if type_key == "quantity_x10":
        quantity = core.number(record, "quantity") * 10
        record["quantity"] = float(quantity)
        record["total"] = float((quantity * core.number(record, "unit_price")).quantize(CENT))
    elif type_key == "unit_change":
        record["unit"] = _next_unit(records, record["unit"])
    elif type_key == "corrupted_amount":
        record["total"] = _cut_to_cents(core.number(record, "total"))
    elif type_key == "corrupted_total":
        record["total"] = _cut_to_cents(_section_sum(changed, record))
    elif type_key == "deleted_item":
        del changed[index]
    elif type_key == "duplicated_item":
        changed.insert(index + 1, copy.deepcopy(record))
    else:
        raise ValueError("unknown error type %r" % type_key)
    return changed


def _names(finding, type_key, item_no):
    """True when the finding names the item the error was planted in."""
    cited = [source.get("item_no") for source in finding.get("sources") or []]
    if type_key != "deleted_item":
        return item_no in cited
    key = structure.number_key(item_no)
    keys = [structure.number_key(number) for number in cited if isinstance(number, str)]
    if key is None or len(keys) != 2 or None in keys:
        return False
    return min(keys) < key < max(keys)


def fitting(findings, type_key, item_no):
    """The (check, type) pairs of the findings that fit this error type and name the item."""
    pairs = dict(TYPES_BY_KEY[type_key])
    hits = set()
    for finding in findings:
        check, type_ = finding.get("check"), finding.get("type")
        if check in pairs and pairs[check] in (None, type_) and _names(finding, type_key, item_no):
            hits.add((check, type_))
    return hits


TYPES_BY_KEY = dict((key, pairs) for key, _name, pairs in TYPES)


def draw(records, seed=prereg.SEED, per_type=prereg.M7_PER_TYPE):
    """The plan: per type, in the order of TYPES, the indexes drawn with the seed, in file order."""
    generator = random.Random(seed)
    plan = []
    for key, _name, _pairs in TYPES:
        candidates = eligible(records, key)
        chosen = sorted(generator.sample(candidates, min(per_type, len(candidates))))
        plan.append((key, len(candidates), chosen))
    return plan


def measure(records, seed=prereg.SEED, per_type=prereg.M7_PER_TYPE, checks=run_all):
    """Plant and count. records: the items of one document.

    Returns {"types": [{"type", "name", "eligible", "planted", "found", "missed_items"}],
    "planted", "found"}. checks: the function that runs the base checks (run_all).
    """
    baseline, _summary = checks(copy.deepcopy(records))
    types, planted_all, found_all = [], 0, 0
    for (key, name, _pairs), (_key, candidates, chosen) in zip(TYPES, draw(records, seed, per_type)):
        found, missed = 0, []
        for index in chosen:
            item_no = core.item_no(records[index])
            findings, _summary = checks(plant(records, key, index))
            if fitting(findings, key, item_no) and not fitting(baseline, key, item_no):
                found += 1
            else:
                missed.append(item_no)
        types.append({"type": key, "name": name, "eligible": candidates, "planted": len(chosen),
                      "found": found, "missed_items": missed})
        planted_all += len(chosen)
        found_all += found
    return {"types": types, "planted": planted_all, "found": found_all}
