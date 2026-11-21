"""Run every twin and stage pair of the plan from data/ (W13).

Usage:
    python -m pipeline.diff.pairs [--data data] [--out out/diff] [--doc docs/TWINS.md]

Reads the organizer files with the merged readers (pipeline/lv for GAEB,
pipeline/pdf for the offer and the print; PDF needs Poppler's pdftotext),
writes one result file per pair to <out>/, the item lists it compared to
<out>/items/ (so that python -m pipeline.diff.run can be run on them), all
results to <out>/summary.json, and the written record to <doc>. Every number
in the record comes from this run. `--doc -` writes no record.

The pairs:
    V1  T1  offer AN24-0305: PDF against D84
        T2  PROJEKT_004: print PDF against X83 (twice: field against field,
            and the whole printed text against the X83 long text)
        T3  8209.003: X83 against D83
    V2  T3  8209.003 tender (D83, and X83) against the order LV24069.D86
        StBALV23040: offer D84 against order D86
    T4  NUMMER_001 X83 against StBALV23040 D84 and D86
    T5  item titles of a GAEB file in the page text of a PDF without reader

Nothing printed or written holds a unit price, a total or a price
difference; prices are counted as equal or not equal.
"""
import argparse
import os
import sys

from pipeline.diff import compare
from pipeline.diff import pdftext
from pipeline.diff import report
from pipeline.diff import run as runner
from pipeline.diff import text as textcmp
from pipeline.lv import gaeb90
from pipeline.lv import gaebxml
from pipeline.lv import model

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PDF_DIR = os.path.join(REPO, "pipeline", "pdf")

# key: (file in data/, reader, what it is)
FILES = {
    "an_pdf": ("Angebot AN24-0305.pdf", "angebot", "offer AN24-0305, PDF"),
    "an_d84": ("Angebot AN24-0305.D84", "gaeb90", "offer AN24-0305, D84"),
    "p4_pdf": ("LV-Ausdruck-[PROJEKT_004].pdf", "ausdruck", "PROJEKT_004, print PDF"),
    "p4_x83": ("GAEB-[PROJEKT_004].X83", "gaebxml", "PROJEKT_004, X83"),
    "hem_x83": ("8209.003_Leistungsverzeichnis_leer.X83", "gaebxml", "8209.003 tender, X83"),
    "hem_d83": ("8209.003_Leistungsverzeichnis_leer.D83", "gaeb90", "8209.003 tender, D83"),
    "hem_d86": ("[ORT_024] LV24069.D86", "gaeb90", "LV24069 order, D86"),
    "stb_d84": ("StBALV23040.D84", "gaeb90", "StBALV23040 offer, D84"),
    "stb_d86": ("StBALV23040.D86", "gaeb90", "StBALV23040 order, D86"),
    "n1_x83": ("[NUMMER_001]_leer.X83", "gaebxml", "NUMMER_001 tender, X83"),
}
PDFS = {
    "leer_pdf": "Leistungsverzeichnis_leer.pdf",
    "hem_pdf": "HEM2301-2_Gesamt-LV.pdf",
}

# (id, group, A, B, mode, text_map)
PAIRS = (
    ("t1_offer_pdf_d84", "twin", "an_pdf", "an_d84", "twin", "fields"),
    ("t2_print_pdf_x83_fields", "twin", "p4_pdf", "p4_x83", "twin", "fields"),
    ("t2_print_pdf_x83", "twin", "p4_pdf", "p4_x83", "twin", "a_all_to_b_long"),
    ("t3_x83_d83", "twin", "hem_x83", "hem_d83", "twin", "fields"),
    ("t3_tender_d83_order_d86", "stage", "hem_d83", "hem_d86", "stage", "fields"),
    ("t3_tender_x83_order_d86", "stage", "hem_x83", "hem_d86", "stage", "fields"),
    ("stbalv_offer_d84_order_d86", "stage", "stb_d84", "stb_d86", "stage", "fields"),
    ("t4_nummer001_x83_stbalv_d84", "t4", "n1_x83", "stb_d84", "stage", "fields"),
    ("t4_nummer001_x83_stbalv_d86", "t4", "n1_x83", "stb_d86", "stage", "fields"),
)

# (id, PDF, GAEB file, role). "control" pairs a PDF with the list of the
# other project: it shows how many titles are found by chance.
TEXT_PAIRS = (
    ("t5_leer_pdf_nummer001_x83", "leer_pdf", "n1_x83", "hypothesis"),
    ("t5_hem_pdf_8209_x83", "hem_pdf", "hem_x83", "hypothesis"),
    ("t5_hem_pdf_8209_d83", "hem_pdf", "hem_d83", "hypothesis"),
    ("t5_hem_pdf_lv24069_d86", "hem_pdf", "hem_d86", "order"),
    ("t5_control_leer_pdf_8209_x83", "leer_pdf", "hem_x83", "control"),
    ("t5_control_hem_pdf_nummer001_x83", "hem_pdf", "n1_x83", "control"),
)

