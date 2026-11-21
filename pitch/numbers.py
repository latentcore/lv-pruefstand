"""Every number of the deck and the pitch texts, with its source (W10, plan K12).

    python -m pitch.numbers                 table: key, value, status, recomputed value
    python -m pitch.numbers <key>           recompute one number from its source and print it
    python -m pitch.numbers --fill-expert   write the expert numbers from reviews/<project>.json

pitch/numbers.json holds, per number, its value, its source (file path and
key, or the command) and a status: "measured" or "open". MEASURES below holds
one function per number that recomputes it from that source. A number without
a measured value is shown as its bracket placeholder ([N]).

Texts and slides name a number as {{key}}; render() puts the value there. So a
number that is not in numbers.json cannot be shown, and a new value reaches
every slide and text with one build.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pipeline.common import quotes  # noqa: E402
from pipeline.skeptic import merge as skeptic_merge  # noqa: E402

PITCH_DIR = os.path.join(ROOT, "pitch")
NUMBERS_FILE = os.path.join(PITCH_DIR, "numbers.json")
OPENING_FILE = os.path.join(PITCH_DIR, "opening.json")
STATUSES = ("measured", "open")
# Folders that are not in git: a number that needs one of them is recomputed only where it exists.
LOCAL_ONLY = ("data", "cache", "out", "reviews")

EN_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve")
DE_WORDS = ("null", "eine", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn", "elf", "zwölf")
PLACEHOLDER = re.compile(r"\{\{\s*(@?[\w.]+)(?::(\w+))?\s*\}\}")


class NumberError(Exception):
    """A number cannot be read, recomputed or shown."""


def path(*parts):
    return os.path.join(ROOT, *parts)


def read_json(file_path):
    with open(file_path, encoding="utf-8") as handle:
        return json.load(handle)


def load(file_path=NUMBERS_FILE):
    data = read_json(file_path)
    if not isinstance(data, dict) or not isinstance(data.get("numbers"), dict) or not data.get("project"):
        raise NumberError("%s: needs the keys project and numbers" % file_path)
    return data


def load_opening(file_path=OPENING_FILE):
    return read_json(file_path)


def files(project):
    """The source files, by short name. Paths are relative to the repository root."""
    return {
        "manifest": "pipeline/pdf/results/%s/manifest.json" % project,
        "pagecheck": "pipeline/pdf/results/%s/pagecheck_lists_summary.json" % project,
        "findings": "pipeline/cross/results/%s/findings.json" % project,
        "verdicts": "pipeline/skeptic/results/%s/verdicts.json" % project,
        "base": "pipeline/base/run.py",
        "agents": "AGENTS.md",
        "bench": "bench/results/bench.json",
        "prereg": "docs/PREREG.md",
        "opening": "pitch/opening.json",
        "out_findings": "out/%s/findings.json" % project,
        "out_items": "out/%s/items.json" % project,
        "text_cache": "cache/%s_text" % project,
        "reviews": "reviews/%s.json" % project,
    }


def is_local_only(relative):
    return relative.split("/")[0] in LOCAL_ONLY


# ---- findings ---------------------------------------------------------------

def committed_findings(project):
    """The findings in git with the verdict of the independent counter-check merged in
    (the same merge that writes out/<project>/findings.json)."""
    names = files(project)
    return skeptic_merge.merge(read_json(path(names["findings"])), read_json(path(names["verdicts"])))


def load_findings(project):
    """out/<project>/findings.json when it is built, else the same data from the files in git."""
    built = path(files(project)["out_findings"])
    if os.path.isfile(built):
        return read_json(built)
    return committed_findings(project)


def find(findings, finding_id):
    for finding in findings:
        if finding.get("id") == finding_id:
            return finding
    raise NumberError("finding %s is not in the findings file" % finding_id)


def skeptic_status(finding):
    return (finding.get("skeptic") or {}).get("status")


def page_texts(project):
    folder = path(files(project)["text_cache"])
    pages = {}
    for name in sorted(os.listdir(folder)):
        if name.endswith(".txt"):
            with open(os.path.join(folder, name), encoding="utf-8") as handle:
                pages.update(quotes.pages_from_text(name[:-4], handle.read()))
    return pages


# ---- measures ---------------------------------------------------------------

MEASURES = {}


def measure(key, *needs):
    """Register the function that recomputes one number; needs = short names of its source files."""
    def register(function):
        MEASURES[key] = (function, needs)
        return function
    return register


@measure("lists", "manifest")
def _lists(project):
    return len(read_json(path(files(project)["manifest"])))


@measure("pages", "manifest")
def _pages(project):
    return sum(entry["pages"] for entry in read_json(path(files(project)["manifest"])))


@measure("items", "manifest")
def _items(project):
    return sum(entry["items"] for entry in read_json(path(files(project)["manifest"])))


@measure("base_checks", "base")
def _base_checks(project):
    from pipeline.base import run
    return len(run.CHECKS)


def _status_count(project, status):
    verdicts = read_json(path(files(project)["verdicts"]))
    return sum(1 for verdict in verdicts.values() if verdict.get("status") == status)


@measure("findings", "findings")
def _findings(project):
    return len(read_json(path(files(project)["findings"])))


@measure("survived", "verdicts")
def _survived(project):
    return _status_count(project, "survived")


@measure("weakened", "verdicts")
def _weakened(project):
    return _status_count(project, "weakened")


def lowered_by_rule(project):
    """Ids of the findings the agent left standing and a rule of pipeline/skeptic/rules.py weakened."""
    verdicts = read_json(path(files(project)["verdicts"]))
    return [finding_id for finding_id, verdict in verdicts.items()
            if verdict.get("status") == "weakened" and verdict.get("agent_status") != "weakened"]


@measure("weakened_agent", "verdicts")
def _weakened_agent(project):
    verdicts = read_json(path(files(project)["verdicts"]))
    return sum(1 for verdict in verdicts.values()
               if verdict.get("status") == "weakened" and verdict.get("agent_status") == "weakened")


@measure("weakened_rule", "verdicts")
def _weakened_rule(project):
    return len(lowered_by_rule(project))


@measure("quotes_found", "findings", "out_items", "text_cache")
def _quotes_found(project):
    """Quotes that pipeline/common/quotes.py finds in the cited item or on the cited page."""
    items = read_json(path(files(project)["out_items"]))
    pages = page_texts(project)
    return sum(1 for finding in read_json(path(files(project)["findings"]))
               for source in finding["sources"] if quotes.source_verified(source, items, pages))


def _pagecheck(project, key):
    return read_json(path(files(project)["pagecheck"]))["totals"][key]


# ---- the committed bench run (bench/results/bench.json, W14) ----------------

def bench_record(project, row_id):
    """One measurement of the committed bench.json by its id (M1 to M9)."""
    for entry in read_json(path(files(project)["bench"]))["measurements"]:
        if entry.get("id") == row_id:
            return entry
    raise NumberError("bench/results/bench.json holds no %s" % row_id)


def _bench_threshold(project, row_id, pattern):
    match = re.search(pattern, bench_record(project, row_id)["threshold"])
    if not match:
        raise NumberError("%s: threshold %r does not match %r" % (row_id, bench_record(project, row_id)["threshold"], pattern))
    return int(match.group(1))


def _speed_input(project):
    """The M9 input built to the item count of docs/PREREG.md (the other input is a file as it is)."""
    runs = [run for run in bench_record(project, "M9")["inputs"] if run["input"] == "built"]
    if len(runs) != 1:
        raise NumberError("M9 holds %d built inputs, not one" % len(runs))
    return runs[0]


@measure("speed_seconds", "bench")
def _speed_seconds(project):
    return _speed_input(project)["median_seconds"]


@measure("speed_items", "bench")
def _speed_items(project):
    return _speed_input(project)["items"]


@measure("speed_runs", "bench")
def _speed_runs(project):
    return bench_record(project, "M9")["runs"]


def _twin(project, twin):
    for pair in bench_record(project, "M3")["pairs"]:
        if pair["twin"] == twin:
            return pair
    raise NumberError("M3 holds no pair %s" % twin)


@measure("m3_t1_both", "bench")
def _m3_t1_both(project):
    return _twin(project, "T1")["items_in_both"]


@measure("m3_t1_gaeb", "bench")
def _m3_t1_gaeb(project):
    return _twin(project, "T1")["items_gaeb"]


@measure("m3_t1_prices_equal", "bench")
def _m3_t1_prices_equal(project):
    """Items of T1 whose unit price and total are both equal; only when every item in both was compared on both."""
    pair = _twin(project, "T1")
    compared = {pair["unit_prices_compared"], pair["totals_compared"], pair["items_in_both"]}
    if len(compared) != 1 or pair["unit_prices_equal"] != pair["totals_equal"]:
        raise NumberError("T1: unit prices and totals were not compared on the same items with the same result")
    return pair["unit_prices_equal"]


@measure("m3_t2_both", "bench")
def _m3_t2_both(project):
    return _twin(project, "T2")["items_in_both"]


@measure("m3_t2_gaeb", "bench")
def _m3_t2_gaeb(project):
    return _twin(project, "T2")["items_gaeb"]


def _seeded_type(project, key):
    for entry in bench_record(project, "M7")["types"]:
        if entry["type"] == key:
            return entry
    raise NumberError("M7 holds no type %s" % key)


@measure("m7_found", "bench")
def _m7_found(project):
    return bench_record(project, "M7")["found"]


@measure("m7_planted", "bench")
def _m7_planted(project):
    return bench_record(project, "M7")["planted"]


@measure("m7_percent", "bench")
def _m7_percent(project):
    """Found / planted in percent, cut to one decimal by the bench (percent_tenths)."""
    tenths = bench_record(project, "M7")["percent_tenths"]
    return tenths // 10 if tenths % 10 == 0 else tenths / 10


@measure("m7_target", "bench")
def _m7_target(project):
    return _bench_threshold(project, "M7", r"B ≥ (\d+) %")


@measure("m7_per_type", "bench")
def _m7_per_type(project):
    return bench_record(project, "M7")["per_type"]


@measure("m7_qty_found", "bench")
def _m7_qty_found(project):
    return _seeded_type(project, "quantity_x10")["found"]


@measure("m7_unit_found", "bench")
def _m7_unit_found(project):
    return _seeded_type(project, "unit_change")["found"]


@measure("m8_rate", "bench")
def _m8_rate(project):
    """False alarms per the item count of m8_per_items in the clean file, in hundredths as the bench gives it."""
    hundredths = bench_record(project, "M8")["clean"]["per_100_hundredths"]
    return hundredths // 100 if hundredths % 100 == 0 else hundredths / 100


@measure("m8_per_items", "prereg")
def _m8_per_items(project):
    with open(path(files(project)["prereg"]), encoding="utf-8") as handle:
        match = re.search(r"`high` plus `medium`, per (\d+) items", handle.read())
    if not match:
        raise NumberError("docs/PREREG.md no longer says per how many items M8 counts")
    return int(match.group(1))


@measure("m8_target", "bench")
def _m8_target(project):
    return _bench_threshold(project, "M8", r"≤ (\d+)")


@measure("pagecheck_lists", "pagecheck")
def _pagecheck_lists(project):
    return len(read_json(path(files(project)["pagecheck"]))["lists_checked"])


@measure("pagecheck_pages", "pagecheck")
def _pagecheck_pages(project):
    return _pagecheck(project, "pages_checked")


@measure("pagecheck_items", "pagecheck")
def _pagecheck_items(project):
    return _pagecheck(project, "items_matched")


@measure("pagecheck_differences", "pagecheck")
def _pagecheck_differences(project):
    return _pagecheck(project, "differences")


@measure("gate1_by_eye", "agents")
def _gate1_by_eye(project):
    """Findings whose pages Mert opened at Gate 1: the ids AGENTS.md names for X-01 to X-03."""
    with open(path(files(project)["agents"]), encoding="utf-8") as handle:
        match = re.search(r"human page check of X-01 to X-03 \(now ([^)]*)\)", handle.read())
    if not match:
        raise NumberError("AGENTS.md no longer names the Gate 1 findings")
    return len(re.findall(r"[A-Z]\d?-[0-9a-f]{6}", match.group(1)))


def _opening_finding(project):
    return find(committed_findings(project), load_opening()["finding_id"])


@measure("opening_lists", "opening", "findings")
def _opening_lists(project):
    return len({source["doc"] for source in _opening_finding(project)["sources"]})


@measure("opening_items", "opening", "findings")
def _opening_items(project):
    return len({(source["doc"], source["item_no"]) for source in _opening_finding(project)["sources"]})


def _opening_number(key):
    """A number read from a quote of the opening finding by the pattern opening.json gives for it."""
    def function(project):
        spec = load_opening()["numbers"][key]
        quote = _opening_finding(project)["sources"][spec["source"]]["quote"]
        match = re.search(spec["regex"], quote)
        if not match:
            raise NumberError("%s: pattern %r is not in quote %d of the opening finding" % (key, spec["regex"], spec["source"]))
        groups = set(match.groups())
        if len(groups) != 1:
            raise NumberError("%s: the pattern gives more than one value: %s" % (key, sorted(groups)))
        return int(groups.pop())
    return function


def _register_opening_numbers():
    try:
        keys = sorted(load_opening().get("numbers") or {})
    except (OSError, ValueError):
        keys = []
    for key in keys:
        MEASURES[key] = (_opening_number(key), ("opening", "findings"))


_register_opening_numbers()


def _reviews(project):
    data = read_json(path(files(project)["reviews"]))
    return {key: entry for key, entry in data.items() if isinstance(entry, dict)}


def _review_count(project, statuses):
    return sum(1 for entry in _reviews(project).values() if entry.get("status") in statuses)


@measure("expert_reviewed", "reviews")
def _expert_reviewed(project):
    return _review_count(project, ("confirmed", "rejected", "unclear"))


@measure("expert_confirmed", "reviews")
def _expert_confirmed(project):
    return _review_count(project, ("confirmed",))


@measure("expert_rejected", "reviews")
def _expert_rejected(project):
    return _review_count(project, ("rejected",))


@measure("expert_eur", "reviews", "opening")
def _expert_eur(project):
    """The expert's own estimate for the opening finding; never ours."""
    value = (_reviews(project).get(load_opening()["finding_id"]) or {}).get("eur_estimate")
    if value is None:
        raise NumberError("the review of the opening finding holds no estimate")
    return int(value) if float(value) == int(value) else value


