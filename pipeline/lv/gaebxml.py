"""GAEB XML reader for .X83, .X84 and .X86 files, versions 3.1 and 3.2 (W12).

Usage:
    python -m pipeline.lv.gaebxml [FILE or FOLDER] [OUT] [--project NAME]

Reads one GAEB XML file, or every .X83/.X84/.X86 file of a folder (default:
data), and writes OUT/<project>/items.json and manifest.json (default OUT:
out) in the contract v1 shape. It prints counts only, never a price.

The layout below was read from the four organizer files, not from the
official format text (MASTER_PLAN part C2). The namespace differs by version
(3.1 ".../GAEB_DA_XML/200407", 3.2 ".../GAEB_DA_XML/DA83/3.2"), so every tag
is read by its local name. The parser resolves no entity, loads no DTD and
uses no network.

    GAEB
      GAEBInfo   Version -> gaeb_version in the manifest
      PrjInfo    NamePrj -> project
      Award
        DP       stage as the file states it (compared with the file type)
        AddText  text before the list (OutlineAddText, DetailAddText)
                 -> preliminary_note without a number
        BoQ
          BoQInfo  LblBoQ -> trade
          BoQBody
            BoQCtgy   section: RNoPart, LblTx -> heading; holds a BoQBody
            Remark    note in a section -> preliminary_note
            Itemlist
              Item       RNoPart, Qty, QU, Description -> item
              Remark     -> preliminary_note
              PerfDescr  description that items point to (RefPerfNo)
                         -> preliminary_note

An item number is the RNoPart values from the outermost section down to the
item, joined with "." (and RNoIndex, when an item has one; not seen in these
files). The section of a heading is its parent section. A note carries the
number of the section it stands in, as in the GAEB 90 reader.

Item kind: Provis (seen: "WithoutTotal", an item without a total) ->
optional; LumpSumItem "Yes" or a lump-sum unit -> lump_sum; else normal.
From the format as generally described, not seen in these files: ALNSerNo
other than 0 -> alternative; UP and IT hold the unit price and the total.
C2 speaks of a "Yes/No" flag on the items: the files hold three such flags,
LumpSumItem ("Yes"), SumDescr ("Yes") and UPBkdn ("No"); only LumpSumItem
changes the kind.

Texts: OutlineText/OutlTxt/TextOutlTxt -> short_text (one line);
DetailTxt -> long_text, its Text and TextComplement parts in file order.
Inside a text, p, ul, li, table, tr and td start a new line, br ends a
line, span is inline. A TextComplement (text the owner or the bidder fills
in) gives caption, body and tail in the running text. SubDescr (a
sub-description of an item) goes to the long text of the item, number first.
An image and a page break inside a text are not text: they are counted under
skipped_elements.

Every element is read, skipped on purpose (counted by name in
skipped_elements), or not known to the reader. An element the reader does
not know is not read, with everything inside it: it is counted in
unparsed_lines (for this format: the number of such elements), by name in
unparsed_elements and by source line in unparsed_element_lines, and a
warning names the entry it stands in. A number field that cannot be read is
counted the same way. An entity reference is never resolved and is counted
as "#entity".

page is null. line is the source line of the element in the file; two of the
four organizer files hold the XML declaration on line 1 and all the rest on
line 2, so there it is 2 everywhere.
"""
import argparse
import hashlib
import os
import sys
from decimal import Decimal, InvalidOperation

from lxml import etree

from pipeline.lv import model

FORMAT = "gaebxml"
STAGE_BY_EXTENSION = {".x83": "83", ".x84": "84", ".x86": "86"}
UNPARSED_SHOWN = 50

# Inside a text: elements that start a new line, and inline elements.
TEXT_BLOCKS = frozenset(["p", "ul", "li", "table", "tr", "td"])
TEXT_INLINE = frozenset(["span"])
TEXT_NOT_TEXT = frozenset(["image", "page"])
COMPLEMENT_PARTS = frozenset(["ComplCaption", "ComplBody", "ComplTail"])
COMPLEMENT_SKIPPED = frozenset(["ComplBodyDec"])

