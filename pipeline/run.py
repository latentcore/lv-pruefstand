"""One command: data/ -> out/<project>/ (MASTER_PLAN §8), the stored demo run (W9).

    python -m pipeline.run [data_dir] [out_dir] [--cache DIR] [--verbose]

Runs every merged step in the order the screen needs and prints one line per
step: number, name, ok / failed / skipped with the reason, seconds. No line
holds a price or an amount. At the end it prints the command that starts the
screen.

Exit code: 0 every step ran and is ok; 1 a step failed (it is named);
3 no step failed, but input is missing (no data folder, no Poppler) and steps
were skipped.

No model is called. The findings between the lists and the verdicts of the
counter-check are stored results (pipeline/cross/results/, pipeline/skeptic/
results/); everything else is computed here from the files in data_dir.

The order is fixed in build_steps(). Two things the review screen cannot see
by itself are settled by it: the merge writes the independent verdict into
out/79-222/findings.json (without it the screen shows the finder's own
verdicts), and the severity step then sets the levels by the fixed rules
(without it the screen shows the finder's levels). When a step after the merge
does not end ok, the half-done findings.json is removed, so the screen shows
its sample-data line instead of wrong data.

After the severity step the page check reads the stated page of every source
of the findings, checks the quote on it by code and writes the page images the
screen shows behind "Quelle zeigen" (out/79-222/pages/). The last step compares
the twins and the stages of the other projects (out/diff/).
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = "79-222"
STORED_FINDINGS = os.path.join(ROOT, "pipeline", "cross", "results", PROJECT, "findings.json")
STORED_VERDICTS = os.path.join(ROOT, "pipeline", "skeptic", "results", PROJECT, "verdicts.json")
STORED_TERMS = os.path.join(ROOT, "pipeline", "skeptic", "results", PROJECT, "terms.json")
COMMITTED_MANIFEST = os.path.join(ROOT, "pipeline", "pdf", "results", PROJECT, "manifest.json")
PRINT_PDF = "LV-Ausdruck-[PROJEKT_004].pdf"
OFFER_PDF = "Angebot AN24-0305.pdf"

OK, FAILED, SKIPPED = "ok", "failed", "skipped"
EXIT_OK, EXIT_FAILED, EXIT_INPUT_MISSING = 0, 1, 3

# Step names that other code and the tests refer to.
TEXT, READER, MANIFEST = "79-222 page texts", "79-222 reader", "79-222 manifest check"
PRINT_READER, OFFER_READER = "print reader PROJEKT_004", "offer reader AN24-0305"
GAEB90, GAEBXML, BASE = "GAEB 90 reader", "GAEB XML reader", "base checks B1-B12"
EVIDENCE, RULES, MERGE = "skeptic evidence", "skeptic rules", "skeptic merge"
SEVERITY = "severity rules"
PAGES, DIFF = "page check, page images", "twin and stage comparison"
# The steps that write and finish out/79-222/findings.json, in this order.
FINDINGS_CHAIN = (MERGE, SEVERITY)


class Step:
    """One line of the run.

    commands: a list of argument lists (or a function that returns one); each
    runs as its own process in the repository folder. call: a function run in
    this process instead. Both return nothing when all is well. needs: names
    of earlier steps that must be ok. missing: a function that returns the
    reason when an input is not there, else None. verify: a function run after
    the commands; it returns the reason when the result is not right.
    detail: a function that returns a few words for the ok line (counts only).
    """

    def __init__(self, name, commands=None, call=None, needs=(), missing=None, verify=None, detail=None):
        self.name = name
        self.commands = commands
        self.call = call
        self.needs = tuple(needs)
        self.missing = missing
        self.verify = verify
        self.detail = detail


def _short(text, limit=200):
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    line = lines[-1] if lines else ""
    return line if len(line) <= limit else line[:limit - 3] + "..."


def run_command(arguments, verbose=False, stream=None):
    """Run one command in the repository folder. Returns None, or why it failed."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        done = subprocess.run(arguments, cwd=ROOT, env=env, capture_output=True)
    except OSError as error:
        return "cannot start %s: %s" % (arguments[0], error)
    out = done.stdout.decode("utf-8", "replace")
    err = done.stderr.decode("utf-8", "replace")
    if verbose and stream is not None:
        for line in (out + err).splitlines():
            print("        | %s" % line, file=stream)
    if done.returncode != 0:
        return "exit code %d: %s" % (done.returncode, _short(err) or _short(out) or "no message")
    return None


