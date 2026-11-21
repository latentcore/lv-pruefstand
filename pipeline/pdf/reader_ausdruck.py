#!/usr/bin/env python3
"""Reader for the tender print layout "LV-Ausdruck" (LV-Ausdruck-[PROJEKT_004].pdf).

Layout: page 1 is a table of contents; then pages with the header lines
"Projekt: ... Seite n", "Bauherr:", "DV-Nr. AG:" and, on item pages, the column
header "Pos  Stl-Nr.  Menge / Einheit  Einheitspreis  Gesamtbetrag". A number at
column 0 starts an entry ("01" a section, "01.0001" an item); the item text
follows; the right-aligned line "<quantity> <unit> ..... ....." closes the item.
The last page is the summary of the sections.

Usage:
    reader_ausdruck.py PDF_OR_TEXT OUT_DIR [DOC]

PDF_OR_TEXT is the PDF (needs Poppler's pdftotext on PATH) or its
`pdftotext -layout` text with "=== PAGE n ===" lines. Output: items.json and
manifest.json (contract v1, format "pdf", stage "83").
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pdfio  # noqa: E402
import reader_79222 as base  # noqa: E402

MONEY = r"-?\d{1,3}(?:\.\d{3})*,\d{2}"
FIELD = r"(?:\.{5,}|" + MONEY + r")"
QTY_RE = re.compile(
    r"^\s{20,}(\d+(?:\.\d{3})*(?:,\d+)?)\s+(\S+)\s+(" + FIELD + r")\s+("
    + FIELD + r")\s*$")
OZ_RE = re.compile(r"^(\d+(?:\.\d+)*)\s{2,}(\S.*?)\s*$")
FOOTER_RE = re.compile(r"Seite \d+ von \d+\s*$")
PROJECT_RE = re.compile(r"^Projekt:\s+(\S.*?)\s{2,}Seite\s+\d+\s*$")
HEADER_RES = (
    PROJECT_RE,
    re.compile(r"^Bauherr:"),
    re.compile(r"^DV-Nr\. AG:"),
    re.compile(r"^Pos\s+Stl-Nr\.\s"),
    re.compile(r"^OZ\s+Abschnitt\s"),
    re.compile(r"^\s+in EUR(?:\s+in EUR)?\s*$"),
)
HEADER_SEARCH_LINES = 10
CARRY_RE = re.compile(r"^\s*Übertrag:\s*" + FIELD + r"?\s*$")
SUM_RES = (
    re.compile(r"^Gesamtsumme\s"),
    re.compile(r"^\s*MWSt\.\s"),
    re.compile(r"^\s*Gesamtsumme inkl\. MWSt\."),
)
TOC_TITLE_RE = re.compile(r"^\s*Inhaltsverzeichnis\s*$")
TOC_ROW_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(LV|Los|Titel|Abschnitt)\s+(\S.*?)"
                        r"(?:\s{2,}(\d+))?\s*$")
SUMMARY_TITLE_RE = re.compile(r"^Zusammenstellung der Abschnitte\s*$")
SUMMARY_ROW_RE = re.compile(r"^\d+(?:\.\d+)*\s{2,}\S.*?\s{2,}" + FIELD + r"\s*$")
# signature lines and their captions, e.g. "(Ort und Datum)"
SIGNATURE_RE = re.compile(r"^\s*(?:\.{20,}|\([^()]*\))\s*$")


class AusdruckParser(base.DocParser):
    STAGE = "83"

    def __init__(self, doc, text):
        super().__init__(doc, text)
        self.trade = ""       # the print names no trade
        self.toc = []         # (number, title, page) of the "Titel" rows

    def _record(self, *args, **kwargs):
        rec = super()._record(*args, **kwargs)
        rec["stage"] = self.STAGE
        return rec

    def _unread(self, page, what):
        self.unparsed += 1
        self.warn("unread line on page %d (%s)" % (page, what))

    def _parse_page(self, page_no, lines):
        footer_at = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if FOOTER_RE.search(lines[i]):
                footer_at = i
                break
        else:
            self.warn("no footer on page %d" % page_no)
        lines = lines[:footer_at]
        toc_at = next((i for i, l in enumerate(lines) if TOC_TITLE_RE.match(l)),
                      None)
        if toc_at is not None:
            self._parse_toc(page_no, lines[toc_at + 1:])
            return
        head_end = -1
        for i, l in enumerate(lines[:HEADER_SEARCH_LINES]):
            if any(r.match(l) for r in HEADER_RES):
                head_end = i
            m = PROJECT_RE.match(l)
            if m and self.project is None:
                self.project = m.group(1)
        if head_end < 0:
            self.warn("no page header on page %d" % page_no)
        body = lines[head_end + 1:]
        summary_page = any(SUMMARY_TITLE_RE.match(l) for l in body)
        for l in body:
            if summary_page:
                self._parse_summary_line(page_no, l)
            else:
                self._parse_line(page_no, l)

    def _parse_toc(self, page_no, lines):
        for l in lines:
            if not l.strip():
                continue
            m = TOC_ROW_RE.match(l)
            if not m:
                self._unread(page_no, "table of contents")
            elif m.group(2) != "LV" and m.group(4):
                self.toc.append((m.group(1), base.norm_space(m.group(3)),
                                 int(m.group(4))))

    def _close_all(self):
        if self.cur is not None:
            self.cur["closed"] = True
        self._close_orphan()

    def _parse_summary_line(self, page, line):
        if not line.strip() or CARRY_RE.match(line):
            return
        self._close_all()
        if (SUMMARY_TITLE_RE.match(line) or SUMMARY_ROW_RE.match(line)
                or SIGNATURE_RE.match(line)
                or any(r.match(line) for r in SUM_RES)):
            return
        self._unread(page, "summary page")

    def _parse_line(self, page, line):
        if not line.strip():
            self._add_text(page, None)
            return
        if CARRY_RE.match(line):
            return
        if any(r.match(line) for r in SUM_RES):
            self._close_all()
            return
        m = QTY_RE.match(line)
        if m:
            self._close_orphan()
            self._set_qty(m, page)
            return
        m = OZ_RE.match(line)
        if m:
            self._start_entry(m.group(1), m.group(2), page)
            return
        if re.search(r"\.{5,}\s*$", line):
            # a line with a price field that is not a quantity line
            self._unread(page, "price field without quantity")
            return
        self._add_text(page, line)

    def _finish(self, page_count):
        if self.project is None:
            self.project = ""     # the contract wants a string
            self.warn("no Projekt line found")
        records, page_count = super()._finish(page_count)
        headings = {r["item_no"]: r for r in records if r["kind"] == "heading"}
        for number, title, page in self.toc:
            h = headings.get(number)
            if h is None:
                self.warn("table of contents names section %s, no such heading "
                          "was read" % number)
            elif h["page"] != page or h["short_text"] != title:
                self.warn("section %s differs from the table of contents "
                          "(page or title)" % number)
        return records, page_count


def parse_text(doc, text):
    """Parse one document. Returns (records, page_count, warnings, unparsed)."""
    p = AusdruckParser(doc, text)
    records, pages = p.parse()
    return records, pages, p.warnings, p.unparsed


def run(source, out_dir=None, doc=None):
    return pdfio.run_reader(AusdruckParser, source, out_dir, doc)


if __name__ == "__main__":
    sys.exit(pdfio.main(AusdruckParser, __doc__, sys.argv[1:]))
