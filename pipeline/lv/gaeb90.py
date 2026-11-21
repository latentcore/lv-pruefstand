"""GAEB 90 reader for .D83, .D84 and .D86 files (W11).

Usage:
    python -m pipeline.lv.gaeb90 [FILE or FOLDER] [OUT] [--project NAME]

Reads one GAEB 90 file, or every .D83/.D84/.D86 file of a folder (default:
data), and writes OUT/<project>/items.json and manifest.json (default OUT:
out) in the contract v1 shape. It prints counts only, never a price.

The record layout below was read from the organizer files, not from the
official format text (MASTER_PLAN part C1). Every line has 80 characters: the
record type in columns 1-2, the payload in 3-74, the line number in 75-80.
The code page is cp850; one of the five files is cp1252, so the reader looks
at the German letters and picks the code page per file (`encoding` in the
manifest).

    T0 T1 T9  text before the header: start, text line, end -> preliminary_note
    00        header: stage in 11-12, project number in 29-62, number mask in 63-71
    01        list name in 3-42 -> trade
    02 .. 09  other header records, not needed
    11 12     section start (number in 3-11) and its name (3-42) -> heading
    20        start of a note; its text follows in 26 -> preliminary_note
    21        item: number 3-11, flags 12-14, repeat mark 21, quantity 24-34
              (3 decimals), unit 35-38
    23        prices: number 3-11, unit price 12-23, total 24-36 (2 decimals),
              quantity again 37-48 (3 decimals; not in every file)
    24        start of a sub-description inside the item; its 25 and 26 follow
              and go to the long text of the item
    25 26     short text (3-74) and long text (6-74). Columns 3-5 of a 26 line
              are empty or mark a text supplement (two digits and A or B)
    28 42     seen only empty (28 after items with the repeat mark, 42 after 41);
              an empty one is skipped, one with content is unreadable
    30        seen after 23 in one file; it looks like the unit price split
              into parts (not verified), not needed
    31 32     section end and section sum, not needed
    41        start of a general description; its 25 and 26 follow -> preliminary_note
    99        end: sum of the totals in 3-14 (2 decimals, zero when the file
              gives none), number of items in 70-74

The unit price field is the decimal trap of the format: the digits start in
column 13 and the last three columns (21-23) are the decimals. A file that
writes 10 digits leaves column 23 empty and so has 2 decimals; a file that
writes 11 digits has 3. model.price_check() proves the reading by
quantity x unit price = total; where the end record carries a sum, the
reader also compares it with the sum of the totals (`sum_check`).
One of the five files has price records without item records and without
the quantity: its items have quantity null and the manifest counts them
under price_check.no_quantity (the quantity stands in the twin file of the
other stage).

Item flags (columns 12-14): the files hold "NNN" and once "NNL". From the
format as generally described, not seen in these files: "W" in column 12 is
an alternative item, "E" in column 13 an optional one. Any other flag is
named in a warning and the item is kept as normal or lump_sum.

A line the reader cannot read (unknown record type, more than 80 characters,
a broken number field, a text line without an owner, a line after the end
record) is counted in `unparsed_lines` of the manifest. Record types that are
skipped on purpose are counted per type in `skipped_records`.
"""
import argparse
import hashlib
import os
import re
import sys
from decimal import Decimal

from pipeline.lv import model

FORMAT = "gaeb90"
STAGE_BY_EXTENSION = {".d83": "83", ".d84": "84", ".d86": "86"}
LINE_LENGTH = 80
PAYLOAD_END = 74
DEFAULT_MASK = "1122PPPPI"
QUANTITY_DECIMALS = 3
UNIT_PRICE_DECIMALS = 3
TOTAL_DECIMALS = 2
HEADER_SKIPPED = ("02", "03", "04", "05", "06", "07", "08", "09")
SKIPPED = HEADER_SKIPPED + ("30", "31", "32", "T9")
EMPTY_ONLY = ("28", "42")
# Records that continue the entry before them; all others start something new.
CONTINUING = ("12", "24", "25", "26", "T1") + EMPTY_ONLY
MARKER_LINE = "@@"
UNPARSED_SHOWN = 50

