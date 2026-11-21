"""Rule checks of the skeptic pass, by code. They can lower a verdict, never raise it.

    python -m pipeline.skeptic.rules <findings.json> <items.json> <verdicts in> <verdicts out> [--text-dir DIR]

Three checks per finding:

1. unsupported_numbers: a number in explanation_de or question_de that stands
   neither in a quote of the finding nor in a cited item of items.json.
   The finding becomes "weakened".
2. single_quote_contradiction: a contradiction (check X2 or type
   "contradiction") with fewer than two different quotes. "weakened".
3. quotes_not_found: a quote that does not stand in the cited item or on the
   cited page (pipeline/common/quotes.py). Recorded only; dropping such a
   finding is the job of the quote check, the filter after the skeptic.

What counts as a number in rule 1
- In explanation_de and question_de: a run of digits with optional "," or "."
  groups ("35", "16,5", "0,000", "11.4.60", "0.19") that does not follow a
  letter directly. "m2", "T30" or "C35" are code words, not numbers; the "x"
  in "300x1200" is a times sign. An item number that starts with a dot
  (".48") is one token.
- The name of a list is not a number: the id after "LV" ("LV 18", "LV 14c")
  and an integer with a leading zero ("Bodenlisten 02, 06 und 07") are
  skipped when that list is in lists_searched, handover or the sources. The
  name of a list that was not searched stays a number and is reported.
- A number is supported when the same value stands in a quote, or in a cited
  item: its item number, short and long text, pre- and post-trade lines and
  quantity. There every run of digits counts, also inside a word. The number
  of lists in lists_searched is supported too ("in den 27 vorliegenden
  Listen"). Anonymization marks such as [PERSON_169] support nothing.
- Values are compared, not spellings: "35" equals "35,000" (German decimal
  comma). A token with a "." is an identifier (item or room number) and must
  match as written; so must an integer with a leading zero.
The rule only compares values. It can miss an unsupported number that
happens to stand somewhere in a quote or cited item; it never reports a
supported one.
"""
import argparse
import os
import re
import sys

from pipeline.common import quotes
from pipeline.skeptic import STATUSES
from pipeline.skeptic.evidence import load_findings, load_items, read_json, write_json

RANK = {status: rank for rank, status in enumerate(STATUSES)}

_TOKEN = r"\d+(?:[.,]\d+)*"
# an item number that starts with a dot (".48"), not inside a word or a number
_DOT_ID = r"(?<![\w.,])\.\d+(?:\.\d+)*"
_ANY_NUMBER = re.compile(_DOT_ID + "|" + _TOKEN)
# not directly after a letter or a digit, and not after a digit plus separator
_FREE_NUMBER = re.compile(_DOT_ID + r"|(?<![^\W_])(?<!\d[.,])" + _TOKEN)
_TIMES = re.compile(r"(?<=\d)[xX×](?=\d)")
_INTEGER = re.compile(r"\d+\Z")
_DECIMAL = re.compile(r"(\d+),(\d+)\Z")
_LIST_NAME = re.compile(r"\b(LVs?\s+)(\d+[a-z]?)\b")
_PLACEHOLDER = re.compile(r"\[[A-ZÄÖÜ]+_\d+\]")


def number_key(token):
    """The value of a number token as a comparable string.

    "35", "35,0" and "35,000" give "35"; "6,50" gives "6,5". A token with a
    "." ("11.4.60", ".48", "50.000") and an integer with a leading zero ("02")
    are identifiers and stay as written.
    """
    if _INTEGER.match(token):
        return token if len(token) > 1 and token[0] == "0" else str(int(token))
    decimal = _DECIMAL.match(token)
    if decimal:
        fraction = decimal.group(2).rstrip("0")
        return str(int(decimal.group(1))) + ("," + fraction if fraction else "")
    return token


def _clean(text):
    return _PLACEHOLDER.sub(" ", quotes.normalize(text))


