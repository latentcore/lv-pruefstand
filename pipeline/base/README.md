# pipeline/base: base checks B1 to B12 (W3)

Twelve checks from plan §7, line "B · temel, kod (model yok)". Code only, no model,
standard library only. They read `items.json` and write findings, both in contract v1
shape (`contract/`). Ids come from `pipeline/common/ids.py`; every quote is item text and
passes `pipeline/common/quotes.py`.

## Command

Run it from the repository root. `out/` stays out of git.

```
python -m pipeline.base.run out/79-222/items.json out/79-222/base_findings.json
```

It runs all twelve checks on every document in the file, writes the findings and prints
one line per check: the check, the number of findings, and `not applicable` where a
document lacks the field the check needs. Other counts on a line: `merged` (findings that
went into another one with the same id), `no_quote` (nothing to quote, no finding written),
`dropped` (quote not found, finding not written), `priced_without_quantity`, `no_totals`,
`sum_not_checkable` (a stated sum over a base item without a total), `covered_by_note`. The output file is new; the command does not touch
`out/<project>/findings.json`.

## The checks

| Check | Fires when | Types | Severity | Not applicable when the document has |
|---|---|---|---|---|
| B1 | quantity × unit price is not the total | `arithmetic_error` | high | no item with unit price, total and quantity |
| B2 | a stated section sum or grand total is not the sum of the item totals | `sum_mismatch` | high | no heading with a total |
| B3 | an item number stands twice; the numbers do not rise; a number is missing in the row | `duplicate_number`, `number_out_of_order`, `number_gap` | medium, info, info | no numbered position |
| B4 | two positions have the same text (short and long) and the same unit | `repeated_item` | medium | no position with text |
| B5 | a unit is missing, is not in the unit list, or differs between positions with the same short text | `unit_missing`, `unit_unknown`, `unit_differs` | high, info, medium | no position with a unit |
| B6 | a quantity is missing, zero, negative, or 10 times off its siblings | `quantity_missing`, `quantity_zero`, `quantity_negative`, `quantity_outlier` | high, high, high, info | no position with a quantity |
| B7 | a unit price is zero or negative, or 10 times off its siblings | `unit_price_not_positive`, `unit_price_outlier` | info | no position with a unit price |
| B8 | a description has no word, or fewer than 3 words | `description_empty`, `description_short` | high, medium | text in fewer than half of the positions |
| B9 | lump-sum items reach 20 % of the positions or of the sum | `lump_sum_share` | medium | no position |
| B10 | an item is optional or alternative; or its text opens a line with such a word and its kind does not say so | `optional_item`, `alternative_item`, `flag_missing` | info, info, medium | no position |
| B11 | the text holds a phrase of the plan's dictionary | `vague_phrase` | medium or info | no text |
| B12 | the text names a product and has no "oder gleichwertig" | `product_without_equivalent` | medium | no text |

Rules that hold for all checks:

- A position is every record that is not a heading or a preliminary note. B11 and B12 also
  read preliminary notes. Unknown keys are ignored. A record without a document name is
  left out.
- "Not applicable" is decided per document. A tender list without prices gives no B1, B2
  or B7 finding.
- A finding about an optional or alternative item is one severity level lower: such an
  item is not part of the contract sum.
- Prices are used by code in B1, B2, B7 and B9 only. No explanation, question, quote or
  printed line holds a unit price or a total. `exposure` holds quantity and unit.
- A quote must stand in the cited item. An item without text is therefore cited through the
  nearest record with text (the one before it, else the one after it); the explanation
  names the item itself and ends with "Ohne eigenen Text; zitiert ist der nächste Eintrag
  mit Text." Findings of one check that get the same id this way are merged into one that
  keeps every explanation and question.
- B7 is a question only: the text says how the price stands to its siblings and asks; it
  never says the price is wrong.
- B10 `optional_item` and `alternative_item` are flags for the handover, not errors.
- `skeptic.status` is `not_run`: the refute pass covers the X checks.

## Thresholds

Each value stands once in `core.py`. No value was tuned to a count. `TEXT_DOC_SHARE` was added
after a run on a GAEB offer file showed that descriptions are not a field of such a file; the
other values were set before any count on real data was seen.

