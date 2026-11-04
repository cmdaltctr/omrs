"""The non-Latin script detector (change non-latin-script-routing, task 1.2, design D2).

Letters are ``str.isalpha()`` characters. A letter is Latin when its Unicode
name starts with ``LATIN``. A verdict needs at least 40 letters, and the page is
non-Latin when at least half of the letters are not Latin. The constants are
fixed and versioned: a test pins them to ``SCRIPT_DETECTOR_VERSION``.
"""

from __future__ import annotations

import pytest

from omrs.integrations.pdf.script_routing import (
    MIN_LETTERS,
    NON_LATIN_SHARE,
    SCRIPT_DETECTOR_VERSION,
    is_non_latin,
)

ARABIC = "ب"  # BA
DEVANAGARI = "क"  # KA
HIRAGANA = "あ"  # A


def test_a_few_letters_give_no_verdict() -> None:
    """A scan's stamp text holds about 7 Latin letters: no verdict, not "Latin"."""
    assert is_non_latin("STAMP A") is None


def test_the_floor_applies_to_non_latin_text_too() -> None:
    assert is_non_latin(ARABIC * (MIN_LETTERS - 1)) is None
    assert is_non_latin(ARABIC * MIN_LETTERS) is True


def test_an_arabic_text_layer_is_non_latin() -> None:
    assert is_non_latin(ARABIC * 280 + "a" * 20) is True


def test_a_devanagari_text_layer_is_non_latin() -> None:
    assert is_non_latin(DEVANAGARI * 400) is True


def test_a_japanese_text_layer_is_non_latin() -> None:
    assert is_non_latin(HIRAGANA * 60) is True


def test_accented_latin_counts_as_latin() -> None:
    assert is_non_latin("éàüñçøåß" * 20) is False


def test_plain_latin_is_latin() -> None:
    assert is_non_latin("The quick brown fox jumps over the lazy dog. " * 4) is False


def test_digits_punctuation_and_space_are_not_letters() -> None:
    """300 symbols and 41 Latin letters: the symbols do not dilute or inflate the share."""
    text = "1234567890 .,;:!?()[]{}-_/\\ " * 20 + "a" * (MIN_LETTERS + 1)
    assert is_non_latin(text) is False
    only_symbols = "1234567890 .,;:!?()[]{}-_/\\ " * 20
    assert is_non_latin(only_symbols) is None


def test_symbols_do_not_count_toward_the_floor() -> None:
    assert is_non_latin(ARABIC * (MIN_LETTERS - 1) + "123456789") is None


def test_the_share_boundary_is_inclusive() -> None:
    half = ARABIC * (MIN_LETTERS // 2) + "a" * (MIN_LETTERS // 2)
    assert is_non_latin(half) is True
    just_under = ARABIC * (MIN_LETTERS // 2 - 1) + "a" * (MIN_LETTERS // 2 + 1)
    assert is_non_latin(just_under) is False


def test_empty_text_gives_no_verdict() -> None:
    assert is_non_latin("") is None


@pytest.mark.parametrize("text", ["ก" * 50, "中" * 50, "א" * 50])
def test_other_non_latin_scripts(text: str) -> None:
    assert is_non_latin(text) is True


def test_constants_are_pinned_to_the_detector_version() -> None:
    """Changing a constant without a version bump fails here.

    The version joins the source index identity, so a change re-ingests PDF
    sources that use the setting. Bump the version, then update this pin.
    """
    assert (SCRIPT_DETECTOR_VERSION, MIN_LETTERS, NON_LATIN_SHARE) == (1, 40, 0.5)
