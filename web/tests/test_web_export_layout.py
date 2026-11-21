"""W8 layout fix, seen in a real browser: in the view "Prüfen" the review form
never lies over the finding, at 1280x720 and at 1920x1080; a long word in a
source card stays inside the card; the keys B, V, U and the arrows work as
before; both views show the three export buttons.

The page is the real index.html, style.css and app.js in a headless Chrome;
only fetch is replaced, and the answer of /api/findings is the one the real
app gives for a synthetic project. Skipped on a machine without Chrome or
Chromium. When a browser is there but gives no page, the test fails.
"""
import html
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from web.app import STATIC_DIR, create_app  # noqa: E402

LONG = ("Die Stützen werden in Köcherfundamente gestellt und nach dem Ausrichten vergossen; der Vergussbeton C30/37 "
        "in fließfähiger Konsistenz, das Verfüllen der Aussparung und alle dafür benötigten Geräte sind in den "
        "Einheitspreis einzurechnen. Vorleistung: bauseitige Montage der Fertigteilstütze. Folgeleistung: sichtbar "
        "bleibender Beton, Oberfläche SB2, Brandschutz R30, Querschnitt 40x50 cm, Stützenhöhe ca. 7,60 m.")
WORD = "Stahlbetonfertigteilstützenundbindermontagearbeiten"
SHORT = "Köcheraussparung,bis70x70x55cm,einschl.Verguss,Schalung,Bewehrung,Abdichtung"


def make_finding(number, sources):
    return {"id": "X1-%06d" % number, "check": "X1", "layer": "between_lists", "type": "double_assignment",
            "severity": "high", "handover": ["LV_91", "LV_92"],
            "sources": [{"doc": doc, "item_no": item_no, "page": page, "quote": "%s (%d)" % (LONG, number)}
                        for doc, item_no, page in sources],
            "lists_searched": ["LV_91", "LV_92", "LV_93"], "search_terms": ["Köcherfundament", "Verguss"],
            "explanation_de": "Das Vergießen der Köcherfundamente steht in drei Positionen von drei Listen (%d)." % number,
            "question_de": "Wer vergießt die Köcherfundamente nach der Stützenmontage (%d)?" % number,
            "exposure": {"quantity": None, "unit": None}, "quotes_verified": True, "origin": "model+code",
            "skeptic": {"status": "survived", "note": "synthetic"}}


THREE = [("LV_91", "1.10", 1), ("LV_92", "2.10", 25), ("LV_93", "3.10", 43)]
FINDINGS = [make_finding(1, THREE), make_finding(2, THREE[:2]), make_finding(3, THREE)]
ITEMS = [{"doc": doc, "project": "P1", "trade": "%s %s" % (WORD, doc), "format": "pdf", "stage": "anfrage",
          "item_no": item_no, "kind": "normal", "section": "", "short_text": SHORT, "long_text": LONG,
          "quantity": 12.0, "unit": "St", "unit_price": None, "total": None, "page": page, "line": None,
          "pre_trade_text": None, "post_trade_text": None} for doc, item_no, page in THREE]


def browser():
    """A browser that prints the page back (--dump-dom): Chrome or Chromium, not Edge on Windows."""
    from web import browser as web_browser
    return web_browser.find_dom()


