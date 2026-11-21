"""Text comparison for twins and stages (W13).

Both texts go through pipeline.common.quotes.normalize(). The result is one
of seven classes:

    equal             the normalized texts are the same
    layout            the same when blanks, line breaks and hyphens are
                      ignored (one file breaks a line where the other does
                      not; normalize() joins "Ein-\nund" to "Einund")
    anonymized_both   every difference is an anonymization placeholder that
                      stands against a placeholder (written differently)
    anonymized_one    as above, and at least one placeholder stands against
                      plain text of the other file
    marks             one of the classes above holds once the square brackets
                      and the marks "[TA11", "[TB11" are left out, with
                      which a GAEB 90 file writes a text supplement into the
                      text
    start             one text is the start of the other (placeholders are
                      allowed to differ as above)
    differs           anything else

The anonymized classes and "start" also ignore blanks, line breaks and
hyphens when the strict comparison fails.

The two "anonymized" classes mean: the files differ only where the organizer's
anonymizer wrote a placeholder. What the placeholder hides is not known, so
this is neither "equal" nor a reader error; it is reported as its own class.

Placeholder forms, all read from the organizer files:
    [PERSON_118]  [PERSON_0000118]   category, "_", digits, in brackets
    PERSON_097    TELEFON_084        the same without brackets
    PER000115     TEL00009   PER89   first three letters of the category and
                                     digits (fixed-width GAEB 90 files: the
                                     placeholder is as long as the word)
    P060                             one or two letters of the category and
                                     three or more digits that start with 0
                                     (a four-letter word); without the 0 it
                                     would look like "PE100", so "P123" is
                                     not taken as a placeholder
    ###                              three or more "#" (one file writes it
                                     where its twin has a plain word)
The anonymizer ran per file: the same word can be a placeholder in one file
and plain text in the other, the number of one name differs between files,
and a placeholder can cover more words in one file than in the other. So a
placeholder may stand for up to MAX_SPAN characters or placeholders of the
other text; the numbers of two placeholders are not compared.
"""
import heapq
import re

from pipeline.common.quotes import normalize

CATEGORIES = ("ADRESSE", "EMAIL", "FIRMA", "KENNZEICHEN", "NUMMER", "ORT",
              "PERSON", "PROJEKT", "TELEFON", "URL")
MAX_SPAN = 60
_NAMES = "|".join(CATEGORIES)
_SHORT = "|".join(sorted(set(name[:3] for name in CATEGORIES)))
_SHORTER = "|".join(sorted(set(name[:size] for name in CATEGORIES for size in (1, 2))))
PLACEHOLDER = re.compile(
    r"\[[A-ZÄÖÜ]{2,}_\d+\]"
    r"|(?<![\w\[])(?:%s)_\d+(?!\w)"
    r"|(?<![\w\[])(?:%s)\d{2,}(?!\w)"
    r"|(?<![\w\[])(?:%s)0\d{2,}(?!\w)"
    r"|#{3,}" % (_NAMES, _SHORT, _SHORTER))

EQUAL = "equal"
LAYOUT = "layout"
ANONYMIZED_BOTH = "anonymized_both"
ANONYMIZED_ONE = "anonymized_one"
MARKS = "marks"
START = "start"
DIFFERS = "differs"
CLASSES = (EQUAL, LAYOUT, ANONYMIZED_BOTH, ANONYMIZED_ONE, MARKS, START, DIFFERS)
# The classes that say "the same text as far as the files let us see".
SAME = (EQUAL, LAYOUT, ANONYMIZED_BOTH, ANONYMIZED_ONE)

_WILD = None  # a placeholder in a token list


def is_placeholder(text):
    """True when the whole text is one anonymization placeholder."""
    return bool(PLACEHOLDER.fullmatch((text or "").strip()))


def has_placeholder(text):
    return bool(PLACEHOLDER.search(text or ""))


def _tokens(text):
    """The text as a list: one entry per character, None for a placeholder."""
    out = []
    end = 0
    for match in PLACEHOLDER.finditer(text):
        out.extend(text[end:match.start()])
        out.append(_WILD)
        end = match.end()
    out.extend(text[end:])
    return out


