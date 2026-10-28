"""The Read document step sets OCR options (tasks 4.1 and 4.2, design D4).

Change integrations-show-runtime-components. The step takes the eight
document-reading keys other than ``pdf_reader``. ``None`` inherits the host
value. A set value passes the same rule as Settings > Document reading. An
engine that is not provisioned under the host workers folder fails admission
with ``option_unavailable``. A graph-wide override of a key stays host-owned.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from tests.unit.test_engine_pipelines_support import build_engine, retrieval_graph
from tests.unit.test_ingestion_graph_adapters_support import offline_settings

from omrs.capabilities import ocr_engine_options
from omrs.config.rules import document_reading_problem
from omrs.core.ingestion.graph_adapters import canonical_ingestion_definition
from omrs.core.ingestion.graph_adapters_catalogue import ReadParams
from omrs.core.pipelines import IssueCode, PipelineValidationError

#: The eight step keys and one valid value for each.
VALID_VALUES: dict[str, Any] = {
    "ocr_fallback_enabled": True,
    "ocr_fallback_min_confidence": 0.4,
    "ocr_fallback_page_fraction": 0.25,
    "ocr_routing_unit": "page",
    "ocr_engine_primary": "paddleocr-vl",
    "ocr_engine_fallback": "dots-mocr",
    "ocr_maths_routing_enabled": False,
    "ocr_maths_page_fraction": 1.0,
}


def _graph(**read: Any) -> dict[str, Any]:
    data = canonical_ingestion_definition("documents").model_dump(mode="json")
    for node in data["graph"]["nodes"]:
        if node["id"] == "read":
            node["params"] = {**node["params"], **read}
    return data


def _workers(tmp_path: Path) -> Path:
    """Return a workers folder: ``dots-mocr`` provisioned, ``paddleocr-vl`` not."""
    root = tmp_path / "workers"
    python = root / "engines" / "dots-mocr" / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("")
    (root / "engines" / "paddleocr-vl").mkdir()
    return root


def _engine(effective_settings: Any, workers: Path) -> Any:
    return build_engine(offline_settings(effective_settings, ocr_workers_dir=str(workers)))


def _issues(engine: Any, data: dict[str, Any], tmp_path: Path) -> list[Any]:
    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(data, inputs={"path": str(tmp_path)})
    return list(caught.value.issues)


# ── Parameter contract (task 4.1) ────────────────────────────────────────


@pytest.mark.parametrize("key", sorted(VALID_VALUES))
def test_each_key_inherits_by_default_and_accepts_a_valid_value(key: str) -> None:
    """``None`` inherits; a value that passes the Settings rule validates."""
    assert getattr(ReadParams(), key) is None
    assert getattr(ReadParams(**{key: None}), key) is None
    assert getattr(ReadParams.model_validate({key: VALID_VALUES[key]}), key) == VALID_VALUES[key]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ocr_fallback_page_fraction", 1.5),
        ("ocr_fallback_min_confidence", -0.1),
        ("ocr_maths_page_fraction", "0.5"),
        ("ocr_fallback_enabled", "yes"),
        ("ocr_routing_unit", "pages"),
        ("ocr_engine_primary", "../escape"),
        ("ocr_engine_fallback", " "),
    ],
)
def test_values_that_break_the_settings_rule_fail(key: str, value: Any) -> None:
    """The step refuses what Settings > Document reading refuses, with the same rule."""
    rule = document_reading_problem(key, value)
    assert rule is not None
    with pytest.raises(ValidationError, match=key) as caught:
        ReadParams.model_validate({key: value})
    assert rule in str(caught.value)


@pytest.mark.parametrize(
    ("key", "value"), [("ocr_fallback_page_fraction", 1.5), ("ocr_routing_unit", "pages")]
)
def test_invalid_values_fail_validation_before_any_node_runs(
    key: str, value: Any, effective_settings: Any, tmp_path: Path
) -> None:
    """Admission reports ``invalid_parameter`` on the Read document node."""
    engine = _engine(effective_settings, _workers(tmp_path))
    issues = _issues(engine, _graph(**{key: value}), tmp_path)
    bad = [i for i in issues if i.code == IssueCode.INVALID_PARAMETER]
    assert bad and bad[0].node_id == "read" and key in bad[0].message
    assert str(document_reading_problem(key, value)) in bad[0].message


def test_engine_parameters_are_option_parameters() -> None:
    """The host reports engine availability for both engine settings."""
    from tests.unit.test_ingestion_graph_adapters_support import build_catalogue

    entry = build_catalogue().get("read.document")
    assert entry is not None
    options = entry.descriptor.option_params
    assert options["ocr_engine_primary"] == "ocr_engine_primary"
    assert options["ocr_engine_fallback"] == "ocr_engine_fallback"
    assert options["pdf_reader"] == "pdf_reader"


# ── Engine availability (task 4.1) ───────────────────────────────────────


@pytest.mark.parametrize("key", ["ocr_engine_primary", "ocr_engine_fallback"])
@pytest.mark.parametrize("engine_name", ["paddleocr-vl", "made-up"])
def test_engine_not_provisioned_fails_with_the_provision_command(
    key: str, engine_name: str, effective_settings: Any, tmp_path: Path
) -> None:
    """The issue names the node, the engine and the provision command."""
    workers = _workers(tmp_path)
    engine = _engine(effective_settings, workers)
    issues = _issues(engine, _graph(**{key: engine_name}), tmp_path)
    unavailable = [i for i in issues if i.code == IssueCode.OPTION_UNAVAILABLE]
    assert unavailable, issues
    issue = unavailable[0]
    options = ocr_engine_options(str(workers), [engine_name])
    reason = next(o["reason"] for o in options if o["name"] == engine_name)
    assert issue.node_id == "read"
    assert engine_name in issue.message
    assert reason and reason in issue.message
    assert "provision.py" in issue.message
    assert "Install the package" not in issue.message


def test_provisioned_engine_validates(effective_settings: Any, tmp_path: Path) -> None:
    """A provisioned engine passes admission."""
    engine = _engine(effective_settings, _workers(tmp_path))
    engine.validate_pipeline(
        _graph(ocr_engine_primary="dots-mocr", ocr_engine_fallback="dots-mocr"),
        inputs={"path": str(tmp_path)},
    )


def test_catalogue_lists_unprovisioned_engines_and_the_inherited_engine(
    effective_settings: Any, tmp_path: Path
) -> None:
    """The step option list carries engine availability, like the reader list."""
    workers = _workers(tmp_path)
    settings = offline_settings(
        effective_settings, ocr_workers_dir=str(workers), ocr_engine_primary="dots-mocr"
    )
    entry = next(
        e
        for e in build_engine(settings).describe_operations()
        if e["operation_id"] == "read.document"
    )
    assert list(entry["unavailable_options"]["ocr_engine_primary"]) == ["paddleocr-vl"]
    assert entry["inherited_values"]["ocr_engine_primary"] == "dots-mocr"


# ── Graph-wide overrides stay host-owned (task 4.2) ──────────────────────


@pytest.mark.parametrize("key", sorted(VALID_VALUES))
def test_graph_wide_ocr_override_is_host_owned(key: str, effective_settings: Any) -> None:
    """``overrides.<key>`` fails with ``host_owned_setting`` and names the step."""
    engine = build_engine(effective_settings())
    data = retrieval_graph()
    data["overrides"] = {key: VALID_VALUES[key]}
    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(data)
    owned = [i for i in caught.value.issues if i.code == IssueCode.HOST_OWNED_SETTING]
    assert owned and owned[0].lever == key
    assert "Set it on the Read document step" in owned[0].message
