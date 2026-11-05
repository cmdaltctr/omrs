"""The Read document step picks a router by name (document-reading-routers, task 4.2).

``ReadParams.document_router`` takes a router name, ``none`` (routing off for
the step) or ``null`` (inherit the host router). A name that no router holds
fails admission with ``option_unavailable`` before any node runs. The step's
router enters the source identity under the host router's rule: the recipe
enters the ``parser`` block, the name does not enter the graph fingerprint.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from tests.unit.test_engine_pipelines_support import build_engine
from tests.unit.test_ingestion_graph_adapters_support import build_catalogue, offline_settings

from omrs.core.ingestion.graph_adapters import canonical_ingestion_definition
from omrs.core.ingestion.graph_adapters_catalogue import READ, ReadParams
from omrs.core.ingestion.graph_adapters_values import with_read_options
from omrs.core.ingestion.graph_fingerprint import graph_shape, standard_shape
from omrs.core.ingestion.reader_identity import pdf_parser_payload
from omrs.core.pipelines import GraphDocument, IssueCode, PipelineValidationError

LOCAL = {"kind": "llamacpp", "address": "http://127.0.0.1:8090", "model": "clef-flash-q8_0"}
RECIPE = {"model": "clef", "question": "Does the text match?", "threshold": 0.172}


def _routers(**names: dict[str, Any]) -> dict[str, Any]:
    return {"decision_models": {"clef": LOCAL}, "document_routers": names}


def _graph(**read: Any) -> dict[str, Any]:
    data = canonical_ingestion_definition("documents").model_dump(mode="json")
    for node in data["graph"]["nodes"]:
        if node["id"] == "read":
            node["params"] = {**node["params"], **read}
    return data


# ── Parameter ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["handwriting", "none", None])
def test_the_step_takes_a_name_none_or_null(value: str | None) -> None:
    assert ReadParams(document_router=value).document_router == value


@pytest.mark.parametrize("value", ["", "  ", "../x", "a b", 3])
def test_the_step_refuses_a_value_outside_the_name_rule(value: Any) -> None:
    with pytest.raises(ValidationError):
        ReadParams(document_router=value)


def test_the_read_operation_reports_the_router_as_a_host_option() -> None:
    assert READ.option_params["document_router"] == "document_router"


# ── Admission ────────────────────────────────────────────────────────────


def test_an_unknown_router_fails_admission_naming_node_and_router(
    effective_settings: Any, tmp_path: Path
) -> None:
    settings = offline_settings(effective_settings, **_routers(handwriting=RECIPE))
    engine = build_engine(settings)

    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(_graph(document_router="missing"), inputs={"path": str(tmp_path)})

    unavailable = [i for i in caught.value.issues if i.code == IssueCode.OPTION_UNAVAILABLE]
    assert unavailable, caught.value.issues
    assert unavailable[0].node_id == "read"
    assert "missing" in unavailable[0].message


@pytest.mark.parametrize("routers", [{"handwriting": RECIPE}, {}])
def test_run_refuses_an_unknown_router_before_any_node_runs(
    effective_settings: Any, tmp_path: Path, routers: dict[str, Any]
) -> None:
    """Review finding C: ``RouterReasons`` lists nothing, yet admission still refuses.

    The validator asks ``choice in option_set.unavailable``, which a ``Mapping``
    answers through ``__getitem__``, so an empty iteration does not let the
    name through. Also with no router defined at all.
    """
    import asyncio

    settings = offline_settings(effective_settings, **_routers(**routers))
    engine = build_engine(settings)
    graph = _graph(document_router="no-such-router")

    with pytest.raises(PipelineValidationError) as caught:
        asyncio.run(engine.run_pipeline(graph, inputs={"path": str(tmp_path)}))

    codes = [i.code for i in caught.value.issues]
    assert IssueCode.OPTION_UNAVAILABLE in codes, caught.value.issues


@pytest.mark.parametrize("value", ["handwriting", "none"])
def test_a_known_router_or_none_passes_admission(
    effective_settings: Any, tmp_path: Path, value: str
) -> None:
    settings = offline_settings(effective_settings, **_routers(handwriting=RECIPE))
    engine = build_engine(settings)
    engine.validate_pipeline(_graph(document_router=value), inputs={"path": str(tmp_path)})


def test_the_catalogue_reports_the_host_router_as_inherited(effective_settings: Any) -> None:
    settings = offline_settings(
        effective_settings, document_router="handwriting", **_routers(handwriting=RECIPE)
    )
    engine = build_engine(settings)
    read = next(op for op in engine.describe_operations() if op["operation_id"] == "read.document")
    assert read["inherited_values"]["document_router"] == "handwriting"
    assert read["unavailable_options"]["document_router"] == {}


# ── Identity ─────────────────────────────────────────────────────────────


def _shape(**read: Any) -> Any:
    return graph_shape(GraphDocument.model_validate(_graph(**read)["graph"]), build_catalogue())


def test_the_router_name_stays_out_of_the_graph_fingerprint() -> None:
    shape = _shape(document_router="handwriting")
    assert shape.fingerprint == standard_shape().fingerprint
    assert shape.standard and shape.identity_block() is None
    assert shape.step_options() == {"document_router": "handwriting"}


def test_a_router_beside_another_option_stays_out_of_the_shape_block() -> None:
    block = _shape(document_router="handwriting", ocr_non_latin_routing="detect").identity_block()
    assert block is not None
    assert block["read_options"] == {"ocr_non_latin_routing": "detect"}


def test_identity_follows_the_step_router(effective_settings: Any) -> None:
    """The step's router overrides the host router in the identity, as in the read."""
    host = effective_settings(**_routers(handwriting=RECIPE, other={**RECIPE, "threshold": 0.5}))
    with_host = effective_settings(
        document_router="other", **_routers(handwriting=RECIPE, other={**RECIPE, "threshold": 0.5})
    )
    step = with_read_options(host, _shape(document_router="handwriting").step_options())
    assert step.document_router == "handwriting"
    entry = pdf_parser_payload(step)["document_router"]
    assert entry["threshold"] == 0.172
    overridden = with_read_options(with_host, {"document_router": "handwriting"})
    assert pdf_parser_payload(overridden) == pdf_parser_payload(step)
    off = with_read_options(with_host, {"document_router": "none"})
    assert "document_router" not in pdf_parser_payload(off)
    assert pdf_parser_payload(off) == pdf_parser_payload(host)


def test_null_inherits_the_host_router(effective_settings: Any) -> None:
    host = effective_settings(document_router="handwriting", **_routers(handwriting=RECIPE))
    assert with_read_options(host, ReadParams(document_router=None)) is host


def test_a_graph_wide_router_override_stays_host_owned() -> None:
    from omrs.core.pipelines.levers import lever_error

    found = lever_error("document_router", "handwriting")
    assert found is not None and found[0] == "host_owned"
