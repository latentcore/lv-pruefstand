"""Matching and field comparison of two item lists (W13, checks V1 and V2).

Input: two lists of items.json records (contract v1), each for one document.
Only positions are matched (kind other than heading and preliminary_note);
headings are compared as sections.

Matching, in this order:
1. By item number: model.item_no_key() of both numbers is the same
   ("01.01.0010" and "1.1.10"). A number that stands twice in one file is
   paired in file order and named under duplicate_numbers.
2. A number that the anonymizer replaced by a placeholder cannot be matched
   by number unless both files hold the same placeholder. When such an item
   is left over and exactly one left-over item of the other file stands
   between the partners of its neighbours, the two are paired "by position".
3. Renumbered items: left-over items, and items of number pairs whose texts
   differ or where one text is only the start of the other, are paired when
   their whole text (short and long) is the same.
   A number pair is split only when one of its two items finds such a text
   partner under another number.

Fields: short_text, long_text (classes of pipeline/diff/text.py), quantity,
unit, unit_price, total. A field is compared only where both items
hold it; otherwise the pair is counted under missing_a, missing_b or
missing_both. Prices leave this module only as "equal / not equal" with the
item number; no price value and no price difference is stored.

text_map says which texts stand against each other:
    fields           short text against short text, long against long
    a_all_to_b_long  the whole text of A (short and long) against the long
                     text of B: for a print that does not show the short
                     text of the list and starts with the long text
    b_all_to_a_long  the same with A and B swapped
"""
import re

from pipeline.common.quotes import normalize
from pipeline.diff import text as textcmp
from pipeline.lv import model

TEXT_MAPS = ("fields", "a_all_to_b_long", "b_all_to_a_long")
NUMBER_TOLERANCE = 1e-6
NUMBER_FIELDS = ("quantity", "unit_price", "total")
PRICE_FIELDS = ("unit_price", "total")
PLAIN_FIELDS = ("unit",)
TITLE_LENGTH = 50
_WORD = re.compile(r"\w")


def positions(items):
    return [item for item in items if model.is_position(item)]


def headings(items):
    return [item for item in items if item.get("kind") == "heading"]


def whole_text(item):
    return normalize("\n".join([item.get("short_text") or "", item.get("long_text") or ""]))


def _text_sides(text_map):
    """[(field name in the result, text of an A item, text of a B item)]."""
    short = lambda item: normalize(item.get("short_text"))
    long_ = lambda item: normalize(item.get("long_text"))
    if text_map == "fields":
        return [("short_text", short, short), ("long_text", long_, long_)]
    if text_map == "a_all_to_b_long":
        return [("text", whole_text, long_)]
    if text_map == "b_all_to_a_long":
        return [("text", long_, whole_text)]
    raise ValueError("text_map %r is not one of %s" % (text_map, ", ".join(TEXT_MAPS)))


def _numbers_equal(a, b):
    return abs(float(a) - float(b)) <= NUMBER_TOLERANCE


def _field_value(item, field):
    value = item.get(field)
    if field in PLAIN_FIELDS:
        value = normalize(value) if isinstance(value, str) else value
        return value or None
    return value


def _by_key(items):
    table = {}
    for index, item in enumerate(items):
        table.setdefault(model.item_no_key(item["item_no"]), []).append(index)
    return table


def _text_class(item_a, item_b, sides):
    """Worst text class of a pair over the compared text fields, or None when
    no text field holds text on both sides."""
    worst = None
    for _, get_a, get_b in sides:
        a, b = get_a(item_a), get_b(item_b)
        if a and b:
            cls = textcmp.classify(a, b)
            if worst is None or textcmp.CLASSES.index(cls) > textcmp.CLASSES.index(worst):
                worst = cls
    return worst


