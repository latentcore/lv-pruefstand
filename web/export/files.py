"""The three export files, built from the data of web/export/model.py.

fragenliste_docx, lv_markiert_xlsx and risikobericht_html return the file
content; print_pdf prints the report with a headless Chrome. Every fixed
German text comes from web/export/texte_de.py; text from the data goes into
the files as text only (escaped in the HTML, never as a formula in the .xlsx).
"""
import html
import io
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.shared import Mm, Pt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from web import browser as web_browser
from web.export import texte_de as T

MARK_COLOUR = "FFEB9C"  # fill of a cited row in LV_markiert.xlsx
BROWSERS = web_browser.NAMES
_NO_SHEET_NAME = re.compile(r"[\\/?*\[\]:]")


# ---- words and numbers ---------------------------------------------------------

def label(names, value):
    """German word for a value of the data; a value without a word is shown as it stands in the file."""
    if not value:
        return T.NICHT_ANGEGEBEN
    return names.get(value, value)


def date_text(moment):
    return T.DATUM.format(tag="%02d" % moment.day, monat="%02d" % moment.month, jahr=moment.year)


def stamp_text(stamp):
    """"2026-11-21T10:42" as German date and time; a text in another form stays as it is."""
    for form in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            moment = datetime.strptime(stamp, form)
        except (TypeError, ValueError):
            continue
        return T.DATUM_MIT_UHRZEIT.format(tag="%02d" % moment.day, monat="%02d" % moment.month, jahr=moment.year,
                                          stunde="%02d" % moment.hour, minute="%02d" % moment.minute)
    return stamp or ""


def confirmed_line(entry):
    """Who confirmed the finding and when, as the review file says it; no role is made up."""
    line = T.BESTAETIGT_VON.format(by=entry["by"]) if entry["by"] else T.BESTAETIGT_OHNE_ROLLE
    return T.BESTAETIGT_AM.format(zeile=line, datum=stamp_text(entry["at"])) if entry["at"] else line


def euro_text(amount):
    """1500.5 -> "1.500,50"."""
    whole, _, cents = ("%.2f" % amount).partition(".")
    return re.sub(r"\B(?=(\d{3})+$)", ".", whole) + "," + cents


def confirmed_by(data):
    """The roles of the reviews that confirmed a finding, for the head of the list of questions."""
    if not data["confirmed"]:
        return T.FRAGENLISTE_KOPF_NIEMAND
    return ", ".join(data["confirmed_by"] + ([T.OHNE_ANGABE] if data["by_missing"] else []))


def page_text(page):
    return T.NICHT_ANGEGEBEN if page is None else str(page)


# ---- 1. Fragen_und_Klaerungsliste.docx -------------------------------------------

def _columns(table, widths):
    table.autofit = False
    for row in table.rows:
        for cell, width in zip(row.cells, widths):
            cell.width = Mm(width)


def _bold_cell(cell, text):
    cell.text = ""
    cell.paragraphs[0].add_run(text).bold = True