EXPERT_KEYS = ("expert_reviewed", "expert_confirmed", "expert_rejected")


def missing_sources(key, project):
    """Source files of a number that are not on this machine (relative paths)."""
    names = files(project)
    return [names[need] for need in MEASURES[key][1] if not os.path.exists(path(names[need]))]


def recompute(key, project):
    if key not in MEASURES:
        raise NumberError("%s: no function recomputes this number" % key)
    return MEASURES[key][0](project)


# ---- showing a number ---------------------------------------------------------

def shown(key, entry, style=None):
    """The text a slide or a text shows for one number."""
    if entry.get("status") != "measured":
        return entry.get("placeholder") or "[%s]" % key
    value = entry["value"]
    if style is None:
        return str(value)
    if style == "round1":  # spoken form, said with "about"; numbers.json keeps the measured value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise NumberError("{{%s:%s}}: %r is not a number" % (key, style, value))
        return "%.1f" % value
    words = {"word": EN_WORDS, "wort": DE_WORDS}.get(style.lower())
    if words is None:
        raise NumberError("{{%s:%s}}: unknown style" % (key, style))
    if not isinstance(value, int) or not 0 <= value < len(words):
        raise NumberError("{{%s:%s}}: %r has no word form" % (key, style, value))
    word = words[value]
    return word.capitalize() if style[0].isupper() else word