def _execute(step, verbose, stream):
    if step.call is not None:
        reason = step.call()
        if reason:
            return reason
    commands = step.commands() if callable(step.commands) else (step.commands or [])
    for arguments in commands:
        reason = run_command(arguments, verbose, stream)
        if reason:
            return reason
    return step.verify() if step.verify else None


def run_steps(steps, stream=None, verbose=False):
    """Run the steps in their order and print one line for each.

    Returns a list of (name, status, reason or detail, seconds). A step whose
    needed step is not ok, or whose input is missing, is skipped and says why;
    it is never run on what an earlier run left behind.
    """
    stream = stream or sys.stdout
    status_of, results = {}, []
    width = max([len(step.name) for step in steps] + [1])
    for number, step in enumerate(steps, 1):
        start = time.perf_counter()
        note = ""
        blocked = [name for name in step.needs if status_of.get(name) != OK]
        if blocked:
            status = SKIPPED
            note = "needs the step \"%s\", which %s" % (
                blocked[0], {FAILED: "failed", SKIPPED: "was skipped"}.get(status_of.get(blocked[0]), "did not run"))
        else:
            try:
                reason = step.missing() if step.missing else None
                if reason:
                    status, note = SKIPPED, reason
                else:
                    reason = _execute(step, verbose, stream)
                    if reason:
                        status, note = FAILED, reason
                    else:
                        status, note = OK, (step.detail() if step.detail else "")
            except Exception as error:  # a step must never end the run without its line
                status, note = FAILED, "%s: %s" % (type(error).__name__, _short(error))
        seconds = time.perf_counter() - start
        status_of[step.name] = status
        results.append((step.name, status, note, seconds))
        line = "%2d/%d  %-*s  %-7s %6.1f s" % (number, len(steps), width, step.name, status, seconds)
        print(line + ("  " + note if note else ""), file=stream, flush=True)
    return results


def poppler_missing():
    """None when Poppler's pdftotext is on PATH, else the reason."""
    exe = shutil.which("pdftotext")
    if not exe:
        return "no pdftotext on PATH (install Poppler)"
    try:
        done = subprocess.run([exe, "-v"], capture_output=True)
    except OSError as error:
        return "pdftotext cannot be started: %s" % error
    if b"poppler" not in (done.stdout + done.stderr).lower():
        return "the pdftotext on PATH is not Poppler's (the xpdf one reads another layout)"
    return None


def _read_json(path):
    with open(path, encoding="utf-8-sig") as handle:
        return json.load(handle)


def _names(folder):
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


