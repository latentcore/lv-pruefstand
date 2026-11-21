"""The pitch texts: pitch/src/*.md with {{numbers}} -> pitch/*.md (W10).

    python -m pitch.texts           write PITCH_EN.md, KERNSAETZE_DE.md and QA.md
    python -m pitch.texts --check   exit 1 when one of them is not what the sources give

The sources name every number as {{key}} of pitch/numbers.json. The written
files are for reading and speaking; edit the sources, never the written files.

Speaking time of the pitch: RATE words per minute plus PAUSE seconds for each
change of slide. A number counts with the words of its English reading (397 =
"three hundred ninety-seven" = 4 words); an open number ([N]) counts as
OPEN_WORDS words. The rehearsal (PROBE.md) gives the real time.
"""
import argparse
import os
import re
import sys

from pitch import check, numbers

SRC_DIR = os.path.join(numbers.PITCH_DIR, "src")
RATE = 140          # words per minute: slow enough for a room that listens in its second language
PAUSE = 2           # seconds for each change of slide
LIMIT = 180         # seconds: the final pitch is 3 minutes (submission-guidelines/README.md)
OPEN_WORDS = 2
NOTES_MARK = check.NOTES_MARK
GENERATED = "<!-- Written by `python -m pitch.build` from %s and pitch/numbers.json. Edit those, not this file. -->"
PLAIN = (("kernsaetze_de.md", "KERNSAETZE_DE.md"), ("qa.md", "QA.md"))
PITCH = ("pitch_en.md", "PITCH_EN.md")
_OPEN = re.compile(r"\[[^\]\s]{1,3}\]")
_NUMBER = re.compile(r"\d+")
_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?")


def read_source(name, expert=True):
    """A source of pitch/src/ in one variant (see variant())."""
    with open(os.path.join(SRC_DIR, name), encoding="utf-8") as handle:
        return variant(handle.read(), expert)


_VARIANT = re.compile(r"<!--((?:no)?expert)-->(.*?)<!--/\1-->", re.DOTALL)


def variant(text, expert=True):
    """The text of one variant: <!--expert-->...<!--/expert--> is kept only with the expert
    session, <!--noexpert-->...<!--/noexpert--> only without it (python -m pitch.build --no-expert)."""
    return _VARIANT.sub(lambda match: match.group(2) if (match.group(1) == "expert") == expert else "", text)