_CP850_LETTERS = frozenset(b"\x81\x84\x94\x8e\x99\x9a\xe1")
_CP1252_LETTERS = frozenset(b"\xe4\xf6\xfc\xc4\xd6\xdc\xdf")
# The raised 2 and 3 of cp1252; in cp850 these bytes are box drawing characters.
_CP1252_RAISED = frozenset(b"\xb2\xb3")


class Gaeb90Error(ValueError):
    """The file cannot be read as GAEB 90 at all."""


def is_gaeb90_name(file_name):
    return os.path.splitext(file_name)[1].lower() in STAGE_BY_EXTENSION


def stage_of(file_name):
    extension = os.path.splitext(file_name)[1].lower()
    if extension not in STAGE_BY_EXTENSION:
        raise Gaeb90Error("%s: the file type is not .D83, .D84 or .D86" % os.path.basename(file_name))
    return STAGE_BY_EXTENSION[extension]


def detect_encoding(raw):
    """cp850 (the usual GAEB 90 code page) unless the German letters of the
    file only make sense as cp1252. A file without any German letter is
    cp1252 when it holds the raised 2 or 3 of that code page."""
    dos = sum(1 for byte in raw if byte in _CP850_LETTERS)
    windows = sum(1 for byte in raw if byte in _CP1252_LETTERS)
    if not dos and not windows:
        return "cp1252" if any(byte in _CP1252_RAISED for byte in raw) else "cp850"
    return "cp1252" if windows > dos else "cp850"


def split_mask(mask):
    """Number mask "1122PPPPI" -> list of (kind, start, end); kind is "level",
    "position" or "index"."""
    parts = []
    for match in re.finditer(r"(.)\1*", mask):
        char = match.group(1)
        if char == " ":
            continue
        kind = "position" if char == "P" else "index" if char == "I" else "level"
        parts.append((kind, match.start(), match.end()))
    return parts


def fixed_number(field, decimals, left_aligned=False):
    """Read a fixed-point field: digits without a decimal point, an optional
    minus sign in front. Returns a Decimal, None for an empty field, or raises
    ValueError. A left-aligned field (the unit price) counts its decimals from
    the field end, so columns left empty at the end are zeros."""
    if not field.strip(" "):
        return None
    text = field.lstrip(" ")
    if left_aligned:
        text = text.rstrip(" ").ljust(len(text), "0")
    else:
        text = text.rstrip(" ")
    sign = -1 if text.startswith("-") else 1
    digits = text[1:] if text[:1] in "+-" else text
    if not digits.isdigit() or not digits.isascii():
        raise ValueError("not a number field")
    return sign * Decimal(int(digits)).scaleb(-decimals)