def build_steps(data_dir, out_dir, cache_dir):
    """The steps of the demo run, in the order they must keep."""
    python = sys.executable
    pdf = os.path.join(ROOT, "pipeline", "pdf")
    text_dir = os.path.join(cache_dir, PROJECT + "_text")
    project_out = os.path.join(out_dir, PROJECT)
    items = os.path.join(project_out, "items.json")
    findings = os.path.join(project_out, "findings.json")
    evidence = os.path.join(project_out, "skeptic", "evidence.json")
    verdicts = os.path.join(project_out, "skeptic", "verdicts.json")
    pages = os.path.join(project_out, "pages")
    diff_out = os.path.join(out_dir, "diff")

    def no_data():
        if not os.path.isdir(data_dir):
            return "no folder %s (put the organizer files there)" % data_dir
        return None

    def no_file(name):
        def check():
            if no_data():
                return no_data()
            if not os.path.isfile(os.path.join(data_dir, name)):
                return "no file \"%s\" in %s" % (name, data_dir)
            return poppler_missing()
        return check

    def no_lists():
        if no_data():
            return no_data()
        if not [n for n in _names(data_dir) if n.startswith("LV_") and n.lower().endswith(".pdf")]:
            return "no LV_*.pdf in %s" % data_dir
        return poppler_missing()

    def no_gaeb(module_name, kinds):
        def check():
            if no_data():
                return no_data()
            module = __import__("pipeline.lv." + module_name, fromlist=["find_files"])
            if not module.find_files(data_dir):
                return "no %s file in %s" % (kinds, data_dir)
            return None
        return check

    def manifest_equal():
        new, committed = _read_json(os.path.join(project_out, "manifest.json")), _read_json(COMMITTED_MANIFEST)
        if new == committed:
            return None
        by_doc = dict((entry.get("doc"), entry) for entry in committed)
        differing = sorted(str(entry.get("doc")) for entry in new if by_doc.get(entry.get("doc")) != entry)
        absent = sorted(set(by_doc) - set(entry.get("doc") for entry in new))
        return "manifest.json is not equal to %s: %d of %d lists differ (%s)%s" % (
            os.path.relpath(COMMITTED_MANIFEST, ROOT), len(differing), len(new), ", ".join(differing[:5]) or "-",
            "; not read: %s" % ", ".join(absent[:5]) if absent else "")

    def item_files():
        return sorted(glob.glob(os.path.join(glob.escape(out_dir), "*", "items.json")))

    def no_pairs():
        if no_data():
            return no_data()
        from pipeline.diff import pairs
        absent = pairs.missing_files(data_dir)
        if absent:
            return "no file \"%s\" in %s%s" % (absent[0], data_dir,
                                              " (and %d more)" % (len(absent) - 1) if len(absent) > 1 else "")
        return poppler_missing()

    def sources():
        return [(finding.get("id"), index) for finding in _read_json(findings)
                for index, _source in enumerate(finding.get("sources") or [])]

    def images_there():
        absent = [name for name in ("%s_%d.png" % pair for pair in sources())
                  if not os.path.isfile(os.path.join(pages, name))]
        if absent:
            return "%d of %d page images were not written to %s (first: %s)" % (
                len(absent), len(sources()), pages, absent[0])
        return None

    def pages_detail():
        summary = _read_json(os.path.join(project_out, "pagecheck.json")).get("summary") or {}
        return "%s of %s quotes on the stated page of the cited item, %d page images" % (
            summary.get("found_on_stated_page", "?"), summary.get("sources", "?"), len(sources()))

    def diff_detail():
        summary = _read_json(os.path.join(diff_out, "summary.json"))
        return "%d comparisons" % (len(summary.get("pairs") or []) + len(summary.get("text_pairs") or []))

    def verdicts_equal():
        if _read_json(verdicts) != _read_json(STORED_VERDICTS):
            return "the verdicts after the rule checks are not equal to %s" % os.path.relpath(STORED_VERDICTS, ROOT)
        return None

    return [
        Step(TEXT, [[python, os.path.join(pdf, "reader_79222.py"), "--extract", data_dir, text_dir]],
             missing=no_lists),
        Step(READER, [[python, os.path.join(pdf, "reader_79222.py"), text_dir, project_out, data_dir]],
             needs=[TEXT]),
        Step(MANIFEST, call=manifest_equal, needs=[READER],
             detail=lambda: "equal to the committed one, %d lists" % len(_read_json(COMMITTED_MANIFEST))),
        # The two print readers write a whole project folder; the GAEB readers
        # add their documents to a folder that is there. So the print readers
        # run first: out/AN24-0305 then holds the offer PDF and its D84 twin.
        Step(PRINT_READER, [[python, os.path.join(pdf, "reader_ausdruck.py"), os.path.join(data_dir, PRINT_PDF),
                             os.path.join(out_dir, "PROJEKT_004")]], missing=no_file(PRINT_PDF)),
        Step(OFFER_READER, [[python, os.path.join(pdf, "reader_angebot.py"), os.path.join(data_dir, OFFER_PDF),
                             os.path.join(out_dir, "AN24-0305")]], missing=no_file(OFFER_PDF)),
        Step(GAEB90, [[python, "-m", "pipeline.lv.gaeb90", data_dir, out_dir]],
             missing=no_gaeb("gaeb90", ".D83/.D84/.D86")),
        Step(GAEBXML, [[python, "-m", "pipeline.lv.gaebxml", data_dir, out_dir]],
             missing=no_gaeb("gaebxml", ".X83/.X84/.X86")),
        Step(BASE, lambda: [[python, "-m", "pipeline.base.run", path,
                             os.path.join(os.path.dirname(path), "base_findings.json")] for path in item_files()],
             missing=lambda: None if item_files() else "no items.json in %s" % out_dir,
             detail=lambda: "%d projects" % len(item_files())),
        Step(EVIDENCE, [[python, "-m", "pipeline.skeptic.evidence", STORED_FINDINGS, items, evidence,
                         "--terms", STORED_TERMS]], needs=[READER]),
        Step(RULES, [[python, "-m", "pipeline.skeptic.rules", STORED_FINDINGS, items, STORED_VERDICTS, verdicts,
                      "--text-dir", text_dir]], needs=[READER], verify=verdicts_equal,
             detail=lambda: "equal to the committed verdicts"),
        Step(MERGE, [[python, "-m", "pipeline.skeptic.merge", STORED_FINDINGS, verdicts, findings]],
             needs=[RULES]),
        Step(SEVERITY, [[python, "-m", "pipeline.common.severity", findings, items, findings]], needs=[MERGE]),
        # The page check reads the findings the screen shows and changes nothing in them; its own
        # copy with quotes_verified goes to findings.pagecheck.json (pipeline/common/README.md).
        Step(PAGES, [[python, "-m", "pipeline.common.pagecheck", findings, data_dir, project_out,
                      os.path.join(project_out, "findings.pagecheck.json"), "--items", items]],
             needs=[SEVERITY], verify=images_there, detail=pages_detail),
        # "--doc -": the written record docs/TWINS.md is a committed file and is not rewritten here.
        Step(DIFF, [[python, "-m", "pipeline.diff.pairs", "--data", data_dir, "--out", diff_out, "--doc", "-"]],
             missing=no_pairs, detail=diff_detail),
    ]


