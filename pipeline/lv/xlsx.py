"""Excel reader for bills of quantities as .xlsx (W16): a simple column mapping.

Usage:
    python -m pipeline.lv.xlsx [FILE or FOLDER] [OUT] [--project NAME]

Reads one .xlsx file, or every .xlsx file of a folder (default: data), and writes
OUT/<project>/items.json and manifest.json (default OUT: out) in the contract v1 shape,
like the GAEB readers. It prints counts only, never a price. The page "Live-Prüfung"
reads an .xlsx upload with parse_bytes() in memory.

The organizer data holds no Excel list (MASTER_PLAN §4), so the column names below are
the usual German headings of an LV export, not read from a real file. A heading cell
matches when its text, without regard to case, blanks, dots, brackets, the euro sign and
a trailing "in €", is one of these names:

    item_no     Pos, PosNr, Position, Positionsnummer, OZ, Ordnungszahl, Nr
    short_text  Kurztext, Bezeichnung, Leistung, Leistungsbeschreibung, Beschreibung, Text
    long_text   Langtext
    quantity    Menge, Anzahl, Masse, Massen, LVMenge
    unit        Einheit, ME, EH, Mengeneinheit
    unit_price  EP, Einheitspreis
    total       GP, Gesamtpreis, Gesamtbetrag, Betrag
    kind        Art, Positionsart, Posart

The heading row is the first row among the first 30 of a sheet that names the item
number column and at least one of short text and quantity; the first sheet with such a
row is read. The trade is the first text above the heading row, else the sheet name.

Rows below the heading row, in order (the sheet row number goes to `line`):
    empty                                        skipped
    no item number, a text, no number            after a position: a line of its long text;
                                                 else a preliminary note
    no item number, a text starting with the     a sum row: skipped and counted
      word Summe, Übertrag, Zwischensumme, Gesamt
    item number, no quantity and no unit         a heading (section), also with a title total
    item number cell "Summe ..." or "Pos" again  a sum row or a repeated heading row: skipped
    item number with a quantity or a unit        a position
A position is optional ("Bedarf", "Eventual", "BP", "E" in the kind column), alternative
("Wahl", "Alternativ", "WP", "A") or, by its unit, a lump sum (model.kind_of).

Numbers: a number cell is taken as it is; a text cell is read in German ("1.250,50") or
plain form ("1250.5"). A cell that holds neither is counted in `unparsed_lines` with a
warning that names the row, never the value. Formulas are read by their stored result;
a formula without one is a missing value. An Excel list names no stage; it counts as a
request ("anfrage").
"""
import argparse
import hashlib
import io
import os
import re
import sys
import zipfile

from pipeline.lv import model

FORMAT = "xlsx"
STAGE = "anfrage"
EXTENSIONS = (".xlsx", ".xlsm")
HEADING_ROWS = 30
UNPARSED_SHOWN = 50

COLUMNS = {
    "item_no": ("pos", "posnr", "position", "positionsnummer", "oz", "ordnungszahl", "nr"),
    "short_text": ("kurztext", "bezeichnung", "leistung", "leistungsbeschreibung", "beschreibung", "text"),
    "long_text": ("langtext",),
    "quantity": ("menge", "anzahl", "masse", "massen", "lvmenge"),
    "unit": ("einheit", "me", "eh", "mengeneinheit"),
    "unit_price": ("ep", "einheitspreis"),
    "total": ("gp", "gesamtpreis", "gesamtbetrag", "betrag"),
    "kind": ("art", "positionsart", "posart"),
}
OPTIONAL_MARKS = ("bedarf", "bedarfsposition", "eventual", "eventualposition", "bp", "e")
ALTERNATIVE_MARKS = ("wahl", "wahlposition", "alternativ", "alternative", "alternativposition", "wp", "a")
SUM_ROW = re.compile(r"^(summe|übertrag|uebertrag|zwischensumme|gesamtsumme|gesamtbetrag|gesamt)\b", re.IGNORECASE)
# German "1.250,50" and "12,5"; "1.250" is 1250 (a dot before three digits is a thousands mark, as in web/app.py).
_GERMAN_DECIMAL = re.compile(r"^-?(\d{1,3}(\.\d{3})+|\d+),\d+$")
_GROUPED = re.compile(r"^-?[1-9]\d{0,2}(\.\d{3})+$")
_PLAIN_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


class XlsxError(ValueError):
    """The file cannot be read as an Excel bill of quantities at all. `german` is the reason for the page."""

    def __init__(self, message, german=None):
        ValueError.__init__(self, message)
        self.german = german


def is_xlsx_name(file_name):
    return os.path.splitext(file_name)[1].lower() in EXTENSIONS


def heading_key(value):
    """The column a heading cell names, or None."""
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    text = re.sub(r"\s+in\s*(€|eur)\s*$", "", text)
    text = re.sub(r"\((€|eur)\)", "", text)
    text = re.sub(r"[\s.\-_/()\[\]€:]+", "", text)
    for key, names in COLUMNS.items():
        if text in names:
            return key
    return None


