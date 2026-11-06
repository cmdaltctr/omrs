"""The example cut comes from the default backend's descriptor (change cuts-follow-ups, D1).

Two texts show an example cut: the ``ocr_local_cuts`` field example (used by the
``omrs config init`` template) and the start-up refusal for the retired
``OCR_LOCAL_MIN_CONFIDENCE``. Neither types a backend name or a number.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
import textwrap

import pytest

from omrs.config.legacy import _REMOVED_ENV_VARS
from omrs.config.reading_lists import ReadingListMixin
from omrs.core import reading_parts


def _descriptor_example() -> dict[str, float]:
    name = reading_parts.DEFAULT_LOCAL_OCR_BACKENDS[0]
    cut = reading_parts.local_backend(name).min_confidence
    assert cut is not None
    return {name: cut}


def test_field_example_is_the_descriptor_default() -> None:
    field = ReadingListMixin.model_fields["ocr_local_cuts"]
    assert field.examples == [_descriptor_example()]


def test_refusal_text_is_the_descriptor_default() -> None:
    text = _REMOVED_ENV_VARS["OCR_LOCAL_MIN_CONFIDENCE"]
    assert json.dumps(_descriptor_example()) in text
    double_underscore = _REMOVED_ENV_VARS["OCR__LOCAL_MIN_CONFIDENCE"]
    assert double_underscore == text


def test_helper_reads_the_table_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    first = reading_parts.LOCAL_OCR_BACKENDS[0]
    patched = dataclasses.replace(first, name="demo-backend", min_confidence=0.77)
    monkeypatch.setattr(reading_parts, "LOCAL_OCR_BACKENDS", (patched,))
    monkeypatch.setattr(reading_parts, "DEFAULT_LOCAL_OCR_BACKENDS", ("demo-backend",))
    assert reading_parts.example_local_cuts() == {"demo-backend": 0.77}


_PATCHED_IMPORT = textwrap.dedent(
    """
    import dataclasses, json
    from omrs.core import reading_parts as rp

    first = rp.LOCAL_OCR_BACKENDS[0]
    patched = dataclasses.replace(first, name="demo-backend", min_confidence=0.77)
    rp.LOCAL_OCR_BACKENDS = (patched,)
    rp.DEFAULT_LOCAL_OCR_BACKENDS = ("demo-backend",)

    from omrs.config import legacy
    from omrs.config.reading_lists import ReadingListMixin

    print(json.dumps({
        "example": ReadingListMixin.model_fields["ocr_local_cuts"].examples,
        "refusal": legacy._REMOVED_ENV_VARS["OCR_LOCAL_MIN_CONFIDENCE"],
    }))
    """
)


def test_field_example_and_refusal_follow_a_patched_descriptor_default() -> None:
    """A fresh interpreter patches the table before ``omrs.config`` is imported."""
    done = subprocess.run(
        [sys.executable, "-I", "-c", _PATCHED_IMPORT],
        capture_output=True,
        text=True,
        check=True,
    )
    seen = json.loads(done.stdout.strip().splitlines()[-1])
    assert seen["example"] == [{"demo-backend": 0.77}]
    assert '{"demo-backend": 0.77}' in seen["refusal"]
    assert "pp-ocrv6-small" not in seen["refusal"]
