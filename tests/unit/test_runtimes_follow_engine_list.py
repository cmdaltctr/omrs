"""The runtimes list follows ``ocr_engines`` (local-ocr-backends D13, task 6.1).

``compose_runtimes.runtime_specs`` feeds ``GET /v1/runtimes``. It lists one
OCR runtime for every engine in the engine list that declares one, and it
labels ``used_by`` with ``ocr_engines``. The old keys stay readable as aliases.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.ocr_worker.runtime_engine import make_engine

from omrs import compose, compose_runtimes
from omrs.config import Settings
from omrs.core.reading_lists import engine_list

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX launcher scripts")

ENGINES = ("engine-a", "engine-b", "engine-c")


@pytest.fixture(autouse=True)
def _clean_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OMRS_OCR_MODEL_CACHE", "OMRS_OCR_RUNTIME_URL"):
        monkeypatch.delenv(name, raising=False)


def _ocr_rows(**values: Any) -> dict[str, list[str]]:
    settings = Settings(_env_file=None, **values)
    rows = compose_runtimes.runtime_specs(settings)
    return {spec.id: users for spec, users in rows if spec.role == "ocr"}


def test_a_third_engine_with_a_runtime_is_listed_and_used_by_ocr_engines(tmp_path: Path) -> None:
    workers = tmp_path / "workers"
    for name in ENGINES:
        make_engine(workers, name)

    assert _ocr_rows(ocr_workers_dir=str(workers), ocr_engines=ENGINES) == {
        "ocr-engine-a": ["ocr_engines"],
        "ocr-engine-b": ["ocr_engines"],
        "ocr-engine-c": ["ocr_engines"],
    }


def test_an_engine_named_twice_is_listed_once(tmp_path: Path) -> None:
    workers = tmp_path / "workers"
    make_engine(workers, "engine-a")

    assert _ocr_rows(ocr_workers_dir=str(workers), ocr_engines=("engine-a", "engine-a")) == {
        "ocr-engine-a": ["ocr_engines"]
    }


def test_an_engine_without_a_runtime_is_not_listed(tmp_path: Path) -> None:
    workers = tmp_path / "workers"
    make_engine(workers, "engine-a")
    make_engine(workers, "engine-b", runtime=False)

    assert list(_ocr_rows(ocr_workers_dir=str(workers), ocr_engines=("engine-a", "engine-b"))) == [
        "ocr-engine-a"
    ]


def test_the_old_primary_key_alone_still_resolves_the_engine_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCR_ENGINE_PRIMARY", "paddleocr-vl")
    effective = compose.settings_to_effective(Settings(_env_file=None))

    assert effective.ocr_engines == ("paddleocr-vl", "paddleocr-vl")
    assert engine_list(effective) == ("paddleocr-vl", "paddleocr-vl")


def test_the_old_keys_alone_still_decide_the_runtimes(tmp_path: Path) -> None:
    workers = tmp_path / "workers"
    make_engine(workers, "engine-a")
    make_engine(workers, "engine-b")

    rows = _ocr_rows(
        ocr_workers_dir=str(workers), ocr_engine_primary="engine-a", ocr_engine_fallback="engine-b"
    )
    assert rows == {
        "ocr-engine-a": ["ocr_engines"],
        "ocr-engine-b": ["ocr_engines"],
    }
