"""Build the deck: pitch/src/slides.html + deck.css + numbers.json -> out/pitch/ (W10).

    python -m pitch.build                 out/pitch/deck.html, deck.pdf, and the texts in pitch/
    python -m pitch.build --deck-only     the deck only; pitch/*.md stay as they are
    python -m pitch.build --out DIR --shots DIR --chrome PATH|none

deck.html is one file without any outside resource: the style sheet and the
screenshots are put into it. deck.pdf is that page printed by a headless
Chrome, 1920 x 1080 px per page, one slide per page. Without a Chrome on the
machine only the HTML is written and the command exits 0.

Exit 1: a rule of the deck is broken (more than 7 slides, a number that is not
in numbers.json, an opening finding that did not survive the counter-check, a
"confirmed" mark without a confirmed review, a pitch text over 3:00), or a
Chrome is there and printed no PDF or a PDF with the wrong number of pages.
"""
import argparse
import base64
import html
import os
import re
import sys

from pitch import check, chrome, numbers, texts

SLIDES = os.path.join(texts.SRC_DIR, "slides.html")
STYLE = os.path.join(texts.SRC_DIR, "deck.css")
DEFAULT_OUT = numbers.path("out", "pitch")
NO_EXPERT_OUT = numbers.path("out", "pitch_no_expert")
SHOTS = (("bauwerk", "Bauwerk"), ("fund", "Fund"))
MARKS = {"open": "Bestätigung durch den Kalkulator: offen", "confirmed": "Vom Kalkulator bestätigt"}
SKEPTIC_DE = {"survived": "bestanden", "weakened": "abgeschwächt", "refuted": "widerlegt"}
TITLE = "LV-Prüfstand, Team Cowork"
NO_REVIEWS = "no reviews file"


class BuildError(Exception):
    """The deck cannot be built without breaking one of its rules."""


def read(file_path):
    with open(file_path, encoding="utf-8") as handle:
        return handle.read()


def list_names(project):
    """doc -> name of the list as its file is called (LV_17 -> LV_17_Trockenbau)."""
    manifest = numbers.read_json(numbers.path(numbers.files(project)["manifest"]))
    return {entry["doc"]: os.path.splitext(entry["file"])[0] for entry in manifest}


def marked(quote, phrases):
    """The quote as HTML, word for word, with the given phrases in <mark>."""
    spans = []
    for phrase in phrases:
        start = quote.find(phrase)
        if start < 0 or not phrase:
            raise BuildError("pitch/opening.json: highlight %r does not stand in the quote" % phrase)
        spans.append((start, start + len(phrase)))
    out, position = [], 0
    for start, end in sorted(spans):
        if start < position:
            raise BuildError("pitch/opening.json: two highlights of one quote overlap")
        out += [html.escape(quote[position:start]), "<mark>", html.escape(quote[start:end]), "</mark>"]
        position = end
    return "".join(out) + html.escape(quote[position:])


def review_status(project, finding_id):
    """Review status of one finding in reviews/<project>.json: a status, None when the file
    holds no review of it, or NO_REVIEWS when the file is not on this machine."""
    file_path = numbers.path(numbers.files(project)["reviews"])
    if not os.path.isfile(file_path):
        return NO_REVIEWS
    entry = numbers.read_json(file_path).get(finding_id)
    return entry.get("status") if isinstance(entry, dict) else None


