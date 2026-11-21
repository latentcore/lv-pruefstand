"""Base checks on the description text: B8, B11, B12."""
import re

from pipeline.base import core
from pipeline.base.core import NOT_APPLICABLE

# B11: the dictionary of MASTER_PLAN §7, each phrase with its spelling variants.
# (plan wording, pattern, severity)
VAGUE_PHRASES = (
    ("nach Angabe der Bauleitung", r"nach\s+Angaben?\s+der\s+Bauleitung", "medium"),
    ("nach Erfordernis", r"nach\s+Erfordernis(?:sen)?\b", "medium"),
    ("ggf.", r"(?<![\w.])ggf\.|\bgegebenenfalls\b", "info"),
    ("ca.", r"(?<![\w.])ca\.|\bcirca\b", "info"),
    ("soweit erforderlich", r"\bsoweit\s+erforderlich\b", "medium"),
    ("bauseits", r"\bbauseits\b|\bbauseitig\w*", "medium"),
    ("komplett", r"\bkomplett(?:e[rnms]?)?\b|(?<![\w.])kompl\.|(?<![\w.])kpl\.", "info"),
    ("einschl. aller Nebenleistungen",
     r"(?:\beinschl\.|\beinschlie(?:ß|ss)lich\b|\binkl\.|\binklusive\b)\s*aller\s+Nebenleistungen", "medium"),
)
_VAGUE = tuple((label, re.compile(pattern, re.IGNORECASE), severity) for label, pattern, severity in VAGUE_PHRASES)

# B12
EQUIVALENT = re.compile(r"(?i)(?:\boder|\bod\.|\bo\.)\s*(?:gleichwertig\w*|gleichw\.|glw\.)")
_TRADEMARK = re.compile(r"[^\W_][\w/-]*(?:\s?®|\((?:R|r|TM|tm)\))")
_TM_WORD = re.compile(r"([^\W_][\w/-]*)(\s?)™")  # in the raw text: normalization turns the sign into "TM"
_MARKER = re.compile(
    r"(?i)(?P<own>\b(?:angebotene[sr]?|angeb\.|gewählte[sr]?|gew\.|gelieferte[sr]?|eingebaute[sr]?)\s+)?"
    r"(?P<word>\b(?:leit|richt)?fabrikate?\b|\bfabr\.|\bhersteller\b|\bherst\.|\berzeugnis\b|\bprodukt\b|\bmarke\b)"
    r"(?P<link>(?:\s*(?:/|und|u\.)?\s*(?:Typ|Hersteller|Fabrikat|Produkt|Modell|Serie|System)\b)*"
    r"(?:\s+der\s+Planung)?)\s*(?P<colon>[:=])?\s*")
_NAME = re.compile(r"[\"'„“”‚‘’»«]?(?P<name>(?=[\w.&+/-]*[^\W\d_])[^\W_][\w.&+/-]*)")
# "for example" between the marker word and the name
_EXAMPLE = re.compile(r"(?i)(?:z\.\s?B\.|z\.\s?B(?![\w.-])|zB\.?(?![\w-])|zum\s+Beispiel\b|bspw\.?(?![\w-])"
                      r"|beispielsweise\b)\s*[:,]?\s*")
# the organizer's stand-in for a name it took out of the text
_TOKEN = re.compile(r"[\"'„“”‚‘’»«]?(?P<name>\[(?:PERSON|FIRMA)_\d+\])")
_FILL_IN = re.compile(r"\s*[\"'„“”‚‘’»«]?\s*(?:[._…]\s?){2,}")
_NOT_A_NAME = frozenset("""
    nach wahl des der die das dem den vom von an ag bieter bieters auftragnehmer auftragnehmers
    auftraggeber auftraggebers siehe wie oder und laut lt gem gemäß frei freigestellt angabe angaben
    typ planung ist sind wird werden einzutragen eintragen angeben anzugeben z.b zb bzw nur mit ohne
    für bei zu zur zum im in auf aus hat haben muss müssen darf dürfen kann können sowie inkl einschl
    vorschrift vorschriften richtlinie richtlinien zulassung nachweis nachweise
""".split())


def b8(doc):
    """B8: empty or very short description of a position.

    Not applicable to a document whose positions mostly have no text (an offer
    file with prices only): there the description is a field the document
    does not have.
    """
    if not doc.has_descriptions():
        return NOT_APPLICABLE
    findings = []
    for record in doc.positions:
        count = len(core.words(core.full_text(record)))
        name = core.label(record)
        if count == 0:
            findings.append(core.make_finding(
                "B8", "description_empty", "high", [doc.source(record)],
                "Die %s hat keine Beschreibung." % name,
                "Welche Leistung ist mit der %s gemeint?" % name, record=record))
        elif count < core.SHORT_TEXT_MIN_WORDS:
            findings.append(core.make_finding(
                "B8", "description_short", "medium", [doc.source(record)],
                "Die Beschreibung der %s besteht aus weniger als %d Wörtern."
                % (name, core.SHORT_TEXT_MIN_WORDS),
                "Was genau umfasst die Leistung der %s (Art, Ausführung, Abmessungen)?" % name,
                record=record))
    return core.collect(findings)


