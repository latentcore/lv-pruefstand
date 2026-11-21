"""German export of the confirmed findings (W8, MASTER_PLAN §7 "Çıktılar").

    python -m web.export --project <name> [--out <dir>]

Three files from out/<name>/findings.json, out/<name>/items.json and
reviews/<name>.json: Fragen_und_Klaerungsliste.docx, LV_markiert.xlsx,
Risikobericht.html (and Risikobericht.pdf, printed by a headless Chrome).
Every fixed German text stands in web/export/texte_de.py.
"""