| Name | Value | Used in | Reason |
|---|---|---|---|
| `PRICE_TOLERANCE` | 0.005 | B1, B2 | Totals are printed in cents. A product such as 3 × 1.115 lies half a cent from both roundings; a difference of one cent or more is an error. Numbers are exact decimals, not floats. |
| `OUTLIER_FACTOR` | 10 | B6, B7 | The plan's wording: "10 times off its sibling items". It is the size of a slipped decimal point or a wrong unit. A value exactly 10 times off counts. |
| `OUTLIER_MIN_SIBLINGS` | 3 | B6, B7 | A median of one or two values is one item's word against another's. Siblings are the other positions of the same section with the same unit and a value above zero; lump sums are left out. |
| `SHORT_TEXT_MIN_WORDS` | 3 | B8 | A description needs at least what, of what, and how or where ("Estrich schwimmend verlegen"). One or two words ("Zulage Bogen") name a thing, not a work. A word is a run of two or more letters or digits; the same word counts once; short and long text count together. |
| `TEXT_DOC_SHARE` | 0.5 | B8 | An offer file carries prices and no descriptions; a few bidder remarks do not make them a field of the document. Below this share an empty description is "not applicable", not a finding. |
| `LUMP_SHARE` | 0.20 | B9 | From one item in five on, a visible part of the work has no quantity that can be measured or checked. The share is taken by count and, when every base item has a total, by value (optional and alternative items are not in the sum); either one fires. |
| `LUMP_MAX_SOURCES` | 5 | B9 | Enough quotes to open the list at the right places; the explanation gives the count of all. |
| `GAP_MIN_DIFFS` | 5 | B3 | A missing number is claimed only when the document has a clear numbering step: at least 5 steps between sibling numbers, more than half of them the same. The gap must be a whole multiple of that step. |
| `QUOTE_MAX` | 160 | all | Longest quote taken from an item (its short text, else the start of its text). |
| `SNIPPET_CONTEXT` | 60 | B10, B11, B12 | Characters kept on each side of a phrase, cut at blanks. |

## Dictionaries

- B11 (`text.VAGUE_PHRASES`): the eight phrases of the plan, each with its spelling variants:
  "nach Angabe(n) der Bauleitung", "nach Erfordernis", "ggf." / "gegebenenfalls", "ca." /
  "circa", "soweit erforderlich", "bauseits" / "bauseitig", "komplett" / "kompl." / "kpl.",
  "einschl. / einschließlich / inkl. / inklusive aller Nebenleistungen". "ggf.", "ca." and
  "komplett" are `info`, the others `medium`. One finding per record names all its phrases.
- B12 (`text.product_names`): a product is named by a trademark sign after a word (®, ™,
  (R), (TM)) or by a marker word (Fabrikat, Leitfabrikat, Richtfabrikat, Fabr., Hersteller,
  Herst., Erzeugnis, Produkt, Marke) followed by a name. After ":" or "=" any word that is
  not a placeholder counts; without one only "Fabrikat" or "Fabr." before a capitalized
  word does. "z.B." (also "z. B.", "zum Beispiel", "bspw.") before the name is passed over.
  An anonymisation token ([PERSON_n], [FIRMA_n]) after a marker word stands for a name the
  organizer took out and counts as a name, unless dots follow it. A marker the bidder fills
  in ("angebotenes Fabrikat: ....", "gew. Fabrikat", "Fabrikat: Bieterangabe")
  names no product. "oder gleichwertig" is also read as "o. glw.", "od. gleichw.". An item
  under a preliminary note that holds the clause (a note at the top, or one whose number
  starts the item's number) is not raised; the count is printed as `covered_by_note`.
- Units (`core._UNIT_WORDS`): spellings of one unit give one name ("Stk", "St.", "Stck");
  "m²", "m2" and "qm" are the same. Compound units such as "StWo" or "m2d" are known.
- Numbers (`core.to_decimal`): contract v1 gives numbers. A text is read as well:
  "1.234,56", "1,234.56", "12,5", "1.234" (groups of three digits), "1234.5".

## Tests

```
python -m pytest -q pipeline/base
python -m pytest -q -rP pipeline/base/tests/test_base_real_data.py
```

Every check has tests on hand-written items: a case that fires, a case that does not, and
the edge cases (missing field, zero, rounding at the cent, thousands separator). The
real-data test runs all twelve checks on every `out/*/items.json` it finds and is skipped
when there is none; the second command prints the count per check.

## Known gaps

- B2 reads a stated sum from the `total` of a heading record (no number = the whole
  document). No reader writes such a total yet, so B2 is "not applicable" on all real
  data so far and is proven on hand-written items only.
- B1 cannot check an offer file that has prices but no quantities; it does not look up
  the quantity in the tender file of the same project.
- B12 finds products by the signs above. A brand that stands in the text without a marker
  word or trademark sign is not found; there is no brand list.
- B4 compares the full text exactly (case and blanks aside); near-repeats are not found.
- B10 `flag_missing` looks only at a word that opens a line, so a reference such as
  "wie Bedarfsposition 1.20" is not taken for a flag.
