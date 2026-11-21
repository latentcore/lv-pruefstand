"""Evidence for a refutation: what all lists say about the terms of a finding.

    python -m pipeline.skeptic.evidence <findings.json> <items.json> <evidence out> [--terms <terms.json>]

The findings are loaded without their `skeptic` key, so the independent pass
never sees the verdict of the finder side. `unit_price` and `total` are removed
from every item when items.json is loaded, before anything is printed or
stored. A term matches an item when it stands, without regard to case, in the
normalized text (pipeline/common/quotes.py) of the item's short text, long
text or its pre- and post-trade lines. All kinds of entries are searched:
items, headings and preliminary notes.
"""
import argparse
import json
import os
import sys

from pipeline.common import quotes

PRICE_KEYS = ("unit_price", "total")
TEXT_KEYS = ("short_text", "long_text", "pre_trade_text", "post_trade_text")
SNIPPET_RADIUS = 120


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, data):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def without_skeptic(findings):
    """Copies of the findings without the `skeptic` key."""
    return [{key: value for key, value in finding.items() if key != "skeptic"} for finding in findings]


def without_prices(items):
    """Copies of the items without `unit_price` and `total`."""
    return [{key: value for key, value in item.items() if key not in PRICE_KEYS} for item in items]


def load_findings(path):
    """findings.json as a list, the `skeptic` key removed from every finding."""
    return without_skeptic(read_json(path))


def load_items(path):
    """items.json as a list, `unit_price` and `total` removed from every item."""
    return without_prices(read_json(path))


def fold(text):
    """Normalized text (quotes.normalize) without regard to case."""
    return quotes.normalize(text).casefold()


def searchable_text(item):
    """The text of one items.json record that a term may match."""
    return "\n".join(item.get(key) or "" for key in TEXT_KEYS)


def finding_terms(finding, added=None):
    """The finding's search terms, then the added ones; no empty term, no term twice."""
    terms, seen = [], set()
    for term in list(finding.get("search_terms") or []) + list(added or []):
        key = fold(term)
        if key and key not in seen:
            seen.add(key)
            terms.append(quotes.normalize(term))
    return terms


def snippet(text, start, length, radius=SNIPPET_RADIUS):
    """The match with up to `radius` characters on each side; "..." marks a cut."""
    left = max(0, start - radius)
    right = min(len(text), start + length + radius)
    return ("..." if left > 0 else "") + text[left:right] + ("..." if right < len(text) else "")


def match_item(item, terms):
    """The terms that stand in the item, with one snippet for each; [] when none does."""
    text = quotes.normalize(searchable_text(item))
    folded = text.casefold()
    # casefold can change the length ("ß" -> "ss"); cut snippets from the folded text then
    shown = text if len(folded) == len(text) else folded
    matches = []
    for term in terms:
        position = folded.find(fold(term))
        if position >= 0:
            matches.append({"term": term, "snippet": snippet(shown, position, len(fold(term)))})
    return matches


def is_cited(finding, item):
    return any(source.get("doc") == item.get("doc") and source.get("item_no") == item.get("item_no")
               for source in finding.get("sources") or [])


def gather(finding, items, added_terms=None):
    """Every entry of every list that matches a term of the finding.

    Returns a dict with the terms used, one hit per matching entry (doc, item
    number, page, kind, short text, quantity, unit, matched terms and
    snippets, and whether the finding cites that entry), the number of hits
    per list and the lists without a hit. `items` must come from load_items
    or without_prices; price keys are dropped again here in any case.
    """
    terms = finding_terms(finding, added_terms)
    own = [quotes.normalize(t) for t in finding.get("search_terms") or []]
    hits = []
    per_list = {}
    for item in without_prices(items):
        doc = item.get("doc")
        per_list.setdefault(doc, 0)
        matches = match_item(item, terms)
        if not matches:
            continue
        per_list[doc] += 1
        hits.append({
            "doc": doc,
            "item_no": item.get("item_no"),
            "page": item.get("page"),
            "kind": item.get("kind"),
            "short_text": item.get("short_text"),
            "quantity": item.get("quantity"),
            "unit": item.get("unit"),
            "cited": is_cited(finding, item),
            "terms": [m["term"] for m in matches],
            "snippets": [m["snippet"] for m in matches],
        })
    return {
        "id": finding.get("id"),
        "terms": terms,
        "added_terms": [t for t in terms if t not in own],
        "lists_searched": sorted(per_list),
        "hits_per_list": {doc: count for doc, count in sorted(per_list.items()) if count},
        "lists_without_hit": sorted(doc for doc, count in per_list.items() if not count),
        "hits": hits,
    }


def gather_all(findings, items, added_terms=None):
    """gather() for every finding, keyed by finding id. added_terms: {finding id: [terms]}."""
    added_terms = added_terms or {}
    unknown = sorted(set(added_terms) - {f.get("id") for f in findings})
    if unknown:
        raise ValueError("added terms for unknown finding ids: %s" % ", ".join(unknown))
    return {f["id"]: gather(f, items, added_terms.get(f["id"])) for f in findings}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pipeline.skeptic.evidence",
                                     description="Gather the evidence for a refutation of each finding.")
    parser.add_argument("findings", help="findings.json (its skeptic key is not read)")
    parser.add_argument("items", help="out/<project>/items.json")
    parser.add_argument("out", help="evidence file to write (keep it out of git, e.g. under out/)")
    parser.add_argument("--terms", help="JSON object {finding id: [added terms]}")
    args = parser.parse_args(argv)

    findings = load_findings(args.findings)
    items = load_items(args.items)
    evidence = gather_all(findings, items, read_json(args.terms) if args.terms else None)
    write_json(args.out, evidence)
    lists = len({item.get("doc") for item in items})
    for finding in findings:
        entry = evidence[finding["id"]]
        print("%s: %d terms (%d added), %d hits in %d of %d lists" % (
            finding["id"], len(entry["terms"]), len(entry["added_terms"]), len(entry["hits"]),
            len(entry["hits_per_list"]), lists))
    print("%d findings, %d entries searched, written to %s" % (len(findings), len(items), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