# Elements that are known and not needed, per parent.
INFO_SKIPPED = frozenset(["VersDate", "Date", "Time", "ProgSystem", "ProgName", "Certific"])
PROJECT_SKIPPED = frozenset(["LblPrj", "Descrip", "Cur", "CurLbl"])
AWARD_SKIPPED = frozenset(["AwardInfo", "OWN"])
BOQ_INFO_SKIPPED = frozenset(["Name", "Date", "OutlCompl", "BoQBkdn", "Ctlg", "NoUPComps", "LblTime"])
ITEM_SKIPPED = frozenset(["UPBkdn", "SumDescr", "RefRNo"])
DESCRIPTION_SKIPPED = frozenset(["StLNo", "STLBBau"])
COMPLETE_TEXT_SKIPPED = frozenset(["ComplTSA", "ComplTSB"])
NOTE_SKIPPED = frozenset(["PerfNo"])
SUB_SKIPPED = frozenset(["UPBkdn"])
ITEM_ATTRIBUTES = frozenset(["ID", "RNoPart", "RNoIndex"])
CATEGORY_ATTRIBUTES = frozenset(["ID", "RNoPart"])


class GaebXmlError(ValueError):
    """The file cannot be read as GAEB XML at all."""


def is_gaebxml_name(file_name):
    return os.path.splitext(file_name)[1].lower() in STAGE_BY_EXTENSION


def stage_of(file_name):
    extension = os.path.splitext(file_name)[1].lower()
    if extension not in STAGE_BY_EXTENSION:
        raise GaebXmlError("%s: the file type is not .X83, .X84 or .X86" % os.path.basename(file_name))
    return STAGE_BY_EXTENSION[extension]


def local(element):
    """Local name of an element; "#entity" for an entity reference; None for
    a comment or a processing instruction."""
    if isinstance(element.tag, str):
        return etree.QName(element).localname
    if isinstance(element, etree._Entity):
        return "#entity"
    return None


def _clean(text):
    """Text of one node. White space that only formats the file (a run with
    a line break and nothing else) is dropped; a line break inside a text
    counts as one blank."""
    if not text:
        return ""
    if not text.strip() and ("\n" in text or "\r" in text):
        return ""
    if "\n" in text or "\r" in text:
        text = " ".join(part for part in text.replace("\r", "\n").split("\n"))
    return text


class _Lines(object):
    """Collects running text as lines."""

    def __init__(self):
        self.lines = [""]

    def add(self, text):
        self.lines[-1] += text

    def end_line(self):
        self.lines.append("")

    def new_line(self):
        if self.lines[-1].strip():
            self.lines.append("")

    def text(self):
        lines = [line.rstrip() for line in self.lines]
        while lines and not lines[-1]:
            lines.pop()
        while lines and not lines[0]:
            lines.pop(0)
        return "\n".join(lines)


def one_line(text):
    return " ".join(text.split())


