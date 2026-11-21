"""Base checks on numbers, units, quantities and item kinds: B3, B4, B5, B6, B10."""
import re
from collections import Counter

from pipeline.base import core
from pipeline.base.core import NOT_APPLICABLE


def number_key(item_no):
    """Item number as a tuple of integers ("1.2.30" -> (1, 2, 30)); an empty
    part counts as -1; None when a part is not a plain number ("10a")."""
    parts = []
    for part in item_no.split("."):
        part = part.strip()
        if not part:
            parts.append(-1)
        elif part.isdigit():
            parts.append(int(part))
        else:
            return None
    return tuple(parts)


def _numbering_step(groups):
    """The step most sibling numbers of the document follow (10 in "10, 20, 30"), or None."""
    diffs = Counter()
    for numbers in groups.values():
        diffs.update(b - a for a, b in zip(numbers, numbers[1:]))
    total = sum(diffs.values())
    if total < core.GAP_MIN_DIFFS:
        return None
    step, count = sorted(diffs.items(), key=lambda pair: (-pair[1], pair[0]))[0]
    return step if count * 2 > total else None


def b3(doc):
    """B3: item numbers of the positions: duplicate number, order, gap in the row."""
    numbered = [r for r in doc.positions if core.item_no(r).strip()]
    if not numbered:
        return NOT_APPLICABLE
    findings = []

    by_number = {}
    for record in numbered:
        by_number.setdefault(core.item_no(record), []).append(record)
    for item_no, records in by_number.items():
        if len(records) > 1:
            findings.append(core.make_finding(
                "B3", "duplicate_number", "medium", [doc.source(r) for r in records],
                "Die Positionsnummer %s ist in %s %d-mal vergeben." % (item_no, doc.name, len(records)),
                "Welche der Positionen mit der Nummer %s gilt, oder sind es verschiedene Leistungen?" % item_no))

    keyed = [(number_key(core.item_no(r)), r) for r in numbered]
    keyed = [(key, r) for key, r in keyed if key is not None]
    for (before_key, before), (key, record) in zip(keyed, keyed[1:]):
        if key < before_key:
            findings.append(core.make_finding(
                "B3", "number_out_of_order", "info", [doc.source(record), doc.source(before)],
                "Die %s steht nach der %s; die Nummern steigen an dieser Stelle nicht an."
                % (core.label(record), core.label(before)),
                "Ist die Reihenfolge der Positionen %s und %s gewollt?"
                % (core.item_no(before), core.item_no(record))))

    first_of, groups = {}, {}
    for key, record in keyed:
        first_of.setdefault(key, record)
    for key in first_of:
        groups.setdefault(key[:-1], []).append(key[-1])
    groups = dict((parent, sorted(numbers)) for parent, numbers in groups.items())
    step = _numbering_step(groups)
    if step:
        for parent, numbers in groups.items():
            for low, high in zip(numbers, numbers[1:]):
                if high - low >= 2 * step and (high - low) % step == 0 and (low - numbers[0]) % step == 0:
                    before, after = first_of[parent + (low,)], first_of[parent + (high,)]
                    findings.append(core.make_finding(
                        "B3", "number_gap", "info", [doc.source(before), doc.source(after)],
                        "Zwischen der %s und der %s fehlt mindestens eine Nummer; die Positionen "
                        "des Verzeichnisses sind sonst im Schritt %d nummeriert."
                        % (core.label(before), core.label(after), step),
                        "Fehlt zwischen den Positionen %s und %s eine Position?"
                        % (core.item_no(before), core.item_no(after))))
    return core.collect(findings)


def _numbers_text(records):
    return ", ".join(core.item_no(r) or "ohne Nummer" for r in records)


def b4(doc):
    """B4: repeated item: the same text (short and long) and the same unit twice in one document.

    A text without a word (a row of dots) is not compared."""
    with_text = [r for r in doc.positions if core.words(core.full_text(r))]
    if not with_text:
        return NOT_APPLICABLE
    groups = {}
    for record in with_text:
        key = (core.full_text(record).casefold(), core.unit_key(record.get("unit")))
        groups.setdefault(key, []).append(record)
    findings = []
    for records in groups.values():
        if len(records) > 1:
            findings.append(core.make_finding(
                "B4", "repeated_item", "medium", [doc.source(r) for r in records],
                "Die Positionen %s in %s haben denselben Text und dieselbe Einheit."
                % (_numbers_text(records), doc.name),
                "Ist die Leistung der Positionen %s mehrfach gewollt, oder ist sie doppelt ausgeschrieben?"
                % _numbers_text(records)))
    return core.collect(findings)


