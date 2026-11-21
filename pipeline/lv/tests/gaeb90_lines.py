"""Builders for hand-written GAEB 90 lines (test helper, invented values only)."""

MASK = "1122PPPPI"


def line(kind, payload="", number=1):
    """One 80 character line: record type, payload, line number."""
    return (kind + payload).ljust(74)[:74] + "%06d" % number


def header(stage="83L", project="P-TEST-1", mask=MASK):
    return "00" + " " * 8 + stage.ljust(3) + " " * 15 + project.ljust(34) + mask.ljust(9) + "90"


def item(number, quantity="00000001000", unit="St", flags="NNN", repeat=" "):
    return "21" + number.ljust(9) + flags + " " * 6 + repeat + " " * 2 + quantity + unit


def prices(number, unit_price, total, quantity=""):
    return "23" + number.ljust(9) + " " + unit_price.ljust(11) + " " + total + " " + quantity


def end(items, total=""):
    return ("99" + total).ljust(69) + "%05d" % items


def build(records, encoding="cp850", newline="\r\n"):
    """Number the records and return the file bytes."""
    lines = [(record.ljust(74)[:74] if len(record) <= 74 else record) + "%06d" % index
             for index, record in enumerate(records, 1)]
    return (newline.join(lines) + newline).encode(encoding)
