"""The written record docs/TWINS.md from the summary of pipeline.diff.pairs.

render(summary) returns the whole file as text. Every number in it is read
from the summary; the fixed sentences hold none. The record holds counts,
item numbers, section titles and short item titles; no price, no long text.
"""
from pipeline.diff import pdftext
from pipeline.diff import text as textcmp

MAX_NUMBERS = 60
TEXT_FIELDS = ("short_text", "long_text", "text")
FIELD_NAMES = {
    "short_text": "short text", "long_text": "long text",
    "text": "whole text of A against long text of B",
    "quantity": "quantity", "unit": "unit", "unit_price": "unit price", "total": "total",
}
CLASS_NAMES = {
    textcmp.LAYOUT: "layout", textcmp.ANONYMIZED_BOTH: "anonymization, both",
    textcmp.ANONYMIZED_ONE: "anonymization, one side", textcmp.MARKS: "marks",
    textcmp.START: "start", textcmp.DIFFERS: "differs",
}
PAIR_TITLES = {
    "t1_offer_pdf_d84": "T1: offer AN24-0305, PDF against D84",
    "t2_print_pdf_x83_fields": "T2: PROJEKT_004, print PDF against X83, field against field",
    "t2_print_pdf_x83": "T2: PROJEKT_004, print PDF against X83, printed text against the X83 long text",
    "t3_x83_d83": "T3: 8209.003, X83 against D83",
    "t3_tender_d83_order_d86": "T3: 8209.003 tender (D83) against the order LV24069.D86",
    "t3_tender_x83_order_d86": "T3: 8209.003 tender (X83) against the order LV24069.D86",
    "stbalv_offer_d84_order_d86": "StBALV23040: offer D84 against order D86",
    "t4_nummer001_x83_stbalv_d84": "T4: NUMMER_001 X83 against StBALV23040.D84",
    "t4_nummer001_x83_stbalv_d86": "T4: NUMMER_001 X83 against StBALV23040.D86",
}
PAIR_NOTES = {
    "t1_offer_pdf_d84": "The D84 holds no short text and a long text for few items (line B; "
                        "some of them hold only a fill-in line without a letter or digit). So the "
                        "texts of this twin cannot be compared beyond the pairs counted under "
                        "long text.",
    "t2_print_pdf_x83_fields": "Listed to show why the next comparison is the one that counts: the "
                               "print does not show the X83 short text, its first printed line is "
                               "the start of the X83 long text.",
    "t2_print_pdf_x83": "Basis: the whole printed text of an item (what the PDF reader gives as "
                        "short and long text) stands against the long text of the X83 item. The "
                        "X83 short text is not compared; the print does not show it.",
}


def numbers(items, limit=MAX_NUMBERS):
    """Item numbers as one line; a long list is cut and says so."""
    if not items:
        return "none"
    shown = ", ".join(items[:limit])
    if len(items) > limit:
        shown += " and %d more (all in the result file)" % (len(items) - limit)
    return shown


def table(head, rows):
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join(" --- " for _ in head) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell).replace("|", "/") for cell in row) + " |")
    return lines


def file_line(side, entry):
    counts = entry["counts"]
    line = ("%s: `%s` (%s): %d items, %d sections; with short text %d, with long text %d, "
            "with quantity %d, with unit %d, with unit price %d"
            % (side, entry["file"], entry["what"], counts["items"], counts["sections"],
               counts["with_short_text"], counts["with_long_text"], counts["with_quantity"],
               counts["with_unit"], counts["with_unit_price"]))
    if counts["with_text_of_no_word"]:
        line += "; text without a letter or digit %d" % counts["with_text_of_no_word"]
    if counts["placeholder_numbers"]:
        line += "; item numbers replaced by the anonymizer: %s" % numbers(counts["placeholder_numbers"])
    return line + "."


