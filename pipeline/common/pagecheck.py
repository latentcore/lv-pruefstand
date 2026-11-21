"""Page check of the findings: does every quote stand on its stated PDF page,
and is that page a page of the cited item?

    python -m pipeline.common.pagecheck [--items <items.json>] <findings in> <data dir> <out dir> [<findings out>]

For every source of every finding the stated page of the source PDF is read,
the quote is looked up in the text of that page with the normalization of
pipeline/common/quotes.py, and the page is saved as an image with the quote
highlighted in yellow. This is a check by code. No human looked at the pages.

Written to <out dir> (data, never in git):
  pages/<finding id>_<source index, from 0>.png   the stated page; both pages,
                                                  one above the other, when the
                                                  quote runs over a page break
  pagecheck.json                                  per finding and source: doc,
                                                  page, status, how it matched,
                                                  the pages of the cited item,
                                                  another page if found there
<findings out>, when given: the findings with quotes_verified = true only
where every source of the finding has the status "found"; nothing else is
changed.

"status" of a source in pagecheck.json ("found" is true for the first only):
  found              the quote stands on the stated page, and the stated page
                     is a page of the cited item
  page_not_of_item   the quote stands on the stated page, but that page is not
                     a page of the cited item ("item_page" is the page where
                     the item starts, "item_pages" all its pages; "other_page"
                     is the page of the item that holds the quote, if one does)
  other_page         the quote does not stand on the stated page but on
                     "other_page" of the same list
  not_found          the quote stands on no page of the list

Pages of an item: items.json (--items; without the option <out dir>/items.json
when that file exists) gives the page where each entry of a list starts. An
item has the pages from its own page up to the page where the next entry of
the list starts; the last entry runs to the last page. A source without item
number is not checked this way. Without items.json no source is, and the
summary counts these sources as item_page_not_checked.

How a quote can match ("match" in pagecheck.json):
  exact                    the normalized quote stands in the normalized text
  line_end_hyphen_joined   the same, and the text had a hyphen at a line end
                           inside the quote that the normalization joined
                           ("Wärme-" / "dämmung" for the quote "Wärmedämmung")
  line_end_hyphen_kept     the quote keeps a hyphen that stands at a line end
                           of the page ("Ein- und Ausbau", "Estrich-Dämmung");
                           quotes.py alone does not find such a quote

Page break: "pages" holds one page, or two when the quote runs over a page
break; the stated page must be one of the two. Between the two parts only
these lines may be left out, any other line there makes the quote fail:
  footer       the lines at the bottom of the first page that stand, digits
               aside (page number), at the same place on every other page of
               the PDF
  carry line   the one line right above that footer, if the same line stands
               on the second page under lines that both pages have, letter for
               letter, at their top ("Übertrag:" under the page header); it is
               left out on both pages
  header       the lines of the second page above that carry line; without a
               carry line, the lines at its top that the first page and more
               than half of the other pages have, letter for letter, at the
               same place
A line that only looks like the last line of many pages (a quantity line above
"Übertrag:") is none of these. A quote over more than two pages is not found.

Page text: the words of PyMuPDF in their order on the page (top to bottom,
left to right). When that text does not hold the quote and Poppler's pdftotext
is on PATH, its -layout text of the page is tried too ("text" names the one
that matched; the highlight then goes to the same words of PyMuPDF, looked
up without regard to spaces).

The PDF of a doc is the one file in <data dir> named <doc>.pdf or <doc>_*.pdf.
"""
import functools
import json
import os
import re
import shutil
import subprocess
import sys

try:
    import pymupdf as fitz
except ImportError:  # older PyMuPDF
    import fitz

from pipeline.common import quotes

DPI = 150
PYMUPDF = "pymupdf"
PDFTOTEXT = "pdftotext"

# "status" of a source in pagecheck.json
FOUND = "found"
NOT_ITEM_PAGE = "page_not_of_item"
OTHER_PAGE = "other_page"
NOT_FOUND = "not_found"

# Stands in the page text where the normalization joined two lines.
_MARK = "\x00"
_MARK_RE = re.escape(_MARK)
_DIGITS = re.compile(r"\d+")
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")

_norm = functools.lru_cache(maxsize=200000)(quotes.normalize)