HYPOTHESIS_TENDERED = 159
HYPOTHESIS_ORDERED = 197
HYPOTHESIS_ADDED = 38
T4_FIRST_ITEMS = 10      # "the first items": at least this many from the start
T5_HOLDS = 0.90          # share of searchable titles found, and found in order
T5_DOES_NOT_HOLD = 0.50

HOLDS = "holds"
DOES_NOT_HOLD = "does not hold"
UNDECIDED = "cannot be decided with the readers we have"


class PairsError(RuntimeError):
    """The pairs cannot be run; the message says why."""


def _pdf_reader(name):
    if PDF_DIR not in sys.path:
        sys.path.insert(0, PDF_DIR)
    import pdfio
    if not pdfio.pdftotext_is_poppler():
        raise PairsError("Poppler's pdftotext is not on PATH (needed for the PDF files)")
    if name == "angebot":
        import reader_angebot
        return reader_angebot.run
    import reader_ausdruck
    return reader_ausdruck.run


def read_items(data, key):
    """The item records of one organizer file, read with its merged reader."""
    file_name, reader, _ = FILES[key]
    path = os.path.join(data, file_name)
    if not os.path.isfile(path):
        raise PairsError("%s is not in %s" % (file_name, data))
    if reader == "gaeb90":
        return gaeb90.parse_file(path)[1]
    if reader == "gaebxml":
        return gaebxml.parse_file(path)[1]
    return _pdf_reader(reader)(path)[0]


def missing_files(data):
    names = [entry[0] for entry in FILES.values()] + list(PDFS.values())
    return [name for name in names if not os.path.isfile(os.path.join(data, name))]


def hypothesis_38(stages):
    """Decide the 38-item hypothesis from the stage results tender -> order
    (one per tender format). Returns verdict, counts and item numbers."""
    out = {"expected": {"tendered": HYPOTHESIS_TENDERED, "ordered": HYPOTHESIS_ORDERED,
                        "added": HYPOTHESIS_ADDED}, "runs": []}
    for pair_id, result in stages:
        stage = result["stage"]
        added = stage["added"]
        zero = result["b"]["quantity_zero"]
        keys = lambda numbers: sorted(model.item_no_key(number) for number in numbers)
        run = {
            "pair": pair_id,
            "tendered": result["a"]["items"], "ordered": result["b"]["items"],
            "in_both": result["matching"]["both"],
            "added": added, "removed": stage["removed"], "renumbered": stage["renumbered"],
            "changed": dict((name, len(stage["changed"][name])) for name in stage["changed"]),
            "order_items_quantity_zero": len(zero),
            "order_items_quantity_zero_and_total_zero": result["b"]["quantity_zero_and_total_zero"],
            "zero_items_are_the_added_items": keys(zero) == keys(added),
            "added_with_quantity_zero": len(stage["added_with_quantity_zero"]),
            "added_without_unit": len(stage["added_without_unit"]),
            "added_without_long_text": len(stage["added_without_long_text"]),
            "added_with_unit_price": stage["added_with_unit_price"],
            "added_with_a_title_of_the_tender": len(stage["added_with_a_title_of_a"]),
            "added_sections": stage["added_sections"],
            "sections_only_in_order": result["sections"]["only_b"],
            "sections_only_in_tender": result["sections"]["only_a"],
        }
        run["confirmed"] = (run["tendered"] == HYPOTHESIS_TENDERED
                            and run["ordered"] == HYPOTHESIS_ORDERED
                            and len(added) == HYPOTHESIS_ADDED
                            and not stage["removed"] and not stage["renumbered"])
        out["runs"].append(run)
    out["verdict"] = "confirmed" if out["runs"] and all(run["confirmed"] for run in out["runs"]) \
        else "refuted"
    return out


def t4_verdict(result):
    """Hypothesis "the first items are the same" for one pair."""
    start = result["from_start"]
    if not start["pairs_with_text_or_quantity"]:
        return UNDECIDED
    return HOLDS if start["same_from_start"] >= T4_FIRST_ITEMS else DOES_NOT_HOLD


def t5_verdict(found):
    """Hypothesis "the PDF is this list" from the title search."""
    if not found["searchable"]:
        return UNDECIDED
    share = found["found_total"] / found["searchable"]
    if share < T5_DOES_NOT_HOLD:
        return DOES_NOT_HOLD
    in_order = found["in_order"] / found["found_total"]
    return HOLDS if share >= T5_HOLDS and in_order >= T5_HOLDS else UNDECIDED


