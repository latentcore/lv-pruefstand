"""Handover map of project 79-222 (W4, MASTER_PLAN §9).

A handover is a place where one trade's work ends and another trade's work
starts. The map says which lists each handover covers and shows, for each of
these lists, the places where the list names the other trade or the
handed-over work ("Vorleistung", "Folgeleistung", "bauseits", the other
trade's material or component).

The handovers and their search terms are written by hand in HANDOVERS below,
starting from the plan's candidate list (PLAN_CANDIDATES). The evidence is
found by code: `build_map` searches the terms in items.json, takes the quote
from the item text and keeps only quotes that pass pipeline/common/quotes.py.
A handover in which not every list has a place is not counted as a handover
with evidence; it stays in the file with its status.

    python -m pipeline.cross.handover_map              table of the committed map
    python -m pipeline.cross.handover_map --findings   which handover covers each finding
    python -m pipeline.cross.handover_map --build      rebuild handover_map.json from out/79-222/items.json

Prices are never read: the code uses doc, item_no, kind, page, short_text and
long_text of an item and nothing else.
"""
import argparse
import hashlib
import json
import os
import re
import sys

from pipeline.common import quotes

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAP_PATH = os.path.join(os.path.dirname(__file__), "handover_map.json")
ITEMS_PATH = os.path.join(ROOT, "out", "79-222", "items.json")
TEXT_DIR = os.path.join(ROOT, "cache", "79-222_text")
FINDINGS_PATH = os.path.join(os.path.dirname(__file__), "results", "79-222", "findings.json")

PROJECT = "79-222"
STATUS_EVIDENCE = "evidence"
STATUS_PARTIAL = "evidence not in every list"
STATUS_NONE = "no evidence in the lists"
STATUSES = (STATUS_EVIDENCE, STATUS_PARTIAL, STATUS_NONE)
ORIGIN_PLAN = "plan"
ORIGIN_LISTS = "lists"
SIGNALS = ("Vorleistung", "Folgeleistung", "Untergrund", "bauseits", "Text")
PRICE_KEYS = ("unit_price", "total")
ID_HEX_DIGITS = 6
QUOTE_REACH = 70
ANCHOR_SLACK = 120

# The candidates of MASTER_PLAN §9, line "Geçiş haritası adayları (W4)", in
# the plan's order. K6 to K9 are the "additional candidates (AI proposal)".
PLAN_CANDIDATES = {
    "K1": ["LV_18", "LV_14c", "LV_02", "LV_06", "LV_07", "LV_20"],
    "K2": ["LV_09", "LV_12", "LV_14b"],
    "K3": ["LV_00", "LV_15", "LV_15a"],
    "K4": ["LV_17", "LV_13", "LV_14", "LV_23"],
    "K5": ["LV_00", "LV_01", "LV_10", "LV_11"],
    "K6": ["LV_03", "LV_17", "LV_18"],
    "K7": ["LV_08", "LV_21", "LV_18"],
    "K8": ["LV_19", "LV_22", "LV_00", "LV_17"],
    "K9": ["LV_14a", "LV_00"],
}