def pair_block(summary, entry):
    """Lines for one pair: files, matching, field tables, unequal items."""
    result = entry["result"]
    matching = result["matching"]
    lines = ["### " + PAIR_TITLES[entry["id"]], "",
             "Result file: `out/diff/%s.json` (mode %s)." % (entry["id"], result["mode"]), "",
             "- " + file_line("A", summary["files"][entry["a"]]),
             "- " + file_line("B", summary["files"][entry["b"]])]
    if entry["id"] in PAIR_NOTES:
        lines.append("- " + PAIR_NOTES[entry["id"]])
    lines.append("- Items in both: %d (by number %d, by position %d, by text under another number %d)."
                 % (matching["both"], matching["by_number"], len(matching["by_position"]),
                    len(matching["renumbered"])))
    for pair in matching["by_position"]:
        lines.append("- Paired by position, because the number is an anonymization placeholder: "
                     "A %s with B %s." % (pair["a"], pair["b"]))
    for pair in matching["renumbered"]:
        lines.append("- Renumbered (same text): A %s is B %s." % (pair["a"], pair["b"]))
    lines.append("- Only in A: %d (%s)." % (len(matching["only_a"]), numbers(matching["only_a"])))
    lines.append("- Only in B: %d (%s)." % (len(matching["only_b"]), numbers(matching["only_b"])))
    duplicates = matching["duplicate_numbers"]
    if duplicates["a"] or duplicates["b"]:
        lines.append("- Numbers that stand twice: A %s; B %s."
                     % (numbers(duplicates["a"]), numbers(duplicates["b"])))
    sections = result["sections"]
    line = ("- Sections: A %d, B %d, in both %d; titles compared %d, the same or the same up to "
            "anonymization %d" % (sections["a"], sections["b"], sections["both"],
                                  sections["titles"]["compared"], sections["titles"]["equal"]))
    if sections["titles"]["not_equal_items"]:
        line += "; not the same (other text, or one is the start of the other) in %s" % numbers(sections["titles"]["not_equal_items"])
    lines.append(line + ".")
    lines.append("")
    fields = result["fields"]
    text_rows, value_rows, unequal = [], [], []
    for name, field in fields.items():
        lacks = [field["missing_a"], field["missing_b"], field["missing_both"]]
        if name in TEXT_FIELDS:
            text_rows.append([FIELD_NAMES[name], field["compared"], field["equal"]]
                             + [field[cls] for cls in textcmp.CLASSES[1:]] + lacks)
            for cls in textcmp.CLASSES[1:]:
                if field[cls]:
                    unequal.append("- %s, %s (%d): %s." % (FIELD_NAMES[name], CLASS_NAMES[cls],
                                                         field[cls], numbers(field[cls + "_items"])))
        else:
            value_rows.append([FIELD_NAMES[name], field["compared"], field["equal"],
                               field["not_equal"]] + lacks)
            if field["not_equal"]:
                unequal.append("- %s, not equal (%d): %s." % (FIELD_NAMES[name], field["not_equal"],
                                                            numbers(field["not_equal_items"])))
    lines += table(["text field", "compared", "equal"]
                   + [CLASS_NAMES[cls] for cls in textcmp.CLASSES[1:]]
                   + ["A lacks", "B lacks", "both lack"], text_rows)
    lines.append("")
    lines += table(["field", "compared", "equal", "not equal", "A lacks", "B lacks", "both lack"],
                   value_rows)
    lines.append("")
    if unequal:
        lines.append("Item numbers (as A writes them) that are not equal:")
        lines.append("")
        lines += unequal
        lines.append("")
    return lines


def changed_cell(result, name):
    """Count of changed items of a stage result, or why there is none."""
    stage, fields = result["stage"], result["fields"]
    if name == "price":
        compared = fields["unit_price"]["compared"] + fields["total"]["compared"]
    elif name == "text":
        compared = sum(fields[field]["compared"] for field in fields if field in TEXT_FIELDS)
    else:
        compared = fields[name]["compared"]
    return len(stage["changed"][name]) if compared else "not compared"


def stage_table(entries):
    rows = []
    for entry in entries:
        result = entry["result"]
        stage = result["stage"]
        rows.append([PAIR_TITLES[entry["id"]], result["a"]["items"], result["b"]["items"],
                     result["matching"]["both"], len(stage["added"]), len(stage["removed"]),
                     len(stage["renumbered"])]
                    + [changed_cell(result, name) for name in ("quantity", "unit", "text", "price")])
    return table(["pair (A earlier, B later)", "A items", "B items", "in both", "added", "removed",
                  "renumbered", "quantity changed", "unit changed", "text changed",
                  "price changed"], rows)