def fragenliste_docx(data):
    """The list of questions as the bytes of a .docx: one block per confirmed finding."""
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.left_margin = section.right_margin = Mm(20)
    section.top_margin = section.bottom_margin = Mm(20)
    document.styles["Normal"].font.size = Pt(11)
    properties = document.core_properties
    properties.title = T.FRAGENLISTE_TITEL
    properties.author = properties.last_modified_by = T.PROGRAMM
    properties.language = "de-DE"
    properties.comments = ""
    properties.created = properties.modified = data["now"].replace(tzinfo=None)

    confirmed = data["confirmed"]
    document.add_heading(T.FRAGENLISTE_TITEL, level=0)
    if data["mode"] == "sample":
        document.add_paragraph().add_run(T.BEISPIELDATEN).bold = True
    head = document.add_table(rows=0, cols=2)
    head.style = "Table Grid"
    for name, value in ((T.FRAGENLISTE_KOPF_PROJEKT, data["project"]),
                        (T.FRAGENLISTE_KOPF_DATUM, date_text(data["now"])),
                        (T.FRAGENLISTE_KOPF_ANZAHL, str(len(confirmed))),
                        (T.FRAGENLISTE_KOPF_BESTAETIGT_VON, confirmed_by(data))):
        cells = head.add_row().cells
        _bold_cell(cells[0], name)
        cells[1].text = value
    _columns(head, (50, 120))
    document.add_paragraph()
    document.add_paragraph(T.FRAGENLISTE_EINLEITUNG)
    if not confirmed:
        document.add_paragraph().add_run(T.FRAGENLISTE_LEER).bold = True

    for entry in confirmed:
        document.add_heading(T.FRAGENLISTE_FRAGE.format(nr=entry["nr"]), level=1)
        document.add_paragraph().add_run(entry["question"] or T.NICHT_ANGEGEBEN).bold = True
        line = document.add_paragraph()
        line.add_run("%s: " % T.FRAGENLISTE_ART).bold = True
        line.add_run("%s · %s %s" % (label(T.ART, entry["type"]), T.FRAGENLISTE_FUND, entry["id"]))
        line = document.add_paragraph()
        line.add_run("%s: " % T.FRAGENLISTE_ERLAEUTERUNG).bold = True
        line.add_run(entry["explanation"] or T.NICHT_ANGEGEBEN)
        document.add_paragraph().add_run("%s:" % T.FRAGENLISTE_FUNDSTELLEN).bold = True
        if entry["sources"]:
            table = document.add_table(rows=1, cols=5)
            table.style = "Table Grid"
            for cell, name in zip(table.rows[0].cells, (T.LISTE, T.GEWERK, T.POSITION, T.SEITE, T.ZITAT)):
                _bold_cell(cell, name)
            for source in entry["sources"]:
                cells = table.add_row().cells
                for cell, value in zip(cells, (source["doc"] or T.NICHT_ANGEGEBEN, source["trade"],
                                              source["item_no"] or T.NICHT_ANGEGEBEN, page_text(source["page"]),
                                              source["quote"] or T.KEIN_ZITAT)):
                    cell.text = value
            _columns(table, (20, 30, 22, 14, 84))
        else:
            document.add_paragraph(T.KEINE_QUELLE)
        document.add_paragraph(confirmed_line(entry))

    document.add_paragraph()
    document.add_paragraph().add_run(T.FRAGENLISTE_SCHLUSS).italic = True
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


# ---- 2. LV_markiert.xlsx ----------------------------------------------------------

def _put(sheet, row, column, value, bold=False, wrap=False, fill=None):
    """Write one cell. A text stays a text, also when it starts with "=" (never a formula)."""
    cell = sheet.cell(row=row, column=column)
    cell.value = value
    if isinstance(value, str):
        cell.data_type = "s"
    if bold:
        cell.font = Font(bold=True)
    if wrap:
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    if fill is not None:
        cell.fill = fill
    return cell


def sheet_names(docs, taken):
    """One sheet name per list: at most 31 characters, none of \\ / ? * [ ] :, no name twice."""
    names, used = {}, set(name.lower() for name in taken)
    for doc in docs:
        base = _NO_SHEET_NAME.sub("_", doc).strip("'").strip()[:31] or "_"
        name, number = base, 2
        while name.lower() in used:
            tail = " (%d)" % number
            name, number = base[:31 - len(tail)] + tail, number + 1
        used.add(name.lower())
        names[doc] = name
    return names


