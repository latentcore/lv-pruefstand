import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from pipeline.common import quotes  # noqa: E402


def item(doc, item_no, short, long_text, page=1):
    return {"doc": doc, "item_no": item_no, "short_text": short, "long_text": long_text, "page": page}


def source(doc, item_no, quote, page=1):
    return {"doc": doc, "item_no": item_no, "page": page, "quote": quote}


def finding(*sources):
    return {"id": "X1-000000", "check": "X1", "sources": list(sources), "quotes_verified": False}


# -- normalize ---------------------------------------------------------

def test_nfkc_folds_ligature_superscript_and_no_break_space():
    assert quotes.normalize("Proﬁl 20\u00a0m²") == "Profil 20 m2"


def test_whitespace_runs_collapse_and_ends_are_stripped():
    assert quotes.normalize("  Estrich \t auf\n\n  Dämmung \r\n") == "Estrich auf Dämmung"


def test_soft_hyphen_is_removed():
    assert quotes.normalize("Wär\u00adme\u00addäm\u00admung") == "Wärmedämmung"


def test_soft_hyphen_at_line_end_joins_the_word():
    assert quotes.normalize("Wärme\u00ad\n   dämmung") == "Wärmedämmung"


def test_line_end_hyphen_joins_a_split_word():
    assert quotes.normalize("auf Wärme-\ndämmung verlegen") == "auf Wärmedämmung verlegen"
    assert quotes.normalize("auf Wärme-  \r\n     dämmung verlegen") == "auf Wärmedämmung verlegen"


def test_line_end_rule_is_plain_and_does_not_look_at_the_words():
    assert quotes.normalize("Estrich-\nDämmung") == "EstrichDämmung"
    assert quotes.normalize("Ein-\nund Ausbau") == "Einund Ausbau"
    assert quotes.normalize("nach DIN-\n18560") == "nach DIN18560"


def test_quote_with_the_line_break_or_in_normalized_form_is_found():
    source_text = "z. B. Ein-\n        und Ausbau der Leisten"
    assert quotes.quote_in_text("Ein-\nund Ausbau", source_text)
    assert quotes.quote_in_text("Einund Ausbau der Leisten", source_text)
    assert not quotes.quote_in_text("Ein- und Ausbau", source_text)


def test_hyphen_inside_a_line_and_list_dash_are_untouched():
    assert quotes.normalize("CT-C25-F4") == "CT-C25-F4"
    assert quotes.normalize("Leistung -\nwie beschrieben") == "Leistung - wie beschrieben"


def test_none_and_empty_give_empty_string():
    assert quotes.normalize(None) == ""
    assert quotes.normalize("") == ""


def test_normalize_is_idempotent():
    text = "Proﬁl-\nleiste  aus\u00a0Alu\u00adminium, 2\u00a0m²"
    once = quotes.normalize(text)
    assert quotes.normalize(once) == once


# -- quote check -------------------------------------------------------

def test_quote_is_found_across_a_line_break_and_a_split_word():
    text = "Zementestrich auf Wärme-\ndämmung,\n  Nenndicke 65 mm"
    assert quotes.quote_in_text("auf Wärmedämmung, Nenndicke 65 mm", text)


def test_quote_check_is_exact_and_case_sensitive():
    text = "Nenndicke 65 mm"
    assert not quotes.quote_in_text("Nenndicke 56 mm", text)
    assert not quotes.quote_in_text("nenndicke 65 mm", text)


def test_empty_quote_is_never_found():
    assert not quotes.quote_in_text("", "Text")
    assert not quotes.quote_in_text("  \n ", "Text")
    assert not quotes.quote_in_text(None, "Text")


def test_source_is_checked_against_the_cited_item_only():
    items = [item("LV_91", "1.10", "Estrich", "Nenndicke 65 mm"),
             item("LV_91", "1.20", "Zulage", "Schnellestrich"),
             item("LV_92", "1.10", "Belag", "Linoleum")]
    assert quotes.source_verified(source("LV_91", "1.10", "Nenndicke 65 mm"), items)
    assert quotes.source_verified(source("LV_91", "1.10", "Estrich Nenndicke"), items)
    assert not quotes.source_verified(source("LV_91", "1.20", "Nenndicke 65 mm"), items)
    assert not quotes.source_verified(source("LV_92", "1.10", "Nenndicke 65 mm"), items)
    assert not quotes.source_verified(source("LV_99", "1.10", "Nenndicke 65 mm"), items)


def test_records_that_share_an_item_no_are_all_tried():
    items = [item("LV_91", "1", "Estricharbeiten", ""),
             item("LV_91", "1", "Vorbemerkung", "Randdämmstreifen liefert der AN Estrich.")]
    assert quotes.source_verified(source("LV_91", "1", "liefert der AN Estrich"), items)


def test_page_text_is_the_second_place_to_look():
    items = [item("LV_91", "1.10", "Estrich", "Nenndicke 65 mm", page=2)]
    pages = {("LV_91", 2): "1.10.   Estrich\n   Nenndicke 65 mm\n            120,000 m2    ........"}
    src = source("LV_91", "1.10", "Nenndicke 65 mm 120,000 m2", page=2)
    assert not quotes.source_verified(src, items)
    assert quotes.source_verified(src, items, pages)
    assert not quotes.source_verified(dict(src, page=3), items, pages)


def test_pages_from_text_splits_at_page_markers():
    text = "ignored\n=== PAGE 1 ===\nerste Seite\n=== PAGE 2 ===\nzweite\nSeite\n"
    pages = quotes.pages_from_text("LV_91", text)
    assert sorted(pages) == [("LV_91", 1), ("LV_91", 2)]
    assert pages[("LV_91", 1)] == "erste Seite"
    assert quotes.quote_in_text("zweite Seite", pages[("LV_91", 2)])


def test_finding_needs_every_quote_and_at_least_one_source():
    items = [item("LV_91", "1.10", "Estrich", "Nenndicke 65 mm"),
             item("LV_92", "2.20", "Belag", "Estrich 50 mm")]
    good = finding(source("LV_91", "1.10", "Nenndicke 65 mm"), source("LV_92", "2.20", "Estrich 50 mm"))
    one_bad = finding(source("LV_91", "1.10", "Nenndicke 65 mm"), source("LV_92", "2.20", "Estrich 55 mm"))
    assert quotes.finding_verified(good, items)
    assert not quotes.finding_verified(one_bad, items)
    assert not quotes.finding_verified(finding(), items)


def test_filter_findings_drops_and_counts_without_changing_the_input():
    items = [item("LV_91", "1.10", "Estrich", "Nenndicke 65 mm")]
    good = finding(source("LV_91", "1.10", "Nenndicke 65 mm"))
    bad = finding(source("LV_91", "1.10", "Nenndicke 80 mm"))
    kept, dropped = quotes.filter_findings([good, bad, good], items)
    assert len(kept) == 2 and len(dropped) == 1
    assert all(f["quotes_verified"] is True for f in kept)
    assert dropped[0] is bad
    assert good["quotes_verified"] is False
