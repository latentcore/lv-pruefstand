# contract/ - contract v1

Contract v1 is MASTER_PLAN §8 as it is written (K9g). The pipeline writes these files; the app only reads them.

| File at run time | Schema | Sample |
|---|---|---|
| `out/<project>/items.json` (list) | `items.schema.json` | `samples/items.json` |
| `out/<project>/findings.json` (list) | `findings.schema.json` | `samples/findings.json` |
| `reviews/<project>.json` (object keyed by finding id) | `reviews.schema.json` | `samples/reviews.json` |
| `out/<project>/manifest.json` (list) | `manifest.schema.json` | `samples/manifest.json` |

The samples are hand-written and synthetic (project `11-111`); they hold no organizer data. The sha256 values in `samples/manifest.json` are placeholders, not hashes of real files.

## Rules

- Readers ignore keys they do not know (example: `price_mode` in `items.json`). Every key that §8 lists must be present; a value that does not apply is `null`.
- Value lists fixed by §8: `kind` = `normal`, `optional`, `alternative`, `lump_sum`, `preliminary_note`, `heading`; `layer` = `single_list`, `between_lists`, `between_stages`, `between_formats`; `format` = `pdf`, `gaeb90`, `gaebxml`, `xlsx`; `stage` = `anfrage`, `83`, `84`, `86`.
- Stable id: `check` + `-` + the first 6 hex digits of sha1(`check` | sorted `doc:item_no` pairs | normalized first quote). Code: `pipeline/common/ids.py`.
- Quote check: a quote must stand, after normalization, in the text of the cited item or of the cited page. Code: `pipeline/common/quotes.py`.
- A change beyond §8 is a [SORU] and waits for both humans.

## Check a file

```python
import json
from pipeline.common import contract

data = json.load(open("out/79-222/findings.json", encoding="utf-8"))
contract.check("findings", data)        # raises ContractError
print(contract.errors("findings", data))  # or: list of messages
```

The schema files are standard JSON Schema; `pipeline/common/contract.py` checks them with the standard library only. Tests: `python -m pytest -q contract pipeline/common`.

## What §8 leaves open (not fixed by the schemas)

- §8 gives no value list for `type`, `severity`, `origin`, `skeptic.status` and the review `status`; the schemas accept any non-empty string. Values in use: `skeptic.status` `survived` and `weakened`; review `status` `confirmed`.
- §8 names the manifest fields only in words. The key names are the ones `pipeline/pdf` already writes: `file`, `sha256`, `format`, `stage`, `pages`, `items`, `unparsed_lines`. `doc`, `warnings` and the other counts are optional.
- `page` may be `null` where a format has no pages (GAEB); §8 shows `line` as `null` for PDF.
- §8 does not say what a finding outside the X checks writes in `skeptic`; the schema requires the object with `status` and `note`.
