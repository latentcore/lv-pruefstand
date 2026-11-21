"""W15: the € field of the view "Fund" (quantity x a typed unit price = € effect).

The arithmetic is the JavaScript function euroEffect in web/static/app.js. Node
is not on the build machine, so `euro_effect` below is its Python twin: the same
steps in the same order, checked against one table of cases. Where a Chrome or
Chromium is installed, two more tests run the real JavaScript in it (headless,
no network) against the same table and drive the page; they skip without one.
"""
import json
import math
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from web.app import STATIC_DIR, create_app, parse_eur  # noqa: E402

NO_PRICE = "Das ist kein Preis. Beispiel: 1.250,50 (Komma vor den Cent, Punkt nur als Tausenderzeichen)."
TOO_LONG = "Der Preis hat zu viele Stellen (höchstens 9 vor und 4 nach dem Komma)."
NO_QUANTITY = "Für diese Position steht keine Menge in der Liste; ohne Menge gibt es keinen €-Effekt."


def static_text(name):
    with open(os.path.join(STATIC_DIR, name), encoding="utf-8") as handle:
        return handle.read()


def group(digits):
    return re.sub(r"\B(?=([0-9]{3})+$)", ".", digits)


def euro_effect(quantity, unit, price_text):
    """Python twin of euroEffect in web/static/app.js (same steps, same order)."""
    text = ("" if price_text is None else str(price_text)).strip()
    text = re.sub(r"\s*(€|EUR)$", "", re.sub(r"^(€|EUR)\s*", "", text))   # one sign before or after
    if text == "":
        return {"state": "empty"}
    if re.match(r"^[0-9]{1,3}(\s[0-9]{3})+(,[0-9]+)?$", text):            # "1 250,50"
        text = re.sub(r"\s", "", text)
    whole, fraction = None, ""
    if "," in text:
        whole, _, fraction = text.rpartition(",")
        if not re.match(r"^([0-9]{1,3}(\.[0-9]{3})+|[0-9]+)$", whole) or not re.match(r"^[0-9]+$", fraction):
            whole = None
    elif re.match(r"^[0-9]{1,3}(\.[0-9]{3})+$", text):
        whole = text
    elif re.match(r"^[0-9]+(\.[0-9]+)?$", text):
        whole, _, fraction = text.partition(".")
    if whole is None:
        return {"state": "error", "message": NO_PRICE}
    whole = re.sub(r"^0+(?=[0-9])", "", whole.replace(".", ""))
    if len(fraction) > 4 or len(whole) > 9:
        return {"state": "error", "message": TOO_LONG}
    if isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or not math.isfinite(quantity) \
            or quantity < 0 or quantity > 1e9:
        return {"state": "error", "message": NO_QUANTITY}
    price = int(whole + fraction.ljust(4, "0"))                # in 1/10 000 €
    amount = int(math.floor(quantity * 1e6 + 0.5))             # in 1/1 000 000 of the unit
    cents = (price * amount + 50000000) // 100000000           # half up
    micro = str(amount).rjust(7, "0")
    quantity_fraction = micro[-6:].rstrip("0")
    result = {
        "state": "ok",
        "quantity": group(micro[:-6]) + ("," + quantity_fraction if quantity_fraction else ""),
        "price": group(whole) + "," + fraction.rstrip("0").ljust(2, "0"),
        "effect": group(str(cents // 100)) + "," + str(cents % 100).rjust(2, "0"),
    }
    result["text"] = "%s%s × %s € = %s €" % (result["quantity"], " " + unit if unit else "",
                                             result["price"], result["effect"])
    return result


# (quantity, unit, typed price) -> (quantity text, price text, € effect), worked out by hand.
GOOD = [
    (120, "m2", "1.250,50", ("120", "1.250,50", "150.060,00")),      # the case of the brief
    (1, "St", "1.250,50", ("1", "1.250,50", "1.250,50")),
    (2.5, "m", "12,5", ("2,5", "12,50", "31,25")),
    (85, "m", "1.250", ("85", "1.250,00", "106.250,00")),           # dot + three digits: thousands
    (85, "m", "12.5", ("85", "12,50", "1.062,50")),                 # dot + one digit: decimal point
    (2, "St", "1250.50", ("2", "1.250,50", "2.501,00")),
    (2, "St", "1.25", ("2", "1,25", "2,50")),
    (1, "psch", "1.234.567,89", ("1", "1.234.567,89", "1.234.567,89")),
    (3, "St", "1.234.567", ("3", "1.234.567,00", "3.703.701,00")),
    (4, "St", " 1 250,50 € ", ("4", "1.250,50", "5.002,00")),
    (4, "St", "1\u00a0250,50\u00a0EUR", ("4", "1.250,50", "5.002,00")),
    (4, "St", "€ 12,50", ("4", "12,50", "50,00")),
    (4, "St", "12,50€", ("4", "12,50", "50,00")),
    (4, "St", "EUR 3", ("4", "3,00", "12,00")),
    (2, "St", "1 250", ("2", "1.250,00", "2.500,00")),
    (1, "psch", "1 234 567,89", ("1", "1.234.567,89", "1.234.567,89")),
    (10, "m3", "007", ("10", "7,00", "70,00")),
    (10, "m3", "0", ("10", "0,00", "0,00")),
    (0, "m3", "99,99", ("0", "99,99", "0,00")),
    (1, "St", "1,005", ("1", "1,005", "1,01")),                     # half up; binary floats give 1,00
    (3, "St", "0,005", ("3", "0,005", "0,02")),
    (1, "St", "0,0049", ("1", "0,0049", "0,00")),
    (0.333, "t", "3", ("0,333", "3,00", "1,00")),
    (1234.5, "m2", "0,1", ("1.234,5", "0,10", "123,45")),
    (0.1, "m", "0,3", ("0,1", "0,30", "0,03")),
    (1131.725, "m2", "42,35", ("1.131,725", "42,35", "47.928,55")),  # 47 928,553 75
    (1000000000, "St", "999.999.999,9999", ("1.000.000.000", "999.999.999,9999", "999.999.999.999.900.000,00")),
    (7, None, "1,10", ("7", "1,10", "7,70")),
    (7, "", "1,10", ("7", "1,10", "7,70")),
]

EMPTY = ["", "   ", None, "€", " EUR ", "\u00a0"]

BAD = [
    ("abc", NO_PRICE), ("1,2,3", NO_PRICE), ("1.2.3", NO_PRICE), ("-5", NO_PRICE), ("+5", NO_PRICE),
    ("1e3", NO_PRICE), ("12,", NO_PRICE), (",5", NO_PRICE), (".", NO_PRICE), ("1.", NO_PRICE), (".5", NO_PRICE),
    ("1.50,5", NO_PRICE), ("1.500.5", NO_PRICE), ("1,250.50", NO_PRICE), ("1..250", NO_PRICE),
    ("12,5 pro m", NO_PRICE), ("NaN", NO_PRICE), ("Infinity", NO_PRICE), ("1.250,5.0", NO_PRICE),
    ("١٢", NO_PRICE), ("12€50", NO_PRICE), ("12 50", NO_PRICE), ("1 2", NO_PRICE), ("12 ,5", NO_PRICE),
    ("1 250 50", NO_PRICE), ("1 250.50", NO_PRICE), ("1250 500", NO_PRICE), ("5 € 5", NO_PRICE), ("€€5", NO_PRICE),
    ("12 EUR 50", NO_PRICE), ("1 250,5 0", NO_PRICE), ("12,34567", TOO_LONG), ("1234567890", TOO_LONG), ("1.234.567.890,00", TOO_LONG),
]

NO_QUANTITIES = [None, "12", True, float("nan"), float("inf"), -1, 1e9 + 1, [1], {}]


@pytest.mark.parametrize("quantity,unit,typed,expected", GOOD)
def test_effect_is_quantity_times_the_typed_price(quantity, unit, typed, expected):
    answer = euro_effect(quantity, unit, typed)
    assert (answer["state"], answer["quantity"], answer["price"], answer["effect"]) == ("ok",) + expected
    assert answer["text"] == "%s%s × %s € = %s €" % (expected[0], " " + unit if unit else "", expected[1], expected[2])


def test_the_case_of_the_brief_reads_as_one_line():
    assert euro_effect(120, "m2", "1.250,50")["text"] == "120 m2 × 1.250,50 € = 150.060,00 €"


@pytest.mark.parametrize("typed", EMPTY)
def test_an_empty_field_shows_neither_a_number_nor_a_message(typed):
    assert euro_effect(120, "m2", typed) == {"state": "empty"}


@pytest.mark.parametrize("typed,message", BAD)
def test_a_wrong_input_gives_a_message_and_no_number(typed, message):
    assert euro_effect(120, "m2", typed) == {"state": "error", "message": message}


@pytest.mark.parametrize("quantity", NO_QUANTITIES)
def test_without_a_usable_quantity_there_is_a_message_and_no_number(quantity):
    assert euro_effect(quantity, "m2", "1.250,50") == {"state": "error", "message": NO_QUANTITY}


def test_effect_agrees_with_exact_fractions():
    from fractions import Fraction
    for quantity, _unit, typed, expected in GOOD:
        price = Fraction(expected[1].replace(".", "").replace(",", "."))
        exact = Fraction(expected[0].replace(".", "").replace(",", ".")) * price * 100
        cents = (exact.numerator * 2 + exact.denominator) // (exact.denominator * 2)  # half up
        assert int(expected[2].replace(".", "").replace(",", "")) == cents, (quantity, typed)


READ_BY_THE_REVIEW_FIELD = ("١٢", "12€50", "12 50", "1 2", "12 ,5", "1 250 50", "1 250.50", "1250 500", "5 € 5", "€€5",
                            "12 EUR 50", "1 250,5 0")


def _reads(typed):
    try:
        return parse_eur(typed) is not None
    except ValueError:
        return False


def test_the_field_reads_a_price_as_the_review_field_reads_an_estimate():
    """What this field reads, parse_eur (the field "Schätzung in €") reads as the same number."""
    for _quantity, _unit, typed, expected in GOOD:
        assert parse_eur(typed) == pytest.approx(float(expected[1].replace(".", "").replace(",", ".")), abs=1e-9)
        assert parse_eur(expected[2]) == pytest.approx(float(expected[2].replace(".", "").replace(",", ".")))
    for typed, message in BAD:
        if message == NO_PRICE and typed not in READ_BY_THE_REVIEW_FIELD:
            with pytest.raises(ValueError):
                parse_eur(typed)
    # The review field (not changed by W15) is looser: it drops every space and sign before it reads.
    assert sorted(typed for typed, message in BAD if message == NO_PRICE and _reads(typed)) == \
        sorted(READ_BY_THE_REVIEW_FIELD)
    for typed in EMPTY:
        assert parse_eur(typed) is None


# ---- the JavaScript text ------------------------------------------------------

def euro_effect_source():
    script = static_text("app.js")
    start, end = script.index("function euroEffect("), script.index("/* end of euroEffect */")
    assert start < end
    return script[start:end]


def test_javascript_function_is_one_small_pure_function_with_the_messages_of_the_twin():
    source = euro_effect_source()
    assert len(source.splitlines()) <= 50
    for message in (NO_PRICE, TOO_LONG, NO_QUANTITY):
        assert json.dumps(message, ensure_ascii=False) in source
    for word in ("document", "window", "fetch", "Storage", "state.", "cookie", "XMLHttpRequest", "parseFloat"):
        assert word not in source, word


def test_typed_price_is_not_stored_and_not_sent_by_the_page_script():
    script = static_text("app.js")
    # The three requests of the page are the ones it had before W15.
    # Saturday night added "/api/evidence/" (the button "Treffer anzeigen"): a GET with the finding id only.
    assert re.findall(r"fetch\(\s*\"([^\"]+)\"", script) == [
        "/api/page-image/", "/api/evidence/", "/api/reviews/", "/api/findings"]
    assert 'fetch("/api/evidence/" + encodeURIComponent(finding.id), { cache: "no-store" })' in script
    # W8 added a fourth request: the GET of an export file. It has no body and names only the project
    # the page shows, so it can send no price.
    assert script.count("fetch(") == 5
    assert 'const shown = state.data ? "?project=" + encodeURIComponent(state.data.project) : "";' in script
    assert 'fetch(button.dataset.export + shown, { cache: "no-store" })' in script
    for word in ("XMLHttpRequest", "sendBeacon", "WebSocket", "EventSource", "sessionStorage", "indexedDB",
                 "document.cookie", ".submit("):
        assert word not in script, word
    # The stored values are the name of the reviewer, as before, and since Saturday night the chosen design
    # ("light" or "dark"): no price.
    assert re.findall(r"localStorage\.(\w+)\(([\w$]+)", script) == [
        ("getItem", "THEME_STORE"), ("setItem", "THEME_STORE"), ("getItem", "BY_STORE"), ("setItem", "BY_STORE")]
    assert 'localStorage.setItem(THEME_STORE, next)' in script and 'const next = document.documentElement' in script
    # The body of a review holds the five values it held before; no unit price.
    body = re.search(r"const body = \{(.*?)\};", script, re.S).group(1)
    assert re.findall(r"(\w+):", body) == ["status", "comment", "eur_estimate", "by", "project"]
    assert "unitPrices" not in body and "unit-price" not in body
    box = script[script.index("/* The € field of one cited item."):script.index("function sourceBox(")]
    assert "fetch" not in box and "save(" not in box and "Storage" not in box and "drafts" not in box
    assert '$("eur")' not in box  # the result is not written into the review field by itself
    assert "state.unitPrices[key] = input.value" in box and "unitPrices" not in script.replace(box, "").replace(
        "unitPrices: {},", "", 1)


def test_field_stands_only_in_the_view_fund():
    script, html = static_text("app.js"), static_text("index.html")
    assert "findingCard(shown, true)" in script and "findingCard(finding, false)" in script
    assert "sourceBox(finding, source, withReview)" in script and "withEuro ? euroBox(finding, source) : null" in script
    assert script.count("euroBox(") == 2
    assert "Einheitspreis" in script and "€-Effekt" in script and "Menge laut Liste" in script
    assert "unit-price" not in html and "Einheitspreis" not in html  # the review form is as it was
    assert re.findall(r'<input[^>]*id="(\w[\w-]*)"', html) == ["k3-switch", "comment", "eur", "by"]


# ---- the answer of /api/findings ------------------------------------------------

def make_finding():
    return {
        "id": "X2-aaaaaa", "check": "X2", "layer": "between_lists", "type": "contradiction", "severity": "medium",
        "handover": ["LV_91", "LV_92"],
        "sources": [{"doc": "LV_91", "item_no": "1.10", "page": 2, "quote": "Nenndicke 65 mm"},
                    {"doc": "LV_92", "item_no": "2.20", "page": 4, "quote": "Estrich 50 mm"},
                    {"doc": "LV_92", "item_no": "1", "page": 1, "quote": "gilt die VOB/C"},
                    {"doc": "LV_93", "item_no": "9.99", "page": 1, "quote": "steht in keiner Liste"}],
        "lists_searched": ["LV_91", "LV_92"], "search_terms": ["Estrich"],
        "explanation_de": "Zwei Dicken für denselben Estrich.", "question_de": "Welche Dicke gilt?",
        "exposure": {"quantity": 120.0, "unit": "m2"}, "quotes_verified": True, "origin": "model+code",
        "skeptic": {"status": "survived", "note": "Testnotiz"},
    }


def make_item(doc, item_no, short_text, long_text, quantity, unit, kind="normal"):
    return {
        "doc": doc, "project": "P1", "trade": "Estrich", "format": "pdf", "stage": "anfrage", "item_no": item_no,
        "kind": kind, "section": "", "short_text": short_text, "long_text": long_text, "quantity": quantity,
        "unit": unit, "unit_price": 7654.32, "total": 98765.43, "page": 1, "line": None,
        "pre_trade_text": None, "post_trade_text": None,
    }


ITEMS = [
    make_item("LV_91", "1.10", "Zementestrich", "schwimmender Estrich, Nenndicke 65 mm", 120.0, "m2"),
    make_item("LV_92", "2.20", "Bodenbelag Büro", "Aufbauhöhe: Estrich 50 mm", 85.5, "m"),
    make_item("LV_92", "1", "Vorbemerkung", "Es gilt die VOB/C.", None, None, kind="preliminary_note"),
]


def write_json(path, data):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)


def project_client(tmp_path, items=ITEMS):
    write_json(tmp_path / "out" / "P1" / "findings.json", [make_finding()])
    write_json(tmp_path / "out" / "P1" / "items.json", items)
    return TestClient(create_app(out_dir=str(tmp_path / "out"), reviews_dir=str(tmp_path / "reviews")))


def test_sources_carry_quantity_and_unit_of_the_cited_item_and_no_price(tmp_path):
    response = project_client(tmp_path).get("/api/findings")
    sources = response.json()["findings"][0]["sources"]
    assert [(s["quantity"], s["unit"]) for s in sources] == [(120.0, "m2"), (85.5, "m"), (None, None), (None, None)]
    for forbidden in ("unit_price", "total", "7654", "98765"):
        assert forbidden not in response.text


@pytest.mark.parametrize("quantity", ["12", True, [1], {"a": 1}])
def test_a_quantity_that_is_no_number_is_sent_as_none(tmp_path, quantity):
    items = [dict(ITEMS[0], quantity=quantity, unit=5)] + ITEMS[1:]
    sources = project_client(tmp_path, items).get("/api/findings").json()["findings"][0]["sources"]
    assert sources[0]["quantity"] is None and sources[0]["unit"] == "5"


def test_sample_mode_sources_carry_quantity_and_unit(tmp_path):
    client = TestClient(create_app(out_dir=str(tmp_path / "out"), reviews_dir=str(tmp_path / "reviews")))
    data = client.get("/api/findings").json()
    assert data["mode"] == "sample"
    sources = [source for finding in data["findings"] for source in finding["sources"]]
    assert sources and all("quantity" in source and "unit" in source for source in sources)
    assert any(isinstance(source["quantity"], (int, float)) for source in sources)


def test_endpoints_are_the_three_of_before(tmp_path):
    app = create_app(out_dir=str(tmp_path / "out"), reviews_dir=str(tmp_path / "reviews"))
    paths = sorted(route.path for route in app.routes if route.path.startswith("/api"))
    # W8 added the three GET endpoints of the export; they take no price and write nothing. The views of
    # Saturday evening added five GET endpoints and POST /api/live, which reads an upload in memory and
    # writes nothing (web/views.py; tests in test_web_views.py).
    export = ["/api/export/fragenliste", "/api/export/lv-markiert", "/api/export/risikobericht"]
    views = ["/api/bench", "/api/diff", "/api/evidence/{finding_id}", "/api/live", "/api/lv", "/api/lv/{doc}",
             "/api/matrix"]
    assert paths == sorted(export + views + ["/api/findings", "/api/page-image/{finding_id}/{index}",
                                             "/api/reviews/{finding_id}"])
    for route in app.routes:
        if route.path in export or route.path in views and route.path != "/api/live":
            assert route.methods == {"GET"}
        if route.path == "/api/live":
            assert route.methods == {"POST"}


def test_a_review_click_stores_the_five_keys_and_no_unit_price(tmp_path):
    client = project_client(tmp_path)
    answer = client.post("/api/reviews/X2-aaaaaa", json={
        "status": "confirmed", "comment": "ok", "eur_estimate": "150.060,00", "by": "Test", "project": "P1",
        "unit_price": "1.250,50", "unitPrices": {"X2-aaaaaa/0": "1.250,50"}})
    assert answer.status_code == 200, answer.text
    with open(str(tmp_path / "reviews" / "P1.json"), encoding="utf-8") as handle:
        stored = json.load(handle)
    assert sorted(stored["X2-aaaaaa"]) == ["at", "by", "comment", "eur_estimate", "status"]
    assert stored["X2-aaaaaa"]["eur_estimate"] == 150060.0  # the copied result is read as the same number
    assert "1.250" not in json.dumps(stored) and "1250.5" not in json.dumps(stored)


# ---- the real JavaScript in a headless browser (skipped without one) -------------

def browser():
    """A browser that prints the page back (--dump-dom): Chrome or Chromium, not Edge on Windows."""
    from web import browser as web_browser
    return web_browser.find_dom()


def run_page(tmp_path, body, scripts):
    """Open one page from a file in a headless browser and return the JSON its last script wrote."""
    chrome = browser()
    if not chrome:
        pytest.skip("no Chrome or Chromium on this machine; the Python twin covers the arithmetic")
    page = tmp_path / "page.html"
    parts = ["<!DOCTYPE html><html lang=\"de\"><head><meta charset=\"utf-8\"></head><body>", body]
    parts += ["<script>\n%s\n</script>" % script.replace("</script", "<\\/script") for script in scripts]
    parts.append("</body></html>")
    with open(str(page), "w", encoding="utf-8") as handle:
        handle.write("\n".join(parts))
    command = [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-extensions",
               "--no-first-run", "--user-data-dir=%s" % (tmp_path / "profile"), "--virtual-time-budget=20000",
               "--dump-dom", page.as_uri()]
    try:
        done = subprocess.run(command, capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as error:
        pytest.skip("the browser did not run: %s" % error)
    dom = done.stdout.decode("utf-8", "replace")
    found = re.search(r'<pre id="w15-result">(.*?)</pre>', dom, re.S)
    if not found:
        pytest.skip("the browser gave no page back (exit code %s)" % done.returncode)
    import html
    return json.loads(html.unescape(found.group(1)))


def test_javascript_function_gives_the_answers_of_the_twin(tmp_path):
    cases = [[quantity, unit, typed] for quantity, unit, typed, _expected in GOOD]
    cases += [[120, "m2", typed] for typed in EMPTY] + [[120, "m2", typed] for typed, _message in BAD]
    cases += [[quantity, "m2", "1.250,50"] for quantity in NO_QUANTITIES
              if not (isinstance(quantity, float) and not math.isfinite(quantity))]
    driver = """
      const cases = %s;
      const answers = cases.map((one) => euroEffect(one[0], one[1], one[2]));
      answers.push(euroEffect(NaN, "m2", "1"), euroEffect(Infinity, "m2", "1"), euroEffect(undefined, "m2", "1"),
                   euroEffect(120, "m2", undefined));
      const pre = document.createElement("pre");
      pre.id = "w15-result";
      pre.textContent = JSON.stringify(answers);
      document.body.append(pre);
    """ % json.dumps(cases)
    answers = run_page(tmp_path, "", [euro_effect_source(), driver])
    assert len(answers) == len(cases) + 4
    for case, answer in zip(cases, answers):
        assert answer == euro_effect(*case), case
    assert answers[-4:] == [{"state": "error", "message": NO_QUANTITY}] * 3 + [{"state": "empty"}]


STUB = """
  window.w15Calls = [];
  window.fetch = function (url, options) {
    window.w15Calls.push({ url: String(url), body: options && options.body ? String(options.body) : null });
    const answer = String(url).indexOf("/api/reviews/") === 0 ? %s : %s;
    return Promise.resolve(new Response(JSON.stringify(answer),
      { status: 200, headers: { "Content-Type": "application/json" } }));
  };
"""

DRIVER = """
  (async function () {
    const seen = {};
    const pause = () => new Promise((resolve) => setTimeout(resolve, 50));
    const fields = () => Array.from(document.querySelectorAll("#fund-detail input.unit-price"));
    const type = (field, text) => { field.value = text; field.dispatchEvent(new Event("input", { bubbles: true })); };
    const result = (index) => {
      const node = document.querySelectorAll("#fund-detail .source")[index].querySelector(".euro-result");
      return node ? [node.className, node.textContent] : null;
    };
    try {
      for (let i = 0; i < 100 && !fields().length; i++) await pause();
      seen.fields = fields().length;
      seen.quantities = Array.from(document.querySelectorAll("#fund-detail .euro-quantity")).map((n) => n.textContent);
      seen.none = document.querySelectorAll("#fund-detail .euro-none").length;
      seen.before = result(0);
      type(fields()[0], "1.250,50");
      seen.good = result(0);
      seen.other = result(1);
      type(fields()[1], "12,5 pro m");
      seen.bad = result(1);
      type(fields()[1], "");
      seen.cleared = result(1);
      document.getElementById("tab-pruefen").click();
      await pause(); await pause();
      seen.fundHidden = document.getElementById("view-fund").hidden;
      seen.inReview = document.querySelectorAll("#view-pruefen input.unit-price, #view-pruefen .euro").length;
      seen.estimate = document.getElementById("eur").value;
      document.querySelector('.status-button[data-status="confirmed"]').click();
      await pause(); await pause();
      seen.saveNote = document.getElementById("save-note").textContent;
      document.getElementById("tab-fund").click();
      await pause(); await pause();
      seen.kept = fields().map((field) => field.value);
      seen.keptResult = result(0);
      seen.calls = window.w15Calls;
      seen.stored = [];
      try {
        for (let i = 0; i < localStorage.length; i++) seen.stored.push(localStorage.key(i));
        for (let i = 0; i < sessionStorage.length; i++) seen.stored.push(sessionStorage.key(i));
      } catch (error) { seen.stored.push("no storage"); }
      seen.cookie = document.cookie;
      seen.address = location.search + location.hash;
    } catch (error) {
      seen.error = String(error && error.stack || error);
    }
    const pre = document.createElement("pre");
    pre.id = "w15-result";
    pre.textContent = JSON.stringify(seen);
    document.body.append(pre);
  })();
"""


def test_page_shows_the_effect_at_once_and_sends_the_typed_price_nowhere(tmp_path):
    client = project_client(tmp_path)
    data = client.get("/api/findings").json()
    saved = client.post("/api/reviews/X2-aaaaaa", json={
        "status": "confirmed", "comment": "", "eur_estimate": "", "by": "", "project": "P1"}).json()
    body = re.search(r"<body>(.*)<script", static_text("index.html"), re.S).group(1)
    seen = run_page(tmp_path, body, [STUB % (json.dumps(saved), json.dumps(data)), static_text("app.js"), DRIVER])
    assert "error" not in seen, seen.get("error")
    # Two cited items carry a quantity: two fields; the note and the missing item say why they have none.
    assert seen["fields"] == 2 and seen["none"] == 2
    assert seen["quantities"] == ["Menge laut Liste: 120 m2", "Menge laut Liste: 85,5 m"]
    assert seen["before"] == ["euro-result", ""]
    assert seen["good"] == ["euro-result ok", "€-Effekt: 120 m2 × 1.250,50 € = 150.060,00 €"]
    assert seen["other"] == ["euro-result", ""]  # each cited item has its own field
    assert seen["bad"] == ["euro-result error", NO_PRICE]
    assert seen["cleared"] == ["euro-result", ""]
    # The view "Prüfen" has no such field and its estimate is not filled in by itself.
    assert seen["fundHidden"] is True and seen["inReview"] == 0 and seen["estimate"] == ""
    assert seen["saveNote"].startswith("Gespeichert")
    # Back in "Fund" the price is still in the page (and nowhere else).
    assert seen["kept"] == ["1.250,50", ""] and seen["keptResult"] == seen["good"]
    assert seen["stored"] in ([], ["no storage"]) and seen["cookie"] == "" and seen["address"] == "#fund"
    urls = [call["url"] for call in seen["calls"]]
    assert set(urls) == {"/api/findings", "/api/reviews/X2-aaaaaa"} and urls.count("/api/reviews/X2-aaaaaa") == 1
    review = [json.loads(call["body"]) for call in seen["calls"] if call["body"]]
    assert review == [{"status": "confirmed", "comment": "", "eur_estimate": "", "by": "", "project": "P1"}]
    sent = json.dumps(seen["calls"])
    for trace in ("1.250", "1250", "150.060", "150060", "12,5", "unit"):
        assert trace not in sent, trace
