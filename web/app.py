"""FastAPI app for the views "Fund" and "Prüfen" (MASTER_PLAN §7, §8, §13, K3).

The app only reads the contract v1 files of the pipeline:
out/<project>/findings.json and out/<project>/items.json. When no project
with a findings.json stands in out/, it reads the synthetic samples in
contract/samples/ and says so. The one file it writes is
reviews/<project>.json (keyed by finding id). A new pipeline run rewrites
findings.json and never touches the reviews file.

Every answer to the page is built from a fixed list of keys. Keys the app does
not know are dropped, and no unit_price or total leaves this module.
"""
import json
import math
import os
import re
import sys
import tempfile
import threading
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fastapi import Body, FastAPI, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from pipeline.common import contract, quotes  # noqa: E402
from web import views  # noqa: E402

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
DEFAULT_OUT_DIR = os.path.join(REPO_ROOT, "out")
DEFAULT_REVIEWS_DIR = os.path.join(REPO_ROOT, "reviews")
HANDOVER_MAP = os.path.join(REPO_ROOT, "pipeline", "cross", "handover_map.json")
BENCH_RESULTS = os.path.join(REPO_ROOT, "bench", "results", "bench.json")

# Review statuses (key or click): bestätigt, verworfen, unklar.
STATUSES = ("confirmed", "rejected", "unclear")
REVIEW_KEYS = ("status", "by", "comment", "eur_estimate", "at")
MAX_COMMENT = 500
MAX_BY = 100

# A project name is a folder name and a file name; a finding id is part of a
# file name. Neither may leave its folder.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_GROUPED_NUMBER = re.compile(r"^\d{1,3}(\.\d{3})+$")
_PLAIN_NUMBER = re.compile(r"^\d+(\.\d+)?$")


class DataError(Exception):
    """A file the app needs cannot be used; the message is German, for the page."""


def safe_name(name):
    return isinstance(name, str) and bool(_SAFE_NAME.match(name)) and ".." not in name


def k3_pass(finding):
    """K3 filter: the refute pass left the finding standing and code found every quote."""
    skeptic = finding.get("skeptic")
    return (isinstance(skeptic, dict) and skeptic.get("status") == "survived"
            and finding.get("quotes_verified") is True)