@functools.lru_cache(maxsize=200000)
def _join_kind(first, second):
    """How quotes.normalize treats the break between two lines that follow
    each other: 0 = a space, 1 = joined and the hyphen dropped, 2 = joined
    (soft hyphen), -1 = something this module does not know."""
    a, b = _norm(first), _norm(second)
    if not a or not b:
        return 0
    joined = _norm(first + "\n" + second)
    if joined == a + " " + b:
        return 0
    if a.endswith("-") and joined == a[:-1] + b:
        return 1
    if joined == a + b:
        return 2
    return -1


def _raw(line):
    return " ".join(chunk[0] for chunk in line)


def build_stream(lines):
    """Normalized text of the lines, with _MARK where two lines were joined.

    lines: a list of lines; a line is a list of chunks (text, page, box), box
    is (x0, y0, x1, y1) or None. Returns (text, spans); spans are
    (start, end, page, box) per chunk. Without the marks the text equals
    quotes.normalize of the lines; if it would not, the plain normalized text
    comes back with no spans.
    """
    pieces, spans, length = [], [], 0
    previous = None
    for line in lines:
        raw = _raw(line)
        kind = _join_kind(previous, raw) if previous is not None else 0
        first = True
        for text, page, box in line:
            norm = _norm(text)
            if not norm:
                continue
            if first and kind in (1, 2) and pieces:
                if kind == 1:
                    pieces[-1] = pieces[-1][:-1]
                    start, end, last_page, last_box = spans[-1]
                    spans[-1] = (start, end - 1, last_page, last_box)
                    length -= 1
                pieces.append(_MARK)
                length += 1
            elif length:
                pieces.append(" ")
                length += 1
            first = False
            pieces.append(norm)
            spans.append((length, length + len(norm), page, box))
            length += len(norm)
        previous = raw
    text = "".join(pieces)
    whole = quotes.normalize("\n".join(_raw(line) for line in lines))
    if _MARK in whole or text.replace(_MARK, "") != whole:
        return whole, []
    return text, spans


def quote_patterns(quote):
    """(normalized quote, strict, tolerant, loose pattern) or None for an
    empty quote. The patterns run on the text of build_stream. The strict one
    finds what quotes.quote_in_text finds. The tolerant one also lets a "-" or
    "- " of the quote stand for a joined line end. The loose one ignores
    spaces; it only places a highlight and never decides "found"."""
    needle = quotes.normalize(quote) if isinstance(quote, str) else ""
    if not needle:
        return None
    strict = (_MARK_RE + "?").join(re.escape(c) for c in needle)
    parts, i = [], 0
    while i < len(needle):
        c = needle[i]
        if c == "-" and needle[i + 1:i + 2] == " ":
            parts.append("(?:-%s? |%s)" % (_MARK_RE, _MARK_RE))
            i += 2
        elif c == "-":
            parts.append("(?:-|%s)" % _MARK_RE)
            i += 1
        else:
            parts.append(re.escape(c))
            i += 1
    tolerant = (_MARK_RE + "?").join(parts)
    loose = ("[ %s]?" % _MARK_RE).join(
        "(?:-|%s)" % _MARK_RE if c == "-" else re.escape(c) for c in needle if c != " ")
    return needle, re.compile(strict), re.compile(tolerant), re.compile(loose)


def find_in_stream(patterns, text, spans, both_pages=None, loose=False):
    """Look the quote up in a stream. Returns (match kind, chunk spans of the
    match) or None. both_pages = (a, b): only a match with chunks of both
    pages counts. loose: use the loose pattern alone (to place a highlight)."""
    needle, strict, tolerant, loose_pattern = patterns
    for pattern in ((loose_pattern,) if loose else (strict, tolerant)):
        pos = 0
        while True:
            m = pattern.search(text, pos)
            if not m:
                break
            hit = [s for s in spans if s[0] < m.end() and s[1] > m.start()]
            if both_pages is None or set(both_pages) <= {s[2] for s in hit}:
                found = m.group(0)
                if _MARK not in found:
                    kind = "exact"
                elif found.replace(_MARK, "") == needle:
                    kind = "line_end_hyphen_joined"
                else:
                    kind = "line_end_hyphen_kept"
                return kind, hit
            pos = m.start() + 1
    return None


