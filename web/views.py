"""Data for the views "Bauwerk", "Einzel-LV", "Live-Prüfung", "Vergleich", "Messung" and for the button
"Treffer anzeigen" of a finding.

Each function returns what one view shows, built from fixed lists of keys, as in
web/app.py: no unit_price and no total leaves this module. The prices of an uploaded
GAEB file are used by code only (the base checks B1, B2, B7, B9 and the recalculation
quantity x unit price = total) and come back as counts. An upload is read in memory;
nothing is written to disk. For a GAEB 90 upload each base finding carries the record lines of
its cited items as they stand in the file ("GAEB-Satz zeigen"); a price record (23, 30) is
replaced by a line that says so, so its unit price and total never reach the page.
"""
import time

from bench import table as bench_table
from pipeline.base.run import run_all
from pipeline.lv import gaeb90, gaebxml, model, xlsx

NO_POSITION = ("heading", "preliminary_note")
SEVERITY_ORDER = ("high", "medium", "info")
ITEM_KEYS = ("item_no", "kind", "section", "short_text", "quantity", "unit", "page")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_ROWS = 3000
MAX_FINDINGS = 400
MAX_WARNINGS = 20
MAX_NUMBERS = 60
MAX_HITS = 80
MAX_SNIPPETS = 2
# GAEB 90: records that continue an item after its first line (texts, prices). Only the record types of
# RAW_SHOWN are shown as they stand; every other one (the price records 23 and 30 among them) is masked.
RAW_FOLLOW = ("23", "24", "25", "26", "28", "30")
RAW_SHOWN = ("11", "12", "20", "21", "24", "25", "26", "41", "T0", "T1")
RAW_PRICE_RECORDS = ("23", "30")
RAW_MASK = "Preissatz: Einheitspreis und Gesamtbetrag werden hier nicht gezeigt"
RAW_MASK_OTHER = "Satz wird hier nicht gezeigt"
MAX_RAW_LINES = 16
MAX_RAW_ITEMS = 3


class ViewError(ValueError):
    """The input cannot be shown; the message is German, for the page."""


def _text(value):
    if value is None or isinstance(value, str):
        return value
    return str(value)


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if value == value and value not in (float("inf"), float("-inf")) else None


def is_position(item):
    return item.get("kind") not in NO_POSITION


def worst(severities):
    known = [s for s in severities if s in SEVERITY_ORDER]
    return min(known, key=SEVERITY_ORDER.index) if known else None


def list_order(items, findings=()):
    """The documents in the order of items.json, then those that only findings name."""
    order, trades, positions = [], {}, {}
    for item in items:
        doc = item.get("doc")
        if not isinstance(doc, str) or not doc:
            continue
        if doc not in trades:
            order.append(doc)
            trades[doc] = ""
            positions[doc] = 0
        if not trades[doc] and isinstance(item.get("trade"), str):
            trades[doc] = item["trade"]
        if is_position(item):
            positions[doc] += 1
    for finding in findings:
        for doc in finding_docs(finding):
            if doc not in trades:
                order.append(doc)
                trades[doc] = ""
                positions[doc] = 0
    return [{"doc": doc, "trade": trades[doc], "positions": positions[doc]} for doc in order]


def finding_docs(finding):
    """The lists a finding lies between: its handover, else the documents of its sources."""
    docs = []
    raw = finding.get("handover") if isinstance(finding.get("handover"), list) else []
    if not raw:
        raw = [s.get("doc") for s in finding.get("sources") or [] if isinstance(s, dict)]
    for doc in raw:
        if isinstance(doc, str) and doc and doc not in docs:
            docs.append(doc)
    return docs


# ---- Bauwerk ------------------------------------------------------------------

