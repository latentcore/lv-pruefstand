"""Synthetic items and findings for the tests of pipeline/skeptic. No organizer data."""
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
COMMITTED_FINDINGS = os.path.join(ROOT, "pipeline", "cross", "results", "79-222", "findings.json")
RESULTS = os.path.join(ROOT, "pipeline", "skeptic", "results", "79-222")
VERDICTS = os.path.join(RESULTS, "verdicts.json")
SUMMARY = os.path.join(RESULTS, "summary.json")
TERMS = os.path.join(RESULTS, "terms.json")
REAL_ITEMS = os.path.join(ROOT, "out", "79-222", "items.json")
REAL_TEXT_DIR = os.path.join(ROOT, "cache", "79-222_text")


def item(doc, item_no, short_text, long_text="", page=1, kind="normal", quantity=None, unit=None, **more):
    record = {"doc": doc, "project": "11-111", "trade": "Test", "format": "pdf", "stage": "anfrage",
              "item_no": item_no, "kind": kind, "section": "", "short_text": short_text,
              "long_text": long_text, "quantity": quantity, "unit": unit, "unit_price": 12.5,
              "total": 437.5, "page": page, "line": None, "pre_trade_text": None,
              "post_trade_text": None}
    record.update(more)
    return record


def items():
    return [
        item("LV_91", "1", "Estricharbeiten", kind="heading"),
        item("LV_91", "", "Vorbemerkung",
             "Die Randdämmstreifen werden vom AN Estrich geliefert und eingebaut.",
             kind="preliminary_note"),
        item("LV_91", "1.10", "Zementestrich, 65 mm",
             "schwimmender Estrich auf Wärme-\ndämmung, Nenndicke 65 mm\nEinbauort: UG",
             page=2, quantity=35.0, unit="m2"),
        item("LV_92", "2.10", "Randdämmstreifen",
             "Randdämmstreifen an allen aufgehenden Bauteilen liefern und einbauen",
             page=3, quantity=85.0, unit="m"),
        item("LV_92", "2.20", "Bodenbelag Vinyl",
             "Aufbauhöhe laut Planung: Estrich 50 mm, Belag 2,5 mm", page=4, quantity=26.0, unit="m2"),
        item("LV_93", "3.10", "Anstrich Fußboden", "Staubbindender Anstrich im Technikraum",
             page=1, quantity=9.0, unit="m2", post_trade_text="Folgeleistung: STRASSE"),
    ]


def finding(**changes):
    record = {
        "id": "X2-aaaaaa",
        "check": "X2",
        "layer": "between_lists",
        "type": "contradiction",
        "severity": "medium",
        "handover": ["LV_91", "LV_92"],
        "sources": [
            {"doc": "LV_91", "item_no": "1.10", "page": 2,
             "quote": "schwimmender Estrich auf Wärmedämmung, Nenndicke 65 mm"},
            {"doc": "LV_92", "item_no": "2.20", "page": 4,
             "quote": "Aufbauhöhe laut Planung: Estrich 50 mm"},
        ],
        "lists_searched": ["LV_91", "LV_92", "LV_93"],
        "search_terms": ["Nenndicke", "Aufbauhöhe", "Estrich"],
        "explanation_de": "Der Estrich ist mit 65 mm ausgeschrieben, der Bodenbelag rechnet mit 50 mm.",
        "question_de": "Welche Estrichdicke gilt für die Aufbauhöhe?",
        "exposure": {"quantity": 35.0, "unit": "m2"},
        "quotes_verified": True,
        "origin": "model+code",
        "skeptic": {"status": "survived", "note": "FINDER NOTE, must not be read."},
    }
    record.update(changes)
    return record


def second_finding(**changes):
    record = finding(
        id="X1-bbbbbb", check="X1", type="double_assignment",
        sources=[
            {"doc": "LV_91", "item_no": "", "page": 1,
             "quote": "Die Randdämmstreifen werden vom AN Estrich geliefert und eingebaut."},
            {"doc": "LV_92", "item_no": "2.10", "page": 3,
             "quote": "Randdämmstreifen an allen aufgehenden Bauteilen liefern und einbauen"},
        ],
        search_terms=["Randdämmstreifen"],
        explanation_de="Die Randdämmstreifen stehen in der Vorbemerkung und als eigene Position.",
        question_de="Welches Gewerk liefert die Randdämmstreifen?",
        exposure={"quantity": 85.0, "unit": "m"},
    )
    record.update(changes)
    return record


def verdict(status="survived", note="LV 91 1.10 decides it."):
    return {"status": status, "note": note, "origin": "agent session, independent context"}