def physical_lines(words, page):
    """Group PyMuPDF words (x0, y0, x1, y1, text, ...) into lines, top to
    bottom, each line left to right. Returns lines of chunks."""
    words = sorted(words, key=lambda w: ((w[1] + w[3]) / 2.0, w[0]))
    lines, middle, height = [], None, None
    for w in words:
        mid, h = (w[1] + w[3]) / 2.0, w[3] - w[1]
        if middle is None or abs(mid - middle) > 0.5 * min(h, height):
            lines.append([])
            middle, height = mid, h
        lines[-1].append(w)
    return [[(w[4], page, tuple(w[:4])) for w in sorted(line, key=lambda w: w[0])]
            for line in lines]


class PdfText:
    """Page texts of one PDF, per text engine, read when first asked for."""

    def __init__(self, path, use_pdftotext=True):
        self.path = path
        with fitz.open(path) as doc:
            self.page_count = doc.page_count
        self.engines = [PYMUPDF]
        if use_pdftotext and shutil.which("pdftotext"):
            self.engines.append(PDFTOTEXT)
        self._lines = {}
        self._layout = None
        self._cuts = {}

    def lines(self, engine, page):
        key = (engine, page)
        if key not in self._lines:
            if engine == PYMUPDF:
                with fitz.open(self.path) as doc:
                    words = doc[page - 1].get_text("words")
                self._lines[key] = physical_lines(words, page)
            else:
                text = self._layout_pages()[page - 1]
                self._lines[key] = [[(line, page, None)] if line.strip() else []
                                    for line in text.split("\n")]
        return self._lines[key]

    def _layout_pages(self):
        if self._layout is None:
            pages = []
            try:
                res = subprocess.run(
                    ["pdftotext", "-layout", "-enc", "UTF-8", self.path, "-"],
                    capture_output=True, check=True)
                pages = res.stdout.decode("utf-8", "replace").split("\f")
            except (OSError, subprocess.CalledProcessError):
                pass
            pages = pages[:self.page_count]
            pages += [""] * (self.page_count - len(pages))
            self._layout = pages
        return self._layout

    def _raws(self, engine, page):
        return [_norm(_raw(line)) for line in self.lines(engine, page) if line]

    def _keys(self, engine, page):
        return [_DIGITS.sub("#", raw) for raw in self._raws(engine, page)]

    def repeated(self, engine, page):
        """(top, bottom) of a page. top: how many lines at the top also stand,
        letter for letter, at the same place on more than half of the other
        pages. bottom: how many lines at the bottom also stand, digits aside
        (page number), at the same place on every other page: the footer."""
        key = (engine, page)
        if key not in self._cuts:
            others = [other for other in range(1, self.page_count + 1) if other != page]
            cuts = []
            for texts, edge, need in (
                    (self._raws, lambda lines, n: lines[n], len(others) // 2 + 1),
                    (self._keys, lambda lines, n: lines[-1 - n], max(len(others), 1))):
                mine = texts(engine, page)
                same, n = [texts(engine, other) for other in others], 0
                while n < len(mine):
                    same = [lines for lines in same
                            if len(lines) > n and edge(lines, n) == edge(mine, n)]
                    if len(same) < need:
                        break
                    n += 1
                cuts.append(n)
            self._cuts[key] = tuple(cuts)
        return self._cuts[key]

    def break_cut(self, engine, page):
        """(bottom, top): how many lines at the bottom of `page` and at the top
        of the next page are no body lines and may be left out of a quote that
        runs over this page break. See "Page break" in the module text."""
        upper, lower = self._raws(engine, page), self._raws(engine, page + 1)
        footer = self.repeated(engine, page)[1]
        shared = 0
        while shared < min(len(upper), len(lower)) and upper[shared] == lower[shared]:
            shared += 1
        if footer < len(upper):
            carry = upper[len(upper) - footer - 1]
            for top in range(min(shared, len(lower) - 1) + 1):
                if lower[top] == carry:
                    return footer + 1, top + 1
        return footer, min(shared, self.repeated(engine, page + 1)[0])

    def match_page(self, engine, page, patterns, loose=False):
        text, spans = build_stream(self.lines(engine, page))
        return find_in_stream(patterns, text, spans, loose=loose)

    def match_pair(self, engine, page, patterns, loose=False):
        """The quote starts on `page` and ends on the next one."""
        if page < 1 or page + 1 > self.page_count:
            return None
        upper = [line for line in self.lines(engine, page) if line]
        lower = [line for line in self.lines(engine, page + 1) if line]
        max_bottom, max_top = self.break_cut(engine, page)
        for bottom in range(max_bottom, -1, -1):
            for top in range(max_top, -1, -1):
                lines = upper[:len(upper) - bottom] + lower[top:]
                text, spans = build_stream(lines)
                hit = find_in_stream(patterns, text, spans, both_pages=(page, page + 1),
                                     loose=loose)
                if hit:
                    return hit
        return None

    def word_boxes(self, pages, patterns):
        """Word boxes for a quote that only the text of another engine held."""
        if len(pages) == 1:
            hit = self.match_page(PYMUPDF, pages[0], patterns, loose=True)
        else:
            hit = self.match_pair(PYMUPDF, pages[0], patterns, loose=True)
        return [(s[2], s[3]) for s in hit[1]] if hit else []


def find_pdf(data_dir, doc):
    """Path of the PDF of a doc id, or (None, error)."""
    hits = []
    for folder, _dirs, names in os.walk(data_dir):
        for name in names:
            stem, ext = os.path.splitext(name)
            if ext.lower() == ".pdf" and (stem == doc or stem.startswith(doc + "_")):
                hits.append(os.path.join(folder, name))
    if not hits:
        return None, "pdf_not_found"
    if len(hits) > 1:
        return None, "pdf_ambiguous"
    return hits[0], None


def render(pdf_path, pages, boxes, out_path):
    """Save the pages (one above the other) as PNG with the boxes in yellow.
    boxes: (page, (x0, y0, x1, y1))."""
    pixmaps = []
    with fitz.open(pdf_path) as doc:
        for number in pages:
            page = doc[number - 1]
            rects = [fitz.Rect(box) for p, box in boxes if p == number]
            if rects:
                page.add_highlight_annot(rects)
            pixmaps.append(page.get_pixmap(dpi=DPI, alpha=False))
    if len(pixmaps) == 1:
        image = pixmaps[0]
    else:
        width = max(p.width for p in pixmaps)
        height = sum(p.height for p in pixmaps)
        image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height), False)
        image.clear_with(255)
        y = 0
        for p in pixmaps:
            p.set_origin(0, y)
            image.copy(p, p.irect)
            y += p.height
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    image.save(out_path)