class _Reader(object):
    def __init__(self, file_name, project=None):
        self.file_name = os.path.basename(file_name)
        self.doc = model.doc_id(self.file_name)
        self.stage = stage_of(self.file_name)
        self.project_override = project
        self.header_project = ""
        self.header_stage = None
        self.version = None
        self.namespace = None
        self.trade = ""
        self.entries = []
        self.warnings = []
        self.unparsed = {}
        self.unparsed_lines = []
        self.unparsed_total = 0
        self.skipped = {}
        self.where = "the file header"
        self.counts = {"sub_descriptions": 0, "repeat_descriptions": 0,
                       "description_references": 0, "text_complements": 0}
        self.unknown_flags = []

    # -- small helpers ---------------------------------------------------
    def warn(self, message):
        self.warnings.append(message)

    def skip(self, name):
        self.skipped[name] = self.skipped.get(name, 0) + 1

    def bad(self, element, name=None, reason=None):
        """Count one element that is not read."""
        name = name or local(element)
        self.unparsed[name] = self.unparsed.get(name, 0) + 1
        self.unparsed_total += 1
        line = getattr(element, "sourceline", None)
        if line is not None and len(self.unparsed_lines) < UNPARSED_SHOWN:
            self.unparsed_lines.append(line)
        self.warn("%s (line %s) in %s: %s" % (name, line if line is not None else "?", self.where,
                                             reason or "the reader does not know this element; not read"))

    def children(self, element, skipped=frozenset()):
        """The child elements with their local names. Comments and processing
        instructions are passed over; names in `skipped` are counted as
        skipped and not returned."""
        for child in element:
            name = local(child)
            if name is None:
                continue
            if name in skipped:
                self.skip(name)
                continue
            yield name, child

    def value(self, element):
        """Text of a plain value element (no child elements expected). Text
        after a comment or a processing instruction belongs to the value."""
        parts = [element.text or ""]
        for child in element:
            if local(child) is not None:
                self.bad(child)
            parts.append(child.tail or "")
        return "".join(parts).strip()

    def number(self, element, what):
        text = self.value(element)
        if not text:
            return None
        try:
            number = Decimal(text)
        except InvalidOperation:
            number = None
        if number is None or not number.is_finite():
            self.bad(element, reason="%s is not a number; not read" % what)
            return None
        return number

    # -- texts -----------------------------------------------------------
    def rich(self, element, lines):
        """Add the text inside `element` to `lines`."""
        lines.add(_clean(element.text))
        for child in element:
            name = local(child)
            if name is None:
                pass
            elif name == "br":
                lines.end_line()
            elif name in TEXT_INLINE:
                self.rich(child, lines)
            elif name == "p":
                lines.new_line()
                self.rich(child, lines)
                lines.end_line()
            elif name in TEXT_BLOCKS:
                lines.new_line()
                self.rich(child, lines)
                lines.new_line()
            elif name == "TextComplement":
                self.complement(child, lines)
            elif name in TEXT_NOT_TEXT:
                self.skip(name)
            else:
                self.bad(child)
            lines.add(_clean(child.tail))

    def complement(self, element, lines):
        self.counts["text_complements"] += 1
        for name, child in self.children(element, COMPLEMENT_SKIPPED):
            if name in COMPLEMENT_PARTS:
                self.rich(child, lines)
            else:
                self.bad(child)

    def plain(self, element):
        lines = _Lines()
        self.rich(element, lines)
        return lines.text()

    def description(self, element):
        """(short text, long text) of a Description element."""
        short, long_lines = [], _Lines()
        for name, child in self.children(element, DESCRIPTION_SKIPPED):
            if name == "CompleteText":
                for part_name, part in self.children(child, COMPLETE_TEXT_SKIPPED):
                    if part_name == "DetailTxt":
                        self.detail(part, long_lines)
                    elif part_name == "OutlineText":
                        short.append(self.outline(part))
                    else:
                        self.bad(part)
            elif name == "OutlineText":
                short.append(self.outline(child))
            else:
                self.bad(child)
        return " ".join(part for part in short if part), long_lines.text()

    def detail(self, element, lines):
        for name, child in self.children(element):
            if name == "Text":
                self.rich(child, lines)
            elif name == "TextComplement":
                self.complement(child, lines)
            else:
                self.bad(child)

    def outline(self, element):
        parts = []
        for name, child in self.children(element):
            if name == "OutlTxt":
                for inner_name, inner in self.children(child):
                    if inner_name == "TextOutlTxt":
                        parts.append(one_line(self.plain(inner)))
                    else:
                        self.bad(inner)
            elif name == "TextOutlTxt":
                parts.append(one_line(self.plain(child)))
            else:
                self.bad(child)
        return " ".join(part for part in parts if part)

    # -- structure -------------------------------------------------------
    def new_entry(self, kind, element, item_no, section):
        entry = {"kind": kind, "line": getattr(element, "sourceline", None), "item_no": item_no,
                 "section": section, "short": "", "long": "", "quantity": None, "unit": None,
                 "unit_price": None, "total": None}
        self.entries.append(entry)
        return entry

    def read(self, raw):
        parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                                 dtd_validation=False, huge_tree=False, remove_blank_text=False)
        try:
            root = etree.fromstring(raw, parser)
        except etree.XMLSyntaxError as error:
            raise GaebXmlError("%s: not well-formed XML (line %s)"
                               % (self.file_name, getattr(error, "lineno", "?")))
        if local(root) != "GAEB":
            raise GaebXmlError("%s: the root element is %s, not GAEB" % (self.file_name, local(root)))
        self.namespace = etree.QName(root).namespace
        award_seen = False
        for name, child in self.children(root):
            if name == "GAEBInfo":
                for info_name, info in self.children(child, INFO_SKIPPED):
                    if info_name == "Version":
                        self.version = self.value(info) or None
                    else:
                        self.bad(info)
            elif name == "PrjInfo":
                for info_name, info in self.children(child, PROJECT_SKIPPED):
                    if info_name == "NamePrj":
                        self.header_project = self.value(info)
                    else:
                        self.bad(info)
            elif name == "Award":
                award_seen = True
                self.award(child)
            else:
                self.bad(child)
        if not award_seen:
            self.warn("no Award element: the file holds no list")
        return self

    def award(self, element):
        for name, child in self.children(element, AWARD_SKIPPED):
            if name == "DP":
                self.header_stage = self.value(child) or None
            elif name == "AddText":
                self.add_text(child)
            elif name == "BoQ":
                self.where = "the list header"
                for boq_name, part in self.children(child):
                    if boq_name == "BoQInfo":
                        self.boq_info(part)
                    elif boq_name == "BoQBody":
                        self.body(part, "")
                    else:
                        self.bad(part)
                self.where = "the file header"
            else:
                self.bad(child)

    def boq_info(self, element):
        for name, child in self.children(element, BOQ_INFO_SKIPPED):
            if name == "LblBoQ":
                self.trade = one_line(self.value(child))
            elif name.startswith("LblUPComp"):
                self.skip("LblUPComp")
            else:
                self.bad(child)

    def add_text(self, element):
        entry = self.new_entry("preliminary_note", element, "", "")
        self.where = "the text before the list (line %s)" % entry["line"]
        for name, child in self.children(element):
            if name == "OutlineAddText":
                entry["short"] = one_line(self.plain(child))
            elif name == "DetailAddText":
                entry["long"] = self.plain(child)
            else:
                self.bad(child)
        self.where = "the file header"

    def body(self, element, section):
        for name, child in self.children(element):
            if name == "BoQCtgy":
                self.category(child, section)
            elif name == "Itemlist":
                for list_name, part in self.children(child):
                    if list_name == "Item":
                        self.item(part, section)
                    elif list_name in ("Remark", "PerfDescr"):
                        self.note(part, section)
                    else:
                        self.where = "section %s" % (section or "(none)")
                        self.bad(part)
            elif name == "Remark":
                self.note(child, section)
            else:
                self.where = "section %s" % (section or "(none)")
                self.bad(child)

    def attributes(self, element, known, what):
        extra = sorted(str(name) for name in element.attrib if name not in known)
        if extra:
            self.warn("%s: attributes the reader does not use: %s" % (what, ", ".join(extra)))

    def category(self, element, parent):
        part = (element.get("RNoPart") or "").strip()
        number = ".".join(piece for piece in (parent, part) if piece)
        entry = self.new_entry("heading", element, number, parent)
        self.where = "section %s (line %s)" % (number or "(no number)", entry["line"])
        if not part:
            self.warn("section at line %s has no number (RNoPart)" % entry["line"])
        self.attributes(element, CATEGORY_ATTRIBUTES, "section %s" % number)
        bodies = []
        for name, child in self.children(element):
            if name == "LblTx":
                entry["short"] = one_line(self.plain(child))
            elif name == "NotApplBoQ":
                if self.value(child) != "No":
                    self.warn("section %s is marked as not applicable (NotApplBoQ); it is read all the same"
                              % number)
                self.skip(name)
            elif name == "BoQBody":
                bodies.append(child)
            else:
                self.bad(child)
        for child in bodies:
            self.body(child, number)

    def note(self, element, section):
        entry = self.new_entry("preliminary_note", element, section, model.section_of(section))
        self.where = "the note at line %s (section %s)" % (entry["line"], section or "none")
        label = ""
        for name, child in self.children(element, NOTE_SKIPPED):
            if name == "Description":
                entry["short"], entry["long"] = self.description(child)
            elif name == "PerfLbl":
                label = one_line(self.value(child))
            else:
                self.bad(child)
        if label and label != entry["short"]:
            entry["short"] = " ".join(part for part in (label + ":" if entry["short"] else label,
                                                        entry["short"]) if part)

    def item(self, element, section):
        part = (element.get("RNoPart") or "").strip()
        index = (element.get("RNoIndex") or "").strip()
        number = ".".join(piece for piece in (section, part, index) if piece)
        entry = self.new_entry("item", element, number, section)
        self.where = "item %s (line %s)" % (number or "(no number)", entry["line"])
        if not part:
            self.warn("item at line %s has no number (RNoPart)" % entry["line"])
        self.attributes(element, ITEM_ATTRIBUTES, "item %s" % number)
        entry.update(optional=False, alternative=False, lump_sum=False)
        subs = []
        for name, child in self.children(element, ITEM_SKIPPED):
            if name == "Qty":
                entry["quantity"] = self.number(child, "the quantity")
            elif name == "QU":
                entry["unit"] = self.value(child) or None
            elif name == "UP":
                entry["unit_price"] = self.number(child, "the unit price")
            elif name == "IT":
                entry["total"] = self.number(child, "the total")
            elif name == "Description":
                entry["short"], entry["long"] = self.description(child)
            elif name == "Provis":
                entry["optional"] = True
                value = self.value(child)
                if value not in ("WithoutTotal", "WithTotal"):
                    self.unknown_flags.append("%s (Provis %s)" % (number, value or "empty"))
            elif name == "LumpSumItem":
                value = self.value(child)
                entry["lump_sum"] = value == "Yes"
                if value not in ("Yes", "No"):
                    self.unknown_flags.append("%s (LumpSumItem %s)" % (number, value or "empty"))
            elif name == "ALNGroupNo":
                self.skip(name)
            elif name == "ALNSerNo":
                entry["alternative"] = self.value(child).strip("0") != ""
            elif name == "RefDescr":
                value = self.value(child)
                if value == "Rep":
                    self.counts["repeat_descriptions"] += 1
                elif value != "Ref":
                    self.unknown_flags.append("%s (RefDescr %s)" % (number, value or "empty"))
                self.skip(name)
            elif name == "RefPerfNo":
                self.counts["description_references"] += 1
                self.skip(name)
            elif name == "SubDescr":
                subs.append(self.sub_description(child))
            else:
                self.bad(child)
        if subs:
            entry["long"] = "\n\n".join(part for part in [entry["long"]] + subs if part)

    def sub_description(self, element):
        self.counts["sub_descriptions"] += 1
        number, short, long_text = "", "", ""
        for name, child in self.children(element, SUB_SKIPPED):
            if name == "SubDNo":
                number = self.value(child)
            elif name == "Description":
                short, long_text = self.description(child)
            else:
                self.bad(child)
        head = " ".join(part for part in (number, short) if part)
        return "\n".join(part for part in (head, long_text) if part)

    # -- result ----------------------------------------------------------
    def items(self):
        project = self.project_override or model.project_id(self.file_name, self.header_project)
        records, seen = [], {}
        for entry in self.entries:
            if entry["kind"] == "item":
                kind = model.kind_of(alternative=entry["alternative"], optional=entry["optional"],
                                     unit=entry["unit"])
                if kind == "normal" and entry["lump_sum"]:
                    kind = "lump_sum"
                if entry["item_no"] in seen:
                    self.warn("item number %s stands twice (lines %s and %s)"
                              % (entry["item_no"], seen[entry["item_no"]], entry["line"]))
                seen[entry["item_no"]] = entry["line"]
            else:
                kind = entry["kind"]
                if kind == "preliminary_note" and not entry["short"] and not entry["long"]:
                    self.warn("note at line %s has no text; not written" % entry["line"])
                    continue
            records.append(model.make_item(
                doc=self.doc, project=project, trade=self.trade, format=FORMAT,
                stage=self.stage, item_no=entry["item_no"], kind=kind,
                section=entry["section"], short_text=entry["short"], long_text=entry["long"],
                quantity=entry["quantity"], unit=entry["unit"],
                unit_price=entry["unit_price"], total=entry["total"],
                page=None, line=entry["line"]))
        return project, records

    def manifest_entry(self, records, sha256):
        if self.header_stage and self.header_stage != self.stage:
            self.warn("the file says stage %s (DP), the file type says %s; the file type is used"
                      % (self.header_stage, self.stage))
        if not self.header_project and not self.project_override:
            self.warn("no project number in the file (PrjInfo/NamePrj): the file name is used")
        check = model.price_check(records)
        if check["no_quantity"]:
            self.warn("%d priced items have no quantity: quantity x unit price = total "
                      "cannot be checked for them" % check["no_quantity"])
        if check["not_equal"]:
            self.warn("quantity x unit price is not the total for %d items: %s"
                      % (check["not_equal"], ", ".join(check["not_equal_items"])))
        if self.unknown_flags:
            self.warn("item flags with a value the reader does not know, items kept by the other rules: %s"
                      % ", ".join(self.unknown_flags))
        if self.unparsed_total:
            self.warn("%d elements not read" % self.unparsed_total)
        return model.make_manifest_entry(
            doc=self.doc, file=self.file_name, sha256=sha256, format=FORMAT,
            stage=self.stage, items=records, pages=None,
            unparsed_lines=self.unparsed_total, warnings=self.warnings,
            unparsed_elements=dict(sorted(self.unparsed.items())),
            unparsed_element_lines=list(self.unparsed_lines),
            skipped_elements=dict(sorted(self.skipped.items())),
            gaeb_version=self.version, namespace=self.namespace,
            sub_descriptions=self.counts["sub_descriptions"],
            repeat_descriptions=self.counts["repeat_descriptions"],
            description_references=self.counts["description_references"],
            text_complements=self.counts["text_complements"],
            priced_items=check["priced"],
            price_check={"equal": check["equal"], "not_equal": check["not_equal"],
                         "no_quantity": check["no_quantity"]})


