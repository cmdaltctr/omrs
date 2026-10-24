"""The web app works with any one non-base extra missing (design D5).

For each extra the test hides the extra's modules, builds the web app
with default settings and a LanceDB store in ``tmp_path``, and checks
three things: the app starts, ``GET /v1/integrations`` reports the extra
``not-installed``, and a hybrid search on a small ingested collection
returns results. The search asks for hybrid scoring so the BM25 path
runs; it turns the reranker off because the ONNX model is a download.
No model, LLM or network call happens.
"""

from __future__ import annotations

import importlib.abc
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from llama_index.core import Settings  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    lance_store,
    login,
    wait_for,
)

import omrs.capabilities as capabilities  # noqa: E402
from omrs.engine import Engine  # noqa: E402
from omrs.transports.api.app import create_app  # noqa: E402
from omrs.transports.api.lifespan import WebConfig  # noqa: E402
from omrs.transports.api.routes import chat_settings  # noqa: E402
from omrs.transports.api.runs_wiring import run_service_factory  # noqa: E402
from omrs.transports.api.security import AccessPolicy  # noqa: E402

#: Top-level modules of each non-base extra, from the extra's requirements in
#: ``pyproject.toml`` and the imports in ``src/omrs``. A name hides the module
#: and all its submodules.
HIDDEN_MODULES: dict[str, tuple[str, ...]] = {
    # chromadb, llama-index-vector-stores-chroma (core/vectordb/chroma, registry probe).
    "chroma": ("chromadb", "llama_index.vector_stores.chroma"),
    # rank-bm25 (core/retrieval/sparse.py; the built-in BM25 takes over).
    "hybrid": ("rank_bm25",),
    # pypdfium2 (integrations/pdf/pypdfium.py, PDF registry probe).
    "pdf-pypdfium2": ("pypdfium2",),
    # leidenalg, igraph (integrations/leidenalg.py, community registry probe).
    "community-leiden": ("leidenalg", "igraph"),
    # azure-ai-documentintelligence (integrations/azure.py). The ``azure``
    # namespace can hold other packages, so only the SDK package is hidden.
    "azure": ("azure.ai.documentintelligence",),
    # llama-index-llms-anthropic pulls in the anthropic SDK (core/providers/llm/anthropic.py).
    "anthropic": ("anthropic", "llama_index.llms.anthropic"),
    # sentence-transformers and transformers, plus torch under them. No base
    # module imports transformers: the ONNX reranker uses tokenizers and onnxruntime.
    "torch": ("torch", "sentence_transformers", "transformers"),
}

COLLECTION = "notes"


def _hidden(name: str, roots: tuple[str, ...]) -> bool:
    return any(name == root or name.startswith(f"{root}.") for root in roots)


class _HideModules(importlib.abc.MetaPathFinder):
    """Raise ``ModuleNotFoundError`` for the hidden modules and their submodules."""

    def __init__(self, roots: tuple[str, ...]) -> None:
        self.roots = roots

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> None:
        if _hidden(fullname, self.roots):
            raise ModuleNotFoundError(f"No module named {fullname!r} (hidden)", name=fullname)
        return None


def _without(original: Callable[[str], bool], roots: tuple[str, ...]) -> Callable[[str], bool]:
    def probe(name: str) -> bool:
        return False if _hidden(name, roots) else original(name)

    return probe


@pytest.fixture
def hide_extra(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[str], None]]:
    """Return a function that hides one extra's modules for this test."""
    finders: list[_HideModules] = []

    def hide(extra: str) -> None:
        roots = HIDDEN_MODULES[extra]
        # A finder alone does not hide a module that an earlier test imported.
        for name in [name for name in sys.modules if _hidden(name, roots)]:
            monkeypatch.delitem(sys.modules, name, raising=False)
        finder = _HideModules(roots)
        sys.meta_path.insert(0, finder)
        finders.append(finder)
        # Patch each place that looks the probe up (gotcha 8b).
        monkeypatch.setattr(
            capabilities, "module_installed", _without(capabilities.module_installed, roots)
        )
        monkeypatch.setattr(
            chat_settings, "module_installed", _without(chat_settings.module_installed, roots)
        )

    yield hide
    for finder in finders:
        sys.meta_path.remove(finder)


def _build_app(tmp_path: Path, engine: Engine, root: Path) -> tuple[Any, AccessPolicy]:
    config = WebConfig(workspace=tmp_path / "ws", port=8765, roots=(root,), static_dir=None)
    policy = AccessPolicy.for_launch(config.host, config.port)
    app = create_app(
        config,
        policy=policy,
        engine_factory=lambda: engine,
        run_service_factory=run_service_factory,
    )
    return app, policy


@pytest.fixture
def docs(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "alpha.md").write_text(
        "# Alpha\n\nThe lighthouse keeper logs the tide every morning.\n", encoding="utf-8"
    )
    (root / "beta.txt").write_text(
        "Bread rises faster in a warm kitchen than in a cold one.\n", encoding="utf-8"
    )
    return root


@pytest.mark.parametrize("extra", list(HIDDEN_MODULES))
def test_app_starts_lists_and_searches_without_extra(
    extra: str,
    tmp_path: Path,
    docs: Path,
    effective_settings: Any,
    hide_extra: Callable[[str], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(tmp_path / "config" / "omrs"))
    hide_extra(extra)
    for name in HIDDEN_MODULES[extra]:
        with pytest.raises(ImportError):
            __import__(name)

    # The class defaults would call an LLM for metadata (conftest pins these two).
    settings = effective_settings(extraction_mode="disabled", pdf_reader="pypdf")
    engine = Engine(settings, store=lance_store(tmp_path), embed_model=Settings.embed_model)
    app, policy = _build_app(tmp_path, engine, docs)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)

        listing = client.get("/v1/integrations")
        assert listing.status_code == 200, listing.text
        by_id = {entry["id"]: entry for entry in listing.json()["integrations"]}
        assert by_id[extra]["availability"] == "not-installed"

        accepted = client.post(
            "/v1/ingestions", json={"path": str(docs), "collection": COLLECTION}, headers=ORIGIN
        )
        assert accepted.status_code == 202, accepted.text
        job_id = accepted.json()["job_id"]
        done = wait_for(lambda: client.get(f"/v1/jobs/{job_id}").json())
        assert done["status"] == "completed", done

        found = client.post(
            f"/v1/collections/{COLLECTION}/search",
            json={
                "query": "lighthouse tide",
                "hybrid": True,
                "rerank": False,
                "similarity_threshold": 0.0,
            },
            headers=ORIGIN,
        )
    assert found.status_code == 200, found.text
    assert found.json(), f"search returned no rows with {extra!r} missing"
