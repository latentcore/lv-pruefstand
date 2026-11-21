# Risk rules: the level of a finding (Schwere)

**Status: proposal for the expert session. No expert has confirmed these rules.** Until one has, the level only sorts the list of findings; it says nothing about money.

Every finding gets one of three levels: `high` (screen: "hoch"), `medium` ("mittel"), `info` ("Hinweis"). Code sets the level by the fixed rules below (`pipeline/common/severity.py`), never a model. **No rule uses a price or a total.** For the cost, the view "Fund" has the field "Einheitspreis": quantity × typed price = "€-Effekt".

## Inputs (the rules read nothing else)

1. **Finding type**: `check` of the finding (X1 "doppelt ausgeschrieben", X2 "Widerspruch", X3 "Lücke", S, B1 to B12, V1, V2).
2. **Cited items**: for each source of the finding the record in `items.json` with the same `doc` and `item_no`. If several records share them: the one whose text holds the quote, else the first that is no heading. A heading never counts. The `kind` of a cited item is `normal`, `optional` (Bedarfsposition), `alternative` (Wahlposition), `lump_sum` (Pauschale) or `preliminary_note` (Vorbemerkung). "Only in a preliminary note" means: every cited item is a Vorbemerkung.
3. **Quantity concerned** (betroffene Menge): `exposure.quantity` with `exposure.unit` of the finding, when it is above 0. Else the quantities above 0 of the cited `normal` items, each with its own unit: large if one of them is large, small only if all of them are small. Else unknown.
   - **large**: 10 or more for pieces (St, Stk, Stck, Stück); 100 or more for every other unit (m, m2, m3, kg, h, ...).
   - **small**: below 2 for pieces; below 10 for every other unit.

## Rules (read from the top; the first rule that fits decides)

| No. | The rule fits when | Level | Reason |
|---|---|---|---|
| 1 | the check is not in the catalogue (X1, X2, X3, S, B1 to B12, V1, V2) | `info` | No rule knows this type; a human looks at it. |
| 2 | the check is B3, B7, B9, B10, B11, B12 or V2 | `info` | Numbering, wording, flags, a question, a change between stages: a note, not an error by itself. |
| 3 | the check is B1 or B2 | `high` | The arithmetic of the list is wrong, so its sum cannot be trusted. |
| 4 | at least one item is cited and every cited item is a Vorbemerkung (preliminary_note) | `medium` | A Vorbemerkung binds the items below it, but no quantity says how much is affected. |
| 5 | at least one cited item is not a Vorbemerkung, and every such item is a Bedarfsposition or Wahlposition (optional, alternative) | `info` | These items are not part of the sum until the client orders them. |
| 6 | the quantity concerned is large | `high` | Much work is affected. |
| 7 | a cited item is a Pauschale (lump_sum) | `medium` | "1 psch" says nothing about the size, so a small quantity must not lower the level. |
| 8 | the quantity concerned is unknown | `medium` | The size cannot be read from the lists; the finding must not be hidden. |
| 9 | the quantity concerned is small | `info` | Little work is affected. |
| 10 | no rule above fits (the quantity concerned is between small and large) | `medium` | Neither much nor little work is affected. |

## Check by hand

Read `check` and `exposure` of the finding, look up each source in `items.json` and read `kind`, `quantity`, `unit`; then go down the table. Example: check X2, `exposure` 35 m2, two `normal` items. Rules 1 to 5 do not fit; 35 m2 is not large; no Pauschale; the quantity is known and not small: rule 10, `medium`.

Set the levels of a file: `python -m pipeline.common.severity <findings in> <items.json> <findings out>`. Only `severity` changes; the command prints the count per level and each finding whose level changed, with its rule.

## Open for the expert session (the team's guesses)

- The thresholds: one fixed pair (10 pieces, 100 of any other unit) for all trades.
- Rule 3: a sum error is always `high`, however small.
- Rule 4: a matter that stands only in a Vorbemerkung is `medium`, not `info` or `high`.
- Rule 5: a Wahlposition is treated like a Bedarfsposition.
- Rule 7: a Pauschale is `medium`, although the bidder carries its quantity risk.