def parse_eur(value):
    """Return the optional € estimate as a float or None; raise ValueError.

    Accepts a number or a text in German or plain form: "1.500", "1.500,50",
    "1500,5", "1500.5", "1500 €". Without a comma, dots that split groups of
    three digits are thousands marks ("1.500" is 1500).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("no number")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = re.sub(r"\s|\u00a0", "", value)
        text = text.replace("€", "").replace("EUR", "")
        if text == "":
            return None
        if "," in text:
            whole, _, fraction = text.rpartition(",")
            if not (_GROUPED_NUMBER.match(whole) or whole.isdigit()) or not fraction.isdigit():
                raise ValueError("no number")
            number = float(whole.replace(".", "") + "." + fraction)
        elif _GROUPED_NUMBER.match(text):
            number = float(text.replace(".", ""))
        elif _PLAIN_NUMBER.match(text):
            number = float(text)
        else:
            raise ValueError("no number")
    else:
        raise ValueError("no number")
    if not math.isfinite(number) or number < 0:
        raise ValueError("not a finite amount of zero or more")
    return number


def now_stamp():
    """Munich time to the minute, as §8 writes it ("2026-11-21T10:42").

    Falls back to the clock of the machine when it has no time zone data.
    """
    try:
        from zoneinfo import ZoneInfo
        moment = datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:  # no tzdata on this machine
        moment = datetime.now()
    return moment.strftime("%Y-%m-%dT%H:%M")


def _text(value):
    if value is None or isinstance(value, str):
        return value
    return str(value)


def _quantity(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value


def _text_list(value):
    if not isinstance(value, list):
        return []
    return [_text(entry) for entry in value if entry is not None]


def _read_json(path):
    with open(path, encoding="utf-8-sig") as handle:
        return json.load(handle)


class Store:
    """Reads the pipeline output of one project and reads and writes its reviews."""

    def __init__(self, out_dir=None, reviews_dir=None, project=None):
        self.out_dir = os.path.abspath(out_dir or DEFAULT_OUT_DIR)
        self.reviews_dir = os.path.abspath(reviews_dir or DEFAULT_REVIEWS_DIR)
        if project is not None and not safe_name(project):
            raise ValueError("project name %r is not a plain folder name" % (project,))
        self.project = project
        self._lock = threading.Lock()

    # ---- where the data comes from -------------------------------------

    def projects(self):
        """Folders in out/ that hold a findings.json, sorted."""
        if not os.path.isdir(self.out_dir):
            return []
        return sorted(
            name for name in os.listdir(self.out_dir)
            if safe_name(name) and os.path.isfile(os.path.join(self.out_dir, name, "findings.json"))
        )

    def locate(self):
        """Decide between the real files and the samples. Looked up at every request."""
        names = self.projects()
        out_name = os.path.basename(self.out_dir)
        if self.project is not None:
            chosen = self.project if self.project in names else None
            wanted = "%s/%s/findings.json" % (out_name, self.project)
        else:
            chosen = names[0] if names else None
            wanted = "%s/<Projekt>/findings.json" % out_name
        if chosen is not None:
            folder = os.path.join(self.out_dir, chosen)
            return {
                "mode": "real", "project": chosen, "missing": None,
                "source": "%s/%s/findings.json" % (out_name, chosen),
                "findings_path": os.path.join(folder, "findings.json"),
                "items_path": os.path.join(folder, "items.json"),
                "pages_dir": os.path.join(folder, "pages"),
                "pages_label": "%s/%s/pages" % (out_name, chosen),
            }
        return {
            "mode": "sample", "project": self._sample_project(), "missing": wanted,
            "source": "contract/samples/findings.json",
            "findings_path": contract.sample_path("findings"),
            "items_path": contract.sample_path("items"),
            "pages_dir": None, "pages_label": None,
        }

    @staticmethod
    def _sample_project():
        try:
            name = contract.load_sample("items")[0]["project"]
        except (OSError, ValueError, LookupError, TypeError):
            name = None
        return name if safe_name(name) else "sample"

    # ---- findings and items ----------------------------------------------

    def load_findings(self, place):
        """Return (usable findings, number of contract errors, first messages)."""
        label = place["source"]
        try:
            data = _read_json(place["findings_path"])
        except OSError:
            raise DataError("%s kann nicht gelesen werden." % label)
        except ValueError:
            raise DataError("%s ist kein gültiges JSON (wird die Datei gerade geschrieben?)." % label)
        if not isinstance(data, list):
            raise DataError("%s ist keine Liste von Funden (Vertrag v1)." % label)
        problems = contract.errors("findings", data)
        usable, seen = [], set()
        for entry in data:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
                continue
            if entry["id"] in seen:
                problems.append("id %s steht mehrfach in der Datei; nur der erste Fund wird gezeigt" % entry["id"])
                continue
            seen.add(entry["id"])
            usable.append(entry)
        return usable, len(problems), problems[:3]

    @staticmethod
    def load_items(place):
        """Return (items, usable). A missing or broken items.json only costs the list names."""
        try:
            data = _read_json(place["items_path"])
        except (OSError, ValueError):
            return [], False
        if not isinstance(data, list):
            return [], False
        return [entry for entry in data if isinstance(entry, dict)], True

    # ---- reviews -----------------------------------------------------------

    def reviews_path(self, project):
        return os.path.join(self.reviews_dir, "%s.json" % project)

    def read_reviews(self, project):
        path = self.reviews_path(project)
        label = "%s/%s.json" % (os.path.basename(self.reviews_dir), project)
        if not os.path.exists(path):
            return {}
        try:
            data = _read_json(path)
        except OSError:
            raise DataError("%s kann nicht gelesen werden." % label)
        except ValueError:
            raise DataError("%s ist kein gültiges JSON. Die Datei wird nicht überschrieben; bitte von Hand prüfen." % label)
        if not isinstance(data, dict):
            raise DataError("%s ist kein Objekt mit Fund-Kennungen (Vertrag v1). Die Datei wird nicht überschrieben." % label)
        return data

    def save_review(self, project, finding_id, fields):
        """Set one review and write the whole file. Every other entry stays as it is."""
        with self._lock:
            reviews = self.read_reviews(project)
            old = reviews.get(finding_id)
            entry = dict(old) if isinstance(old, dict) else {}
            entry.update(fields)
            problems = contract.schema_errors(entry, contract.load_schema("reviews")["additionalProperties"])
            if problems:
                raise DataError("Die Bewertung passt nicht zum Vertrag v1: %s" % "; ".join(problems[:3]))
            reviews[finding_id] = entry
            os.makedirs(self.reviews_dir, exist_ok=True)
            handle, temp_path = tempfile.mkstemp(dir=self.reviews_dir, prefix=".%s." % project, suffix=".tmp")
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as out:
                    json.dump(reviews, out, ensure_ascii=False, indent=2)
                    out.write("\n")
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(temp_path, self.reviews_path(project))
            except BaseException:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise
            return entry, reviews


# ---- what the page gets ---------------------------------------------------

def review_view(entry):
    """The five §8 keys of a review, or None when there is no usable entry."""
    if not isinstance(entry, dict) or not isinstance(entry.get("status"), str) or not entry["status"]:
        return None
    estimate = entry.get("eur_estimate")
    if isinstance(estimate, bool) or not isinstance(estimate, (int, float)) or not math.isfinite(estimate):
        estimate = None
    return {
        "status": entry["status"],
        "by": _text(entry.get("by")) or "",
        "comment": _text(entry.get("comment")) or "",
        "eur_estimate": estimate,
        "at": _text(entry.get("at")) or "",
    }


def _index_items(items):
    by_key, trades = {}, {}
    for item in items:
        by_key.setdefault((item.get("doc"), item.get("item_no")), []).append(item)
        if isinstance(item.get("trade"), str) and item["trade"] and item.get("doc") not in trades:
            trades[item.get("doc")] = item["trade"]
    return by_key, trades


def _cited_item(source, by_key):
    """The items.json record a source cites: the one that holds the quote, else the first non-heading."""
    candidates = by_key.get((source.get("doc"), source.get("item_no")), [])
    for item in candidates:
        if quotes.quote_in_text(_text(source.get("quote")), quotes.item_text(item)):
            return item
    for item in candidates:
        if item.get("kind") != "heading":
            return item
    return candidates[0] if candidates else None


def finding_view(finding, by_key, trades, review):
    sources = []
    raw_sources = finding.get("sources") if isinstance(finding.get("sources"), list) else []
    for index, source in enumerate(raw_sources):
        if not isinstance(source, dict):
            source = {}
        item = _cited_item(source, by_key)
        sources.append({
            "index": index,
            "doc": _text(source.get("doc")),
            "trade": trades.get(source.get("doc")),
            "item_no": _text(source.get("item_no")),
            "page": source.get("page") if isinstance(source.get("page"), int) else None,
            "quote": _text(source.get("quote")),
            "short_text": _text(item.get("short_text")) if item else None,
            # For the € field of the view "Fund": quantity x a price typed in the browser.
            "quantity": _quantity(item.get("quantity")) if item else None,
            "unit": _text(item.get("unit")) if item else None,
        })
    skeptic = finding.get("skeptic") if isinstance(finding.get("skeptic"), dict) else {}
    return {
        "id": finding["id"],
        "check": _text(finding.get("check")),
        "layer": _text(finding.get("layer")),
        "type": _text(finding.get("type")),
        "severity": _text(finding.get("severity")),
        "handover": _text_list(finding.get("handover")),
        "sources": sources,
        "lists_searched": _text_list(finding.get("lists_searched")),
        "search_terms": _text_list(finding.get("search_terms")),
        "explanation_de": _text(finding.get("explanation_de")),
        "question_de": _text(finding.get("question_de")),
        "quotes_verified": finding.get("quotes_verified") is True,
        "origin": _text(finding.get("origin")),
        "skeptic": {"status": _text(skeptic.get("status")), "note": _text(skeptic.get("note"))},
        "k3_pass": k3_pass(finding),
        "review": review,
    }


def count(findings, reviews):
    """Counters for the page: every finding, the K3 queue, and what the filter holds back."""
    def tally(group):
        numbers = {"count": len(group), "open": 0}
        numbers.update((status, 0) for status in STATUSES)
        for finding in group:
            review = review_view(reviews.get(finding["id"]))
            status = review["status"] if review else None
            numbers[status if status in STATUSES else "open"] += 1
        return numbers

    passed = [finding for finding in findings if k3_pass(finding)]
    known = set(finding["id"] for finding in findings)
    return {
        "all": tally(findings),
        "k3": tally(passed),
        "held_back": len(findings) - len(passed),
        "reviews_without_finding": sum(1 for key in reviews if key not in known),
    }


def _problem(status_code, message):
    return JSONResponse({"error": message}, status_code=status_code)


def create_app(out_dir=None, reviews_dir=None, project=None):
    """Build the app. out_dir and reviews_dir default to out/ and reviews/ of the repository."""
    store = Store(out_dir=out_dir, reviews_dir=reviews_dir, project=project)
    app = FastAPI(title="LV-Prüfstand", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    @app.get("/")
    def page():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"), headers={"Cache-Control": "no-store"})

    @app.get("/api/findings")
    def get_findings():
        place = store.locate()
        try:
            findings, error_count, error_examples = store.load_findings(place)
            reviews = store.read_reviews(place["project"])
        except DataError as error:
            return _problem(500, str(error))
        items, items_usable = store.load_items(place)
        by_key, trades = _index_items(items)
        return {
            "project": place["project"],
            "mode": place["mode"],
            "source": place["source"],
            "missing": place["missing"],
            "items_usable": items_usable,
            "contract_errors": error_count,
            "contract_error_examples": error_examples,
            "findings": [
                finding_view(finding, by_key, trades, review_view(reviews.get(finding["id"])))
                for finding in findings
            ],
            "counters": count(findings, reviews),
        }

    @app.post("/api/reviews/{finding_id}")
    def post_review(finding_id: str, body: dict = Body(...)):
        place = store.locate()
        try:
            findings, _, _ = store.load_findings(place)
        except DataError as error:
            return _problem(500, str(error))
        shown_project = body.get("project")
        if shown_project is not None and shown_project != place["project"]:
            # The page shows another project than the one read now (out/ changed since it loaded).
            return _problem(409, "Die Seite zeigt Projekt %s, gelesen wird jetzt Projekt %s. Bitte die Seite neu laden."
                            % (shown_project, place["project"]))
        if finding_id not in set(finding["id"] for finding in findings):
            return _problem(404, "Der Fund %s steht nicht in %s." % (finding_id, place["source"]))
        status = body.get("status")
        if status not in STATUSES:
            return _problem(422, "Status muss confirmed, rejected oder unclear sein.")
        comment = body.get("comment", "")
        by = body.get("by", "")
        if comment is None:
            comment = ""
        if by is None:
            by = ""
        if not isinstance(comment, str) or not isinstance(by, str):
            return _problem(422, "Kommentar und Prüfer müssen Text sein.")
        comment = " ".join(comment.split())
        by = " ".join(by.split())
        if len(comment) > MAX_COMMENT:
            return _problem(422, "Der Kommentar ist länger als %d Zeichen." % MAX_COMMENT)
        if len(by) > MAX_BY:
            return _problem(422, "Der Name des Prüfers ist länger als %d Zeichen." % MAX_BY)
        try:
            estimate = parse_eur(body.get("eur_estimate"))
        except ValueError:
            return _problem(422, "Die Schätzung in € ist keine Zahl (Beispiel: 1500 oder 1.500,50).")
        fields = {"status": status, "by": by, "comment": comment, "eur_estimate": estimate, "at": now_stamp()}
        try:
            entry, reviews = store.save_review(place["project"], finding_id, fields)
        except DataError as error:
            return _problem(500, str(error))
        except OSError:
            return _problem(500, "Die Bewertung konnte nicht gespeichert werden (Schreibfehler).")
        return {"id": finding_id, "review": review_view(entry), "counters": count(findings, reviews)}

    @app.get("/api/page-image/{finding_id}/{index}")
    def page_image(finding_id: str, index: int):
        place = store.locate()
        try:
            findings, _, _ = store.load_findings(place)
        except DataError as error:
            return _problem(500, str(error))
        finding = next((entry for entry in findings if entry["id"] == finding_id), None)
        sources = finding.get("sources") if finding else None
        if not isinstance(sources, list) or not 0 <= index < len(sources) or not safe_name(finding_id):
            return JSONResponse({"error": "Diese Quelle gibt es nicht.", "expected": None}, status_code=404)
        name = "%s_%d.png" % (finding_id, index)
        if place["pages_dir"] is None:
            return JSONResponse({"error": "Zu den Beispieldaten gibt es keine Seitenbilder.", "expected": None},
                                status_code=404)
        path = os.path.join(place["pages_dir"], name)
        expected = "%s/%s" % (place["pages_label"], name)
        if not os.path.isfile(path):
            return JSONResponse({"error": "Das Seitenbild liegt nicht vor.", "expected": expected}, status_code=404)
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})

    # ---- export (W8): each file is built at this moment from the current reviews ----

    def export_data(shown_project):
        """(export data, None), or (None, the answer that says why there is no file)."""
        from web.export import model  # imported here: web.export itself imports this module
        place = store.locate()
        if shown_project is not None and shown_project != place["project"]:
            # As for a review: the page shows another project than the one read now.
            return None, _problem(409, "Die Seite zeigt Projekt %s, gelesen wird jetzt Projekt %s. Bitte die Seite neu laden."
                                  % (shown_project, place["project"]))
        try:
            return model.load(store, place=place), None
        except DataError as error:
            return None, _problem(500, str(error))

    def download(content, name, media_type):
        return Response(content, media_type=media_type, headers={
            "Content-Disposition": 'attachment; filename="%s"' % name, "Cache-Control": "no-store"})

    @app.get("/api/export/fragenliste")
    def export_fragenliste(project: str = None):
        from web.export import files, model
        data, problem = export_data(project)
        if problem is not None:
            return problem
        return download(files.fragenliste_docx(data), model.NAMES["docx"],
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    @app.get("/api/export/lv-markiert")
    def export_lv_markiert(project: str = None):
        from web.export import files, model
        data, problem = export_data(project)
        if problem is not None:
            return problem
        return download(files.lv_markiert_xlsx(data), model.NAMES["xlsx"],
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    @app.get("/api/export/risikobericht")
    def export_risikobericht(format: str = "pdf", project: str = None):
        """The report as PDF; as HTML with format=html, and when no Chrome on this machine prints the PDF."""
        from web.export import files, model
        if format not in ("pdf", "html"):
            return _problem(422, "Das Format muss pdf oder html sein.")
        data, problem = export_data(project)
        if problem is not None:
            return problem
        report = files.risikobericht_html(data)
        pdf = files.print_pdf(report)[0] if format == "pdf" else None
        if pdf is not None:
            return download(pdf, model.NAMES["pdf"], "application/pdf")
        return download(report.encode("utf-8"), model.NAMES["html"], "text/html; charset=utf-8")

    # ---- the views "Bauwerk", "Einzel-LV", "Live-Prüfung", "Vergleich", "Messung" (web/views.py) ----

    def optional_json(path):
        try:
            return _read_json(path)
        except (OSError, ValueError):
            return None

    def base_findings(place):
        if place["mode"] != "real":
            return [], False
        data = optional_json(os.path.join(os.path.dirname(place["findings_path"]), "base_findings.json"))
        return (data, True) if isinstance(data, list) else ([], False)

    @app.get("/api/matrix")
    def get_matrix():
        place = store.locate()
        try:
            findings, _, _ = store.load_findings(place)
        except DataError as error:
            return _problem(500, str(error))
        items, _ = store.load_items(place)
        return views.matrix(findings, items, optional_json(HANDOVER_MAP), place["project"])

    @app.get("/api/lv")
    def get_lists():
        place = store.locate()
        items, _ = store.load_items(place)
        found, present = base_findings(place)
        return {"project": place["project"], "mode": place["mode"], "base_findings_file": present,
                "lists": views.lv_lists(items, found)}

    @app.get("/api/lv/{doc}")
    def get_list(doc: str):
        place = store.locate()
        items, _ = store.load_items(place)
        found, _ = base_findings(place)
        try:
            return views.lv_document(items, found, doc)
        except views.ViewError as error:
            return _problem(404, str(error))

    @app.post("/api/live")
    async def post_live(request: Request):
        from urllib.parse import unquote
        name = unquote(request.headers.get("x-file-name", ""))
        raw = await request.body()
        try:
            return views.live(raw, name)
        except views.ViewError as error:
            return _problem(422, str(error))

    @app.get("/api/diff")
    def get_diff():
        summary = optional_json(os.path.join(store.out_dir, "diff", "summary.json"))
        if summary is None:
            return _problem(404, "Der Vergleich ist noch nicht berechnet. Er entsteht mit python -m pipeline.run "
                                 "(Schritt \"twin and stage comparison\", Ordner out/diff/).")
        try:
            return views.diff(summary)
        except views.ViewError as error:
            return _problem(500, str(error))

    @app.get("/api/bench")
    def get_bench():
        try:
            return views.bench(optional_json(BENCH_RESULTS))
        except views.ViewError as error:
            return _problem(404, str(error))

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