class _Reader(object):
    def __init__(self, file_name, project=None):
        self.file_name = os.path.basename(file_name)
        self.doc = model.doc_id(self.file_name)
        self.stage = stage_of(self.file_name)
        self.project_override = project
        self.header_project = ""
        self.header_stage = None
        self.trade = ""
        self.mask = None
        self.entries = []
        self.warnings = []
        self.unparsed = []
        self.skipped = {}
        self.declared_items = None
        self.owner = None
        self.last_item = None
        self.target = None
        self.open_section = ""
        self.last_heading = None
        self.price_only = 0
        self.unknown_flags = []
        self.seen_end = False
        self.group_numbers = set()
        self.supplements = 0
        self.declared_sum = None

    # -- small helpers ---------------------------------------------------
    def warn(self, message):
        self.warnings.append(message)

    def bad(self, line_no):
        self.unparsed.append(line_no)

    def skip(self, key):
        self.skipped[key] = self.skipped.get(key, 0) + 1

    def parts(self, number):
        return split_mask(self.mask or DEFAULT_MASK), number.ljust(9)

    def group_no(self, number):
        mask, number = self.parts(number)
        levels = [number[a:b].strip() for kind, a, b in mask if kind == "level"]
        return ".".join(part for part in levels if part)

    def item_no(self, number):
        """(item number, section). The number is split by the mask; a number
        whose section the file never names is kept as written."""
        mask, number = self.parts(number)
        section = self.group_no(number)
        if self.group_numbers and section not in self.group_numbers:
            return number.replace(" ", ""), None
        rest = [number[a:b].strip() for kind, a, b in mask if kind != "level"]
        return ".".join(part for part in [section] + rest if part), section

    def close_section(self, number):
        closed = self.group_no(number)
        if closed and (self.open_section == closed or self.open_section.startswith(closed + ".")):
            self.open_section = model.section_of(closed)

    def new_entry(self, kind, line_no, item_no, section):
        entry = {"kind": kind, "line": line_no, "item_no": item_no, "section": section,
                 "short": [], "long": [], "quantity": None, "unit": None,
                 "unit_price": None, "total": None, "flags": "", "number": None}
        self.entries.append(entry)
        self.owner = entry
        self.target = "long"
        return entry

    def new_note(self, line_no, titled=False):
        entry = self.new_entry("preliminary_note", line_no, self.open_section,
                               model.section_of(self.open_section))
        entry["titled"] = titled
        return entry

    # -- records ---------------------------------------------------------
    def read(self, raw):
        self.encoding = detect_encoding(raw)
        text = raw.decode(self.encoding, errors="replace")
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.line_count = sum(1 for line in lines if line.strip())
        damaged = [line_no for line_no, line in enumerate(lines, 1) if "\ufffd" in line]
        if damaged:
            self.warn("%d lines hold a byte that is not in code page %s; it is read as U+FFFD (first line %d)"
                      % (len(damaged), self.encoding, damaged[0]))
        self._collect_groups(lines)
        for line_no, line in enumerate(lines, 1):
            if not line.strip():
                continue
            if len(line) > LINE_LENGTH or len(line) < 2:
                self.bad(line_no)
                if line[:2] == "23":
                    self.owner = self.priced_item(line[2:11])
                elif line[:2] not in CONTINUING:
                    self.owner = None
                continue
            self.record(line_no, line.ljust(LINE_LENGTH))
        if self.mask is None:
            self.warn("no number mask in a header record (00): mask %s assumed" % DEFAULT_MASK)
        if not self.seen_end:
            self.warn("no end record (99): the file may be cut off")
        return self

    def _collect_groups(self, lines):
        for line in lines:
            if line[:2] == "00" and len(line) >= 71:
                self.mask = line[62:71].strip() or None
                break
        for line in lines:
            if len(line) > LINE_LENGTH:
                continue
            if line[:2] == "99":
                break
            if line[:2] in ("11", "31", "32"):
                number = self.group_no(line[2:11])
                if number:
                    self.group_numbers.add(number)

    def record(self, line_no, line):
        kind, payload = line[:2], line[2:PAYLOAD_END]
        if self.seen_end:
            self.bad(line_no)
        elif kind == "00":
            self.header_stage = line[10:12].strip() or None
            self.header_project = line[28:62].strip()
        elif kind == "01":
            self.trade = line[2:42].strip()
        elif kind == "T0":
            self.new_note(line_no)
            self.owner["item_no"], self.owner["section"] = "", ""
        elif kind == "T1":
            self.text_line(line_no, payload, pre_text=True)
        elif kind == "11":
            number = self.group_no(line[2:11])
            self.open_section = number
            self.last_heading = self.new_entry("heading", line_no, number, model.section_of(number))
            self.owner = None
        elif kind == "12":
            if self.last_heading is None or self.last_heading["short"]:
                self.bad(line_no)
            else:
                self.last_heading["short"].append(line[2:42].strip())
        elif kind == "20":
            self.new_note(line_no)
        elif kind == "41":
            self.new_note(line_no, titled=True)
            self.target = "short"
        elif kind == "21":
            self.item(line_no, line)
        elif kind == "23":
            self.prices(line_no, line)
        elif kind == "24":
            if self.owner is None or self.owner["kind"] != "item":
                self.bad(line_no)
            else:
                self.owner["long"].append("")
                self.target = "sub"
                self.owner["subs"] = self.owner.get("subs", 0) + 1
        elif kind == "25":
            self.short_line(line_no, payload)
        elif kind == "26":
            self.text_line(line_no, payload)
        elif kind in EMPTY_ONLY:
            if payload.strip():
                self.bad(line_no)
            else:
                self.skip(kind)
        elif kind in SKIPPED:
            if kind in ("31", "32"):
                self.close_section(line[2:11])
                self.owner = None
            elif kind == "T9":
                self.owner = None
            self.skip(kind)
        elif kind == "99":
            self.seen_end = True
            self.owner = None
            count = line[69:74]
            self.declared_items = int(count) if count.isdigit() else None
            try:
                self.declared_sum = fixed_number(line[2:14], TOTAL_DECIMALS)
            except ValueError:
                self.bad(line_no)
        else:
            self.bad(line_no)
            self.owner = None

    def item(self, line_no, line):
        number = line[2:11]
        item_no, section = self.item_no(number)
        if section is None:
            section = self.open_section
            self.warn("item %s (line %d): its number names no section of the file; kept as written"
                      % (item_no, line_no))
        entry = self.last_item = self.new_entry("item", line_no, item_no, section)
        entry["number"] = number
        entry["flags"] = line[11:14]
        entry["repeat"] = line[20] != " "
        entry["unit"] = line[34:38].strip() or None
        if entry["unit"] and any("\u2500" <= char <= "\u259f" for char in entry["unit"]):
            self.warn("item %s (line %d): the unit holds a box drawing character; "
                      "the code page %s may be wrong" % (item_no, line_no, self.encoding))
        try:
            entry["quantity"] = fixed_number(line[23:34], QUANTITY_DECIMALS)
        except ValueError:
            self.bad(line_no)
            self.warn("item %s (line %d): quantity field not readable" % (item_no, line_no))
        self.open_section = section

    def priced_item(self, number):
        """The item a price record with this number belongs to, or None."""
        entry = self.last_item
        if entry is None or entry["number"] != number or entry.get("has_prices"):
            return None
        return entry

    def prices(self, line_no, line):
        number = line[2:11]
        entry = self.priced_item(number)
        if entry is not None and self.owner is not entry:
            self.owner, self.target = entry, "long"
        if entry is None:
            item_no, section = self.item_no(number)
            if section is None:
                section = self.open_section
                self.warn("item %s (line %d): its number names no section of the file; kept as written"
                          % (item_no, line_no))
            entry = self.last_item = self.new_entry("item", line_no, item_no, section)
            entry["number"] = number
            entry["flags"] = "NNN"
            self.price_only += 1
            self.open_section = section
        entry["has_prices"] = True
        try:
            unit_price = fixed_number(line[11:23], UNIT_PRICE_DECIMALS, left_aligned=True)
            total = fixed_number(line[23:36], TOTAL_DECIMALS)
            quantity = fixed_number(line[36:48], QUANTITY_DECIMALS)
        except ValueError:
            self.bad(line_no)
            self.warn("item %s (line %d): price record not readable" % (entry["item_no"], line_no))
            return
        entry["unit_price"], entry["total"] = unit_price, total
        if entry["quantity"] is None:
            entry["quantity"] = quantity
        elif quantity is not None and quantity != entry["quantity"]:
            self.warn("item %s (line %d): the quantity in the price record differs from the item record"
                      % (entry["item_no"], line_no))

    def short_line(self, line_no, payload):
        entry = self.owner
        text = payload.strip()
        if entry is None:
            self.bad(line_no)
        elif entry["kind"] == "item" and self.target == "sub":
            entry["long"].append(text)
        elif entry["kind"] == "item" or entry.get("titled"):
            if entry["long"]:
                entry["long"].append(text)
            else:
                entry["short"].append(text)
        else:
            self.bad(line_no)

    def text_line(self, line_no, payload, pre_text=False):
        entry = self.owner
        if entry is None:
            self.bad(line_no)
            return
        text = payload.rstrip() if pre_text else payload[3:].rstrip()
        if not pre_text and payload[:3].strip():
            self.supplements += 1
        if text.strip() == MARKER_LINE:
            self.skip("26 with only %s" % MARKER_LINE)
            return
        if self.target == "short":
            self.target = "long"
        entry["long"].append(text)

    # -- result ----------------------------------------------------------
    def kind_of(self, entry):
        flags = entry["flags"].ljust(3)
        if flags[0] not in "NW " or flags[1] not in "NE " or flags[2] not in "N ":
            self.unknown_flags.append("%s (%s)" % (entry["item_no"], flags.strip()))
        return model.kind_of(alternative=flags[0] == "W", optional=flags[1] == "E",
                             unit=entry["unit"])

    def items(self):
        project = self.project_override or model.project_id(self.file_name, self.header_project)
        records, seen = [], {}
        for entry in self.entries:
            long_lines = list(entry["long"])
            short = " ".join(part for part in entry["short"] if part)
            if entry["kind"] == "preliminary_note":
                kind = "preliminary_note"
                while long_lines and not long_lines[0].strip():
                    long_lines.pop(0)
                if not short and long_lines:
                    short = long_lines.pop(0).strip()
                if not short and not long_lines:
                    self.warn("note at line %d has no text; not written" % entry["line"])
                    continue
            elif entry["kind"] == "heading":
                kind = "heading"
            else:
                kind = self.kind_of(entry)
                if entry["item_no"] in seen:
                    self.warn("item number %s stands twice (lines %d and %d)"
                              % (entry["item_no"], seen[entry["item_no"]], entry["line"]))
                seen[entry["item_no"]] = entry["line"]
            records.append(model.make_item(
                doc=self.doc, project=project, trade=self.trade, format=FORMAT,
                stage=self.stage, item_no=entry["item_no"], kind=kind,
                section=entry["section"], short_text=short,
                long_text="\n".join(long_lines).strip("\n"),
                quantity=entry["quantity"], unit=entry["unit"],
                unit_price=entry["unit_price"], total=entry["total"],
                page=None, line=entry["line"]))
        return project, records

    def manifest_entry(self, records, sha256):
        positions = sum(1 for record in records if model.is_position(record))
        if self.header_stage and self.header_stage != self.stage:
            self.warn("the header says stage %s, the file type says %s; the file type is used"
                      % (self.header_stage, self.stage))
        if self.declared_items is not None and self.declared_items != positions:
            self.warn("the end record names %d items, the reader found %d" % (self.declared_items, positions))
        if self.price_only:
            self.warn("%d items come from price records (23) without an item record (21): "
                      "kind, unit and texts are not in this file" % self.price_only)
        check = model.price_check(records)
        if check["no_quantity"]:
            self.warn("%d priced items have no quantity in this file: quantity x unit price = total "
                      "cannot be checked for them" % check["no_quantity"])
        if check["not_equal"]:
            self.warn("quantity x unit price is not the total for %d items: %s"
                      % (check["not_equal"], ", ".join(check["not_equal_items"])))
        sum_check = "not_in_file"
        if self.declared_sum:
            totals = sum(Decimal(repr(record["total"])) for record in records
                         if model.is_position(record) and record["total"] is not None)
            sum_check = "equal" if totals == self.declared_sum else "not_equal"
            if sum_check == "not_equal":
                self.warn("the sum in the end record is not the sum of the item totals")
        if self.unknown_flags:
            self.warn("item flags the reader does not know, items kept by the other rules: %s"
                      % ", ".join(self.unknown_flags))
        if self.unparsed:
            self.warn("%d lines not read" % len(self.unparsed))
        return model.make_manifest_entry(
            doc=self.doc, file=self.file_name, sha256=sha256, format=FORMAT,
            stage=self.stage, items=records, pages=None,
            unparsed_lines=len(self.unparsed), warnings=self.warnings,
            unparsed_line_numbers=self.unparsed[:UNPARSED_SHOWN],
            lines=self.line_count, encoding=self.encoding,
            declared_items=self.declared_items,
            sub_descriptions=sum(entry.get("subs", 0) for entry in self.entries),
            repeat_descriptions=sum(1 for entry in self.entries if entry.get("repeat")),
            text_supplement_lines=self.supplements,
            skipped_records=dict(sorted(self.skipped.items())),
            priced_items=check["priced"],
            price_check={"equal": check["equal"], "not_equal": check["not_equal"],
                         "no_quantity": check["no_quantity"]},
            sum_check=sum_check)


