#!/usr/bin/env python3
"""Page-by-page check of 79-222 lists against the reader output (W2 "done").

The check does not use the reader's text or its line rules. It takes the words
of every PDF page with their positions (PyMuPDF), finds the column positions
from the column header of the page ("OZ", "Menge", "ME"), and then reads:
  - an item number: a number word that starts in the OZ column;
  - a quantity: a number word that ends at the right edge of the "Menge"
    column, with the unit beside it in the "ME" column.
An item number followed by a quantity (before the next item number) is an item
that the page shows. For every page the check then says:
  - every item the page shows is in items.json with that page;
  - no item of items.json for that page is missing on the page;
  - quantity and unit of items.json equal the ones on the page (when an item
    runs over a page break, its quantity stands on a later page; such items are
    listed as "continued", with the page of the quantity);
  - every other number in the OZ column (heading, numbered note) is in
    items.json with that page, and every heading of items.json is on its page.
A difference is listed, never dropped. No price is read or written.

Usage:
    pagecheck_lists.py PDF_DIR ITEMS_JSON OUT_JSON [SUMMARY_JSON] [DOC ...]
"""

import hashlib
import json
import os
import re
import sys

DEFAULT_DOCS = ["LV_18", "LV_14c", "LV_02", "LV_17", "LV_00"]

DOC_RE = re.compile(r"^(LV_\d+[a-z]?)(?:_|\.)")
NUMBER_WORD_RE = re.compile(r"^(?=.*\d)[\d.]+$")
QUANTITY_WORD_RE = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d+$")
OZ_HEADS = ("OZ", "Ordnungszahl")
X_TOL = 2.5      # points; a word belongs to a column when its edge is this near
ROW_TOL = 4.0    # points; words this near in y stand in one row
SUMMARY_TITLE = "Zusammenstellung"


def german_number(text):
    return float(text.replace(".", "").replace(",", "."))


def item_number(word):
    return word.rstrip(".")


def rows_of(words):
    """Group (x0, y0, x1, y1, text) words into rows, top to bottom."""
    rows = []
    for w in sorted(words, key=lambda w: (w[1], w[0])):
        if rows and abs(rows[-1][0] - w[1]) <= ROW_TOL:
            rows[-1][1].append(w)
        else:
            rows.append((w[1], [w]))
    return [sorted(r, key=lambda w: w[0]) for _, r in rows]


def find_columns(words):
    """Column positions from the column header row of a page, or None."""
    for row in rows_of(words):
        texts = [w[4] for w in row]
        if "Menge" not in texts or "ME" not in texts:
            continue
        if row[0][4] not in OZ_HEADS:
            continue
        menge = row[texts.index("Menge")]
        unit = row[texts.index("ME")]
        return {"oz_x0": row[0][0], "qty_x1": menge[2], "unit_x0": unit[0],
                "top": max(w[3] for w in row)}
    return None


def page_events(words, columns):
    """Read one page. Returns (events, is_summary_page).

    events, top to bottom: ("no", item_no) and ("qty", quantity, unit|None).
    """
    top = columns["top"]
    bottom = None
    summary = False
    for w in words:
        if w[4] == "Druckdatum:":
            bottom = w[1] if bottom is None else min(bottom, w[1])
    body = [w for w in words
            if w[1] > top and (bottom is None or w[3] < bottom - ROW_TOL)]
    events = []
    for row in rows_of(body):
        if len(row) == 1 and row[0][4] == SUMMARY_TITLE:
            summary = True
        first = row[0]
        if (abs(first[0] - columns["oz_x0"]) <= X_TOL
                and NUMBER_WORD_RE.match(first[4])):
            events.append((first[1], "no", item_number(first[4]), None))
        for i, w in enumerate(row):
            if not QUANTITY_WORD_RE.match(w[4]):
                continue
            if abs(w[2] - columns["qty_x1"]) > X_TOL:
                continue
            if not row[i + 1:]:
                continue    # a number alone at the column edge is body text
            nxt = row[i + 1]
            unit = nxt[4] if abs(nxt[0] - columns["unit_x0"]) <= X_TOL else None
            events.append((w[1], "qty", german_number(w[4]), unit))
    events.sort(key=lambda e: e[0])
    return [e[1:] for e in events], summary


