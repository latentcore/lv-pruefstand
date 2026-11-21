"""M7 on hand-written items: how each error is planted, which ones count as found, the seed."""
import copy
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))

import bench_samples as samples  # noqa: E402
from bench import prereg, seeded  # noqa: E402
from pipeline.base.run import run_all  # noqa: E402


def by_number(records, item_no):
    return next(r for r in records if r["item_no"] == item_no)


def test_types_are_the_six_of_the_record_in_its_order():
    assert [key for key, _name, _pairs in seeded.TYPES] == [
        "quantity_x10", "unit_change", "corrupted_amount", "corrupted_total", "deleted_item", "duplicated_item"]


def test_eligible_items_follow_the_rules():
    records = samples.clean_list()
    records.append(samples.item("02.70", "Leistung ohne Preis", unit_price=None, total=None))
    records.append(samples.item("02.80", "Leistung mit kleinem Betrag", quantity=1.0, unit_price=0.5))
    numbers = lambda key: [records[i]["item_no"] for i in seeded.eligible(records, key)]  # noqa: E731
    assert "02.70" not in numbers("quantity_x10") and "02.70" not in numbers("corrupted_amount")
    assert "02.80" in numbers("quantity_x10") and "02.80" not in numbers("corrupted_amount")
    assert numbers("corrupted_total") == ["01"]  # section 02 now holds an item without a total
    assert len(seeded.eligible(samples.clean_list(), "corrupted_total")) == 2
    assert numbers("deleted_item") == [r["item_no"] for r in samples.positions(records)]


def test_each_plant_changes_one_record_and_leaves_the_original_alone():
    records = samples.clean_list()
    before = copy.deepcopy(records)
    index = next(i for i, r in enumerate(records) if r["item_no"] == "01.20")
    planted = seeded.plant(records, "quantity_x10", index)
    assert by_number(planted, "01.20")["quantity"] == 120.0 and by_number(planted, "01.20")["total"] == 480.0
    planted = seeded.plant(records, "unit_change", index)
    assert by_number(planted, "01.20")["unit"] == "m"  # sorted units m, m2: the next after m2 is m
    planted = seeded.plant(records, "corrupted_amount", index)
    assert by_number(planted, "01.20")["total"] == 52.8  # 48.00 × 1.1, cut to cents
    planted = seeded.plant(records, "corrupted_total", 0)
    assert planted[0]["total"] == 509.3  # (33 + 48 + 65 + 84 + 105 + 128) × 1.1
    planted = seeded.plant(records, "deleted_item", index)
    assert len(planted) == len(records) - 1 and "01.20" not in [r["item_no"] for r in planted]
    planted = seeded.plant(records, "duplicated_item", index)
    assert [r["item_no"] for r in planted].count("01.20") == 2 and planted[index + 1] == records[index]
    assert records == before


def test_corrupted_total_is_cut_never_rounded_up():
    records = [samples.heading("01", "Abschnitt"), samples.item("01.10", "Leistung", quantity=1.0, unit_price=1.09)]
    planted = seeded.plant(records, "corrupted_total", 0)
    assert planted[0]["total"] == 1.19  # 1.09 × 1.1 = 1.199


def test_draw_uses_the_seed_and_keeps_file_order():
    records = samples.clean_list()
    plan = seeded.draw(records, per_type=3)
    generator = random.Random(prereg.SEED)
    for key, candidates, chosen in plan:
        eligible = seeded.eligible(records, key)
        assert candidates == len(eligible)
        assert chosen == sorted(generator.sample(eligible, min(3, len(eligible))))
    assert plan == seeded.draw(records, per_type=3)


def test_fewer_eligible_than_per_type_takes_all_and_shows_the_count():
    result = seeded.measure(samples.clean_list())
    totals = dict((t["type"], (t["eligible"], t["planted"])) for t in result["types"])
    assert totals["corrupted_total"] == (2, 2) and totals["deleted_item"] == (12, 12)
    assert result["planted"] == sum(t["planted"] for t in result["types"])


def test_found_and_missed_on_hand_written_items():
    result = seeded.measure(samples.findable_list())
    found = dict((t["type"], (t["found"], t["planted"], t["missed_items"])) for t in result["types"])
    assert found["quantity_x10"][:2] == (16, 16)
    assert found["corrupted_amount"][:2] == (16, 16)
    assert found["corrupted_total"][:2] == (2, 2)
    assert found["duplicated_item"][:2] == (16, 16)
    # the first and the last item of a section leave no gap between two numbers when deleted
    assert found["deleted_item"] == (12, 16, ["01.10", "01.80", "02.10", "02.80"])
    # B5 sees a changed unit only when another item has the same short text
    assert found["unit_change"][0] == 0
    assert result["found"] == sum(t["found"] for t in result["types"])


def test_unit_change_is_found_when_the_same_work_stands_twice():
    records = [samples.heading("01", "Abschnitt"),
               samples.item("01.10", "Wand streichen", unit="m2"), samples.item("01.20", "Decke streichen", unit="m"),
               samples.item("01.30", "Wand streichen", unit="m2", quantity=12.0)]
    index = next(i for i, r in enumerate(records) if r["item_no"] == "01.10")
    findings, _summary = run_all(seeded.plant(records, "unit_change", index))
    assert ("B5", "unit_differs") in seeded.fitting(findings, "unit_change", "01.10")


def test_a_finding_the_unchanged_file_already_has_does_not_count():
    records = samples.findable_list()

    def checks(items):
        findings, summary = run_all(items)
        if items == records:  # the unchanged file: every item already carries a B3 duplicate finding
            findings = findings + [{"check": "B3", "type": "duplicate_number",
                                    "sources": [{"item_no": r["item_no"]}]} for r in samples.positions(items)]
        return findings, summary

    result = seeded.measure(records, checks=checks)
    duplicated = next(t for t in result["types"] if t["type"] == "duplicated_item")
    assert duplicated["found"] == 0 and duplicated["planted"] == 16


def test_a_finding_of_another_check_does_not_count():
    hits = seeded.fitting([{"check": "B4", "type": "repeated_item", "sources": [{"item_no": "01.10"}]}],
                          "quantity_x10", "01.10")
    assert hits == set()


def test_a_gap_counts_only_when_its_two_numbers_enclose_the_deleted_one():
    gap = {"check": "B3", "type": "number_gap", "sources": [{"item_no": "01.10"}, {"item_no": "01.30"}]}
    assert seeded.fitting([gap], "deleted_item", "01.20") == {("B3", "number_gap")}
    assert seeded.fitting([gap], "deleted_item", "01.40") == set()


def test_result_holds_no_price():
    assert samples.price_leaks(seeded.measure(samples.findable_list())) == []
