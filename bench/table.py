"""The table of the bench, made from bench.json and from nothing else.

One function per output: the printed table (text()), the README table
(markdown()) and the German lines of the report (lines_de()). All three read
the same records, so they cannot disagree.
"""
from bench import prereg

HEADER = ("#", "Measurement", "Result", "Threshold", "Threshold met")
HEADER_DE = "Messlauf (bench), Stand %s. Schwellen vor dem Lauf festgelegt (docs/PREREG.md)."
MET_DE = {
    prereg.YES: "erfüllt", prereg.NO: "nicht erfüllt",
    prereg.NOT_MEASURABLE: "nicht messbar", prereg.NOT_YET: "noch nicht gemessen",
}
NAMES_DE = {
    "M1": "GAEB-Dateien lesen", "M2": "Nachrechnen", "M3": "PDF gegen GAEB-Zwilling",
    "M4": "PDF-Leser, 27 Verzeichnisse", "M5": "Urteil der Fachleute", "M6": "Zitatfilter",
    "M7": "Selbst eingebaute Fehler (interne Messung)", "M8": "Fehlalarme", "M9": "Geschwindigkeit",
}
THRESHOLDS_DE = {
    "M1": "9/9", "M2": "jede Abweichung wird einzeln genannt",
    "M3": "≥ 98 % der Positionen, ≥ 98 % der Preise",
    "M4": "Unterschied 0; was nicht gelesen wurde, wird offen genannt",
    "M5": "die Zahlen, wie sie herauskommen; Hauptbeleg", "M6": "wird berichtet",
    "M7": "B ≥ 90 %; X wird nur berichtet", "M8": "≤ 5", "M9": "≤ 5 s",
}
TYPES_DE = {
    "quantity_x10": "Menge ×10", "unit_change": "Einheit geändert", "corrupted_amount": "Betrag verfälscht",
    "corrupted_total": "Summe verfälscht", "deleted_item": "Position gelöscht",
    "duplicated_item": "Position doppelt",
}
M5_NOT_YET_DE = "nicht gemessen: während der Veranstaltung fand keine Sitzung mit einer Fachperson statt"
M5_RULE = ("counted: `by` not empty and without \"test\", `at` within the session; "
           "the bench cannot tell a real expert from a test click beyond that")
M5_RULE_DE = ("gezählt wird ein Eintrag mit Rolle ohne «test» und Zeitpunkt in der Sitzung; "
              "mehr kann der Messlauf nicht unterscheiden")
NOT_COUNTED_DE = {
    "not a review record": "kein Bewertungseintrag", "no decision": "keine Entscheidung",
    "no role given": "ohne Rolle", "role holds 'test'": "Rolle enthält «test»",
    "outside the expert session": "außerhalb der Sitzung",
}
X_DE = "X nicht gemessen: dafür wäre ein neuer Modelllauf nötig, und der Messlauf startet kein Modell"