def b5(doc):
    """B5: unit missing, not known, or different for the same work (same short text)."""
    if not any(core.clean_unit(r.get("unit")) for r in doc.positions):
        return NOT_APPLICABLE
    findings = []
    for record in doc.positions:
        name = core.label(record)
        if not core.clean_unit(record.get("unit")):
            if record.get("kind") == "lump_sum":
                continue  # the kind says it: a lump sum needs no unit
            findings.append(core.make_finding(
                "B5", "unit_missing", "high", [doc.source(record)],
                "Die %s hat keine Einheit." % name,
                "In welcher Einheit wird die %s abgerechnet?" % name, record=record))
        elif core.canonical_unit(record.get("unit")) is None:
            unit = record["unit"].strip()
            findings.append(core.make_finding(
                "B5", "unit_unknown", "info", [doc.source(record)],
                "Die Einheit «%s» der %s steht nicht in der Liste der bekannten Einheiten." % (unit, name),
                "Was bedeutet die Einheit «%s» der %s?" % (unit, name), record=record))
    groups = {}
    for record in doc.positions:
        short = core.quotes.normalize(record.get("short_text")).casefold()
        if short and core.clean_unit(record.get("unit")):
            groups.setdefault(short, []).append(record)
    for records in groups.values():
        units = []
        for record in records:
            if core.unit_key(record.get("unit")) not in [core.unit_key(u) for u in units]:
                units.append(record["unit"].strip())
        if len(units) > 1:
            findings.append(core.make_finding(
                "B5", "unit_differs", "medium", [doc.source(r) for r in records],
                "Die Positionen %s in %s haben denselben Kurztext, aber verschiedene Einheiten (%s)."
                % (_numbers_text(records), doc.name, ", ".join(units)),
                "Ist die verschiedene Einheit bei den Positionen %s gewollt?" % _numbers_text(records)))
    return core.collect(findings)


def b6(doc):
    """B6: quantity missing, zero, negative, or 10 times off its sibling items."""
    if not any(core.number(r, "quantity") is not None for r in doc.positions):
        return NOT_APPLICABLE
    findings = []
    for record in doc.positions:
        quantity = core.number(record, "quantity")
        name = core.label(record)
        is_lump = record.get("kind") == "lump_sum" or core.canonical_unit(record.get("unit")) == core.LUMP_UNIT
        if quantity is None:
            if is_lump:
                continue  # a lump sum counts once
            type_, text = "quantity_missing", "Die %s hat keine Menge." % name
        elif quantity == 0:
            type_, text = "quantity_zero", "Die Menge der %s ist null." % name
        elif quantity < 0:
            type_, text = "quantity_negative", "Die Menge der %s ist negativ." % name
        else:
            continue
        findings.append(core.make_finding(
            "B6", type_, "high", [doc.source(record)], text,
            "Welche Menge gilt für die %s?" % name, record=record))
    for record, side in core.outliers(doc, lambda r: core.number(r, "quantity")):
        name = core.label(record)
        direction = "über" if side == "high" else "unter"
        findings.append(core.make_finding(
            "B6", "quantity_outlier", "info", [doc.source(record)],
            "Die Menge der %s liegt mindestens um den Faktor 10 %s der mittleren Menge der anderen "
            "Positionen desselben Abschnitts mit gleicher Einheit." % (name, direction),
            "Ist die Menge der %s richtig (Einheit, Kommastelle)?" % name, record=record))
    return core.collect(findings)


_FLAG_WORD = re.compile(r"(?im)^\W*(Bedarfs|Eventual|Wahl|Alternativ)pos(?:ition|\.)")
_FLAG_KIND = {"bedarfs": "optional", "eventual": "optional", "wahl": "alternative", "alternativ": "alternative"}
_FLAG_TEXT = {
    "optional": ("optional_item", "Bedarfsposition",
                 "Die %s ist eine Bedarfsposition; sie wird nur auf Anordnung ausgeführt.",
                 "Wird die %s beauftragt, und mit welcher Menge ist zu rechnen?"),
    "alternative": ("alternative_item", "Wahlposition",
                    "Die %s ist eine Wahlposition; sie ersetzt eine andere Position, wenn sie gewählt wird.",
                    "Wird die %s anstelle der Grundposition ausgeführt, und wann fällt die Entscheidung?"),
}


def b10(doc):
    """B10: flags of optional (Bedarfsposition) and alternative (Wahlposition) items.

    Every such item gets a flag. An item whose text opens a line with one of
    these words but whose kind does not say so gets a "flag_missing" finding.
    """
    if not doc.positions:
        return NOT_APPLICABLE
    findings = []
    for record in doc.positions:
        name = core.label(record)
        kind = record.get("kind")
        if kind in _FLAG_TEXT:
            type_, _, text, question = _FLAG_TEXT[kind]
            findings.append(core.make_finding(
                "B10", type_, "info", [doc.source(record)], text % name, question % name, record=record))
            continue
        raw = "%s\n%s" % (record.get("short_text") or "", record.get("long_text") or "")
        match = _FLAG_WORD.search(raw)
        if match:
            word = _FLAG_TEXT[_FLAG_KIND[match.group(1).lower()]][1]
            normal = core.full_text(record)
            found = re.search(r"(?i)(Bedarfs|Eventual|Wahl|Alternativ)pos(?:ition|\.)", normal)
            quote = core.snippet(normal, found.start(), found.end()) if found else None
            findings.append(core.make_finding(
                "B10", "flag_missing", "medium", [doc.source(record, quote)],
                "Der Text der %s nennt sie %s, sie ist aber nicht als solche gekennzeichnet." % (name, word),
                "Ist die %s eine %s oder eine Grundposition?" % (name, word), record=record))
    return core.collect(findings)