def read_document(pages):
    """pages: list of word lists, page 1 first. Returns a dict with
    "items" [{item_no, page, quantity, unit, quantity_page}],
    "numbers" [{item_no, page}] (numbers without quantity),
    "loose_quantities" [page], "pages_without_header" [page],
    "summary_pages" [page]."""
    columns = None
    for words in pages:
        columns = find_columns(words)
        if columns:
            break
    out = {"items": [], "numbers": [], "loose_quantities": [],
           "pages_without_header": [], "summary_pages": []}
    open_no = None
    for page_no, words in enumerate(pages, 1):
        own = find_columns(words)
        if own is None:
            out["pages_without_header"].append(page_no)
            if columns is None:
                continue
            own = dict(columns, top=-1.0)
        events, summary = page_events(words, own)
        if summary:
            out["summary_pages"].append(page_no)
            if open_no:
                out["numbers"].append(open_no)
                open_no = None
            continue
        for kind, value, unit in events:
            if kind == "no":
                if open_no:
                    out["numbers"].append(open_no)
                open_no = {"item_no": value, "page": page_no}
            elif open_no is None:
                out["loose_quantities"].append(page_no)
            else:
                out["items"].append(dict(open_no, quantity=value, unit=unit,
                                         quantity_page=page_no))
                open_no = None
    if open_no:
        out["numbers"].append(open_no)
    return out


def _take(pool, key):
    """Remove and return one entry with this key from a dict of lists."""
    entries = pool.get(key)
    if entries:
        return entries.pop(0)
    return None


def _take_group(pool, key):
    """Remove and return the records one printed number stands for: the first
    one left with this key and the notes after it, up to the next heading."""
    entries = pool.get(key)
    if not entries:
        return []
    group = [entries.pop(0)]
    while entries and entries[0]["kind"] != "heading":
        group.append(entries.pop(0))
    return group


def check_document(doc, shown, records, page_count):
    """Compare what the pages show with the items.json records of one list.

    Returns {"doc", "pages": [per page], and the totals}."""
    priced = {}
    headings = {}
    numbered = {}
    for r in records:
        key = (r["page"], r["item_no"])
        if r["quantity"] is not None:
            priced.setdefault(key, []).append(r)
            continue
        numbered.setdefault(key, []).append(r)      # headings and notes
        if r["kind"] == "heading":
            headings.setdefault(key, []).append(r)
    priced_pages = {}
    for r in records:
        if r["quantity"] is not None:
            priced_pages.setdefault(r["item_no"], []).append(r["page"])

    pages = [{"page": n, "items_on_page": 0, "items_in_reader": 0,
              "items_matched": 0, "quantity_unit_equal": 0,
              "other_numbers_on_page": 0, "other_numbers_matched": 0,
              "continued": [], "differences": []}
             for n in range(1, page_count + 1)]

    def page(n):
        return pages[n - 1]

    def diff(n, kind, item_no, **more):
        entry = {"doc": doc, "page": n, "item_no": item_no, "difference": kind}
        entry.update(more)
        page(n)["differences"].append(entry)

    for (n, _), recs in priced.items():
        if 1 <= n <= page_count:
            page(n)["items_in_reader"] += len(recs)
    for item in shown["items"]:
        n = item["page"]
        p = page(n)
        p["items_on_page"] += 1
        rec = _take(priced, (n, item["item_no"]))
        if rec is None:
            other = [x for x in priced_pages.get(item["item_no"], []) if x != n]
            if other:
                diff(n, "item on the page, in items.json with another page",
                     item["item_no"], items_json_page=other[0])
            else:
                diff(n, "item on the page, not in items.json", item["item_no"])
            continue
        p["items_matched"] += 1
        if item["quantity_page"] != n:
            p["continued"].append({"doc": doc, "page": n,
                                   "item_no": item["item_no"],
                                   "quantity_page": item["quantity_page"]})
        equal = True
        if rec["quantity"] != item["quantity"]:
            equal = False
            diff(n, "quantity differs", item["item_no"],
                 on_page=item["quantity"], in_items_json=rec["quantity"])
        if rec["unit"] != item["unit"]:
            equal = False
            diff(n, "unit differs", item["item_no"],
                 on_page=item["unit"], in_items_json=rec["unit"])
        if equal:
            p["quantity_unit_equal"] += 1
    for (n, item_no), recs in sorted(priced.items()):
        for _ in recs:
            if 1 <= n <= page_count:
                diff(n, "item in items.json, not on the page", item_no)
            else:
                pages[-1]["differences"].append({
                    "doc": doc, "page": n, "item_no": item_no,
                    "difference": "item in items.json on a page the PDF does not have"})
    for number in shown["numbers"]:
        n = number["page"]
        p = page(n)
        p["other_numbers_on_page"] += 1
        key = (n, number["item_no"])
        group = _take_group(numbered, key)
        if group:
            p["other_numbers_matched"] += 1
            if group[0]["kind"] == "heading":
                _take(headings, key)
        else:
            diff(n, "number on the page, not in items.json with that page",
                 number["item_no"])
    for (n, item_no), recs in sorted(headings.items()):
        for _ in recs:
            if 1 <= n <= page_count:
                diff(n, "heading in items.json, not on the page", item_no)
    for n in shown["loose_quantities"]:
        diff(n, "quantity on the page without an item number", None)
    for p in pages:
        p["differences"].sort(key=lambda d: (d["item_no"] or "", d["difference"]))
    result = {"doc": doc, "pages_checked": page_count,
              "pages_without_header": shown["pages_without_header"],
              "summary_pages": shown["summary_pages"], "pages": pages}
    result.update(totals(pages))
    return result


