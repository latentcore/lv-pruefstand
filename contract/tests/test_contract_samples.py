"""Contract v1: every sample and the committed result files follow their schema."""
import copy
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402

from pipeline.common import contract, ids, quotes  # noqa: E402

COMMITTED_FINDINGS = os.path.join(ROOT, "pipeline", "cross", "results", "79-222", "findings.json")
COMMITTED_MANIFEST = os.path.join(ROOT, "pipeline", "pdf", "results", "79-222", "manifest.json")
REAL_ITEMS = os.path.join(ROOT, "out", "79-222", "items.json")
REAL_TEXT_DIR = os.path.join(ROOT, "cache", "79-222_text")

# The keys as MASTER_PLAN §8 writes them.
ITEM_KEYS = ["doc", "project", "trade", "format", "stage", "item_no", "kind", "section",
             "short_text", "long_text", "quantity", "unit", "unit_price", "total", "page",
             "line", "pre_trade_text", "post_trade_text"]
FINDING_KEYS = ["id", "check", "layer", "type", "severity", "handover", "sources",
                "lists_searched", "search_terms", "explanation_de", "question_de", "exposure",
                "quotes_verified", "origin", "skeptic"]
SOURCE_KEYS = ["doc", "item_no", "page", "quote"]
REVIEW_KEYS = ["status", "by", "comment", "eur_estimate", "at"]
MANIFEST_KEYS = ["file", "sha256", "format", "stage", "pages", "items", "unparsed_lines"]
KINDS = ["normal", "optional", "alternative", "lump_sum", "preliminary_note", "heading"]
LAYERS = ["single_list", "between_lists", "between_stages", "between_formats"]
FORMATS = ["pdf", "gaeb90", "gaebxml", "xlsx"]
STAGES = ["anfrage", "83", "84", "86"]


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def sample(name):
    return copy.deepcopy(contract.load_sample(name))


# -- samples -----------------------------------------------------------

@pytest.mark.parametrize("name", contract.NAMES)
def test_sample_loads_and_follows_its_schema(name):
    data = contract.load_sample(name)
    assert data, "sample %s is empty" % name
    assert contract.errors(name, data) == []


def test_schemas_require_exactly_the_keys_of_the_plan():
    items = contract.load_schema("items")["items"]
    findings = contract.load_schema("findings")["items"]
    review = contract.load_schema("reviews")["additionalProperties"]
    manifest = contract.load_schema("manifest")["items"]
    assert items["required"] == ITEM_KEYS and sorted(items["properties"]) == sorted(ITEM_KEYS)
    assert findings["required"] == FINDING_KEYS and sorted(findings["properties"]) == sorted(FINDING_KEYS)
    assert findings["properties"]["sources"]["items"]["required"] == SOURCE_KEYS
    assert findings["properties"]["exposure"]["required"] == ["quantity", "unit"]
    assert findings["properties"]["skeptic"]["required"] == ["status", "note"]
    assert review["required"] == REVIEW_KEYS and sorted(review["properties"]) == sorted(REVIEW_KEYS)
    assert manifest["required"] == MANIFEST_KEYS


def test_schemas_carry_the_value_lists_of_the_plan():
    items = contract.load_schema("items")["items"]["properties"]
    findings = contract.load_schema("findings")["items"]["properties"]
    manifest = contract.load_schema("manifest")["items"]["properties"]
    assert items["kind"]["enum"] == KINDS
    assert findings["layer"]["enum"] == LAYERS
    assert items["format"]["enum"] == FORMATS and manifest["format"]["enum"] == FORMATS
    assert items["stage"]["enum"] == STAGES and manifest["stage"]["enum"] == STAGES


def test_sample_items_show_every_kind_and_an_unknown_key():
    items = contract.load_sample("items")
    assert {i["kind"] for i in items} == set(KINDS)
    assert any("price_mode" in i for i in items)
    assert all(list(i)[:len(ITEM_KEYS)] == ITEM_KEYS for i in items)


def test_sample_findings_carry_stable_ids():
    findings = contract.load_sample("findings")
    assert [f["id"] for f in findings if not ids.has_stable_id(f)] == []
    assert all(f["id"].startswith(f["check"] + "-") for f in findings)
    assert len({f["id"] for f in findings}) == len(findings)


def test_sample_quotes_stand_in_the_sample_items():
    kept, dropped = quotes.filter_findings(contract.load_sample("findings"), contract.load_sample("items"))
    assert dropped == [] and len(kept) == 3


def test_changed_sample_quote_is_dropped_and_counted():
    findings = sample("findings")
    findings[1]["sources"][0]["quote"] = "schwimmender Estrich auf Wärmedämmung, Nenndicke 45 mm"
    kept, dropped = quotes.filter_findings(findings, contract.load_sample("items"))
    assert len(kept) == 2 and [f["id"] for f in dropped] == [findings[1]["id"]]


def test_sample_reviews_point_at_sample_findings():
    finding_ids = {f["id"] for f in contract.load_sample("findings")}
    assert set(contract.load_sample("reviews")) <= finding_ids


