"""Shared parts of the base checks: numbers, units, documents, quotes, findings.

Thresholds stand here once; pipeline/base/README.md gives the reason for each.
"""
import re
import statistics
from decimal import Decimal, InvalidOperation

from pipeline.common import ids, quotes

# --- thresholds (README.md, "Thresholds") ---------------------------------
PRICE_TOLERANCE = Decimal("0.005")   # B1, B2: half a cent
OUTLIER_FACTOR = Decimal(10)         # B6, B7: "10 times off"
OUTLIER_MIN_SIBLINGS = 3             # B6, B7: other items needed for a median
SHORT_TEXT_MIN_WORDS = 3             # B8: fewer distinct words is "very short"
LUMP_SHARE = Decimal("0.20")         # B9: share of lump-sum items, by count or by value
LUMP_MAX_SOURCES = 5                 # B9: lump-sum items quoted in the finding
TEXT_DOC_SHARE = Decimal("0.5")      # B8: share of positions with text a document needs
GAP_MIN_DIFFS = 5                    # B3: number steps a document needs for a gap check
QUOTE_MAX = 160                      # longest quote taken from an item's text
SNIPPET_CONTEXT = 60                 # characters kept on each side of a phrase

NOT_A_POSITION = ("heading", "preliminary_note")
NOT_IN_SUM = ("optional", "alternative")
SEVERITIES = ("high", "medium", "info")
SKEPTIC = {"status": "not_run",
           "note": "Base check by code (no model); the refute pass covers the X checks only."}
NO_TEXT_NOTE = " Ohne eigenen Text; zitiert ist der nächste Eintrag mit Text."
_ANCHORED = "_anchored"

# --- numbers ---------------------------------------------------------------
_GROUPED_DOTS = re.compile(r"^\d{1,3}(\.\d{3})+$")
_PLAIN_NUMBER = re.compile(r"^\d+(\.\d+)?$")


