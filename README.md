# LV-Prüfstand

TUM.ai Construction Hackathon (20-22 Nov 2026, Garching), team Cowork, Challenge A.

LV-Prüfstand reads all bills of quantities (Leistungsverzeichnisse) of one building as a single project and finds errors *between* the documents: work that two trades both price, a contradiction between two lists, a gap that no list covers. Every finding carries verbatim quotes from the sources, every quote is checked by code against its source, and the arithmetic of priced GAEB files is recomputed by code; a person confirms or rejects what is shown. The screen shows the building as a trade matrix ("Bauwerk"), every finding with its quotes and its source page ("Fund"), the review ("Prüfen"), each list with its base checks ("Einzel-LV"), a live check of a GAEB file dropped into the page ("Live-Prüfung"), the tender-against-order and twin comparisons ("Vergleich") and the measurements ("Messung").

## What this repository holds, and what it does not

This is the public copy of our working repository, with a fresh history. It holds the code, the tests, the contract (schemas and synthetic samples) and the rules. It does **not** hold:

- the organizer data (the bills of quantities, GAEB files and offers of the challenge); they belong to the organizers and are never in git;
- the stored findings of the challenge project and the verdicts of the counter-check: they quote the organizer files word for word;
- our internal plan, agent notes and status messages.

So with this repository alone the screen runs on **synthetic samples** (made-up lists of project `11-111` in `contract/samples/`) and says so in a yellow line ("Beispieldaten"). The demo video shows the same code on the organizer data.

## Run it on the samples

Everything runs on one laptop, offline once the packages are installed.

1. **Python 3.12** and a virtual environment: `python3.12 -m venv .venv`, then `source .venv/bin/activate` (Windows: `.venv\Scripts\activate`), then `python -m pip install -r requirements.txt`. This is the only step that needs the network.
2. **The tests**: `python -m pytest -q`. Tests that need the organizer data skip without it. A test that fails after it looked for a file this copy leaves out (the stored results above, the opening finding of the deck, the pitch texts and numbers) is reported as skipped, with the missing path as the reason; any other failure stays a failure (`conftest.py`).
3. **The screen**: `python -m web`, then open `http://127.0.0.1:8000/#pruefen`. The yellow line "Beispieldaten" shows that the synthetic samples are read. Views "Bauwerk" (trade matrix), "Fund" (the findings with their quotes), "Prüfen" (keys `B` bestätigt, `V` verworfen, `U` unklar), "Einzel-LV", "Live-Prüfung" (drop any GAEB 90, GAEB XML or Excel file of your own: it is read in memory and checked by B1 to B12), "Vergleich" (needs a pipeline run on the organizer data) and "Messung". Details: [`web/README.md`](web/README.md).
4. **The number checks on a GAEB 90 file of your own**: this copy holds no GAEB file (the organizer files are not published), so bring one. `python -m pipeline.lv.gaeb90 <file.D83> out/live` reads the file into `out/live/<project>/items.json` (its printed line names the folder), then `python -m pipeline.base.run out/live/<project>/items.json out/live/<project>/base_findings.json` runs the base checks B1 to B12 on it (`pipeline/base/README.md`).

## Run it on the organizer data

The full run `python -m pipeline.run` reads the organizer files from `data/` and needs **Poppler** for the PDF lists (`pdftotext -v` must name Poppler; macOS: `brew install poppler`, Debian and Ubuntu: `sudo apt install poppler-utils`). Without `data/` it stops with exit code 3 and says what is missing. Its steps after the readers check our stored findings against the lists; those findings are not in this copy (see above), so here the run on the organizer data ends at that step.

## What is stored and what is live

**No model is called by any command of this repository.** No command needs a key or the network after the install. The finder's lists hold no prices; code strips price fields before the counter-check. The tool runs offline and calls no model. The screen's answers carry no unit price and no total, and a price typed into the screen stays in the browser.

| | What | Where |
|---|---|---|
| **Stored** (made earlier with a model; not in this copy) | the findings between the trade lists of the challenge project, with their quotes, and the verdicts of the counter-check (a second, independent model pass that tried to refute each finding) | not published |
| **Live**, by code | reading the files: PDF lists, GAEB 90 and GAEB XML files, offer and print PDFs, Excel lists (.xlsx, a simple column mapping) | `pipeline/pdf/`, `pipeline/lv/` |
| **Live** | every number check: the base checks B1 to B12 | `pipeline/base/` |
| **Live** | the check of stored findings against the lists read on the laptop: evidence search, rule checks on the verdicts (a quote that is not on its page or a number without a source lowers the verdict), the merge | `pipeline/skeptic/`, `pipeline/common/quotes.py` |
| **Live** | the page check: every quote is searched by code on its stated page of the source PDF, and the page is saved as an image with the quote in yellow | `pipeline/common/pagecheck.py` |
| **Live** | the comparison of twins (one list in two formats) and stages (tender, offer, order) | `pipeline/diff/` |
| **Live** | severity by fixed rules | `pipeline/common/severity.py`, [`docs/RISK_RULES.md`](docs/RISK_RULES.md) |
| **Live** | the screen: trade matrix, findings, review (reviews go to `reviews/`), each list with its base checks, comparisons, measurements; the € effect from a typed price | `web/` |
| **Live** | "Live-Prüfung": a GAEB or Excel file dropped into the page is read in memory, recalculated and checked by B1 to B12; a GAEB 90 note shows the record lines of its items (price records masked); nothing is stored, no price goes back to the page | `web/views.py` |
| **Live** | the exports (German question list .docx, marked list .xlsx, risk report .html and .pdf), built from the confirmed findings at the moment of the click | `web/export/` |

## Layout

