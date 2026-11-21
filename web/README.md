# web/

App for the views "Bauwerk", "Fund", "Prüfen", "Einzel-LV", "Live-Prüfung", "Vergleich" and "Messung" (W6, W7 and the views of plan §7): FastAPI plus one page without a build step (`static/`), German, a warm dark design by default and a light one by the button ◐ in the header (the choice stays in the browser), fully offline (system fonts, no outside resource; one stylesheet `style.css` for the header, "Fund" and "Prüfen", `views.css` for the other views). The German export (W8) is in `export/`; see "Export" below. The address names the view: `#bauwerk`, `#fund` (the default), `#pruefen`, `#einzel`, `#live`, `#vergleich`, `#messung`.

## The views "Bauwerk", "Einzel-LV", "Live-Prüfung", "Vergleich", "Messung"

Their data comes from `views.py`; the page part is `static/views.js` and `static/views.css`. Every answer is built from fixed lists of keys: no `unit_price` and no `total` reaches the page.

- "Bauwerk": one row and one column per list of the project (order of `items.json`). A cell is lit when a finding lies between the two lists (a finding between three lists lights its three pairs; a finding inside one list lights the diagonal); the colour is the highest level of its findings, stripes mean all of them are held back by the Prüffilter, a green frame means one is confirmed. Grey cells are handovers of `pipeline/cross/handover_map.json` (only for its own project). A click lists the findings of the cell; a click on one opens it in "Fund".
- "Einzel-LV": a list of the project with all its records and the marks of the base checks of `out/<project>/base_findings.json` (written by `python -m pipeline.run`). A search field (number and short text), "nur Positionen mit Hinweis" and an order (as in the list, marked items first, largest quantity first) work on the rows in the page.
- "Live-Prüfung": a GAEB 90 (.D83, .D84, .D86), GAEB XML (.X83, .X84, .X86) or Excel (.xlsx) file, dropped or chosen, is sent to `POST /api/live` (raw body, its name in the header `X-File-Name`, at most 20 MB), read in memory by `pipeline/lv`, recalculated (counts only) and checked by B1 to B12 (`pipeline/base`). Nothing is written to disk. For a GAEB 90 file every note carries the record lines of its cited items as they stand in the file ("GAEB-Satz zeigen"); a price record (23, 30) comes as a line that says it is not shown. PDF lists go through `python -m pipeline.run`.
- "Treffer anzeigen" (views "Fund" and "Prüfen"): `GET /api/evidence/<finding id>` gives where the search terms of the finding stand in the lists, read from `out/<project>/skeptic/evidence.json` of `python -m pipeline.run` (fixed keys; quantity and unit, no price; at most 80 hits shown).
- "Vergleich": `out/diff/summary.json` of `python -m pipeline.run` as counts and item numbers; prices only as equal or not equal.
- "Messung": `bench/results/bench.json` with the German texts of `bench/table.py`, and a box "Nicht gebaut" (price suggestions, what-if, text recognition, AVA link).

## Expert session (for Mert)

1. Start, in the repository folder: `python -m web` (other port: `python -m web --port 8001`; project by name: `--project 79-222`).
2. Open `http://127.0.0.1:8000/#pruefen` in the browser. A yellow line "Beispieldaten" means `out/<project>/findings.json` is missing and the synthetic samples are shown.
3. Type the expert's role once into "Geprüft von". Keys: `B` bestätigt, `V` verworfen, `U` unklar, `←` `→` previous and next finding.
4. Comment (one sentence) and "Schätzung in €": type, then `Enter` (it saves and leaves the field; inside a field the letters are text). Before the first B, V or U of a finding they are saved together with that key.
5. Every key or click writes `reviews/<project>.json` at once ("Gespeichert: …" in green, "NICHT gespeichert" in red). The switch "Prüffilter" (plan K3) is on; switch it off to see the findings it holds back.
6. Layout of "Prüfen": header, counters and the review form keep their place; the part between them (filter switch, export buttons, the finding, the key list) scrolls in its own box, so the form never lies over the finding. `←` `→` put the next finding at the top of that box; `↑` `↓`, `Bild auf`, `Bild ab`, `Pos1`, `Ende` and the mouse wheel scroll it. In a window lower than 600 px or narrower than 1200 px the page scrolls as a whole and the form stands under the finding.

## What it reads and writes

