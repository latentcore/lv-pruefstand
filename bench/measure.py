"""M1 to M9 (MASTER_PLAN §11, docs/PREREG.md). Each function returns one record of bench.json.

A record holds "id", "name", "threshold", "met" (yes / no / not measurable /
not measured yet), "reason" where one is needed, and the numbers of the
measurement: counts, percentages, seconds, file names and item numbers. The
readers and checks are the ones of pipeline/; nothing is copied here. Prices
are touched by code only (M2, M3, M7) and never written.
"""
import copy
import json
import os
import platform
import statistics
import sys
import tempfile
import time

from pipeline.base.run import run_all
from pipeline.common import quotes, severity
from pipeline.lv import gaeb90, gaebxml, model

from bench import prereg, seeded, twins

_PDF_DIR = os.path.join(prereg.REPO_ROOT, "pipeline", "pdf")
if _PDF_DIR not in sys.path:
    sys.path.append(_PDF_DIR)  # pipeline/pdf is a folder of scripts, not a package

import pagecheck_lists  # noqa: E402
import reader_79222  # noqa: E402


def record(row_id, met, reason=None, **numbers):
    """One record of bench.json for a row of the table."""
    name, threshold = next((name, threshold) for key, name, threshold in prereg.ROWS if key == row_id)
    if met not in prereg.MET_VALUES:
        raise ValueError("unknown 'threshold met' value %r" % met)
    entry = {"id": row_id, "name": name, "threshold": threshold, "met": met}
    if reason:
        entry["reason"] = reason
    entry.update(numbers)
    return entry


def missing(row_id, names):
    """The record of a measurement whose input is not there."""
    return record(row_id, prereg.NOT_YET, reason="input not found: %s" % ", ".join(names))


def tenths(part, whole):
    """part / whole in tenths of a percent, cut (never rounded up); None without a whole."""
    return (1000 * part) // whole if whole else None


def at_least(part, whole, percent):
    """part / whole >= percent, on the counts themselves."""
    return bool(whole) and 100 * part >= percent * whole


class Context:
    """The input folders of one run, and what several measurements share."""

    def __init__(self, data="data", reviews="reviews", findings=None, work=None):
        self.data = data
        self.reviews = reviews
        self.findings = findings or os.path.join(prereg.REPO_ROOT, prereg.M6_FINDINGS)
        self._work = work
        self._gaeb = {}
        self._pdf_runs = None

    def path(self, file_name):
        return os.path.join(self.data, file_name)

    def has(self, file_name):
        return os.path.isfile(self.path(file_name))

    def gaeb(self, file_name):
        """The records of one GAEB file (read once per run)."""
        if file_name not in self._gaeb:
            self._gaeb[file_name] = read_gaeb(self.path(file_name))
        return self._gaeb[file_name]

    def work(self):
        if self._work is None:
            self._work = tempfile.mkdtemp(prefix="bench-")
        return self._work

    def lv_pdfs(self):
        if not os.path.isdir(self.data):
            return []
        return sorted(name for name in os.listdir(self.data)
                      if name.lower().endswith(".pdf") and reader_79222.doc_id(name))

    def pdf_runs(self):
        """Two runs of pdftotext and the 79-222 reader, each into a fresh folder:
        [(text folder, items, manifest), (text folder, items, manifest)]."""
        if self._pdf_runs is None:
            runs = []
            for number in (1, 2):
                text_dir = os.path.join(self.work(), "run%d" % number, "text")
                out_dir = os.path.join(self.work(), "run%d" % number, "out")
                reader_79222.extract_pdfs(self.data, text_dir)
                items, manifest = reader_79222.run(text_dir, out_dir, self.data)
                runs.append((text_dir, items, manifest))
            self._pdf_runs = runs
        return self._pdf_runs


def read_gaeb(path):
    """The records of one GAEB file, through the reader of pipeline/lv that fits its name."""
    reader = gaeb90 if gaeb90.is_gaeb90_name(path) else gaebxml
    _project, records, _entry = reader.parse_file(path)
    return records


def positions(records):
    return [r for r in records if model.is_position(r)]


# ---- M1 ---------------------------------------------------------------------

def m1(ctx):
    files, absent = [], []
    for file_name, expected in prereg.GAEB_FILES:
        entry = {"file": file_name, "expected": expected, "read": None, "equal": False}
        if not ctx.has(file_name):
            absent.append(file_name)
            entry["error"] = "file not found"
        else:
            try:
                entry["read"] = len(positions(ctx.gaeb(file_name)))
                entry["equal"] = entry["read"] == expected
            except Exception as error:  # a file the reader cannot read does not count
                entry["error"] = "reader error: %s" % type(error).__name__
        files.append(entry)
    equal = sum(1 for entry in files if entry["equal"])
    if absent:
        met, reason = prereg.NOT_YET, "input not found: %s" % ", ".join(absent)
    else:
        met, reason = (prereg.YES if equal == prereg.M1_NEEDED else prereg.NO), None
    return record("M1", met, reason, files_expected=len(files), files_equal=equal, files=files)


