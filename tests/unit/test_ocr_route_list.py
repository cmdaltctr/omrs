"""The OCR engine list: ordered routes, dispatch and index identity.

Change ordered-reader-and-ocr-lists, tasks 3.1 and 3.2 (design D5, D6). Scenarios
come from ``specs/ocr-worker-engines/spec.md`` and ``specs/maths-page-routing/spec.md``.
Everything external is an in-process fake; no worker process starts.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from omrs.core.ingestion.ocr_identity import more_route_fingerprints, route_fingerprints
from omrs.core.ingestion.source_state import build_index_identity
from omrs.core.reading_lists import engine_list
from omrs.integrations.ocr_worker.client import OcrWorkerError
from omrs.integrations.ocr_worker.dispatch import RoutedClient
from omrs.integrations.ocr_worker.fingerprint import (
    UNAVAILABLE_OCR_WORKER_FINGERPRINT,
    OcrWorkerFingerprint,
)
from omrs.integrations.ocr_worker.managed import RUNTIME_STOPPED_CODE, UNAVAILABLE_CODE
from omrs.integrations.ocr_worker.pool import OcrClientPool
from omrs.integrations.ocr_worker.protocol import make_success
from omrs.integrations.ocr_worker.routes import (
    OcrRoutes,
    build_route_clients,
    engine_names,
    reset_route_log,
)


def _fp(backend_id: str, *, available: bool = True, protocol: str = "1.1") -> Any:
    if not available:
        return UNAVAILABLE_OCR_WORKER_FINGERPRINT
    return OcrWorkerFingerprint(
        available=True,
        protocol_version=protocol,
        packages=(("pkg", "1.0"),),
        pipeline_identity=backend_id,
        pipeline_revision="r1",
        model_identity=f"{backend_id}-m",
        model_revision="m1",
        output_schema_id="s",
        output_schema_version="1",
        backend_id=backend_id,
    )


class _Route:
    """An in-process route client that records requests and can fail or answer empty."""

    def __init__(
        self,
        backend_id: str,
        *,
        available: bool = True,
        leased: bool = False,
        error: str | None = None,
        markdown: str | None = None,
    ) -> None:
        self.fingerprint = _fp(backend_id, available=available)
        self.lease = object() if leased else None
        self.calls = 0
        self._error = error
        self._markdown = markdown if markdown is not None else f"{backend_id} text"
        self.backend_id = backend_id

    def parse(self, pdf_path: str, *, pages: Any = None, timeout: Any = None) -> Any:
        self.calls += 1
        if self._error is not None:
            raise OcrWorkerError(self._error, "fake")
        return make_success("r", self._markdown, ocr_backend=self.backend_id, page_count=1)

    def close(self) -> None:
        pass


# ── Selection (task 3.1) ───────────────────────────────────────────────────


def test_routes_hold_a_tuple_and_expose_the_first_two_entries() -> None:
    a, b, c = _Route("a"), _Route("b"), _Route("c")
    routes = OcrRoutes((a, b, c))

    assert routes.routes == (a, b, c)
    assert routes.primary is a and routes.fallback is b
    assert routes.fingerprint == a.fingerprint
    assert routes.fallback_fingerprint == b.fingerprint
    assert len(routes.fingerprints) == 3


def test_a_list_of_one_reports_the_unavailable_fallback() -> None:
    routes = OcrRoutes((_Route("a"),))

    assert routes.fallback is None
    assert routes.fallback_fingerprint is UNAVAILABLE_OCR_WORKER_FINGERPRINT


def test_first_available_route_serves() -> None:
    a, b, c = _Route("a"), _Route("b"), _Route("c")

    assert OcrRoutes((a, b, c)).select() is a


def test_three_engines_with_only_the_third_available_use_the_third() -> None:
    a, b, c = _Route("a", available=False), _Route("b", available=False), _Route("c")

    assert OcrRoutes((a, b, c)).select() is c


def test_protocol_filter_skips_routes_that_cannot_serve_page_lists() -> None:
    old = _Route("a")
    old.fingerprint = _fp("a", protocol="1.0")
    new = _Route("b")

    assert OcrRoutes((old, _Route("x", available=False), new)).select(protocol="1.1") is new


def test_nothing_available_selects_none() -> None:
    assert OcrRoutes((_Route("a", available=False), None)).select() is None
    assert OcrRoutes().select() is None


# ── An empty or poor answer never moves a request ─────────────────────────


def test_an_empty_answer_never_moves_the_request() -> None:
    """Spec: "An empty answer does not move the request"."""
    first = _Route("a", leased=True, markdown="")
    second = _Route("b", leased=True)
    client = OcrRoutes((first, second)).select()
    assert isinstance(client, RoutedClient)

    result = client.parse("doc.pdf", pages=[1])

    assert result.markdown == ""
    assert (first.calls, second.calls) == (1, 0)
    assert client.fingerprint == first.fingerprint


def test_a_poor_answer_never_moves_the_request() -> None:
    first = _Route("a", leased=True, markdown=" \n ")
    second = _Route("b", leased=True)

    RoutedClient([first, second]).parse("doc.pdf", pages=[1])

    assert second.calls == 0


# ── Walk down the list before dispatch, operator-stop retry once ──────────


def test_unavailable_routes_pass_the_request_down_the_whole_list() -> None:
    a = _Route("a", leased=True, error=UNAVAILABLE_CODE)
    b = _Route("b", leased=True, error=UNAVAILABLE_CODE)
    c = _Route("c", leased=True)
    client = RoutedClient([a, b, c])

    client.parse("doc.pdf")

    assert (a.calls, b.calls, c.calls) == (1, 1, 1)
    assert client.fingerprint == c.fingerprint


def test_operator_stop_goes_once_to_the_next_route() -> None:
    """Spec: "Operator stop during a request"."""
    a = _Route("a", leased=True, error=RUNTIME_STOPPED_CODE)
    b, c = _Route("b", leased=True), _Route("c", leased=True)

    RoutedClient([a, b, c]).parse("doc.pdf")

    assert (a.calls, b.calls, c.calls) == (1, 1, 0)


def test_a_second_operator_stop_is_the_files_error() -> None:
    """Spec: "The operator-stop retry happens once only": a third route is never tried."""
    a = _Route("a", leased=True, error=RUNTIME_STOPPED_CODE)
    b = _Route("b", leased=True, error=RUNTIME_STOPPED_CODE)
    c = _Route("c", leased=True)

    with pytest.raises(OcrWorkerError) as caught:
        RoutedClient([a, b, c]).parse("doc.pdf")

    assert caught.value.code == RUNTIME_STOPPED_CODE
    assert (a.calls, b.calls, c.calls) == (1, 1, 0)


def test_a_crash_after_the_retry_is_not_retried() -> None:
    a = _Route("a", leased=True, error=RUNTIME_STOPPED_CODE)
    b = _Route("b", leased=True, error="worker_crashed")
    c = _Route("c", leased=True)

    with pytest.raises(OcrWorkerError) as caught:
        RoutedClient([a, b, c]).parse("doc.pdf")

    assert caught.value.code == "worker_crashed"
    assert c.calls == 0


def test_a_crash_on_the_first_route_is_never_retried() -> None:
    a = _Route("a", leased=True, error="worker_crashed")
    b = _Route("b", leased=True)

    with pytest.raises(OcrWorkerError):
        RoutedClient([a, b]).parse("doc.pdf")

    assert b.calls == 0


# ── Shared clients and composition ─────────────────────────────────────────


def _engine(root: Path, name: str) -> None:
    python = root / "engines" / name / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")


def _probe_available(command: list[str]) -> Any:
    return _fp(Path(command[0]).parent.parent.parent.name.replace("-", "_"))


@pytest.fixture(autouse=True)
def _fresh_route_log() -> None:
    reset_route_log()


def test_routes_that_resolve_to_one_command_share_one_client(
    tmp_path: Path, effective_settings: Any
) -> None:
    _engine(tmp_path, "dots-mocr")
    _engine(tmp_path, "paddleocr-vl")
    probes: list[list[str]] = []

    def probe(command: list[str]) -> Any:
        probes.append(command)
        return _probe_available(command)

    settings = effective_settings(
        ocr_fallback_enabled=True,
        ocr_workers_dir=str(tmp_path),
        ocr_engines=("dots-mocr", "paddleocr-vl", "dots-mocr"),
    )

    routes = build_route_clients(settings, probe=probe)

    assert len(routes.routes) == 3
    assert routes.routes[0] is routes.routes[2]
    assert routes.routes[0] is not routes.routes[1]
    assert len(probes) == 2


def test_a_list_of_three_builds_three_routes_in_order(
    tmp_path: Path, effective_settings: Any
) -> None:
    for name in ("alpha", "beta", "gamma"):
        _engine(tmp_path, name)
    settings = effective_settings(
        ocr_fallback_enabled=True,
        ocr_workers_dir=str(tmp_path),
        ocr_engines=("alpha", "beta", "gamma"),
    )

    routes = build_route_clients(settings, probe=_probe_available)

    assert [fp.backend_id for fp in routes.fingerprints] == ["alpha", "beta", "gamma"]


def test_only_the_third_engine_provisioned_is_selected(
    tmp_path: Path, effective_settings: Any
) -> None:
    _engine(tmp_path, "gamma")
    settings = effective_settings(
        ocr_fallback_enabled=True,
        ocr_workers_dir=str(tmp_path),
        ocr_engines=("alpha", "beta", "gamma"),
    )

    routes = build_route_clients(settings, probe=_probe_available)

    assert routes.select() is routes.routes[2]


def test_the_start_up_line_names_a_third_engine(
    tmp_path: Path, effective_settings: Any, caplog: pytest.LogCaptureFixture
) -> None:
    _engine(tmp_path, "gamma")
    settings = effective_settings(
        ocr_fallback_enabled=True,
        ocr_workers_dir=str(tmp_path),
        ocr_engines=("alpha", "beta", "gamma"),
    )

    with caplog.at_level(logging.INFO, logger="omrs.integrations.ocr_worker.routes"):
        build_route_clients(settings, probe=_probe_available)

    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("OCR routes:")]
    assert lines == [
        "OCR routes: primary=alpha [unavailable], fallback=beta [unavailable], "
        "engine 3=gamma [available]"
    ]


def test_the_pool_holds_the_whole_list_and_shares_clients(
    tmp_path: Path, effective_settings: Any
) -> None:
    for name in ("alpha", "beta"):
        _engine(tmp_path, name)
    settings = effective_settings(
        ocr_fallback_enabled=True,
        ocr_workers_dir=str(tmp_path),
        ocr_engines=("alpha", "beta", "alpha", "missing"),
    )
    pool = OcrClientPool(probe=_probe_available)
    try:
        routes = pool.routes(settings)
    finally:
        pool.close()

    assert len(routes.routes) == 4
    assert routes.routes[0] is routes.routes[2]
    assert routes.routes[3] is None


def test_engine_names_agrees_with_the_settings_reader(effective_settings: Any) -> None:
    """The leaf copy in ``routes`` must answer as ``core.reading_lists.engine_list`` does."""
    cases = [
        effective_settings(),
        effective_settings(ocr_engines=("a", "b", "c")),
        effective_settings(ocr_engines=(), ocr_engine_primary="p", ocr_engine_fallback=""),
        effective_settings(ocr_engines=(), ocr_engine_primary="p", ocr_engine_fallback="p"),
    ]
    for settings in cases:
        assert engine_names(settings) == engine_list(settings)


# ── Maths pages walk the whole list ────────────────────────────────────────


def test_maths_pages_fall_back_down_the_whole_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    """Spec maths-page-routing: the next available engine serves, in one request."""
    from tests.unit.test_ocr_route_dispatch import (
        _Client,
        _counts,
        _maths,
        _metadata,
        _read,
        _scan,
    )

    monkeypatch.setattr(
        "omrs.integrations.pdf.blank_pages.find_blank_pages", lambda file, pages: frozenset()
    )
    _scan(monkeypatch, 12, needs_ocr=set())
    _maths(monkeypatch, {1, 2, 3, 4})
    first = _Client("dots_mocr", available=False)
    second = _Client("paddleocr_vl", available=False)
    third = _Client("glm_ocr")
    settings = effective_settings(ocr_fallback_enabled=True)

    doc = _read(settings, OcrRoutes((first, second, third)), _metadata(12), tmp_path)

    assert first.calls == [] and second.calls == []
    assert [c["pages"] for c in third.calls] == [[1, 2, 3, 4]]
    assert _counts(doc.metadata)["ocr_pages_worker"] == 4


def test_the_protocol_warning_names_the_position_of_each_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    effective_settings: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from tests.unit.test_ocr_route_dispatch import _Client, _maths, _metadata, _read, _scan

    monkeypatch.setattr(
        "omrs.integrations.pdf.blank_pages.find_blank_pages", lambda file, pages: frozenset()
    )
    _scan(monkeypatch, 6, needs_ocr=set())
    _maths(monkeypatch, {1, 2})
    routes = [_Client("a"), _Client("b"), _Client("c")]
    for client in routes:
        client.fingerprint = SimpleNamespace(
            available=True, protocol_version="1.0", backend_id=client.fingerprint.backend_id
        )

    with caplog.at_level(logging.WARNING):
        _read(
            effective_settings(ocr_fallback_enabled=True),
            OcrRoutes(tuple(routes)),
            _metadata(6),
            tmp_path,
        )

    assert "primary speaks 1.0, fallback speaks 1.0, engine 3 speaks 1.0" in caplog.text


# ── Index identity (task 3.2, design D5) ───────────────────────────────────

#: Digests of the default two-engine install, captured on the tree BEFORE this
#: change (commit a87435a1) with the fingerprints from ``_fp``. They must never move.
PRE_CHANGE_TWO_ENGINE_DIGEST = "a8e0349436fb2658f336e2a3e7219967a6ca926b0c184d95618c57d2c08cab3e"
PRE_CHANGE_ONE_ENGINE_DIGEST = "2f545cfbecc733a5a16455a1f9fa6cf44d982a3863a300cdb01f582c78b99db4"
PRE_CHANGE_SAME_ENGINE_TWICE_DIGEST = (
    "303598d20be19f0ea500c401b41eb28beed1050a1463e8f3d2e038832698ec96"
)

_IDENTITY = {
    "content_type": "application/pdf",
    "chunk_size": 512,
    "chunk_overlap": 100,
    "text_format": "markdown",
    "pdf_reader_revision": 1,
}


def _digest(settings: Any, routes: Any) -> str:
    first, second = route_fingerprints(routes)
    return build_index_identity(
        settings,
        ocr_worker_fingerprint=first,
        ocr_fallback_fingerprint=second,
        ocr_more_fingerprints=more_route_fingerprints(routes),
        **_IDENTITY,
    )


@pytest.fixture
def pdf_settings(effective_settings: Any) -> Any:
    return effective_settings(pdf_reader="pdf_inspector", ocr_fallback_enabled=True)


def test_the_default_two_engine_digest_is_unchanged(pdf_settings: Any) -> None:
    """Spec: "Two-engine install keeps its digest"."""
    routes = OcrRoutes((_Route("dots_mocr"), _Route("paddleocr_vl")))

    assert _digest(pdf_settings, routes) == PRE_CHANGE_TWO_ENGINE_DIGEST


def test_a_list_of_one_gives_the_digest_of_an_empty_fallback(pdf_settings: Any) -> None:
    routes = OcrRoutes((_Route("dots_mocr"),))

    assert _digest(pdf_settings, routes) == PRE_CHANGE_ONE_ENGINE_DIGEST


def test_a_fallback_equal_to_the_primary_keeps_its_digest(pdf_settings: Any) -> None:
    shared = _Route("paddleocr_vl")

    assert _digest(pdf_settings, OcrRoutes((shared, shared))) == PRE_CHANGE_SAME_ENGINE_TWICE_DIGEST


def test_two_or_fewer_engines_add_no_more_fingerprints_member(pdf_settings: Any) -> None:
    assert more_route_fingerprints(OcrRoutes((_Route("a"), _Route("b")))) == ()
    assert more_route_fingerprints(OcrRoutes((_Route("a"),))) == ()
    assert more_route_fingerprints(None) == ()
    assert more_route_fingerprints(_Route("single")) == ()


def test_a_third_engine_changes_the_digest(pdf_settings: Any) -> None:
    """Spec: "Adding a third engine reindexes PDF sources"."""
    two = OcrRoutes((_Route("dots_mocr"), _Route("paddleocr_vl")))
    three = OcrRoutes((_Route("dots_mocr"), _Route("paddleocr_vl"), _Route("glm_ocr")))

    assert _digest(pdf_settings, three) != _digest(pdf_settings, two)


def test_the_third_engine_fingerprint_reaches_the_digest(pdf_settings: Any) -> None:
    base = (_Route("dots_mocr"), _Route("paddleocr_vl"))

    glm = _digest(pdf_settings, OcrRoutes((*base, _Route("glm_ocr"))))
    other = _digest(pdf_settings, OcrRoutes((*base, _Route("other_ocr"))))
    missing = _digest(pdf_settings, OcrRoutes((*base, _Route("glm_ocr", available=False))))

    assert len({glm, other, missing}) == 3


def test_engine_order_beyond_the_second_changes_the_digest(pdf_settings: Any) -> None:
    base = (_Route("dots_mocr"), _Route("paddleocr_vl"))
    ab = OcrRoutes((*base, _Route("c3"), _Route("c4")))
    ba = OcrRoutes((*base, _Route("c4"), _Route("c3")))

    assert _digest(pdf_settings, ab) != _digest(pdf_settings, ba)


def test_more_fingerprints_payload_is_the_canonical_list(
    monkeypatch: pytest.MonkeyPatch, pdf_settings: Any
) -> None:
    """The member is a list of the canonical fingerprint payloads, in list order."""
    from omrs.core.ingestion import source_state
    from omrs.core.ingestion.ocr_identity import ocr_fingerprint_payload

    captured: dict[str, Any] = {}

    class _Spy:
        @staticmethod
        def dumps(payload: Any, **kwargs: Any) -> str:
            captured.update(payload)
            return json.dumps(payload, **kwargs)

    monkeypatch.setattr(source_state, "json", _Spy)
    routes = OcrRoutes((_Route("a"), _Route("b"), _Route("c"), _Route("d", available=False)))

    _digest(pdf_settings, routes)

    assert captured["ocr_more_fingerprints"] == [
        ocr_fingerprint_payload(routes.routes[2].fingerprint),
        ocr_fingerprint_payload(UNAVAILABLE_OCR_WORKER_FINGERPRINT),
    ]
