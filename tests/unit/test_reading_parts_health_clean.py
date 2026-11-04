"""Health rows clean the reason text before it leaves the server (review of PR #168).

A panic or an ``ImportError`` from ``dlopen`` can hold the full home folder. The
``off_reason`` of a local OCR backend and the ``problem`` of a discovered part
come back with the home folder as ``~`` and a length cap. The log keeps the
full text. A discovered part that fails to load keeps its entry-point name.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_part_discovery_support import fake_parts_builder, run_discovery

from omrs.integrations.pdf import page_routing
from omrs.transports.api import reading_parts_health as health


@pytest.fixture
def fake_parts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    yield from fake_parts_builder(tmp_path, monkeypatch)


def _off_reason(settings: Any) -> str:
    (row,) = health.reading_parts_health(settings)["local_ocr_backends"]
    return row["off_reason"]


def test_the_home_folder_in_a_reason_comes_back_as_a_tilde(effective_settings: Any) -> None:
    home = str(Path.home())
    page_routing.switch_local_tier_off(f"OSError: dlopen({home}/lib/libpaddle.dylib) failed")

    assert _off_reason(effective_settings()) == "OSError: dlopen(~/lib/libpaddle.dylib) failed"


def test_an_over_long_reason_is_capped(effective_settings: Any) -> None:
    page_routing.switch_local_tier_off("PanicException: " + "x" * 1000)

    reason = _off_reason(effective_settings())

    assert len(reason) == health.MAX_REASON_CHARS
    assert reason.startswith("PanicException: xxx")
    assert reason.endswith("…")


def test_a_normal_reason_is_unchanged(effective_settings: Any) -> None:
    page_routing.switch_local_tier_off("PanicException: lock poisoned")

    assert _off_reason(effective_settings()) == "PanicException: lock poisoned"


def test_a_broken_part_row_has_its_entry_point_name_and_a_clean_problem(fake_parts) -> None:
    home = str(Path.home())
    fake_parts(
        "acmebroken",
        {"omrs.page_rules": {"acme": "{mod:desc}:RULE"}},
        {"desc": f"raise ImportError('cannot open {home}/acme/lib.so')\n"},
    )
    found = run_discovery()

    (row,) = [row for row in health.discovered_rows(found) if row["distribution"] == "acmebroken"]

    assert row["name"] == "acme"
    assert "~/acme/lib.so" in row["problem"]
    assert home not in row["problem"]