# ---- M2 ---------------------------------------------------------------------

def m2(ctx):
    absent = [name for name in prereg.PRICED_FILES if not ctx.has(name)]
    if absent:
        return missing("M2", absent)
    files = []
    for file_name in prereg.PRICED_FILES:
        records = ctx.gaeb(file_name)
        check = model.price_check(records)
        files.append({
            "file": file_name, "items": len(positions(records)),
            "checked": check["equal"] + check["not_equal"], "deviating": check["not_equal"],
            "not_checkable_no_quantity": check["no_quantity"],
            "deviating_items": list(check["not_equal_items"]),
        })
    return record(
        "M2", prereg.YES, files=files,
        checked=sum(f["checked"] for f in files), deviating=sum(f["deviating"] for f in files),
        not_checkable_no_quantity=sum(f["not_checkable_no_quantity"] for f in files))


# ---- M3 ---------------------------------------------------------------------

def m3(ctx):
    absent = [name for _twin, pdf, gaeb in prereg.M3_PAIRS for name in (pdf, gaeb) if not ctx.has(name)]
    if absent:
        return missing("M3", absent)
    if not twins.available():
        return record("M3", prereg.NOT_YET, reason=twins.NOT_AVAILABLE)
    try:
        pairs = [twins.measure(ctx, twin, pdf, gaeb) for twin, pdf, gaeb in prereg.M3_PAIRS]
    except twins.TwinError as error:  # Poppler's pdftotext is missing
        return record("M3", prereg.NOT_YET, reason=str(error))
    parts = []
    for pair in pairs:
        parts.append(at_least(pair["items_in_both"], pair["items_gaeb"], prereg.M3_ITEMS_PERCENT))
        if pair["prices_measurable"]:
            parts.append(all(at_least(pair[key + "_equal"], pair[key + "_compared"], prereg.M3_PRICES_PERCENT)
                             for key in ("unit_prices", "totals") if pair[key + "_compared"]))
    not_measurable = [pair["twin"] for pair in pairs if not pair["prices_measurable"]]
    reason = None
    if not_measurable:
        reason = "prices not measurable for %s" % ", ".join(not_measurable)
    return record("M3", prereg.YES if all(parts) else prereg.NO, reason, pairs=pairs)


# ---- M4 ---------------------------------------------------------------------

def m4(ctx):
    pdfs = ctx.lv_pdfs()
    if len(pdfs) != prereg.M4_LISTS:
        return record("M4", prereg.NOT_YET, lists=len(pdfs), lists_expected=prereg.M4_LISTS,
                      reason="input not found: %d of %d LV_*.pdf" % (len(pdfs), prereg.M4_LISTS))
    try:
        (_text, items, first), (_text2, _items2, second) = ctx.pdf_runs()
    except RuntimeError as error:  # pdftotext is not installed
        return record("M4", prereg.NOT_YET, reason=str(error))
    counts = [dict((entry["doc"], entry["items"]) for entry in manifest) for manifest in (first, second)]
    docs = sorted(set(counts[0]) | set(counts[1]))
    difference = sum(abs(counts[0].get(doc, 0) - counts[1].get(doc, 0)) for doc in docs)
    items_path = os.path.join(ctx.work(), "run1", "out", "items.json")
    summary = pagecheck_lists.summarize(
        pagecheck_lists.run(ctx.data, items_path, list(prereg.M4_PAGECHECK_LISTS)))
    totals = summary["totals"]
    with_warnings = [entry["doc"] for entry in first if entry["warnings"]]
    numbers = {
        "lists": len(first), "lists_expected": prereg.M4_LISTS,
        "items_run1": sum(counts[0].values()), "items_run2": sum(counts[1].values()),
        "difference": difference,
        "pagecheck": {
            "lists": list(summary["lists_checked"]), "pages": totals["pages_checked"],
            "items_on_page": totals["items_on_page"], "items_matched": totals["items_matched"],
            "quantity_unit_equal": totals["quantity_unit_equal"], "differences": totals["differences"],
        },
        "warnings": sum(len(entry["warnings"]) for entry in first),
        "lists_with_warnings": with_warnings,
        "unparsed_lines": sum(entry["unparsed_lines"] for entry in first),
    }
    passed = difference == 0 and totals["differences"] == 0
    return record("M4", prereg.YES if passed else prereg.NO, **numbers)