def _valid_page(page, pdf):
    if page is None:
        return "page_missing"
    if isinstance(page, bool) or not isinstance(page, int):
        return "page_not_a_number"
    if page < 1 or page > pdf.page_count:
        return "page_out_of_range"
    return None


def item_ranges(items):
    """{(doc, item number): [(first page, page where the next entry of the
    list starts, or None for the last entry)]} from items.json records, in
    their order in the file. A number that stands twice in a list (a heading
    and its note) has two ranges."""
    by_doc = {}
    for item in items:
        if isinstance(item, dict) and _is_page(item.get("page")):
            by_doc.setdefault(item.get("doc"), []).append(item)
    ranges = {}
    for doc, entries in by_doc.items():
        for index, item in enumerate(entries):
            last = entries[index + 1]["page"] if index + 1 < len(entries) else None
            ranges.setdefault((doc, item.get("item_no")), []).append((item["page"], last))
    return ranges


def _is_page(page):
    return isinstance(page, int) and not isinstance(page, bool) and page >= 1


def _item_pages(source, ranges, pdf):
    """Pages of the cited item as [(first, last)], [] when the list has no
    such item, None when there is nothing to check against."""
    item_no = source.get("item_no")
    if ranges is None or not isinstance(item_no, str) or not item_no:
        return None
    return [(first, max(first, pdf.page_count if last is None else last))
            for first, last in ranges.get((source.get("doc"), item_no), [])]