def test_sample_manifest_matches_the_sample_items():
    items = contract.load_sample("items")
    manifest = {m["doc"]: m for m in contract.load_sample("manifest")}
    assert {i["doc"] for i in items} <= set(manifest)
    for doc, entry in manifest.items():
        counted = sum(1 for i in items if i["doc"] == doc
                      and i["kind"] not in ("heading", "preliminary_note"))
        assert entry["items"] == counted, doc
    assert any(m["unparsed_lines"] > 0 and m["items"] == 0 for m in manifest.values())


# -- what the schemas reject -------------------------------------------

@pytest.mark.parametrize("name,keys", [("items", ITEM_KEYS), ("findings", FINDING_KEYS),
                                       ("manifest", MANIFEST_KEYS)])
def test_each_missing_key_is_reported(name, keys):
    for key in keys:
        data = sample(name)
        del data[0][key]
        assert contract.errors(name, data) == ["$[0]: key %r is missing" % key]


def test_each_missing_review_key_is_reported():
    for key in REVIEW_KEYS:
        data = sample("reviews")
        finding_id = sorted(data)[0]
        del data[finding_id][key]
        assert contract.errors("reviews", data) == ["$.%s: key %r is missing" % (finding_id, key)]


def test_each_missing_source_exposure_and_skeptic_key_is_reported():
    for part, keys in (("exposure", ["quantity", "unit"]), ("skeptic", ["status", "note"])):
        for key in keys:
            data = sample("findings")
            del data[0][part][key]
            assert len(contract.errors("findings", data)) == 1
    for key in SOURCE_KEYS:
        data = sample("findings")
        del data[0]["sources"][1][key]
        assert len(contract.errors("findings", data)) == 1


@pytest.mark.parametrize("name,key", [("items", "kind"), ("items", "format"), ("items", "stage"),
                                      ("findings", "layer"), ("manifest", "format"),
                                      ("manifest", "stage")])
def test_value_outside_the_plan_list_is_reported(name, key):
    data = sample(name)
    data[0][key] = "something_else"
    assert len(contract.errors(name, data)) == 1


def test_wrong_shapes_are_reported():
    items = sample("items")
    items[2]["quantity"] = "120,000"
    items[2]["page"] = "2"
    assert len(contract.errors("items", items)) == 2
    findings = sample("findings")
    findings[0]["id"] = "X1-3F9A2C"
    findings[0]["sources"] = []
    findings[0]["quotes_verified"] = "yes"
    assert len(contract.errors("findings", findings)) == 3
    reviews = sample("reviews")
    reviews[sorted(reviews)[0]]["eur_estimate"] = "150 EUR"
    assert len(contract.errors("reviews", reviews)) == 1
    manifest = sample("manifest")
    manifest[0]["sha256"] = "abc"
    manifest[0]["items"] = -1
    assert len(contract.errors("manifest", manifest)) == 2
    assert len(contract.errors("items", {"items": []})) == 1
    assert len(contract.errors("reviews", [])) == 1


def test_unknown_keys_are_accepted_everywhere():
    for name in ("items", "findings", "manifest"):
        data = sample(name)
        data[0]["some_future_key"] = {"a": 1}
        assert contract.errors(name, data) == []
    reviews = sample("reviews")
    reviews[sorted(reviews)[0]]["some_future_key"] = 1
    assert contract.errors("reviews", reviews) == []


# -- committed result files --------------------------------------------

def test_committed_findings_follow_the_findings_schema():
    findings = load(COMMITTED_FINDINGS)
    assert len(findings) == 24
    assert contract.errors("findings", findings) == []


def test_committed_pdf_manifest_follows_the_manifest_schema():
    manifest = load(COMMITTED_MANIFEST)
    assert len(manifest) == 27
    assert contract.errors("manifest", manifest) == []


# -- real data (out of git): runs only where it was built ---------------

@pytest.mark.skipif(not os.path.exists(REAL_ITEMS), reason="out/79-222/items.json not built")
def test_real_items_follow_the_items_schema():
    items = load(REAL_ITEMS)
    assert items
    assert contract.errors("items", items) == []
    assert any("price_mode" in i for i in items)


@pytest.mark.skipif(not (os.path.exists(REAL_ITEMS) and os.path.isdir(REAL_TEXT_DIR)),
                    reason="out/79-222/items.json or cache/79-222_text not built")
def test_committed_findings_pass_the_quote_check_on_real_data():
    pages = {}
    for file_name in sorted(os.listdir(REAL_TEXT_DIR)):
        if file_name.endswith(".txt"):
            with open(os.path.join(REAL_TEXT_DIR, file_name), encoding="utf-8") as handle:
                pages.update(quotes.pages_from_text(file_name[:-4], handle.read()))
    kept, dropped = quotes.filter_findings(load(COMMITTED_FINDINGS), load(REAL_ITEMS), pages)
    assert [f["id"] for f in dropped] == []
    assert len(kept) == 24