def _text_records(doc):
    return [r for r in doc.records if r.get("kind") != "heading" and core.full_text(r)]


def b11(doc):
    """B11: the plan's dictionary of vague phrases, in positions and preliminary notes."""
    records = _text_records(doc)
    if not records:
        return NOT_APPLICABLE
    findings = []
    for record in records:
        text = core.full_text(record)
        hits, sources, severity = [], [], "info"
        for label, pattern, level in _VAGUE:
            match = pattern.search(text)
            if not match:
                continue
            hits.append(label)
            if level == "medium":
                severity = "medium"
            if not any(match.group(0) in source["quote"] for source in sources):
                sources.append(doc.source(record, core.snippet(text, match.start(), match.end())))
        if hits:
            listed = ", ".join("«%s»" % label for label in hits)
            name = core.label(record)
            findings.append(core.make_finding(
                "B11", "vague_phrase", severity, sources,
                "Die %s enthält unbestimmte Formulierungen: %s. Art oder Umfang der Leistung "
                "sind damit nicht eindeutig beschrieben." % (name, listed),
                "Was ist in der %s mit %s gemeint: welche Art und welcher Umfang der Leistung sind geschuldet?"
                % (name, listed),
                record=record if record.get("kind") != "preliminary_note" else None,
                search_terms=hits))
    return core.collect(findings)


def product_names(text, raw=""):
    """Spans (start, end) in a normalized text where a product is named.
    raw: the same text before normalization, to find the ™ sign.

    Two signs: a trademark mark after a word (®, ™, (R), (TM)), or a marker
    word (Fabrikat, Fabr., Hersteller, Herst., Erzeugnis, Produkt, Marke)
    followed by a name. After a colon or "=" any word that is not a
    placeholder counts as a name; without one, only "Fabrikat" or "Fabr."
    followed by a capitalized word does. "z.B." before the name is passed
    over. An anonymisation token ([PERSON_n], [FIRMA_n]) stands for a name
    the organizer took out and counts as one, unless dots follow it. A marker
    that asks the bidder ("angebotenes Fabrikat: ....", "Fabrikat:
    Bieterangabe") or is followed by dots names no product.
    """
    spans = [match.span() for match in _TRADEMARK.finditer(text)]
    for word, blank in set(_TM_WORD.findall(raw or "")):
        marked = core.quotes.normalize(word + blank + "™")
        spans.extend(match.span() for match in re.finditer(re.escape(marked), text))
    for match in _MARKER.finditer(text):
        if match.group("own"):
            continue
        example = _EXAMPLE.match(text, match.end())
        start = example.end() if example else match.end()
        name = _TOKEN.match(text, start)
        if name:
            if _FILL_IN.match(text, name.end()):
                continue
        else:
            name = _NAME.match(text, start)
            if not name:
                continue
            word = name.group("name").rstrip(".").casefold()
            if word in _NOT_A_NAME or word.startswith("bieter") or len(word) < 2:
                continue
        if not match.group("colon"):
            marker = match.group("word").casefold()
            first = name.group("name")[0]
            if "fabr" not in marker or match.group("link").strip() or not (first.isupper() or first == "["):
                continue
        spans.append((match.start("word"), name.end()))
    return sorted(spans)


def b12(doc):
    """B12: a product name without "oder gleichwertig".

    Not raised when the record itself, or a preliminary note of the same
    document that stands at the top or in a section above the record, says
    "oder gleichwertig"; those are counted as covered_by_note.
    """
    records = _text_records(doc)
    if not records:
        return NOT_APPLICABLE
    clause_sections = [core.item_no(n) for n in doc.notes if EQUIVALENT.search(core.full_text(n))]
    findings, covered = [], 0
    for record in records:
        text = core.full_text(record)
        spans = product_names(text, core.quotes.item_text(record))
        if not spans or EQUIVALENT.search(text):
            continue
        number = core.item_no(record)
        if any(s == "" or number == s or number.startswith(s + ".") for s in clause_sections):
            covered += 1
            continue
        name = core.label(record)
        start, end = spans[0]
        findings.append(core.make_finding(
            "B12", "product_without_equivalent", "medium",
            [doc.source(record, core.snippet(text, start, end))],
            "Die %s nennt ein Fabrikat oder Produkt ohne den Zusatz «oder gleichwertig»." % name,
            "Ist in der %s nur das genannte Fabrikat zugelassen, oder gilt «oder gleichwertig»?" % name,
            record=record if record.get("kind") != "preliminary_note" else None,
            search_terms=["oder gleichwertig"]))
    outcome = core.collect(findings)
    if covered:
        outcome.notes["covered_by_note"] = covered
    return outcome
