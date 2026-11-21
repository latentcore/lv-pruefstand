"""W6/W7: one page without a build step, German, a warm dark design with a light
one by one click, smallest font 18 px, fully offline, started with one command."""
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from web.app import STATIC_DIR, create_app  # noqa: E402

STATIC_FILES = ["index.html", "app.js", "style.css", "views.js", "views.css"]


def static_text(name):
    with open(os.path.join(STATIC_DIR, name), encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(out_dir=str(tmp_path / "out"), reviews_dir=str(tmp_path / "reviews")))


def test_page_and_its_files_are_served(client):
    page = client.get("/")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert page.text.replace("\r\n", "\n") == static_text("index.html")
    for name in ("app.js", "style.css", "views.js", "views.css"):
        response = client.get("/static/%s" % name)
        assert response.status_code == 200
        assert response.text.replace("\r\n", "\n") == static_text(name)
        assert "/static/%s" % name in page.text


def test_page_is_german_and_has_the_two_views():
    html = static_text("index.html")
    assert '<html lang="de">' in html
    assert re.search(r'data-view="fund">Fund</button>', html)
    assert re.search(r'data-view="pruefen">Prüfen</button>', html)
    script = static_text("app.js")
    for word in ("Quelle zeigen", "bestätigt", "verworfen", "unklar", "offen", "Durchsuchte Listen",
                 "Suchbegriffe", "Gegenprüfung", "Seite ", "Position "):
        assert word in script, word
    for word in ("Bestätigt", "Verworfen", "Unklar", "Kommentar (ein Satz)", "Schätzung in € (optional)"):
        assert word in html, word


def test_review_has_one_click_and_one_key_per_status():
    html = static_text("index.html")
    for status, key in (("confirmed", "B"), ("rejected", "V"), ("unclear", "U")):
        assert re.search(r'<button type="button" class="status-button %s" data-status="%s">[^<]+<kbd>%s</kbd>'
                         % (status, status, key), html)
    assert re.search(r'KEYS = \{ b: "confirmed", v: "rejected", u: "unclear" \}', static_text("app.js"))


def test_k3_switch_is_visible_and_on_by_default():
    html = static_text("index.html")
    assert re.search(r'<input type="checkbox" id="k3-switch" checked>', html)
    script = static_text("app.js")
    assert "filterOn: true" in script
    assert "held_back" in script  # the counters show what the filter holds back


def test_page_needs_no_outside_resource():
    for name in STATIC_FILES:
        text = static_text(name)
        assert not re.search(r"https?:|//[a-z0-9.-]+\.[a-z]{2,}/", text, re.I), name
        assert "@import" not in text and "url(" not in text, name
    html = static_text("index.html")
    assert re.findall(r'(?:src|href)="([^"]+)"', html) == [
        "/static/style.css", "/static/views.css", "/static/views.js", "/static/app.js"]
    assert "import(" not in static_text("app.js") and "importScripts" not in static_text("app.js")


def test_smallest_font_is_18_px():
    css = static_text("style.css")
    sizes = re.findall(r"font-size\s*:\s*([^;}]+)", css)
    assert sizes, "no font size found"
    for size in sizes:
        match = re.match(r"^(\d+(?:\.\d+)?)px$", size.strip())
        assert match, "font size %r is not in px" % size
        assert float(match.group(1)) >= 18, size
    assert re.search(r"body\s*\{[^}]*font-size:\s*20px", css)
    # Form controls and keys take the page font; a browser default would be smaller.
    assert re.search(r"button, input, select, textarea\s*\{\s*font:\s*inherit", css)
    assert re.search(r"kbd\s*\{\s*font:\s*inherit", css)
    for shorthand in re.findall(r"(?<![-\w])font\s*:\s*([^;}]+)", css):
        assert shorthand.strip() == "inherit"
    html, script = static_text("index.html"), static_text("app.js")
    assert "font-size" not in html and "style=" not in html
    assert "fontSize" not in script and "font-size" not in script
    for tag in ("<small", "<sub", "<sup", "<textarea", "<select"):
        assert tag not in html