def totals(pages):
    keys = ["items_on_page", "items_in_reader", "items_matched",
            "quantity_unit_equal", "other_numbers_on_page",
            "other_numbers_matched"]
    out = {k: sum(p[k] for p in pages) for k in keys}
    out["continued"] = sum(len(p["continued"]) for p in pages)
    out["differences"] = sum(len(p["differences"]) for p in pages)
    return out


def summarize(results):
    """The small summary that goes to git: counts and every difference."""
    lists = []
    for r in results:
        entry = {k: v for k, v in r.items() if k != "pages"}
        entry["continued_items"] = [c for p in r["pages"] for c in p["continued"]]
        entry["difference_list"] = [d for p in r["pages"] for d in p["differences"]]
        lists.append(entry)
    keys = ["pages_checked", "items_on_page", "items_in_reader", "items_matched",
            "quantity_unit_equal", "other_numbers_on_page",
            "other_numbers_matched", "continued", "differences"]
    return {"check": "page by page, by code (pipeline/pdf/pagecheck_lists.py)",
            "lists_checked": [r["doc"] for r in results],
            "totals": {k: sum(r[k] for r in results) for k in keys},
            "lists": lists}


def pdf_words(path):
    """Words of every page of a PDF: [[(x0, y0, x1, y1, text), ...], ...]."""
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    with pymupdf.open(path) as pdf:
        return [[tuple(w[:5]) for w in page.get_text("words")] for page in pdf]


def find_pdf(pdf_dir, doc):
    for name in sorted(os.listdir(pdf_dir)):
        m = DOC_RE.match(name)
        if name.lower().endswith(".pdf") and m and m.group(1) == doc:
            return os.path.join(pdf_dir, name)
    return None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(pdf_dir, items_path, docs=None):
    """Check the lists. Returns the full per-page result (a list, one per list)."""
    with open(items_path, encoding="utf-8") as f:
        items = json.load(f)
    results = []
    for doc in docs or DEFAULT_DOCS:
        pdf = find_pdf(pdf_dir, doc)
        if pdf is None:
            raise FileNotFoundError("no PDF for %s in %s" % (doc, pdf_dir))
        pages = pdf_words(pdf)
        shown = read_document(pages)
        records = [r for r in items if r["doc"] == doc]
        result = check_document(doc, shown, records, len(pages))
        result["file"] = os.path.basename(pdf)
        result["sha256"] = sha256_file(pdf)
        results.append(result)
    return results


def write_json(path, data):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


def main(argv):
    if len(argv) < 3:
        sys.stderr.write(__doc__)
        return 2
    pdf_dir, items_path, out_path = argv[:3]
    summary_path = None
    docs = []
    for arg in argv[3:]:
        if arg.endswith(".json"):
            summary_path = arg
        else:
            docs.append(arg)
    results = run(pdf_dir, items_path, docs or None)
    write_json(out_path, results)
    summary = summarize(results)
    if summary_path:
        write_json(summary_path, summary)
    t = summary["totals"]
    print("lists=%d pages=%d items_on_page=%d matched=%d quantity_unit_equal=%d "
          "continued=%d differences=%d" % (
              len(results), t["pages_checked"], t["items_on_page"],
              t["items_matched"], t["quantity_unit_equal"], t["continued"],
              t["differences"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