def matrix(findings, items, handover_map=None, project=None):
    """The trade matrix: one cell per pair of lists that a finding or a handover joins.

    A finding between two lists lights the cell of the two; a finding between three
    lights the three cells of its pairs; a finding inside one list lights the cell on
    the diagonal. handover_map: pipeline/cross/handover_map.json, used only when it
    is the map of this project; a handover with evidence in its lists marks its pairs.
    """
    lists = list_order(items, findings)
    rank = dict((entry["doc"], index) for index, entry in enumerate(lists))
    cells = {}

    def cell(a, b):
        a, b = sorted((a, b), key=lambda doc: rank.get(doc, len(rank)))
        return cells.setdefault((a, b), {"a": a, "b": b, "findings": [], "severities": [], "handovers": []})

    for finding in findings:
        docs = finding_docs(finding)
        pairs = [(a, b) for i, a in enumerate(docs) for b in docs[i + 1:]] or [(d, d) for d in docs[:1]]
        for a, b in pairs:
            entry = cell(a, b)
            if finding.get("id") not in entry["findings"]:
                entry["findings"].append(_text(finding.get("id")))
                entry["severities"].append(_text(finding.get("severity")))
    handovers = []
    if isinstance(handover_map, dict) and handover_map.get("project") == project:
        for handover in handover_map.get("handovers") or []:
            if not isinstance(handover, dict):
                continue
            docs = [doc for doc in handover.get("lists") or [] if doc in rank]
            name, status = _text(handover.get("name_de")) or "", _text(handover.get("status")) or ""
            handovers.append({"name": name, "lists": docs, "status": status})
            for i, a in enumerate(docs):
                for b in docs[i + 1:]:
                    entry = cell(a, b)
                    if name not in entry["handovers"]:
                        entry["handovers"].append(name)
    out = []
    for (a, b), entry in sorted(cells.items(), key=lambda pair: (rank.get(pair[0][0], 0), rank.get(pair[0][1], 0))):
        out.append({"a": a, "b": b, "findings": entry["findings"], "severity": worst(entry["severities"]),
                    "handovers": entry["handovers"]})
    return {
        "lists": lists,
        "positions": sum(entry["positions"] for entry in lists),
        "cells": out,
        "handovers": handovers,
    }


# ---- Einzel-LV ---------------------------------------------------------------------

def base_view(finding):
    """One base finding for the page: check, type, level, cited item numbers, texts. No price."""
    sources = [s for s in finding.get("sources") or [] if isinstance(s, dict)]
    return {
        "id": _text(finding.get("id")),
        "check": _text(finding.get("check")),
        "type": _text(finding.get("type")),
        "severity": _text(finding.get("severity")),
        "doc": _text(sources[0].get("doc")) if sources else None,
        "item_nos": [_text(s.get("item_no")) for s in sources],
        "quote": _text(sources[0].get("quote")) if sources else None,
        "explanation_de": _text(finding.get("explanation_de")),
        "question_de": _text(finding.get("question_de")),
    }


def item_row(item):
    row = dict((key, _text(item.get(key)) if key not in ("quantity", "page") else None) for key in ITEM_KEYS)
    row["quantity"] = _number(item.get("quantity"))
    page = item.get("page")
    row["page"] = page if isinstance(page, int) and not isinstance(page, bool) else None
    return row


def lv_lists(items, base_findings):
    """The lists of the project with the number of base findings of each."""
    counts = {}
    for finding in base_findings:
        doc = base_view(finding)["doc"]
        counts[doc] = counts.get(doc, 0) + 1
    lists = list_order(items)
    for entry in lists:
        entry["base_findings"] = counts.get(entry["doc"], 0)
    return lists


def lv_document(items, base_findings, doc):
    """The records of one list (fixed keys) and its base findings."""
    rows = [item_row(item) for item in items if item.get("doc") == doc]
    if not rows:
        raise ViewError("Die Liste %s steht nicht in items.json." % doc)
    found = [base_view(f) for f in base_findings if base_view(f)["doc"] == doc]
    trade = next((item.get("trade") for item in items if item.get("doc") == doc and item.get("trade")), "")
    return {"doc": doc, "trade": _text(trade) or "", "rows": rows[:MAX_ROWS], "rows_total": len(rows),
            "findings": found[:MAX_FINDINGS], "findings_total": len(found), "checks": check_counts(found)}


def check_counts(findings):
    counts = {}
    for finding in findings:
        counts[finding["check"]] = counts.get(finding["check"], 0) + 1
    return [{"check": check, "findings": counts[check]}
            for check in sorted(counts, key=lambda name: (len(name), name))]


