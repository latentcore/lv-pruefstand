"""Text normalization and the quote check (MASTER_PLAN §8).

A finding may only cite text that stands in its source. Quote and source go
through the same normalization; the quote must then be an exact, case-sensitive
substring of the text of the cited item or of the cited page. A finding with a
quote that is not found is dropped and counted; that count is measurement M6.
"""
import re
import unicodedata

SOFT_HYPHEN = "\u00ad"

# A hyphen between a word character at a line end and a word character at the
# start of the next line.
_LINE_END_HYPHEN = re.compile(r"(?<=\w)-[ \t]*\r?\n[ \t]*(?=\w)")
_SOFT_HYPHEN_BREAK = re.compile(SOFT_HYPHEN + r"[ \t]*\r?\n[ \t]*")
_WHITESPACE = re.compile(r"\s+")
_PAGE_MARKER = re.compile(r"^=== PAGE (\d+) ===\s*$")


def normalize(text):
    """Return text in the form used for quote checks and stable ids.

    Steps, in this order: Unicode NFKC; soft hyphens removed (one at a line
    end joins the two lines); a hyphen at a line end removed together with the
    line break ("Wärme-\\ndämmung" -> "Wärmedämmung"); every run of whitespace
    collapsed to one space; ends stripped. None gives "".

    The line-end rule is the plain one of §8 and does not look at the words:
    "Ein-\\nund Ausbau" becomes "Einund Ausbau". Source and quote get the same
    treatment, so a quote copied with its line breaks, or stored in normalized
    form, is found; a quote typed as "Ein- und Ausbau" for such a source is not.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _SOFT_HYPHEN_BREAK.sub("", text).replace(SOFT_HYPHEN, "")
    text = _LINE_END_HYPHEN.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


def quote_in_text(quote, text):
    """True when the normalized quote is not empty and stands in the normalized text."""
    needle = normalize(quote)
    return bool(needle) and needle in normalize(text)


def item_text(item):
    """Text of one items.json record that a quote may cite."""
    return "\n".join([item.get("short_text") or "", item.get("long_text") or ""])


def pages_from_text(doc, text):
    """Split extracted text with "=== PAGE n ===" marker lines (the layout of
    pipeline/pdf's text cache) into {(doc, n): page text}."""
    pages = {}
    current = None
    for line in text.split("\n"):
        match = _PAGE_MARKER.match(line)
        if match:
            current = (doc, int(match.group(1)))
            pages[current] = []
        elif current is not None:
            pages[current].append(line)
    return {key: "\n".join(lines) for key, lines in pages.items()}


def source_verified(source, items, pages=None):
    """True when the source's quote stands in the cited item or on the cited page.

    items: items.json records. pages: optional {(doc, page): page text}.
    """
    quote = source.get("quote")
    for item in items:
        if item.get("doc") == source.get("doc") and item.get("item_no") == source.get("item_no"):
            if quote_in_text(quote, item_text(item)):
                return True
    if pages:
        page_text = pages.get((source.get("doc"), source.get("page")))
        if page_text is not None and quote_in_text(quote, page_text):
            return True
    return False


def finding_verified(finding, items, pages=None):
    """True when the finding has at least one source and every quote is found."""
    sources = finding.get("sources") or []
    return bool(sources) and all(source_verified(s, items, pages) for s in sources)


def filter_findings(findings, items, pages=None):
    """Split findings into (kept, dropped) by the quote check.

    Kept findings are copies with quotes_verified set to True. The input is
    not changed. len(dropped) is the number to report (M6).
    """
    kept, dropped = [], []
    for finding in findings:
        if finding_verified(finding, items, pages):
            kept.append(dict(finding, quotes_verified=True))
        else:
            dropped.append(finding)
    return kept, dropped
