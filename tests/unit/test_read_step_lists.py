"""The Read document step takes ordered reader and engine lists.

Change ordered-reader-and-ocr-lists, task 4.1 (design D7). ``pdf_readers`` and
``ocr_engines`` join the older single-value options. A step sets one form or
the other. A saved graph with the old options keeps its fingerprint and so its
index identity.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from tests.unit.test_engine_pipelines_support import build_engine, retrieval_graph
from tests.unit.test_ingestion_graph_adapters_support import (
    build_catalogue,
    canonical_graph,
    offline_settings,
)

from omrs.config.rules import document_reading_problem, reading_list_problem
from omrs.core.ingestion.graph_adapters import canonical_ingestion_definition
from omrs.core.ingestion.graph_adapters_catalogue import READ_OPTION_KEYS, ReadParams
from omrs.core.ingestion.graph_adapters_values import with_read_options
from omrs.core.ingestion.graph_fingerprint import graph_shape, standard_shape
from omrs.core.pipelines import IssueCode, PipelineValidationError, parse_definition
from omrs.core.pipelines.levers import lever_error
from omrs.core.reading_lists import engine_list, reader_list
from omrs.integrations.pdf import registry

# Fingerprints recorded from the commit before this change (a87435a1). A new
# optional parameter must not move them.
PINNED = {
    "pypdf": "d9117c6dab89461a2f67f1e1e34ce6b4bd65ccb6ac12a371a95756a55cb531ac",
    "pdf_inspector": "07d897e9d7fafd8db5f2ff71568926dedbe79c71708dc8b0da45b7ba3efa57c9",
    "engine": "b96199d2196a8b4943c2350b655c7ee9e7db553d1a2b032be83bc3ab4435a985",
    "chunk": "f18e65ee5da4aeb8f80d8feb191734dba2f5b892f90d369a3ce7bcda9fb19bf1",
}


def _graph(**read: Any) -> dict[str, Any]:
    data = canonical_ingestion_definition("documents").model_dump(mode="json")
    for node in data["graph"]["nodes"]:
        if node["id"] == "read":
            node["params"] = {**node["params"], **read}
    return data


def _issues(engine: Any, data: dict[str, Any], tmp_path: Path) -> list[Any]:
    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(data, inputs={"path": str(tmp_path)})
    return list(caught.value.issues)


# ── Parameters ───────────────────────────────────────────────────────────


def test_the_list_options_inherit_by_default_and_are_read_options() -> None:
    assert ReadParams().pdf_readers is None
    assert ReadParams().ocr_engines is None
    assert {"pdf_readers", "ocr_engines"} <= set(READ_OPTION_KEYS)


def test_a_valid_list_validates() -> None:
    params = ReadParams.model_validate(
        {"pdf_readers": ["pdf_inspector", "pypdf"], "ocr_engines": ["dots-mocr"]}
    )
    assert params.pdf_readers == ("pdf_inspector", "pypdf")
    assert params.ocr_engines == ("dots-mocr",)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("pdf_readers", []),
        ("pdf_readers", ["pypdf", "pypdf"]),
        ("pdf_readers", ["auto"]),
        ("pdf_readers", ["pdfminer"]),
        ("pdf_readers", ["pypdf", ""]),
        ("pdf_readers", "pypdf"),
        ("ocr_engines", []),
        ("ocr_engines", ["dots-mocr", "dots-mocr"]),
        ("ocr_engines", ["../escape"]),
        ("ocr_engines", ["dots-mocr", " "]),
    ],
)
def test_a_list_that_breaks_the_settings_rule_fails_with_that_rule(key: str, value: Any) -> None:
    rule = reading_list_problem(key, value)
    assert rule is not None
    with pytest.raises(ValidationError, match=key) as caught:
        ReadParams.model_validate({key: value})
    assert rule in str(caught.value)
    assert document_reading_problem(key, value) == rule


@pytest.mark.parametrize(
    ("old", "value", "new", "new_value"),
    [
        ("pdf_reader", "pypdf", "pdf_readers", ["pypdf"]),
        ("ocr_engine_primary", "dots-mocr", "ocr_engines", ["dots-mocr"]),
        ("ocr_engine_fallback", "paddleocr-vl", "ocr_engines", ["dots-mocr"]),
    ],
)
def test_a_step_that_sets_both_forms_fails_naming_both_keys(
    old: str, value: str, new: str, new_value: list[str]
) -> None:
    with pytest.raises(ValidationError) as caught:
        ReadParams.model_validate({old: value, new: new_value})
    assert old in str(caught.value) and new in str(caught.value)


def test_the_old_options_alone_still_validate() -> None:
    params = ReadParams.model_validate(
        {"pdf_reader": "pypdf", "ocr_engine_primary": "a", "ocr_engine_fallback": "b"}
    )
    assert (params.pdf_reader, params.ocr_engine_primary, params.ocr_engine_fallback) == (
        "pypdf",
        "a",
        "b",
    )


def test_both_forms_in_a_graph_fail_admission_naming_both_keys(
    effective_settings: Any, tmp_path: Path
) -> None:
    engine = build_engine(offline_settings(effective_settings))
    issues = _issues(engine, _graph(pdf_reader="pypdf", pdf_readers=["pypdf"]), tmp_path)
    bad = [i for i in issues if i.code == IssueCode.INVALID_PARAMETER]
    assert bad and bad[0].node_id == "read"
    assert "pdf_reader" in bad[0].message and "pdf_readers" in bad[0].message


# ── Identity: a saved graph keeps its fingerprint ────────────────────────


def _fingerprint(**changes: Any) -> str:
    data = canonical_graph("documents", **changes)
    return graph_shape(parse_definition(data).graph, build_catalogue()).fingerprint


@pytest.mark.parametrize(
    ("name", "changes"),
    [
        ("pypdf", {"read": {"pdf_reader": "pypdf"}}),
        ("pdf_inspector", {"read": {"pdf_reader": "pdf_inspector"}}),
        ("engine", {"read": {"ocr_engine_primary": "paddleocr-vl"}}),
        ("chunk", {"chunk": {"chunk_size": 300}}),
    ],
)
def test_a_saved_graph_keeps_its_fingerprint(name: str, changes: dict[str, Any]) -> None:
    assert _fingerprint(**changes) == PINNED[name]


def test_the_canonical_graph_stays_standard() -> None:
    assert _fingerprint() == standard_shape().fingerprint


def test_a_set_list_moves_the_fingerprint_and_lists_are_ordered() -> None:
    a = _fingerprint(read={"pdf_readers": ["pdf_inspector", "pypdf"]})
    b = _fingerprint(read={"pdf_readers": ["pypdf", "pdf_inspector"]})
    assert len({a, b, standard_shape().fingerprint}) == 3


def test_the_identity_block_names_a_step_list() -> None:
    data = canonical_graph("documents", read={"pdf_readers": ["pypdf"], "ocr_engines": ["x"]})
    shape = graph_shape(parse_definition(data).graph, build_catalogue())
    assert shape.pdf_reader is None
    assert shape.read_options == {"pdf_readers": ["pypdf"], "ocr_engines": ["x"]}
    assert shape.identity_block()["read_options"] == {  # type: ignore[index]
        "ocr_engines": ["x"],
        "pdf_readers": ["pypdf"],
    }


# ── The step list wins over a list the host filled in ────────────────────


def _host(effective_settings: Any, **overrides: Any) -> Any:
    """Settings as compose builds them: the lists are filled from the host."""
    fields: dict[str, Any] = {
        "extraction_mode": "disabled",
        "ocr_fallback_enabled": False,
        "pdf_reader": "pdf_inspector",
        "pdf_readers": ("pdf_inspector", "liteparse", "pypdf"),
        "ocr_engine_primary": "dots-mocr",
        "ocr_engine_fallback": "paddleocr-vl",
        "ocr_engines": ("dots-mocr", "paddleocr-vl"),
    }
    return effective_settings(**{**fields, **overrides})


def test_an_old_reader_option_replaces_the_host_list(effective_settings: Any) -> None:
    step = with_read_options(_host(effective_settings), {"pdf_reader": "pypdf"})
    assert reader_list(step) == ("pypdf",)
    assert step.pdf_reader == "pypdf"


def test_the_old_pdf_inspector_option_expands_to_its_rescue_chain(effective_settings: Any) -> None:
    host = _host(effective_settings, pdf_readers=("pypdf",), pdf_reader="pypdf")
    step = with_read_options(host, {"pdf_reader": "pdf_inspector"})
    assert reader_list(step) == ("pdf_inspector", "liteparse", "pypdf")


def test_a_step_reader_list_replaces_the_host_list(effective_settings: Any) -> None:
    step = with_read_options(_host(effective_settings), {"pdf_readers": ("pypdfium2", "pypdf")})
    assert reader_list(step) == ("pypdfium2", "pypdf")
    assert step.pdf_reader == "pypdfium2"


def test_a_step_with_no_reader_option_keeps_the_host_list(effective_settings: Any) -> None:
    host = _host(effective_settings)
    assert with_read_options(host, {"pdf_readers": None}) is host
    step = with_read_options(host, {"ocr_fallback_enabled": True})
    assert reader_list(step) == ("pdf_inspector", "liteparse", "pypdf")


def test_an_old_primary_replaces_entry_one_of_the_host_engines(effective_settings: Any) -> None:
    step = with_read_options(_host(effective_settings), {"ocr_engine_primary": "other"})
    assert engine_list(step) == ("other", "paddleocr-vl")
    assert step.ocr_engine_primary == "other"


def test_an_old_fallback_replaces_entry_two_of_the_host_engines(effective_settings: Any) -> None:
    step = with_read_options(_host(effective_settings), {"ocr_engine_fallback": "other"})
    assert engine_list(step) == ("dots-mocr", "other")
    assert step.ocr_engine_fallback == "other"


def test_an_old_primary_beside_a_one_engine_host_list_gives_a_list_of_one(
    effective_settings: Any,
) -> None:
    host = _host(
        effective_settings,
        ocr_engines=("dots-mocr",),
        ocr_engine_fallback="",
    )
    step = with_read_options(host, {"ocr_engine_primary": "other"})
    assert engine_list(step) == ("other",)
    assert step.ocr_engine_fallback == ""


def test_a_step_engine_list_replaces_the_host_list(effective_settings: Any) -> None:
    step = with_read_options(_host(effective_settings), {"ocr_engines": ("a", "b", "c")})
    assert engine_list(step) == ("a", "b", "c")
    assert (step.ocr_engine_primary, step.ocr_engine_fallback) == ("a", "b")


def test_a_one_engine_step_list_clears_the_old_fallback(effective_settings: Any) -> None:
    step = with_read_options(_host(effective_settings), {"ocr_engines": ("a",)})
    assert engine_list(step) == ("a",)
    assert step.ocr_engine_fallback == ""


# ── Admission: an uninstalled reader or unprovisioned engine ─────────────


@pytest.fixture
def missing_pypdfium2(monkeypatch: pytest.MonkeyPatch) -> None:
    def _probe(name: str) -> None:
        if name == "pypdfium2":
            raise ImportError("PDF reader 'pypdfium2' dependency 'pypdfium2' is not importable")

    monkeypatch.setattr(registry, "probe", _probe)


@pytest.mark.usefixtures("missing_pypdfium2")
def test_a_step_list_with_an_uninstalled_reader_fails_naming_node_and_reader(
    effective_settings: Any, tmp_path: Path
) -> None:
    engine = build_engine(offline_settings(effective_settings))
    issues = _issues(engine, _graph(pdf_readers=["pdf_inspector", "pypdfium2"]), tmp_path)
    found = [i for i in issues if i.code == IssueCode.OPTION_UNAVAILABLE]
    assert len(found) == 1
    assert found[0].node_id == "read"
    assert "pypdfium2" in found[0].message and "pdf_readers" in found[0].message
    assert "pdf_inspector" not in found[0].message.replace("pdf_readers", "")


@pytest.mark.usefixtures("missing_pypdfium2")
def test_a_step_list_of_installed_readers_validates(
    effective_settings: Any, tmp_path: Path
) -> None:
    engine = build_engine(offline_settings(effective_settings))
    engine.validate_pipeline(
        _graph(pdf_readers=["pdf_inspector", "pypdf"]), inputs={"path": str(tmp_path)}
    )


@pytest.mark.usefixtures("missing_pypdfium2")
def test_the_host_list_may_hold_an_uninstalled_reader(
    effective_settings: Any, tmp_path: Path
) -> None:
    host = offline_settings(effective_settings, pdf_readers=("pypdfium2", "pypdf"))
    build_engine(host).validate_pipeline(_graph(), inputs={"path": str(tmp_path)})


@pytest.mark.usefixtures("missing_pypdfium2")
def test_the_catalogue_reports_list_availability_and_the_inherited_lists(
    effective_settings: Any,
) -> None:
    host = _host(effective_settings, pdf_reader="pypdf")
    entry = next(
        e for e in build_engine(host).describe_operations() if e["operation_id"] == "read.document"
    )
    assert list(entry["unavailable_options"]["pdf_readers"]) == ["pypdfium2"]
    assert entry["inherited_values"]["pdf_readers"] == ["pdf_inspector", "liteparse", "pypdf"]
    assert entry["inherited_values"]["ocr_engines"] == ["dots-mocr", "paddleocr-vl"]
    assert "pdf_readers" in entry["option_params"] and "ocr_engines" in entry["option_params"]


def _workers(tmp_path: Path) -> Path:
    """A workers folder: ``dots-mocr`` provisioned, ``paddleocr-vl`` not."""
    root = tmp_path / "workers"
    python = root / "engines" / "dots-mocr" / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("")
    (root / "engines" / "paddleocr-vl").mkdir()
    return root


def test_an_unprovisioned_engine_in_a_step_list_fails_with_the_provision_command(
    effective_settings: Any, tmp_path: Path
) -> None:
    host = offline_settings(effective_settings, ocr_workers_dir=str(_workers(tmp_path)))
    issues = _issues(
        build_engine(host), _graph(ocr_engines=["dots-mocr", "paddleocr-vl"]), tmp_path
    )
    found = [i for i in issues if i.code == IssueCode.OPTION_UNAVAILABLE]
    assert len(found) == 1
    assert found[0].node_id == "read"
    assert "paddleocr-vl" in found[0].message and "provision.py" in found[0].message
    assert "dots-mocr" not in found[0].message


def test_provisioned_engines_in_a_step_list_validate(
    effective_settings: Any, tmp_path: Path
) -> None:
    host = offline_settings(effective_settings, ocr_workers_dir=str(_workers(tmp_path)))
    build_engine(host).validate_pipeline(
        _graph(ocr_engines=["dots-mocr"]), inputs={"path": str(tmp_path)}
    )


# ── Graph-wide overrides stay host-owned ─────────────────────────────────


@pytest.mark.parametrize("key", ["pdf_readers", "ocr_engines"])
def test_a_list_override_is_host_owned(key: str, effective_settings: Any) -> None:
    kind, message = lever_error(key, ["x"]) or (None, "")
    assert kind == "host_owned"
    assert "Read document step" in message

    engine = build_engine(effective_settings())
    data = retrieval_graph()
    data["overrides"] = {key: ["x"]}
    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(data)
    owned = [i for i in caught.value.issues if i.code == IssueCode.HOST_OWNED_SETTING]
    assert owned and owned[0].lever == key
