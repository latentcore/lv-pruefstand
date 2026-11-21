# pipeline/skeptic: the independent refute pass (W5b)

Second of the four filters of plan §8: finder, independent skeptic, quote check, human.
The pass tries to refute each finding against all lists and writes only the `skeptic`
field. It deletes nothing; a refuted finding stays in the file with status `refuted`.

## Commands

Run them from the repository root. `out/` and `cache/` stay out of git.

```
python -m pipeline.skeptic.evidence pipeline/cross/results/79-222/findings.json out/79-222/items.json \
    out/79-222/skeptic/evidence.json --terms pipeline/skeptic/results/79-222/terms.json
python -m pipeline.skeptic.rules pipeline/cross/results/79-222/findings.json out/79-222/items.json \
    pipeline/skeptic/results/79-222/verdicts.json pipeline/skeptic/results/79-222/verdicts.json \
    --text-dir cache/79-222_text
python -m pipeline.skeptic.merge pipeline/cross/results/79-222/findings.json \
    pipeline/skeptic/results/79-222/verdicts.json out/79-222/findings.json
```

1. `evidence` loads the findings with the `skeptic` key removed and the items with
   `unit_price` and `total` removed. For each finding it lists every entry of every list
   (items, headings, preliminary notes) in which one of the finding's `search_terms` or
   one of the added terms stands: doc, item number, page, kind, short text, quantity,
   unit, the terms and a snippet. It also names the lists without a hit.
2. `rules` runs the rule checks and writes `rules`, `rule_note` (one German line that
   names the rules that fired, "" when none did), `agent_status` and the final `status`
   into each verdict. status = agent_status, lowered where a rule says so;
   a rule never raises a status. Running it again on its own output changes nothing.
3. `merge` writes the findings with `skeptic` replaced by the verdict of the same id, so
   `skeptic.note` is the German `note` of the verdict; the review screen shows it.
   Count, order and every other key stay as they are. It stops with an error when a
   finding has no verdict, a verdict has no finding, a status is not allowed, a note is
   empty, or the result does not pass `contract/findings.schema.json`.

## Rule checks (`rules.py`)

- `unsupported_numbers`: a number in `explanation_de` or `question_de` that stands neither
  in a quote of the finding nor in a cited item of `items.json` (item number, texts,
  quantity). The finding becomes `weakened`. Sums the finder computed, numbers taken from
  an item that is not cited, and item or room numbers that are named but not cited all
  count. The names of the lists ("LV 18", "02, 06 und 07") and the number of lists
  searched do not. The exact token rules stand at the top of `rules.py`.
- `single_quote_contradiction`: a contradiction (check X2 or type `contradiction`) with
  fewer than two different quotes becomes `weakened`.
- `quotes_not_found`: a quote that stands neither in the cited item nor on the cited page
  (`pipeline/common/quotes.py`) is recorded with doc, item number and page. It does not
  change the status; dropping such a finding is the job of the quote check.

## Notes are German

The review screen is German (plan §7), so every text it can show is German:

- `note` in `verdicts.json`: the agent's reason, in the terms of the lists (Position,
  Vorbemerkung, Leistungsverzeichnis, Stückzahl). List names ("LV 13"), item numbers,
  quoted words, numbers and units stand as in the lists. Quantities and dimensions only,
  never a price.
- `rule_note`, written by `rules.py`: "Regelprüfung: " and then the parts that fired,
  joined by "; ": "Zahl ohne Beleg in einem Zitat oder in der zitierten Position: 13, 18",
  "Widerspruch mit nur einem Zitat", "Zitat nicht gefunden: LV_18 11.2 S. 1".

The agent session wrote its notes in English. `verdicts_notes_en.json` (id → note) keeps
these originals; the German notes are their translation, sentence by sentence, with
nothing judged anew. `tests/test_skeptic_notes_de.py` checks for each of the 24 notes
that the numbers (with their decimal marks), item numbers, list names and quoted words
equal those of the original, that the count of sentences and ";" clauses is the same,
and that no note holds one of these English words: the, and, is, are, only, no, not,
with, of, which, that, has, have, stands, but, for, from, its, this, these, to, or, by,
says, item, items, list, lists (one of them stands in every sentence of the originals).
It cannot check the meaning of a translated word; that is a human's reading.

## Results for 79-222 (`results/79-222/`)

- `verdicts.json`: one verdict per finding id. `agent_status` and `note` were written by
  the agent in an independent session (`origin`: "agent session, independent context"):
  the session loaded the findings without the `skeptic` key, did not read the finder's
  notes, and judged each finding from the evidence of step 1 and the item texts only.
  `status`, `rules` and `rule_note` were then set by `rules`. The `note` is the German
  translation of what the session wrote.
- `verdicts_notes_en.json`: the English originals of the notes, by finding id.
- `terms.json`: the search terms the skeptic added to those of the finder.
- `summary.json`: the reported counts. 24 findings: 11 survived, 13 weakened, 0 refuted.
  Before the rule checks the agent had 17 survived, 7 weakened, 0 refuted; the number
  rule lowered 6.

## Limits

- No finding was refuted. Where another list makes a claim doubtful (for example
  LV 00 3.1.470 for X3-153652) the claim itself still stands in the cited items, so the
  verdict is `weakened`.
- The number rule compares values only. It cannot tell whether a supported number is
  used with the right meaning, and it lowers a correct finding whose explanation holds a
  sum or a number from an item that is not cited (6 cases here; `agent_status` keeps the
  verdict before the rule).
- A term matches as a substring without regard to case, so a short term also hits inside
  longer words; the evidence is a reading list, not a proof.
- The verdicts are a model's reading of the lists, not an expert's. The expert session
  is the fourth filter.