def placeholders(text):
    """(name, style) of every {{...}} in a text; a name with @ is a field, not a number."""
    return [(match.group(1), match.group(2)) for match in PLACEHOLDER.finditer(text)]


def render(text, numbers, fields=None, number_html=None, field_html=None):
    """Put numbers and fields into a text. number_html and field_html turn a shown
    value into HTML (the deck); without them the text is plain (Markdown)."""
    fields = fields or {}

    def put(match):
        name, style = match.group(1), match.group(2)
        if name.startswith("@"):
            if name[1:] not in fields:
                raise NumberError("{{%s}}: no such field" % name)
            value = fields[name[1:]]
            return field_html(name[1:], value) if field_html else str(value)
        if name not in numbers:
            raise NumberError("{{%s}}: this number is not in pitch/numbers.json" % name)
        text_shown = shown(name, numbers[name], style)
        return number_html(name, numbers[name], text_shown) if number_html else text_shown

    return PLACEHOLDER.sub(put, text)


# ---- command ----------------------------------------------------------------

def table(data):
    project = data["project"]
    rows, wrong = [], []
    for key, entry in data["numbers"].items():
        if key not in MEASURES:
            again = "no function"
        elif missing_sources(key, project):
            again = "source not here: " + ", ".join(missing_sources(key, project))
        else:
            try:
                again = recompute(key, project)
            except NumberError as error:
                again = "not there: %s" % error
            if entry["status"] == "measured" and again != entry["value"]:
                wrong.append("%s: numbers.json says %r, the source gives %r" % (key, entry["value"], again))
        rows.append("%-24s %-10s %-9s %s" % (key, shown(key, entry), entry["status"], again))
    return rows, wrong