def cell_text(value):
    """A cell as text ("" when empty). An item number stored as a whole number loses no digit."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def cell_number(value):
    """(number or None, readable). An empty cell is (None, True)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, True
    if isinstance(value, bool):
        return None, False
    if isinstance(value, (int, float)):
        return float(value), True
    text = re.sub(r"\s+", "", str(value)).replace("€", "")
    if _GERMAN_DECIMAL.match(text) or _GROUPED.match(text):
        return float(text.replace(".", "").replace(",", ".")), True
    if _PLAIN_NUMBER.match(text):
        return float(text), True
    return None, False


class _Reader:
    def __init__(self, file_name, project=None):
        self.file_name = os.path.basename(file_name)
        self.doc = model.doc_id(self.file_name)
        self.project_override = project
        self.warnings, self.unparsed = [], []
        self.sum_rows = 0
        self.repeated_headings = 0
        self.sheet = None
        self.trade = ""
        self.columns = {}
        self.rows = []

    def warn(self, message):
        self.warnings.append(message)

    def read(self, raw):
        try:
            import openpyxl
        except ImportError:  # pragma: no cover - openpyxl is in requirements.txt
            raise XlsxError("openpyxl is not installed (python -m pip install -r requirements.txt)")
        try:
            book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        except Exception as error:  # noqa: BLE001 - zip, XML or workbook errors of any kind: the file is no workbook
            raise XlsxError("%s is not an Excel workbook (.xlsx): %s" % (self.file_name, type(error).__name__),
                            "keine Excel-Arbeitsmappe (.xlsx)")
        try:
            for sheet in book.worksheets:
                try:
                    sheet.reset_dimensions()  # a stale <dimension> entry must not cut the sheet short
                    rows = [tuple(row) for row in sheet.iter_rows(values_only=True)]
                except Exception as error:
                    raise XlsxError("%s: the sheet %s cannot be read: %s" % (self.file_name, sheet.title, type(error).__name__),
                                    "die Tabelle %s ist beschädigt" % sheet.title)
                found = self.find_heading(rows)
                if found is not None:
                    self.sheet = sheet.title
                    start, columns = found
                    self.columns = columns
                    self.trade = self.title_above(rows, start) or sheet.title
                    self.rows = [(number, row) for number, row in enumerate(rows, 1) if number > start + 1]
                    break
        finally:
            book.close()
        if self.sheet is None:
            raise XlsxError("%s: no sheet has a heading row with an item number column (Pos, OZ, Position) and "
                            "a text or quantity column (Kurztext, Bezeichnung, Menge)" % self.file_name,
                            "keine Tabelle hat eine Kopfzeile mit einer Spalte für die Positionsnummer (Pos., OZ, "
                            "Position) und einer für Kurztext oder Menge")
        return self

    @staticmethod
    def find_heading(rows):
        for index, row in enumerate(rows[:HEADING_ROWS]):
            columns = {}
            for column, value in enumerate(row):
                key = heading_key(value)
                if key and key not in columns:
                    columns[key] = column
            if "item_no" in columns and ("short_text" in columns or "quantity" in columns):
                return index, columns
        return None

    @staticmethod
    def title_above(rows, start):
        for row in rows[:start]:
            for value in row:
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    def value(self, row, key):
        column = self.columns.get(key)
        if column is None or column >= len(row):
            return None
        return row[column]

    def number(self, row, key, row_no):
        number, readable = cell_number(self.value(row, key))
        if not readable:
            self.unparsed.append(row_no)
            self.warn("row %d: the %s cell holds no number" % (row_no, key.replace("_", " ")))
        return number

    def items(self):
        project = self.project_override or model.project_id(self.file_name)
        records, seen, open_section, last = [], {}, "", None
        for row_no, row in self.rows:
            if all(cell_text(value) == "" for value in row):
                continue
            item_no = cell_text(self.value(row, "item_no"))
            if item_no and (SUM_ROW.match(item_no) or heading_key(item_no) == "item_no"):
                self.sum_rows += 1 if SUM_ROW.match(item_no) else 0
                self.repeated_headings += 0 if SUM_ROW.match(item_no) else 1
                continue
            short = cell_text(self.value(row, "short_text"))
            long_text = cell_text(self.value(row, "long_text"))
            unit = cell_text(self.value(row, "unit")) or None
            if isinstance(self.value(row, "item_no"), float) and not self.value(row, "item_no").is_integer():
                self.warn("row %d: the item number is stored as a number (%s); write it as text to keep "
                          "trailing zeros" % (row_no, item_no))
            quantity = self.number(row, "quantity", row_no)
            unit_price = self.number(row, "unit_price", row_no)
            total = self.number(row, "total", row_no)
            if not item_no:
                text = short or long_text
                if not text:
                    continue
                if SUM_ROW.match(text) and quantity is None and unit is None:
                    self.sum_rows += 1
                    continue
                if last is not None and last["kind"] not in model.NOT_A_POSITION and quantity is None and unit is None:
                    last["long_text"] = (last["long_text"] + "\n" + text).strip("\n")
                    continue
                last = model.make_item(doc=self.doc, project=project, trade=self.trade, format=FORMAT, stage=STAGE,
                                       item_no="", kind="preliminary_note", section=open_section,
                                       short_text=short or text, long_text=long_text if short else "", line=row_no)
                records.append(last)
                continue
            if quantity is None and unit is None:
                open_section = item_no
                last = model.make_item(doc=self.doc, project=project, trade=self.trade, format=FORMAT, stage=STAGE,
                                       item_no=item_no, kind="heading", section=model.section_of(item_no),
                                       short_text=short, long_text=long_text, line=row_no)
                records.append(last)
                continue
            mark = re.sub(r"[\s.\-]+", "", cell_text(self.value(row, "kind")).lower())
            kind = model.kind_of(alternative=mark in ALTERNATIVE_MARKS, optional=mark in OPTIONAL_MARKS, unit=unit)
            if item_no in seen:
                self.warn("item number %s stands twice (rows %d and %d)" % (item_no, seen[item_no], row_no))
            seen[item_no] = row_no
            section = model.section_of(item_no) or open_section
            last = model.make_item(doc=self.doc, project=project, trade=self.trade, format=FORMAT, stage=STAGE,
                                   item_no=item_no, kind=kind, section=section, short_text=short,
                                   long_text=long_text, quantity=quantity, unit=unit, unit_price=unit_price,
                                   total=total, line=row_no)
            records.append(last)
        return project, records

    def manifest_entry(self, records, sha256):
        check = model.price_check(records)
        if check["not_equal"]:
            self.warn("quantity x unit price is not the total for %d items: %s"
                      % (check["not_equal"], ", ".join(check["not_equal_items"])))
        if check["no_quantity"]:
            self.warn("%d priced items have no quantity: quantity x unit price = total cannot be checked for them"
                      % check["no_quantity"])
        return model.make_manifest_entry(
            doc=self.doc, file=self.file_name, sha256=sha256, format=FORMAT, stage=STAGE, items=records,
            pages=None, unparsed_lines=len(self.unparsed), warnings=self.warnings,
            unparsed_line_numbers=self.unparsed[:UNPARSED_SHOWN], sheet=self.sheet,
            columns=sorted(self.columns), sum_rows=self.sum_rows, repeated_heading_rows=self.repeated_headings,
            priced_items=check["priced"],
            price_check={"equal": check["equal"], "not_equal": check["not_equal"], "no_quantity": check["no_quantity"]})


