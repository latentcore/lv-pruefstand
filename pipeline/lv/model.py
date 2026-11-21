"""Canonical item model (W11, MASTER_PLAN §8).

Every reader in pipeline/lv builds its records with make_item() and
make_manifest_entry() and writes them with write_project(), so all formats
give the same contract v1 shape (contract/items.schema.json,
contract/manifest.schema.json). The schema check itself is
pipeline/common/contract.py; this module does not copy it.
"""
import hashlib
import json
import os
import re
from decimal import Decimal

from pipeline.common import contract

ITEM_KEYS = (
    "doc", "project", "trade", "format", "stage", "item_no", "kind", "section",
    "short_text", "long_text", "quantity", "unit", "unit_price", "total",
    "page", "line", "pre_trade_text", "post_trade_text",
)
KINDS = ("normal", "optional", "alternative", "lump_sum", "preliminary_note", "heading")
FORMATS = ("pdf", "gaeb90", "gaebxml", "xlsx")
STAGES = ("anfrage", "83", "84", "86")
NOT_A_POSITION = ("heading", "preliminary_note")
# Same unit list as pipeline/pdf: an item with one of these units is a lump sum.
LUMP_UNITS = frozenset(["psch", "pau", "pausch", "pauschal"])
# quantity x unit price may differ from the total by half a cent (rounding).
PRICE_TOLERANCE = Decimal("0.005")