def match(items_a, items_b, text_map="fields"):
    """Pair the positions of two lists. Returns a dict:
    pairs [(index in A, index in B, how)] with how = "number", "position" or
    "text"; only_a, only_b (indexes); duplicate_a, duplicate_b (item numbers);
    a, b (the position lists the indexes point into)."""
    a, b = positions(items_a), positions(items_b)
    sides = _text_sides(text_map)
    keys_a, keys_b = _by_key(a), _by_key(b)
    pairs = {}
    for key, indexes in keys_a.items():
        for ia, ib in zip(indexes, keys_b.get(key, [])):
            pairs[ia] = (ib, "number")
    duplicates_a = sorted(a[i[0]]["item_no"] for i in keys_a.values() if len(i) > 1)
    duplicates_b = sorted(b[i[0]]["item_no"] for i in keys_b.values() if len(i) > 1)

    def left_over():
        used_b = set(ib for ib, _ in pairs.values())
        return ([i for i in range(len(a)) if i not in pairs],
                [i for i in range(len(b)) if i not in used_b])

    # 2. placeholder numbers, by position
    free_a, free_b = left_over()
    partner_of_a = dict((ia, ib) for ia, (ib, _) in pairs.items())
    partner_of_b = dict((ib, ia) for ia, ib in partner_of_a.items())

    def window(index, partner, size, size_other):
        """Open range of the other list between the partners of the nearest
        paired neighbours of `index`."""
        low, high = -1, size_other
        for i in range(index - 1, -1, -1):
            if i in partner:
                low = partner[i]
                break
        for i in range(index + 1, size):
            if i in partner:
                high = partner[i]
                break
        return low, high

    for ia in list(free_a):
        if not textcmp.is_placeholder(a[ia]["item_no"]):
            continue
        low, high = window(ia, partner_of_a, len(a), len(b))
        inside = [ib for ib in free_b if low < ib < high]
        if len(inside) == 1:
            pairs[ia] = (inside[0], "position")
            free_b.remove(inside[0])
    free_a = [i for i in free_a if i not in pairs]
    for ib in list(free_b):
        if not textcmp.is_placeholder(b[ib]["item_no"]):
            continue
        low, high = window(ib, partner_of_b, len(b), len(a))
        inside = [ia for ia in free_a if low < ia < high]
        if len(inside) == 1:
            pairs[inside[0]] = (ib, "position")
            free_a.remove(inside[0])
            free_b.remove(ib)

    # 3. renumbered items, by whole text
    doubtful = [ia for ia, (ib, how) in pairs.items()
                if how == "number"
                and _text_class(a[ia], b[ib], sides) in (textcmp.START, textcmp.DIFFERS)]
    free_a, free_b = left_over()
    pool_a = sorted(free_a + doubtful)
    pool_b = sorted(free_b + [pairs[ia][0] for ia in doubtful])
    by_text = {}
    for ib in pool_b:
        text = whole_text(b[ib])
        if text:
            by_text.setdefault(text, []).append(ib)
    moved = []
    settled = set()
    for ia in pool_a:
        # the number partner holds the same whole text (it only stands in
        # another field): the pair stays a number pair
        own = pairs[ia][0] if ia in pairs else None
        candidates = by_text.get(whole_text(a[ia]), [])
        if own in candidates:
            candidates.remove(own)
            settled.add(ia)
    for ia in pool_a:
        candidates = by_text.get(whole_text(a[ia]), [])
        if ia not in settled and candidates:
            moved.append((ia, candidates.pop(0)))
    if moved:
        taken_b = set(ib for _, ib in moved)
        for ia in doubtful:
            if pairs[ia][0] in taken_b:
                del pairs[ia]
        for ia, ib in moved:
            pairs[ia] = (ib, "text")
    free_a, free_b = left_over()
    return {"a": a, "b": b,
            "pairs": sorted((ia, ib, how) for ia, (ib, how) in pairs.items()),
            "only_a": free_a, "only_b": free_b,
            "duplicate_a": duplicates_a, "duplicate_b": duplicates_b}


def _empty_field(text):
    field = {"compared": 0, "equal": 0, "not_equal": 0, "not_equal_items": [],
             "missing_a": 0, "missing_b": 0, "missing_both": 0}
    if text:
        for cls in textcmp.CLASSES[1:]:
            field[cls] = 0
            field[cls + "_items"] = []
    return field


def _count_missing(field, has_a, has_b):
    if has_a and has_b:
        return False
    field["missing_both" if not has_a and not has_b
          else "missing_a" if not has_a else "missing_b"] += 1
    return True


def compare_fields(matching, text_map="fields"):
    """Field by field over the pairs. Returns {field: counts and the item
    numbers (as file A writes them) of the pairs that are not equal}."""
    return _compare_fields(matching, text_map)[0]


