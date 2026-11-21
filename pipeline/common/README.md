# pipeline/common

Shared code of the pipeline: `quotes.py` (quote check), `ids.py` (finding ids), `contract.py` (schema check), `pagecheck.py` (page check of the findings).

## Page check of the findings (`pagecheck.py`)

For every source of every finding: read the stated page of the source PDF, check by code that the quote stands on it and that the page is a page of the cited item, and save the page as an image with the quote in yellow. No human looks at the pages.

```
python -m pipeline.common.pagecheck pipeline/cross/results/79-222/findings.json data out/79-222 out/79-222/findings.pagecheck.json
```

Needs `data/` (the organizer PDFs) and `out/79-222/items.json` (built by the two reader commands in `AGENTS.md`). With `out/79-222` as the out dir it writes:

- `out/79-222/pages/<finding id>_<source index from 0>.png`: where the review screen (`web/`) reads the page images.
- `out/79-222/pagecheck.json`: per finding and source the status, how the quote matched, the pages of the cited item.
- `out/79-222/findings.pagecheck.json` (the fourth argument, optional): the findings with `quotes_verified` = true only where every source is `found`; nothing else changed. Do not name `out/79-222/findings.json` here, that is the merged file of the skeptic pass.

`items.json` is taken from `--items <file>`, else from `<out dir>/items.json`. Without it the pages of the items are not checked; the summary line then counts the sources as `item_page_not_checked`.

Status of a source:

| status | meaning | counts as verified |
|---|---|---|
| `found` | the quote stands on the stated page, and that page is a page of the cited item | yes |
| `page_not_of_item` | the quote stands on the stated page, but the cited item is on other pages (`item_page`, `item_pages`) | no |
| `other_page` | the quote stands on another page of the list (`other_page`) | no |
| `not_found` | the quote stands on no page of the list | no |

An item has the pages from its own page in `items.json` up to the page where the next entry of the list starts. A source whose item number is not in `items.json` for that list is `page_not_of_item` too (`error`: `item_not_in_items`); a source without item number is not checked this way.

A quote may run over one page break. Between its two parts only the page footer, the page header and a carry line ("Übertrag:" on both sides of the break) may be left out; the module text of `pagecheck.py` says how these are told from body lines.

Known gaps:

- A quote that runs over more than two pages is not found. With the reader text of each entry of `items.json` as the quote this holds for 7 of 1346 entries (LV_14 5.3, LV_14a .1 and 5 preliminary notes).
- A header line that changes from page to page (a page number in the header) is not seen as header; a quote over that page break is then not found.
- If the last body line of a page and the first body line of the next page are the same line, they are taken for a carry line, and a quote that leaves out both is accepted. The 27 lists of 79-222 have no such page break (all 270 carry lines are "Übertrag:").
- The page range of an item ends on the page where the next entry starts, also when the next entry starts at the top of that page.
- Matching is case-sensitive, like `quotes.py`.