- `contract/`: schemas of the four files the pipeline writes and the app reads, with synthetic samples.
- `pipeline/`: `run.py` (the one command), readers (`pdf/`, `lv/`), checks (`base/`, `diff/`), the counter-check (`skeptic/`), shared code (`common/`: contract check, ids, quote check, page check, severity), the handover check between trades (`cross/`).
- `web/`: app, review screen, exports.
- `bench/`: the measurement code (`python -m bench.run`, M1 to M9 of `docs/PREREG.md`), its tests, and the results measured on the organizer data (`bench/results/bench.json`, the table under "Measurements" below).
- `pitch/`: the code that builds the deck and the pitch texts, the slide source (`pitch/src/slides.html`, `pitch/src/deck.css`) and the test of the screenshot step. The pitch texts and the speaker sheet, their numbers and the opening finding are not in this copy (they retell findings of the organizer files or wait for numbers of the expert session), so the deck does not build from it; the deck reaches the judges as a PDF through the submission form.
- `docs/`: measurement plan (`PREREG.md`), severity rules (`RISK_RULES.md`).
- `scripts/clean_clone_check.py`: clones a branch into an empty folder, installs, and runs the steps above with the network off.
- `data/`, `cache/`, `out/`, `reviews/` stay out of git (`.gitignore`).

Codes in comments, READMEs and tests such as "plan §14", W1 to W19 (work packages), K1 to K12 (team decisions), "Filter K3" on the screen, or a pointer to `AGENTS.md` or `MASTER_PLAN.md` refer to the team's private plan and notes, which are not in this copy. Counts named in such comments (for example of stored findings) describe the stored results of the challenge project.

## Measurements

`python -m bench.run` measures M1 to M9 on the organizer data and writes `bench/results/bench.json`; `python -m bench.readme --readme README.md` writes the table below from that file (`--check` compares them). The thresholds were locked in `docs/PREREG.md` before the first measured run. Every result stands as it came out, also below its threshold: two thresholds were missed (column "Threshold met"). M7 counts errors we seeded ourselves. The bench calls no model and no network service. M9 seconds depend on the machine named in the row.

<!-- bench:start -->
| # | Measurement | Result | Threshold | Threshold met |
|---|---|---|---|---|
| M1 | GAEB parsing | 9 of 9 files with the expected item count | 9/9 | yes |
| M2 | Recalculation | 720 items checked in 4 files, 0 deviate; 249 priced items without a quantity not checkable | every deviation is listed one by one | yes |
| M3 | PDF ↔ GAEB twin | T1 Angebot AN24-0305.D84: 274 of 274 items of the GAEB file also in the PDF (100.0 %), unit prices equal 274 of 274, totals equal 274 of 274 (100.0 %); T2 GAEB-[PROJEKT_004].X83: 50 of 50 items of the GAEB file also in the PDF (100.0 %), prices not measurable: no item pair holds a unit price or a total in both files | ≥ 98 % of items, ≥ 98 % of prices | yes |
| M4 | PDF reader, 27 lists | 27 lists, 1131 and 1131 items in two runs, difference 0; page check of LV_18, LV_14c, LV_02, LV_17, LV_00: 388 of 388 items match on 115 pages, 0 differences; not read: 11 reader warnings in 3 lists, 0 unparsed lines | difference 0; what could not be read is stated openly | yes |
| M5 | Expert verdict | not measured: no expert session took place during the event; reviews/79-222.json does not exist; counted: `by` not empty and without "test", `at` within the session; the bench cannot tell a real expert from a test click beyond that | the numbers as they come out; headline evidence | not measured yet |
| M6 | Quote filter | 24 committed findings with 51 quotes checked, 0 dropped because a quote was not found | reported | yes |
| M7 | Seeded errors (internal measurement) | B: 83 of 120 found (69.1 %) in StBALV23040.D86; by type, found/planted: quantity ×10 5/20, unit change 8/20, corrupted amount 20/20, corrupted total 20/20, deleted item 14/20, duplicated item 16/20; X not measured: finding a deleted or changed item of a cross-list finding again needs a new model run, and the bench never runs a model | B ≥ 90 %; X is only reported | no |
| M8 | False alarms | StBALV23040.D86: 43 high or medium findings in 249 items = 17.26 per 100; for comparison, without a threshold, [ORT_024] LV24069.D86: 84 in 197 = 42.63 per 100 | ≤ 5 | no |
| M9 | Speed | base layer, median of 5 runs: 0.106 s (300 items built from StBALV23040.D86) and 0.154 s (501-24-01_GAEB-XML_sas.x83, 296 items); machine: aarch64, 10 cores, 8 GB RAM, Linux 7.0.14-linuxkit, Python 3.12.16 | ≤ 5 s | yes |
<!-- bench:end -->

## Tools we used

- AI tools: the build work was done by Devin sessions with the model Claude Fable 5.2 and, after the Devin usage ended, by Claude Code agents (Claude Opus workers with a Claude Fable lead) in a local Docker box. On the last evening, Claude Code (Claude Opus 5.5) added the views "Bauwerk", "Einzel-LV", "Live-Prüfung", "Vergleich" and "Messung", Microsoft Edge support and the demo video. Claude was also used for planning, the first reading of the lists and checks before the build. The semantic results in the demo are stored results of these sessions, not live model calls.
- KÖPRÜ, a relay tool written before the event to connect two agents, was planned and not used; it is not part of the product.
- Open source: FastAPI, Uvicorn, lxml, PyMuPDF, pandas, openpyxl, python-docx, pytest, httpx (`requirements.txt`); Poppler `pdftotext` for the PDF lists; a headless Chrome, Chromium or Microsoft Edge, when installed, prints the risk report to PDF.
