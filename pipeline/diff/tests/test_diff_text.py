import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import pytest  # noqa: E402

from pipeline.diff import text as t  # noqa: E402


@pytest.mark.parametrize("word", ["[PERSON_118]", "[PERSON_0000118]", "PERSON_097", "TELEFON_084",
                                  "PER000115", "TEL00009", "PER89", "P060", "###", "[FIRMA_059]"])
def test_placeholder_forms_are_recognized(word):
    assert t.is_placeholder(word)
    assert t.has_placeholder("vor %s nach" % word)


@pytest.mark.parametrize("word", ["01.01.0010", "PE100", "P123", "DN100", "Person", "##", "8.1.3",
                                  "PERSONAL_1x", "[1]"])
def test_plain_words_are_not_placeholders(word):
    assert not t.is_placeholder(word)


def test_equal_after_normalization():
    assert t.classify("Rohr  DN 100\nliefern", "Rohr DN 100 liefern") == t.EQUAL
    assert t.classify("Ein-\nund Ausbau", "Einund Ausbau") == t.EQUAL
    assert t.classify("Ma\u00dfe ½ m", "Maße 1⁄2 m") == t.EQUAL


def test_layout_only():
    assert t.classify("Rohrleitungs- und Bau", "Rohrleitungsund Bau") == t.LAYOUT
    assert t.classify("Zu-/Abluft", "Zu /Abluft") == t.LAYOUT


def test_placeholders_written_differently_on_both_sides():
    assert t.classify("gemäß [PERSON_128] liefern", "gemäß [PERSON_00000128] liefern") == t.ANONYMIZED_BOTH
    assert t.classify("aus [PERSON_110] bauen", "aus PER00110 bauen") == t.ANONYMIZED_BOTH
    assert t.classify("[PERSON_115] Bogen DN 65", "PER00007 Bogen DN 65") == t.ANONYMIZED_BOTH


def test_placeholder_against_a_plain_word():
    assert t.classify("Rohr aus Edelstahl DN 65", "Rohr aus PER000115 DN 65") == t.ANONYMIZED_ONE
    assert t.classify("Typ Pumpe: A", "### Pumpe: A") == t.ANONYMIZED_ONE
    assert t.classify("[PERSON_115]-Bogen DN 65", "[PERSON_7] DN 65") == t.ANONYMIZED_ONE
    assert t.classify("CrNiMo-Stahl Gehäuse", "CrNiMo-PER89 Gehäuse") == t.ANONYMIZED_ONE


def test_a_placeholder_does_not_hide_a_real_difference():
    assert t.classify("Rohr aus [PERSON_1] DN 65", "Rohr aus [PERSON_2] DN 80") == t.DIFFERS
    assert t.classify("Rohr aus Edelstahl DN 65 liefern", "Bogen aus PER000115 DN 65 liefern") == t.DIFFERS
    long_word = "x" * (t.MAX_SPAN + 5)
    assert t.classify("Rohr %s Ende" % long_word, "Rohr [PERSON_1] Ende") == t.DIFFERS


def test_start_and_differs():
    assert t.classify("Rohr DN 100", "Rohr DN 100 liefern und verlegen") == t.START
    assert t.classify("Rohr DN 100 liefern", "Rohr DN 150 liefern") == t.DIFFERS
    assert t.classify("Rohr [PERSON_1] DN", "Rohr [PERSON_001] DN 100 liefern") == t.START
    tail = "Abfuhr und Lagerung " * 5
    assert len(tail) > t.MAX_SPAN
    assert t.classify("Rohr mit Gerät, inkl. [PERSON_36]", "Rohr mit Gerät, inkl. " + tail) == t.START
    assert t.classify("Rohr mit Gerät, inkl. [PERSON_36]", "Rohr mit Gerät, inkl. Abfuhr") == t.ANONYMIZED_ONE


def test_supplement_marks():
    assert t.classify("Menge = Produkt aus\n1 Stück\nmal 28 Wochen",
                      "[TA11 Menge = Produkt aus [\n1 Stück\nmal\n] ]\n28 Wochen") == t.MARKS
    assert t.classify("Typ [ A ] von [PERSON_1]", "Typ A von [PERSON_001]") == t.MARKS
    assert t.classify("Typ [ A ]", "Typ B") == t.DIFFERS
    assert t.without_marks("[TB11 x [PERSON_1] ] y") == "x [PERSON_1] y"


def test_classes_are_ordered_from_equal_to_differs():
    assert t.CLASSES[0] == t.EQUAL and t.CLASSES[-1] == t.DIFFERS
    assert set(t.SAME) < set(t.CLASSES) and t.START not in t.SAME and t.MARKS not in t.SAME


def test_empty_text_is_not_compared():
    with pytest.raises(ValueError):
        t.classify("", "x")
