"""Alle festen deutschen Texte der drei Exportdateien, an EINER Stelle zum Korrekturlesen.

Every fixed German text of Fragen_und_Klaerungsliste.docx, LV_markiert.xlsx and
Risikobericht.html/.pdf stands in this file and nowhere else (a test checks it).
The other modules of web/export/ only put these texts and the data together.

Rules for a change here (MASTER_PLAN §18 "Almanca kalitesi", K12):
- the terms of the lists themselves: Leistungsverzeichnis, Position,
  Vorbemerkung, Gewerk, Nachunternehmer;
- the names of the views "Fund" and "Prüfen" for type, level and status;
- no number: every number comes from a file and is filled into a {placeholder};
- no claim that somebody checked something: who confirmed comes from the
  review file ({by}); no legal advice.

A text in braces, such as {projekt}, is a placeholder; keep it as it is.
"""

# ---- Wörter der Ansichten "Fund" und "Prüfen" (web/static/app.js) -----------

# Art des Fundes (findings.json: type). A value that is not listed is shown as it stands in the file.
ART = {
    "double_assignment": "Doppelt ausgeschrieben",
    "contradiction": "Widerspruch",
    "gap": "Lücke",
}

# Schwere (findings.json: severity), in the order of the report: most important first.
SCHWERE = {
    "high": "hoch",
    "medium": "mittel",
    "info": "Hinweis",
}

# Bewertung (reviews: status) and "offen" for a finding without a review.
STATUS = {
    "confirmed": "bestätigt",
    "rejected": "verworfen",
    "unclear": "unklar",
    "open": "offen",
}

# Ergebnis der Gegenprüfung (findings.json: skeptic.status).
GEGENPRUEFUNG = {
    "survived": "bestanden",
    "weakened": "abgeschwächt",
    "refuted": "widerlegt",
}

NICHT_ANGEGEBEN = "nicht angegeben"
OHNE_ANGABE = "ohne Angabe"
KEIN_ZITAT = "(kein Zitat)"
KEINE_QUELLE = "Dieser Fund nennt keine Quelle."

# Shown in the head of all three files when the app reads contract/samples/ instead of a project.
BEISPIELDATEN = "Beispieldaten (synthetisch, keine echten Listen)"

# Date and time: {tag}.{monat}.{jahr} and {stunde}:{minute} are filled by code.
DATUM = "{tag}.{monat}.{jahr}"
DATUM_MIT_UHRZEIT = "{tag}.{monat}.{jahr}, {stunde}:{minute} Uhr"

# Name of the program in the file properties (author field of .docx and .xlsx).
PROGRAMM = "LV-Prüfstand"

# Who confirmed a finding, under its block in the list of questions and in the report.
# {by} is the role from the review file; {zeile} is one of the two lines above it.
BESTAETIGT_VON = "Bestätigt von {by}"
BESTAETIGT_OHNE_ROLLE = "Bestätigt; die Rolle des Prüfers ist nicht eingetragen"
BESTAETIGT_AM = "{zeile} (am {datum})"

# ---- Tabellenköpfe für eine Fundstelle (alle drei Dateien) -------------------

LISTE = "Liste"
GEWERK = "Gewerk"
POSITION = "Position"
SEITE = "Seite"
ZITAT = "Zitat"

# ---- 1. Fragen- und Klärungsliste (.docx) ------------------------------------

FRAGENLISTE_TITEL = "Fragen- und Klärungsliste"
FRAGENLISTE_KOPF_PROJEKT = "Projekt"
FRAGENLISTE_KOPF_DATUM = "Datum"
FRAGENLISTE_KOPF_ANZAHL = "Anzahl der Fragen"
FRAGENLISTE_KOPF_BESTAETIGT_VON = "Bestätigt von"
# In the head, in place of a role, when no finding is confirmed yet.
FRAGENLISTE_KOPF_NIEMAND = "noch kein Fund bestätigt"
FRAGENLISTE_EINLEITUNG = (
    "Diese Liste enthält Fragen, die sich ergeben, wenn alle Leistungsverzeichnisse des Projekts "
    "zusammen als ein Projekt gelesen werden. Aufgenommen sind nur Funde mit der Bewertung „bestätigt“; "
    "wer bestätigt hat, steht im Kopf dieser Liste. Zu jeder Frage stehen die Fundstellen mit "
    "Liste, Position, Seite und wörtlichem Zitat."
)
FRAGENLISTE_LEER = (
    "Es gibt noch keinen bestätigten Fund. Diese Liste enthält deshalb keine Fragen."
)
FRAGENLISTE_FRAGE = "Frage {nr}"
FRAGENLISTE_ART = "Art"
FRAGENLISTE_FUND = "Fund"
FRAGENLISTE_ERLAEUTERUNG = "Erläuterung"
FRAGENLISTE_FUNDSTELLEN = "Fundstellen"
FRAGENLISTE_SCHLUSS = (
    "Diese Liste stellt Fragen zur Klärung. Sie bewertet die Sachverhalte nicht rechtlich."
)

# ---- 2. LV markiert (.xlsx) --------------------------------------------------

