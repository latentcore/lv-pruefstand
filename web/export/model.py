"""What the three export files show: read once from the project files.

Everything is built from fixed lists of keys. No unit_price and no total of
items.json is copied, so no price can reach an export file. Every number here
is a count over the project files (MASTER_PLAN K12).
"""
import json
import math
import os
import re
from collections import Counter
from datetime import datetime

from bench import run as bench_run
from bench import table as bench_table
from pipeline.common import quotes
from web.app import Store, count, review_view

NAMES = {
    "docx": "Fragen_und_Klaerungsliste.docx",
    "xlsx": "LV_markiert.xlsx",
    "html": "Risikobericht.html",
    "pdf": "Risikobericht.pdf",
}
SEVERITY_ORDER = ("high", "medium", "info")
SKEPTIC_ORDER = ("survived", "weakened", "refuted")
NO_POSITION = ("heading", "preliminary_note")

# Characters that XML 1.0 does not allow (.docx and .xlsx are XML inside).
_NOT_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]|[\ud800-\udfff]")


def clean(value):
    """Text of the data as it is, without the characters no XML file can hold. None gives ""."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return _NOT_XML.sub("", value)


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value


def today():
    """Now in Munich time; the clock of the machine when it has no time zone data."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:  # no tzdata on this machine
        return datetime.now()


def _item_row(item):
    """The six columns of LV_markiert plus trade and kind. No price key."""
    return {
        "doc": clean(item.get("doc")),
        "trade": clean(item.get("trade")),
        "item_no": clean(item.get("item_no")),
        "kind": clean(item.get("kind")),
        "short_text": clean(item.get("short_text")),
        "quantity": _number(item.get("quantity")),
        "unit": clean(item.get("unit")),
        "page": item.get("page") if isinstance(item.get("page"), int) and not isinstance(item.get("page"), bool)
        else None,
    }


def cited_index(source, items):
    """Index in items of the record a source cites, or None.

    Among the records with the doc and item number of the source: the one whose
    text holds the quote, else the first on the cited page that is no heading,
    else the first that is no heading, else the first.
    """
    found = [index for index, item in enumerate(items)
             if item.get("doc") == source.get("doc") and item.get("item_no") == source.get("item_no")]
    if not found:
        return None
    quote = source.get("quote")
    if isinstance(quote, str) and quote.strip():
        for index in found:
            if quotes.quote_in_text(quote, quotes.item_text(items[index])):
                return index
    no_heading = [index for index in found if items[index].get("kind") != "heading"]
    for index in no_heading:
        if items[index].get("page") == source.get("page"):
            return index
    return (no_heading or found)[0]


