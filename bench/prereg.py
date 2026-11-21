"""The fixed choices of docs/PREREG.md, as the code uses them.

docs/PREREG.md is the record; a test fails when a value here is not written
there. Nothing in this module may change after the lock. A choice that turns
out wrong is not edited: it gets a dated line under "Deviations after the
lock" in docs/PREREG.md.
"""
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREREG_PATH = os.path.join(REPO_ROOT, "docs", "PREREG.md")

SEED = 20261121

# M1: the 9 GAEB files and their expected item counts (plan §4).
GAEB_FILES = (
    ("8209.003_Leistungsverzeichnis_leer.X83", 159),
    ("8209.003_Leistungsverzeichnis_leer.D83", 159),
    ("[ORT_024] LV24069.D86", 197),
    ("Angebot AN24-0305.D84", 274),
    ("StBALV23040.D84", 249),
    ("StBALV23040.D86", 249),
    ("[NUMMER_001]_leer.X83", 248),
    ("GAEB-[PROJEKT_004].X83", 50),
    ("501-24-01_GAEB-XML_sas.x83", 296),
)
M1_NEEDED = 9

# M2: the 4 priced GAEB files.
PRICED_FILES = (
    "[ORT_024] LV24069.D86",
    "Angebot AN24-0305.D84",
    "StBALV23040.D84",
    "StBALV23040.D86",
)

# M3: twin, PDF, GAEB file. Thresholds in percent.
M3_PAIRS = (
    ("T1", "Angebot AN24-0305.pdf", "Angebot AN24-0305.D84"),
    ("T2", "LV-Ausdruck-[PROJEKT_004].pdf", "GAEB-[PROJEKT_004].X83"),
)
M3_ITEMS_PERCENT = 98
M3_PRICES_PERCENT = 98

# M4: the 27 lists of project 79-222; the 5 lists of the page check.
M4_PROJECT = "79-222"
M4_LISTS = 27
M4_PAGECHECK_LISTS = ("LV_18", "LV_14c", "LV_02", "LV_17", "LV_00")

# M5: the expert session, Munich time, as the review file writes it.
M5_PROJECT = "79-222"
M5_SESSION = ("2026-11-21T10:00", "2026-11-21T14:00")
M5_STATUSES = ("confirmed", "rejected", "unclear")
M5_NOT_YET = "not measured: no expert session took place during the event"

# M6: the committed findings.
M6_FINDINGS = os.path.join("pipeline", "cross", "results", "79-222", "findings.json")

# M7: seeded errors.
M7_PER_TYPE = 20
M7_PERCENT = 90

# M8: the clean file, and the other order-stage file reported beside it.
CLEAN_FILE = "StBALV23040.D86"
M8_OTHER_FILE = "[ORT_024] LV24069.D86"
M8_PER_100 = 5
M8_LEVELS = ("high", "medium")

# M9: speed.
M9_ITEMS = 300
M9_BUILT_FROM = CLEAN_FILE
M9_AS_IS_FILE = "501-24-01_GAEB-XML_sas.x83"
M9_RUNS = 5
M9_SECONDS = 5

# Column "threshold met".
YES, NO, NOT_MEASURABLE, NOT_YET = "yes", "no", "not measurable", "not measured yet"
MET_VALUES = (YES, NO, NOT_MEASURABLE, NOT_YET)

# The rows of the table: id, name, threshold as docs/PREREG.md words it.
ROWS = (
    ("M1", "GAEB parsing", "9/9"),
    ("M2", "Recalculation", "every deviation is listed one by one"),
    ("M3", "PDF ↔ GAEB twin", "≥ 98 % of items, ≥ 98 % of prices"),
    ("M4", "PDF reader, 27 lists", "difference 0; what could not be read is stated openly"),
    ("M5", "Expert verdict", "the numbers as they come out; headline evidence"),
    ("M6", "Quote filter", "reported"),
    ("M7", "Seeded errors (internal measurement)", "B ≥ 90 %; X is only reported"),
    ("M8", "False alarms", "≤ 5"),
    ("M9", "Speed", "≤ 5 s"),
)