LV_TITEL = "LV markiert"
# Name of the first sheet (at most 31 characters, none of \ / ? * [ ] :).
LV_BLATT_FUNDE = "Bestätigte Funde"
LV_KOPFZEILE = "Projekt: {projekt} · Datum: {datum} · Bestätigte Funde: {anzahl}"
LV_HINWEIS = (
    "Jede Liste hat ein eigenes Blatt mit allen Einträgen der Liste. Gelb markiert sind die Zeilen, "
    "die ein bestätigter Fund zitiert; dort stehen auch Fund, Art und Frage."
)
LV_LEER = (
    "Es gibt noch keinen bestätigten Fund. In den Blättern der Listen ist deshalb keine Zeile markiert."
)
LV_OHNE_POSITIONEN = (
    "Die Datei items.json fehlt oder ist nicht lesbar. Die Blätter der Listen fehlen deshalb in dieser Datei."
)
LV_NR = "Nr."
LV_FUND = "Fund"
LV_ART = "Art"
LV_SCHWERE = "Schwere"
LV_FRAGE = "Frage"
LV_ERLAEUTERUNG = "Erläuterung"
LV_BLATT = "Blatt"
LV_ZEILE = "Zeile"
LV_KURZTEXT = "Kurztext"
LV_MENGE = "Menge"
LV_EINHEIT = "Einheit"
# In the columns "Blatt" and "Zeile" when a cited item does not stand in items.json.
LV_NICHT_GEFUNDEN = "steht nicht in items.json"

# ---- 3. Risikobericht (.html, daraus .pdf) -----------------------------------

BERICHT_TITEL = "Risikobericht"
BERICHT_UNTERTITEL = "Projekt {projekt} · Stand {datum}"

BERICHT_ZUSAMMENFASSUNG = "Zusammenfassung"
BERICHT_LISTEN = "Leistungsverzeichnisse (Listen)"
BERICHT_POSITIONEN = "Positionen"
BERICHT_FUNDE = "Funde"
BERICHT_DAVON = "Bewertung der Funde"
# Shown under the numbers only when the lists hold headings or preliminary notes.
BERICHT_EINTRAEGE = (
    "Nicht als Positionen gezählt: Überschriften {ueberschriften}, Vorbemerkungen {vorbemerkungen}."
)
# Shown only when the review file holds reviews of findings that the current findings file no longer holds.
BERICHT_BEWERTUNG_OHNE_FUND = (
    "Bewertungen zu Funden, die in der aktuellen Datei der Funde nicht mehr stehen: {anzahl}. "
    "Sie sind in diesem Bericht nicht gezählt."
)
BERICHT_OHNE_POSITIONEN = (
    "Die Datei items.json fehlt oder ist nicht lesbar; die Zahl der Listen und Positionen ist deshalb nicht bekannt."
)
BERICHT_UNBEKANNT = "nicht bekannt"

BERICHT_WICHTIGSTE_FUNDE = "Die wichtigsten Funde"
BERICHT_WICHTIGSTE_FUNDE_HINWEIS = "Bestätigte Funde, geordnet nach der Schwere: hoch, mittel, Hinweis."
BERICHT_LEER = "Es gibt noch keinen bestätigten Fund."
BERICHT_ART = "Art"
BERICHT_SCHWERE = "Schwere"
BERICHT_FUND = "Fund"
BERICHT_ERLAEUTERUNG = "Erläuterung"
BERICHT_KOMMENTAR = "Kommentar des Prüfers"
BERICHT_SCHAETZUNG = "Schätzung des Prüfers"
BERICHT_EURO = "{betrag} €"

BERICHT_METHODE = "Methode"
# Three or four sentences. No number, and nothing about who checked what: that stands next to each finding.
BERICHT_METHODE_SAETZE = (
    "Alle Leistungsverzeichnisse des Projekts werden als ein Projekt gelesen, nicht jede Liste für sich.",
    "Zwischen den Gewerken werden Kandidaten gesucht: doppelt ausgeschriebene Leistungen, Widersprüche "
    "und Lücken. Jedes Zitat prüft das Programm gegen den Text der zitierten Position oder Seite der Liste.",
    "Ein zweiter, unabhängiger Durchgang versucht, jeden Fund zu widerlegen. Eine Zahlenregel im Programm "
    "stuft einen Fund herab, wenn eine Zahl in seiner Erläuterung oder Frage in keinem Zitat und in keiner "
    "zitierten Position steht. Zuletzt bestätigt oder "
    "verwirft ein Prüfer die Funde; seine Rolle steht bei jedem Fund so, wie sie in der Bewertung "
    "eingetragen ist.",
    "Die Analyse zwischen den Gewerken ist vorab berechnet; dieser Bericht rechnet sie nicht neu.",
)

BERICHT_MESSUNG = "Messung"
BERICHT_MESSUNG_HINWEIS = "Dieser Kasten zeigt nur Zahlen, die in den Dateien des Projekts stehen."
BERICHT_MESSUNG_ZAEHLUNG = "Gelesen"
BERICHT_MESSUNG_BEWERTUNG = "Bewertung"
BERICHT_MESSUNG_GEGENPRUEFUNG = "Gegenprüfung (zweiter Durchgang und Zahlenregel)"
# {anzahl} = {durchgang} + {regel}: weakened by the second pass, and lowered by the number rule after the pass left it standing.
BERICHT_MESSUNG_ABGESCHWAECHT = (
    "{anzahl} abgeschwächt ({durchgang} vom zweiten Durchgang abgeschwächt, {regel} von der Zahlenregel herabgestuft)"
)
BERICHT_MESSUNG_LAUF = "Messlauf"
# Shown above the lines when they come from the committed bench/results/bench.json.
BERICHT_MESSUNG_GESPEICHERT = "Gespeicherter Messlauf aus dem Repository, nicht auf diesem Rechner gemessen."
BERICHT_MESSUNG_FEHLT = "Die Messung ist noch nicht gelaufen."
BERICHT_MESSUNG_UNLESBAR = (
    "Die Datei bench.json ist nicht lesbar. Zahlen aus dem Messlauf werden deshalb nicht gezeigt."
)

BERICHT_SCHLUSS = (
    "Dieser Bericht ist keine Rechtsberatung. Er nennt keine Preise aus den Listen; "
    "ein Betrag in Euro steht nur dort, wo der Prüfer eine Schätzung eingetragen hat."
)
