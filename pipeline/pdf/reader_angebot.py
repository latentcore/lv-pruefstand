#!/usr/bin/env python3
"""Reader for the offer print layout (Angebot AN24-0305.pdf, 27 pages).

Layout: every page has the column header "Pos-Nr.  Menge ME  EP / EUR  GP / EUR";
what stands above it is the page header. An item is one line "<number>
<quantity> <unit> <unit price> <total>" in the Pos-Nr. column; its text follows
on the next lines, indented. "Bereich n." and "Abschnitt n.m." start sections,
"Hinweistext" marks a note whose text the print does not show. "Übertrag:",
"Summe ..." and "Zusammenstellung ..." lines and the last page
("Gesamtzusammenstellung") are sums, not items.

The offer holds prices. They go to items.json (unit_price, total) only; no
warning and no message of this reader carries a price or a source line.

Usage:
    reader_angebot.py PDF_OR_TEXT OUT_DIR [DOC]

PDF_OR_TEXT is the PDF (needs Poppler's pdftotext on PATH) or its
`pdftotext -layout` text with "=== PAGE n ===" lines. Output: items.json and
manifest.json (contract v1, format "pdf", stage "84").
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pdfio  # noqa: E402
import reader_79222 as base  # noqa: E402

MONEY = r"-?\d{1,3}(?:\.\d{3})*,\d{2}"
QTY = r"\d{1,3}(?:\.\d{3})*,\d+"
OZ = r"\d+(?:\.\d+)+\.?"
COLUMNS_RE = re.compile(r"^(\s*)Pos-Nr\.\s+Menge\s+ME\s")
OFFER_NO_RE = re.compile(r"ngebot-Nr\.:\s+(\S+)")
ITEM_RE = re.compile(r"^\s*(" + OZ + r")\s+(" + QTY + r")\s+(\S+)\s+(" + MONEY
                     + r")\s+(" + MONEY + r")\s*$")
OZ_START_RE = re.compile(r"^\s*" + OZ + r"(?:\s|$)")
SECTION_RE = re.compile(r"^\s*(?:Bereich|Abschnitt|Unterabschnitt|Titel|Los)\s+"
                        r"(\d+(?:\.\d+)*\.?)\s{2,}(\S.*?)\s*$")
NOTE_RE = re.compile(r"^\s*Hinweistext(?:\s+\S.*)?\s*$")
CARRY_RE = re.compile(r"^\s*Übertrag:\s+" + MONEY + r"\s*$")
SUM_RES = (
    re.compile(r"^\s*Summe\s"),
    re.compile(r"^\s*Zusammenstellung\s"),
    re.compile(r"^\s*zzgl\. Mehrwertsteuer\s"),
    re.compile(r"^\s*Gesamtsumme:"),
)
GRAND_TOTAL_RE = re.compile(r"^\s*Gesamtzusammenstellung\s*$")
MONEY_ONLY_RE = re.compile(r"^\s*" + MONEY + r"\s*$")
CLOSING_RES = (
    re.compile(r"^\s*Mit freundlichen Grüßen\s*$"),
    re.compile(r"^\s*Datum:.*Unterschrift:"),
)
FOOTER_RE = re.compile(r"\bIBAN:")
# a text line belongs to an item when it starts this far right of the
# Pos-Nr. column
TEXT_INDENT = 3


class AngebotParser(base.DocParser):
    STAGE = "84"

    def __init__(self, doc, text):
        super().__init__(doc, text)
        self.trade = ""        # the print names no trade
        self.after_sum = False
        self.grand_total = False

    def _record(self, *args, **kwargs):
        rec = super()._record(*args, **kwargs)
        rec["stage"] = self.STAGE
        return rec

    def _unread(self, page, what):
        self.unparsed += 1
        self.warn("unread line on page %d (%s)" % (page, what))

    def _close_all(self):
        if self.cur is not None:
            self.cur["closed"] = True
        self._close_orphan()

    def _parse_page(self, page_no, lines):
        head_end = None
        column = 0
        for i, l in enumerate(lines):
            m = OFFER_NO_RE.search(l)
            if m and self.project is None:
                self.project = m.group(1)
            m = COLUMNS_RE.match(l)
            if m:
                head_end, column = i, len(m.group(1))
                break
        if head_end is None:
            self.warn("no column header on page %d, page not read" % page_no)
            self.unparsed += sum(1 for l in lines if l.strip())
            return
        end = len(lines)
        for i in range(head_end + 1, len(lines)):
            if FOOTER_RE.search(lines[i]):
                end = i
                break
        for l in lines[head_end + 1:end]:
            self._parse_line(page_no, l, column)

    def _parse_line(self, page, line, column=0):
        if not line.strip():
            self._add_text(page, None)
            return
        indent = len(line) - len(line.lstrip())
        in_column = indent < column + TEXT_INDENT
        was_after_sum, self.after_sum = self.after_sum, False
        if CARRY_RE.match(line):
            return
        if GRAND_TOTAL_RE.match(line) and in_column:
            self._close_all()
            self.grand_total = True
            return
        if any(r.match(line) for r in SUM_RES) and in_column:
            self._close_all()
            self.after_sum = True
            return
        if MONEY_ONLY_RE.match(line) and was_after_sum:
            return                      # the amount of a wrapped sum line
        if self.grand_total:
            if not any(r.match(line) for r in CLOSING_RES):
                self._unread(page, "after the last sum")
            return
        if in_column:
            m = ITEM_RE.match(line)
            if m:
                self._start_entry(m.group(1), "", page)
                self.cur["qty"] = {
                    "quantity": base.parse_german_number(m.group(2)),
                    "unit": m.group(3),
                    "unit_price": base.parse_german_number(m.group(4)),
                    "total": base.parse_german_number(m.group(5)),
                    "unit_price_only": False,
                }
                return
            if OZ_START_RE.match(line):
                self._close_all()
                self._unread(page, "line with an item number")
                return
            m = SECTION_RE.match(line)
            if m:
                self._start_entry(m.group(1), m.group(2), page)
                self.cur["closed"] = True
                return
            if NOTE_RE.match(line):
                self._close_all()
                self._add_text(page, line)
                self._close_orphan()
                return
            self._close_all()
            self._unread(page, "text in the Pos-Nr. column")
            return
        self._add_text(page, line)

    def _finish(self, page_count):
        # The item line comes first in this layout; the first text line under
        # it is the short text.
        for e in self.entries:
            if e["type"] == "numbered" and e["qty"] and not e["title"]:
                for i, (_, t) in enumerate(e["body"]):
                    if t is not None:
                        e["title"] = t
                        del e["body"][:i + 1]
                        break
        if self.project is None:
            self.project = ""
            self.warn("no offer number found")
        return super()._finish(page_count)


def parse_text(doc, text):
    """Parse one document. Returns (records, page_count, warnings, unparsed)."""
    p = AngebotParser(doc, text)
    records, pages = p.parse()
    return records, pages, p.warnings, p.unparsed


def run(source, out_dir=None, doc=None):
    return pdfio.run_reader(AngebotParser, source, out_dir, doc)


if __name__ == "__main__":
    sys.exit(pdfio.main(AngebotParser, __doc__, sys.argv[1:]))
