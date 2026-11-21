"""M3 on hand-written twins: item and price shares through pipeline/diff, and the 'threshold met' rule."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import bench_samples as samples  # noqa: E402
from bench import measure, prereg, twins  # noqa: E402


def gaeb_list(count=50, priced=True):
    return [samples.heading("01", "Abschnitt")] + [
        samples.item("01.%d" % (10 * n), "Leistung %d" % n, unit_price=3.0 if priced else None)
        for n in range(1, count + 1)]


def test_every_m3_file_has_a_reader_in_pipeline_diff():
    for _twin, pdf, gaeb in prereg.M3_PAIRS:
        assert twins._key(pdf) and twins._key(gaeb)


def test_items_in_both_and_only_in_the_pdf():
    gaeb = gaeb_list()
    pdf = [r for r in gaeb if r["item_no"] != "01.500"] + [samples.item("02.10", "Leistung im PDF allein")]
    entry = twins.counts("T1", "a.pdf", "a.D84", pdf, gaeb)
    assert (entry["items_gaeb"], entry["items_pdf"], entry["items_in_both"]) == (50, 50, 49)
    assert (entry["items_only_pdf"], entry["items_only_gaeb"], entry["items_percent_tenths"]) == (1, 1, 980)


def test_price_share_is_the_lower_of_unit_prices_and_totals():
    gaeb, pdf = gaeb_list(), gaeb_list()
    pdf[1]["total"] = pdf[1]["total"] + 1
    pdf[2]["unit_price"], pdf[3]["unit_price"] = 4.0, 4.0
    entry = twins.counts("T1", "a.pdf", "a.D84", pdf, gaeb)
    assert (entry["unit_prices_equal"], entry["unit_prices_compared"]) == (48, 50)
    assert (entry["totals_equal"], entry["totals_compared"]) == (49, 50)
    assert entry["prices_measurable"] and entry["prices_percent_tenths"] == 960
    assert samples.price_leaks(entry) == []


def test_prices_are_not_measurable_when_no_pair_holds_one_on_both_sides():
    entry = twins.counts("T2", "b.pdf", "b.X83", gaeb_list(priced=False), gaeb_list())
    assert not entry["prices_measurable"] and entry["prices_percent_tenths"] is None
    assert entry["prices_reason"] == twins.NO_PRICE_PAIR


def _m3(monkeypatch, lists):
    monkeypatch.setattr(twins, "read", lambda data, name: lists[name])
    files = dict((name, []) for _twin, pdf, gaeb in prereg.M3_PAIRS for name in (pdf, gaeb))
    return measure.m3(samples.context_with(files))


def test_m3_is_met_only_when_every_measurable_part_meets_98_percent(monkeypatch):
    (_t1, pdf1, gaeb1), (_t2, pdf2, gaeb2) = prereg.M3_PAIRS
    lists = {pdf1: gaeb_list(), gaeb1: gaeb_list(), pdf2: gaeb_list(priced=False), gaeb2: gaeb_list(priced=False)}
    entry = _m3(monkeypatch, lists)
    assert entry["met"] == prereg.YES and entry["reason"] == "prices not measurable for T2"
    assert [pair["twin"] for pair in entry["pairs"]] == ["T1", "T2"]
    lists[pdf2] = gaeb_list(count=48, priced=False)  # 48 of 50 items: 96 %
    assert _m3(monkeypatch, lists)["met"] == prereg.NO
    lists[pdf2] = gaeb_list(count=49, priced=False)  # 49 of 50 items: 98 %
    assert _m3(monkeypatch, lists)["met"] == prereg.YES
    lists[pdf1] = gaeb_list()
    lists[pdf1][1]["unit_price"] = 9.0
    lists[pdf1][2]["unit_price"] = 9.0  # 48 of 50 unit prices: 96 %
    assert _m3(monkeypatch, lists)["met"] == prereg.NO


def test_m3_without_pdftotext_is_not_measured_yet(monkeypatch):
    def fail(data, name):
        raise twins.TwinError("Poppler's pdftotext is not on PATH (needed for the PDF files)")
    monkeypatch.setattr(twins, "read", fail)
    files = dict((name, []) for _twin, pdf, gaeb in prereg.M3_PAIRS for name in (pdf, gaeb))
    entry = measure.m3(samples.context_with(files))
    assert entry["met"] == prereg.NOT_YET and "pdftotext" in entry["reason"]