def opening_fields(opening, findings, names, reviewed, plan_survived):
    """The fields of slide 1 from the findings file; raises BuildError when the finding may not open the deck.

    Returns (fields, notes)."""
    finding = numbers.find(findings, opening["finding_id"])
    status = numbers.skeptic_status(finding)
    notes = []
    if status != "survived":
        raise BuildError("opening finding %s has the counter-check status %r; slide 1 takes a finding that survived"
                         % (finding["id"], status))
    if finding.get("quotes_verified") is not True:
        raise BuildError("opening finding %s: its quotes are not verified by the quote check" % finding["id"])
    if plan_survived and opening["finding_id"] != opening["plan_finding_id"]:
        raise BuildError("the finding the plan names (%s) survived the counter-check: it opens the deck"
                         % opening["plan_finding_id"])
    sources = finding["sources"]
    if len(sources) != 2:
        raise BuildError("opening finding %s has %d quotes; slide 1 shows a finding with two" % (finding["id"], len(sources)))
    confirmation = opening.get("confirmation")
    if confirmation not in MARKS:
        raise BuildError("pitch/opening.json: confirmation is %r; allowed: %s" % (confirmation, ", ".join(sorted(MARKS))))
    if confirmation == "confirmed" and reviewed == NO_REVIEWS:
        notes.append("pitch/opening.json says confirmed; the reviews file is not on this machine, so this is not checked here")
    elif confirmation == "confirmed" and reviewed != "confirmed":
        raise BuildError("pitch/opening.json says confirmed, but the review of %s in reviews/ says %r"
                         % (finding["id"], reviewed))
    if confirmation == "open" and reviewed == "confirmed":
        notes.append("the review of %s says confirmed: set confirmation to \"confirmed\" in pitch/opening.json" % finding["id"])
    if reviewed == "rejected":
        notes.append("WARNING: the review of %s says rejected. If that is the estimator's answer, slide 1 needs "
                     "another finding (pitch/README.md)." % finding["id"])
    highlight = opening.get("highlight") or []
    cards = []
    for index, source in enumerate(sources):
        where = "%s · Position %s · Seite %s" % (names.get(source["doc"], source["doc"]), source["item_no"], source["page"])
        cards.append('<figure class="source"><figcaption data-from="findings">%s</figcaption>'
                     '<blockquote data-source="%d">%s</blockquote></figure>'
                     % (html.escape(where), index, marked(source["quote"], highlight[index] if index < len(highlight) else [])))
    fields = {
        "opening.sources": "".join(cards),
        "opening.question": html.escape(finding["question_de"]),
        "opening.mark": html.escape(MARKS[confirmation]),
        "opening.status": html.escape("Fund %s · Gegenprüfung: %s" % (finding["id"], SKEPTIC_DE.get(status, status))),
    }
    return fields, notes


def shot_fields(shots_dir, project):
    fields = {}
    for name, view in SHOTS:
        file_path = os.path.join(shots_dir, name + ".png")
        if os.path.isfile(file_path) and os.path.getsize(file_path) > 0:
            with open(file_path, "rb") as handle:
                data = base64.b64encode(handle.read()).decode("ascii")
            fields["shot." + name] = '<img alt="Screenshot of the view %s" src="data:image/png;base64,%s">' % (html.escape(view), data)
        else:
            fields["shot." + name] = ('<div class="shot-missing">Screenshot missing: view „%s“. Start the review screen data, '
                                      'then run: python -m pitch.shots --project %s</div>' % (html.escape(view), html.escape(project)))
    return fields


def number_html(key, entry, text):
    return '<span class="n%s" data-n="%s">%s</span>' % ("" if entry["status"] == "measured" else " open", html.escape(key), html.escape(text))


def build_deck(data, opening, shots_dir, expert=True):
    """(deck html, notes). Raises BuildError or numbers.NumberError.

    expert=False: the variant without the expert session (texts.variant); the mark of slide 1 is not yellow."""
    project = data["project"]
    findings = numbers.load_findings(project)
    plan_survived = any(finding.get("id") == opening.get("plan_finding_id") and numbers.skeptic_status(finding) == "survived"
                        for finding in findings)
    fields, notes = opening_fields(opening, findings, list_names(project),
                                   review_status(project, opening["finding_id"]), plan_survived)
    fields.update(shot_fields(shots_dir, project))
    fields["project"] = html.escape(project)
    source = re.sub(r"<!--.*?-->", "", texts.variant(read(SLIDES), expert), flags=re.DOTALL)
    body = numbers.render(source, data["numbers"], fields, number_html=number_html, field_html=lambda name, value: value)
    if fields["opening.mark"] == html.escape(MARKS["confirmed"]):
        body = body.replace('<p class="mark">', '<p class="mark confirmed">')
    elif not expert:
        body = body.replace('<p class="mark">', '<p class="mark plain">')
    deck = ('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>%s</title>\n<style>\n%s</style>\n'
            '</head>\n<body>\n%s\n</body>\n</html>\n' % (html.escape(TITLE), read(STYLE), body.strip()))
    return deck, notes