# ---- Live-Prüfung --------------------------------------------------------------------

def reader_for(file_name):
    if gaeb90.is_gaeb90_name(file_name):
        return gaeb90
    if gaebxml.is_gaebxml_name(file_name):
        return gaebxml
    if xlsx.is_xlsx_name(file_name):
        return xlsx
    raise ViewError("Nur GAEB-Dateien und Excel-Listen werden hier gelesen: .D83, .D84, .D86 (GAEB 90), "
                    ".X83, .X84, .X86 (GAEB DA XML) oder .xlsx. PDF-Leistungsverzeichnisse liest die Pipeline "
                    "(python -m pipeline.run).")


def gaeb90_lines(raw):
    """The lines of a GAEB 90 file, decoded with the code page the reader picks."""
    text = raw.decode(gaeb90.detect_encoding(raw), errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def raw_record(lines, start):
    """The record lines of one entry of a GAEB 90 file, from its first line (1-based) to the
    next record that starts something new. A price record is replaced by RAW_MASK."""
    out = []
    index = start - 1
    number = None
    while 0 <= index < len(lines) and len(out) < MAX_RAW_LINES:
        line = lines[index].rstrip()
        kind = line[:2]
        if out and kind not in RAW_FOLLOW:
            break
        if kind in ("21", "23"):
            if number is not None and line[2:11] != number:
                break  # the price record of the next item (a file of price records only)
            number = line[2:11]
        if kind in RAW_SHOWN:
            out.append({"no": index + 1, "text": line, "masked": False})
        else:
            out.append({"no": index + 1, "text": kind + "  " + (RAW_MASK if kind in RAW_PRICE_RECORDS else RAW_MASK_OTHER),
                        "masked": True})
        index += 1
    return out


def attach_raw(views, records, raw):
    """Give each base finding of a GAEB 90 upload the record lines of its cited items."""
    lines = gaeb90_lines(raw)
    starts, notes = {}, {}
    for record in records:
        if record.get("item_no") and isinstance(record.get("line"), int):
            target = notes if record.get("kind") == "preliminary_note" else starts
            target.setdefault(record["item_no"], []).append(record["line"])
    for number, lines_of_notes in notes.items():
        starts.setdefault(number, lines_of_notes)  # a note only when nothing else has the number
    for view in views:
        view["raw"] = [{"item_no": number, "line": start, "lines": raw_record(lines, start)}
                       for number in view["item_nos"][:MAX_RAW_ITEMS] for start in starts.get(number, [])[:2]]


def live(raw, file_name, clock=time.perf_counter):
    """Read an uploaded GAEB file in memory and run the twelve base checks on it."""
    import os
    name = os.path.basename((file_name or "").replace("\\", "/")).strip()
    if not name:
        raise ViewError("Die Datei hat keinen Namen.")
    if not raw:
        raise ViewError("Die Datei %s ist leer." % name)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ViewError("Die Datei %s ist größer als %d MB." % (name, MAX_UPLOAD_BYTES // (1024 * 1024)))
    reader = reader_for(name)
    start = clock()
    try:
        _project, records, entry = reader.parse_bytes(raw, name, project="live")
    except ValueError as error:
        what = "Excel-Liste" if reader is xlsx else "GAEB"
        raise ViewError("Die Datei %s kann nicht als %s gelesen werden (%s)."
                        % (name, what, getattr(error, "german", None) or error))
    read_done = clock()
    findings, summary = run_all(records)
    checks_done = clock()
    check = entry.get("price_check") or {}
    positions = [record for record in records if model.is_position(record)]
    views = [base_view(finding) for finding in findings][:MAX_FINDINGS]
    if reader is gaeb90:
        attach_raw(views, records, raw)
    return {
        "file": name,
        "format": entry.get("format"),
        "stage": entry.get("stage"),
        "items": len(positions),
        "headings": entry.get("headings", 0),
        "notes": entry.get("preliminary_notes", 0),
        "unparsed": entry.get("unparsed_lines", 0),
        "warnings": [_text(w) for w in (entry.get("warnings") or [])[:MAX_WARNINGS]],
        "warnings_total": len(entry.get("warnings") or []),
        "recalculation": {"priced": entry.get("priced_items", 0), "equal": check.get("equal", 0),
                          "not_equal": check.get("not_equal", 0), "no_quantity": check.get("no_quantity", 0)},
        "seconds": {"read": round(read_done - start, 3), "checks": round(checks_done - read_done, 3)},
        "checks": [{"check": s["check"], "title": s["title"], "findings": s["findings"],
                    "not_applicable": bool(s["documents"]) and len(s["not_applicable"]) == s["documents"]}
                   for s in summary],
        "findings": views,
        "findings_total": len(findings),
        "rows": [item_row(record) for record in records][:MAX_ROWS],
        "rows_total": len(records),
    }


# ---- Vergleich -------------------------------------------------------------------------

PAIR_TITLES_DE = {
    "t1_offer_pdf_d84": "Angebot AN24-0305: PDF gegen GAEB D84",
    "t2_print_pdf_x83_fields": "PROJEKT_004: Ausdruck (PDF) gegen X83, Feld für Feld",
    "t2_print_pdf_x83": "PROJEKT_004: Ausdruck (PDF) gegen X83, gedruckter Text gegen Langtext",
    "t3_x83_d83": "8209.003: X83 gegen D83 (dieselbe Ausschreibung)",
    "t3_tender_d83_order_d86": "8209.003: Ausschreibung (D83) gegen Auftrag LV24069 (D86)",
    "t3_tender_x83_order_d86": "8209.003: Ausschreibung (X83) gegen Auftrag LV24069 (D86)",
    "stbalv_offer_d84_order_d86": "StBALV23040: Angebot (D84) gegen Auftrag (D86)",
    "t4_nummer001_x83_stbalv_d84": "NUMMER_001 (X83) gegen StBALV23040 (D84)",
    "t4_nummer001_x83_stbalv_d86": "NUMMER_001 (X83) gegen StBALV23040 (D86)",
}
VERDICT_DE = {"holds": "trifft zu", "does not hold": "trifft nicht zu",
              "cannot be decided with the readers we have": "mit den vorhandenen Lesern nicht entscheidbar",
              "confirmed": "bestätigt", "refuted": "widerlegt"}
FIELDS = ("quantity", "unit", "unit_price", "total", "short_text", "long_text", "text")


def _numbers(values):
    values = [_text(v) for v in values or []]
    return {"count": len(values), "shown": values[:MAX_NUMBERS]}


def diff(summary):
    """The comparisons of pipeline.diff.pairs (out/diff/summary.json) as counts and item numbers."""
    if not isinstance(summary, dict):
        raise ViewError("Die Vergleichsdatei ist nicht lesbar.")
    files = summary.get("files") or {}

    def side(key):
        entry = files.get(key) or {}
        return {"file": _text(entry.get("file")), "items": (entry.get("counts") or {}).get("items")}

    pairs = []
    for pair in summary.get("pairs") or []:
        result = pair.get("result") or {}
        matching = result.get("matching") or {}
        fields = {}
        for name in FIELDS:
            field = (result.get("fields") or {}).get(name)
            if isinstance(field, dict):
                fields[name] = {"compared": field.get("compared", 0), "equal": field.get("equal", 0)}
        entry = {
            "id": _text(pair.get("id")), "title": PAIR_TITLES_DE.get(pair.get("id"), _text(pair.get("id"))),
            "group": _text(pair.get("group")), "a": side(pair.get("a")), "b": side(pair.get("b")),
            "both": matching.get("both", 0), "only_a": _numbers(matching.get("only_a")),
            "only_b": _numbers(matching.get("only_b")), "renumbered": len(matching.get("renumbered") or []),
            "fields": fields, "verdict": VERDICT_DE.get(pair.get("verdict"), _text(pair.get("verdict"))),
        }
        stage = result.get("stage")
        if isinstance(stage, dict):
            changed = stage.get("changed") or {}
            entry["stage"] = {
                "added": _numbers(stage.get("added")), "removed": _numbers(stage.get("removed")),
                "renumbered": len(stage.get("renumbered") or []),
                "changed": dict((name, len(changed.get(name) or [])) for name in ("quantity", "unit", "text", "price")),
                "added_sections": [_text(s) for s in stage.get("added_sections") or []],
            }
        pairs.append(entry)
    titles = []
    for pair in summary.get("text_pairs") or []:
        result = pair.get("result") or {}
        titles.append({
            "id": _text(pair.get("id")), "role": _text(pair.get("role")),
            "pdf": _text((summary.get("pdfs") or {}).get(pair.get("pdf"))),
            "list": side(pair.get("list"))["file"],
            "verdict": VERDICT_DE.get(pair.get("verdict"), _text(pair.get("verdict"))),
            "searchable": result.get("searchable", 0), "found": result.get("found_total", 0),
            "in_order": result.get("in_order", 0),
        })
    hypothesis = summary.get("hypothesis_38") or {}
    runs = hypothesis.get("runs") or [{}]
    run = runs[0]
    return {
        "pairs": pairs,
        "titles": titles,
        "hypothesis": {
            "verdict": VERDICT_DE.get(hypothesis.get("verdict"), _text(hypothesis.get("verdict"))),
            "tendered": run.get("tendered"), "ordered": run.get("ordered"), "in_both": run.get("in_both"),
            "added": _numbers(run.get("added")), "removed": len(run.get("removed") or []),
            "renumbered": len(run.get("renumbered") or []),
            "sections": [{"item_no": _text(s.get("item_no")), "title": _text(s.get("title"))}
                         for s in run.get("sections_only_in_order") or [] if isinstance(s, dict)],
            "zero_quantity": bool(run.get("zero_items_are_the_added_items")),
        },
    }


# ---- Treffer anzeigen ---------------------------------------------------------------------

def evidence(entry, finding_id):
    """Where the search terms of one finding stand in the lists (out/<project>/skeptic/evidence.json,
    written by python -m pipeline.run). Fixed keys; quantity and unit, never a price."""
    if not isinstance(entry, dict):
        raise ViewError("Zu %s liegen keine Suchtreffer vor." % finding_id)
    hits = [hit for hit in entry.get("hits") or [] if isinstance(hit, dict)]
    per_list = entry.get("hits_per_list") if isinstance(entry.get("hits_per_list"), dict) else {}
    return {
        "id": _text(entry.get("id")) or finding_id,
        "terms": [_text(t) for t in entry.get("terms") or []],
        "lists_searched": [_text(d) for d in entry.get("lists_searched") or []],
        "hits_per_list": [{"doc": _text(doc), "hits": count} for doc, count in per_list.items()
                          if isinstance(count, int) and not isinstance(count, bool)],
        "lists_without_hit": [_text(d) for d in entry.get("lists_without_hit") or []],
        "hits": [{
            "doc": _text(hit.get("doc")), "item_no": _text(hit.get("item_no")),
            "page": hit.get("page") if isinstance(hit.get("page"), int) and not isinstance(hit.get("page"), bool) else None,
            "kind": _text(hit.get("kind")), "short_text": _text(hit.get("short_text")),
            "quantity": _number(hit.get("quantity")), "unit": _text(hit.get("unit")),
            "cited": hit.get("cited") is True, "terms": [_text(t) for t in hit.get("terms") or []],
            "snippets": [_text(s) for s in (hit.get("snippets") or [])[:MAX_SNIPPETS]],
        } for hit in hits[:MAX_HITS]],
        "hits_total": len(hits),
    }


# ---- Messung ---------------------------------------------------------------------------

def bench(data):
    """The measurements M1 to M9 of bench/results/bench.json, in German, as the report writes them."""
    if not isinstance(data, dict) or not isinstance(data.get("measurements"), list):
        raise ViewError("Die Messdatei bench/results/bench.json ist nicht lesbar.")
    rows = []
    for entry in data["measurements"]:
        rows.append({
            "id": entry["id"], "name": bench_table.NAMES_DE.get(entry["id"], entry.get("name")),
            "result": bench_table.result(entry, german=True),
            "threshold": bench_table.THRESHOLDS_DE.get(entry["id"], entry.get("threshold")),
            "met": entry["met"], "met_de": bench_table.MET_DE.get(entry["met"], entry["met"]),
        })
    return {"measured_at": _text(data.get("measured_at")), "rows": rows}
