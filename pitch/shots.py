"""Screenshots of the real review screen for slide 3 (W10).

    python -m pitch.shots --project 79-222        out/pitch/shots/fund.png, pruefen.png

It starts the app of web/ (the same create_app that `python -m web` starts) on
a free port of this machine, with the real out/<project>/ and reviews/, and
lets a headless Chrome or Edge take one picture of 1920 x 1080 px of the views "Bauwerk" (the cell of
the opening finding selected) and "Fund". The page
is the app's own index.html, style.css and app.js; one short script is added
that picks the opening finding (pitch/opening.json), nothing else. The run
writes no review.

The pictures carry quotes from the organizer's files: they stay in out/ and
are never committed. `python -m pitch.build` puts them into the deck.

Exit 0: both pictures written, or no Chrome on this machine (nothing written,
the deck then shows grey boxes). Exit 1: the browser gave no picture. Exit 2:
out/<project>/findings.json is missing; the app would show its synthetic
samples, and those do not go into the deck.
"""
import argparse
import json
import os
import socket
import struct
import sys
import threading
import time

from pitch import chrome, numbers

WIDTH, HEIGHT = 1920, 1080
VIEWS = (("bauwerk", "#bauwerk"), ("fund", ""))
DEFAULT_OUT = numbers.path("out", "pitch", "shots")
# Picks one finding in the page: in the view "Bauwerk" a click on the cell that holds it; else a
# click on its entry in the list of the view "Fund", and "Weiter" in the view "Prüfen" until the
# finding is the one shown.
DRIVER = """
<script>
(function () {
  var id = %s, tries = 0;
  function pick() {
    tries += 1;
    var entry = document.querySelector('#fund-list button[data-id="' + id + '"]');
    var bauwerk = location.hash === "#bauwerk";
    var cell = bauwerk ? document.querySelector('td[data-findings~="' + id + '"]') : null;
    if (!entry || (bauwerk && !cell)) { if (tries < 200) setTimeout(pick, 50); return; }
    if (bauwerk) {
      if (!cell.classList.contains("active")) cell.click();
      setTimeout(function () { document.documentElement.setAttribute("data-shot-ready", id); }, 300);
      return;
    }
    if (!entry.classList.contains("active")) entry.click();
    var steps = 0;
    var detail = document.getElementById("pruefen-detail");
    while (detail && detail.textContent.indexOf(id) < 0 && steps < 200) {
      document.getElementById("next").click();
      steps += 1;
    }
    document.documentElement.setAttribute("data-shot-ready", id);
  }
  window.addEventListener("load", pick);
})();
</script>
"""


def driven_page(index_html, finding_id):
    """The app's page with the driver script added before </body>."""
    script = DRIVER % json.dumps(finding_id)
    if "</body>" not in index_html:
        raise ValueError("the app's index.html has no </body>")
    return index_html.replace("</body>", script + "</body>", 1)


def make_app(out_dir, reviews_dir, project, finding_id):
    """The app of web/ plus one page, /shot, that is its index.html with the driver script."""
    from fastapi.responses import HTMLResponse
    from web.app import STATIC_DIR, create_app
    app = create_app(out_dir=out_dir, reviews_dir=reviews_dir, project=project)

    @app.get("/shot")
    def shot():
        with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as handle:
            return HTMLResponse(driven_page(handle.read(), finding_id), headers={"Cache-Control": "no-store"})

    return app


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class Server:
    """The app on 127.0.0.1, in a thread, for the time of a `with` block."""

    def __init__(self, app):
        import uvicorn
        self.port = free_port()
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="error"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        deadline = time.time() + 20
        while not self.server.started:
            if time.time() > deadline or not self.thread.is_alive():
                raise RuntimeError("the app did not start")
            time.sleep(0.05)
        return "http://127.0.0.1:%d" % self.port

    def __exit__(self, *unused):
        self.server.should_exit = True
        self.thread.join(timeout=10)


def png_size(file_path):
    """(width, height) of a PNG file."""
    with open(file_path, "rb") as handle:
        head = handle.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("%s is not a PNG file" % file_path)
    return struct.unpack(">II", head[16:24])


def take(project, out_dir, data_dir=None, reviews_dir=None, browser=None, finding_id=None):
    """Write the pictures. Returns (exit code, lines to print)."""
    data_dir = data_dir or numbers.path("out")
    reviews_dir = reviews_dir or numbers.path("reviews")
    if not os.path.isfile(os.path.join(data_dir, project, "findings.json")):
        return 2, ["pitch.shots: %s is missing; build it first (python -m pipeline.run). No picture of the "
                   "synthetic samples is taken." % os.path.join(data_dir, project, "findings.json")]
    if not browser:
        return 0, ["no Chrome or Chromium on this machine: no screenshots. The deck shows grey boxes."]
    finding_id = finding_id or numbers.load_opening()["finding_id"]
    os.makedirs(out_dir, exist_ok=True)
    lines = []
    with Server(make_app(data_dir, reviews_dir, project, finding_id)) as base:
        for name, anchor in VIEWS:
            target = os.path.join(out_dir, name + ".png")
            if os.path.isfile(target):
                os.remove(target)
            why = chrome.screenshot(browser, "%s/shot%s" % (base, anchor), target, WIDTH, HEIGHT)
            if why:
                return 1, lines + ["pitch.shots: no picture of the view %s: %s" % (name, why)]
            size = png_size(target)
            if size != (WIDTH, HEIGHT):
                return 1, lines + ["pitch.shots: %s is %d x %d px, not %d x %d" % ((target,) + size + (WIDTH, HEIGHT))]
            lines.append("written: %s (%d x %d px, finding %s)" % (target, WIDTH, HEIGHT, finding_id))
    return 0, lines + ["not in git: the pictures carry quotes from the organizer's files. Now run python -m pitch.build"]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pitch.shots", description=__doc__.split("\n")[0])
    parser.add_argument("--project", default=None, help="folder name in out/ (default: the project of pitch/numbers.json)")
    parser.add_argument("--out", default=DEFAULT_OUT, help="folder for the pictures (default: out/pitch/shots)")
    parser.add_argument("--data", default=None, help="pipeline output folder (default: out/)")
    parser.add_argument("--reviews", default=None, help="folder with the review files (default: reviews/)")
    parser.add_argument("--chrome", default=None, help="browser file, or \"none\"")
    args = parser.parse_args(argv)
    try:
        project = args.project or numbers.load()["project"]
        code, lines = take(project, args.out, args.data, args.reviews, chrome.browser(args.chrome))
    except (OSError, ValueError, RuntimeError, numbers.NumberError) as error:
        code, lines = 1, ["pitch.shots: %s" % error]
    for line in lines:
        print(line, file=sys.stderr if line.startswith("pitch.shots:") else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
