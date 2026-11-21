"""Base checks that use prices: B1, B2, B7, B9.

Prices are used by code only. No explanation, question or quote of these
checks holds a unit price or a total; quotes are item text.
"""
from decimal import Decimal

from pipeline.base import core
from pipeline.base.core import NOT_APPLICABLE, Outcome


def _priced(record):
    return core.number(record, "unit_price") is not None and core.number(record, "total") is not None


def _quantity(record):
    """Quantity for the product; a lump-sum item without a quantity counts once."""
    quantity = core.number(record, "quantity")
    if quantity is None and (record.get("kind") == "lump_sum"
                             or core.canonical_unit(record.get("unit")) == core.LUMP_UNIT):
        return Decimal(1)
    return quantity


def b1(doc):
    """B1: quantity x unit price = total, to half a cent.

    A priced item without a quantity cannot be checked; it is counted as
    priced_without_quantity. An optional or alternative item with a unit
    price and a total of zero is in order: its total is not carried."""
    priced = [r for r in doc.positions if _priced(r)]
    if not any(_quantity(r) is not None for r in priced):
        return NOT_APPLICABLE  # no prices, or prices without quantities (an offer file without them)
    findings, no_quantity = [], 0
    for record in priced:
        quantity = _quantity(record)
        if quantity is None:
            no_quantity += 1
            continue
        total = core.number(record, "total")
        if abs(quantity * core.number(record, "unit_price") - total) <= core.PRICE_TOLERANCE:
            continue
        if record.get("kind") in core.NOT_IN_SUM and total == 0:
            continue  # unit price only: the total of such an item is not carried
        name = core.label(record)
        findings.append(core.make_finding(
            "B1", "arithmetic_error", "high", [doc.source(record)],
            "Menge mal Einheitspreis ergibt nicht den Gesamtbetrag der %s." % name,
            "Welcher Wert der %s ist richtig: Menge, Einheitspreis oder Gesamtbetrag?" % name,
            record=record))
    outcome = core.collect(findings)
    if no_quantity:
        outcome.notes["priced_without_quantity"] = no_quantity
    return outcome


def _sum(records):
    return sum((core.number(r, "total") or Decimal(0) for r in records), Decimal(0))


def b2(doc):
    """B2: a stated section sum or grand total equals the sum of the item totals.

    A stated sum is the `total` of a heading record: of its section, or of the
    whole document when the heading has no number. A sum over a base item
    without a total cannot be checked; it is counted as sum_not_checkable.
    """
    stated = [h for h in doc.headings if core.number(h, "total") is not None]
    if not stated:
        return NOT_APPLICABLE
    findings, not_checkable = [], 0
    for heading in stated:
        section = core.item_no(heading)
        below = [r for r in doc.positions if core.in_section(r, section)]
        in_sum = [r for r in below if r.get("kind") not in core.NOT_IN_SUM]
        if any(core.number(r, "total") is None for r in in_sum):
            not_checkable += 1
            continue
        base = _sum(in_sum)
        with_optional = base + _sum(r for r in below if r.get("kind") == "optional")
        total = core.number(heading, "total")
        if min(abs(total - base), abs(total - with_optional)) <= core.PRICE_TOLERANCE:
            continue
        if section:
            where, what = "im Abschnitt %s" % section, "der ausgewiesenen Abschnittssumme"
        else:
            where, what = "des Verzeichnisses", "der ausgewiesenen Gesamtsumme"
        findings.append(core.make_finding(
            "B2", "sum_mismatch", "high", [doc.source(heading)],
            "Die Summe der Gesamtbeträge der Positionen %s stimmt nicht mit %s überein "
            "(geprüft ohne und mit Bedarfspositionen, ohne Wahlpositionen)." % (where, what),
            "Welche Positionen zählen zur Summe %s, und welcher Betrag ist richtig?" % where))
    outcome = core.collect(findings)
    if not_checkable:
        outcome.notes["sum_not_checkable"] = not_checkable
    return outcome


def b7(doc):
    """B7: unusual unit price. A question only, never a statement that the price is wrong."""
    priced = [r for r in doc.positions if core.number(r, "unit_price") is not None]
    if not priced:
        return NOT_APPLICABLE
    findings = []
    for record in priced:
        if core.number(record, "unit_price") <= 0:
            name = core.label(record)
            findings.append(core.make_finding(
                "B7", "unit_price_not_positive", "info", [doc.source(record)],
                "Für die %s ist kein positiver Einheitspreis angegeben." % name,
                "Ist die Leistung der %s in einer anderen Position enthalten, oder fehlt der Preis?" % name,
                record=record))
    for record, side in core.outliers(doc, lambda r: core.number(r, "unit_price")):
        name = core.label(record)
        direction = "über" if side == "high" else "unter"
        findings.append(core.make_finding(
            "B7", "unit_price_outlier", "info", [doc.source(record)],
            "Der Einheitspreis der %s liegt mindestens um den Faktor 10 %s dem mittleren Einheitspreis "
            "der anderen Positionen desselben Abschnitts mit gleicher Einheit." % (name, direction),
            "Ist der Einheitspreis der %s so gewollt (Einheit, Kommastelle)?" % name,
            record=record))
    return core.collect(findings)


def _is_lump(record):
    return record.get("kind") == "lump_sum" or core.canonical_unit(record.get("unit")) == core.LUMP_UNIT


def b9(doc):
    """B9: share of lump-sum (psch) items, by count and by value.

    The share by value is taken only when every base item has a total;
    otherwise the sum is not known and the document counts as no_totals."""
    positions = doc.positions
    if not positions:
        return NOT_APPLICABLE
    lump = [r for r in positions if _is_lump(r)]
    by_count = Decimal(len(lump)) / Decimal(len(positions))
    in_sum = [r for r in positions if r.get("kind") not in core.NOT_IN_SUM]
    has_totals = bool(in_sum) and all(core.number(r, "total") is not None for r in in_sum)
    total = _sum(in_sum)
    by_value = _sum(r for r in in_sum if _is_lump(r)) / total if has_totals and total > 0 else None
    notes = {} if has_totals else {"no_totals": 1}
    count_hit = by_count >= core.LUMP_SHARE
    value_hit = by_value is not None and by_value >= core.LUMP_SHARE
    if not lump or not (count_hit or value_hit):
        return Outcome(notes=notes)
    threshold = int(core.LUMP_SHARE * 100)
    text = "%d von %d Positionen in %s sind Pauschalpositionen." % (len(lump), len(positions), doc.name)
    if count_hit:
        text += " Ihr Anteil nach Anzahl erreicht die Schwelle von %d %%." % threshold
    if value_hit:
        text += " Ihr Anteil an der Summe der Gesamtbeträge erreicht die Schwelle von %d %%." % threshold
    sources = [doc.source(r) for r in lump[:core.LUMP_MAX_SOURCES]]
    outcome = core.collect([core.make_finding(
        "B9", "lump_sum_share", "medium", sources, text,
        "Lassen sich die Pauschalpositionen in %s nach Menge und Einheit aufgliedern?" % doc.name)])
    outcome.notes.update(notes)
    return outcome