def _compare_fields(matching, text_map):
    """compare_fields() and, per value field, the pairs (index in A, index
    in B) that are not equal."""
    a, b = matching["a"], matching["b"]
    sides = _text_sides(text_map)
    fields = {}
    for name, _, _ in sides:
        fields[name] = _empty_field(text=True)
    unequal = {}
    for name in ("quantity",) + PLAIN_FIELDS + PRICE_FIELDS:
        fields[name] = _empty_field(text=False)
        unequal[name] = []
    for ia, ib, _ in matching["pairs"]:
        item_a, item_b = a[ia], b[ib]
        number = item_a["item_no"]
        for name, get_a, get_b in sides:
            field = fields[name]
            text_a, text_b = get_a(item_a), get_b(item_b)
            if _count_missing(field, bool(text_a), bool(text_b)):
                continue
            field["compared"] += 1
            cls = textcmp.classify(text_a, text_b)
            if cls == textcmp.EQUAL:
                field["equal"] += 1
            else:
                field["not_equal"] += 1
                field["not_equal_items"].append(number)
                field[cls] += 1
                field[cls + "_items"].append(number)
        for name in ("quantity",) + PLAIN_FIELDS + PRICE_FIELDS:
            field = fields[name]
            value_a, value_b = _field_value(item_a, name), _field_value(item_b, name)
            if _count_missing(field, value_a is not None, value_b is not None):
                continue
            field["compared"] += 1
            same = (_numbers_equal(value_a, value_b) if name in NUMBER_FIELDS
                    else value_a == value_b)
            if same:
                field["equal"] += 1
            else:
                field["not_equal"] += 1
                field["not_equal_items"].append(number)
                unequal[name].append((ia, ib))
    return fields, unequal


def compare_sections(items_a, items_b):
    """Headings of both lists by number key: counts, and number and title of
    the sections that only one list has."""
    a, b = headings(items_a), headings(items_b)
    keys_a, keys_b = _by_key(a), _by_key(b)
    both = [key for key in keys_a if key in keys_b]
    titles = {"compared": 0, "equal": 0, "not_equal_items": []}
    for key in both:
        text_a = normalize(a[keys_a[key][0]].get("short_text"))
        text_b = normalize(b[keys_b[key][0]].get("short_text"))
        if text_a and text_b:
            titles["compared"] += 1
            if textcmp.classify(text_a, text_b) in textcmp.SAME:
                titles["equal"] += 1
            else:
                titles["not_equal_items"].append(a[keys_a[key][0]]["item_no"])

    def only(side, keys, other):
        return [{"item_no": side[index]["item_no"], "title": normalize(side[index].get("short_text"))}
                for key, indexes in keys.items() if key not in other for index in indexes[:1]]

    return {"a": len(a), "b": len(b), "both": len(both), "titles": titles,
            "only_a": only(a, keys_a, keys_b), "only_b": only(b, keys_b, keys_a)}


def describe(items):
    """Counts of one document: no text and no price."""
    pos = positions(items)
    first = items[0] if items else {}
    return {"doc": first.get("doc"), "format": first.get("format"), "stage": first.get("stage"),
            "items": len(pos), "sections": len(headings(items)),
            "notes": sum(1 for item in items if item.get("kind") == "preliminary_note"),
            "with_short_text": sum(1 for item in pos if normalize(item.get("short_text"))),
            "with_long_text": sum(1 for item in pos if normalize(item.get("long_text"))),
            "with_text_of_no_word": sum(1 for item in pos if whole_text(item)
                                        and not _WORD.search(whole_text(item))),
            "with_quantity": sum(1 for item in pos if item.get("quantity") is not None),
            "with_unit": sum(1 for item in pos if normalize(item.get("unit"))),
            "with_unit_price": sum(1 for item in pos if item.get("unit_price") is not None),
            "placeholder_numbers": [item["item_no"] for item in pos
                                    if textcmp.is_placeholder(item["item_no"])],
            "quantity_zero": [item["item_no"] for item in pos if item.get("quantity") == 0],
            "quantity_zero_and_total_zero": sum(1 for item in pos if item.get("quantity") == 0
                                                and item.get("total") == 0)}


def title(item):
    """Short title of an item for a report: the start of its short text."""
    return normalize(item.get("short_text"))[:TITLE_LENGTH].rstrip()