def first_items_table(first):
    rows = []
    for item in first:
        rows.append([item["a"], item["b"] or "-", item["matched"] or "-", item["title"] or "-",
                     CLASS_NAMES.get(item["short_text"], item["short_text"]) or "not compared",
                     item["quantity"] or "not compared", item["unit"] or "not compared"])
    return table(["A number", "B number", "paired by", "title in A", "short text", "quantity",
                  "unit"], rows)


def hypothesis_block(summary):
    data = summary["hypothesis_38"]
    expected = data["expected"]
    lines = ["## The 38-item hypothesis", "",
             "Hypothesis (plan §4, point 4): %d items were tendered (8209.003), %d were ordered "
             "(LV24069.D86), so %d items were added after the tender."
             % (expected["tendered"], expected["ordered"], expected["added"]), "",
             "**Answer: %s.**" % data["verdict"], "",
             "Decided by item number (item_no_key) and by text (an item of the order that has "
             "no number partner is searched by its whole text under every other number), once "
             "per format of the tender:", ""]
    rows = []
    for run in data["runs"]:
        rows.append([PAIR_TITLES[run["pair"]], run["tendered"], run["ordered"], run["in_both"],
                     len(run["added"]), len(run["removed"]), len(run["renumbered"]),
                     run["changed"]["quantity"], run["changed"]["unit"], run["changed"]["text"],
                     run["added_with_a_title_of_the_tender"]])
    lines += table(["pair", "tendered", "ordered", "in both", "added", "removed", "renumbered",
                    "quantity changed", "unit changed", "text changed",
                    "added items with a short text of the tender"], rows)
    run = data["runs"][0]
    lines += ["", "What holds: %d added, %d removed, %d renumbered." % (
        len(run["added"]), len(run["removed"]), len(run["renumbered"])), "",
        "The added items (%d): %s." % (len(run["added"]), numbers(run["added"], limit=10 ** 6)), ""]
    sections = ", ".join("%s %s" % (section["item_no"], section["title"])
                         for section in run["sections_only_in_order"])
    lines += ["The W11 fact, tested: the order holds %d items with quantity 0, and %d items with "
              "quantity 0 and total 0. These are the added items: %s. Of the %d added items, %d "
              "have quantity 0, %d have no unit, %d have no long text, %d hold a unit price field."
              % (run["order_items_quantity_zero"], run["order_items_quantity_zero_and_total_zero"],
                 "yes, the same set of numbers" if run["zero_items_are_the_added_items"] else "no",
                 len(run["added"]), run["added_with_quantity_zero"], run["added_without_unit"],
                 run["added_without_long_text"], run["added_with_unit_price"]), "",
              "The added items stand in %d sub-sections (%s); the order has %d sections that the "
              "tender does not have: %s. The tender has %d sections that the order does not have."
              % (len(run["added_sections"]), ", ".join(run["added_sections"]),
                 len(run["sections_only_in_order"]), sections or "none",
                 len(run["sections_only_in_tender"])), ""]
    in_pdf = data["added_titles_in_tender_pdf"]
    lines += ["Cross-check with the tender PDF `%s` (see T5): of the added items, %d short texts "
              "stand in the PDF as written, %d when hyphens are ignored too, %d only with "
              "anonymization allowed, %d do not stand there, %d cannot be searched (the short "
              "text is only a placeholder)."
              % (summary["pdfs"]["hem_pdf"], in_pdf[pdftext.FOUND_AS_WRITTEN],
                 in_pdf[pdftext.FOUND_LAYOUT], in_pdf[pdftext.FOUND_ANONYMIZED],
                 in_pdf[pdftext.NOT_FOUND], in_pdf[pdftext.NOT_SEARCHABLE]), ""]
    if data["verdict"] == "confirmed" and all(run["zero_items_are_the_added_items"]
                                              for run in data["runs"]):
        lines += ["What it means: the difference between tender and order is only the appended "
                  "supplement sections named above. No tendered item was removed or renumbered; "
                  "the items in both files are compared in the V2 table (quantity, unit, text). "
                  "The order file writes the added items with quantity 0, without unit and with "
                  "total 0, so they are listed in the order but add nothing to its quantities or "
                  "to its sum as the file states them. Whether they were ordered at their unit "
                  "price cannot be read from this file.", ""]
    else:
        lines += ["What it means: the hypothesis does not hold as stated; the counts above say "
                  "what holds instead.", ""]
    return lines


