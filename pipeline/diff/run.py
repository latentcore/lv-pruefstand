"""Compare two item lists (W13, checks V1 and V2).

Usage:
    python -m pipeline.diff.run <items A> <items B> <out json>
        [--mode twin|stage] [--doc-a DOC] [--doc-b DOC]
        [--text-map fields|a_all_to_b_long|b_all_to_a_long]

<items A> and <items B> are items.json files (contract v1). When a file
holds several documents, --doc-a or --doc-b names the one to take; A and B
may be the same file. mode twin: the same list in two formats. mode stage:
A is the earlier stage (tender, offer), B the later one (offer, order).

The result goes to <out json>. The command prints counts only. Neither the
file nor the output holds a unit price, a total or a price difference.
"""
import argparse
import json
import os
import sys

from pipeline.diff import compare
from pipeline.diff import text as textcmp


class DiffError(ValueError):
    """The input cannot be compared; the message says why."""


def load_items(path, doc=None):
    """The records of one document from an items.json file."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        raise DiffError("%s: %s" % (path, error))
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise DiffError("%s does not hold a list of items" % path)
    docs = sorted(set(str(item.get("doc")) for item in data))
    if doc is None:
        if len(docs) != 1:
            raise DiffError("%s holds %d documents (%s): name one with --doc-a or --doc-b"
                            % (path, len(docs), ", ".join(docs)))
        doc = docs[0]
    items = [item for item in data if str(item.get("doc")) == doc]
    if not items:
        raise DiffError("%s holds no document %r (it holds: %s)" % (path, doc, ", ".join(docs)))
    for item in items:
        if not isinstance(item.get("item_no"), str) or not isinstance(item.get("kind"), str):
            raise DiffError("%s: an item of %r has no item_no or no kind" % (path, doc))
    return items


def write_json(path, data):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
        handle.write("\n")


def summary_line(result):
    """One line of counts for the console: no text, no price."""
    matching = result["matching"]
    parts = ["%s: A %d items, B %d items; in both %d, only A %d, only B %d"
             % (result["mode"], result["a"]["items"], result["b"]["items"], matching["both"],
                len(matching["only_a"]), len(matching["only_b"]))]
    if matching["by_position"] or matching["renumbered"]:
        parts.append("by position %d, renumbered %d"
                     % (len(matching["by_position"]), len(matching["renumbered"])))
    for name, field in result["fields"].items():
        if not field["compared"]:
            parts.append("%s not compared" % name)
        elif textcmp.DIFFERS in field:
            parts.append("%s equal %d, layout %d, anonymization %d, start %d, differs %d"
                         % (name, field["equal"], field[textcmp.LAYOUT],
                            field[textcmp.ANONYMIZED_BOTH] + field[textcmp.ANONYMIZED_ONE],
                            field[textcmp.START], field[textcmp.DIFFERS]))
        else:
            parts.append("%s equal %d, not equal %d" % (name, field["equal"], field["not_equal"]))
    return "; ".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pipeline.diff.run",
                                     description="Compare two item lists: twin (V1) or stage (V2).")
    parser.add_argument("items_a", help="items.json of document A")
    parser.add_argument("items_b", help="items.json of document B")
    parser.add_argument("out", help="result file (JSON)")
    parser.add_argument("--mode", choices=("twin", "stage"), default="twin")
    parser.add_argument("--doc-a", help="document id in <items A>, when the file holds several")
    parser.add_argument("--doc-b", help="document id in <items B>, when the file holds several")
    parser.add_argument("--text-map", choices=compare.TEXT_MAPS, default="fields")
    args = parser.parse_args(argv)
    try:
        items_a = load_items(args.items_a, args.doc_a)
        items_b = load_items(args.items_b, args.doc_b)
    except DiffError as error:
        print("error: %s" % error, file=sys.stderr)
        return 2
    result = compare.compare(items_a, items_b, args.mode, args.text_map)
    write_json(args.out, result)
    print(summary_line(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
