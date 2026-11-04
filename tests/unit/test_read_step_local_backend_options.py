"""The Read document step reports host facts for ``ocr_local_backends``.

Change local-ocr-backends, task 6.4. The step inherits the host backend list,
and a backend that is not installed fails admission with ``option_unavailable``
and the command that installs its extra, like an unprovisioned OCR engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_engine_pipelines_support import build_engine
from tests.unit.test_ingestion_graph_adapters_support import offline_settings

from omrs.core.ingestion.graph_adapters import canonical_ingestion_definition
from omrs.core.pipelines import IssueCode, PipelineValidationError
from omrs.integrations.pdf.local_ocr import registry as local_ocr_registry


def _graph(**read: Any) -> dict[str, Any]:
    data = canonical_ingestion_definition("documents").model_dump(mode="json")
    for node in data["graph"]["nodes"]:
        if node["id"] == "read":
            node["params"] = {**node["params"], **read}
    return data


def test_a_backend_that_is_not_installed_fails_with_its_extra(
    effective_settings: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The issue names the node, the backend and the extra that installs it."""
    monkeypatch.setattr(local_ocr_registry, "installed", lambda name: name != "indra")
    engine = build_engine(offline_settings(effective_settings))

    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(
            _graph(ocr_local_backends=["indra", "pp-ocrv6-small"]),
            inputs={"path": str(tmp_path)},
        )

    unavailable = [i for i in caught.value.issues if i.code == IssueCode.OPTION_UNAVAILABLE]
    assert unavailable, caught.value.issues
    assert unavailable[0].node_id == "read"
    assert "indra" in unavailable[0].message
    assert "local-ocr-indra" in unavailable[0].message


def test_installed_backends_pass_admission(
    effective_settings: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local_ocr_registry, "installed", lambda name: True)
    engine = build_engine(offline_settings(effective_settings))

    engine.validate_pipeline(
        _graph(ocr_local_backends=["indra", "pp-ocrv6-small"]), inputs={"path": str(tmp_path)}
    )