def to_decimal(value):
    """Exact decimal of a quantity or price, or None when there is no usable number.

    Contract v1 gives numbers. A text is read too, so a reader that passes the
    printed form does not break the checks: "1.234,56" and "1,234.56" (the last
    mark is the decimal mark), "12,5" (German decimal comma), "1.234" (dots
    that split groups of three digits are thousands marks), "1234.5".
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return Decimal(repr(value))
    if not isinstance(value, str):
        return None
    text = re.sub(r"[\s\u00a0'’]", "", value)
    sign = 1
    if text[:1] in ("+", "-"):
        sign = -1 if text[0] == "-" else 1
        text = text[1:]
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    elif _GROUPED_DOTS.match(text):
        text = text.replace(".", "")
    if not _PLAIN_NUMBER.match(text):
        return None
    try:
        return sign * Decimal(text)
    except InvalidOperation:
        return None


def number(record, key):
    return to_decimal(record.get(key))


# --- units -----------------------------------------------------------------
_UNIT_WORDS = {
    "st": "st", "stk": "st", "stck": "st", "stück": "st", "stueck": "st",
    "m": "m", "lfm": "m", "lfdm": "m",
    "m2": "m2", "qm": "m2",
    "m3": "m3", "cbm": "m3",
    "mm": "mm", "cm": "cm", "km": "km",
    "kg": "kg", "g": "g", "t": "t", "to": "t",
    "l": "l",
    "h": "h", "std": "h", "stunde": "h", "stunden": "h",
    "d": "d", "tag": "d", "tage": "d",
    "wo": "wo", "woche": "wo", "wochen": "wo",
    "mt": "mt", "mon": "mt", "monat": "mt", "monate": "mt",
    "jahr": "jahr", "jahre": "jahr",
    "psch": "psch", "pau": "psch", "pausch": "psch", "pauschal": "psch",
    "satz": "satz", "set": "set", "paar": "paar",
    "%": "%", "kw": "kw", "kwh": "kwh",
}
_COMPOUND_UNIT = re.compile(r"^(st|stk|stck|m|m2|m3|t|to|kg)(d|tag|wo|woche|mt|mon|monat|h)$")
LUMP_UNIT = "psch"


def clean_unit(unit):
    """The unit as written, lower case, without blanks and dots, ² and ³ as 2 and 3; "" when missing."""
    if not isinstance(unit, str):
        return ""
    text = unit.strip().lower().replace("²", "2").replace("³", "3").replace("^", "")
    return re.sub(r"[\s.]", "", text)


def canonical_unit(unit):
    """One name per known unit ("Stk", "St." and "Stck" give "st"); None when the unit is missing or not known."""
    text = clean_unit(unit)
    if text in _UNIT_WORDS:
        return _UNIT_WORDS[text]
    match = _COMPOUND_UNIT.match(text)
    if match:
        return "%s*%s" % (_UNIT_WORDS[match.group(1)], _UNIT_WORDS[match.group(2)])
    return None


def unit_key(unit):
    """Key for "the same unit": the canonical name, else the cleaned text."""
    return canonical_unit(unit) or clean_unit(unit)


# --- text ------------------------------------------------------------------
def full_text(record):
    """Normalized text of a record that a quote may cite (short and long text)."""
    return quotes.normalize(quotes.item_text(record))


def clip(text, limit=QUOTE_MAX):
    """Text cut to at most `limit` characters, at a blank where there is one."""
    if len(text) <= limit:
        return text
    cut = text.rfind(" ", 0, limit + 1)
    return text[:cut if cut > 0 else limit].rstrip()


def quote_of(record):
    """Quote for a finding about the whole record: its short text, else the
    start of its text; None when the record has no text. Never a price: the
    text fields are the only source."""
    text = full_text(record)
    if not text:
        return None
    head = quotes.normalize(record.get("short_text"))
    return clip(head if head and text.startswith(head) else text)


def snippet(text, start, end, context=SNIPPET_CONTEXT):
    """The words around text[start:end], cut at blanks; a substring of text."""
    left = max(0, start - context)
    if left > 0:
        blank = text.find(" ", left, start)
        left = blank + 1 if blank != -1 else start
    right = min(len(text), end + context)
    if right < len(text):
        blank = text.rfind(" ", end, right + 1)
        right = blank if blank != -1 else end
    return text[left:right].strip()


def words(text):
    """Distinct words of a text: runs of two or more letters or digits, case ignored."""
    return set(token.casefold() for token in re.findall(r"[^\W_]{2,}", text or ""))


# --- documents -------------------------------------------------------------
def item_no(record):
    value = record.get("item_no")
    return value if isinstance(value, str) else ""


def label(record):
    """German name of a record for explanation texts."""
    number_text = item_no(record)
    kind = record.get("kind")
    word = "Abschnitt" if kind == "heading" else "Vorbemerkung" if kind == "preliminary_note" else "Position"
    return "%s %s" % (word, number_text) if number_text else "%s ohne Nummer" % word


class Doc:
    """The records of one document, in file order."""

    def __init__(self, name, records):
        self.name = name
        self.records = records
        self.positions = [r for r in records if r.get("kind") not in NOT_A_POSITION]
        self.headings = [r for r in records if r.get("kind") == "heading"]
        self.notes = [r for r in records if r.get("kind") == "preliminary_note"]
        self._index = dict((id(record), index) for index, record in enumerate(records))

    def has_descriptions(self):
        """True when at least TEXT_DOC_SHARE of the positions have text. An offer
        file that carries prices and only a few bidder remarks has none."""
        with_text = sum(1 for r in self.positions if words(full_text(r)))
        return with_text > 0 and with_text >= TEXT_DOC_SHARE * len(self.positions)

    def anchor(self, record):
        """The nearest record with text: the record itself, else the one before it, else the one after it."""
        index = self._index[id(record)]
        for other in [record] + self.records[:index][::-1] + self.records[index + 1:]:
            if full_text(other):
                return other
        return None

    def source(self, record, quote=None):
        """A findings.json source for a record, or None when nothing can be quoted.

        A record without text is cited through the nearest record with text
        (a quote must stand in the cited item); the caller names the record
        itself in the explanation and make_finding() adds NO_TEXT_NOTE."""
        target = record
        if quote is None:
            target = self.anchor(record)
            if target is None:
                return None
            quote = quote_of(target)
        page = target.get("page")
        source = {"doc": self.name, "item_no": item_no(target),
                  "page": page if isinstance(page, int) and not isinstance(page, bool) else None,
                  "quote": quote}
        if target is not record:
            source[_ANCHORED] = True
        return source


def split_docs(items):
    """items.json records grouped by document, documents in order of first appearance.

    An entry that is not a record, or has no document name, cannot be cited and is left out."""
    groups = {}
    for record in items:
        if isinstance(record, dict) and isinstance(record.get("doc"), str) and record["doc"].strip():
            groups.setdefault(record["doc"], []).append(record)
    return [Doc(name, records) for name, records in groups.items()]


def in_section(record, section_no):
    """True when the record sits in the section with that number or below it; "" is the whole document."""
    if section_no == "":
        return True
    section = record.get("section")
    if not isinstance(section, str):
        section = item_no(record).rpartition(".")[0]
    return section == section_no or section.startswith(section_no + ".")


# --- results ---------------------------------------------------------------
class Outcome:
    """What one check says about one document."""

    def __init__(self, findings=None, applicable=True, notes=None):
        self.findings = findings or []
        self.applicable = applicable
        self.notes = notes or {}


NOT_APPLICABLE = Outcome(applicable=False)


def lower_severity(severity):
    index = SEVERITIES.index(severity)
    return SEVERITIES[min(index + 1, len(SEVERITIES) - 1)]


def make_finding(check, type_, severity, sources, explanation_de, question_de,
                 record=None, search_terms=()):
    """One findings.json record of contract v1 for a base check.

    sources: list from Doc.source(); entries that are None are left out, and a
    finding without any source is not built (returns None). record: the item
    the finding is about; it gives the exposure (quantity and unit, never a
    price) and lowers the severity by one level for an optional or alternative
    item, because such an item is not part of the contract sum.
    """
    given, sources, anchored = [s for s in sources if s], [], False
    for source in given:
        anchored = anchored or bool(source.get(_ANCHORED))
        source = dict((key, value) for key, value in source.items() if key != _ANCHORED)
        if source not in sources:
            sources.append(source)
    if not sources:
        return None
    if anchored:
        explanation_de += NO_TEXT_NOTE
    exposure = {"quantity": None, "unit": None}
    if record is not None:
        quantity = number(record, "quantity")
        unit = record.get("unit")
        exposure = {"quantity": float(quantity) if quantity is not None else None,
                    "unit": unit if isinstance(unit, str) and unit.strip() else None}
        if record.get("kind") in NOT_IN_SUM:
            severity = lower_severity(severity)
    doc = sources[0]["doc"]
    return {
        "id": ids.finding_id(check, sources), "check": check, "layer": "single_list",
        "type": type_, "severity": severity, "handover": [doc], "sources": sources,
        "lists_searched": [doc], "search_terms": list(search_terms),
        "explanation_de": explanation_de, "question_de": question_de,
        "exposure": exposure, "quotes_verified": False, "origin": "code",
        "skeptic": dict(SKEPTIC),
    }


def _join(texts):
    """Distinct sentences joined in order; NO_TEXT_NOTE once, at the end."""
    bodies, note = [], ""
    for text in texts:
        if text.endswith(NO_TEXT_NOTE):
            text, note = text[:-len(NO_TEXT_NOTE)], NO_TEXT_NOTE
        if text not in bodies:
            bodies.append(text)
    return " ".join(bodies) + note


def collect(findings):
    """Outcome from the findings of one check on one document.

    None entries (no quotable source) are counted as no_quote. Findings with
    the same id are merged into one: the id is built from the check, the
    cited items and the first quote, so two findings of a check share it when
    they cite the same item, which happens when items without text are cited
    through the same neighbour. The merged finding keeps every explanation
    and question, the highest severity, and an exposure only when it is the
    same for all; "merged" counts the findings that went into another one.
    """
    kept, by_id = [], {}
    for finding in findings:
        if finding is None:
            continue
        first = by_id.get(finding["id"])
        if first is None:
            by_id[finding["id"]] = finding
            kept.append(finding)
            continue
        first["explanation_de"] = _join([first["explanation_de"], finding["explanation_de"]])
        first["question_de"] = _join([first["question_de"], finding["question_de"]])
        if SEVERITIES.index(finding["severity"]) < SEVERITIES.index(first["severity"]):
            first["severity"] = finding["severity"]
        if finding["exposure"] != first["exposure"]:
            first["exposure"] = {"quantity": None, "unit": None}
        for term in finding["search_terms"]:
            if term not in first["search_terms"]:
                first["search_terms"].append(term)
    notes = {}
    missing = sum(1 for f in findings if f is None)
    if missing:
        notes["no_quote"] = missing
    if len(findings) - missing - len(kept):
        notes["merged"] = len(findings) - missing - len(kept)
    return Outcome(kept, notes=notes)


# --- "10 times off its siblings" (B6, B7) -----------------------------------
def outliers(doc, value_of):
    """Positions whose value is 10 times above or below the median of their siblings.

    Siblings: the other positions of the same section with the same unit and a
    value above zero; lump-sum items are left out. At least
    OUTLIER_MIN_SIBLINGS siblings are needed. Returns [(record, "high"|"low")].
    """
    groups = {}
    for record in doc.positions:
        value = value_of(record)
        key = unit_key(record.get("unit"))
        if value is None or value <= 0 or not key or key == LUMP_UNIT or record.get("kind") == "lump_sum":
            continue
        groups.setdefault((record.get("section") or "", key), []).append((record, value))
    found = []
    for members in groups.values():
        if len(members) <= OUTLIER_MIN_SIBLINGS:
            continue
        for index, (record, value) in enumerate(members):
            others = [v for i, (_, v) in enumerate(members) if i != index]
            median = statistics.median(others)
            if value >= OUTLIER_FACTOR * median:
                found.append((record, "high"))
            elif value * OUTLIER_FACTOR <= median:
                found.append((record, "low"))
    order = dict((id(record), index) for index, record in enumerate(doc.positions))
    return sorted(found, key=lambda pair: order[id(pair[0])])