- Reads `out/<project>/findings.json` and `out/<project>/items.json` (contract v1, `contract/README.md`; unknown keys are ignored) at every request, so a new pipeline run shows after a reload of the page. Without `--project` it takes the first folder in `out/` that holds a `findings.json`. When there is none, it reads `contract/samples/` (project `11-111`) and says so.
- Writes only `reviews/<project>.json`, keyed by finding id, with `status` (`confirmed`, `rejected`, `unclear`), `by`, `comment`, `eur_estimate`, `at` (plan §8). One click changes one entry; all other entries stay, also those of findings that a new run no longer holds. A reviews file that is not valid JSON is reported and never overwritten. A click from a page that still shows another project than the one read now is refused (reload the page).
- K3 filter: the "Prüfen" queue holds the findings with `skeptic.status = "survived"` and `quotes_verified = true`. The counters show how many the filter holds back. The view "Fund" lists every finding.
- "Quelle zeigen" shows `out/<project>/pages/<finding id>_<source index from 0>.png` when that file exists, and names the missing file when it does not. Another package writes these images.
- No `unit_price` and no `total` is sent to the page; every answer is built from a fixed list of keys (`web/app.py`).
- € field (W15): in the view "Fund" every cited item with a quantity has the field "Einheitspreis in €". The page shows quantity × typed price = "€-Effekt" at once (`euroEffect` in `static/app.js`; German input such as `1.250,50`; a wrong input shows a message and no number). The typed price stays in the page: it is not stored, not sent and not written to reviews. To keep the result, type it into "Schätzung in €" in the view "Prüfen". For this, each source in the answer of `GET /api/findings` now also carries `quantity` and `unit` of its cited item.

## Export (W8)

Three files from the findings whose review status is `confirmed`, and from no other finding (the K3 filter plays no part here):

- `Fragen_und_Klaerungsliste.docx`: head (project, date, number of questions, who confirmed = the `by` values of the reviews), then one block per finding: question, type, explanation, a table with one row per source (list, trade, item number, page, quote word for word).
- `LV_markiert.xlsx`: first sheet "Bestätigte Funde" (one row per source, with sheet and row of the cited item), then **one sheet per list** with every record of `items.json` (list, item number, short text, quantity, unit, page). A row that a confirmed finding cites is filled yellow and carries finding id, type and question. There is no price column; `unit_price` and `total` are never read into the export. Text is written as text, never as a formula.
- `Risikobericht.html` (one file, no outside resource, print style A4) and `Risikobericht.pdf`, printed from it by a headless Chrome or Chromium: summary (lists, items, findings; bestätigt, verworfen, unklar, offen), the confirmed findings ordered by `severity`, a method box, a measurement box. The measurement box shows the counts, the skeptic counts of `findings.json` and, when `out/<project>/bench.json` exists, its lines as they are (`{"lines": [...]}` or a list of texts; another JSON object is shown as `key: value` lines). Without that file it says that the measurement has not run yet. A review's `eur_estimate` is shown only as "Schätzung des Prüfers" next to its finding.

The three files show the findings in one order (by `severity`: high, medium, info; inside a level the order of `findings.json`), so "Frage 2" is the same finding in all of them.

Command: `python -m web.export --project 79-222` writes into `out/79-222/export/` (not in git); `--out <dir>` writes elsewhere; `--data` and `--reviews` name other input folders. It reads `out/<project>/findings.json`, `out/<project>/items.json`, `reviews/<project>.json` and changes none of them. With zero confirmed findings the files are still written and say so. Without Chrome only the HTML is written; the command says so and exits 0 (open the HTML and print it to PDF). Exit 1: a Chrome is there but printed no PDF; exit 2: no `findings.json` for the project, or a reviews file that cannot be read.

Page: the views "Fund" and "Prüfen" have the buttons "Fragenliste exportieren", "LV markiert exportieren", "Risikobericht exportieren". Each downloads the file built at that moment from the current reviews. The request names the project the page shows (`?project=`); when the app reads another project by now, it answers 409 and asks for a reload, as it does for a review. "Risikobericht exportieren" gives the PDF; on a machine without Chrome it gives the HTML and says so.

German texts: every fixed text of the three files stands in `export/texte_de.py`, for proofreading in one place (a test fails when a fixed text stands elsewhere). `export/model.py` reads the data, `export/files.py` writes the files.

## Endpoints

`GET /` the page · `GET /api/findings` findings with their review, the K3 mark and the counters · `POST /api/reviews/<finding id>` with `{"status", "comment", "eur_estimate", "by"}` · `GET /api/page-image/<finding id>/<source index>` · `GET /api/export/fragenliste` (.docx) · `GET /api/export/lv-markiert` (.xlsx) · `GET /api/export/risikobericht` (PDF; HTML with `?format=html` and when no Chrome, Chromium or Edge prints the PDF) · `GET /api/matrix` · `GET /api/lv` · `GET /api/lv/<list>` · `POST /api/live` · `GET /api/diff` · `GET /api/bench` · `GET /api/evidence/<finding id>`.

## Tests

`python -m pytest -q web` (needs `httpx` for the FastAPI test client). `web/tests/test_web_eur_effect.py` checks the € arithmetic through a Python twin of `euroEffect` (no Node on the build machine); two of its tests run the real JavaScript in a headless Chrome or Chromium and are skipped where none is installed. `web/tests/test_web_realdata.py` and `web/tests/test_web_export_realdata.py` run only where `out/79-222/items.json` is built and are skipped elsewhere. `web/tests/test_web_export_layout.py` opens the real page in a headless Chrome at 1280x720 and 1920x1080 (skipped without Chrome; it fails when a Chrome is there but gives no page). The PDF tests are skipped without Chrome.
