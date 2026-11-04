"""The three built-in page rules (change local-ocr-backends, tasks 3.2 to 3.4, design D6).

Each rule calls its detector through the detector's module at call time, so
these tests patch the detector where it is defined (design D17, gotcha 8b).
The last tests run the page unit end to end on stubbed engines: a fake rule
with order 40 runs after ``non_latin``, and maths claims a page first.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from llama_index.core import Document

from omrs.integrations.ocr_worker.protocol import make_success
from omrs.integrations.pdf.ocr_routing import OcrRoutedPdfInspector
from omrs.integrations.pdf.page_routing import LocalOcrPage
from omrs.integrations.pdf.page_rules import blank, maths, non_latin, registry
from omrs.integrations.pdf.page_rules.base import RuleContext, RuleOutcome
from omrs.integrations.pdf.script_routing import NON_LATIN_OUTPUT_REASON, PAGES_NON_LATIN_KEY

FILE = Path("doc.pdf")
DEVANAGARI = "क" * 400


class _Routes:
    """``OcrRoutes`` stand-in: ``select`` answers whether an engine is available."""

    def __init__(self, available: bool) -> None:
        self._available = available

    def select(self, *, protocol: str) -> Any:
        return object() if self._available else None


def _ctx(settings: Any, *, flagged=(1, 2, 3), routed=None, routes=None) -> RuleContext:
    return RuleContext(
        file=FILE,
        evidence=[],
        flagged=frozenset(flagged),
        routed=frozenset(flagged if routed is None else routed),
        settings=settings,
        routes=routes if routes is not None else _Routes(True),
    )


# ── Registration (task 3.5) ───────────────────────────────────────────────


def test_the_built_in_rules_run_as_blank_maths_non_latin():
    assert [(name, facts["order"]) for name, facts in registry.ordered()] == [
        ("blank", 10),
        ("maths", 20),
        ("non_latin", 30),
    ]


#: Modules and names the page unit must not import: it runs the rules only
#: through the pipeline (spec page-routing-rules, "No hand-wired rule").
_RULE_MODULES = {"blank", "maths", "non_latin", "blank_pages", "maths_routing", "script_routing"}
_RULE_NAMES = {
    "find_blank_pages",
    "detect_maths_pages",
    "split_page_routes",
    "stamp_maths_count",
    "non_latin_direct_pages",
    "post_check_enabled",
    "stamp_non_latin_count",
}


def test_the_page_unit_imports_no_rule_module_and_no_rule_name():
    import ast

    from omrs.integrations.pdf import ocr_routing

    tree = ast.parse(Path(ocr_routing.__file__).read_text(encoding="utf-8"))
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
            names: list[str] = []
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
            names = [alias.name for alias in node.names]
        else:
            continue
        for module in modules:
            if set(module.split(".")) & _RULE_MODULES:
                problems.append(f"module {module}")
        problems += [f"name {name}" for name in names if name in _RULE_NAMES | _RULE_MODULES]
    assert problems == []
    assert not hasattr(OcrRoutedPdfInspector, "_local_fallback")


def test_each_registration_loads_the_rule_object_of_its_module():
    assert registry.RULES.get("blank") is blank.RULE
    assert registry.RULES.get("maths") is maths.RULE
    assert registry.RULES.get("non_latin") is non_latin.RULE


# ── blank (task 3.2) ──────────────────────────────────────────────────────


def test_blank_drops_what_the_blank_test_finds_on_the_routed_pages(monkeypatch, effective_settings):
    calls: list[tuple[Any, list[int]]] = []

    def fake(file, pages):
        calls.append((file, list(pages)))
        return frozenset({3})

    monkeypatch.setattr("omrs.integrations.pdf.blank_pages.find_blank_pages", fake)

    outcome = blank.RULE.run(_ctx(effective_settings(), flagged=(3, 1, 2)))

    assert calls == [(FILE, [1, 2, 3])]
    assert outcome.drop == {3}
    assert outcome.direct == frozenset()


def test_blank_runs_no_test_when_no_page_is_routed(monkeypatch, effective_settings):
    def fake(file, pages):
        raise AssertionError("the blank test must not run without a routed page")

    monkeypatch.setattr("omrs.integrations.pdf.blank_pages.find_blank_pages", fake)

    assert blank.RULE.run(_ctx(effective_settings(), flagged=())).drop == frozenset()


# ── maths (task 3.3) ──────────────────────────────────────────────────────


def test_maths_sends_every_detected_page_direct(monkeypatch, effective_settings):
    settings = effective_settings(ocr_maths_routing_enabled=True)
    seen: list[Any] = []

    def fake(file, given):
        seen.append((file, given))
        return frozenset({2, 7})

    monkeypatch.setattr("omrs.integrations.pdf.maths_routing.detect_maths_pages", fake)

    outcome = maths.RULE.run(_ctx(settings, flagged=(1,)))

    assert seen == [(FILE, settings)]
    # Maths detects on every page, flagged or not (design D5 semantic 2).
    assert outcome.direct == {2, 7}
    assert outcome.drop == frozenset()


def test_maths_stamps_the_detected_count_including_dropped_pages(monkeypatch, effective_settings):
    monkeypatch.setattr(
        "omrs.integrations.pdf.maths_routing.detect_maths_pages",
        lambda file, settings: frozenset({2, 7}),
    )
    ctx = _ctx(effective_settings(ocr_maths_routing_enabled=True))
    metadata: dict = {}

    maths.RULE.stamp(metadata, ctx, maths.RULE.run(ctx), ())

    assert metadata == {"pages_maths_font": 2}


def test_maths_off_sends_nothing_and_stamps_nothing(monkeypatch, effective_settings):
    monkeypatch.setattr(
        "omrs.integrations.pdf.maths_routing.detect_maths_pages", lambda file, settings: None
    )
    ctx = _ctx(effective_settings(ocr_maths_routing_enabled=False))
    outcome = maths.RULE.run(ctx)
    metadata: dict = {}

    maths.RULE.stamp(metadata, ctx, outcome, ())

    assert outcome.direct == frozenset()
    assert metadata == {}


# ── non_latin (task 3.4) ──────────────────────────────────────────────────


def test_non_latin_sends_the_detector_pages_direct(monkeypatch, effective_settings):
    settings = effective_settings(ocr_non_latin_routing="always")
    routes = _Routes(True)
    seen: list[Any] = []

    def fake(file, routed, given_settings, given_routes):
        seen.append((file, set(routed), given_settings, given_routes))
        return frozenset({2})

    monkeypatch.setattr("omrs.integrations.pdf.script_routing.non_latin_direct_pages", fake)

    outcome = non_latin.RULE.run(_ctx(settings, flagged=(1, 2, 3), routed=(1, 2), routes=routes))

    assert seen == [(FILE, {1, 2}, settings, routes)]
    assert outcome.direct == {2}


@pytest.mark.parametrize(
    ("mode", "engine", "has_check"),
    [
        ("detect", True, True),
        ("detect", False, False),
        ("always", True, False),
        ("off", True, False),
    ],
)
def test_non_latin_post_check_only_under_detect_with_an_engine(
    effective_settings, mode, engine, has_check
):
    ctx = _ctx(effective_settings(ocr_non_latin_routing=mode), routes=_Routes(engine))

    check = non_latin.RULE.post_check(ctx, RuleOutcome())

    assert (check is not None) is has_check


def test_the_non_latin_post_check_names_its_reason(effective_settings):
    ctx = _ctx(effective_settings(ocr_non_latin_routing="detect"))
    check = non_latin.RULE.post_check(ctx, RuleOutcome())

    assert check(DEVANAGARI, None) == NON_LATIN_OUTPUT_REASON
    assert check("Latin text " * 20, None) is None
    assert check("क" * 10, None) is None


def test_non_latin_degrade_hands_every_unread_page_to_the_local_tier_with_a_warning(
    effective_settings, caplog
):
    ctx = _ctx(effective_settings(ocr_non_latin_routing="always"))

    with caplog.at_level(logging.WARNING):
        pages = non_latin.RULE.degrade(ctx, RuleOutcome(direct=frozenset({1, 2})), [1, 2])

    assert pages == [1, 2]
    assert [r.getMessage() for r in caplog.records] == [
        "No OCR engine read 2 non-Latin page(s) in doc.pdf; they went to the local tier."
    ]


def test_non_latin_stamps_direct_plus_escalated_output(effective_settings):
    ctx = _ctx(effective_settings(ocr_non_latin_routing="detect"))
    outcome = RuleOutcome(direct=frozenset({5}))
    escalated = [
        LocalOcrPage(1, DEVANAGARI, 0.95, None, True, (NON_LATIN_OUTPUT_REASON,)),
        LocalOcrPage(2, "x", 0.2, None, True, ("low_confidence",)),
        None,
    ]
    metadata: dict = {}

    non_latin.RULE.stamp(metadata, ctx, outcome, escalated)

    assert metadata == {PAGES_NON_LATIN_KEY: 2}


def test_non_latin_off_stamps_nothing(effective_settings):
    ctx = _ctx(effective_settings(ocr_non_latin_routing="off"))
    metadata: dict = {}

    non_latin.RULE.stamp(metadata, ctx, RuleOutcome(), [])

    assert metadata == {}


# ── End to end through the page unit (spec page-routing-rules) ────────────


class _Inner:
    def load_data(self, file, *args, **kwargs) -> list:
        metadata = {"pdf_reader": "pdf_inspector", "page_count": 3, "pages_needing_ocr": 2}
        return [Document(text="whole", metadata=metadata)]


class _Worker:
    def __init__(self, texts: dict[int, str], available: bool = True) -> None:
        self.fingerprint = SimpleNamespace(
            available=available, protocol_version="1.1", backend_id="paddleocr_vl"
        )
        self.calls: list[list[int]] = []
        self._texts = texts

    def parse(self, pdf_path: str, *, pages=None, timeout=None):
        self.calls.append(list(pages))
        markdown = [self._texts.get(page, "") for page in pages]
        joined = "\n\n".join(markdown)
        return make_success(
            "req", joined, ocr_backend="x", page_count=len(pages), pages_markdown=markdown
        )


def _scan(monkeypatch) -> None:
    """Three pages: 1 native, 2 and 3 flagged, with no text layer."""
    pages = [
        SimpleNamespace(page=0, markdown="native 1", needs_ocr=False, ocr_reason=None),
        SimpleNamespace(page=1, markdown="", needs_ocr=True, ocr_reason=None),
        SimpleNamespace(page=2, markdown="", needs_ocr=True, ocr_reason=None),
    ]
    stub = SimpleNamespace(extract_pages_markdown=lambda path: SimpleNamespace(pages=pages))
    monkeypatch.setitem(sys.modules, "pdf_inspector", stub)
    monkeypatch.setattr(
        "omrs.integrations.pdf.blank_pages.find_blank_pages", lambda file, pages: frozenset()
    )


@pytest.fixture
def local_calls(monkeypatch) -> list[list[int]]:
    """A local tier that reads every page it gets as ``LOCAL n``."""
    from omrs.integrations.pdf import ocr_routing

    calls: list[list[int]] = []

    def fake(file, pages, **kwargs):
        calls.append(list(pages))
        return [LocalOcrPage(p, f"LOCAL {p}", 0.95, None, False, ()) for p in pages]

    monkeypatch.setattr(ocr_routing, "local_ocr", fake)
    return calls


class _FortyRule:
    """A page rule registered by the test only: it sends page 3 direct."""

    def __init__(self) -> None:
        self.seen: list[RuleContext] = []

    def run(self, ctx: RuleContext) -> RuleOutcome:
        self.seen.append(ctx)
        return RuleOutcome(direct=frozenset({3}))


FORTY = _FortyRule()


@pytest.fixture
def forty_registered():
    from omrs.core.reading_parts import PageRuleDescriptor

    descriptor = PageRuleDescriptor(
        name="forty",
        import_path=f"{__name__}:FORTY",
        label="Forty",
        help_key="page_rule.forty",
        order=40,
        sends_direct=True,
    )
    saved = registry.RULES.snapshot()
    registry.register(
        descriptor.name,
        descriptor.import_path,
        order=descriptor.order,
        sends_direct=descriptor.sends_direct,
    )
    FORTY.seen.clear()
    yield
    registry.RULES.restore(saved)


def test_a_fake_rule_with_order_40_runs_after_non_latin(
    monkeypatch, tmp_path, effective_settings, local_calls, forty_registered
):
    _scan(monkeypatch)
    monkeypatch.setattr(
        "omrs.integrations.pdf.blank_pages.find_blank_pages", lambda file, pages: frozenset({2})
    )
    worker = _Worker({3: "WORKER 3"})

    docs = OcrRoutedPdfInspector(
        _Inner(), settings=effective_settings(ocr_maths_routing_enabled=False), ocr_client=worker
    ).load_data(tmp_path / "doc.pdf")

    assert [name for name, _ in registry.ordered()][-2:] == ["non_latin", "forty"]
    assert FORTY.seen[0].routed == {3}, "the blank rule ran first and dropped page 2"
    assert local_calls == []
    assert worker.calls == [[3]]
    assert [doc.text for doc in docs] == ["native 1", "WORKER 3"]


def test_maths_claims_first_so_the_non_latin_degrade_never_sees_a_maths_page(
    monkeypatch, tmp_path, effective_settings, local_calls
):
    """Maths on, ``always``: page 2 is a maths page, page 3 is not; the engine reads neither."""
    _scan(monkeypatch)
    monkeypatch.setattr(
        "omrs.integrations.pdf.maths_routing.detect_maths_pages",
        lambda file, settings: frozenset({2}),
    )
    degraded: list[list[int]] = []
    original = non_latin.RULE.degrade

    def spy(ctx, outcome, unread):
        degraded.append(list(unread))
        return original(ctx, outcome, unread)

    monkeypatch.setattr(non_latin.RULE, "degrade", spy)
    worker = _Worker({})
    settings = effective_settings(ocr_maths_routing_enabled=True, ocr_non_latin_routing="always")

    docs = OcrRoutedPdfInspector(_Inner(), settings=settings, ocr_client=worker).load_data(
        tmp_path / "doc.pdf"
    )

    assert worker.calls == [[2, 3]], "the maths and non-Latin page go once"
    assert degraded == [[3]]
    assert local_calls == [[3]]
    assert [doc.text for doc in docs] == ["native 1", "LOCAL 3"]
    assert docs[0].metadata["ocr_pages_unresolved"] == 1, "maths page 2 stays unresolved"


def test_maths_claims_first_with_no_engine_at_all(
    monkeypatch, tmp_path, effective_settings, local_calls
):
    _scan(monkeypatch)
    monkeypatch.setattr(
        "omrs.integrations.pdf.maths_routing.detect_maths_pages",
        lambda file, settings: frozenset({2}),
    )
    degraded: list[list[int]] = []
    monkeypatch.setattr(non_latin.RULE, "degrade", lambda ctx, o, unread: degraded.append(unread))
    settings = effective_settings(ocr_maths_routing_enabled=True, ocr_non_latin_routing="always")

    OcrRoutedPdfInspector(_Inner(), settings=settings, ocr_client=_Worker({}, False)).load_data(
        tmp_path / "doc.pdf"
    )

    assert degraded == []
    assert local_calls == [[3]], "with no engine the non-Latin page goes local as before"
