"""Hand-written items for the bench tests. No real tender text, no real price."""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DOC = "BENCH_T1"
WORK = ("Mauerwerk herstellen", "Beton einbauen", "Schalung stellen", "Bewehrung verlegen",
        "Estrich einbringen", "Putz auftragen", "Fenster einsetzen", "Türen montieren",
        "Dämmung anbringen", "Abdichtung aufbringen", "Fliesen verlegen", "Anstrich ausführen")


def item(item_no, short, kind="normal", quantity=10.0, unit="m2", unit_price=2.0, total=None, doc=DOC):
    """One items.json record in contract v1 shape; total = quantity x unit price when not given."""
    if total is None and quantity is not None and unit_price is not None:
        total = round(quantity * unit_price, 2)
    return {
        "doc": doc, "project": "T", "trade": "Test", "format": "gaeb90", "stage": "86",
        "item_no": item_no, "kind": kind, "section": item_no.rpartition(".")[0],
        "short_text": short, "long_text": "", "quantity": quantity, "unit": unit,
        "unit_price": unit_price, "total": total, "page": None, "line": 1,
        "pre_trade_text": None, "post_trade_text": None,
    }


def heading(item_no, short, doc=DOC):
    return item(item_no, short, kind="heading", quantity=None, unit=None, unit_price=None, doc=doc)


def clean_list(doc=DOC, per_section=6):
    """Two sections, items numbered in steps of 10, every item with quantity, unit, unit price and total.

    Quantities of one section and unit lie close together, so no base check has a reason to speak."""
    records, names = [], iter(WORK)
    for section, unit in (("01", "m2"), ("02", "m")):
        records.append(heading(section, "Abschnitt %s Rohbau" % section, doc=doc))
        for number in range(1, per_section + 1):
            records.append(item("%s.%d" % (section, 10 * number), "%s Bauteil %s" % (next(names), section),
                                quantity=10.0 + number, unit=unit, unit_price=2.0 + number, doc=doc))
    return records


def findable_list(doc=DOC, per_section=8):
    """Two sections of equal quantities: a quantity ×10 stands out against its siblings (B6)."""
    records = []
    for section, unit in (("01", "m2"), ("02", "m")):
        records.append(heading(section, "Abschnitt %s Ausbau" % section, doc=doc))
        for number in range(1, per_section + 1):
            records.append(item("%s.%d" % (section, 10 * number), "Leistung %d im Abschnitt %s" % (number, section),
                                quantity=10.0, unit=unit, unit_price=3.0, doc=doc))
    return records


def positions(records):
    return [r for r in records if r["kind"] not in ("heading", "preliminary_note")]


def context_with(records_by_file, data="no-data-folder", reviews="no-reviews-folder", findings=None):
    """A measure.Context whose GAEB files are the given records; every other file is absent."""
    import copy

    from bench import measure

    class SampleContext(measure.Context):
        def has(self, file_name):
            return file_name in records_by_file

        def gaeb(self, file_name):
            return copy.deepcopy(records_by_file[file_name])

    return SampleContext(data=data, reviews=reviews, findings=findings)


def numbers_of(value):
    """Every number in a JSON value, with the path of keys that leads to it."""
    found = []

    def walk(node, path):
        if isinstance(node, dict):
            for key, child in node.items():
                walk(child, path + (key,))
        elif isinstance(node, list):
            for child in node:
                walk(child, path)
        elif isinstance(node, float):
            found.append((path, node))
    walk(value, ())
    return found


FORBIDDEN_KEY_PARTS = ("price", "total", "amount", "sum", "eur", "betrag", "preis", "quote")
FLOAT_KEYS = ("median_seconds", "read_median_seconds")


def price_leaks(data):
    """Why a bench.json could hold a price: a key that names one, or a float outside the seconds."""
    leaks = []

    def walk(node, path):
        if isinstance(node, dict):
            for key, child in node.items():
                if any(part in key.lower() for part in FORBIDDEN_KEY_PARTS) and key not in ALLOWED_KEYS:
                    leaks.append("key %s" % "/".join(path + (key,)))
                walk(child, path + (key,))
        elif isinstance(node, list):
            for child in node:
                walk(child, path)
        elif isinstance(node, float) and (not path or path[-1] not in FLOAT_KEYS):
            leaks.append("float at %s" % "/".join(path))
    walk(data, ())
    return leaks


# Keys that hold a count of quotes, of price comparisons or of totals compared; never a value.
ALLOWED_KEYS = ("quotes", "unit_prices_equal", "unit_prices_compared", "totals_equal", "totals_compared",
                "prices_measurable", "prices_reason", "prices_reason_de", "prices_percent_tenths",
                "summary_pages")
