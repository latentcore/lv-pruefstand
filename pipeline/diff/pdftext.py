"""Which item titles of a GAEB file stand in the text of a PDF (W13, T5).

For a PDF layout without a reader. No item is read from the PDF: the short
text of every position of the GAEB file is searched in the page texts
(`pdftotext -layout`, the same extraction as pipeline/pdf). Both sides are
normalized as pipeline/common/quotes.py does. A title is searched three
ways, from strict to loose, because the print breaks a title where it wants
and the anonymizer ran on the PDF and on the list separately.

Result per item, the first that applies:
    found_as_written  the title stands on a page letter for letter: both
                      texts normalized as quotes.py does, blanks and line
                      breaks left out (the print breaks a title inside a
                      word, "24kN/" and "m3"), nothing else ignored; a
                      placeholder in the title must stand there as the same
                      placeholder
    found_layout      not as written, but letter for letter once hyphens
                      are left out of both texts too
    found_anonymized  it stands there only when anonymization placeholders
                      are allowed to differ. The rule, as stands_in() applies
                      it (characters are counted without blanks and hyphens):
                      1. A placeholder of the title stands for a placeholder
                         or for 1 to MAX_SPAN characters of the page; so one
                         at the beginning or end of the title stands for
                         whatever the page holds there, also a placeholder.
                      2. A placeholder of the page stands for a placeholder
                         of the title, or for 1 to MAX_SPAN characters and
                         placeholders of it, but never for the first or the
                         last character of the title: otherwise every title
                         that agrees with the page up to a placeholder would
                         count as found.
                      3. One piece of the title stands on the page letter
                         for letter and the rest is laid to both sides of it
                         by 1 and 2: a whole run between two placeholders
                         (of MIN_RUN characters or more, or the longest
                         run when all are shorter), or
                         the first or the last ANCHOR characters of a run
                         longer than twice ANCHOR.
                      4. A title that begins with a placeholder joined to a
                         word ("[..]-Blindflansch DN 50") is also found
                         where one placeholder of the page stands for that
                         placeholder and its word together and the rest of
                         the title (MIN_RUN characters or more) follows by
                         1 and 2 (page: "[..] DN 50"). The same at the end
                         of a title.
                      So a title whose first or last word is plain and is a
                      placeholder on the page is not found; a title whose
                      first or last word is or holds a placeholder is found
                      also where the page holds a placeholder there.
    not_found
    not_searchable    the title has fewer than MIN_LENGTH characters outside
                      placeholders; it would be found anywhere

"in_order" is the longest row of found titles whose pages do not go back
when the items are taken in file order: a list that is printed in the PDF
gives a long row, titles that stand there by chance do not.

This says how much of the list's wording is in the PDF. It does not check
quantities or units; that needs a reader for the layout.
"""
import collections
import os
import sys

from pipeline.common import quotes
from pipeline.diff import compare
from pipeline.diff import text as textcmp
from pipeline.lv import model

MIN_LENGTH = 5
ANCHOR = 6
MIN_RUN = 3
WILD = "\ue000"  # one placeholder in a search string (private use character)

FOUND_AS_WRITTEN = "found_as_written"
FOUND_LAYOUT = "found_layout"
FOUND_ANONYMIZED = "found_anonymized"
NOT_FOUND = "not_found"
NOT_SEARCHABLE = "not_searchable"
FOUND = (FOUND_AS_WRITTEN, FOUND_LAYOUT, FOUND_ANONYMIZED)
CLASSES = FOUND + (NOT_FOUND, NOT_SEARCHABLE)

# One page: its number; its text normalized and without blanks; that
# without hyphens too; and that with each placeholder as WILD.
Page = collections.namedtuple("Page", "number written loose wild")


def written_string(text):
    """The normalized text without blanks (normalize() has made every line
    break a blank); placeholders stay as they are written."""
    return quotes.normalize(text).replace(" ", "")


def loose_string(text):
    """written_string() without hyphens."""
    return written_string(text).replace("-", "")


def search_string(text):
    """The text without blanks and hyphens, each placeholder as WILD."""
    return "".join(WILD if token is None else token for token in textcmp.loose_tokens(text))