def run_all(data):
    """Read every file and run every pair. Returns (summary, items): the
    summary dict holds counts, item numbers and short titles and no price;
    items holds the records per file key as the readers gave them."""
    missing = missing_files(data)
    if missing:
        raise PairsError("missing in %s: %s" % (data, ", ".join(missing)))
    items = dict((key, read_items(data, key)) for key in FILES)
    pages = dict((key, pdftext.page_strings(os.path.join(data, PDFS[key]))) for key in PDFS)
    return summarize(items, pages), items


def summarize(items, pages):
    """Run every pair on item lists that are already read. items: {key of
    FILES: records}; pages: {key of PDFS: result of pdftext.page_strings}."""
    summary = {"files": dict((key, {"file": FILES[key][0], "what": FILES[key][2],
                                    "counts": compare.describe(items[key])}) for key in FILES),
               "pdfs": dict(PDFS), "pairs": [], "text_pairs": [],
               "rules": {"t4_first_items": T4_FIRST_ITEMS,
                         "t5_max_span": textcmp.MAX_SPAN, "t5_anchor": pdftext.ANCHOR,
                         "t5_long_run": 2 * pdftext.ANCHOR, "t5_min_run": pdftext.MIN_RUN,
                         "t5_holds_percent": round(T5_HOLDS * 100),
                         "t5_does_not_hold_percent": round(T5_DOES_NOT_HOLD * 100)}}
    results = {}
    for pair_id, group, key_a, key_b, mode, text_map in PAIRS:
        result = compare.compare(items[key_a], items[key_b], mode, text_map)
        results[pair_id] = result
        entry = {"id": pair_id, "group": group, "a": key_a, "b": key_b, "result": result}
        if group == "t4":
            entry["verdict"] = t4_verdict(result)
        summary["pairs"].append(entry)
    for pair_id, pdf, key, role in TEXT_PAIRS:
        found = pdftext.titles_in_pages(items[key], pages[pdf])
        classes = found.pop("classes")
        entry = {"id": pair_id, "pdf": pdf, "list": key, "role": role, "result": found}
        if role == "hypothesis":
            entry["verdict"] = t5_verdict(found)
        if role == "order":
            added = results["t3_tender_d83_order_d86"]["stage"]["added"]
            counts = dict((cls, 0) for cls in pdftext.CLASSES)
            for number in added:
                counts[classes[model.item_no_key(number)]] += 1
            entry["added_items"] = counts
        summary["text_pairs"].append(entry)
    summary["hypothesis_38"] = hypothesis_38(
        [(pair_id, results[pair_id]) for pair_id in ("t3_tender_d83_order_d86",
                                                     "t3_tender_x83_order_d86")])
    summary["hypothesis_38"]["added_titles_in_tender_pdf"] = next(
        entry["added_items"] for entry in summary["text_pairs"] if entry["role"] == "order")
    return summary


def write_all(summary, items, out_dir):
    """Write the result files; returns their paths. The item lists go to
    out_dir/items/ (they hold what the readers read, prices included, and
    stay out of git like the rest of out/)."""
    written = []
    for key in sorted(items):
        path = os.path.join(out_dir, "items", key + ".json")
        runner.write_json(path, items[key])
    for entry in summary["pairs"] + summary["text_pairs"]:
        path = os.path.join(out_dir, entry["id"] + ".json")
        runner.write_json(path, entry["result"])
        written.append(path)
    path = os.path.join(out_dir, "summary.json")
    runner.write_json(path, summary)
    written.append(path)
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pipeline.diff.pairs",
                                     description="Run all twin and stage pairs from data/.")
    parser.add_argument("--data", default=os.environ.get("LV_DATA_DIR") or "data")
    parser.add_argument("--out", default=os.path.join("out", "diff"))
    parser.add_argument("--doc", default=os.path.join("docs", "TWINS.md"),
                        help="the written record; - writes none")
    args = parser.parse_args(argv)
    try:
        summary, items = run_all(args.data)
    except PairsError as error:
        print("error: %s" % error, file=sys.stderr)
        return 2
    written = write_all(summary, items, args.out)
    for entry in summary["pairs"]:
        print("%s  %s" % (entry["id"], runner.summary_line(entry["result"])))
    for entry in summary["text_pairs"]:
        found = entry["result"]
        print("%s  titles %d, searchable %d, found %d, in order %d"
              % (entry["id"], found["items"], found["searchable"], found["found_total"],
                 found["in_order"]))
    print("38-item hypothesis: %s" % summary["hypothesis_38"]["verdict"])
    print("%d files written to %s" % (len(written), args.out))
    if args.doc != "-":
        with open(args.doc, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(report.render(summary))
        print("record written to %s" % args.doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