# One entry per handover. "lists" are in work order where there is one
# (the list that hands over first). "terms" are regular expressions, searched
# case-sensitively in the normalized item text of that list; they name the
# other trade or the handed-over work. A list without terms cannot get
# evidence. "plan" is the plan candidate the handover comes from; None means
# the handover was added because the lists themselves name each other.
HANDOVERS = [
    # --- K1: screed, floor heating, floor coverings ---------------------
    {"name_de": "Estrich → Bodenbeläge (PVC, Kautschuk, Teppich)", "plan": "K1",
     "lists": ["LV_18", "LV_02", "LV_06", "LV_07", "LV_20"],
     "terms": {"LV_18": [r"Bodenbel[aä]g", r"Oberbel[aä]g", r"Kautschuk", r"Teppich", r"Vinyl", r"Textil"],
               "LV_02": [r"Estrich"], "LV_06": [r"Estrich"], "LV_07": [r"Estrich"], "LV_20": [r"Estrich"]}},
    {"name_de": "Fußbodenheizung → Estrich", "plan": "K1",
     "lists": ["LV_14c", "LV_18"],
     "terms": {"LV_14c": [r"Estrich"], "LV_18": [r"Fußbodenheizung", r"Heizungsbauer"]},
     "trades_without_list": ["Heizung"],
     "note": "LV_18 names a 'Heizungsbauer' and a 'Fußbodenheizung' under the screed; LV_14c is the "
             "Industriebodenheizung. No main heating list is among the 27 (plan §4), so the trade "
             "that LV_18 names may belong to a list that is missing."},
    # --- K2: roof --------------------------------------------------------
    {"name_de": "Porenbetondach → Dachabdichtung", "plan": "K2",
     "lists": ["LV_09", "LV_12"],
     "terms": {"LV_09": [r"Dachabdichtung", r"Dampfsperr", r"Dachdecker", r"Dachaufbau"],
               "LV_12": [r"Porenbeton"]}},
    {"name_de": "Dachabdichtung ↔ Dachentwässerung", "plan": "K2",
     "lists": ["LV_12", "LV_14b"],
     "terms": {"LV_12": [r"Dachabl[aä]uf", r"Dachentwässerung", r"Notüberl[aä]uf"],
               "LV_14b": [r"Dachabdichtung", r"Dachbahn", r"Dachhaut", r"bauseitigen Dachabl"]}},
    # --- K3: waterproofing of foundation and walls with the shell --------
    {"name_de": "Rohbau → Abdichtung Außenwände", "plan": "K3",
     "lists": ["LV_00", "LV_15"],
     "terms": {"LV_00": [r"Abdichtungsarbeiten-Außenwände", r"Außenabdichtung", r"Außenwand mit Abdichtung",
                         r"abgedichtete", r"abzudichtenden", r"Abdichtung mittels"],
               "LV_15": [r"Beton[a-z]*wände", r"Sohlplatte", r"bauseits"]}},
    {"name_de": "Rohbau → Abdichtung Bodenplatte Büro", "plan": "K3",
     "lists": ["LV_00", "LV_15a"],
     "terms": {"LV_00": [r"Abdichtungsarbeiten-Bodenplatte", r"Bodenabdichtung", r"Abdichtung an Bodeneinläufen",
                         r"Abdichtung Sockelbereich"],
               "LV_15a": [r"Bodenplatte", r"Betonboden"]}},
    # --- K4: drywall, electrical, plumbing -------------------------------
    {"name_de": "Trockenbau ↔ Elektro", "plan": "K4",
     "lists": ["LV_17", "LV_13"],
     "terms": {"LV_17": [r"Leuchte", r"Elektro", r"Steckdose", r"Schalter", r"Kabel"],
               "LV_13": [r"Hohlwand", r"Zwischendecke", r"Abhangdecke", r"abgehängte", r"Gipskarton", r"Trockenbau"]}},
    {"name_de": "Trockenbau ↔ Sanitär", "plan": "K4",
     "lists": ["LV_17", "LV_14"],
     "terms": {"LV_17": [r"Sanitär", r"Installationsebene"],
               "LV_14": [r"Trockenbau", r"Vorwand", r"Ständerwand", r"GK-"]}},
    {"name_de": "Trockenbau, Sanitär → Sanitärtrennwände", "plan": "K4",
     "lists": ["LV_17", "LV_14", "LV_23"],
     "terms": {"LV_17": [r"WC-Trenn", r"Sanitärtrennw", r"Trennwandanlage"],
               "LV_14": [r"Trennw[aä]nd", r"Kabine"],
               "LV_23": [r"TB-", r"Vorwände", r"Trockenbau"]}},
    # --- K5: precast parts with the shell --------------------------------
    {"name_de": "Rohbau ↔ Fertigteiltreppen", "plan": "K5",
     "lists": ["LV_00", "LV_01"],
     "terms": {"LV_00": [r"Fertigteiltreppe", r"Fertigteil-Treppe", r"Treppenl[aä]uf"],
               "LV_01": [r"UG-Sohle", r"Ortbeton", r"bauseit", r"Rohbau"]}},
    {"name_de": "Rohbau ↔ Fertigteilstützen und -binder", "plan": "K5",
     "lists": ["LV_00", "LV_10"],
     "terms": {"LV_00": [r"Fertigteilstütze", r"FT-Stütze", r"FT-Binder", r"FT-Satteldach", r"Köcher"],
               "LV_10": [r"Köcher", r"Fundament", r"Ortbeton", r"bauseit", r"Rohbau"]}},
    {"name_de": "Rohbau ↔ Fertigteil-Sandwichsockel", "plan": "K5",
     "lists": ["LV_00", "LV_11"],
     "terms": {"LV_00": [r"Sandwich", r"FT-Sockel", r"Sockelelement"],
               "LV_11": [r"Fundament", r"Ortbeton", r"bauseit", r"Rohbau", r"Bodenplatte"]}},
    # --- K6: painter with drywall and screed -----------------------------
    {"name_de": "Trockenbau → Maler", "plan": "K6",
     "lists": ["LV_17", "LV_03"],
     "terms": {"LV_17": [r"malerfertig", r"Anstrich", r"Endbeschichtung", r"Maler"],
               "LV_03": [r"\bGK\b", r"Gipskarton", r"Trockenbau", r"Abhangdecke"]}},
    {"name_de": "Estrich → Maler (Bodenanstrich)", "plan": "K6",
     "lists": ["LV_18", "LV_03"],
     "terms": {"LV_18": [r"[Aa]nstrich"],
               "LV_03": [r"Estrich", r"Fußboden", r"[Ss]taubbind"]}},
    # --- K7: tiles and natural stone with screed -------------------------
    {"name_de": "Estrich → Fliesen", "plan": "K7",
     "lists": ["LV_18", "LV_08"],
     "terms": {"LV_18": [r"keramisch", r"Fliese"], "LV_08": [r"Estrich"]}},
    {"name_de": "Estrich → Naturstein", "plan": "K7",
     "lists": ["LV_18", "LV_21"],
     "terms": {"LV_18": [r"Naturstein"], "LV_21": [r"Estrich"]}},
    # --- K8: doors with shell and drywall --------------------------------
    {"name_de": "Rohbau, Trockenbau → Sektionaltore und Stahltüren", "plan": "K8",
     "lists": ["LV_00", "LV_17", "LV_19"],
     "terms": {"LV_00": [r"\bTore\b", r"Türöffnung", r"Tür-/", r"Stahltür"],
               "LV_17": [r"Türöffnung", r"Türzarge"],
               "LV_19": [r"Stahlbeton", r"Rohbau", r"Mauerwerk", r"Trockenbau", r"Gipskarton", r"Ständerw", r"bauseit"]}},
    {"name_de": "Rohbau, Trockenbau → Schreiner (Innentüren)", "plan": "K8",
     "lists": ["LV_00", "LV_17", "LV_22"],
     "terms": {"LV_00": [r"Türöffnung", r"Tür-/", r"Holztür"],
               "LV_17": [r"Türöffnung", r"Türzarge", r"Holztür"],
               "LV_22": [r"Stahlbeton", r"Rohbau", r"Mauerwerk", r"Trockenbau", r"Gipskarton", r"Ständerw", r"bauseit"]}},
    # --- K9: concrete core activation with the shell ---------------------
    {"name_de": "Rohbau ↔ Betonkernaktivierung", "plan": "K9",
     "lists": ["LV_00", "LV_14a"],
     "terms": {"LV_00": [r"Betonkern", r"Bauteilaktivierung", r"Einlegearbeiten TGA"],
               "LV_14a": [r"Rohbau", r"bauseitiger unterer Bewehrung", r"Betonier"]},
     "note": "LV_00 names the other trade only as 'TGA'."},
    # --- added from the lists: both sides name each other -----------------
    {"name_de": "Rohbau → Dachabdichtung", "plan": None,
     "lists": ["LV_00", "LV_12"],
     "terms": {"LV_00": [r"Lichtkuppel", r"Attika"],
               "LV_12": [r"Ortbeton", r"\bStb\b", r"Stahlbeton", r"Öffnung in Dachkonstruktion"]}},
    {"name_de": "Rohbau → Dachentwässerung (Kernbohrungen)", "plan": None,
     "lists": ["LV_00", "LV_14b"],
     "terms": {"LV_00": [r"Kernbohrung(?:en)? in Stb", r"Anfahrtpauschale Kernbohrungen"], "LV_14b": [r"Kernbohrung"]}},
    {"name_de": "Stahltüren und Zargen → Maler", "plan": None,
     "lists": ["LV_19", "LV_03"],
     "terms": {"LV_19": [r"grundiert", r"[Bb]eschicht", r"lackier"], "LV_03": [r"Tür", r"Zarge"]}},
    {"name_de": "Elektro ↔ Estrich, Bodenbelag (Bodentanks, Potentialausgleich)", "plan": None,
     "lists": ["LV_13", "LV_18", "LV_20"],
     "terms": {"LV_13": [r"Estrich", r"Bodenbelag"],
               "LV_18": [r"Bodentank", r"Bodendose", r"Unterflur", r"Elektro"],
               "LV_20": [r"Potentialausgleich"]}},
    {"name_de": "Fertigteiltreppen, Rohbau → Natursteinbelag", "plan": None,
     "lists": ["LV_01", "LV_00", "LV_21", "LV_08"],
     "terms": {"LV_01": [r"Naturstein"], "LV_00": [r"Naturstein"],
               "LV_21": [r"Treppenanlage", r"Treppenbelag", r"Stahlbetonpodest"],
               "LV_08": [r"Treppenlauf aus Stahlbeton", r"Treppenpodest", r"Treppenstufe"]}},
    # --- added from the lists: only one side names the other --------------
    {"name_de": "Fertigteilbinder → Porenbetondach", "plan": None,
     "lists": ["LV_10", "LV_09"],
     "terms": {"LV_10": [r"Dachplatte", r"Porenbetondach", r"Dachelement"], "LV_09": [r"Binder", r"Stb\.-FT"]}},
    {"name_de": "Dachabdichtung → Trockenbau (Laibung Lichtkuppel)", "plan": None,
     "lists": ["LV_12", "LV_17"],
     "terms": {"LV_12": [r"Gipskarton", r"Trockenbau"], "LV_17": [r"Lichtkuppel", r"Dachfläche", r"Dachöffnung"]}},
]