def check_source(source, pdf, pdf_error, ranges=None):
    """Check one source. ranges: item_ranges() of items.json, or None for no
    check of the item's pages. Returns (result for pagecheck.json, pages to
    draw, boxes to highlight)."""
    page = source.get("page")
    result = {
        "doc": source.get("doc"), "item_no": source.get("item_no"), "page": page,
        "status": NOT_FOUND, "found": False, "match": None, "pages": [], "text": None,
        "item_page": None, "item_pages": None, "other_page": None, "other_match": None,
        "highlight_boxes": 0, "image": None, "error": None,
    }
    patterns = quote_patterns(source.get("quote"))
    if patterns is None:
        result["error"] = "quote_missing"
    if pdf is None:
        result["error"] = pdf_error
        return result, [], []
    page_error = _valid_page(page, pdf)
    if patterns is None:
        return result, ([] if page_error else [page]), []
    if page_error:
        result["error"] = page_error
        stated = None
    else:
        stated = page
        hit = _match_at(pdf, stated, patterns)
        if hit:
            kind, engine, pages, boxes = hit
            result.update(match=kind, pages=pages, text=engine, highlight_boxes=len(boxes))
            of_item = _item_pages(source, ranges, pdf)
            if of_item is None:
                result.update(status=FOUND, found=True)
                return result, pages, boxes
            result["item_pages"] = _page_list(of_item)
            if of_item:
                result["item_page"] = of_item[0][0]
            else:
                result["error"] = "item_not_in_items"
            if stated in result["item_pages"]:
                result.update(status=FOUND, found=True)
                return result, pages, boxes
            result["status"] = NOT_ITEM_PAGE
            for first in result["item_pages"]:
                there = _match_at(pdf, first, patterns, before=False)
                if there:
                    result.update(other_page=first, other_match=_other_match(there))
                    break
            return result, pages, boxes
    others = [p for p in range(1, pdf.page_count + 1) if p != stated]
    for engine in pdf.engines:
        for other in others:
            hit = pdf.match_page(engine, other, patterns)
            if hit:
                result.update(status=OTHER_PAGE, other_page=other, other_match=hit[0])
                return result, ([stated] if stated else []), []
    for engine in pdf.engines:
        for other in others:
            hit = pdf.match_pair(engine, other, patterns)
            if hit:
                result.update(status=OTHER_PAGE, other_page=other,
                              other_match=hit[0] + ", pages %d-%d" % (other, other + 1))
                return result, ([stated] if stated else []), []
    return result, ([stated] if stated else []), []


def _match_at(pdf, page, patterns, before=True):
    """The quote on `page`, or over the break after it, or (before) over the
    break in front of it: (match kind, text engine, pages, boxes) or None."""
    tries = [(lambda e: pdf.match_page(e, page, patterns), [page]),
             (lambda e: pdf.match_pair(e, page, patterns), [page, page + 1])]
    if before:
        tries.append((lambda e: pdf.match_pair(e, page - 1, patterns), [page - 1, page]))
    for attempt, pages in tries:
        for engine in pdf.engines:
            hit = attempt(engine)
            if hit:
                kind, spans = hit
                boxes = [(s[2], s[3]) for s in spans if s[3] is not None]
                if engine != PYMUPDF:
                    boxes = pdf.word_boxes(pages, patterns)
                return kind, engine, pages, boxes
    return None


def _other_match(hit):
    kind, _engine, pages, _boxes = hit
    return kind if len(pages) == 1 else kind + ", pages %d-%d" % tuple(pages)


def _page_list(of_item):
    return sorted({page for first, last in of_item for page in range(first, last + 1)})


