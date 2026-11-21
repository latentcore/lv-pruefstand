"""Rewrite the bench table of the root README.md from bench/results/bench.json.

    python -m bench.readme [--check]

Only the lines between the two markers change. When the README has no
markers yet, they are added at its end. --check writes nothing and returns 1
when the table of the README differs from the JSON.
"""
import argparse
import os
import sys

from bench import prereg, run, table

README_PATH = os.path.join(prereg.REPO_ROOT, "README.md")
START, END = "<!-- bench:start -->", "<!-- bench:end -->"


class MarkerError(ValueError):
    """The README does not hold exactly one start marker followed by one end marker."""


def block(data):
    """The two markers with the table between them."""
    return "%s\n%s\n%s" % (START, table.markdown(data), END)


def current_table(text):
    """The text between the markers, or None when the README has no markers."""
    starts, ends = text.count(START), text.count(END)
    if not starts and not ends:
        return None
    if starts != 1 or ends != 1 or text.index(START) > text.index(END):
        raise MarkerError("README needs exactly one %s followed by one %s" % (START, END))
    return text[text.index(START) + len(START):text.index(END)].strip("\n")


def rewrite(text, data):
    """The README text with the table replaced; everything outside the markers stays as it is."""
    if current_table(text) is None:
        separator = "" if not text or text.endswith("\n\n") else "\n" if text.endswith("\n") else "\n\n"
        return text + separator + block(data) + "\n"
    return text[:text.index(START)] + block(data) + text[text.index(END) + len(END):]


def in_sync(text, data):
    return current_table(text) == table.markdown(data)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m bench.readme", description=__doc__.split("\n")[0])
    parser.add_argument("--readme", default=README_PATH)
    parser.add_argument("--results", default=run.RESULTS_PATH)
    parser.add_argument("--check", action="store_true", help="write nothing; 1 when README and JSON differ")
    args = parser.parse_args(argv)
    try:
        data = run.read_json(args.results)
        with open(args.readme, encoding="utf-8", newline="") as handle:
            raw = handle.read()
        # A checkout on Windows (core.autocrlf) has CRLF line ends; compare and rewrite on LF, keep the file's ends.
        crlf = "\r\n" in raw
        text = raw.replace("\r\n", "\n")
        if args.check:
            if in_sync(text, data):
                return 0
            print("the bench table of %s differs from %s" % (args.readme, args.results), file=sys.stderr)
            return 1
        changed = rewrite(text, data)
    except (OSError, ValueError) as error:
        print("cannot rewrite the table: %s" % error, file=sys.stderr)
        return 2
    if changed != text:
        with open(args.readme, "w", encoding="utf-8", newline="") as handle:
            handle.write(changed.replace("\n", "\r\n") if crlf else changed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