def lv_markiert_xlsx(data):
    """LV_markiert as the bytes of an .xlsx: first the confirmed findings, then one sheet per list.

    A row that a confirmed finding cites is filled with MARK_COLOUR and carries
    the finding id, the type and the question. There is no price column.
    """
    book = Workbook()
    book.properties.creator = book.properties.lastModifiedBy = T.PROGRAMM
    book.properties.title = T.LV_TITEL
    book.properties.created = book.properties.modified = data["now"].replace(tzinfo=None)
    fill = PatternFill(fill_type="solid", start_color=MARK_COLOUR, end_color=MARK_COLOUR)
    confirmed, items = data["confirmed"], data["items"]
    names = sheet_names(data["docs"], [T.LV_BLATT_FUNDE])

    # Where each item stands: sheet and row; which findings cite it.
    place, next_row, cited = {}, {}, {}
    for index, item in enumerate(items):
        next_row[item["doc"]] = next_row.get(item["doc"], 1) + 1
        place[index] = (names[item["doc"]], next_row[item["doc"]])
    for entry in confirmed:
        for source in entry["sources"]:
            if source["item"] is not None and entry not in cited.setdefault(source["item"], []):
                cited[source["item"]].append(entry)

    first = book.active
    first.title = T.LV_BLATT_FUNDE
    _put(first, 1, 1, T.LV_TITEL, bold=True)
    _put(first, 2, 1, T.LV_KOPFZEILE.format(projekt=data["project"], datum=date_text(data["now"]),
                                              anzahl=len(confirmed)))
    notes = [T.BEISPIELDATEN] if data["mode"] == "sample" else []
    notes.append(T.LV_HINWEIS if confirmed else T.LV_LEER)
    if not data["items_usable"]:
        notes.append(T.LV_OHNE_POSITIONEN)
    row = 3
    for note in notes:
        _put(first, row, 1, note)
        row += 1
    row += 1
    heads = (T.LV_NR, T.LV_FUND, T.LV_ART, T.LV_SCHWERE, T.LV_FRAGE, T.LV_ERLAEUTERUNG, T.LISTE, T.POSITION,
             T.SEITE, T.ZITAT, T.LV_BLATT, T.LV_ZEILE)
    for column, name in enumerate(heads, 1):
        _put(first, row, column, name, bold=True)
    first.freeze_panes = first.cell(row=row + 1, column=1)
    for entry in confirmed:
        for source in entry["sources"] or [None]:
            row += 1
            values = [entry["nr"], entry["id"], label(T.ART, entry["type"]), label(T.SCHWERE, entry["severity"]),
                      entry["question"] or T.NICHT_ANGEGEBEN, entry["explanation"] or T.NICHT_ANGEGEBEN]
            if source is None:
                values += [T.KEINE_QUELLE]
            else:
                sheet, line = place.get(source["item"], (T.LV_NICHT_GEFUNDEN, T.LV_NICHT_GEFUNDEN))
                values += [source["doc"] or T.NICHT_ANGEGEBEN, source["item_no"] or T.NICHT_ANGEGEBEN,
                           source["page"] if source["page"] is not None else T.NICHT_ANGEGEBEN,
                           source["quote"] or T.KEIN_ZITAT, sheet, line]
            for column, value in enumerate(values, 1):
                _put(first, row, column, value, wrap=column in (5, 6, 10))
    for column, width in enumerate((6, 14, 24, 10, 60, 60, 12, 14, 8, 80, 18, 10), 1):
        first.column_dimensions[get_column_letter(column)].width = width

    heads = (T.LISTE, T.POSITION, T.LV_KURZTEXT, T.LV_MENGE, T.LV_EINHEIT, T.SEITE, T.LV_FUND, T.LV_ART, T.LV_FRAGE)
    sheets = {}
    for doc in data["docs"]:
        sheet = sheets[doc] = book.create_sheet(names[doc])
        for column, name in enumerate(heads, 1):
            _put(sheet, 1, column, name, bold=True)
        sheet.freeze_panes = "A2"
        for column, width in enumerate((12, 14, 60, 12, 10, 8, 16, 24, 70), 1):
            sheet.column_dimensions[get_column_letter(column)].width = width
    for index, item in enumerate(items):
        sheet, row = sheets[item["doc"]], place[index][1]
        marks = cited.get(index, [])
        values = [item["doc"], item["item_no"], item["short_text"], item["quantity"], item["unit"], item["page"],
                  "\n".join(entry["id"] for entry in marks),
                  "\n".join(label(T.ART, entry["type"]) for entry in marks),
                  "\n".join(entry["question"] or T.NICHT_ANGEGEBEN for entry in marks)]
        for column, value in enumerate(values, 1):
            _put(sheet, row, column, value if value != "" else None, wrap=bool(marks) and column >= 7,
                 fill=fill if marks else None)
    for doc, sheet in sheets.items():
        sheet.auto_filter.ref = "A1:%s%d" % (get_column_letter(len(heads)), max(next_row.get(doc, 1), 1))
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