def _bench(path):
    """(state, lines) of out/<project>/bench.json: "missing", "unreadable" or "ok" with its lines as they are."""
    if not os.path.exists(path):
        return "missing", []
    try:
        with open(path, encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return "unreadable", []
    if isinstance(data, dict) and isinstance(data.get("lines"), list):
        data = data["lines"]

    def line(value):
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    if isinstance(data, list):
        lines = [line(entry) for entry in data]
    elif isinstance(data, dict):
        lines = ["%s: %s" % (key, line(value)) for key, value in data.items()]
    else:
        lines = [line(data)]
    return "ok", [clean(entry) for entry in lines]


def committed_bench(project, path=None):
    """(state, lines) of the committed bench/results/bench.json, made into the German lines of bench.table.
    The state is "committed" (the report says the run was not made on this machine).

    Only for the project the bench measures (bench.run.REPORT_PROJECT); "missing" for any other.
    Used when out/<project>/bench.json is absent: nothing is measured here.
    """
    if project != bench_run.REPORT_PROJECT:
        return "missing", []
    path = path or bench_run.RESULTS_PATH
    if not os.path.exists(path):
        return "missing", []
    try:
        lines = bench_table.lines_de(bench_run.read_json(path))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return "unreadable", []
    return "committed", [clean(entry) for entry in lines]


def weakened_split(findings):
    """(by the second pass, by the number rule) among the findings whose skeptic status is weakened.

    A rule of pipeline/skeptic/rules.py only lowers: a weakened finding whose agent_status is not
    weakened was lowered by the rule. Without agent_status the status is the agent's own (rules.py).
    """
    agent = rule = 0
    for finding in findings:
        skeptic = finding.get("skeptic") if isinstance(finding.get("skeptic"), dict) else {}
        if skeptic.get("status") != "weakened":
            continue
        if skeptic.get("agent_status") in (None, "weakened"):
            agent += 1
        else:
            rule += 1
    return agent, rule


def build(findings, items, reviews, project, mode="real", items_usable=True, bench=("missing", []), now=None):
    """Put the data of one project into the form the three writers read."""
    items = [item for item in items if isinstance(item, dict)]
    rows = [_item_row(item) for item in items]
    trades = {}
    for row in rows:
        if row["trade"] and row["doc"] not in trades:
            trades[row["doc"]] = row["trade"]

    confirmed = []
    for finding in findings:
        review = review_view(reviews.get(finding["id"]))
        if not review or review["status"] != "confirmed":
            continue
        sources = []
        raw_sources = finding.get("sources") if isinstance(finding.get("sources"), list) else []
        for source in raw_sources:
            if not isinstance(source, dict):
                source = {}
            page = source.get("page")
            sources.append({
                "doc": clean(source.get("doc")),
                "trade": trades.get(clean(source.get("doc")), ""),
                "item_no": clean(source.get("item_no")),
                "page": page if isinstance(page, int) and not isinstance(page, bool) else None,
                "quote": clean(source.get("quote")),
                "item": cited_index(source, items),
            })
        confirmed.append({
            "id": clean(finding["id"]),
            "type": clean(finding.get("type")),
            "severity": clean(finding.get("severity")),
            "question": clean(finding.get("question_de")),
            "explanation": clean(finding.get("explanation_de")),
            "sources": sources,
            "by": clean(review["by"]),
            "at": clean(review["at"]),
            "comment": clean(review["comment"]),
            "eur_estimate": review["eur_estimate"],
        })
    rank = {name: place for place, name in enumerate(SEVERITY_ORDER)}
    confirmed.sort(key=lambda entry: rank.get(entry["severity"], len(rank)))  # stable: file order inside a level
    for number, entry in enumerate(confirmed, 1):
        entry["nr"] = number

    skeptic = Counter()
    for finding in findings:
        status = finding.get("skeptic", {}).get("status") if isinstance(finding.get("skeptic"), dict) else None
        skeptic[status if isinstance(status, str) and status else None] += 1
    numbers = count(findings, reviews)
    by = []
    for entry in confirmed:
        if entry["by"] and entry["by"] not in by:
            by.append(entry["by"])
    docs = []
    for row in rows:
        if row["doc"] not in docs:
            docs.append(row["doc"])
    return {
        "project": clean(project),
        "mode": mode,
        "now": now or today(),
        "confirmed": confirmed,
        "confirmed_by": by,
        "by_missing": any(not entry["by"] for entry in confirmed),
        "items": rows,
        "items_usable": bool(items_usable),
        "docs": docs,
        "counts": {
            "lists": len(docs),
            "positions": sum(1 for row in rows if row["kind"] not in NO_POSITION),
            "headings": sum(1 for row in rows if row["kind"] == "heading"),
            "preliminary_notes": sum(1 for row in rows if row["kind"] == "preliminary_note"),
            "findings": numbers["all"]["count"],
            "confirmed": numbers["all"]["confirmed"],
            "rejected": numbers["all"]["rejected"],
            "unclear": numbers["all"]["unclear"],
            "open": numbers["all"]["open"],
            "reviews_without_finding": numbers["reviews_without_finding"],
        },
        "skeptic": [(name, skeptic.get(name, 0)) for name in SKEPTIC_ORDER]
        + sorted(((name, number) for name, number in skeptic.items() if name not in SKEPTIC_ORDER),
                 key=lambda pair: (pair[0] is None, pair[0] or "")),
        "weakened_split": weakened_split(findings),
        "bench_state": bench[0],
        "bench_lines": list(bench[1]),
    }


def load(store, now=None, place=None):
    """Read the project the store points at (as the page does) and build the export data.

    Raises web.app.DataError when findings.json or the reviews file cannot be used.
    """
    place = place or store.locate()
    findings, _, _ = store.load_findings(place)
    reviews = store.read_reviews(place["project"])
    items, items_usable = store.load_items(place)
    bench = ("missing", [])
    if place["mode"] == "real":
        bench = _bench(os.path.join(os.path.dirname(place["findings_path"]), "bench.json"))
        if bench[0] == "missing":
            bench = committed_bench(place["project"])
    return build(findings, items, reviews, place["project"], mode=place["mode"], items_usable=items_usable,
                 bench=bench, now=now)


def load_project(project, out_dir=None, reviews_dir=None, now=None):
    """Export data of out/<project>/. Raises FileNotFoundError when it holds no findings.json."""
    store = Store(out_dir=out_dir, reviews_dir=reviews_dir, project=project)
    place = store.locate()
    if place["mode"] != "real":
        raise FileNotFoundError(place["missing"])
    return load(store, now=now)
