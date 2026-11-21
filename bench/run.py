"""Run the measurement bench (W14, MASTER_PLAN §11, docs/PREREG.md).

    python -m bench.run [--data data] [--out out] [--reviews reviews]
    python -m bench.run --table

The first form measures M1 to M9, writes bench/results/bench.json (in git:
counts, percentages, seconds, file names and item numbers; never a price or
an amount), writes out/79-222/bench.json (the German lines of the report,
made from the same JSON) and prints the table. The second form prints the
table from the committed JSON without measuring.
"""
import argparse
import datetime
import json
import os
import sys

from bench import prereg, table

RESULTS_PATH = os.path.join(prereg.REPO_ROOT, "bench", "results", "bench.json")
REPORT_PROJECT = "79-222"


def now_stamp():
    """Munich time to the minute; the clock of the machine when it has no time zone data."""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:
        now = datetime.datetime.now()
    return now.strftime("%Y-%m-%dT%H:%M")


def read_json(path):
    with open(path, encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path, data):
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
        handle.write("\n")


def measure(data="data", reviews="reviews", findings=None, now=None):
    """Measure M1 to M9. Returns the content of bench.json."""
    from bench import measure as measurements  # the readers are needed only for a measured run
    ctx = measurements.Context(data=data, reviews=reviews, findings=findings)
    return {
        "bench": "LV-Prüfstand, M1 to M9 (MASTER_PLAN §11)",
        "prereg": "docs/PREREG.md",
        "measured_at": now or now_stamp(),
        "measurements": measurements.run(ctx),
    }


def write_report_lines(data, out="out", project=REPORT_PROJECT):
    """out/<project>/bench.json for the report: the German lines of the same JSON."""
    path = os.path.join(out, project, "bench.json")
    write_json(path, {"lines": table.lines_de(data)})
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m bench.run", description=__doc__.split("\n")[0])
    parser.add_argument("--data", default="data", help="folder with the organizer data (default: data)")
    parser.add_argument("--out", default="out", help="output folder of the pipeline (default: out)")
    parser.add_argument("--reviews", default="reviews", help="folder with reviews/<project>.json (default: reviews)")
    parser.add_argument("--results", default=RESULTS_PATH, help="the bench.json to write or to print")
    parser.add_argument("--table", action="store_true", help="print the table from the JSON, measure nothing")
    args = parser.parse_args(argv)
    if args.table:
        try:
            data = read_json(args.results)
        except (OSError, ValueError) as error:
            print("cannot read %s: %s" % (args.results, error), file=sys.stderr)
            return 2
    else:
        write_json(args.results, measure(args.data, args.reviews))
        data = read_json(args.results)  # the table comes from the file, not from memory
        write_report_lines(data, args.out)
    print(table.text(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
