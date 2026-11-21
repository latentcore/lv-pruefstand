"""Hand-written items for the base check tests. No real tender text, no real price."""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pipeline.base import core  # noqa: E402
from pipeline.common import contract, ids, quotes  # noqa: E402

DOC = "LV_T1"
TEXT = "Mauerwerk aus Kalksandstein herstellen"


def item(item_no, short=TEXT, long_text="", kind="normal", quantity=10.0, unit="m2",
         unit_price=None, total=None, doc=DOC, page=1, **extra):
    """One items.json record in contract v1 shape; the section is the item number without its last part."""
    record = {
        "doc": doc, "project": "T", "trade": "Test", "format": "pdf", "stage": "anfrage",
        "item_no": item_no, "kind": kind, "section": item_no.rpartition(".")[0],
        "short_text": short, "long_text": long_text, "quantity": quantity, "unit": unit,
        "unit_price": unit_price, "total": total, "page": page, "line": 1,
        "pre_trade_text": None, "post_trade_text": None,
    }
    record.update(extra)
    return record


def heading(item_no, short="Abschnitt Rohbau", total=None, doc=DOC):
    return item(item_no, short, kind="heading", quantity=None, unit=None, total=total, doc=doc)


def note(item_no, text, doc=DOC):
    return item(item_no, "Vorbemerkung", long_text=text, kind="preliminary_note", quantity=None, unit=None, doc=doc)


def run(check, items):
    """The check's outcome on the one document the items form."""
    docs = core.split_docs(items)
    assert len(docs) == 1
    return check(docs[0])


def found(check, items):
    """The findings of a check on one document, each proven to be a valid contract v1 record."""
    outcome = run(check, items)
    assert outcome.applicable
    valid(outcome.findings, items)
    return outcome.findings


def valid(findings, items):
    """Schema, stable id, quote check, German text, no id twice."""
    contract.check("findings", [dict(f, quotes_verified=True) for f in findings])
    assert len({f["id"] for f in findings}) == len(findings)
    for finding in findings:
        assert ids.has_stable_id(finding)
        assert quotes.finding_verified(finding, items), finding
        assert finding["layer"] == "single_list" and finding["origin"] == "code"
        assert finding["explanation_de"].strip() and finding["question_de"].strip().endswith("?")
        assert finding["handover"] == finding["lists_searched"] == [finding["sources"][0]["doc"]]


def types(findings):
    return sorted(f["type"] for f in findings)


def no_amount(findings, *amounts):
    """No given price text stands anywhere in the findings."""
    dumped = json.dumps(findings, ensure_ascii=False)
    for amount in amounts:
        assert amount not in dumped, amount
