"""Real-data tests of the W2 "done" criterion. They need the organizer files
in data/ (or in the folder named by LV_DATA_DIR) and Poppler's pdftotext; they
are skipped when one of the two is missing. Only counts and "equal / not
equal" are asserted; no amount is printed."""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PDF_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PDF_DIR))
sys.path.insert(0, PDF_DIR)
sys.path.insert(0, REPO)

import pagecheck_lists  # noqa: E402
import pdfio  # noqa: E402
import reader_79222  # noqa: E402
import reader_angebot  # noqa: E402
import reader_ausdruck  # noqa: E402
from pipeline.common import contract  # noqa: E402

DATA = os.environ.get("LV_DATA_DIR") or os.path.join(REPO, "data")
RESULTS = os.path.join(PDF_DIR, "results", "79-222")
AUSDRUCK = os.path.join(DATA, "LV-Ausdruck-[PROJEKT_004].pdf")
ANGEBOT = os.path.join(DATA, "Angebot AN24-0305.pdf")
LISTS = os.path.join(DATA, "LV_00_Roh_und_Erdauarbeiten.pdf")
POPPLER = pdfio.pdftotext_is_poppler()
NO_POPPLER = "Poppler's pdftotext is not on PATH"


def read_bytes(folder, name):
    with open(os.path.join(folder, name), "rb") as f:
        return f.read()


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def priced(records):
    return [x for x in records if x["quantity"] is not None]


class Lists79222(unittest.TestCase):
    """Two runs of the 27-list reader, and the page check of 5 lists."""

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(LISTS):
            raise unittest.SkipTest("no 79-222 lists in %s" % DATA)
        if not POPPLER:
            raise unittest.SkipTest(NO_POPPLER)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.runs = []
        for k in range(2):
            text_dir = os.path.join(cls.tmp.name, "text%d" % k)
            out_dir = os.path.join(cls.tmp.name, "out%d" % k)
            reader_79222.extract_pdfs(DATA, text_dir)
            reader_79222.run(text_dir, out_dir, DATA)
            cls.runs.append(out_dir)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_two_runs_give_the_same_items_and_manifest(self):
        for name in ("items.json", "manifest.json"):
            self.assertEqual(read_bytes(self.runs[0], name),
                             read_bytes(self.runs[1], name), name)

    def test_manifest_equals_the_committed_one(self):
        self.assertEqual(read_json(os.path.join(self.runs[0], "manifest.json")),
                         read_json(os.path.join(RESULTS, "manifest.json")))

    def test_item_count(self):
        manifest = read_json(os.path.join(self.runs[0], "manifest.json"))
        items = read_json(os.path.join(self.runs[0], "items.json"))
        self.assertEqual(len(manifest), 27)
        self.assertEqual(sum(m["items"] for m in manifest), 1131)
        self.assertEqual(len(priced(items)), 1131)

    def test_five_lists_page_by_page(self):
        results = pagecheck_lists.run(
            DATA, os.path.join(self.runs[0], "items.json"))
        self.assertEqual([x["doc"] for x in results], pagecheck_lists.DEFAULT_DOCS)
        manifest = {m["doc"]: m for m in
                    read_json(os.path.join(self.runs[0], "manifest.json"))}
        for x in results:
            m = manifest[x["doc"]]
            self.assertEqual(x["pages_checked"], m["pages"], x["doc"])
            self.assertEqual(len(x["pages"]), m["pages"], x["doc"])
            self.assertEqual(x["sha256"], m["sha256"], x["doc"])
            # every item of the reader is on its page, and the other way round
            self.assertEqual(x["items_in_reader"], m["items"], x["doc"])
            self.assertEqual(x["items_on_page"], m["items"], x["doc"])
            self.assertEqual(x["items_matched"], m["items"], x["doc"])
            self.assertEqual(x["quantity_unit_equal"], m["items"], x["doc"])
            self.assertEqual(x["differences"], 0, x["doc"])
        summary = pagecheck_lists.summarize(results)
        self.assertEqual(summary["totals"]["pages_checked"], 115)
        # the committed summary is what the check gives today
        self.assertEqual(
            summary, read_json(os.path.join(RESULTS, "pagecheck_lists_summary.json")))

    def test_continued_items_have_their_quantity_on_the_next_page(self):
        results = pagecheck_lists.run(
            DATA, os.path.join(self.runs[0], "items.json"))
        for x in results:
            for p in x["pages"]:
                for c in p["continued"]:
                    self.assertEqual(c["quantity_page"], c["page"] + 1, c)


