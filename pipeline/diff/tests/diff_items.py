"""Hand-written synthetic items for the W13 tests (no organizer data)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from pipeline.lv import model  # noqa: E402


def item(item_no, short="Rohr DN 100 liefern", long="Rohr liefern und verlegen.", quantity=2.0,
         unit="m", doc="A.X83", kind="normal", **more):
    values = dict(doc=doc, project="P1", trade="Trade", format="gaebxml", stage="83",
                  item_no=item_no, kind=kind, short_text=short, long_text=long,
                  quantity=quantity, unit=unit)
    values.update(more)
    return model.make_item(**values)


def heading(item_no, title, doc="A.X83"):
    return item(item_no, short=title, long="", quantity=None, unit=None, doc=doc, kind="heading")


def tender():
    """Three items in one section."""
    return [heading("01", "Rohre"),
            item("01.0010", "Rohr DN 100 liefern", "Rohr DN 100 liefern und verlegen.", 10.0, "m"),
            item("01.0020", "Bogen DN 100", "Bogen 90 Grad liefern.", 4.0, "St"),
            item("01.0030", "Schieber DN 100", "Schieber mit Handrad liefern.", 1.0, "St")]


def order(changes=None, drop=(), extra=()):
    """The tender as an order in another number writing (1.10 for 01.0010);
    `changes` maps a number to changed fields, `drop` removes numbers,
    `extra` appends items."""
    numbers = {"01.0010": "1.10", "01.0020": "1.20", "01.0030": "1.30"}
    out = [heading("1", "Rohre", doc="B.D86")]
    for source in tender()[1:]:
        if source["item_no"] in drop:
            continue
        values = dict(short=source["short_text"], long=source["long_text"],
                      quantity=source["quantity"], unit=source["unit"])
        values.update((changes or {}).get(source["item_no"], {}))
        out.append(item(numbers[source["item_no"]], doc="B.D86", format="gaeb90", stage="86",
                        **values))
    return out + list(extra)