def test_design_is_warm_and_dark_with_a_light_one_by_one_click():
    """Mert, Sat 21 Nov evening: a white page strains the eyes. The page is dark by default; the button in the
    header switches to the light design (for a weak projector) and the choice stays in the browser. The system
    setting does not choose: the page looks the same on every machine until someone clicks."""
    css = static_text("style.css")
    root = re.search(r":root \{([^}]*)\}", css).group(1)
    light = re.search(r":root\[data-theme=\"light\"\] \{([^}]*)\}", css).group(1)
    assert re.search(r"color-scheme:\s*dark;", root) and re.search(r"--paper:\s*#1f1e1d;", root)
    assert re.search(r"color-scheme:\s*light;", light) and re.search(r"--paper:\s*#ffffff;", light)
    assert "prefers-color-scheme" not in css + static_text("views.css")
    assert re.search(r"body\s*\{[^}]*background:\s*var\(--paper\)", css)
    # Every colour the light design changes is a variable of the dark one: no colour is left behind in a rule.
    names = set(re.findall(r"(--[\w-]+):", light))
    assert names and names <= set(re.findall(r"(--[\w-]+):", root))
    html, script = static_text("index.html"), static_text("app.js")
    assert '<meta name="color-scheme" content="dark light">' in html
    assert '<button type="button" class="theme-toggle" id="theme-toggle"' in html
    assert 'document.documentElement.setAttribute("data-theme", "light")' in script
    assert 'localStorage.setItem(THEME_STORE, next)' in script


def test_data_text_is_never_put_into_the_page_as_html():
    script = static_text("app.js")
    for risky in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert risky not in script


def test_there_is_no_api_description_page(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


# ---- one command ------------------------------------------------------------

def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def call(port, path, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=data,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


class Running:
    """`python -m web` as its own process, as Mert starts it."""

    def __init__(self, tmp_path, *extra):
        self.port = free_port()
        command = [sys.executable, "-m", "web", "--port", str(self.port),
                   "--out", str(tmp_path / "out"), "--reviews", str(tmp_path / "reviews")] + list(extra)
        self.process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def __enter__(self):
        deadline = time.time() + 30
        while True:
            try:
                call(self.port, "/api/findings")
                return self
            except (urllib.error.URLError, ConnectionError, socket.timeout):
                if self.process.poll() is not None or time.time() > deadline:
                    output = self.process.stdout.read().decode("utf-8", "replace")
                    self.stop()
                    raise AssertionError("python -m web did not start: %s" % output)
                time.sleep(0.1)

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.process.stdout.close()

    def __exit__(self, *unused):
        self.stop()


def test_one_command_starts_the_app_and_a_click_survives_its_restart(tmp_path):
    with Running(tmp_path) as app:
        data = call(app.port, "/api/findings")
        assert data["mode"] == "sample"
        finding_id = data["findings"][0]["id"]
        answer = call(app.port, "/api/reviews/%s" % finding_id,
                      {"status": "confirmed", "comment": "bleibt", "eur_estimate": "1.500", "by": "Test"})
        assert answer["counters"]["all"]["confirmed"] == 1
        with urllib.request.urlopen("http://127.0.0.1:%d/" % app.port, timeout=5) as page:
            assert b"<title>LV-Pr\xc3\xbcfstand</title>" in page.read()
    with Running(tmp_path) as app:
        data = call(app.port, "/api/findings")
        review = [f for f in data["findings"] if f["id"] == finding_id][0]["review"]
        assert (review["status"], review["comment"], review["eur_estimate"], review["by"]) == (
            "confirmed", "bleibt", 1500.0, "Test")
        assert data["counters"]["all"]["confirmed"] == 1


def test_one_command_reads_a_named_project(tmp_path):
    folder = tmp_path / "out" / "P7"
    os.makedirs(str(folder))
    finding = {"id": "X2-aaaaaa", "check": "X2", "layer": "between_lists", "type": "contradiction",
               "severity": "high", "handover": [], "sources": [], "lists_searched": [], "search_terms": [],
               "explanation_de": "a", "question_de": "b", "exposure": {"quantity": None, "unit": None},
               "quotes_verified": True, "origin": "code", "skeptic": {"status": "survived", "note": ""}}
    with open(str(folder / "findings.json"), "w", encoding="utf-8") as handle:
        json.dump([finding], handle)
    with Running(tmp_path, "--project", "P7") as app:
        data = call(app.port, "/api/findings")
        assert (data["mode"], data["project"]) == ("real", "P7")
        assert [f["id"] for f in data["findings"]] == ["X2-aaaaaa"]