def spoken_number_words(value):
    """How many words the English reading of a whole number has (625 -> 4, 27 -> 2, 0 -> 1)."""
    value = int(value)
    if value < 0:
        return 1 + spoken_number_words(-value)
    if value < 21:
        return 1
    if value < 100:
        return 1 if value % 10 == 0 else 2
    if value < 1000:
        return 2 + (spoken_number_words(value % 100) if value % 100 else 0)
    count = 0
    for unit in (1000000000, 1000000, 1000):
        if value >= unit:
            count += spoken_number_words(value // unit) + 1
            value %= unit
    return count + (spoken_number_words(value) if value else 0)


def count_words(text):
    """Spoken words of a text: words, numbers by their reading, open numbers as OPEN_WORDS."""
    text, opened = _OPEN.subn(" ", text)
    count = opened * OPEN_WORDS
    for token in _NUMBER.findall(text):
        count += spoken_number_words(token)
    return count + len(_WORD.findall(_NUMBER.sub(" ", text)))


def clock(seconds):
    seconds = int(round(seconds))
    return "%d:%02d" % (seconds // 60, seconds % 60)


def split_pitch(source):
    """(head, [(title, body)], notes) of the pitch source: parts start with '## '."""
    body, _, notes = source.partition(NOTES_MARK)
    pieces = re.split(r"^## +(.+)$", body, flags=re.MULTILINE)
    parts = [(pieces[index].strip(), pieces[index + 1].strip()) for index in range(1, len(pieces), 2)]
    return pieces[0].strip(), parts, notes.strip()


def timing(parts):
    """Per part: words and seconds; the total holds the pauses between the parts."""
    rows = [{"title": title, "words": count_words(body), "seconds": count_words(body) * 60.0 / RATE}
            for title, body in parts]
    words = sum(row["words"] for row in rows)
    pauses = PAUSE * max(len(rows) - 1, 0)
    return rows, {"words": words, "pauses": pauses, "seconds": words * 60.0 / RATE + pauses}


def pitch_total(data, expert=True):
    """Words and seconds of the pitch text of one variant."""
    return timing(split_pitch(numbers.render(read_source(PITCH[0], expert), data["numbers"]))[1])[1]


def render_pitch(data, expert=True):
    head, parts, notes = split_pitch(numbers.render(read_source(PITCH[0], expert), data["numbers"]))
    rows, total = timing(parts)
    rule = (" A number counts with the words of its reading; an open number such as [N] counts as %d words." % OPEN_WORDS
            if expert else " A number counts with the words of its reading.")
    lines = [GENERATED % ("pitch/src/" + PITCH[0]), "", head, "",
             "Speaking time, estimated: **%s of %s** (%d words at %d words per minute, plus %d seconds for each of the %d "
             "changes of slide).%s"
             % (clock(total["seconds"]), clock(LIMIT), total["words"], RATE, PAUSE, max(len(rows) - 1, 0), rule), ""]
    for (title, body), row in zip(parts, rows):
        lines += ["## %s" % title, "", "*%d words, %s*" % (row["words"], clock(row["seconds"])), "", body, ""]
    lines += ["## Time per part", "", "| Part | Words | Time | Running total with pauses |", "|---|---|---|---|"]
    running = 0.0
    for index, row in enumerate(rows):
        running += row["seconds"] + (PAUSE if index else 0)
        lines.append("| %s | %d | %s | %s |" % (row["title"], row["words"], clock(row["seconds"]), clock(running)))
    lines += ["| **Total** | **%d** | | **%s** |" % (total["words"], clock(total["seconds"])), ""]
    if notes:
        lines += [notes, ""]
    return "\n".join(lines)


def render_plain(source_name, data, expert=True):
    return "%s\n\n%s" % (GENERATED % ("pitch/src/" + source_name),
                         numbers.render(read_source(source_name, expert), data["numbers"]).strip() + "\n")


def render_all(data, expert=True):
    """{file name in pitch/: text}."""
    out = {PITCH[1]: render_pitch(data, expert)}
    for source_name, target in PLAIN:
        out[target] = render_plain(source_name, data, expert)
    return out


def stale(data, folder=numbers.PITCH_DIR):
    """Names of the written files that differ from what the sources give now."""
    names = []
    for name, text in render_all(data).items():
        target = os.path.join(folder, name)
        try:
            with open(target, encoding="utf-8") as handle:
                same = handle.read() == text
        except OSError:
            same = False
        if not same:
            names.append(name)
    return names


def write(data, folder=numbers.PITCH_DIR, expert=True):
    rendered = render_all(data, expert)
    for name, text in rendered.items():
        with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
            handle.write(text)
    return sorted(rendered)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pitch.texts", description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 when a written file is not current")
    args = parser.parse_args(argv)
    try:
        data = numbers.load()
        if args.check:
            names = stale(data)
            for name in names:
                print("pitch/%s is not current: run python -m pitch.texts" % name, file=sys.stderr)
            return 1 if names else 0
        names = write(data)
        _, total = timing(split_pitch(numbers.render(read_source(PITCH[0]), data["numbers"]))[1])
    except (numbers.NumberError, OSError, ValueError) as error:
        print("pitch.texts: %s" % error, file=sys.stderr)
        return 1
    print("written: %s" % ", ".join("pitch/" + name for name in names))
    print("pitch text: %d words, %s of %s" % (total["words"], clock(total["seconds"]), clock(LIMIT)))
    if total["seconds"] > LIMIT:
        print("pitch.texts: the pitch text is longer than %s: shorten pitch/src/%s" % (clock(LIMIT), PITCH[0]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