def list_ids(finding):
    """Ids of the lists a finding may name: lists_searched, handover and the docs of its sources."""
    ids = set(finding.get("lists_searched") or []) | set(finding.get("handover") or [])
    return ids | {s.get("doc") for s in finding.get("sources") or []}


def free_numbers(text, lists=()):
    """Number tokens of a sentence, in order: digit runs that do not follow a letter.

    lists: ids such as "LV_18". The id after "LV" and an integer with a
    leading zero are left out when they name one of these lists.
    """
    def drop_list_name(match):
        return match.group(1) if "LV_" + match.group(2) in lists else match.group(0)

    text = _LIST_NAME.sub(drop_list_name, _TIMES.sub(" x ", _clean(text)))
    tokens = [match.group(0) for match in _FREE_NUMBER.finditer(text)]
    return [t for t in tokens if not (_INTEGER.match(t) and t[0] == "0" and len(t) > 1 and "LV_" + t in lists)]


def all_number_keys(text):
    """Values of every digit run of a source text, also inside words ("Ø150mm", "40x50")."""
    return {number_key(token) for token in _ANY_NUMBER.findall(_clean(text))}


def quantity_token(quantity):
    """An items.json quantity as a German number token: 35.0 -> "35", 2.5 -> "2,5"."""
    if quantity is None or isinstance(quantity, bool):
        return ""
    return ("%.6f" % quantity).rstrip("0").rstrip(".").replace(".", ",")


def cited_items(finding, items):
    """The items.json records that the sources of the finding cite (doc and item_no)."""
    cited = {(s.get("doc"), s.get("item_no")) for s in finding.get("sources") or []}
    return [item for item in items if (item.get("doc"), item.get("item_no")) in cited]


def supported_number_keys(finding, items):
    """Values that stand in a quote or in a cited item of the finding."""
    keys = set()
    for source in finding.get("sources") or []:
        for part in (source.get("quote"), source.get("item_no")):
            keys |= all_number_keys(part or "")
    for item in cited_items(finding, items):
        for name in ("item_no", "short_text", "long_text", "pre_trade_text", "post_trade_text"):
            keys |= all_number_keys(item.get(name) or "")
        keys |= all_number_keys(quantity_token(item.get("quantity")))
    if finding.get("lists_searched"):
        keys.add(str(len(finding["lists_searched"])))
    return keys


def unsupported_numbers(finding, items):
    """Numbers of explanation_de and question_de without support, as written, each once."""
    supported = supported_number_keys(finding, items)
    lists = list_ids(finding)
    found = []
    for name in ("explanation_de", "question_de"):
        for token in free_numbers(finding.get(name) or "", lists):
            if number_key(token) not in supported and token not in found:
                found.append(token)
    return found


def is_contradiction(finding):
    return finding.get("check") == "X2" or finding.get("type") == "contradiction"


def single_quote_contradiction(finding):
    """True for a contradiction that carries fewer than two different quotes."""
    if not is_contradiction(finding):
        return False
    different = {quotes.normalize(s.get("quote")) for s in finding.get("sources") or []}
    different.discard("")
    return len(different) < 2


def quotes_not_found(finding, items, pages=None):
    """The sources whose quote stands neither in the cited item nor on the cited page.

    pages: {(doc, page): page text} or None; without it only the item text is checked.
    """
    return [{"doc": s.get("doc"), "item_no": s.get("item_no"), "page": s.get("page")}
            for s in finding.get("sources") or []
            if not quotes.source_verified(s, items, pages)]


def check(finding, items, pages=None):
    """All rule checks for one finding. `lowers_to` is "weakened" or None."""
    numbers = unsupported_numbers(finding, items)
    single = single_quote_contradiction(finding)
    return {
        "unsupported_numbers": numbers,
        "single_quote_contradiction": single,
        "quotes_not_found": quotes_not_found(finding, items, pages),
        "page_text_checked": pages is not None,
        "lowers_to": "weakened" if (numbers or single) else None,
    }