class SingleDocument(unittest.TestCase):
    PDF = None
    READER = None
    ITEMS = PAGES = STAGE = None

    @classmethod
    def setUpClass(cls):
        if cls.PDF is None:
            raise unittest.SkipTest("base class")
        if not os.path.exists(cls.PDF):
            raise unittest.SkipTest("%s is not in %s" % (os.path.basename(cls.PDF), DATA))
        if not POPPLER:
            raise unittest.SkipTest(NO_POPPLER)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.outs = [os.path.join(cls.tmp.name, "out%d" % k) for k in range(2)]
        for out in cls.outs:
            cls.records, cls.manifest = cls.READER.run(cls.PDF, out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_item_count_equals_the_twin(self):
        self.assertEqual(len(priced(self.records)), self.ITEMS)
        self.assertEqual(self.manifest[0]["items"], self.ITEMS)

    def test_manifest_entry(self):
        self.assertEqual(len(self.manifest), 1)
        m = self.manifest[0]
        self.assertEqual((m["file"], m["format"], m["stage"], m["pages"]),
                         (os.path.basename(self.PDF), "pdf", self.STAGE, self.PAGES))
        self.assertEqual(m["sha256"], reader_79222.sha256_file(self.PDF))
        self.assertEqual(m["unparsed_lines"], 0)
        self.assertEqual(m["warnings"], [])
        self.assertEqual(contract.errors("manifest", self.manifest), [])

    def test_items_follow_the_contract(self):
        self.assertEqual(len(contract.errors("items", self.records)), 0)
        for x in self.records:
            self.assertEqual((x["format"], x["stage"]), ("pdf", self.STAGE))
            self.assertTrue(1 <= x["page"] <= self.PAGES)
        for x in priced(self.records):
            self.assertTrue(x["unit"], x["item_no"])
            self.assertTrue(x["short_text"], x["item_no"])
        numbers = [x["item_no"] for x in priced(self.records)]
        self.assertEqual(len(set(numbers)), len(numbers))

    def test_two_runs_give_the_same_files(self):
        for name in ("items.json", "manifest.json"):
            self.assertEqual(read_bytes(self.outs[0], name),
                             read_bytes(self.outs[1], name), name)


class Projekt004Print(SingleDocument):
    PDF, READER = AUSDRUCK, reader_ausdruck
    ITEMS, PAGES, STAGE = 50, 22, "83"      # 50 = the X83 twin (plan §4)

    def test_no_price_in_a_tender_print(self):
        for x in self.records:
            self.assertIsNone(x["unit_price"])
            self.assertIsNone(x["total"])

    def test_sections(self):
        self.assertEqual(
            [x["item_no"] for x in self.records if x["kind"] == "heading"
             and "." not in x["item_no"]], ["01", "02", "03", "04"])


class OfferAN240305(SingleDocument):
    PDF, READER = ANGEBOT, reader_angebot
    ITEMS, PAGES, STAGE = 274, 27, "84"     # 274 = the D84 twin (plan §4)

    def test_every_item_has_its_prices(self):
        for x in priced(self.records):
            self.assertIsNotNone(x["unit_price"], x["item_no"])
            self.assertIsNotNone(x["total"], x["item_no"])

    def test_quantity_times_unit_price_is_the_total(self):
        wrong = [x["item_no"] for x in priced(self.records)
                 if abs(round(x["quantity"] * x["unit_price"], 2) - x["total"]) > 0.011]
        self.assertEqual(len(wrong), 0)


del SingleDocument


if __name__ == "__main__":
    unittest.main()