def joined_words(text):
    """(head, tail) of a title: when it begins with a placeholder that is
    joined to a word, the number of characters of that word in the search
    string ("[..]-Blindflansch DN 50": 12); the same for a placeholder the
    title ends with. 0 when there is no such placeholder, when it is a word
    of its own, or when the word holds another placeholder."""
    text = quotes.normalize(text)
    found = list(textcmp.PLACEHOLDER.finditer(text))
    head = tail = ""
    if found and found[0].start() == 0:
        head = text[found[0].end():].split(" ")[0]
    if found and found[-1].end() == len(text):
        tail = text[:found[-1].start()].split(" ")[-1]
    return tuple(0 if textcmp.has_placeholder(word) else len(word.replace("-", ""))
                 for word in (head, tail))


def page_strings(pdf_path):
    """The pages of a PDF file as Page tuples."""
    pdf_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pdf")
    if pdf_dir not in sys.path:
        sys.path.insert(0, pdf_dir)
    import pdfio
    return without_form_feed_page(pages_of_text(pdfio.extract_text(pdf_path)))


def without_form_feed_page(pages):
    """pdftotext ends every page with a form feed, and pdfio.extract_text
    writes a page marker for the empty text after the last one. That is not
    a page of the PDF: drop it. An empty page before it stays."""
    if pages and not pages[-1].written:
        return pages[:-1]
    return pages


def pages_of_text(text):
    """Page tuples of text with "=== PAGE n ===" marker lines."""
    pages = quotes.pages_from_text("", text)
    return [Page(number, written_string(pages[("", number)]), loose_string(pages[("", number)]),
                 search_string(pages[("", number)])) for _, number in sorted(pages)]


def _consumes(pattern, text):
    """True when the whole pattern can be laid on the start of the text."""
    size, length = len(pattern), len(text)
    if not size:
        return True
    seen = {(0, 0)}
    stack = [(0, 0)]
    while stack:
        i, j = stack.pop()
        if i == size:
            return True
        if j == length:
            continue
        steps = []
        wild_p, wild_t = pattern[i] == WILD, text[j] == WILD
        if wild_p == wild_t and (wild_p or pattern[i] == text[j]):
            steps.append((i + 1, j + 1))
        if wild_p:
            steps.extend((i + 1, j + k) for k in range(1, min(textcmp.MAX_SPAN, length - j) + 1))
        if wild_t:
            # never up to the end of the pattern: see the module text
            steps.extend((i + k, j + 1) for k in range(1, min(textcmp.MAX_SPAN, size - i - 1) + 1))
        for step in steps:
            if step not in seen:
                seen.add(step)
                stack.append(step)
    return False


def _anchors(pattern):
    """[(offset, plain piece)] of the pattern to look up with str.find: every
    plain run, and the two ends of a long one (the page may hold a
    placeholder in its middle)."""
    out = []
    offset = 0
    pieces = pattern.split(WILD)
    # a title of short runs between placeholders ("DN [..] mm [..] St") is
    # looked up by its longest run, however short
    shortest = min(MIN_RUN, max(len(piece) for piece in pieces))
    for piece in pieces:
        if piece and len(piece) >= shortest:
            out.append((offset, piece))
            if len(piece) > 2 * ANCHOR:
                out.append((offset, piece[:ANCHOR]))
                out.append((offset + len(piece) - ANCHOR, piece[-ANCHOR:]))
        offset += len(piece) + 1
    return sorted(out, key=lambda anchor: -len(anchor[1]))


def stands_in(pattern, page, head=0, tail=0):
    """True when the pattern stands in the page with placeholders allowed
    to differ (the rule is in the module text). Both are search strings;
    head and tail are the joined_words() of the title."""
    return (_stands_by_piece(pattern, page) or _stands_behind_placeholder(pattern, page, head)
            or _stands_behind_placeholder(pattern[::-1], page[::-1], tail))


def _stands_behind_placeholder(pattern, page, head):
    """Point 4 of the rule: one placeholder of the page stands for the
    placeholder the pattern begins with and the `head` characters of its
    word; the rest of the pattern follows. For the end of a title both
    strings are given reversed."""
    rest = pattern[1 + head:]
    if not head or len(rest.replace(WILD, "")) < MIN_RUN:
        return False
    reach = len(rest) + textcmp.MAX_SPAN * rest.count(WILD)
    at = page.find(WILD)
    while at >= 0:
        if _consumes(rest, page[at + 1:at + 1 + reach]):
            return True
        at = page.find(WILD, at + 1)
    return False