def static_text(name):
    with open(os.path.join(STATIC_DIR, name), encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture(scope="module")
def answer(tmp_path_factory):
    folder = tmp_path_factory.mktemp("layout")
    os.makedirs(str(folder / "out" / "P1"))
    for name, data in (("findings.json", FINDINGS), ("items.json", ITEMS)):
        with open(str(folder / "out" / "P1" / name), "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
    client = TestClient(create_app(out_dir=str(folder / "out"), reviews_dir=str(folder / "reviews")))
    data = client.get("/api/findings").json()
    assert len(data["findings"]) == 3 and all(entry["k3_pass"] for entry in data["findings"])
    return data


STUB = """
  window.w8Calls = [];
  window.fetch = function (url, options) {
    window.w8Calls.push({ url: String(url), method: (options && options.method) || "GET",
                          body: options && options.body ? JSON.parse(options.body) : null });
    let answer = %s;
    if (String(url).indexOf("/api/reviews/") === 0) {
      const status = JSON.parse(options.body).status;
      answer = { id: "x", review: { status: status, by: "", comment: "", eur_estimate: null, at: "2026-11-21T10:42" },
                 counters: answer.counters };
    }
    if (String(url).indexOf("/api/export/") === 0) {
      return Promise.resolve(new Response("file", { status: 200, headers: {
        "Content-Disposition": 'attachment; filename="Test.docx"' } }));
    }
    return Promise.resolve(new Response(JSON.stringify(answer),
      { status: 200, headers: { "Content-Type": "application/json" } }));
  };
"""

DRIVER = """
  (async function () {
    const seen = { errors: [] };
    window.addEventListener("error", (event) => seen.errors.push(String(event.message)));
    const pause = (time) => new Promise((resolve) => setTimeout(resolve, time || 60));
    const rect = (node) => { const r = node.getBoundingClientRect();
      return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, height: r.height, width: r.width }; };
    const key = (name) => document.dispatchEvent(new KeyboardEvent("keydown", { key: name, bubbles: true, cancelable: true }));
    const shown = (node) => { const r = node.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
    try {
      await pause(200);
      const view = "%s";
      seen.viewport = [window.innerWidth, window.innerHeight];
      seen.pageScrolls = document.documentElement.scrollHeight > window.innerHeight + 1;
      seen.bodyClass = document.body.className;
      const root = document.getElementById("view-" + view);
      seen.exportButtons = Array.from(root.querySelectorAll(".export-button")).filter(shown).map((b) => b.textContent);
      const hiddenView = document.getElementById(view === "fund" ? "view-pruefen" : "view-fund");
      seen.hiddenButtons = Array.from(hiddenView.querySelectorAll(".export-button")).filter(shown).length;
      // Smallest font of any text that is shown.
      let smallest = 1000;
      for (const node of document.body.querySelectorAll("*")) {
        if (!shown(node)) continue;
        const own = Array.from(node.childNodes).some((child) => child.nodeType === 3 && child.textContent.trim());
        if (own || node.tagName === "INPUT") smallest = Math.min(smallest, parseFloat(getComputedStyle(node).fontSize));
      }
      seen.smallestFont = smallest;
      const detail = document.getElementById(view === "fund" ? "fund-detail" : "pruefen-detail");
      // A long word stays inside its card, and the cards stay inside the finding.
      seen.cards = Array.from(detail.querySelectorAll(".source")).map((card) => {
        const box = rect(card);
        const lines = Array.from(card.querySelectorAll(".where, .item, blockquote"));
        return { width: box.width, insideDetail: box.right <= rect(detail).right + 1 && box.left >= rect(detail).left - 1,
                 overflow: lines.filter((line) => line.scrollWidth > line.clientWidth + 1 ||
                   rect(line).right > box.right + 1).length,
                 cardOverflow: card.scrollWidth > card.clientWidth + 1 };
      });
      seen.columns = new Set(Array.from(detail.querySelectorAll(".source")).map((card) => Math.round(rect(card).left))).size;
      if (view === "pruefen") {
        const form = document.getElementById("review-form");
        const box = document.getElementById("pruefen-scroll");
        seen.form = rect(form);
        seen.box = rect(box);
        seen.counters = rect(document.getElementById("counters"));
        seen.boxScrolls = box.scrollHeight > box.clientHeight + 1;
        seen.formPosition = getComputedStyle(form).position;
        // Every part of the finding can be brought into view above the form, and nothing lies over it there.
        const parts = Array.from(detail.querySelectorAll("h2, .where, blockquote, .statement"));
        seen.parts = parts.length;
        seen.covered = [];
        seen.reach = [];
        for (const part of parts) {
          for (const edge of ["top", "bottom"]) {
            const now = rect(part);
            box.scrollTop += edge === "top" ? now.top - seen.box.top : now.bottom - seen.box.bottom;
            await pause(10);
            const at = rect(part);
            const y = edge === "top" ? at.top + 3 : at.bottom - 3;
            const inBox = y >= seen.box.top && y <= seen.box.bottom && y < seen.form.top;
            const hit = document.elementFromPoint(at.left + 5, y);
            seen.reach.push(inBox);
            if (!inBox || !hit || !detail.contains(hit) || form.contains(hit)) {
              seen.covered.push(part.className + "/" + edge + "/" + (hit ? hit.tagName + "." + hit.className : "none"));
            }
          }
        }
        // Scrolled to the end, the last line of the scrolling part ends above the form.
        box.scrollTop = box.scrollHeight;
        await pause(10);
        const last = box.lastElementChild;
        seen.lastLine = { bottom: rect(last).bottom, formTop: rect(form).top, boxBottom: rect(box).bottom };
        // Keys: arrows turn the pages, B, V and U write a review; PageDown scrolls the finding.
        box.scrollTop = 0;
        const position = () => document.getElementById("position").textContent;
        seen.positions = [position()];
        key("ArrowRight"); await pause();
        seen.positions.push(position());
        seen.alignedAfterArrow = Math.abs(rect(document.getElementById("pruefen-detail")).top - rect(box).top) <= 2;
        const before = box.scrollTop;
        key("PageDown"); await pause();
        seen.pageDownScrolls = box.scrollTop > before;
        key("ArrowRight"); await pause();
        seen.positions.push(position());
        key("ArrowRight"); await pause();
        seen.positions.push(position());
        key("ArrowLeft"); await pause();
        seen.positions.push(position());
        for (const letter of ["b", "V", "u"]) { key(letter); await pause(); }
        seen.reviews = window.w8Calls.filter((call) => call.method === "POST").map((call) => [call.url, call.body.status]);
        seen.saveNote = document.getElementById("save-note").textContent;
        seen.active = Array.from(document.querySelectorAll(".status-button.active")).map((b) => b.dataset.status);
        const field = document.getElementById("comment");
        field.focus();
        field.dispatchEvent(new KeyboardEvent("keydown", { key: "b", bubbles: true, cancelable: true }));
        await pause();
        seen.reviewsAfterTyping = window.w8Calls.filter((call) => call.method === "POST").length;
        field.blur();
      }
      root.querySelector(".export-button").click();
      await pause(200);
      seen.exportCalls = window.w8Calls.filter((call) => call.url.indexOf("/api/export/") === 0).map((call) => call.url);
      seen.exportNote = root.querySelector(".export-note").textContent;
    } catch (error) {
      seen.errors.push(String(error && error.stack || error));
    }
    const pre = document.createElement("pre");
    pre.id = "w8-result";
    pre.textContent = JSON.stringify(seen);
    document.body.append(pre);
  })();
"""


FRAME = {}  # height of the window frame of this browser: window height minus the height of the page


def open_page(tmp_path, answer, view, width, height):
    """The real page with a page area of width x height; returns what the driver measured.

    --window-size sets the size of the window. A headless Chrome may take a part
    of it for its frame, so the page is opened again with a window that much higher.
    """
    seen = open_window(tmp_path, answer, view, width, height + FRAME.get("height", 0))
    if seen["viewport"][1] != height:
        FRAME["height"] = FRAME.get("height", 0) + height - seen["viewport"][1]
        seen = open_window(tmp_path, answer, view, width, height + FRAME["height"])
    assert seen["viewport"] == [width, height]
    return seen


def open_window(tmp_path, answer, view, width, height):
    chrome = browser()
    if not chrome:
        pytest.skip("no Chrome or Chromium on this machine")
    page = static_text("index.html")
    page = page.replace('<link rel="stylesheet" href="/static/style.css">', "<style>\n%s\n</style>" % static_text("style.css"))
    scripts = [STUB % json.dumps(answer, ensure_ascii=False), static_text("app.js"), DRIVER % view]
    inline = "\n".join("<script>\n%s\n</script>" % script.replace("</script", "<\\/script") for script in scripts)
    assert '<script src="/static/app.js"></script>' in page and "<style>" in page
    page = page.replace('<script src="/static/app.js"></script>', inline)
    path = tmp_path / "page.html"
    with open(str(path), "w", encoding="utf-8") as handle:
        handle.write(page)
    found, why = None, ""
    for attempt in (1, 2):  # a headless Chrome sometimes hangs at its start; one second try, then the test fails
        command = [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-extensions", "--no-first-run",
                   "--user-data-dir=%s" % (tmp_path / ("profile%d" % attempt)), "--window-size=%d,%d" % (width, height),
                   "--virtual-time-budget=20000", "--dump-dom", "%s#%s" % (path.as_uri(), view)]
        try:
            done = subprocess.run(command, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            why = "no answer within 60 seconds"
            continue
        found = re.search(r'<pre id="w8-result">(.*?)</pre>', done.stdout.decode("utf-8", "replace"), re.S)
        if found:
            break
        why = "exit code %s: %s" % (done.returncode, done.stderr.decode("utf-8", "replace")[-300:])
    assert found, "the browser is there but gave no page back (%s)" % why
    seen = json.loads(html.unescape(found.group(1)))
    assert seen["errors"] == []
    return seen


LABELS = ["Fragenliste exportieren", "LV markiert exportieren", "Risikobericht exportieren"]


# 1280x633 is the page area of a headless Chrome that is started with --window-size=1280,720.
@pytest.mark.parametrize("width,height,room", [(1280, 720, 340), (1920, 1080, 680), (1280, 633, 250)])
def test_form_never_lies_over_the_finding_in_the_view_pruefen(tmp_path, answer, width, height, room):
    seen = open_page(tmp_path, answer, "pruefen", width, height)
    form, box = seen["form"], seen["box"]
    # Counters, the box of the finding and the form stand one under the other inside the window.
    assert seen["formPosition"] == "static" and not seen["pageScrolls"]
    assert seen["counters"]["bottom"] <= box["top"] + 1
    assert box["bottom"] <= form["top"] + 1
    assert form["bottom"] <= height
    assert form["height"] <= 215  # the form stays compact: the finding gets the rest of the window
    assert box["height"] >= room, box["height"]
    # The three sources with long quotes need more room than the box has: it scrolls, the form does not move.
    assert seen["boxScrolls"] is True
    assert seen["parts"] == 3 + 3 + 2 + 1  # title, three source heads, three quotes, explanation and question
    assert all(seen["reach"]) and seen["covered"] == []
    assert seen["lastLine"]["bottom"] <= seen["lastLine"]["formTop"] + 1
    assert seen["lastLine"]["bottom"] <= seen["lastLine"]["boxBottom"] + 1
    # The three source cards stand side by side, and no long word leaves its card.
    assert seen["columns"] == 3 and len(seen["cards"]) == 3
    for card in seen["cards"]:
        assert card["overflow"] == 0 and not card["cardOverflow"] and card["insideDetail"] and card["width"] >= 340
    assert seen["smallestFont"] >= 18
    assert seen["exportButtons"] == LABELS and seen["hiddenButtons"] == 0
    assert seen["exportCalls"] == ["/api/export/fragenliste?project=P1"] and seen["exportNote"] == "Exportiert: Test.docx"


def test_keys_work_as_before_at_1280x720(tmp_path, answer):
    seen = open_page(tmp_path, answer, "pruefen", 1280, 720)
    assert seen["positions"] == ["Fund 1 von 3", "Fund 2 von 3", "Fund 3 von 3", "Fund 3 von 3", "Fund 2 von 3"]
    assert seen["alignedAfterArrow"] is True and seen["pageDownScrolls"] is True
    assert seen["reviews"] == [["/api/reviews/X1-000002", "confirmed"], ["/api/reviews/X1-000002", "rejected"],
                               ["/api/reviews/X1-000002", "unclear"]]
    assert seen["active"] == ["unclear"] and seen["saveNote"].startswith("Gespeichert: unklar")
    assert seen["reviewsAfterTyping"] == 3  # inside a text field a letter is text


@pytest.mark.parametrize("width,height,columns", [(1280, 720, 2), (1920, 1080, 3)])
def test_view_fund_keeps_long_words_inside_the_cards_and_has_the_export_buttons(tmp_path, answer, width, height, columns):
    seen = open_page(tmp_path, answer, "fund", width, height)
    assert "in-pruefen" not in seen["bodyClass"]
    assert len(seen["cards"]) == 3 and seen["columns"] == columns
    for card in seen["cards"]:
        assert card["overflow"] == 0 and not card["cardOverflow"] and card["insideDetail"] and card["width"] >= 340
    assert seen["smallestFont"] >= 18
    assert seen["exportButtons"] == LABELS and seen["hiddenButtons"] == 0
    assert seen["exportCalls"] == ["/api/export/fragenliste?project=P1"] and seen["exportNote"] == "Exportiert: Test.docx"


@pytest.mark.parametrize("width,height", [(1280, 500), (500, 634), (1100, 700)])
def test_low_or_narrow_window_scrolls_as_a_whole_and_the_form_stays_in_the_flow(tmp_path, answer, width, height):
    seen = open_page(tmp_path, answer, "pruefen", width, height)
    assert seen["formPosition"] == "static" and seen["pageScrolls"] is True and seen["boxScrolls"] is False
    assert seen["box"]["height"] >= 600  # the whole finding stands in the page; nothing is cut off
    assert seen["box"]["bottom"] <= seen["form"]["top"] + 1  # the form stands under the finding, not over it
    assert seen["exportButtons"] == LABELS and all(not card["cardOverflow"] for card in seen["cards"])
    assert seen["positions"] == ["Fund 1 von 3", "Fund 2 von 3", "Fund 3 von 3", "Fund 3 von 3", "Fund 2 von 3"]
    assert [status for _, status in seen["reviews"]] == ["confirmed", "rejected", "unclear"]


def test_layout_rules_stand_in_the_stylesheet():
    css = static_text("style.css")
    assert "position: sticky" not in css and "position: fixed" not in css
    assert re.search(r"@media \(min-height: 600px\) and \(min-width: 1200px\) \{\s*body\.in-pruefen \{ height: 100vh;", css)
    assert re.search(r"body\.in-pruefen \.review-scroll \{[^}]*min-height: 160px", css) and "overflow: hidden" not in css
    assert re.search(r"\.source \.where \{[^}]*overflow-wrap: anywhere", css)
    assert re.search(r"\.source \.item \{[^}]*overflow-wrap: anywhere", css)
    script = static_text("app.js")
    assert 'document.body.classList.toggle("in-pruefen", state.view === "pruefen")' in script
    assert re.search(r'KEYS = \{ b: "confirmed", v: "rejected", u: "unclear" \}', script)