def handover_id(lists):
    """Stable id of a handover: "G-" + first 6 hex digits of sha1 over the
    sorted doc ids joined with "|". The same lists give the same id in every
    run, in any order."""
    names = sorted(set(lists))
    if not names:
        raise ValueError("a handover needs at least one list for its id")
    digest = hashlib.sha1("|".join(names).encode("utf-8")).hexdigest()
    return "G-" + digest[:ID_HEX_DIGITS]


# "Vorleistung: x", "Folgeleistung (baus.) x" (the reader accepts both forms) and "Untergrund: x".
_LABEL = re.compile(r"\b(?:(Vorleistung|Folgeleistung)\b(?:\s*\([^)]*\))?\s*:?|(Untergrund)\s*:)")
_BAUSEITS = re.compile(r"[Bb]auseit|\bbaus\.")
_SIGNAL_RANK = dict((name, rank) for rank, name in enumerate(SIGNALS))


def _whole_words(text, start, end):
    while start > 0 and text[start - 1] != " ":
        start -= 1
    while end < len(text) and text[end] != " ":
        end += 1
    return start, end


def quote_around(text, start, end, reach_left=QUOTE_REACH, reach_right=QUOTE_REACH):
    """Return (quote, start of the quote in text) for the match text[start:end]:
    the match widened to whole words plus up to `reach_left` characters before
    and `reach_right` after it, cut at spaces. `text` must be normalized
    (single spaces)."""
    start, end = _whole_words(text, start, end)
    left = max(0, start - reach_left)
    if left > 0:
        space = text.find(" ", left, start)
        left = start if space < 0 else space + 1
    right = min(len(text), end + reach_right)
    if right < len(text):
        space = text.rfind(" ", end, right)
        right = end if space < 0 else space
    return text[left:right], left


