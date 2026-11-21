# PREREG - measurement plan (MASTER_PLAN §11)

**Status: LOCKED, 2026-11-21 04:45 (Europe/Berlin).** The lock is this commit. It was made before the first measured run of `python -m bench.run` (W14). After the lock nobody changes a threshold or a choice below; a choice that turns out wrong gets a dated line under "Deviations after the lock".

## Measurements and thresholds

| # | Measurement | How | Threshold |
|---|---|---|---|
| M1 | GAEB parsing | item count in the 9 files | 9/9 |
| M2 | Recalculation | quantity × unit price = total in the 4 priced GAEB files | every deviation is listed one by one |
| M3 | PDF ↔ GAEB twin | AN24-0305: matching items and prices; PROJEKT_004: 50 items | ≥ 98 % of items, ≥ 98 % of prices |
| M4 | PDF reader, 27 lists | same item count in two runs; 5 lists checked page by page | difference 0; what could not be read is stated openly |
| M5 | **Expert verdict** | labelled findings: confirmed, rejected, unclear | the numbers as they come out; headline evidence |
| M6 | Quote filter | number of findings dropped because a quote was not found | reported |
| M7 | Seeded errors (internal measurement) | B types: quantity ×10, unit change, corrupted amount, corrupted total, deleted item, duplicated item; for X: delete or change a known item | B ≥ 90 %; X is only reported |
| M8 | False alarms | `high` + `medium` findings per 100 items in a clean file | ≤ 5 |
| M9 | Speed | GAEB file with 300 items, base layer | ≤ 5 s |

## Rules

- The seed is fixed.
- The thresholds are locked before the run.
- Every result is written down as it comes out, also when it is below its threshold.
- M7 is at most one sentence in the pitch and is called "errors we seeded ourselves".
- No number is written that was not measured (plan K12).

## Open before the lock: fixed choices (filled at the lock)

What was known when these choices were made: the item counts of the plan (§4), the fields each GAEB file holds (how many positions have a quantity, a unit, a unit price, a total, a text; read once to see which error types can be planted where), the code of the base checks, and the T1 and T2 tables of W13 (`docs/TWINS.md` on its branch). No base check had been run by the bench on any GAEB file, and no M7 or M8 number had been seen.

- **Seed value:** 20261121. Used as `random.Random(20261121)`; one generator, the six types of M7 in the order given below.
- **Numbers:** a percentage is computed from the two counts and compared with its threshold without rounding. It is shown cut to one decimal (never rounded up). "Items" are positions: records that are not a heading and not a preliminary note.
- **Column "threshold met":** `yes`, `no`, `not measurable` (the data cannot give the number; the reason is written) or `not measured yet`. For M2, M5 and M6 the threshold is the reporting itself: `yes` when the numbers are in the table. A measurement with several parts (M3, M4, M9) is `yes` only when every measurable part meets its threshold; a part that is not measurable is named in the result.
- **M1, the 9 GAEB files and their expected item counts (plan §4):** `8209.003_Leistungsverzeichnis_leer.X83` 159 · `8209.003_Leistungsverzeichnis_leer.D83` 159 · `[ORT_024] LV24069.D86` 197 · `Angebot AN24-0305.D84` 274 · `StBALV23040.D84` 249 · `StBALV23040.D86` 249 · `[NUMMER_001]_leer.X83` 248 · `GAEB-[PROJEKT_004].X83` 50 · `501-24-01_GAEB-XML_sas.x83` 296. A file counts when the reader (`pipeline/lv`) reads it without an error and gives exactly that many items.
- **M2, the 4 priced GAEB files:** `[ORT_024] LV24069.D86`, `Angebot AN24-0305.D84`, `StBALV23040.D84`, `StBALV23040.D86`. Checked with `price_check` of `pipeline/lv/model.py` (tolerance half a cent). Checked = items with unit price, total and quantity. A priced item without a quantity cannot be checked and is counted as such, not as equal. A deviation is listed by file and item number, never by value.
- **M3, the pairs:** T1 `Angebot AN24-0305.pdf` against `Angebot AN24-0305.D84`; T2 `LV-Ausdruck-[PROJEKT_004].pdf` against `GAEB-[PROJEKT_004].X83`. Compared through `pipeline/diff` (W13). Percent of items = items in both files / items of the GAEB file; items only in the PDF are counted beside it. Percent of prices = the lower of (unit prices equal / unit prices compared) and (totals equal / totals compared), over the item pairs in which both files hold the field. When no pair holds a price on both sides, the price part is "not measurable" with the reason, not a percentage.
- **M4:** two runs = two times `pdftotext` and the 79-222 reader on the 27 `LV_*.pdf`, each into a fresh folder; difference = sum over the lists of the absolute difference of the item counts. The 5 lists of the page check are the ones `pipeline/pdf/pagecheck_lists.py` checks: `LV_18`, `LV_14c`, `LV_02`, `LV_17`, `LV_00`. `yes` needs difference 0 and 0 differences in the page check. Warnings and unparsed lines of the reader are counted in the result.
- **M5:** read from `reviews/79-222.json`. An entry counts as an expert decision when its `by` is not empty, does not contain "test" (any case), and its `at` lies in the expert session, Saturday 2026-11-21 10:00 to 14:00 (Europe/Berlin). The bench cannot tell more than that; it reports every `by` value it found with its counts, and the entries it did not count with the reason. No file or no counted decision: "not measured yet".
- **M6:** the committed findings `pipeline/cross/results/79-222/findings.json` through `pipeline/common/quotes.py`, against a fresh reader output and the page texts.
- **M7, seeded errors:** clean file = the one of M8. 20 errors per type, 6 types, 120 in all; when fewer than 20 items are eligible for a type, all eligible ones are taken and the planted count is shown. Each error is planted alone in its own copy of the reader output; the 12 base checks run on the copy. The items are drawn with the seed from the eligible items in file order. A planted error counts as found only when a finding of the fitting check and type names that item number in its sources and the unchanged file has no such finding for that item.
  1. Quantity ×10: a normal item with quantity above 0, unit price and total; the quantity is multiplied by 10 and the total is recomputed, so the list stays consistent. Fitting: B6 `quantity_outlier`.
  2. Unit change: a normal item with a unit; the unit becomes the next different unit in the sorted list of the units of the file (after the last, the first). Fitting: B5, any type.
  3. Corrupted amount: a normal item with quantity, unit price and a total of at least 1.00; the total is multiplied by 1.1 and cut to cents. Fitting: B1 `arithmetic_error`.
  4. Corrupted total: a section heading whose base items all have a total and sum to at least 1.00. The reader writes no stated sum (known gap of W3), so the bench writes the right sum into the heading of the copy and then multiplies it by 1.1, cut to cents. This measures B2 on the records, not the reader. Fitting: B2 `sum_mismatch` that names the heading.
  5. Deleted item: a position; its record is removed. Fitting: B3 `number_gap` whose two cited numbers enclose the deleted number.
  6. Duplicated item: a position; a copy of its record is put right after it. Fitting: B3 `duplicate_number` or B4 `repeated_item`.
  B rate = found / planted over the six types; the per-type counts are shown, also the low ones. X (cross-list findings): not measured by the bench. The X finder is a model pass; finding a deleted or changed item again needs a new model run, and the bench never runs a model.