# ---- 3. Risikobericht.html and .pdf ------------------------------------------------

STYLE = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
html { color-scheme: light; }
body { margin: 0 auto; padding: 12mm 10mm; max-width: 210mm; font-family: Arial, Helvetica, sans-serif;
  font-size: 11pt; line-height: 1.4; color: #111827; background: #ffffff; }
h1 { font-size: 22pt; margin: 0; }
h2 { font-size: 14pt; margin: 8mm 0 2mm; border-bottom: 1.5pt solid #111827; padding-bottom: 1mm; }
h3 { font-size: 12pt; margin: 0 0 1.5mm; }
p { margin: 0 0 2mm; }
.sub { color: #374151; }
.sample { font-weight: bold; border: 1.5pt solid #92400e; background: #fef3c7; padding: 2mm 3mm; }
.numbers { display: grid; grid-template-columns: repeat(3, 1fr); gap: 3mm; margin: 3mm 0; }
.number { border: 1pt solid #9ca3af; border-radius: 2mm; padding: 2mm 3mm; break-inside: avoid; }
.number b { display: block; font-size: 18pt; line-height: 1.1; }
.status { grid-template-columns: repeat(4, 1fr); }
.confirmed { border-color: #166534; background: #dcfce7; }
.rejected { border-color: #991b1b; background: #fee2e2; }
.unclear { border-color: #92400e; background: #fef3c7; }
.finding { border: 1pt solid #9ca3af; border-radius: 2mm; padding: 3mm 4mm; margin: 0 0 4mm; }
.finding h3, .finding .tags { break-after: avoid; }
.tags span { display: inline-block; border: 1pt solid #9ca3af; border-radius: 3mm; padding: 0 2.5mm;
  margin: 0 1.5mm 1.5mm 0; background: #f3f4f6; }
.sources { display: grid; grid-template-columns: repeat(auto-fit, minmax(55mm, 1fr)); gap: 3mm; margin: 2mm 0; }
.source { border: 1pt solid #9ca3af; border-radius: 2mm; padding: 2mm 3mm; break-inside: avoid; }
.where { font-weight: bold; overflow-wrap: anywhere; }
blockquote { margin: 1.5mm 0 0; padding: 1.5mm 3mm; border-left: 3pt solid #f59e0b; background: #fffbeb;
  white-space: pre-wrap; overflow-wrap: anywhere; }
.review { color: #374151; }
.box { border: 1.5pt solid #111827; border-radius: 2mm; padding: 3mm 4mm; margin: 6mm 0 0; break-inside: avoid;
  background: #f3f4f6; }
.box h2 { margin-top: 0; border: 0; padding: 0; }
.box ul { margin: 0 0 2mm; padding-left: 5mm; }
.bench { white-space: pre-wrap; overflow-wrap: anywhere; }
footer { margin-top: 6mm; color: #374151; font-style: italic; }
@media print { body { padding: 0; max-width: none; } }
"""


def risikobericht_html(data):
    """The Risikobericht as one HTML text without any outside resource, styled for A4 print."""
    e = html.escape
    counts, confirmed = data["counts"], data["confirmed"]
    known = data["items_usable"]
    parts = [
        '<!DOCTYPE html>\n<html lang="de">\n<head>\n<meta charset="utf-8">',
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">",
        "<title>%s · %s</title>" % (e(T.BERICHT_TITEL), e(data["project"])),
        "<style>%s</style>\n</head>\n<body>" % STYLE,
        "<header><h1>%s</h1>" % e(T.BERICHT_TITEL),
        '<p class="sub">%s</p>' % e(T.BERICHT_UNTERTITEL.format(projekt=data["project"],
                                                                 datum=date_text(data["now"]))),
    ]
    if data["mode"] == "sample":
        parts.append('<p class="sample">%s</p>' % e(T.BEISPIELDATEN))
    parts.append("</header>")

    def number(name, value, kind=""):
        return '<div class="number %s"><b>%s</b>%s</div>' % (kind, e(str(value)), e(name))

    parts.append('<section id="zusammenfassung"><h2>%s</h2><div class="numbers">' % e(T.BERICHT_ZUSAMMENFASSUNG))
    parts.append(number(T.BERICHT_LISTEN, counts["lists"] if known else T.BERICHT_UNBEKANNT))
    parts.append(number(T.BERICHT_POSITIONEN, counts["positions"] if known else T.BERICHT_UNBEKANNT))
    parts.append(number(T.BERICHT_FUNDE, counts["findings"]))
    parts.append('</div><p>%s:</p><div class="numbers status">' % e(T.BERICHT_DAVON))
    for status in ("confirmed", "rejected", "unclear", "open"):
        parts.append(number(T.STATUS[status], counts[status], status))
    parts.append("</div>")
    if not known:
        parts.append("<p>%s</p>" % e(T.BERICHT_OHNE_POSITIONEN))
    elif counts["headings"] or counts["preliminary_notes"]:
        parts.append("<p>%s</p>" % e(T.BERICHT_EINTRAEGE.format(ueberschriften=counts["headings"],
                                                                 vorbemerkungen=counts["preliminary_notes"])))
    if counts["reviews_without_finding"]:
        parts.append("<p>%s</p>" % e(T.BERICHT_BEWERTUNG_OHNE_FUND.format(anzahl=counts["reviews_without_finding"])))
    parts.append("</section>")

    parts.append('<section id="funde"><h2>%s</h2>' % e(T.BERICHT_WICHTIGSTE_FUNDE))
    parts.append('<p class="sub">%s</p>' % e(T.BERICHT_WICHTIGSTE_FUNDE_HINWEIS if confirmed else T.BERICHT_LEER))
    for entry in confirmed:
        parts.append('<article class="finding" data-id="%s"><h3>%s. %s</h3>'
                     % (e(entry["id"]), entry["nr"], e(entry["question"] or T.NICHT_ANGEGEBEN)))
        parts.append('<p class="tags"><span>%s: %s</span><span>%s: %s</span><span>%s %s</span></p>' % (
            e(T.BERICHT_ART), e(label(T.ART, entry["type"])), e(T.BERICHT_SCHWERE),
            e(label(T.SCHWERE, entry["severity"])), e(T.BERICHT_FUND), e(entry["id"])))
        parts.append("<p><b>%s:</b> %s</p>" % (e(T.BERICHT_ERLAEUTERUNG), e(entry["explanation"] or T.NICHT_ANGEGEBEN)))
        if entry["sources"]:
            parts.append('<div class="sources">')
            for source in entry["sources"]:
                where = [source["doc"] or T.NICHT_ANGEGEBEN] + ([source["trade"]] if source["trade"] else [])
                item = "%s %s · %s %s" % (T.POSITION, source["item_no"] or T.NICHT_ANGEGEBEN, T.SEITE,
                                          page_text(source["page"]))
                parts.append('<div class="source"><div class="where">%s: %s</div><div>%s</div>'
                             "<blockquote>%s</blockquote></div>"
                             % (e(T.LISTE), e(" · ".join(where)), e(item), e(source["quote"] or T.KEIN_ZITAT)))
            parts.append("</div>")
        else:
            parts.append("<p>%s</p>" % e(T.KEINE_QUELLE))
        parts.append('<p class="review">%s</p>' % e(confirmed_line(entry)))
        if entry["comment"]:
            parts.append('<p class="review">%s: %s</p>' % (e(T.BERICHT_KOMMENTAR), e(entry["comment"])))
        if entry["eur_estimate"] is not None:
            parts.append('<p class="review estimate">%s: %s</p>' % (
                e(T.BERICHT_SCHAETZUNG), e(T.BERICHT_EURO.format(betrag=euro_text(entry["eur_estimate"])))))
        parts.append("</article>")
    parts.append("</section>")

    parts.append('<section class="box" id="methode"><h2>%s</h2>' % e(T.BERICHT_METHODE))
    parts.extend("<p>%s</p>" % e(sentence) for sentence in T.BERICHT_METHODE_SAETZE)
    parts.append("</section>")

    parts.append('<section class="box" id="messung"><h2>%s</h2><p class="sub">%s</p><ul>'
                 % (e(T.BERICHT_MESSUNG), e(T.BERICHT_MESSUNG_HINWEIS)))
    read = ["%s: %s" % (T.BERICHT_FUNDE, counts["findings"])]
    if known:
        read = ["%s: %s" % (T.BERICHT_LISTEN, counts["lists"]),
                "%s: %s" % (T.BERICHT_POSITIONEN, counts["positions"])] + read
    parts.append("<li><b>%s:</b> %s</li>" % (e(T.BERICHT_MESSUNG_ZAEHLUNG), e(" · ".join(read))))
    parts.append("<li><b>%s:</b> %s</li>" % (e(T.BERICHT_MESSUNG_BEWERTUNG), e(" · ".join(
        "%s %s" % (counts[status], T.STATUS[status]) for status in ("confirmed", "rejected", "unclear", "open")))))
    by_pass, by_rule = data["weakened_split"]

    def skeptic_part(name, amount):
        if name == "weakened" and amount:
            return T.BERICHT_MESSUNG_ABGESCHWAECHT.format(anzahl=amount, durchgang=by_pass, regel=by_rule)
        return "%s %s" % (amount, label(T.GEGENPRUEFUNG, name))

    parts.append("<li><b>%s:</b> %s</li>" % (e(T.BERICHT_MESSUNG_GEGENPRUEFUNG), e(" · ".join(
        skeptic_part(name, amount) for name, amount in data["skeptic"]))))
    parts.append("</ul>")
    if data["bench_state"] in ("ok", "committed"):
        if data["bench_state"] == "committed":
            parts.append('<p class="bench-note">%s</p>' % e(T.BERICHT_MESSUNG_GESPEICHERT))
        parts.append('<p><b>%s:</b></p><ul class="bench">' % e(T.BERICHT_MESSUNG_LAUF))
        parts.extend("<li>%s</li>" % e(line) for line in data["bench_lines"])
        parts.append("</ul>")
    else:
        parts.append('<p class="bench-note">%s</p>' % e(
            T.BERICHT_MESSUNG_FEHLT if data["bench_state"] == "missing" else T.BERICHT_MESSUNG_UNLESBAR))
    parts.append("</section>")
    parts.append("<footer>%s</footer>\n</body>\n</html>\n" % e(T.BERICHT_SCHLUSS))
    return "\n".join(parts)


def browser():
    """Path of a Chrome, Chromium or Microsoft Edge on this machine, or None (web/browser.py)."""
    return web_browser.find()


def print_pdf(report_html, chrome=None, timeout=90):
    """Print the report with a headless Chrome. Returns (pdf bytes, None) or (None, why not)."""
    chrome = chrome or browser()
    if not chrome:
        return None, "no Chrome or Chromium on this machine"
    with tempfile.TemporaryDirectory(prefix="lv-export-") as folder:
        page, target = os.path.join(folder, "Risikobericht.html"), os.path.join(folder, "Risikobericht.pdf")
        with open(page, "w", encoding="utf-8") as handle:
            handle.write(report_html)
        command = [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-extensions", "--no-first-run",
                   "--user-data-dir=%s" % os.path.join(folder, "profile"), "--no-pdf-header-footer",
                   "--print-to-pdf-no-header", "--print-to-pdf=%s" % target, Path(page).as_uri()]
        try:
            done = subprocess.run(command, capture_output=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            return None, "the browser did not run: %s" % error
        if not os.path.isfile(target) or os.path.getsize(target) == 0:
            return None, "the browser printed no PDF (exit code %s)" % done.returncode
        with open(target, "rb") as handle:
            return handle.read(), None
