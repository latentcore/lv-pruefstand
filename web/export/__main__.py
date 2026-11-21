"""python -m web.export --project <name> [--out <dir>]: write the three export files of one project."""
import argparse
import os
import sys

from web.app import DEFAULT_OUT_DIR, DEFAULT_REVIEWS_DIR, DataError, safe_name
from web.export import files, model


def write_all(data, folder):
    """Write the three files (and the PDF when a browser prints it). Returns (paths, why there is no PDF).

    When no PDF is printed, a Risikobericht.pdf of an earlier run is removed: the
    folder must not pair the new files with a report of older reviews.
    """
    os.makedirs(folder, exist_ok=True)
    report = files.risikobericht_html(data)
    contents = [("docx", files.fragenliste_docx(data)), ("xlsx", files.lv_markiert_xlsx(data)),
                ("html", report.encode("utf-8"))]
    pdf, problem = files.print_pdf(report)
    if pdf is not None:
        contents.append(("pdf", pdf))
    elif os.path.exists(os.path.join(folder, model.NAMES["pdf"])):
        os.remove(os.path.join(folder, model.NAMES["pdf"]))
    paths = []
    for kind, content in contents:
        path = os.path.join(folder, model.NAMES[kind])
        with open(path, "wb") as handle:
            handle.write(content)
        paths.append(path)
    return paths, problem


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m web.export", description=__doc__)
    parser.add_argument("--project", required=True, help="folder name in out/, for example 79-222")
    parser.add_argument("--out", default=None, help="folder for the export files (default: out/<project>/export/)")
    parser.add_argument("--data", default=DEFAULT_OUT_DIR, help="pipeline output folder to read (default: out/)")
    parser.add_argument("--reviews", default=DEFAULT_REVIEWS_DIR, help="folder of the review files (default: reviews/)")
    args = parser.parse_args(argv)
    if not safe_name(args.project):
        print("error: project name %r is not a plain folder name" % args.project, file=sys.stderr)
        return 2
    try:
        data = model.load_project(args.project, out_dir=args.data, reviews_dir=args.reviews)
    except FileNotFoundError as error:
        print("error: %s was not found" % error, file=sys.stderr)
        return 2
    except DataError as error:
        print("error: %s" % error, file=sys.stderr)
        return 2
    folder = args.out or os.path.join(args.data, args.project, "export")
    paths, problem = write_all(data, folder)
    for path in paths:
        print("written: %s" % path)
    print("confirmed findings in the files: %d of %d" % (len(data["confirmed"]), data["counts"]["findings"]))
    if not data["items_usable"]:
        print("note: items.json is missing or not readable; LV_markiert.xlsx holds no list sheet")
    if problem and files.browser() is None:
        print("note: %s; Risikobericht.pdf was not written. Open Risikobericht.html and print it to PDF." % problem)
    elif problem:
        print("error: Risikobericht.pdf was not written: %s" % problem, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