def signal_of(quote, offset):
    """How the quote names the other side. `offset` is where the matched term
    starts in the quote. A label ("Vorleistung:", "Folgeleistung:",
    "Untergrund:") counts when it is the last label before the term."""
    label = None
    for match in _LABEL.finditer(quote, 0, offset):
        label = match
    if label is not None and ":" not in quote[label.end():offset]:
        return label.group(1) or label.group(2)
    if _BAUSEITS.search(quote):
        return "bauseits"
    return "Text"


def _is_page(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _fields(item):
    return [quotes.normalize(item.get("short_text")), quotes.normalize(item.get("long_text"))]


_WORD = re.compile(r"\S+")


def page_spans(item, page_texts):
    """Lay the long text of an item on its pages.

    `page_texts` is a list of (page, normalized page text) from the item's
    first page on. Returns [(page, start, end)]: the part [start:end] of the
    normalized long text stands on that page. [] for an item without long
    text. None when the text cannot be laid on the pages (the caller then
    falls back to `fit_to_page`).

    On the first page the long text must start right after the item's number
    and short text (within ANCHOR_SLACK characters), so that a similar item
    on the same page is not taken for this one.
    """
    short, text = _fields(item)
    if not page_texts or page_texts[0][0] != item.get("page"):
        return None
    first = page_texts[0][1]
    anchor = -1 if short else 0
    number = item.get("item_no")
    # The print shows "11.3.30.   short text"; a marker line may stand between number and short text.
    for start_text in ([number + ". " + short, number + " " + short] if number else []) + [short]:
        found = first.find(start_text) if short else -1
        if found >= 0:
            anchor = found + len(start_text)
            break
    if anchor < 0:
        return None
    words = [(match.start(), match.end()) for match in _WORD.finditer(text)]
    spans, done = [], 0
    for index, (page, page_text) in enumerate(page_texts):
        def stands(count):
            found = page_text.find(text[words[done][0]:words[done + count - 1][1]], anchor if index == 0 else 0)
            return found >= 0 and (index > 0 or not short or found - anchor <= ANCHOR_SLACK)
        low, high = 0, len(words) - done
        while low < high:
            middle = (low + high + 1) // 2
            if stands(middle):
                low = middle
            else:
                high = middle - 1
        if low == 0:
            if index == 0 and done == 0 and words:
                continue
            break
        spans.append((page, words[done][0], words[done + low - 1][1]))
        done += low
        if done == len(words):
            break
    return spans if done == len(words) else None


def fit_to_page(quote, offset, end, page_texts):
    """Fit a quote to one page. `quote[offset:end]` is the matched term (whole
    words); `page_texts` is a list of (page, text) in page order.

    Returns (quote, offset, page) for the first page that holds the whole
    quote. Otherwise the quote is shortened word by word, never cutting the
    term, and the page that keeps the longest part wins. None when no page
    holds the term.
    """
    for page, text in page_texts:
        if quotes.quote_in_text(quote, text):
            return quote, offset, page
    words = [(match.start(), match.end()) for match in _WORD.finditer(quote)]
    inside = [index for index, (start, stop) in enumerate(words) if start < end and stop > offset]
    best = None
    for page, text in page_texts:
        first, last = inside[0], inside[-1]
        if not quotes.quote_in_text(quote[words[first][0]:words[last][1]], text):
            continue
        while first > 0 and quotes.quote_in_text(quote[words[first - 1][0]:words[last][1]], text):
            first -= 1
        while last + 1 < len(words) and quotes.quote_in_text(quote[words[first][0]:words[last + 1][1]], text):
            last += 1
        left, right = words[first][0], words[last][1]
        if best is None or right - left > len(best[0]):
            best = (quote[left:right], offset - left, page)
    return best


def _locate(text, field_no, match, item, spans, page_texts):
    """(quote, where the term starts in the quote, page) for one hit."""
    start, end = _whole_words(text, match.start(), match.end())
    if spans is not None:
        regions = [(item["page"], 0, len(text))] if field_no == 0 else spans
        for page, low, high in regions:
            if low <= start and end <= high:
                quote, left = quote_around(text[low:high], match.start() - low, match.end() - low)
                if quotes.quote_in_text(quote, dict(page_texts)[page]):
                    return quote, match.start() - low - left, page
    quote, left = quote_around(text, match.start(), match.end())
    fitted = fit_to_page(quote, start - left, end - left, page_texts) if page_texts else None
    if fitted is not None:
        return fitted[0], fitted[1] + match.start() - start, fitted[2]
    return quote, match.start() - left, item["page"]


def find_places(items, doc, terms, pages=None):
    """Search the terms in the items of one list (items without a page number
    cannot be cited and are left out). One place per item: the hit with the
    strongest signal, then the earliest.

    With `pages` ({(doc, page): text}) the quote is taken from the part of
    the item that stands on one page, and the place gets that page: an item
    may run over a page break (`page_spans`, else `fit_to_page`). Without
    `pages` the place gets the item's first page.

    Returns (places, dropped): dropped counts hits whose quote does not pass
    the quote check of pipeline/common/quotes.py.
    """
    patterns = [(term, re.compile(term)) for term in terms]
    own = [item for item in items if item.get("doc") == doc and _is_page(item.get("page"))]
    places, dropped = [], 0
    for index, item in enumerate(own):
        hits = [(field_no, term, match, text) for field_no, text in enumerate(_fields(item))
                for term, pattern in patterns for match in pattern.finditer(text)]
        if not hits:
            continue
        page_texts, spans = [], None
        if pages:
            last_page = max(item["page"], own[index + 1]["page"]) if index + 1 < len(own) else item["page"] + 1
            page_texts = [(number, pages[(doc, number)]) for number in range(item["page"], last_page + 1)
                          if (doc, number) in pages]
            spans = page_spans(item, [(number, quotes.normalize(text)) for number, text in page_texts])
        found = []
        for field_no, term, match, text in hits:
            quote, offset, page = _locate(text, field_no, match, item, spans, page_texts)
            signal = signal_of(quote, offset)
            found.append((_SIGNAL_RANK[signal], field_no, match.start(), term, signal, quote, page))
        _, _, _, term, signal, quote, page = min(found, key=lambda hit: hit[:3])
        place = {"doc": doc, "item_no": item.get("item_no"), "kind": item.get("kind"), "page": page,
                 "quote": quote, "term": term, "signal": signal}
        if quotes.source_verified(place, own, pages):
            places.append(place)
        else:
            dropped += 1
    return places, dropped


def status_of(lists, lists_not_in_set, evidence):
    """(status, lists without evidence). A handover has evidence only when
    every list it names is among the given lists and has at least one place."""
    with_evidence = set(place["doc"] for place in evidence)
    missing = [doc for doc in lists if doc not in with_evidence]
    if not with_evidence:
        return STATUS_NONE, missing
    if missing or lists_not_in_set:
        return STATUS_PARTIAL, missing
    return STATUS_EVIDENCE, missing


def build_map(items, pages=None, handovers=None, plan_candidates=None, project=PROJECT):
    """Build the map from items.json records. Returns (map, dropped quotes)."""
    handovers = HANDOVERS if handovers is None else handovers
    plan_candidates = PLAN_CANDIDATES if plan_candidates is None else plan_candidates
    in_set = sorted(set(item["doc"] for item in items if item.get("doc")))
    out, dropped_total = [], 0
    for spec in handovers:
        lists = [doc for doc in spec["lists"] if doc in in_set]
        not_in_set = [doc for doc in spec["lists"] if doc not in in_set]
        terms = spec.get("terms") or {}
        evidence = []
        for doc in lists:
            places, dropped = find_places(items, doc, terms.get(doc) or [], pages)
            evidence.extend(places)
            dropped_total += dropped
        status, missing = status_of(lists, not_in_set, evidence)
        out.append({
            "id": handover_id(spec["lists"]),
            "name_de": spec["name_de"],
            "origin": ORIGIN_PLAN if spec.get("plan") else ORIGIN_LISTS,
            "plan_candidate": spec.get("plan"),
            "lists": lists,
            "lists_not_in_set": not_in_set,
            "trades_without_list": list(spec.get("trades_without_list") or []),
            "status": status,
            "lists_without_evidence": missing,
            "terms": dict((doc, list(terms.get(doc) or [])) for doc in lists),
            "evidence": evidence,
            "note": spec.get("note") or "",
        })
    candidates = []
    for key in sorted(plan_candidates):
        mine = [h for h in out if h["plan_candidate"] == key]
        named = set(doc for h in mine for doc in h["lists"] + h["lists_not_in_set"])
        candidates.append({
            "candidate": key,
            "lists": list(plan_candidates[key]),
            "lists_not_in_set": [doc for doc in plan_candidates[key] if doc not in in_set],
            "handovers": [h["id"] for h in mine],
            "lists_in_no_handover": [doc for doc in plan_candidates[key] if doc not in named],
        })
    return {"project": project, "lists_in_set": in_set, "plan_candidates": candidates, "handovers": out}, dropped_total


def _price_keys(value, path="map"):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in PRICE_KEYS:
                yield "%s: key %s is not allowed" % (path, key)
            for error in _price_keys(child, "%s.%s" % (path, key)):
                yield error
    elif isinstance(value, list):
        for index, child in enumerate(value):
            for error in _price_keys(child, "%s[%d]" % (path, index)):
                yield error


def _is_text(value):
    return isinstance(value, str) and bool(value.strip())


def _is_text_list(value):
    return isinstance(value, list) and all(_is_text(entry) for entry in value) and len(set(value)) == len(value)


def _handover_errors(handover, where, in_set):
    errors = []
    if not isinstance(handover, dict):
        return ["%s: not an object" % where]
    for key in ("id", "name_de", "origin", "plan_candidate", "lists", "lists_not_in_set", "trades_without_list",
                "status", "lists_without_evidence", "terms", "evidence", "note"):
        if key not in handover:
            errors.append("%s: key %s is missing" % (where, key))
    if errors:
        return errors
    for key in ("lists", "lists_not_in_set", "trades_without_list", "lists_without_evidence"):
        if not _is_text_list(handover[key]):
            errors.append("%s: %s must be a list of different non-empty strings" % (where, key))
    if not isinstance(handover["terms"], dict) or not isinstance(handover["evidence"], list):
        errors.append("%s: terms must be an object and evidence a list" % where)
    if errors:
        return errors
    lists, outside = handover["lists"], handover["lists_not_in_set"]
    if not _is_text(handover["name_de"]):
        errors.append("%s: name_de is empty" % where)
    if not isinstance(handover["note"], str):
        errors.append("%s: note must be a string" % where)
    if not lists and not outside:
        errors.append("%s: names no list" % where)
    elif handover["id"] != handover_id(lists + outside):
        errors.append("%s: id %r is not the stable id %s" % (where, handover["id"], handover_id(lists + outside)))
    for doc in lists:
        if doc not in in_set:
            errors.append("%s: %s is in lists but not among the lists of the set" % (where, doc))
    for doc in outside:
        if doc in in_set or doc in lists:
            errors.append("%s: %s is in lists_not_in_set but is a list of the set" % (where, doc))
    if handover["origin"] == ORIGIN_PLAN:
        if not _is_text(handover["plan_candidate"]):
            errors.append("%s: origin plan needs a plan_candidate" % where)
    elif handover["origin"] == ORIGIN_LISTS:
        if handover["plan_candidate"] is not None:
            errors.append("%s: origin lists must have plan_candidate null" % where)
    else:
        errors.append("%s: origin %r is unknown" % (where, handover["origin"]))
    for doc, terms in handover["terms"].items():
        if doc not in lists:
            errors.append("%s: terms for %s, which is not one of its lists" % (where, doc))
        if not isinstance(terms, list) or not all(_is_text(term) for term in terms):
            errors.append("%s: terms of %s must be a list of non-empty strings" % (where, doc))
            continue
        for term in terms:
            try:
                re.compile(term)
            except re.error:
                errors.append("%s: term %r of %s is not a regular expression" % (where, term, doc))
    places_ok = True
    for index, place in enumerate(handover["evidence"]):
        here = "%s evidence[%d]" % (where, index)
        if not isinstance(place, dict):
            errors.append("%s: not an object" % here)
            places_ok = False
            continue
        problems = []
        if place.get("doc") not in lists:
            problems.append("doc %r is not one of the handover's lists" % (place.get("doc"),))
        if not isinstance(place.get("item_no"), str):
            problems.append("item_no must be a string")
        if not _is_text(place.get("kind")):
            problems.append("kind is empty")
        page = place.get("page")
        if not _is_page(page):
            problems.append("page must be a whole number from 1")
        if not _is_text(place.get("quote")):
            problems.append("quote is empty")
        if place.get("signal") not in SIGNALS:
            problems.append("signal %r is unknown" % (place.get("signal"),))
        doc_terms = handover["terms"].get(place.get("doc"))
        if not isinstance(doc_terms, list) or place.get("term") not in doc_terms:
            problems.append("term %r is not a term of its list" % (place.get("term"),))
        if problems:
            places_ok = False
        errors.extend("%s: %s" % (here, problem) for problem in problems)
    if handover["status"] not in STATUSES:
        errors.append("%s: status %r is unknown" % (where, handover["status"]))
    elif places_ok:
        status, missing = status_of(lists, outside, handover["evidence"])
        if handover["status"] != status:
            errors.append("%s: status is %r but the evidence gives %r" % (where, handover["status"], status))
        if handover["lists_without_evidence"] != missing:
            errors.append("%s: lists_without_evidence is %r but the evidence gives %r"
                          % (where, handover["lists_without_evidence"], missing))
    return errors


def validate_map(data):
    """Return the list of errors of a handover map; empty when it is valid."""
    if not isinstance(data, dict):
        return ["map: not an object"]
    errors = []
    if not _is_text(data.get("project")):
        errors.append("map: project is empty")
    in_set = data.get("lists_in_set")
    if not _is_text_list(in_set):
        errors.append("map: lists_in_set must be a list of different non-empty strings")
        in_set = []
    handovers = data.get("handovers")
    if not isinstance(handovers, list):
        return errors + ["map: handovers must be a list"]
    seen = {}
    for index, handover in enumerate(handovers):
        where = "handover[%d]" % index
        errors.extend(_handover_errors(handover, where, in_set))
        if isinstance(handover, dict) and isinstance(handover.get("id"), str):
            if handover["id"] in seen:
                errors.append("%s: id %s is already used by handover[%d]" % (where, handover["id"], seen[handover["id"]]))
            seen.setdefault(handover["id"], index)
    candidates = data.get("plan_candidates")
    if not isinstance(candidates, list):
        errors.append("map: plan_candidates must be a list")
    else:
        for index, candidate in enumerate(candidates):
            where = "plan_candidates[%d]" % index
            if not isinstance(candidate, dict) or not _is_text(candidate.get("candidate")):
                errors.append("%s: needs a candidate name" % where)
                continue
            for key in ("lists", "lists_not_in_set", "handovers", "lists_in_no_handover"):
                if not isinstance(candidate.get(key), list):
                    errors.append("%s: %s must be a list" % (where, key))
            for ref in candidate.get("handovers") or []:
                if ref not in seen:
                    errors.append("%s: handover %r is not in the map" % (where, ref))
    errors.extend(_price_keys(data))
    return errors


def load_map(path=MAP_PATH):
    """Read a handover map file and return it. Raises ValueError with every
    error when the file does not have the form `build_map` writes."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    errors = validate_map(data)
    if errors:
        raise ValueError("%s: %d error(s): %s" % (path, len(errors), "; ".join(errors)))
    return data


def read_pages(text_dir):
    """{(doc, page): text} from the text cache of pipeline/pdf; {} when the folder is missing."""
    pages = {}
    if not os.path.isdir(text_dir):
        return pages
    for name in sorted(os.listdir(text_dir)):
        if name.endswith(".txt"):
            with open(os.path.join(text_dir, name), encoding="utf-8") as handle:
                pages.update(quotes.pages_from_text(name[:-4], handle.read()))
    return pages


def unverified_places(data, items, pages=None):
    """The evidence places whose quote does not pass pipeline/common/quotes.py,
    as (handover id, place)."""
    return [(handover["id"], place) for handover in data["handovers"] for place in handover["evidence"]
            if not quotes.source_verified(place, items, pages)]


def counts(data):
    """Numbers of the map: handovers by status and evidence places."""
    by_status = dict((status, 0) for status in STATUSES)
    for handover in data["handovers"]:
        by_status[handover["status"]] += 1
    return {"handovers": len(data["handovers"]), "by_status": by_status,
            "evidence_places": sum(len(handover["evidence"]) for handover in data["handovers"])}


def _table(rows):
    widths = [max(len(row[column]) for row in rows) for column in range(len(rows[0]))]
    lines = []
    for index, row in enumerate(rows):
        lines.append("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())
        if index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return lines


def format_table(data):
    """The map as text: handover, lists (with the evidence places of each list),
    number of evidence places, status."""
    rows = [("id", "handover", "lists (evidence places)", "places", "status")]
    for handover in data["handovers"]:
        per_list = dict((doc, 0) for doc in handover["lists"])
        for place in handover["evidence"]:
            per_list[place["doc"]] += 1
        cells = ["%s (%d)" % (doc, per_list[doc]) for doc in handover["lists"]]
        cells += ["%s (not among the %d lists)" % (doc, len(data["lists_in_set"])) for doc in handover["lists_not_in_set"]]
        rows.append((handover["id"], handover["name_de"], ", ".join(cells), str(len(handover["evidence"])), handover["status"]))
    numbers = counts(data)
    lines = _table(rows)
    lines.append("")
    lines.append("project %s, %d lists; %d handovers in the file" % (data["project"], len(data["lists_in_set"]), numbers["handovers"]))
    lines.append("with evidence in every list: %d; %s: %d; %s: %d; evidence places: %d" % (
        numbers["by_status"][STATUS_EVIDENCE], STATUS_PARTIAL, numbers["by_status"][STATUS_PARTIAL],
        STATUS_NONE, numbers["by_status"][STATUS_NONE], numbers["evidence_places"]))
    for handover in data["handovers"]:
        if handover["trades_without_list"]:
            lines.append("%s names a trade without a list among the %d: %s" % (
                handover["id"], len(data["lists_in_set"]), ", ".join(handover["trades_without_list"])))
    for candidate in data.get("plan_candidates") or []:
        if candidate["lists_in_no_handover"] or candidate["lists_not_in_set"]:
            lines.append("plan candidate %s: in no handover: %s; not among the lists: %s" % (
                candidate["candidate"], ", ".join(candidate["lists_in_no_handover"]) or "-",
                ", ".join(candidate["lists_not_in_set"]) or "-"))
    return "\n".join(lines)


COVERED = "covered"
COVERED_WEAK = "covered by a handover without evidence in every list"
PARTLY = "partly covered"
NOT_COVERED = "not covered"
SINGLE_LIST = "single list"
COVERAGE_RESULTS = (COVERED, COVERED_WEAK, PARTLY, NOT_COVERED, SINGLE_LIST)


def cover_findings(findings, data):
    """Say for each finding which handovers of the map cover its `handover` lists.

    covered: a handover with evidence in every list holds all lists of the
    finding. covered by a handover without evidence in every list: only such
    handovers hold them all. partly covered: no handover holds them all, but
    some hold two or more of them. single list: the finding names fewer than
    two lists, so it lies on no handover between lists.
    """
    rows = []
    for finding in findings:
        lists = []
        for doc in finding.get("handover") or []:
            if doc not in lists:
                lists.append(doc)
        row = {"id": finding.get("id"), "lists": lists, "handovers": [], "result": SINGLE_LIST}
        if len(lists) >= 2:
            wanted = set(lists)
            full = [h for h in data["handovers"] if wanted <= set(h["lists"])]
            strong = [h for h in full if h["status"] == STATUS_EVIDENCE]
            part = [h for h in data["handovers"] if len(wanted & set(h["lists"])) >= 2]
            if strong:
                row["result"], row["handovers"] = COVERED, [h["id"] for h in strong]
            elif full:
                row["result"], row["handovers"] = COVERED_WEAK, [h["id"] for h in full]
            elif part:
                row["result"], row["handovers"] = PARTLY, [h["id"] for h in part]
            else:
                row["result"] = NOT_COVERED
        rows.append(row)
    return rows


def coverage_counts(rows):
    numbers = dict((result, 0) for result in COVERAGE_RESULTS)
    for row in rows:
        numbers[row["result"]] += 1
    return numbers


def format_coverage(rows):
    table = [("finding", "lists", "result", "handovers")]
    for row in rows:
        table.append((str(row["id"]), ", ".join(row["lists"]), row["result"], ", ".join(row["handovers"]) or "-"))
    numbers = coverage_counts(rows)
    lines = _table(table)
    lines.append("")
    lines.append("%d findings: %s" % (len(rows), "; ".join("%s: %d" % (result, numbers[result]) for result in COVERAGE_RESULTS)))
    return "\n".join(lines)


def _read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def write_map(data, path=MAP_PATH):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
        handle.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pipeline.cross.handover_map",
                                     description="Handover map of project 79-222: table, findings coverage, rebuild.")
    parser.add_argument("--map", default=MAP_PATH, help="map file to read or, with --build, to write")
    parser.add_argument("--build", action="store_true", help="search the evidence in items.json and write the map")
    parser.add_argument("--items", default=ITEMS_PATH, help="items.json of the project (for --build)")
    parser.add_argument("--text-dir", default=TEXT_DIR, help="text cache with page markers (for --build; gives exact pages)")
    parser.add_argument("--findings", nargs="?", const=FINDINGS_PATH, default=None, metavar="FILE",
                        help="print which handover covers each finding (default file: the committed findings)")
    args = parser.parse_args(argv)
    if args.build:
        if not os.path.exists(args.items):
            print("items.json not found: %s (build it as AGENTS.md says)" % args.items, file=sys.stderr)
            return 2
        items = _read_json(args.items)
        pages = read_pages(args.text_dir)
        data, dropped = build_map(items, pages)
        errors = validate_map(data)
        if errors:
            print("the built map is not valid: %s" % "; ".join(errors), file=sys.stderr)
            return 1
        write_map(data, args.map)
        print("written: %s (quotes dropped by the quote check: %d; page texts %s)" % (
            args.map, dropped, "used" if pages else "not found, pages are the items' first pages"))
    try:
        data = load_map(args.map)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    if args.findings:
        print(format_coverage(cover_findings(_read_json(args.findings), data)))
    else:
        print(format_table(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
