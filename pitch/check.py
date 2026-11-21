"""Checks on the pitch sources and the built deck (W10, plan K12 and §15).

The tests call these functions; `python -m pitch.build` calls them too and
stops when one of them reports something.

A number is a run of digits, or a number word from two on ("two", "zwei",
"hundred", "dozen", "half", "twice"). "one", "first", "second" and "both" are
not checked: they are also plain words ("one building", "a second agent").
Identifiers are not numbers: the project name, GAEB 90, the names of lists,
checks, plan decisions, packages and findings (IDENTIFIERS below).
"""
import re
from html.parser import HTMLParser

from pitch import numbers

IDENTIFIERS = re.compile(
    r"\b79-222\b|\bGAEB 90\b|\bLV[ _]\d+[a-z]?\b|\b[BKW]\d+[a-z]?\b|§\s?\d+|\b[XS]\d?-[0-9a-f]{6}\b|\bGate \d\b")
NOTES_MARK = "<!-- notes -->"
_NUMBERING = re.compile(r"^(#+ +\d+ +· +|\s*\d+\. +)", re.MULTILINE)
DIGITS = re.compile(r"\d+(?:[.,:/x]\d+)*")
NUMBER_WORDS = re.compile(
    r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\w+teen|twenty|thirty|forty|fifty|sixty|seventy|"
    r"eighty|ninety|hundreds?|thousands?|millions?|dozens?|half|twice|"
    r"zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|elf|zwölf|\w+zehn|zwanzig|dreißig|vierzig|fünfzig|sechzig|"
    r"siebzig|achtzig|neunzig|hundert\w*|tausend\w*|dutzend|halb\w*|doppelt so)\b", re.IGNORECASE)
# K12: no claim of speed or saving, no share, no money, unless it is a number of numbers.json.
CLAIMS = re.compile(
    r"\b(faster|quicker|schneller|saves?|saved|saving|savings|spart|gespart|einsparung\w*|percent|prozent)\b|%|€|\bEUR\b|\beuros?\b",
    re.IGNORECASE)
MONEY = re.compile(r"€|\bEUR\b|\beuros?\b", re.IGNORECASE)
OPTIONAL_ITEM = re.compile(r"optional item|Bedarfsposition|Eventualposition", re.IGNORECASE)
SLIDE_WORD = re.compile(r"[^\W_]")
MAX_SLIDES = 7
MAX_WORDS = 40
MIN_FONT_PX = 24
NETWORK = re.compile(r"https?:|//[\w-]+\.\w|@import|@font-face|<link\b|<script\b|<iframe\b|\bsrc=\"(?!data:)|url\(\s*['\"]?(?!data:)",
                     re.IGNORECASE)


def statements(source):
    """The part of a text source that is spoken or shown as a statement: everything before the notes mark."""
    return source.partition(NOTES_MARK)[0]


def without_numbering(source):
    """A text source without the numbers of its headings ("## 1 · ...") and list entries ("1. ...")."""
    return _NUMBERING.sub("", source)


def without_placeholders(text):
    return numbers.PLACEHOLDER.sub(" ", text)


def stray_numbers(text):
    """Numbers a source text states itself instead of naming a key of numbers.json."""
    plain = IDENTIFIERS.sub(" ", without_placeholders(text))
    return DIGITS.findall(plain) + [match.group(0) for match in NUMBER_WORDS.finditer(plain)]


def claims(text):
    """Words of speed, saving, share or money that stand in a text outside a {{number}}.

    "{{expert_eur}} euros" and "{{twin_accuracy}} percent" are allowed: the unit of a number of numbers.json."""
    plain = re.sub(r"\{\{[^}]*\}\}\s*(euros?|percent|prozent|%|€)", " ", text, flags=re.IGNORECASE)
    return [match.group(0) for match in CLAIMS.finditer(without_placeholders(plain))]


def unknown_numbers(text, data):
    """{{keys}} of a text that numbers.json does not hold."""
    return sorted({name for name, _ in numbers.placeholders(text)
                   if not name.startswith("@") and name not in data["numbers"]})


def network_references(text):
    return sorted({match.group(0) for match in NETWORK.finditer(text)})


def font_sizes(css):
    """Every font-size of the style sheet as (value, unit)."""
    return [(float(value), unit) for value, unit in re.findall(r"font(?:-size)?\s*:[^;]*?(\d+(?:\.\d+)?)(px|pt|em|rem|%|vw|vh)", css)]


