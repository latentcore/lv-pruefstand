# reader_79222 - LV text reader for project 79-222

Usage (standard library Python 3, no network):

    python3 reader_79222.py TEXT_DIR OUT_DIR [PDF_DIR]
    python3 reader_79222.py --extract PDF_DIR TEXT_DIR   # needs pdftotext on PATH

Input: one `LV_<id>.txt` per list, made with `pdftotext -layout`; a line `=== PAGE n ===` starts page n. The doc id (`LV_18`, `LV_14c`) comes from the file name. With PDF_DIR the manifest gets the PDF file name and its sha256 (the PDF itself is not parsed).

Output in OUT_DIR:
- `items.json` - one record per item, heading and preliminary note (key order fixed, see `KEYS`); `price_mode` is added for "Nur Einh.-Pr." (`unit_price_only`) and "Bedarfsposition mit GB" (`in_total`).
- `manifest.json` - per list: pages, counts, `unparsed_lines` and concrete `warnings`.

How it reads: page header (up to the "in EUR" line) and footer (from "Druckdatum:") are dropped, as are "Übertrag:", "Summe" and closing lines. An OZ at column 0 starts an entry; the right-aligned quantity line closes it. A numbered entry without quantity is a heading when later numbers sit under it; its prose becomes a separate preliminary_note with the same item_no. Unnumbered text between items becomes a preliminary_note owned by the current section.

Tests: `python3 -m unittest` in this folder. Set `LV_TEXT_DIR` to the real text folder to also run the real-data checks; without it they are skipped.

Limits:
- Built for the print layout of this one tender software (79-222 "Anfrage"); other layouts need new rules.
- Short text is the first line only; a wrapped short text continues in long_text.
- A paragraph break that falls exactly on a page break is lost.
- unit_price and total are null in these blank tenders; the reader parses them only if numbers are printed.
- `line` is always null (page-based format).

# Rest of W2: page check, PROJEKT_004 print layout, offer layout

All three are checked by code only; no human page check was done for them.

## pagecheck_lists - 5 lists page by page against items.json

    python pipeline/pdf/pagecheck_lists.py data out/79-222/items.json out/79-222/pagecheck_lists.json pipeline/pdf/results/79-222/pagecheck_lists_summary.json

Lists: LV_18, LV_14c, LV_02, LV_17, LV_00 (115 pages). The check does not use the reader's text or line rules: it takes the words of each PDF page with their positions (PyMuPDF), finds the OZ, Menge and ME columns from the column header and reads item numbers, quantities and units by column position. Per page it says: every item the page shows is in `items.json` with that page; no item of `items.json` for that page is missing; quantity and unit are equal; headings and numbered notes too. Every difference is listed with list, page and item number. No price is read.

Result on the organizer files (`results/79-222/pagecheck_lists_summary.json`): 115 pages, 388 items on the pages, 388 in `items.json`, 388 matched, 388 with equal quantity and unit, 0 differences. 51 of the 388 items run over a page break: `items.json` gives the page of the item number, the quantity line stands on the next page. They are listed as `continued_items` with both pages, not counted as differences. The last page of each list has no column header (closing page or "Zusammenstellung"); it is read with the columns of the list and shows no item.

## reader_ausdruck - print layout of LV-Ausdruck-[PROJEKT_004].pdf

    python pipeline/pdf/reader_ausdruck.py "data/LV-Ausdruck-[PROJEKT_004].pdf" out/PROJEKT_004

Contract v1 items (format "pdf", stage "83") and one manifest entry. Result: 22 pages, 50 items (= the X83 twin), 4 headings, 5 notes, 0 unread lines. Page 1 (table of contents) and page 22 (sums) give no items; the section pages and titles are checked against the table of contents.

## reader_angebot - offer layout of Angebot AN24-0305.pdf

    python pipeline/pdf/reader_angebot.py "data/Angebot AN24-0305.pdf" out/AN24-0305

Contract v1 items (format "pdf", stage "84") and one manifest entry. Result: 27 pages, 274 items (= the D84 twin), 21 headings, 16 notes, 0 unread lines. Unit price and total go to `items.json` only; warnings name the page and the kind of line, never the line or an amount.

Both readers take the PDF (Poppler's `pdftotext` on PATH) or its `pdftotext -layout` text with `=== PAGE n ===` lines. `pdfio.py` holds their shared input and output steps.

Limits:
- Each reader is built for one print layout and was run on one file.
- The twin comparison here is the item count only; the item-by-item comparison is W13.
- The offer print shows "Hinweistext" lines without their text; they become notes with the title only.
- The offer print names no trade and the PROJEKT_004 print none either: `trade` is "".

Tests: `python -m pytest -q` in the repository root. `tests/test_w2_real_data.py` needs `data/` (or `LV_DATA_DIR`) and Poppler's `pdftotext`; without them it is skipped.