# ---- M5 ---------------------------------------------------------------------

def _review_class(entry):
    """Why a review entry is not counted as an expert decision; None when it is counted."""
    if not isinstance(entry, dict):
        return "not a review record"
    by, at, status = entry.get("by"), entry.get("at"), entry.get("status")
    if status not in prereg.M5_STATUSES:
        return "no decision"
    if not isinstance(by, str) or not by.strip():
        return "no role given"
    if "test" in by.casefold():
        return "role holds 'test'"
    start, end = prereg.M5_SESSION
    if not isinstance(at, str) or not start <= at[:16] <= end:
        return "outside the expert session"
    return None


def m5(ctx):
    path = os.path.join(ctx.reviews, "%s.json" % prereg.M5_PROJECT)
    file_name = "reviews/%s.json" % prereg.M5_PROJECT
    if not os.path.isfile(path):
        return record("M5", prereg.NOT_YET, reason=prereg.M5_NOT_YET, file=file_name, file_found=False)
    try:
        with open(path, encoding="utf-8-sig") as handle:
            reviews = json.load(handle)
    except (OSError, ValueError):
        reviews = None
    if not isinstance(reviews, dict):
        return record("M5", prereg.NOT_YET, reason=prereg.M5_NOT_YET + " (the review file cannot be read)",
                      file=file_name, file_found=True)
    roles, not_counted, roles_found = {}, {}, set()
    for entry in reviews.values():
        by = entry.get("by") if isinstance(entry, dict) else None
        if isinstance(by, str) and by.strip():
            roles_found.add(by.strip())
        why_not = _review_class(entry)
        if why_not:
            not_counted[why_not] = not_counted.get(why_not, 0) + 1
            continue
        counts = roles.setdefault(by.strip(), dict((status, 0) for status in prereg.M5_STATUSES))
        counts[entry["status"]] += 1
    totals = dict((status, sum(counts[status] for counts in roles.values())) for status in prereg.M5_STATUSES)
    counted = sum(totals.values())
    numbers = {
        "file": file_name, "file_found": True, "entries": len(reviews), "counted": counted,
        "confirmed": totals["confirmed"], "rejected": totals["rejected"], "unclear": totals["unclear"],
        "by_role": [dict(role=role, **roles[role]) for role in sorted(roles)],
        "not_counted": dict(sorted(not_counted.items())), "roles_found": sorted(roles_found),
    }
    if not counted:
        return record("M5", prereg.NOT_YET, reason=prereg.M5_NOT_YET, **numbers)
    return record("M5", prereg.YES, **numbers)


# ---- M6 ---------------------------------------------------------------------

def m6(ctx):
    if not os.path.isfile(ctx.findings):
        return missing("M6", [prereg.M6_FINDINGS.replace(os.sep, "/")])
    if not ctx.lv_pdfs():
        return missing("M6", ["LV_*.pdf"])
    try:
        text_dir, items, _manifest = ctx.pdf_runs()[0]
    except RuntimeError as error:
        return record("M6", prereg.NOT_YET, reason=str(error))
    with open(ctx.findings, encoding="utf-8-sig") as handle:
        findings = json.load(handle)
    pages = {}
    for name in sorted(os.listdir(text_dir)):
        doc = reader_79222.doc_id(name)
        if doc and name.endswith(".txt"):
            with open(os.path.join(text_dir, name), encoding="utf-8") as handle:
                pages.update(quotes.pages_from_text(doc, handle.read()))
    kept, dropped = quotes.filter_findings(findings, items, pages)
    return record(
        "M6", prereg.YES, file=prereg.M6_FINDINGS.replace(os.sep, "/"), findings=len(findings),
        quotes=sum(len(f.get("sources") or []) for f in findings), kept=len(kept), dropped=len(dropped),
        dropped_ids=[f.get("id") for f in dropped])


# ---- M7 ---------------------------------------------------------------------

def m7(ctx):
    if not ctx.has(prereg.CLEAN_FILE):
        return missing("M7", [prereg.CLEAN_FILE])
    records = ctx.gaeb(prereg.CLEAN_FILE)
    result = seeded.measure(records)
    met = prereg.YES if at_least(result["found"], result["planted"], prereg.M7_PERCENT) else prereg.NO
    return record(
        "M7", met, file=prereg.CLEAN_FILE, seed=prereg.SEED, per_type=prereg.M7_PER_TYPE,
        planted=result["planted"], found=result["found"],
        percent_tenths=tenths(result["found"], result["planted"]),
        types=result["types"], x=seeded.X_NOT_MEASURED)