def parse_bytes(raw, file_name, project=None, sha256=None):
    """Read GAEB XML bytes. Returns (project, item records, manifest entry)."""
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
    """The GAEB XML files of a folder, or the one file given."""
    if os.path.isdir(source):
        return [os.path.join(source, name) for name in sorted(os.listdir(source))
                if is_gaebxml_name(name) and os.path.isfile(os.path.join(source, name))]
    if not os.path.isfile(source):
        raise GaebXmlError("%s: no such file or folder" % source)
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
    parser = argparse.ArgumentParser(prog="python -m pipeline.lv.gaebxml",
                                     description="Read GAEB XML files into OUT/<project>/items.json and manifest.json.")
    parser.add_argument("source", nargs="?", default="data", help="one .X83/.X84/.X86 file or a folder (default: data)")
    parser.add_argument("out", nargs="?", default="out", help="output folder (default: out)")
    parser.add_argument("--project", help="project folder name instead of the one from the file")
    args = parser.parse_args(argv)
    try:
        report = run(args.source, args.out, args.project)
    except ValueError as error:
        print("error: %s" % error, file=sys.stderr)
        return 2
    if not report:
        print("no .X83/.X84/.X86 file in %s" % args.source, file=sys.stderr)
        return 1
    for entry in report:
        check = entry["price_check"]
        print("%s -> %s: %d items, %d headings, %d notes, %d elements not read, %d warnings; "
              "priced %d: equal %d, not equal %d, no quantity %d"
              % (entry["file"], os.path.join(args.out, entry["project"]), entry["items"],
                 entry["headings"], entry["preliminary_notes"], entry["unparsed_lines"],
                 len(entry["warnings"]), entry["priced_items"], check["equal"],
                 check["not_equal"], check["no_quantity"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