def percent(tenths, comma=False):
    """Tenths of a percent as text ("97.9 %"); "–" when there is none."""
    if tenths is None:
        return "–"
    text = "%d.%d %%" % (tenths // 10, tenths % 10)
    return text.replace(".", ",") if comma else text


def hundredths(value, comma=False):
    if value is None:
        return "–"
    text = "%d.%02d" % (value // 100, value % 100)
    return text.replace(".", ",") if comma else text


def seconds(value, comma=False):
    text = "%.3f s" % value
    return text.replace(".", ",") if comma else text


def _reason(entry, german):
    """The reason of a record that was not measured, in the language of the output."""
    reason = entry.get("reason") or ""
    if not german:
        return reason
    if reason.startswith(prereg.M5_NOT_YET):
        return M5_NOT_YET_DE + reason[len(prereg.M5_NOT_YET):].replace(
            " (the review file cannot be read)", " (die Bewertungsdatei ist nicht lesbar)")
    for english, german_text in (("input not found: ", "Eingabe fehlt: "),
                                 ("pdftotext not found on PATH", "pdftotext ist nicht installiert"),
                                 ("Poppler's pdftotext is not on PATH (needed for the PDF files)",
                                  "Popplers pdftotext ist nicht installiert (für die PDF-Dateien nötig)"),
                                 ("pipeline/diff (W13) is not merged yet",
                                  "pipeline/diff (W13) ist noch nicht eingebaut"),
                                 ("prices not measurable for ", "Preise nicht messbar bei ")):
        reason = reason.replace(english, german_text)
    return reason


def _m1(entry, de):
    wrong = [f for f in entry["files"] if not f["equal"] and f["read"] is not None]
    failed = [f for f in entry["files"] if f.get("error", "").startswith("reader error")]
    text = ("%d von %d Dateien mit der erwarteten Positionszahl" if de else
            "%d of %d files with the expected item count") % (entry["files_equal"], entry["files_expected"])
    for f in wrong:
        text += ("; %s: %d gelesen, %d erwartet" if de else "; %s: read %d, expected %d") % (
            f["file"], f["read"], f["expected"])
    for f in failed:
        text += ("; %s: Lesefehler" if de else "; %s: reader error") % f["file"]
    return text


def _m2(entry, de):
    text = ("%d Positionen in %d Dateien nachgerechnet, %d weichen ab" if de else
            "%d items checked in %d files, %d deviate") % (
                entry["checked"], len(entry["files"]), entry["deviating"])
    listed = ["%s: %s" % (f["file"], ", ".join(f["deviating_items"])) for f in entry["files"] if f["deviating_items"]]
    if listed:
        text += " (%s)" % "; ".join(listed)
    if entry["not_checkable_no_quantity"]:
        text += ("; %d Positionen mit Preis ohne Menge nicht prüfbar" if de else
                 "; %d priced items without a quantity not checkable") % entry["not_checkable_no_quantity"]
    return text


def _m3(entry, de):
    parts = []
    for pair in entry["pairs"]:
        text = ("%s %s: %d von %d Positionen der GAEB-Datei auch im PDF (%s)" if de else
                "%s %s: %d of %d items of the GAEB file also in the PDF (%s)") % (
                    pair["twin"], pair["gaeb"], pair["items_in_both"], pair["items_gaeb"],
                    percent(pair["items_percent_tenths"], de))
        if pair["items_only_pdf"]:
            text += (", %d nur im PDF" if de else ", %d only in the PDF") % pair["items_only_pdf"]
        if pair["prices_measurable"]:
            text += (", Einheitspreise gleich %d von %d, Gesamtbeträge gleich %d von %d (%s)" if de else
                     ", unit prices equal %d of %d, totals equal %d of %d (%s)") % (
                         pair["unit_prices_equal"], pair["unit_prices_compared"],
                         pair["totals_equal"], pair["totals_compared"],
                         percent(pair["prices_percent_tenths"], de))
        else:
            text += (", Preise nicht messbar: %s" if de else ", prices not measurable: %s") % (
                pair["prices_reason_de"] if de else pair["prices_reason"])
        parts.append(text)
    return "; ".join(parts)


def _m4(entry, de):
    check = entry["pagecheck"]
    text = ("%d Verzeichnisse, %d und %d Positionen in zwei Läufen, Unterschied %d; Seitenprüfung von %s: "
            "%d von %d Positionen stimmen auf %d Seiten, %d Abweichungen; nicht gelesen: %d Warnungen "
            "des Lesers in %d Verzeichnissen, %d nicht gelesene Zeilen" if de else
            "%d lists, %d and %d items in two runs, difference %d; page check of %s: %d of %d items match "
            "on %d pages, %d differences; not read: %d reader warnings in %d lists, %d unparsed lines")
    return text % (entry["lists"], entry["items_run1"], entry["items_run2"], entry["difference"],
                   ", ".join(check["lists"]), check["items_matched"], check["items_on_page"], check["pages"],
                   check["differences"], entry["warnings"], len(entry["lists_with_warnings"]),
                   entry["unparsed_lines"])


def _m5_found(entry, de):
    if not entry.get("file_found"):
        return ("; %s fehlt" if de else "; %s does not exist") % entry["file"]
    if "entries" not in entry:
        return ""
    text = ("; %d Einträge in %s, %d gezählt" if de else "; %d entries in %s, %d counted") % (
        entry["entries"], entry["file"], entry["counted"])
    if entry["not_counted"]:
        text += (" (nicht gezählt: %s)" if de else " (not counted: %s)") % ", ".join(
            "%s %d" % (NOT_COUNTED_DE.get(why, why) if de else why, count)
            for why, count in entry["not_counted"].items())
    if entry["roles_found"]:
        text += ("; gefundene Rollen: %s" if de else "; role names found: %s") % ", ".join(entry["roles_found"])
    return text


def _m5(entry, de):
    text = ("%d bestätigt, %d verworfen, %d unklar" if de else "%d confirmed, %d rejected, %d unclear") % (
        entry["confirmed"], entry["rejected"], entry["unclear"])
    roles = ["%s %d/%d/%d" % (r["role"], r["confirmed"], r["rejected"], r["unclear"]) for r in entry["by_role"]]
    text += (" (je Rolle bestätigt/verworfen/unklar: %s)" if de else
             " (by role, confirmed/rejected/unclear: %s)") % "; ".join(roles)
    return text + _m5_found(entry, de) + "; " + (M5_RULE_DE if de else M5_RULE)


def _m6(entry, de):
    text = ("%d Befunde im Repository mit %d Zitaten geprüft, %d verworfen, weil ein Zitat nicht gefunden wurde"
            if de else "%d committed findings with %d quotes checked, %d dropped because a quote was not found")
    text = text % (entry["findings"], entry["quotes"], entry["dropped"])
    if entry["dropped_ids"]:
        text += " (%s)" % ", ".join(entry["dropped_ids"])
    return text


def _m7(entry, de):
    types = ", ".join("%s %d/%d" % (TYPES_DE[t["type"]] if de else t["name"], t["found"], t["planted"])
                      for t in entry["types"])
    text = ("B: %d von %d gefunden (%s) in %s; je Art gefunden/eingebaut: %s; %s" if de else
            "B: %d of %d found (%s) in %s; by type, found/planted: %s; X %s")
    return text % (entry["found"], entry["planted"], percent(entry["percent_tenths"], de), entry["file"],
                   types, X_DE if de else entry["x"])


def _m8(entry, de):
    clean, other = entry["clean"], entry["other"]
    text = ("%s: %d Befunde hoch oder mittel bei %d Positionen = %s je 100" if de else
            "%s: %d high or medium findings in %d items = %s per 100") % (
                clean["file"], clean["high_medium"], clean["items"], hundredths(clean["per_100_hundredths"], de))
    if other:
        text += ("; zum Vergleich, ohne Schwelle, %s: %d bei %d = %s je 100" if de else
                 "; for comparison, without a threshold, %s: %d in %d = %s per 100") % (
                     other["file"], other["high_medium"], other["items"],
                     hundredths(other["per_100_hundredths"], de))
    return text


def _m9(entry, de):
    parts = []
    for run in entry["inputs"]:
        if run["input"] == "built":
            what = ("%d Positionen, gebaut aus %s" if de else "%d items built from %s") % (run["items"], run["file"])
        else:
            what = ("%s, %d Positionen" if de else "%s, %d items") % (run["file"], run["items"])
        parts.append("%s (%s)" % (seconds(run["median_seconds"], de), what))
    text = ("Grundprüfungen, Median aus %d Läufen: %s; Rechner: %s" if de else
            "base layer, median of %d runs: %s; machine: %s")
    return text % (entry["runs"], (" und " if de else " and ").join(parts), entry["machine"])


_RESULT = {"M1": _m1, "M2": _m2, "M3": _m3, "M4": _m4, "M5": _m5, "M6": _m6, "M7": _m7, "M8": _m8, "M9": _m9}
_MEASURED_KEY = {"M1": "files", "M2": "files", "M3": "pairs", "M4": "pagecheck", "M5": "by_role",
                 "M6": "findings", "M7": "types", "M8": "clean", "M9": "inputs"}


def result(entry, german=False):
    """The result cell of one record."""
    row_id, met = entry["id"], entry["met"]
    measured = _MEASURED_KEY[row_id] in entry and not (row_id == "M5" and met == prereg.NOT_YET)
    if not measured:
        text = _reason(entry, german) or (MET_DE[met] if german else met)
        if row_id == "M5":
            text += _m5_found(entry, german) + "; " + (M5_RULE_DE if german else M5_RULE)
        return text
    text = _RESULT[row_id](entry, german)
    if met == prereg.NOT_YET and entry.get("reason"):
        text += "; " + _reason(entry, german)
    return text


def rows(data):
    """The rows of the table: (id, name, result, threshold, threshold met), from bench.json."""
    return [(entry["id"], entry["name"], result(entry), entry["threshold"], entry["met"])
            for entry in data["measurements"]]


def _cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def markdown(data):
    """The README table."""
    lines = ["| %s |" % " | ".join(HEADER), "|%s|" % "|".join("---" for _ in HEADER)]
    for row in rows(data):
        lines.append("| %s |" % " | ".join(_cell(cell) for cell in row))
    return "\n".join(lines)


def text(data):
    """The printed table: one block per measurement, so that long results stay readable."""
    lines = ["bench: %s (measured %s)" % (" | ".join(HEADER), data.get("measured_at") or "?")]
    for row_id, name, result_text, threshold, met in rows(data):
        lines.append("%s | %s | %s | %s | %s" % (row_id, name, result_text, threshold, met))
    return "\n".join(lines)


def lines_de(data):
    """The German lines of the report (out/<project>/bench.json)."""
    lines = [HEADER_DE % (data.get("measured_at") or "?").replace("T", " ")]
    for entry in data["measurements"]:
        lines.append("%s %s: %s. Schwelle: %s. Schwelle eingehalten: %s." % (
            entry["id"], NAMES_DE[entry["id"]], result(entry, german=True),
            THRESHOLDS_DE[entry["id"]], MET_DE[entry["met"]]))
    return lines