def fill_expert(data, file_path=NUMBERS_FILE):
    project = data["project"]
    if missing_sources(EXPERT_KEYS[0], project):
        raise NumberError("%s is not on this machine" % files(project)["reviews"])
    for key in EXPERT_KEYS:
        data["numbers"][key].update(value=recompute(key, project), status="measured")
    try:
        data["numbers"]["expert_eur"].update(value=recompute("expert_eur", project), status="measured")
    except NumberError:
        # No estimate (never given, or taken back): the number is open and its sentence is dropped by hand.
        data["numbers"]["expert_eur"].update(value=None, status="open")
    with open(file_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    return {key: data["numbers"][key]["value"] for key in EXPERT_KEYS}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pitch.numbers", description=__doc__.split("\n")[0])
    parser.add_argument("key", nargs="?", help="recompute this one number and print it")
    parser.add_argument("--fill-expert", action="store_true",
                        help="count reviews/<project>.json and write the three expert numbers as measured")
    args = parser.parse_args(argv)
    try:
        data = load()
        if args.fill_expert:
            print("written: %s; now run python -m pitch.build" % fill_expert(data))
            return 0
        if args.key:
            gone = missing_sources(args.key, data["project"]) if args.key in MEASURES else []
            if gone:
                raise NumberError("%s: source not on this machine: %s" % (args.key, ", ".join(gone)))
            print(recompute(args.key, data["project"]))
            return 0
        rows, wrong = table(data)
    except (NumberError, OSError, ValueError, KeyError) as error:
        print("pitch.numbers: %s" % error, file=sys.stderr)
        return 1
    print("\n".join(rows))
    for line in wrong:
        print("WRONG " + line, file=sys.stderr)
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
