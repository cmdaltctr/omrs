"""The output-script verdict of a local OCR result (change local-ocr-backends, design D10).

``script_routing.output_script`` names the Unicode script that holds at least half
of the letters of a text with at least 40 letters. The floor and the share are
fixed in code with their own version number; the non-Latin detector and its
version do not change.
"""

from __future__ import annotations

from omrs.integrations.pdf import script_routing
from omrs.integrations.pdf.script_routing import output_script

DEVANAGARI = "क"
ARABIC = "ب"
BENGALI = "ক"


def test_a_mostly_devanagari_text_is_devanagari() -> None:
    assert output_script(DEVANAGARI * 380 + "a" * 20) == "devanagari"


def test_a_text_with_no_script_at_half_gets_no_verdict() -> None:
    assert output_script(ARABIC * 40 + "a" * 30 + BENGALI * 30) is None


def test_a_short_text_gets_no_verdict() -> None:
    assert output_script(ARABIC * 39) is None
    assert output_script(ARABIC * 40) == "arabic"


def test_exactly_half_is_enough() -> None:
    assert output_script(BENGALI * 20 + ARABIC * 10 + "a" * 10) == "bengali"


def test_digits_punctuation_and_space_are_not_letters() -> None:
    assert output_script("12345 ,.;!? " * 20 + ARABIC * 39) is None


def test_accented_latin_counts_as_latin() -> None:
    assert output_script("é" * 30 + "a" * 30) == "latin"


def test_the_rule_has_its_own_version_and_the_detector_keeps_its_own() -> None:
    """A change to the floor or share bumps OUTPUT_SCRIPT_VERSION, not the detector's."""
    assert script_routing.OUTPUT_SCRIPT_VERSION == 1
    assert (script_routing.OUTPUT_SCRIPT_MIN_LETTERS, script_routing.OUTPUT_SCRIPT_SHARE) == (
        40,
        0.5,
    )
    assert script_routing.SCRIPT_DETECTOR_VERSION == 1
    assert (script_routing.MIN_LETTERS, script_routing.NON_LATIN_SHARE) == (40, 0.5)