def settle_findings(results, findings_path, stream):
    """Say what out/<project>/findings.json is after the run; remove a half-done one.

    Returns True when the file was written and finished by this run.
    """
    status = dict((name, state) for name, state, _note, _seconds in results)
    chain = [name for name in FINDINGS_CHAIN if name in status]
    if chain and all(status[name] == OK for name in chain):
        return True
    if not os.path.exists(findings_path):
        return False
    if status.get(MERGE) == OK:
        os.remove(findings_path)
        print("Removed %s: a step after the merge did not end ok, so the file was not finished." % findings_path,
              file=stream)
    else:
        print("Note: %s is from an earlier run; this run did not write it." % findings_path, file=stream)
    return False


def run(data_dir, out_dir, cache_dir, stream=None, verbose=False, steps=None):
    """Run the demo pipeline. Returns the exit code."""
    stream = stream or sys.stdout
    data_dir, out_dir, cache_dir = (os.path.abspath(path) for path in (data_dir, out_dir, cache_dir))
    print("LV-Pruefstand demo run: %s -> %s (no model call, nothing leaves this machine)" % (data_dir, out_dir),
          file=stream)
    results = run_steps(steps if steps is not None else build_steps(data_dir, out_dir, cache_dir), stream, verbose)
    failed = [name for name, state, _note, _seconds in results if state == FAILED]
    skipped = [name for name, state, _note, _seconds in results if state == SKIPPED]
    done = settle_findings(results, os.path.join(out_dir, PROJECT, "findings.json"), stream)
    total = sum(seconds for _name, _state, _note, seconds in results)
    print("%d steps: %d ok, %d failed, %d skipped, %.1f s" % (
        len(results), len(results) - len(failed) - len(skipped), len(failed), len(skipped), total), file=stream)
    if failed:
        print("FAILED: %s" % ", ".join(failed), file=stream)
    if skipped:
        print("Not complete, skipped: %s" % ", ".join(skipped), file=stream)
    extra = "" if out_dir == os.path.join(ROOT, "out") else " --out \"%s\"" % out_dir
    if done:
        print("Screen:  python -m web --project %s%s   then open http://127.0.0.1:8000/#pruefen" % (PROJECT, extra),
              file=stream)
        print("Export:  python -m web.export --project %s%s" % (
            PROJECT, extra.replace("--out", "--data")), file=stream)
    else:
        print("No findings.json for %s was written. The screen then shows its sample data "
              "(yellow line \"Beispieldaten\"):  python -m web" % PROJECT, file=stream)
    if failed:
        return EXIT_FAILED
    return EXIT_INPUT_MISSING if skipped else EXIT_OK


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pipeline.run", description=__doc__.split("\n")[0])
    parser.add_argument("data_dir", nargs="?", default=os.path.join(ROOT, "data"),
                        help="folder with the organizer files (default: data/ of the repository)")
    parser.add_argument("out_dir", nargs="?", default=os.path.join(ROOT, "out"),
                        help="output folder, one subfolder per project (default: out/ of the repository)")
    parser.add_argument("--cache", default=os.path.join(ROOT, "cache"),
                        help="folder for the page texts (default: cache/ of the repository)")
    parser.add_argument("--verbose", action="store_true", help="also print what each step prints (counts, no prices)")
    args = parser.parse_args(argv)
    return run(args.data_dir, args.out_dir, args.cache, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
