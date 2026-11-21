"""All twelve base checks on every out/*/items.json that exists. Skipped when out/ holds none.

Build out/79-222/items.json with the two reader commands of AGENTS.md ("Data and
items.json"). A project folder that another reader adds to out/ is picked up
without a change here. The count per check is printed; see it with
`python -m pytest -q -rP pipeline/base/tests/test_base_real_data.py`.
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pytest  # noqa: E402

import base_samples as s  # noqa: E402
from pipeline.base import core, run  # noqa: E402
from pipeline.common import contract, ids, quotes  # noqa: E402

ITEM_FILES = sorted(glob.glob(os.path.join(s.ROOT, "out", "*", "items.json")))
PROJECTS = [os.path.basename(os.path.dirname(path)) for path in ITEM_FILES]
CHECK_NAMES = ["B%d" % n for n in range(1, 13)]
_NUMBER_TOKEN = re.compile(r"[\w.]*\d[\w.]*")

pytestmark = pytest.mark.skipif(not ITEM_FILES, reason="no out/*/items.json built")


@pytest.fixture(scope="module", params=ITEM_FILES or [None], ids=PROJECTS or ["no-project"])
def project(request):
    with open(request.param, encoding="utf-8") as handle:
        items = json.load(handle)
    findings, summary = run.run_all(items)
    return {"name": os.path.basename(os.path.dirname(request.param)), "items": items,
            "findings": findings, "summary": summary}


def test_all_twelve_checks_run_and_report_their_count(project):
    summary = project["summary"]
    assert [entry["check"] for entry in summary] == CHECK_NAMES
    documents = len(core.split_docs(project["items"]))
    assert documents > 0 and all(entry["documents"] == documents for entry in summary)
    assert sum(entry["findings"] for entry in summary) == len(project["findings"])
    print("base checks on out/%s/items.json: %d documents, %d records, %d findings"
          % (project["name"], documents, len(project["items"]), len(project["findings"])))
    for entry in summary:
        print(run.summary_line(entry))


def test_the_result_is_schema_valid(project):
    contract.check("findings", project["findings"])
    for finding in project["findings"]:
        assert finding["check"] in CHECK_NAMES and finding["layer"] == "single_list"
        assert finding["quotes_verified"] is True


def test_every_quote_passes_the_quote_check_and_none_was_dropped(project):
    assert all(entry["dropped"] == 0 for entry in project["summary"]), project["summary"]
    by_key = {}
    for item in project["items"]:
        by_key.setdefault((item.get("doc"), item.get("item_no")), []).append(item)
    for finding in project["findings"]:
        for source in finding["sources"]:
            cited = by_key.get((source["doc"], source["item_no"]), [])
            assert quotes.source_verified(source, cited), (finding["id"], source)


def test_ids_are_stable_and_unique(project):
    assert all(entry["same_id"] == 0 for entry in project["summary"]), project["summary"]
    seen = [finding["id"] for finding in project["findings"]]
    assert len(set(seen)) == len(seen)
    assert all(ids.has_stable_id(finding) for finding in project["findings"])


def test_price_findings_name_no_amount(project):
    """B1, B2 and B7 texts hold no number except item numbers of the document and "Faktor 10"."""
    numbers = {}
    for item in project["items"]:
        if isinstance(item, dict) and isinstance(item.get("item_no"), str):
            numbers.setdefault(item.get("doc"), set()).add(item["item_no"])
    for finding in project["findings"]:
        if finding["check"] not in ("B1", "B2", "B7"):
            continue
        allowed = numbers[finding["sources"][0]["doc"]] | {"10"}
        text = finding["explanation_de"] + " " + finding["question_de"]
        for token in _NUMBER_TOKEN.findall(text):
            assert token in allowed or token.rstrip(".") in allowed, (finding["id"], token)


# Items of 79-222 that name a product after a marker word and have no "gleichwertig",
# read from the page text: the name follows "z.B." or is an anonymisation token.
# LV_13 "2.7": the reader numbers the items below it "2.7..n".
B12_MARKED_79_222 = (("LV_12", "6.1.70"), ("LV_12", "6.2.50"), ("LV_12", "6.3.52"), ("LV_08", "13.2.5.0"),
                     ("LV_08", "13.3.30"), ("LV_08", "13.3.35"), ("LV_08", "13.3.36"), ("LV_08", "13.3.37"),
                     ("LV_13", "2.7"))


def test_b12_reports_the_products_named_after_an_example_mark_or_as_a_token(project):
    if project["name"] != "79-222":
        pytest.skip("item list of project 79-222")
    reported = {(f["sources"][0]["doc"], f["sources"][0]["item_no"])
                for f in project["findings"] if f["check"] == "B12"}
    for doc, number in B12_MARKED_79_222:
        assert any(d == doc and (n == number or n.startswith(number + ".")) for d, n in reported), (doc, number)
    print("B12 on out/79-222: %d findings, the %d marked items among them" % (len(reported), len(B12_MARKED_79_222)))


def test_a_check_that_needs_prices_is_not_applicable_to_a_list_without_prices(project):
    by_check = {entry["check"]: entry for entry in project["summary"]}
    for doc in core.split_docs(project["items"]):
        if all(core.number(r, "unit_price") is None and core.number(r, "total") is None for r in doc.records):
            for check in ("B1", "B2", "B7"):
                assert doc.name in by_check[check]["not_applicable"], (check, doc.name)
            assert not any(f["check"] in ("B1", "B2", "B7") and f["sources"][0]["doc"] == doc.name
                           for f in project["findings"])
