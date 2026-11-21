#!/usr/bin/env python3
"""Reader for the 79-222 trade bills of quantities (LV printouts, "Anfrage").

Input: one text file per list, made with `pdftotext -layout`, where a line
"=== PAGE n ===" starts page n. Output: items.json and manifest.json.

Usage:
    reader_79222.py TEXT_DIR OUT_DIR [PDF_DIR]
    reader_79222.py --extract PDF_DIR TEXT_DIR
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

PAGE_RE = re.compile(r"^=== PAGE (\d+) ===\s*$")
DOC_RE = re.compile(r"^(LV_\d+[a-z]?)(?:_|\.)")

# An OZ sits at column 0: "11.4.60.", "1.4.1.8", "1.2..1", ".6". It is followed
# by at least two spaces and the short text, or stands alone on the line.
OZ_RE = re.compile(r"^(\d+(?:\.\d*)*\.?|\.\d+(?:\.\d+)*\.?)(?:\s{2,}(\S.*))?\s*$")

NUM = r"\d{1,3}(?:\.\d{3})*,\d+"
PRICE_COL = r"(?:\.{10,}|" + NUM + r")"
QTY_RE = re.compile(
    r"^\s{20,}(" + NUM + r")(?:\s+(\S+))?\s+(" + PRICE_COL + r")\s+("
    + PRICE_COL + r"|Nur Einh\.-Pr\.)\s*$"
)

HEADER_END_RES = (
    re.compile(r"^\s+in EUR\s+in EUR\s*$"),
    re.compile(r"^Ordnungszahl\s"),
)
LV_LINE_RE = re.compile(r"^LV:\s")
PROJECT_RE = re.compile(r"^Projekt:\s+(\S+)\s+(\S.*?)\s*$")
FOOTER_RE = re.compile(r"^Druckdatum:")
CARRY_RE = re.compile(r"^\s*Übertrag:\s*$")
SUMMARY_RES = (
    re.compile(r"^\s*Summe\s"),
    re.compile(r"^\s*Zuzüglich der gesetzlichen Mehrwertsteuer"),
    re.compile(r"^\s*in Höhe von [\d,]+ %"),
    re.compile(r"^\s*\.{10,} EUR\s*$"),
    re.compile(r"^\s*\(Ort\)\s+\(Datum\)"),
    re.compile(r"^Das LV besteht aus den Seiten"),
)
PRE_RE = re.compile(r"^(\s*)(?:-\s+)?(?:Untergrund/)?Vorleistung(?:\s*\([^)]*\))?(?:\s*:\s*|\s{2,})(.*)$")
POST_RE = re.compile(r"^(\s*)(?:-\s+)?Folgeleistung(?:\s*\([^)]*\))?(?:\s*:\s*|\s{2,})(.*)$")
KEY_RE = re.compile(r"^\s*[^\s:][^:]{0,40}:(\s|$)")
NOTE_TITLE_RE = re.compile(r"Vorbemerk|Hinweis|Anmerkung|ZTV", re.I)
LUMP_UNITS = {"psch", "pau", "pausch", "pauschal"}

KEYS = ["doc", "project", "trade", "format", "stage", "item_no", "kind",
        "section", "short_text", "long_text", "quantity", "unit",
        "unit_price", "total", "page", "line", "pre_trade_text",
        "post_trade_text"]


def parse_german_number(text):
    """'1.234,500' -> 1234.5"""
    return float(text.replace(".", "").replace(",", "."))


def norm_space(text):
    return re.sub(r"\s+", " ", text).strip()


def norm_item_no(raw):
    return raw.rstrip(".")


def section_of(item_no):
    parts = item_no.split(".")
    if len(parts) <= 1:
        return ""
    return ".".join(parts[:-1]).rstrip(".")


def split_pages(text):
    """Return list of (page_no, [lines]). A last marker with no content is a
    pdftotext artifact (trailing form feed) and is not a page."""
    pages = []
    current = None
    for line in text.split("\n"):
        m = PAGE_RE.match(line)
        if m:
            current = (int(m.group(1)), [])
            pages.append(current)
        elif current is not None:
            current[1].append(line)
        elif line.strip():
            pages.append((0, [line]))
            current = pages[-1]
    while pages and not any(l.strip() for l in pages[-1][1]):
        pages.pop()
    return pages


def parse_trade(lv_line, project_line):
    rest = lv_line[3:]
    lead = len(rest) - len(rest.lstrip())
    body = rest.strip()
    parts = re.split(r"\s{2,}", body)
    if len(parts) >= 2:
        return " ".join(parts[1:]).strip()
    m = PROJECT_RE.match(project_line or "")
    if m:
        col = m.start(2)
        starts = [wm.start() for wm in re.finditer(r"\S+", lv_line)
                  if wm.start() > 3 + lead]
        if starts:
            best = min(starts, key=lambda x: (abs(x - col), -x))
            return lv_line[best:].strip()
    return body


class DocParser:
    def __init__(self, doc, text):
        self.doc = doc
        self.text = text
        self.warnings = []
        self.unparsed = 0
        self.project = None
        self.trade = None
        self.entries = []
        self.cur = None
        self.orphan = None

    def warn(self, msg):
        self.warnings.append(msg)

    # entries are dicts with: no, title, body [(page, text|None)], page, qty...
    def _close_orphan(self):
        o = self.orphan
        self.orphan = None
        if o and any(t for _, t in o["body"]):
            self.entries.append(o)

    def _start_entry(self, raw_no, title, page):
        self._close_orphan()
        self.cur = {"type": "numbered", "raw_no": raw_no,
                    "no": norm_item_no(raw_no), "title": title or "",
                    "body": [], "page": page, "qty": None, "closed": False}
        self.entries.append(self.cur)

    def _add_text(self, page, text):
        if self.cur is not None and not self.cur["closed"]:
            self.cur["body"].append((page, text))
            return
        if self.orphan is None:
            if text is None:
                return
            owner = ""
            for e in reversed(self.entries):
                if e["type"] == "numbered":
                    owner = e["no"] if e["qty"] is None else section_of(e["no"])
                    break
            self.orphan = {"type": "orphan", "no": owner, "title": "",
                           "body": [], "page": page, "qty": None}
        self.orphan["body"].append((page, text))

    def _set_qty(self, m, page):
        if self.cur is None or self.cur["closed"]:
            self.warn("quantity line without item on page %d" % page)
            self.unparsed += 1
            return
        self.cur["qty"] = {
            "quantity": parse_german_number(m.group(1)),
            "unit": m.group(2),
            "unit_price": None if m.group(3).startswith(".") else parse_german_number(m.group(3)),
            "total": None if m.group(4).startswith((".", "Nur")) else parse_german_number(m.group(4)),
            "unit_price_only": m.group(4).startswith("Nur"),
        }
        self.cur["closed"] = True

    def parse(self):
        pages = split_pages(self.text)
        expected = 1
        for page_no, _ in pages:
            if page_no != expected:
                self.warn("page marker %d where %d expected" % (page_no, expected))
            expected = page_no + 1
        for page_no, lines in pages:
            self._parse_page(page_no, lines)
        self._close_orphan()
        return self._finish(len(pages))

    def _parse_page(self, page_no, lines):
        footer_at = len(lines)
        for i, l in enumerate(lines):
            if FOOTER_RE.match(l):
                footer_at = i
                break
        else:
            self.warn("no footer on page %d" % page_no)
        head_end = None
        lv_at = None
        project_line = None
        summary_page = False
        for i, l in enumerate(lines[:min(footer_at, 25)]):
            if PROJECT_RE.match(l):
                project_line = l
            if LV_LINE_RE.match(l):
                lv_at = i
            if l.strip() == "Zusammenstellung":
                summary_page = True
            if any(r.match(l) for r in HEADER_END_RES):
                head_end = i
                break
        if head_end is None:
            head_end = lv_at
        if head_end is None:
            self.warn("no page header on page %d" % page_no)
            head_end = -1
        if project_line and self.project is None:
            self.project = PROJECT_RE.match(project_line).group(1)
        if lv_at is not None and self.trade is None:
            self.trade = parse_trade(lines[lv_at], project_line)
        for l in lines[head_end + 1:footer_at]:
            self._parse_line(page_no, l, summary_page)

    def _parse_line(self, page, line, summary_page):
        if not line.strip():
            self._add_text(page, None)
            return
        if CARRY_RE.match(line):
            return
        if any(r.match(line) for r in SUMMARY_RES):
            if self.cur is not None:
                self.cur["closed"] = True
            self._close_orphan()
            return
        if summary_page:
            self.unparsed += 1
            self.warn("unread line on summary page %d" % page)
            return
        m = QTY_RE.match(line)
        if m:
            self._close_orphan()
            self._set_qty(m, page)
            return
        m = OZ_RE.match(line)
        if m and re.search(r"\d", m.group(1)):
            self._start_entry(m.group(1), m.group(2), page)
            return
        self._add_text(page, line)

    # -- building output ------------------------------------------------

    @staticmethod
    def _lines(body):
        """Drop blank runs at page breaks and at the ends; collapse others."""
        out = []
        n = len(body)
        i = 0
        while i < n:
            p, t = body[i]
            if t is not None:
                out.append((p, t))
                i += 1
                continue
            j = i
            while j < n and body[j][1] is None:
                j += 1
            if out and j < n:
                prev_page = out[-1][0]
                next_page = body[j][0]
                if prev_page == next_page:
                    out.append((p, None))
            i = j
        return out

    @staticmethod
    def _trade_values(lines):
        pre = post = None
        for idx, (_, t) in enumerate(lines):
            if t is None:
                continue
            for rx, which in ((PRE_RE, "pre"), (POST_RE, "post")):
                m = rx.match(t)
                if not m:
                    continue
                value_col = m.start(2) if m.group(2) else len(t)
                parts = [m.group(2).strip()] if m.group(2).strip() else []
                for _, t2 in lines[idx + 1:]:
                    if t2 is None or PRE_RE.match(t2) or POST_RE.match(t2):
                        break
                    indent = len(t2) - len(t2.lstrip())
                    if indent < value_col - 2:
                        break
                    if KEY_RE.match(t2) and indent < value_col:
                        break
                    parts.append(t2.strip())
                val = norm_space(" ".join(parts)) or None
                if which == "pre" and pre is None:
                    pre = val
                elif which == "post" and post is None:
                    post = val
        return pre, post

    @staticmethod
    def _text(lines):
        out = []
        for _, t in lines:
            if t is None:
                if out and out[-1] != "":
                    out.append("")
            else:
                out.append(norm_space(t))
        while out and out[-1] == "":
            out.pop()
        return "\n".join(out)

    def _record(self, item_no, kind, short, lines, page, qty=None, extra=None):
        pre, post = self._trade_values(lines)
        rec = {
            "doc": self.doc, "project": self.project, "trade": self.trade,
            "format": "pdf", "stage": "anfrage", "item_no": item_no,
            "kind": kind, "section": section_of(item_no),
            "short_text": short, "long_text": self._text(lines),
            "quantity": qty["quantity"] if qty else None,
            "unit": qty["unit"] if qty else None,
            "unit_price": qty["unit_price"] if qty else None,
            "total": qty["total"] if qty else None,
            "page": page, "line": None,
            "pre_trade_text": pre, "post_trade_text": post,
        }
        if extra:
            rec["price_mode"] = extra
        return rec

    def _finish(self, page_count):
        numbered = [e["no"] for e in self.entries if e["type"] == "numbered"]
        parents = set()
        for no in numbered:
            parts = no.split(".")
            for k in range(1, len(parts)):
                parents.add(".".join(parts[:k]).rstrip("."))
        priced_depths = set(len(e["no"].split(".")) for e in self.entries
                            if e["type"] == "numbered" and e["qty"])
        seen = {}
        records = []
        for e in self.entries:
            lines = self._lines(e["body"])
            if e["type"] == "orphan":
                if not lines:
                    continue
                records.append(self._record(
                    e["no"], "preliminary_note", norm_space(lines[0][1]),
                    lines[1:], e["page"]))
                continue
            no = e["no"]
            if e["qty"] is None and no in parents:
                records.append(self._record(no, "heading", norm_space(e["title"]),
                                            [], e["page"]))
                if lines:
                    records.append(self._record(
                        no, "preliminary_note", norm_space(lines[0][1]),
                        lines[1:], lines[0][0]))
                continue
            if e["qty"] is None:
                if not lines:
                    records.append(self._record(no, "heading", norm_space(e["title"]),
                                                [], e["page"]))
                    continue
                if (len(no.split(".")) in priced_depths
                        and not NOTE_TITLE_RE.search(e["title"])):
                    self.warn("numbered entry %s on page %d has text but no "
                              "quantity line, kept as preliminary_note" % (no, e["page"]))
                records.append(self._record(no, "preliminary_note",
                                            norm_space(e["title"]), lines, e["page"]))
                continue
            if no in seen:
                self.warn("duplicate item number %s on pages %d and %d"
                          % (no, seen[no], e["page"]))
            seen[no] = e["page"]
            title = norm_space(e["title"])
            kind = "normal"
            mode = None
            while title.startswith("***"):
                marker = title
                if "Bedarfsposition" in marker:
                    kind = "optional"
                    if "mit GB" in marker:
                        mode = "in_total"
                elif "Wahlposition" in marker or "Alternativposition" in marker:
                    kind = "alternative"
                elif "Grundposition" in marker:
                    pass
                else:
                    self.warn("unknown marker '%s' at item %s" % (marker, no))
                if lines and lines[0][1] is not None:
                    title = norm_space(lines[0][1])
                    lines = lines[1:]
                else:
                    title = ""
                    self.warn("item %s has a marker but no short text" % no)
            if not title:
                self.warn("item %s on page %d has no short text" % (no, e["page"]))
            unit = (e["qty"]["unit"] or "")
            if kind == "normal" and unit.lower() in LUMP_UNITS:
                kind = "lump_sum"
            if e["qty"]["unit_price_only"]:
                mode = "unit_price_only"
            if e["qty"]["unit"] is None:
                self.warn("item %s on page %d has a quantity without unit"
                          % (no, e["page"]))
            records.append(self._record(no, kind, title, lines, e["page"],
                                        e["qty"], mode))
        if self.project is None:
            self.warn("no Projekt line found")
        if self.trade is None:
            self.warn("no LV line found")
        return records, page_count


def parse_text(doc, text):
    """Parse one list. Returns (records, page_count, warnings, unparsed)."""
    p = DocParser(doc, text)
    records, pages = p.parse()
    return records, pages, p.warnings, p.unparsed


def doc_id(filename):
    m = DOC_RE.match(os.path.basename(filename))
    return m.group(1) if m else None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_pdf(pdf_dir, doc):
    for name in sorted(os.listdir(pdf_dir)):
        if name.lower().endswith(".pdf") and doc_id(name) == doc:
            return os.path.join(pdf_dir, name)
    return None


def run(text_dir, out_dir, pdf_dir=None):
    names = sorted(n for n in os.listdir(text_dir)
                   if n.endswith(".txt") and doc_id(n))
    all_items = []
    manifest = []
    project = None
    for name in names:
        doc = doc_id(name)
        with open(os.path.join(text_dir, name), encoding="utf-8") as f:
            text = f.read()
        records, pages, warnings, unparsed = parse_text(doc, text)
        file_name, digest = name, None
        if pdf_dir:
            pdf = find_pdf(pdf_dir, doc)
            if pdf:
                file_name, digest = os.path.basename(pdf), sha256_file(pdf)
            else:
                warnings.append("no source PDF found for %s" % doc)
        if records and project is None:
            project = records[0]["project"]
        manifest.append({
            "doc": doc, "file": file_name, "sha256": digest,
            "format": "pdf", "stage": "anfrage", "pages": pages,
            "items": sum(1 for r in records if r["quantity"] is not None),
            "headings": sum(1 for r in records if r["kind"] == "heading"),
            "preliminary_notes": sum(1 for r in records
                                     if r["kind"] == "preliminary_note"),
            "unparsed_lines": unparsed, "warnings": warnings,
        })
        all_items.extend(records)
    os.makedirs(out_dir, exist_ok=True)
    for fname, data in (("items.json", all_items), ("manifest.json", manifest)):
        with open(os.path.join(out_dir, fname), "w", encoding="utf-8",
                  newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.write("\n")
    return all_items, manifest


def extract_pdfs(pdf_dir, text_dir):
    """Run `pdftotext -layout` on each LV_*.pdf and add page markers."""
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("pdftotext not found on PATH")
    os.makedirs(text_dir, exist_ok=True)
    done = []
    for name in sorted(os.listdir(pdf_dir)):
        doc = doc_id(name)
        if not doc or not name.lower().endswith(".pdf"):
            continue
        res = subprocess.run([exe, "-layout", "-enc", "UTF-8",
                              os.path.join(pdf_dir, name), "-"],
                             capture_output=True, check=True)
        chunks = res.stdout.decode("utf-8").split("\f")
        out = []
        for i, chunk in enumerate(chunks, 1):
            out.append("=== PAGE %d ===" % i)
            out.append(chunk.rstrip("\n"))
        path = os.path.join(text_dir, doc + ".txt")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(out) + "\n")
        done.append(path)
    return done


def main(argv):
    if len(argv) == 3 and argv[0] == "--extract":
        for p in extract_pdfs(argv[1], argv[2]):
            print(p)
        return 0
    if len(argv) not in (2, 3):
        sys.stderr.write(__doc__)
        return 2
    items, manifest = run(*argv)
    print("docs=%d entries=%d priced=%d pages=%d warnings=%d unparsed=%d" % (
        len(manifest), len(items), sum(m["items"] for m in manifest),
        sum(m["pages"] for m in manifest),
        sum(len(m["warnings"]) for m in manifest),
        sum(m["unparsed_lines"] for m in manifest)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