def parse_bytes(raw, file_name, project=None, sha256=None):
    """Read GAEB 90 bytes. Returns (project, item records, manifest entry)."""
    reader = _Reader(file_name, project).read(raw)
    project, records = reader.items()
    if sha256 is None:
        sha256 = hashlib.sha256(raw).hexdigest()
    return project, records, reader.manifest_entry(records, sha256)


def parse_file(path, project=None):
    with open(path, "rb") as handle:
        raw = handle.read()
    return parse_bytes(raw, os.path.basename(path), project)


def find_files(source):
    """The GAEB 90 files of a folder, or the one file given."""
    if os.path.isdir(source):
        return [os.path.join(source, name) for name in sorted(os.listdir(source))
                if is_gaeb90_name(name) and os.path.isfile(os.path.join(source, name))]
    if not os.path.isfile(source):
        raise Gaeb90Error("%s: no such file or folder" % source)
    stage_of(source)
    return [source]


def run(source="data", out_root="out", project=None):
    """Read the files and write out_root/<project>/. Returns the manifest
    entries with the project added under "project" (not written to disk)."""
    by_project = {}
    for path in find_files(source):
        name, records, entry = parse_file(path, project)
        by_project.setdefault(name, ([], []))
        by_project[name][0].extend(records)
        by_project[name][1].append(entry)
    report = []
    for name in sorted(by_project):
        records, entries = by_project[name]
        model.write_project(out_root, name, records, entries)
        report.extend(dict(entry, project=name) for entry in entries)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pipeline.lv.gaeb90",
                                     description="Read GAEB 90 files into OUT/<project>/items.json and manifest.json.")
    parser.add_argument("source", nargs="?", default="data", help="one .D83/.D84/.D86 file or a folder (default: data)")
    parser.add_argument("out", nargs="?", default="out", help="output folder (default: out)")
    parser.add_argument("--project", help="project folder name instead of the one from the file")
    args = parser.parse_args(argv)
    try:
        report = run(args.source, args.out, args.project)
    except Gaeb90Error as error:
        print("error: %s" % error, file=sys.stderr)
        return 2
    if not report:
        print("no .D83/.D84/.D86 file in %s" % args.source, file=sys.stderr)
        return 1
    for entry in report:
        check = entry["price_check"]
        print("%s -> %s: %d items, %d headings, %d notes, %d lines not read, %d warnings; "
              "priced %d: equal %d, not equal %d, no quantity %d"
              % (entry["file"], os.path.join(args.out, entry["project"]), entry["items"],
                 entry["headings"], entry["preliminary_notes"], entry["unparsed_lines"],
                 len(entry["warnings"]), entry["priced_items"], check["equal"],
                 check["not_equal"], check["no_quantity"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