def t4_block(summary):
    lines = ["## T4: NUMMER_001 against StBALV23040", "",
             "Hypothesis: the first items of `%s` and of the two StBALV23040 files are the same. "
             "Rule: \"holds\" when the lists are the same from their first item on for at least "
             "%d items (number, and quantity, unit and short text where both files hold them; "
             "the table gives the length of that run); \"%s\" when the pair has no text and no "
             "quantity to compare."
             % (summary["files"]["n1_x83"]["file"], summary["rules"]["t4_first_items"],
                "cannot be decided with the readers we have"),
             ""]
    entries = [entry for entry in summary["pairs"] if entry["group"] == "t4"]
    rows = []
    for entry in entries:
        result = entry["result"]
        start = result["from_start"]
        rows.append([PAIR_TITLES[entry["id"]], "**%s**" % entry["verdict"],
                     start["same_from_start"], start["stopped_at"] or "-",
                     start["pairs_with_text_or_quantity"], result["matching"]["both"],
                     len(result["matching"]["only_a"]), len(result["matching"]["only_b"])])
    lines += table(["pair", "answer", "items the same from the start", "run ends at A item",
                    "pairs with text or quantity", "in both", "only in A", "only in B"], rows)
    lines.append("")
    for entry in entries:
        lines += pair_block(summary, entry)
        lines += ["The first items of A and their partners in B:", ""]
        lines += first_items_table(entry["result"]["from_start"]["first"])
        lines.append("")
    return lines