def doc_id(file_name):
    """Document id for one file: the file name with every character outside
    A-Z a-z 0-9 . _ - turned into "_". The extension stays, because twins
    share the name stem (example: one list as .X83 and .D83)."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.basename(file_name)).strip("_")
    if not name:
        raise ValueError("file name %r gives an empty document id" % file_name)
    return name


def project_id(file_name, header_project=None):
    """Project folder name: the project number of the file header when the
    file has one, else the file name without extension and without a leading
    "Angebot ". Characters outside A-Z a-z 0-9 . _ - become "_"."""
    raw = (header_project or "").strip()
    if not raw:
        raw = os.path.splitext(os.path.basename(file_name))[0]
        raw = re.sub(r"^Angebot\s+", "", raw)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("_")
    if not name or set(name) == {"."}:
        raise ValueError("no project name for file %r" % file_name)
    return name


def section_of(item_no):
    """Number of the section an item number sits in ("01.02.3" -> "01.02")."""
    parts = item_no.split(".")
    return ".".join(parts[:-1]) if len(parts) > 1 else ""


def item_no_key(item_no):
    """Comparison key for item numbers across formats: every part without
    leading zeros and blanks ("01.01.0010" and "1.1.10" give "1.1.10").
    items.json keeps the number as the file writes it."""
    parts = []
    for part in item_no.split("."):
        part = part.strip()
        parts.append(part.lstrip("0") or ("0" if part else ""))
    return ".".join(parts)


def kind_of(alternative=False, optional=False, unit=None):
    """Kind of a position from what the file says about it."""
    if alternative:
        return "alternative"
    if optional:
        return "optional"
    if unit and unit.strip().rstrip(".").lower() in LUMP_UNITS:
        return "lump_sum"
    return "normal"


def _number(name, value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("%s must be a number or None, got %r" % (name, type(value).__name__))
    return float(value)


def _text(name, value, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ValueError("%s must be a string, got %r" % (name, type(value).__name__))
    return value


def make_item(doc, project, trade, format, stage, item_no, kind, short_text="",
              long_text="", section=None, quantity=None, unit=None,
              unit_price=None, total=None, page=None, line=None,
              pre_trade_text=None, post_trade_text=None):
    """One items.json record with all contract v1 keys, in contract order."""
    if not doc:
        raise ValueError("doc is empty")
    if format not in FORMATS:
        raise ValueError("format %r is not one of %s" % (format, ", ".join(FORMATS)))
    if stage not in STAGES:
        raise ValueError("stage %r is not one of %s" % (stage, ", ".join(STAGES)))
    if kind not in KINDS:
        raise ValueError("kind %r is not one of %s" % (kind, ", ".join(KINDS)))
    for name, value in (("page", page), ("line", line)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValueError("%s must be an integer or None" % name)
    item_no = _text("item_no", item_no)
    return {
        "doc": _text("doc", doc), "project": _text("project", project),
        "trade": _text("trade", trade), "format": format, "stage": stage,
        "item_no": item_no, "kind": kind,
        "section": section_of(item_no) if section is None else _text("section", section),
        "short_text": _text("short_text", short_text),
        "long_text": _text("long_text", long_text),
        "quantity": _number("quantity", quantity),
        "unit": _text("unit", unit, optional=True),
        "unit_price": _number("unit_price", unit_price),
        "total": _number("total", total),
        "page": page, "line": line,
        "pre_trade_text": _text("pre_trade_text", pre_trade_text, optional=True),
        "post_trade_text": _text("post_trade_text", post_trade_text, optional=True),
    }


def is_position(item):
    """True for an item that can carry a quantity (not a heading, not a note)."""
    return item["kind"] not in NOT_A_POSITION


def price_check(items):
    """Check quantity x unit price = total for every priced position.

    A position is priced when it has a unit price and a total. Returns counts
    and item numbers only, never a price:
    {"priced", "equal", "not_equal", "no_quantity", "not_equal_items"}.
    """
    result = {"priced": 0, "equal": 0, "not_equal": 0, "no_quantity": 0, "not_equal_items": []}
    for item in items:
        if not is_position(item) or item["unit_price"] is None or item["total"] is None:
            continue
        result["priced"] += 1
        if item["quantity"] is None:
            result["no_quantity"] += 1
            continue
        product = Decimal(repr(item["quantity"])) * Decimal(repr(item["unit_price"]))
        if abs(product - Decimal(repr(item["total"]))) <= PRICE_TOLERANCE:
            result["equal"] += 1
        else:
            result["not_equal"] += 1
            result["not_equal_items"].append(item["item_no"])
    return result


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_manifest_entry(doc, file, sha256, format, stage, items, pages=None,
                        unparsed_lines=0, warnings=None, **counts):
    """One manifest.json record. `items` is the list of this document's item
    records; the entry stores how many of them are positions, headings and
    notes. Extra counts go in as keyword arguments."""
    if format not in FORMATS:
        raise ValueError("format %r is not one of %s" % (format, ", ".join(FORMATS)))
    if stage not in STAGES:
        raise ValueError("stage %r is not one of %s" % (stage, ", ".join(STAGES)))
    entry = {
        "doc": doc, "file": file, "sha256": sha256, "format": format, "stage": stage,
        "pages": pages,
        "items": sum(1 for item in items if is_position(item)),
        "headings": sum(1 for item in items if item["kind"] == "heading"),
        "preliminary_notes": sum(1 for item in items if item["kind"] == "preliminary_note"),
        "unparsed_lines": unparsed_lines,
        "warnings": list(warnings or []),
    }
    entry.update(counts)
    return entry


def _read_list(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("%s does not hold a list" % path)
    return data


def write_project(out_root, project, items, manifest):
    """Write out_root/<project>/items.json and manifest.json.

    Records of other documents that are already in the two files stay; records
    of the documents in `manifest` are replaced. So several readers (GAEB 90,
    GAEB XML, PDF) can write into one project folder. Two files with the same
    document id are refused. Both files are checked against contract v1
    before anything is written. Returns the folder.
    """
    folder = os.path.join(out_root, project)
    docs = set(entry["doc"] for entry in manifest)
    stray = sorted(set(item["doc"] for item in items) - docs)
    if stray:
        raise ValueError("items without a manifest entry: %s" % ", ".join(stray))
    saved = _read_list(os.path.join(folder, "manifest.json"))
    files = {}
    for entry in manifest:
        if entry["doc"] in files:
            raise ValueError("two files give the document id %r (%r, %r): rename one"
                             % (entry["doc"], files[entry["doc"]], entry["file"]))
        files[entry["doc"]] = entry["file"]
    for entry in saved:
        if entry.get("doc") in files and entry.get("file") != files[entry["doc"]]:
            raise ValueError("document id %r is already used by the file %r in %s: rename %r"
                             % (entry["doc"], entry.get("file"), folder, files[entry["doc"]]))
    old_manifest = [e for e in saved if e.get("doc") not in docs]
    old_items = [i for i in _read_list(os.path.join(folder, "items.json")) if i.get("doc") not in docs]
    all_manifest = sorted(old_manifest + list(manifest), key=lambda e: str(e.get("doc") or e.get("file")))
    order = dict((entry.get("doc"), index) for index, entry in enumerate(all_manifest))
    all_items = sorted(old_items + list(items), key=lambda i: order.get(i.get("doc"), len(order)))
    contract.check("items", all_items)
    contract.check("manifest", all_manifest)
    os.makedirs(folder, exist_ok=True)
    for name, data in (("items.json", all_items), ("manifest.json", all_manifest)):
        with open(os.path.join(folder, name), "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=1)
            handle.write("\n")
    return folder