def lower(status, rule_result):
    """The status after the rule checks: never better than `status`."""
    if status not in RANK:
        raise ValueError("status %r is not one of %s" % (status, ", ".join(STATUSES)))
    floor = rule_result.get("lowers_to")
    if floor is None:
        return status
    if floor not in RANK:
        raise ValueError("rule result lowers to unknown status %r" % floor)
    return status if RANK[status] >= RANK[floor] else floor


def rule_note(rule_result):
    """One German line for the review screen that says which rule fired; "" when none did."""
    parts = []
    if rule_result["unsupported_numbers"]:
        parts.append("Zahl ohne Beleg in einem Zitat oder in der zitierten Position: %s"
                     % ", ".join(rule_result["unsupported_numbers"]))
    if rule_result["single_quote_contradiction"]:
        parts.append("Widerspruch mit nur einem Zitat")
    if rule_result["quotes_not_found"]:
        parts.append("Zitat nicht gefunden: %s" % ", ".join(
            "%s %s S. %s" % (q["doc"], q["item_no"], q["page"]) for q in rule_result["quotes_not_found"]))
    return "Regelprüfung: " + "; ".join(parts) + "." if parts else ""


def apply_rules(findings, items, verdicts, pages=None):
    """The verdicts with `rules`, `rule_note` and the final `status` set by code.

    Each verdict keeps `agent_status` (the verdict before the rules; taken from
    `status` when the key is missing) and its note. status = agent_status,
    lowered where a rule says so. The input is not changed.
    """
    ids = [f.get("id") for f in findings]
    missing = [i for i in ids if i not in verdicts]
    unknown = sorted(set(verdicts) - set(ids))
    if missing or unknown:
        raise ValueError("verdicts do not fit the findings: missing %s, unknown %s" % (missing, unknown))
    result = {}
    for finding in findings:
        verdict = dict(verdicts[finding["id"]])
        agent_status = verdict.get("agent_status", verdict.get("status"))
        rule_result = check(finding, items, pages)
        verdict["agent_status"] = agent_status
        verdict["status"] = lower(agent_status, rule_result)
        verdict["rules"] = rule_result
        verdict["rule_note"] = rule_note(rule_result)
        result[finding["id"]] = verdict
    return result


def load_pages(text_dir):
    """{(doc, page): page text} from a folder of <doc>.txt files with "=== PAGE n ===" lines."""
    pages = {}
    for file_name in sorted(os.listdir(text_dir)):
        if file_name.endswith(".txt"):
            with open(os.path.join(text_dir, file_name), encoding="utf-8") as handle:
                pages.update(quotes.pages_from_text(file_name[:-4], handle.read()))
    return pages


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pipeline.skeptic.rules",
                                     description="Apply the rule checks to the verdicts of the skeptic pass.")
    parser.add_argument("findings", help="findings.json (its skeptic key is not read)")
    parser.add_argument("items", help="out/<project>/items.json")
    parser.add_argument("verdicts_in", help="verdicts keyed by finding id")
    parser.add_argument("verdicts_out", help="file to write; may be the same file")
    parser.add_argument("--text-dir", help="page texts (cache/<project>_text) for the quote check")
    args = parser.parse_args(argv)

    findings = load_findings(args.findings)
    pages = load_pages(args.text_dir) if args.text_dir else None
    try:
        result = apply_rules(findings, load_items(args.items), read_json(args.verdicts_in), pages)
    except ValueError as error:
        print("error: %s" % error, file=sys.stderr)
        return 1
    write_json(args.verdicts_out, result)
    lowered = [i for i, v in result.items() if v["status"] != v["agent_status"]]
    for finding_id in lowered:
        print("%s: %s -> %s. %s" % (finding_id, result[finding_id]["agent_status"],
                                    result[finding_id]["status"], result[finding_id]["rule_note"]))
    print("%d verdicts, %d lowered by a rule, written to %s" % (len(result), len(lowered), args.verdicts_out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