def _stands_by_piece(pattern, page):
    """Points 1 to 3 of the rule."""
    if WILD not in pattern and pattern in page:
        return True
    if WILD not in pattern and WILD not in page:
        return False
    for offset, piece in _anchors(pattern):
        before = pattern[:offset][::-1]
        after = pattern[offset + len(piece):]
        reach_before = len(before) + textcmp.MAX_SPAN * before.count(WILD)
        reach_after = len(after) + textcmp.MAX_SPAN * after.count(WILD)
        at = page.find(piece)
        while at >= 0:
            end = at + len(piece)
            if _consumes(before, page[max(0, at - reach_before):at][::-1]) \
                    and _consumes(after, page[end:end + reach_after]):
                return True
            at = page.find(piece, at + 1)
    return False


def _in_order(page_lists, page_numbers):
    """Length of the longest row of entries, in the order given, whose pages
    never go back; every entry picks one of its pages."""
    best = dict((number, 0) for number in page_numbers)
    for hits in page_lists:
        new = dict(best)
        for page in hits:
            new[page] = max(new[page], 1 + max(best[p] for p in page_numbers if p <= page))
        best = new
    return max(best.values()) if best else 0


def titles_in_pages(items, pages, show=5):
    """Search the short text of every position in the pages (Page tuples).
    Returns counts per class, the item numbers per class other than
    "found_as_written", the in-order count, the pages on which found titles
    stand, the first `show` items with number, title, class and first page,
    and under "placeholder_title" the numbers of the "found_anonymized"
    items after whose item number a page holds a placeholder (the printed
    title begins with one)."""
    counts = dict((cls, 0) for cls in CLASSES)
    numbers = dict((cls, []) for cls in CLASSES[1:])
    page_numbers = [page.number for page in pages]
    hit_lists = []
    hit_pages = set()
    first = []
    classes = {}
    placeholder_title = []
    for item in compare.positions(items):
        written = written_string(item.get("short_text"))
        loose = loose_string(item.get("short_text"))
        pattern = search_string(item.get("short_text") or "")
        hits = []
        if len(pattern.replace(WILD, "")) < MIN_LENGTH:
            cls = NOT_SEARCHABLE
        else:
            as_written = [page.number for page in pages if written in page.written]
            layout = [page.number for page in pages if loose in page.loose]
            # every page counts for the order, also one where the title
            # stands only with a placeholder
            head, tail = joined_words(item.get("short_text"))
            hits = sorted(set(as_written + layout
                              + [page.number for page in pages
                                 if stands_in(pattern, page.wild, head, tail)]))
            cls = (FOUND_AS_WRITTEN if as_written else FOUND_LAYOUT if layout
                   else FOUND_ANONYMIZED if hits else NOT_FOUND)
            number = search_string(item["item_no"]) + WILD
            if cls == FOUND_ANONYMIZED and any(number in page.wild for page in pages):
                placeholder_title.append(item["item_no"])
        counts[cls] += 1
        classes[model.item_no_key(item["item_no"])] = cls
        if cls != FOUND_AS_WRITTEN:
            numbers[cls].append(item["item_no"])
        if hits:
            hit_lists.append(hits)
            hit_pages.update(hits)
        if len(first) < show:
            first.append({"item_no": item["item_no"], "title": compare.title(item),
                          "result": cls, "page": hits[0] if hits else None})
    found = sum(counts[cls] for cls in FOUND)
    return {"pages": len(pages), "items": sum(counts.values()),
            "searchable": sum(counts.values()) - counts[NOT_SEARCHABLE],
            "found_total": found, "counts": counts, "numbers": numbers,
            "placeholder_title": placeholder_title,
            "in_order": _in_order(hit_lists, page_numbers),
            "first_page": min(hit_pages) if hit_pages else None,
            "last_page": max(hit_pages) if hit_pages else None,
            "first": first, "classes": classes}