def loose_tokens(text):
    """The normalized text as a list of characters without blanks and
    hyphens; None stands for a placeholder."""
    return _loose(_tokens(normalize(text)))


_MARK = re.compile(r"\[T[AB]\d\d|[\[\]]")


def without_marks(text):
    """The normalized text without square brackets and supplement marks;
    placeholders keep their brackets."""
    text = normalize(text)
    out = []
    end = 0
    for match in PLACEHOLDER.finditer(text):
        out.append(_MARK.sub("", text[end:match.start()]))
        out.append(match.group())
        end = match.end()
    out.append(_MARK.sub("", text[end:]))
    return normalize("".join(out))


def _loose(tokens):
    """The token list without blanks and hyphens."""
    return [token for token in tokens if token is _WILD or token not in " -"]


def _align(a, b):
    """Walk both token lists from the start. A character must meet the same
    character; a placeholder meets one placeholder (cost 0) or 1 to MAX_SPAN
    entries of the other list (cost 1). Returns (cost of the cheapest full
    alignment or None, cost of the cheapest alignment that uses up one list
    and not the other, or None)."""
    n, m = len(a), len(b)
    best = {(0, 0): 0}
    heap = [(0, 0, 0)]
    full = None
    start = None
    while heap:
        _, i, j = heapq.heappop(heap)
        cost = best[(i, j)]
        if i == n or j == m:
            if i == n and j == m:
                full = cost if full is None else min(full, cost)
            else:
                start = cost if start is None else min(start, cost)
            continue
        steps = []
        if a[i] is _WILD and b[j] is _WILD:
            steps.append((i + 1, j + 1, 0))
        elif a[i] is not _WILD and b[j] is not _WILD:
            if a[i] == b[j]:
                steps.append((i + 1, j + 1, 0))
        # A placeholder must not swallow the end of the other text while its
        # own text goes on: that would make any two texts a "start".
        if a[i] is _WILD:
            first = 2 if b[j] is _WILD else 1
            for k in range(first, min(MAX_SPAN, m - j) + 1):
                if j + k < m or i + 1 == n:
                    steps.append((i + 1, j + k, 1))
        if b[j] is _WILD:
            first = 2 if a[i] is _WILD else 1
            for k in range(first, min(MAX_SPAN, n - i) + 1):
                if i + k < n or j + 1 == m:
                    steps.append((i + k, j + 1, 1))
        for ni, nj, extra in steps:
            new = cost + extra
            if best.get((ni, nj), new + 1) > new:
                if (ni, nj) not in best:
                    heapq.heappush(heap, (ni + nj, ni, nj))
                best[(ni, nj)] = new
    return full, start


def classify(text_a, text_b):
    """Class of two texts (see the module text). Both must be non-empty after
    normalization; an empty text is "missing" and is not compared here."""
    a, b = normalize(text_a), normalize(text_b)
    if not a or not b:
        raise ValueError("classify() needs two non-empty texts")
    found = _classify(a, b)
    if found in (START, DIFFERS):
        bare_a, bare_b = without_marks(a), without_marks(b)
        if bare_a and bare_b and (bare_a, bare_b) != (a, b) and (
                bare_a == bare_b or _classify(bare_a, bare_b) in SAME):
            return MARKS
    return found


def _classify(a, b):
    if a == b:
        return EQUAL
    tokens_a, tokens_b = _tokens(a), _tokens(b)
    loose_a, loose_b = _loose(tokens_a), _loose(tokens_b)
    if loose_a == loose_b and _WILD not in loose_a:
        return LAYOUT
    if _WILD not in loose_a and _WILD not in loose_b:
        size = min(len(loose_a), len(loose_b))
        return START if size and loose_a[:size] == loose_b[:size] else DIFFERS
    start = None
    for pair in ((tokens_a, tokens_b), (loose_a, loose_b)):
        full, start_cost = _align(*pair)
        if full is not None:
            return ANONYMIZED_ONE if full else ANONYMIZED_BOTH
        if start_cost is not None:
            start = start_cost
    return START if start is not None else DIFFERS