def check_findings(findings, data_dir, out_dir, use_pdftotext=True, items=None):
    """Check every source of every finding, save the page images under
    out_dir/pages and return the report (the content of pagecheck.json).
    items: the records of items.json; without them the stated page is not
    checked against the pages of the cited item."""
    if not isinstance(findings, list) or not all(isinstance(f, dict) for f in findings):
        raise ValueError("findings must be a list of records")
    ids = [f.get("id") for f in findings]
    if not all(isinstance(i, str) and i for i in ids):
        raise ValueError("a finding has no id")
    if len(set(ids)) != len(ids):
        raise ValueError("finding ids repeat: %s" % ", ".join(sorted({i for i in ids if ids.count(i) > 1})))
    ranges = item_ranges(items) if items is not None else None
    pdfs = {}
    report = []
    count = dict.fromkeys((FOUND, NOT_ITEM_PAGE, OTHER_PAGE, NOT_FOUND), 0)
    highlighted = unchecked = 0
    for finding in findings:
        sources = finding.get("sources") or []
        if not isinstance(sources, list) or not all(isinstance(s, dict) for s in sources):
            raise ValueError("sources of %s must be a list of records" % finding["id"])
        results = []
        for index, source in enumerate(sources):
            doc = source.get("doc")
            if doc not in pdfs:
                path, error = find_pdf(data_dir, doc) if isinstance(doc, str) and doc else (None, "pdf_not_found")
                pdfs[doc] = (PdfText(path, use_pdftotext) if path else None, error)
            pdf, pdf_error = pdfs[doc]
            result, pages, boxes = check_source(source, pdf, pdf_error, ranges)
            if pages:
                name = "%s_%d.png" % (_UNSAFE.sub("_", finding["id"]), index)
                render(pdf.path, pages, boxes, os.path.join(out_dir, "pages", name))
                result["image"] = "pages/" + name
            results.append(dict({"index": index}, **result))
            count[result["status"]] += 1
            if result["found"]:
                highlighted += 1 if result["highlight_boxes"] else 0
                unchecked += 1 if ranges is None and source.get("item_no") else 0
        report.append({
            "id": finding["id"],
            "quotes_verified": bool(results) and all(r["found"] for r in results),
            "sources": results,
        })
    failed = [f["id"] for f in report if not f["quotes_verified"]]
    return {
        "check": "by code (pipeline.common.pagecheck); no human looked at the pages",
        "summary": {
            "findings": len(report),
            "sources": sum(count.values()),
            "found_on_stated_page": count[FOUND],
            "stated_page_not_of_item": count[NOT_ITEM_PAGE],
            "found_on_other_page": count[OTHER_PAGE],
            "not_found": count[NOT_FOUND],
            "item_page_not_checked": unchecked,
            "highlighted": highlighted,
            "findings_verified": len(report) - len(failed),
            "findings_failed": len(failed),
            "failed_ids": failed,
        },
        "findings": report,
    }


def apply_report(findings, report):
    """Copies of the findings with quotes_verified from the report. Nothing
    else is changed; the input is not changed."""
    verdict = {f["id"]: f["quotes_verified"] for f in report["findings"]}
    return [dict(finding, quotes_verified=verdict[finding["id"]]) for finding in findings]


def summary_line(report):
    s = report["summary"]
    return ("pagecheck: findings=%d sources=%d found_on_stated_page=%d stated_page_not_of_item=%d "
            "found_on_other_page=%d not_found=%d item_page_not_checked=%d highlighted=%d "
            "findings_verified=%d findings_failed=%d failed_ids=%s" % (
                s["findings"], s["sources"], s["found_on_stated_page"],
                s["stated_page_not_of_item"], s["found_on_other_page"], s["not_found"],
                s["item_page_not_checked"], s["highlighted"], s["findings_verified"],
                s["findings_failed"], ",".join(s["failed_ids"]) or "-"))


def _write_json(path, data):
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


USAGE = ("usage: python -m pipeline.common.pagecheck [--items <items.json>] "
         "<findings in> <data dir> <out dir> [<findings out>]\n")


def main(argv):
    argv = list(argv)
    items_path = None
    if "--items" in argv:
        at = argv.index("--items")
        if at + 1 >= len(argv):
            sys.stderr.write(USAGE)
            return 2
        items_path = argv[at + 1]
        del argv[at:at + 2]
    if len(argv) not in (3, 4):
        sys.stderr.write(USAGE)
        return 2
    findings_in, data_dir, out_dir = argv[:3]
    if not os.path.isdir(data_dir):
        sys.stderr.write("pagecheck: data dir not found: %s\n" % data_dir)
        return 2
    if items_path is None and os.path.isfile(os.path.join(out_dir, "items.json")):
        items_path = os.path.join(out_dir, "items.json")
    try:
        items = None
        if items_path is not None:
            with open(items_path, encoding="utf-8") as f:
                items = json.load(f)
            if not isinstance(items, list):
                raise ValueError("items must be a list of records: %s" % items_path)
        with open(findings_in, encoding="utf-8") as f:
            findings = json.load(f)
        report = check_findings(findings, data_dir, out_dir, items=items)
    except (OSError, ValueError) as error:
        sys.stderr.write("pagecheck: %s\n" % error)
        return 2
    if items is None:
        sys.stderr.write("pagecheck: no items.json (--items, or <out dir>/items.json): the stated "
                         "pages were not checked against the pages of the cited items\n")
    _write_json(os.path.join(out_dir, "pagecheck.json"), report)
    if len(argv) == 4:
        _write_json(argv[3], apply_report(findings, report))
    print(summary_line(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