class _Deck(HTMLParser):
    """Text of the built deck, per slide, split into: quoted from the findings
    file, numbers of numbers.json, and the rest."""

    VOID = {"img", "br", "meta", "hr", "input", "link"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.slides = []
        self.stack = []  # (tag, kind) with kind in: slide, findings, quote, number, skip, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        kind = None
        classes = (attrs.get("class") or "").split()
        if tag == "section" and "slide" in classes:
            kind = "slide"
            self.slides.append({"id": attrs.get("id"), "rest": [], "findings": [], "quotes": [], "numbers": [],
                                "boxes": [], "images": 0, "missing_shots": 0, "marks": []})
        elif tag in ("style", "script", "title"):
            kind = "skip"
        elif tag == "blockquote":
            kind = "quote"
            if self.slides:
                self.slides[-1]["quotes"].append({"source": attrs.get("data-source"), "text": ""})
        elif attrs.get("data-from") == "findings":
            kind = "findings"
        elif "data-n" in attrs:
            kind = "number"
            if self.slides:
                self.slides[-1]["numbers"].append({"key": attrs["data-n"], "text": ""})
        if self.slides:
            if tag == "img":
                self.slides[-1]["images"] += 1
            if "shot-missing" in classes:
                self.slides[-1]["missing_shots"] += 1
                kind = "box"
            if "mark" in classes and tag == "p":
                self.slides[-1]["marks"].append("")
                kind = kind or "mark"
        if tag not in self.VOID:
            self.stack.append((tag, kind))

    def handle_endtag(self, tag):
        while self.stack:
            open_tag, _ = self.stack.pop()
            if open_tag == tag:
                break

    def handle_data(self, data):
        kinds = [kind for _, kind in self.stack if kind]
        if "skip" in kinds or "slide" not in kinds:
            return
        slide = self.slides[-1]
        if "mark" in kinds:
            slide["marks"][-1] += data
        if "box" in kinds:
            slide["boxes"].append(data)  # a grey box in place of a screenshot: an instruction, not slide text
        elif "quote" in kinds:
            slide["quotes"][-1]["text"] += data
        elif "number" in kinds:
            slide["numbers"][-1]["text"] += data
        elif "findings" in kinds:
            slide["findings"].append(data)
        else:
            slide["rest"].append(data)


def read_deck(deck_html):
    """The slides of a built deck: a list of dicts with id, rest (text that is not a
    quote, not taken from the findings file and not a number), findings (list, item
    number, page of a quote), quotes, numbers, images, missing_shots, marks."""
    parser = _Deck()
    parser.feed(deck_html)
    parser.close()
    for slide in parser.slides:
        slide["rest"] = " ".join(" ".join(slide["rest"]).split())
        slide["findings"] = " ".join(" ".join(slide["findings"]).split())
        slide["marks"] = [" ".join(mark.split()) for mark in slide["marks"]]
    return parser.slides


def slide_words(slide):
    """Words of a slide outside its quotes: its own text, its numbers, and the list,
    item number and page lines of the quotes."""
    text = " ".join([slide["rest"], slide["findings"]] + [number["text"] for number in slide["numbers"]])
    return [token for token in text.split() if SLIDE_WORD.search(token)]


def allowed_texts(key, entry):
    """What a slide may show for one number: its value (also as a word, where it has one) or its placeholder."""
    texts = {numbers.shown(key, entry)}
    if entry["status"] == "measured":
        for style in ("word", "Word", "wort", "Wort"):
            try:
                texts.add(numbers.shown(key, entry, style))
            except numbers.NumberError:
                pass
    return texts


def deck_problems(deck_html, data):
    """Everything that breaks a rule of the deck; an empty list when it is fine."""
    problems = []
    slides = read_deck(deck_html)
    if not 1 <= len(slides) <= MAX_SLIDES:
        problems.append("the deck has %d slides; the limit is %d" % (len(slides), MAX_SLIDES))
    for found in network_references(deck_html):
        problems.append("the deck names an outside resource: %s" % found)
    for index, slide in enumerate(slides, 1):
        name = "slide %d (%s)" % (index, slide["id"])
        for found in stray_numbers(slide["rest"]):
            problems.append("%s shows a number that is not in numbers.json: %s" % (name, found))
        for number in slide["numbers"]:
            entry = data["numbers"].get(number["key"])
            if entry is None:
                problems.append("%s: number %s is not in numbers.json" % (name, number["key"]))
            elif number["text"] not in allowed_texts(number["key"], entry):
                problems.append("%s: %s shows %r" % (name, number["key"], number["text"]))
        everything = " ".join([slide["rest"], slide["findings"]] + [quote["text"] for quote in slide["quotes"]]
                              + [number["text"] for number in slide["numbers"]])
        if MONEY.search(everything):
            problems.append("%s shows a price or an amount" % name)
        for found in claims(slide["rest"]):
            problems.append("%s makes a claim that is not measured: %s" % (name, found))
        count = len(slide_words(slide))
        if count > MAX_WORDS:
            problems.append("%s has %d words outside quotes; the limit is %d" % (name, count, MAX_WORDS))
    return problems
