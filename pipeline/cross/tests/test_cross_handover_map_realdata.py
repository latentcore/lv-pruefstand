"""W4 handover map on the real project 79-222. These tests run only where the
organizer data was read into out/79-222/items.json (AGENTS.md "Data and
items.json"); they are skipped elsewhere. No quote text and no price is
printed."""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from pipeline.common import quotes  # noqa: E402
from pipeline.cross import handover_map as hm  # noqa: E402

needs_items = pytest.mark.skipif(not os.path.exists(hm.ITEMS_PATH), reason="out/79-222/items.json is not built")
needs_text = pytest.mark.skipif(not (os.path.exists(hm.ITEMS_PATH) and os.path.isdir(hm.TEXT_DIR)),
                                reason="out/79-222/items.json or cache/79-222_text is not built")


@pytest.fixture(scope="module")
def items():
    with open(hm.ITEMS_PATH, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def pages():
    return hm.read_pages(hm.TEXT_DIR)


@pytest.fixture(scope="module")
def committed():
    return hm.load_map()


def where(handover, place):
    return "%s %s %s p%s" % (handover["id"], place["doc"], place["item_no"], place["page"])


@needs_items
def test_every_doc_id_of_the_map_is_a_list_of_items_json(items, committed):
    docs = set(item["doc"] for item in items)
    assert len(docs) == 27
    assert set(committed["lists_in_set"]) == docs
    for handover in committed["handovers"]:
        assert set(handover["lists"]) <= docs, handover["id"]
        assert not set(handover["lists_not_in_set"]) & docs, handover["id"]
        assert set(place["doc"] for place in handover["evidence"]) <= docs, handover["id"]
    for candidate in committed["plan_candidates"]:
        assert set(candidate["lists"]) - set(candidate["lists_not_in_set"]) <= docs


@needs_items
def test_every_evidence_place_cites_an_item_of_items_json(items, committed):
    known = set((item["doc"], item["item_no"], item["kind"]) for item in items)
    missing = [where(h, p) for h in committed["handovers"] for p in h["evidence"]
               if (p["doc"], p["item_no"], p["kind"]) not in known]
    assert missing == []


@needs_items
def test_every_evidence_quote_stands_in_its_cited_item(items, committed):
    bad = ["%s %s %s" % (ident, place["doc"], place["item_no"]) for ident, place in hm.unverified_places(committed, items)]
    assert bad == []


@needs_text
def test_every_evidence_quote_passes_the_quote_check_with_page_texts(items, pages, committed):
    assert pages
    bad = ["%s %s %s" % (ident, place["doc"], place["item_no"])
           for ident, place in hm.unverified_places(committed, items, pages)]
    assert bad == []


@needs_text
def test_every_evidence_quote_stands_on_its_stated_page(pages, committed):
    off = [where(h, p) for h in committed["handovers"] for p in h["evidence"]
           if not quotes.quote_in_text(p["quote"], pages.get((p["doc"], p["page"]), ""))]
    assert off == []


@needs_items
def test_every_stated_page_lies_between_the_start_of_its_item_and_the_next_item(items, committed):
    by_doc = {}
    for record in items:
        by_doc.setdefault(record["doc"], []).append(record)
    off = []
    for handover in committed["handovers"]:
        for place in handover["evidence"]:
            own = by_doc[place["doc"]]
            fits = False
            for index, record in enumerate(own):
                if (record["item_no"], record["kind"]) != (place["item_no"], place["kind"]):
                    continue
                last = max(record["page"], own[index + 1]["page"]) if index + 1 < len(own) else record["page"] + 1
                if record["page"] <= place["page"] <= last and quotes.quote_in_text(place["quote"], quotes.item_text(record)):
                    fits = True
            if not fits:
                off.append(where(handover, place))
    assert off == []


@needs_text
def test_the_committed_map_is_what_the_code_finds_in_the_real_data(items, pages, committed):
    built, dropped = hm.build_map(items, pages)
    assert dropped == 0
    assert hm.validate_map(built) == []
    assert json.dumps(built, sort_keys=True, ensure_ascii=False) == json.dumps(committed, sort_keys=True, ensure_ascii=False)


@needs_items
def test_building_without_page_texts_finds_the_same_places(items, committed):
    built, dropped = hm.build_map(items)
    assert dropped == 0
    for mine, theirs in zip(built["handovers"], committed["handovers"]):
        assert mine["status"] == theirs["status"], mine["id"]
        assert [(p["doc"], p["item_no"], p["term"]) for p in mine["evidence"]] == \
               [(p["doc"], p["item_no"], p["term"]) for p in theirs["evidence"]], mine["id"]
    assert hm.unverified_places(built, items) == []


@needs_items
def test_each_handover_with_evidence_has_a_place_in_each_of_its_lists(committed):
    with_evidence = [h for h in committed["handovers"] if h["status"] == hm.STATUS_EVIDENCE]
    assert 15 <= len(with_evidence) <= 20
    for handover in with_evidence:
        assert len(handover["lists"]) >= 2 and not handover["lists_not_in_set"]
        for doc in handover["lists"]:
            assert [p for p in handover["evidence"] if p["doc"] == doc], (handover["id"], doc)


@needs_items
def test_no_price_reaches_the_map_or_the_table(items, committed, capsys):
    def keys(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key
                for found in keys(child):
                    yield found
        elif isinstance(value, list):
            for child in value:
                for found in keys(child):
                    yield found
    built, _ = hm.build_map(items)
    assert not set(keys(built)) & {"unit_price", "total"}
    assert not set(keys(committed)) & {"unit_price", "total"}
    assert hm.main([]) == 0
    out = capsys.readouterr().out
    assert "unit_price" not in out and "total" not in out