def parse_bytes(raw, file_name, project=None, sha256=None):
    """Read .xlsx bytes. Returns (project, item records, manifest entry)."""
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
    """The .xlsx files of a folder, or the one file given."""
    if os.path.isdir(source):
        return [os.path.join(source, name) for name in sorted(os.listdir(source))
                if is_xlsx_name(name) and not name.startswith("~$") and os.path.isfile(os.path.join(source, name))]
    if not os.path.isfile(source):
        raise XlsxError("%s: no such file or folder" % source)
    if not is_xlsx_name(source):
        raise XlsxError("%s: the file type is not .xlsx" % os.path.basename(source))
    return [source]


def run(source="data", out_root="out", project=None):
    """Read the files and write out_root/<project>/. Returns the manifest entries with "project" added."""
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
    parser = argparse.ArgumentParser(prog="python -m pipeline.lv.xlsx",
                                     description="Read Excel lists (.xlsx) into OUT/<project>/items.json and manifest.json.")
    parser.add_argument("source", nargs="?", default="data", help="one .xlsx file or a folder (default: data)")
    parser.add_argument("out", nargs="?", default="out", help="output folder (default: out)")
    parser.add_argument("--project", help="project folder name instead of the one from the file name")
    args = parser.parse_args(argv)
    try:
        report = run(args.source, args.out, args.project)
    except XlsxError as error:
        print("error: %s" % error, file=sys.stderr)
        return 2
    if not report:
        print("no .xlsx file in %s" % args.source, file=sys.stderr)
        return 1
    for entry in report:
        check = entry["price_check"]
        print("%s -> %s: sheet %s, %d items, %d headings, %d notes, %d cells not read, %d warnings; "
              "priced %d: equal %d, not equal %d, no quantity %d"
              % (entry["file"], os.path.join(args.out, entry["project"]), entry["sheet"], entry["items"],
                 entry["headings"], entry["preliminary_notes"], entry["unparsed_lines"], len(entry["warnings"]),
                 entry["priced_items"], check["equal"], check["not_equal"], check["no_quantity"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