# ---- M8 ---------------------------------------------------------------------

def false_alarms(records):
    """high + medium findings of the 12 base checks on the records, after the severity rule."""
    findings, _summary = run_all(copy.deepcopy(records))
    findings, _decided = severity.apply(findings, records)
    by_check = {}
    for finding in findings:
        if finding["severity"] in prereg.M8_LEVELS:
            by_check[finding["check"]] = by_check.get(finding["check"], 0) + 1
    count, items = sum(by_check.values()), len(positions(records))
    return {
        "items": items, "high_medium": count, "by_check": by_check,
        "per_100_hundredths": (10000 * count) // items if items else None,
        "within": bool(items) and 100 * count <= prereg.M8_PER_100 * items,
    }


def m8(ctx):
    if not ctx.has(prereg.CLEAN_FILE):
        return missing("M8", [prereg.CLEAN_FILE])
    clean = dict(file=prereg.CLEAN_FILE, **false_alarms(ctx.gaeb(prereg.CLEAN_FILE)))
    other = None
    if ctx.has(prereg.M8_OTHER_FILE):
        other = dict(file=prereg.M8_OTHER_FILE, **false_alarms(ctx.gaeb(prereg.M8_OTHER_FILE)))
    within = clean.pop("within")
    if other:
        other.pop("within")
    return record("M8", prereg.YES if within else prereg.NO, clean=clean, other=other)


# ---- M9 ---------------------------------------------------------------------

def build_300(records, count=prereg.M9_ITEMS):
    """The records of a file made into a list of `count` items by the rule of docs/PREREG.md:
    all records in file order, then copies of the first items with the numbers 99.10, 99.20, ... in a
    new section 99. A file with more items than `count` cannot be used."""
    items = positions(records)
    lacking = count - len(items)
    if lacking < 0 or lacking > len(items):
        raise ValueError("cannot build %d items from a file with %d" % (count, len(items)))
    built = copy.deepcopy(records)
    for number, item in enumerate(items[:lacking], 1):
        added = copy.deepcopy(item)
        added["item_no"], added["section"] = "99.%d" % (10 * number), "99"
        built.append(added)
    return built


def median_seconds(action, runs=prereg.M9_RUNS, clock=time.perf_counter):
    """Median of the seconds of `runs` calls of action(), no warm-up run."""
    seconds = []
    for _run in range(runs):
        start = clock()
        action()
        seconds.append(clock() - start)
    return round(statistics.median(seconds), 4)


def machine():
    """The machine of the run: processor, cores, memory, system, Python. No host name."""
    processor, memory = platform.processor() or platform.machine(), None
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as handle:
            names = [line.split(":", 1)[1].strip() for line in handle if line.startswith("model name")]
        processor = names[0] if names else processor
        with open("/proc/meminfo", encoding="utf-8") as handle:
            kilobytes = [int(line.split()[1]) for line in handle if line.startswith("MemTotal")]
        memory = round(kilobytes[0] / 1024 / 1024) if kilobytes else None
    except (OSError, ValueError, IndexError):
        pass
    parts = [processor, "%d cores" % (os.cpu_count() or 0)]
    if memory:
        parts.append("%d GB RAM" % memory)
    parts.append("%s %s" % (platform.system(), platform.release()))
    parts.append("Python %s" % platform.python_version())
    return ", ".join(part for part in parts if part)


def m9(ctx, clock=time.perf_counter):
    absent = [name for name in (prereg.M9_BUILT_FROM, prereg.M9_AS_IS_FILE) if not ctx.has(name)]
    if absent:
        return missing("M9", absent)
    built = build_300(ctx.gaeb(prereg.M9_BUILT_FROM))
    as_is = ctx.gaeb(prereg.M9_AS_IS_FILE)
    inputs = []
    for label, file_name, records in (("built", prereg.M9_BUILT_FROM, built),
                                      ("as it is", prereg.M9_AS_IS_FILE, as_is)):
        inputs.append({
            "input": label, "file": file_name, "items": len(positions(records)),
            "median_seconds": median_seconds(lambda: run_all(records), clock=clock),
            "read_median_seconds": median_seconds(lambda: read_gaeb(ctx.path(file_name)), clock=clock),
        })
    within = all(entry["median_seconds"] <= prereg.M9_SECONDS for entry in inputs)
    return record("M9", prereg.YES if within else prereg.NO, runs=prereg.M9_RUNS, inputs=inputs,
                  machine=machine())


MEASUREMENTS = (m1, m2, m3, m4, m5, m6, m7, m8, m9)


def run(ctx):
    """All nine records, in order."""
    return [measurement(ctx) for measurement in MEASUREMENTS]