def percent(part, whole):
    """part of whole in percent with one decimal, cut off (not rounded up)."""
    if not whole:
        return "-"
    tenths = part * 1000 // whole
    return "%d.%d" % (tenths // 10, tenths % 10)


def t5_strength(summary, entry):
    """One sentence on what a "holds" rests on, when the titles found as
    written or with hyphens ignored would not meet the rule alone."""
    found = entry["result"]
    only = found["counts"][pdftext.FOUND_ANONYMIZED]
    without = found["found_total"] - only
    holds = summary["rules"]["t5_holds_percent"]
    if entry.get("verdict") != "holds" or without * 100 >= holds * found["searchable"]:
        return []
    return ["How strong the answer is: \"holds\" for `%s` against `%s` rests on the %d titles "
            "found only with anonymization allowed (%d of the %d found titles; without them %d "
            "of %d searchable titles, %s percent, are found, which is below the %d percent of "
            "the rule), and in %d of these %d the title in the PDF begins with a placeholder (a "
            "placeholder follows the item number on a page), so their first word cannot be "
            "compared."
            % (summary["pdfs"][entry["pdf"]], summary["files"][entry["list"]]["file"], only,
               only, found["found_total"], without, found["searchable"],
               percent(without, found["searchable"]), holds,
               len(found["placeholder_title"]), only), ""]


def t5_block(summary):
    rules = summary["rules"]
    lines = ["## T5: PDF files without a reader", "",
             "Hypothesis: `%s` is the list of `%s`, and `%s` is the list of 8209.003. No reader "
             "exists for these two layouts, so no item is read from the PDF. Instead the short "
             "text of every item of the GAEB file is searched in the page text of the PDF "
             "(pipeline/diff/pdftext.py). Quantities and units are not checked."
             % (summary["pdfs"]["leer_pdf"], summary["files"]["n1_x83"]["file"],
                summary["pdfs"]["hem_pdf"]), "",
             "The columns, each title counted once, in the first column that applies:", "",
             "- searchable: the items whose short text has enough characters outside "
             "anonymization placeholders to be searched (the others would be found anywhere).",
             "- found as written: the short text stands on a page letter for letter; both texts "
             "are normalized as pipeline/common/quotes.py does, and blanks and line breaks are "
             "left out, because the print breaks a title inside a word. A placeholder in the "
             "short text must stand in the PDF as the same placeholder.",
             "- found, hyphens ignored too: not as written, but letter for letter once hyphens "
             "are left out of both texts as well.",
             "- found, only with anonymization allowed: neither of the two, but it stands there "
             "when placeholders are allowed to differ, by this rule (characters are counted "
             "without blanks and hyphens). (1) A placeholder of the title stands for a "
             "placeholder or for 1 to %(t5_max_span)d characters of the PDF; so one at the "
             "beginning or end of the title stands for whatever the PDF holds there, also a "
             "placeholder. (2) A placeholder of the PDF stands for a placeholder of the title, "
             "or for 1 to %(t5_max_span)d characters and placeholders of it, but never for the "
             "first or the last character of the title. (3) One piece of the title stands in "
             "the PDF letter for letter and the rest is laid to both sides of it by 1 and 2: a "
             "whole run between two placeholders (of %(t5_min_run)d characters or more, or the "
             "longest run when all are shorter), or the first or the last %(t5_anchor)d "
             "characters of a run longer than %(t5_long_run)d. (4) A title that begins with a "
             "placeholder joined to a word (list: \"[..]-Blindflansch DN 50\") is also found "
             "where one placeholder of the PDF stands for that placeholder and its word "
             "together and the rest of the title, %(t5_min_run)d characters or more, follows by "
             "1 and 2 (PDF: \"[..] DN 50\"); the same at the end of a title. So a title whose "
             "first or last word is plain is not found where the PDF holds a placeholder for "
             "that word; a title whose first or last word is or holds a placeholder is found "
             "also where the PDF holds a placeholder there." % rules,
             "- found in all: the sum of the three columns before it; the percent is of "
             "\"searchable\" (percents have one decimal and are cut off, not rounded).",
             "- in order: the longest row of found titles whose pages do not go back when the "
             "items are taken in file order; the percent is of \"found in all\".",
             "- The control rows search the list of the other project in the same PDF: they "
             "show how many titles are found by chance.", "",
             "Rule: \"holds\" when \"found in all\" is at least %d percent of \"searchable\" and "
             "\"in order\" is at least %d percent of \"found in all\"; \"does not hold\" when "
             "\"found in all\" is below %d percent of \"searchable\"; otherwise \"cannot be decided "
             "with the readers we have\". The X83 and the D83 of 8209.003 are the same list (T3 "
             "above) but the anonymizer replaced other words in each of them and in the PDF, so "
             "their counts differ."
             % (rules["t5_holds_percent"], rules["t5_holds_percent"],
                rules["t5_does_not_hold_percent"]), ""]
    rows = []
    for entry in summary["text_pairs"]:
        found = entry["result"]
        counts = found["counts"]
        answer = "**%s**" % entry["verdict"] if "verdict" in entry else "(%s)" % entry["role"]
        rows.append(["`%s`" % summary["pdfs"][entry["pdf"]],
                     "`%s`" % summary["files"][entry["list"]]["file"], answer, found["pages"],
                     found["items"], found["searchable"], counts[pdftext.FOUND_AS_WRITTEN],
                     counts[pdftext.FOUND_LAYOUT], counts[pdftext.FOUND_ANONYMIZED],
                     found["found_total"], percent(found["found_total"], found["searchable"]),
                     counts[pdftext.NOT_FOUND], found["in_order"],
                     percent(found["in_order"], found["found_total"]),
                     "%s to %s" % (found["first_page"], found["last_page"])
                     if found["first_page"] else "-"])
    lines += table(["PDF", "list", "answer", "PDF pages", "items", "searchable", "found as written",
                    "found, hyphens ignored too", "found, only with anonymization allowed",
                    "found in all", "percent of searchable", "not found", "in order",
                    "percent of found in all", "pages with titles"], rows)
    lines.append("")
    for entry in summary["text_pairs"]:
        lines += t5_strength(summary, entry)
    for entry in summary["text_pairs"]:
        if entry["role"] == "control":
            continue
        found = entry["result"]
        lines += ["### `%s` in `%s`" % (summary["files"][entry["list"]]["file"],
                                       summary["pdfs"][entry["pdf"]]), "",
                  "Result file: `out/diff/%s.json`." % entry["id"], "",
                  "- Not found (%d): %s." % (found["counts"][pdftext.NOT_FOUND],
                                             numbers(found["numbers"][pdftext.NOT_FOUND])),
                  "- Not searchable, the short text is too short outside placeholders (%d): %s."
                  % (found["counts"][pdftext.NOT_SEARCHABLE],
                     numbers(found["numbers"][pdftext.NOT_SEARCHABLE])), "",
                  "The first items of the list:", ""]
        lines += table(["item", "title", "result", "PDF page"],
                       [[item["item_no"], item["title"] or "-", item["result"].replace("_", " "),
                         item["page"] or "-"] for item in found["first"]])
        lines.append("")
    return lines


def answers_block(summary):
    lines = ["## Answers", "",
             "- 38-item hypothesis: **%s** (details below)." % summary["hypothesis_38"]["verdict"]]
    for entry in summary["pairs"]:
        if entry["group"] == "t4":
            lines.append("- %s: **%s**." % (PAIR_TITLES[entry["id"]], entry["verdict"]))
    for entry in summary["text_pairs"]:
        if "verdict" in entry:
            lines.append("- T5: `%s` is the list of `%s`: **%s** (by item titles only)."
                         % (summary["pdfs"][entry["pdf"]],
                            summary["files"][entry["list"]]["file"], entry["verdict"]))
    lines.append("")
    return lines


HEAD = """# Twins and stage differences (W13, checks V1 and V2)

This file is written by `python -m pipeline.diff.pairs` from the organizer files in `data/`.
Do not edit it by hand: the real-data test `pipeline/diff/tests/test_diff_real_data.py`
compares it with a fresh run. It holds counts, item numbers, section titles and short item
titles. It holds no price: unit prices and totals are compared by code and only counted as
equal or not equal.
"""

HOW = """## How to read the tables

Items are paired by item number (`item_no_key` of pipeline/lv/model.py: `01.01.0010` and
`1.1.10` are the same number). Headings and preliminary notes are not items. An item whose
number the anonymizer replaced is kept as written and can only be paired by position. The
XML field `line` is not used.

Texts are normalized as pipeline/common/quotes.py does and then fall into one class:

- equal: the same text.
- layout: the same when blanks, line breaks and hyphens are ignored.
- anonymization, both: the only differences are anonymization placeholders that both files
  hold and write differently (the anonymizer ran per file).
- anonymization, one side: as before, and at least one placeholder stands where the other
  file holds plain words. What the placeholder hides is not known; this is not counted as
  equal and not as a reader error.
- marks: the same (or the same up to anonymization) once square brackets and the marks that
  a GAEB 90 file writes around a text supplement are left out.
- start: one text is the start of the other.
- differs: anything else.

"compared" counts the pairs in which both files hold the field; the "lacks" columns count
the others. In a stage comparison "text changed" counts the classes start and differs.
"""

OPEN = """## Open points

- No reader was changed. No wrong reading of a reader was found in these pairs: every
  quantity and unit that both files of a twin hold is counted above. The texts counted as
  "differs" were looked at: in T1 the D84 holds a fill-in line where the PDF holds words; in
  T4 a D86 short text opens with a reference to the item before it, which the X83 does not
  write, or holds a placeholder that the anonymizer broke in two, and the long texts differ
  inside a text supplement.
- Anonymization limits every text comparison here: the same word can be a placeholder in one
  file and plain text in its twin. The classes "anonymization" say where; they do not say the
  texts are equal.
- An item number replaced by the anonymizer (named in the file lines above) cannot be checked
  by number against a file that has the real number; the pairing by position is a guess that
  the tables name.
- T5 is a title search, not a reading of the PDF: it does not check quantities or units. A
  reader for these two layouts would be needed for that.
- The offer D84 of AN24-0305 holds prices and no item text; its text cannot be compared with
  the PDF.
"""


def render(summary):
    """The whole record as text."""
    lines = [HEAD]
    lines += answers_block(summary)
    lines += [HOW, "## V1: twin comparison (the same list in two formats)", ""]
    for entry in summary["pairs"]:
        if entry["group"] == "twin":
            lines += pair_block(summary, entry)
    stages = [entry for entry in summary["pairs"] if entry["group"] == "stage"]
    lines += ["## V2: stage difference (tender, offer, order of the same list)", ""]
    lines += stage_table(stages)
    lines.append("")
    for entry in stages:
        lines += pair_block(summary, entry)
        stage = entry["result"]["stage"]
        lines += ["- Added (%d): %s." % (len(stage["added"]), numbers(stage["added"])),
                  "- Removed (%d): %s." % (len(stage["removed"]), numbers(stage["removed"])),
                  "- Text changed (%d): %s." % (len(stage["changed"]["text"]),
                                              numbers(stage["changed"]["text"])),
                  "- Price not equal (%d): %s." % (len(stage["changed"]["price"]),
                                                 numbers(stage["changed"]["price"])), ""]
    lines += hypothesis_block(summary)
    lines += t4_block(summary)
    lines += t5_block(summary)
    lines.append(OPEN)
    return "\n".join(lines).rstrip("\n") + "\n"
