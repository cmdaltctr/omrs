"""Compose siblings that read ``Settings`` run reading-part discovery first.

If a sibling is the first to read settings in a process, a listed discovered
backend must still be accepted (change local-ocr-backends, design D11). Each
test uses a fake distribution; no package is installed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_part_discovery_support import backend_distribution, fake_parts_builder

import omrs.config as config
from omrs import compose_answer, compose_embedding, compose_engine


@pytest.fixture
def fake_parts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Yield the fake-distribution builder; discovery has not run in this test."""
    yield from fake_parts_builder(tmp_path, monkeypatch)


def _check_embedding_model() -> Any:
    return compose_embedding.check_embedding_model(
        "llamacpp", "fake-model", list_models=lambda url: []
    )


SIBLING_READS: dict[str, Callable[[], Any]] = {
    "server_default_identity": compose_embedding.server_default_identity,
    "check_embedding_model": _check_embedding_model,
    "build_answer_llm": compose_answer.build_answer_llm,
    "build_verify_llm": compose_answer.build_verify_llm,
    "configured_vector_store": compose_engine.configured_vector_store,
    "experiment_base_settings": compose_engine.experiment_base_settings,
}


@pytest.mark.parametrize("read", SIBLING_READS.values(), ids=SIBLING_READS.keys())
def test_a_sibling_settings_read_accepts_a_discovered_backend(
    read: Callable[[], Any], fake_parts, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend_distribution(fake_parts)
    monkeypatch.setenv("OCR_LOCAL_BACKENDS", "fake-ocr,pp-ocrv6-small")
    monkeypatch.setattr(config, "_settings", None)

    read()

    assert config.get_settings().ocr_local_backends == ("fake-ocr", "pp-ocrv6-small")
