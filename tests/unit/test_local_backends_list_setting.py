"""``ocr_local_backends`` in Settings > Document reading and the Read document step.

Change local-ocr-backends, task 6.4 (design D8, spec "Settings and the Read
document step SHALL edit the backend list"). The list is edited like the PDF
reader list. A saved graph that never set it keeps its fingerprint.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from tests.unit.test_engine_pipelines_support import build_engine
from tests.unit.test_ingestion_graph_adapters_support import (
    build_catalogue,
    canonical_graph,
    offline_settings,
)

from omrs.config import rules
from omrs.config.rules import LIST_DUPLICATE_RULE, LIST_EMPTY_RULE, document_reading_problem
from omrs.core.ingestion import graph_adapters_catalogue
from omrs.core.ingestion.graph_adapters import canonical_ingestion_definition
from omrs.core.ingestion.graph_adapters_catalogue import ReadParams
from omrs.core.ingestion.graph_adapters_values import with_read_options
from omrs.core.ingestion.graph_fingerprint import graph_shape, standard_shape
from omrs.core.pipelines import IssueCode, PipelineValidationError, levers, parse_definition

KEY = "ocr_local_backends"


# ── The key lists ────────────────────────────────────────────────────────


def test_the_key_is_a_document_reading_key_and_a_read_step_key() -> None:
    assert KEY in rules.DOCUMENT_READING_KEYS
    assert KEY in graph_adapters_catalogue.READ_OCR_KEYS
    assert KEY in graph_adapters_catalogue.READ_OPTION_KEYS
    assert KEY in levers._READ_STEP_OCR_KEYS


def test_a_graph_wide_override_is_host_owned_and_points_at_the_step() -> None:
    problem = levers.lever_error(KEY, ["pp-ocrv6-small"])

    assert problem is not None and problem[0] == "host_owned"
    assert "Read document step" in problem[1]


# ── The write rule ───────────────────────────────────────────────────────


def test_the_default_list_passes() -> None:
    assert document_reading_problem(KEY, ["pp-ocrv6-small"]) is None


@pytest.mark.parametrize(
    ("value", "rule"),
    [
        ([], LIST_EMPTY_RULE),
        (["pp-ocrv6-small", "pp-ocrv6-small"], LIST_DUPLICATE_RULE),
        ("pp-ocrv6-small", rules.LIST_TYPE_RULE),
    ],
)
def test_a_list_that_breaks_the_list_rules_is_refused(value: Any, rule: str) -> None:
    assert document_reading_problem(KEY, value) == rule


def test_an_unknown_name_is_refused_naming_the_accepted_values() -> None:
    rule = document_reading_problem(KEY, ["nope"])

    assert rule is not None
    assert "pp-ocrv6-small" in rule
    assert "nope" not in rule


# ── The Read document step ───────────────────────────────────────────────


def test_the_step_inherits_by_default_and_takes_a_valid_list() -> None:
    assert ReadParams().ocr_local_backends is None
    params = ReadParams.model_validate({KEY: ["pp-ocrv6-small"]})
    assert params.ocr_local_backends == ("pp-ocrv6-small",)


def test_an_unknown_name_in_the_step_is_refused() -> None:
    with pytest.raises(ValidationError, match="Accepted values: pp-ocrv6-small"):
        ReadParams.model_validate({KEY: ["nope"]})


def _graph(**read: Any) -> dict[str, Any]:
    data = canonical_ingestion_definition("documents").model_dump(mode="json")
    for node in data["graph"]["nodes"]:
        if node["id"] == "read":
            node["params"] = {**node["params"], **read}
    return data


def test_an_unknown_name_in_a_graph_gives_invalid_parameter(
    effective_settings: Any, tmp_path: Path
) -> None:
    """Scenario "Unknown name in a step"."""
    engine = build_engine(offline_settings(effective_settings))

    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(_graph(**{KEY: ["nope"]}), inputs={"path": str(tmp_path)})

    bad = [issue for issue in caught.value.issues if issue.code == IssueCode.INVALID_PARAMETER]
    assert bad and bad[0].node_id == "read"
    assert KEY in bad[0].message and "pp-ocrv6-small" in bad[0].message


def test_a_step_list_reaches_the_node_settings(effective_settings: Any) -> None:
    settings = effective_settings()

    assert with_read_options(settings, {KEY: ("pp-ocrv6-small",)}).ocr_local_backends == (
        "pp-ocrv6-small",
    )


# ── Fingerprints ─────────────────────────────────────────────────────────


def _fingerprint(**changes: Any) -> str:
    data = canonical_graph("documents", **changes)
    return graph_shape(parse_definition(data).graph, build_catalogue()).fingerprint


def test_a_graph_without_the_key_keeps_the_standard_fingerprint() -> None:
    """Scenario "Saved graph keeps its fingerprint" (the pins sit in test_read_step_lists)."""
    assert _fingerprint() == standard_shape().fingerprint


def test_a_set_list_moves_the_fingerprint_and_names_the_list() -> None:
    data = canonical_graph("documents", read={KEY: ["pp-ocrv6-small"]})
    shape = graph_shape(parse_definition(data).graph, build_catalogue())

    assert shape.fingerprint != standard_shape().fingerprint
    assert shape.read_options == {KEY: ["pp-ocrv6-small"]}