def leading_run(matching, show=5):
    """How far both lists are the same from their first item on, in file
    order. An item counts as the same when the n-th position of A is paired
    with the n-th position of B and quantity, unit and short text do not
    differ (a field that one side lacks is not compared; the short text
    classes of text.SAME, "marks" and "start" count as not different).
    Returns the length of that run, the item at which it ends, how many
    pairs had a text or a quantity to compare, and the first `show` items
    with number, title of A and the result per field."""
    a, b = matching["a"], matching["b"]
    partner = dict((ia, (ib, how)) for ia, ib, how in matching["pairs"])
    run, stopped_at, open_run = 0, None, True
    with_content = 0
    first = []
    for ia, item_a in enumerate(a):
        ib, how = partner.get(ia, (None, None))
        entry = {"a": item_a["item_no"], "b": None, "matched": how, "title": title(item_a),
                 "short_text": None, "quantity": None, "unit": None}
        same = ib == ia
        if ib is not None:
            item_b = b[ib]
            entry["b"] = item_b["item_no"]
            text_a, text_b = normalize(item_a.get("short_text")), normalize(item_b.get("short_text"))
            if text_a and text_b:
                entry["short_text"] = textcmp.classify(text_a, text_b)
                same = same and entry["short_text"] != textcmp.DIFFERS
            for name in ("quantity", "unit"):
                value_a, value_b = _field_value(item_a, name), _field_value(item_b, name)
                if value_a is not None and value_b is not None:
                    equal = (_numbers_equal(value_a, value_b) if name == "quantity"
                             else value_a == value_b)
                    entry[name] = "equal" if equal else "not equal"
                    same = same and equal
            if entry["short_text"] or entry["quantity"]:
                with_content += 1
        if open_run and same:
            run += 1
        elif open_run:
            open_run = False
            stopped_at = item_a["item_no"]
        if len(first) < show:
            first.append(entry)
    return {"same_from_start": run, "stopped_at": stopped_at,
            "pairs_with_text_or_quantity": with_content, "first": first}


def compare(items_a, items_b, mode="twin", text_map="fields"):
    """Compare two documents. mode "twin" (V1): the same list in two formats.
    mode "stage" (V2): A is the earlier stage, B the later one; the result
    then also holds "stage" with added, removed, renumbered and changed
    items. Returns a dict that can be written as JSON."""
    if mode not in ("twin", "stage"):
        raise ValueError("mode %r is not twin or stage" % mode)
    matching = match(items_a, items_b, text_map)
    a, b = matching["a"], matching["b"]
    fields, unequal = _compare_fields(matching, text_map)

    def numbered(how):
        return [{"a": a[ia]["item_no"], "b": b[ib]["item_no"]}
                for ia, ib, kind in matching["pairs"] if kind == how]

    result = {
        "mode": mode, "text_map": text_map,
        "a": describe(items_a), "b": describe(items_b),
        "matching": {
            "both": len(matching["pairs"]),
            "by_number": sum(1 for pair in matching["pairs"] if pair[2] == "number"),
            "by_position": numbered("position"),
            "renumbered": numbered("text"),
            "only_a": [a[i]["item_no"] for i in matching["only_a"]],
            "only_b": [b[i]["item_no"] for i in matching["only_b"]],
            "duplicate_numbers": {"a": matching["duplicate_a"], "b": matching["duplicate_b"]},
        },
        "fields": fields,
        "sections": compare_sections(items_a, items_b),
    }
    result["from_start"] = leading_run(matching)
    if mode == "stage":
        result["stage"] = _stage(matching, fields, unequal)
    return result


def _stage(matching, fields, unequal):
    """The stage view of a comparison: A is the earlier stage. `unequal` is
    the second result of _compare_fields()."""
    a, b = matching["a"], matching["b"]
    text_fields = [name for name in fields if name in ("short_text", "long_text", "text")]
    changed_text = []
    for name in text_fields:
        for number in fields[name]["not_equal_items"]:
            if number not in changed_text and (
                    number in fields[name]["start_items"] or number in fields[name]["differs_items"]):
                changed_text.append(number)

    def values(name):
        return [{"item_no": a[ia]["item_no"], "a": a[ia].get(name), "b": b[ib].get(name)}
                for ia, ib in unequal[name]]

    price = []
    for name in PRICE_FIELDS:
        for number in fields[name]["not_equal_items"]:
            if number not in price:
                price.append(number)
    added = matching["only_b"]
    titles_a = set(normalize(item.get("short_text")) for item in a) - {""}
    return {
        "added": [b[i]["item_no"] for i in added],
        "removed": [a[i]["item_no"] for i in matching["only_a"]],
        "renumbered": [{"a": a[ia]["item_no"], "b": b[ib]["item_no"]}
                       for ia, ib, how in matching["pairs"] if how == "text"],
        "changed": {"quantity": values("quantity"), "unit": values("unit"),
                    "text": changed_text, "price": price},
        "added_with_quantity_zero": [b[i]["item_no"] for i in added if b[i].get("quantity") == 0],
        "added_without_unit": [b[i]["item_no"] for i in added if not normalize(b[i].get("unit"))],
        "added_without_long_text": [b[i]["item_no"] for i in added
                                    if not normalize(b[i].get("long_text"))],
        "added_with_unit_price": sum(1 for i in added if b[i].get("unit_price") is not None),
        "added_with_a_title_of_a": [b[i]["item_no"] for i in added
                                    if normalize(b[i].get("short_text")) in titles_a],
        "added_sections": sorted(set(b[i].get("section") or "" for i in added)),
    }