def pdf_pages(file_path):
    """Number of pages and the (width, height) of each page in points."""
    try:
        import pymupdf as fitz  # PyMuPDF, in requirements.txt
    except ImportError:
        import fitz
    with fitz.open(file_path) as document:
        return [(page.rect.width, page.rect.height) for page in document]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pitch.build", description=__doc__.split("\n")[0])
    parser.add_argument("--out", default=DEFAULT_OUT, help="output folder (default: out/pitch)")
    parser.add_argument("--shots", default=None, help="folder with fund.png and pruefen.png (default: <out>/shots)")
    parser.add_argument("--chrome", default=None, help="browser file, or \"none\" to write the HTML only")
    parser.add_argument("--deck-only", action="store_true", help="do not write the texts in pitch/")
    parser.add_argument("--no-expert", action="store_true",
                        help="the variant without the expert session: no estimator number or sentence; deck and "
                             "texts go to --out (default: out/pitch_no_expert), pitch/*.md stay as they are")
    args = parser.parse_args(argv)
    if args.no_expert and args.out == DEFAULT_OUT:
        args.out = NO_EXPERT_OUT
    shots_dir = args.shots or os.path.join(DEFAULT_OUT if args.no_expert else args.out, "shots")
    try:
        data = numbers.load()
        deck, notes = build_deck(data, numbers.load_opening(), shots_dir, expert=not args.no_expert)
    except (BuildError, numbers.NumberError, OSError, ValueError, KeyError) as error:
        print("pitch.build: %s" % error, file=sys.stderr)
        return 1
    os.makedirs(args.out, exist_ok=True)
    deck_file, pdf_file = os.path.join(args.out, "deck.html"), os.path.join(args.out, "deck.pdf")
    with open(deck_file, "w", encoding="utf-8") as handle:
        handle.write(deck)
    slides = check.read_deck(deck)
    print("written: %s (%d slides)" % (deck_file, len(slides)))
    for note in notes:
        print("note: %s" % note)
    for slide in slides:
        if slide["missing_shots"]:
            print("note: slide %s shows %d grey box(es) instead of screenshots: run python -m pitch.shots --project %s"
                  % (slide["id"], slide["missing_shots"], data["project"]))
    shown_open = sorted({number["key"] for slide in slides for number in slide["numbers"]
                         if data["numbers"].get(number["key"], {}).get("status") == "open"})
    if args.no_expert:
        print("variant without the expert session: open numbers on the slides: %s" % (", ".join(shown_open) or "none"))
    else:
        still_open = sorted(key for key, entry in data["numbers"].items() if entry["status"] == "open")
        print("open numbers (shown as brackets): %s" % (", ".join(still_open) or "none"))
    failed = False
    for problem in check.deck_problems(deck, data):
        print("pitch.build: %s" % problem, file=sys.stderr)
        failed = True
    if args.no_expert and not args.deck_only:
        names = texts.write(data, args.out, expert=False)
        total = texts.pitch_total(data, expert=False)
        print("written: %s" % ", ".join(os.path.join(args.out, name) for name in names))
        print("pitch text: %d words, %s of %s" % (total["words"], texts.clock(total["seconds"]), texts.clock(texts.LIMIT)))
        if total["seconds"] > texts.LIMIT:
            print("pitch.build: the pitch text is longer than %s" % texts.clock(texts.LIMIT), file=sys.stderr)
            failed = True
    elif not args.deck_only:
        failed = texts.main([]) != 0 or failed
    browser = chrome.browser(args.chrome)
    if os.path.isfile(pdf_file):
        os.remove(pdf_file)  # never leave an older PDF next to a newer deck
    if not browser:
        print("no Chrome or Chromium on this machine: no deck.pdf. Open deck.html in a browser and print it to PDF.")
        return 1 if failed else 0
    why = chrome.print_pdf(browser, deck_file, pdf_file)
    if why:
        print("pitch.build: no deck.pdf: %s" % why, file=sys.stderr)
        return 1
    pages = pdf_pages(pdf_file)
    print("written: %s (%d pages)" % (pdf_file, len(pages)))
    if len(pages) != len(slides) or len(pages) > check.MAX_SLIDES:
        print("pitch.build: deck.pdf has %d pages for %d slides; the limit is %d pages"
              % (len(pages), len(slides), check.MAX_SLIDES), file=sys.stderr)
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