- **M8, the clean file:** `StBALV23040.D86` (249 items). Why: no file in the data is known to be free of errors, so "clean" is a convention: an order-stage file (D86), the last stage after tender and offer, in which every position holds quantity, unit, unit price, total and text (needed to plant all six types of M7); of the two D86 files it is the larger one. Seen before the lock: the other D86 file, `[ORT_024] LV24069.D86`, has positions without a unit, so it does not meet the field rule. Its number is reported too, without a threshold, so that the choice hides nothing. Counted: findings of the 12 base checks after the severity rule of `pipeline/common/severity.py`, `high` plus `medium`, per 100 items. Every such finding counts as a false alarm; a real defect of the file would count too, so the number is an upper bound.
- **M9, file and machine:** the base layer (`run_all` of `pipeline/base/run.py`, all 12 checks) on records in memory; reading the file is not part of it and is timed beside it. No data file has exactly 300 items, so two inputs are timed: (a) a 300-item list built from `StBALV23040.D86`: its 249 items in file order, then copies of its first 51 items with the numbers 99.10, 99.20, … in a new section 99; (b) `501-24-01_GAEB-XML_sas.x83` as it is (296 items, no prices). Seconds = median of 5 runs in one process, no warm-up run. `yes` needs both medians at or below 5 s. Machine: the Devin cloud machine of the night run (Intel Xeon, 8 cores, 31 GB RAM, Ubuntu 22.04, Python 3.12); the run writes the machine it ran on into `bench/results/bench.json`.

## Deviations after the lock

- 2026-11-21: M9 was measured in a Docker box on a Mac limited to 4 CPUs and 6 GB, not on the machine named in the lock (the Devin cloud machine). The machine line of `bench/results/bench.json` (aarch64, 10 cores, 8 GB RAM, Linux linuxkit) is what the system inside the box reports; the limits of the box were 4 CPUs and 6 GB. The humans confirm this line.
- 2026-11-21, 16:30: M5: no expert session took place during the event (none was found in the window of Saturday 10:00 to 14:00). The window and the counting rule stay as locked; only the reason text of a missing review file changed from "not measured yet: the expert session is Saturday 10:00 to 14:00" to "not measured: no expert session took place during the event" (`bench/prereg.py`, `bench/table.py`). The M5 record of `bench/results/bench.json` was measured again alone (no review file, so nothing counted); the other eight records are those of the run named in `measured_at`. Written by Claude on Mert's instruction; the humans confirm this line.
