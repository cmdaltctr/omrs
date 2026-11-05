"""Added pages in the page unit (change document-reading-routers, task 3.2, design D4).

A page rule that declares ``adds_pages`` sends unflagged pages with native text
to the OCR engine list. These tests run the page unit end to end on stubbed
engines with a fake rule at order 45. The pages go to the engine once, a page no
engine reads goes to the rule's degrade hook, ``pages_needing_ocr`` stays the
scan's count, and the five page-source counts still sum to the page count.
"""

from __future__ import annotations

import logging
import sys
from types import SimpleNamespace

import pytest
from llama_index.core import Document

from omrs.integrations.ocr_worker.protocol import make_success
from omrs.integrations.pdf import ocr_routing
from omrs.integrations.pdf.ocr_routing import OcrRoutedPdfInspector
from omrs.integrations.pdf.page_routing import LocalOcrPage
from omrs.integrations.pdf.page_rules import registry
from omrs.integrations.pdf.page_rules.base import RuleContext, RuleOutcome


class _Inner:
    def load_data(self, file, *args, **kwargs) -> list:
        metadata = {"pdf_reader": "pdf_inspector", "page_count": 5, "pages_needing_ocr": 0}
        return [Document(text="whole", metadata=metadata)]


class _Worker:
    def __init__(self, texts: dict[int, str], *, available: bool = True, protocol: str = "1.1"):
        self.fingerprint = SimpleNamespace(
            available=available, protocol_version=protocol, backend_id="paddleocr_vl"
        )
        self.calls: list[list[int]] = []
        self._texts = texts

    def parse(self, pdf_path: str, *, pages=None, timeout=None):
        self.calls.append(list(pages))
        markdown = [self._texts.get(page, "") for page in pages]
        return make_success(
            "req",
            "\n\n".join(markdown),
            ocr_backend="x",
            page_count=len(pages),
            pages_markdown=markdown,
        )


def _scan(monkeypatch, pages: int = 5, flagged: frozenset[int] = frozenset({2})) -> None:
    """*pages* pages numbered from 1; the pages in *flagged* have no text layer."""
    scan = [
        SimpleNamespace(
            page=number - 1,
            markdown="" if number in flagged else f"native {number}",
            needs_ocr=number in flagged,
            ocr_reason=None,
        )
        for number in range(1, pages + 1)
    ]
    stub = SimpleNamespace(extract_pages_markdown=lambda path: SimpleNamespace(pages=scan))
    monkeypatch.setitem(sys.modules, "pdf_inspector", stub)
    monkeypatch.setattr(
        "omrs.integrations.pdf.blank_pages.find_blank_pages", lambda file, pages: frozenset()
    )


class _Rule:
    """A rule that adds fixed pages and, when asked, drops fixed pages."""

    def __init__(self, add=(), drop=()) -> None:
        self.add, self.drop = frozenset(add), frozenset(drop)
        self.seen: list[RuleContext] = []
        self.degraded: list[list[int]] = []

    def run(self, ctx: RuleContext) -> RuleOutcome:
        self.seen.append(ctx)
        return RuleOutcome(add=self.add, drop=self.drop)

    def degrade(self, ctx: RuleContext, outcome: RuleOutcome, unread: list[int]) -> list[int]:
        self.degraded.append(list(unread))
        return list(unread)


@pytest.fixture
def rules():
    """Register an adder at order 45 and a dropper at order 50; restore the registry after."""
    saved = registry.RULES.snapshot()
    made: dict[str, _Rule] = {}

    def install(name: str, rule: _Rule, order: int, **flags: bool) -> _Rule:
        registry.register(name, f"fake.module:{name}", order=order, **flags)
        registry.RULES.cache[name] = rule
        made[name] = rule
        return rule

    yield install
    registry.RULES.restore(saved)


@pytest.fixture
def local_calls(monkeypatch) -> list[list[int]]:
    calls: list[list[int]] = []

    def fake(file, pages, **kwargs):
        calls.append(list(pages))
        return [LocalOcrPage(p, f"LOCAL {p}", 0.95, None, False, ()) for p in pages]

    monkeypatch.setattr(ocr_routing, "local_ocr", fake)
    return calls


def _read(tmp_path, settings, worker) -> list:
    return OcrRoutedPdfInspector(_Inner(), settings=settings, ocr_client=worker).load_data(
        tmp_path / "doc.pdf"
    )


def _settings(effective_settings):
    return effective_settings(ocr_maths_routing_enabled=False, ocr_non_latin_routing="off")


def test_an_added_page_goes_to_the_engine_and_never_to_the_local_tier(
    monkeypatch, tmp_path, effective_settings, local_calls, rules
):
    _scan(monkeypatch)
    rules("adder", _Rule(add={3}), 45, adds_pages=True)
    worker = _Worker({3: "WORKER 3", 2: "WORKER 2"})

    docs = _read(tmp_path, _settings(effective_settings), worker)

    assert local_calls == [[2]], "the flagged page reads locally, the added page does not"
    assert worker.calls == [[3]]
    assert [doc.text for doc in docs] == ["native 1", "LOCAL 2", "WORKER 3", "native 4", "native 5"]
    assert docs[0].metadata["ocr_pages_worker"] == 1


def test_pages_needing_ocr_stays_the_scan_count_and_ocr_is_required(
    monkeypatch, tmp_path, effective_settings, local_calls, rules
):
    _scan(monkeypatch, flagged=frozenset())
    rules("adder", _Rule(add={3}), 45, adds_pages=True)
    worker = _Worker({3: "WORKER 3"})

    docs = _read(tmp_path, _settings(effective_settings), worker)

    metadata = docs[0].metadata
    assert metadata["pages_needing_ocr"] == 0, "the scan flagged no page"
    assert metadata["ocr_required"] is True
    assert metadata["ocr_used"] is True
    assert local_calls == []
    counts = [metadata[k] for k in metadata if k.startswith("ocr_pages_")]
    assert sum(counts) == metadata["page_count"] == 5


def test_a_page_no_engine_reads_goes_to_the_degrade_hook_and_the_local_tier(
    monkeypatch, tmp_path, effective_settings, local_calls, rules
):
    _scan(monkeypatch, flagged=frozenset())
    rule = rules("adder", _Rule(add={3}), 45, adds_pages=True, has_degrade=True)

    docs = _read(tmp_path, _settings(effective_settings), _Worker({}, available=False))

    assert rule.degraded == [[3]]
    assert local_calls == [[3]]
    assert docs[2].text == "LOCAL 3"
    assert docs[0].metadata["ocr_pages_local"] == 1


def test_with_no_tier_the_added_page_keeps_native_text_and_counts_unresolved(
    monkeypatch, tmp_path, effective_settings, local_calls, rules
):
    _scan(monkeypatch, flagged=frozenset())
    rules("adder", _Rule(add={3}), 45, adds_pages=True, has_degrade=True)
    monkeypatch.setattr(ocr_routing, "local_tier_off_reason", lambda settings: "off")

    docs = _read(tmp_path, _settings(effective_settings), _Worker({}, available=False))

    assert local_calls == []
    assert docs[2].text == "native 3"
    assert docs[0].metadata["ocr_pages_unresolved"] == 1
    assert docs[0].metadata["pages_needing_ocr"] == 0


def test_a_protocol_1_0_worker_leaves_added_pages_unresolved_with_a_warning(
    monkeypatch, tmp_path, effective_settings, local_calls, rules, caplog
):
    _scan(monkeypatch, flagged=frozenset())
    rules("adder", _Rule(add={3}), 45, adds_pages=True)
    worker = _Worker({3: "WORKER 3"}, protocol="1.0")
    monkeypatch.setattr(ocr_routing, "local_tier_off_reason", lambda settings: "off")

    with caplog.at_level(logging.WARNING, logger="omrs.integrations.pdf.ocr_routing"):
        docs = _read(tmp_path, _settings(effective_settings), worker)

    assert worker.calls == []
    assert docs[2].text == "native 3"
    assert docs[0].metadata["ocr_pages_unresolved"] == 1
    assert any("protocol" in record.getMessage() for record in caplog.records)


def test_a_later_drop_keeps_the_page_native_and_does_not_count_it_blank(
    monkeypatch, tmp_path, effective_settings, local_calls, rules
):
    _scan(monkeypatch, flagged=frozenset())
    rules("adder", _Rule(add={3}), 45, adds_pages=True)
    rules("dropper", _Rule(drop={3}), 50, drops_pages=True)
    worker = _Worker({3: "WORKER 3"})

    docs = _read(tmp_path, _settings(effective_settings), worker)

    assert worker.calls == [], "a later drop removes the added page from the engine request"
    assert docs[2].text == "native 3"
    metadata = docs[0].metadata
    assert metadata["ocr_pages_blank"] == 0
    assert metadata["ocr_pages_native"] == 5


def test_one_rejected_page_of_a_thousand_sends_exactly_one_page(
    monkeypatch, tmp_path, effective_settings, local_calls, rules
):
    _scan(monkeypatch, pages=1000, flagged=frozenset())
    rules("adder", _Rule(add={500}), 45, adds_pages=True)
    worker = _Worker({500: "WORKER 500"})

    docs = _read(tmp_path, _settings(effective_settings), worker)

    assert worker.calls == [[500]]
    assert local_calls == []
    assert len(docs) == 1000
    assert docs[499].text == "WORKER 500"


def test_no_adding_rule_changes_nothing(
    monkeypatch, tmp_path, effective_settings, local_calls, rules
):
    _scan(monkeypatch)
    worker = _Worker({})

    docs = _read(tmp_path, _settings(effective_settings), worker)

    assert worker.calls == []
    assert local_calls == [[2]]
    assert [doc.text for doc in docs] == ["native 1", "LOCAL 2", "native 3", "native 4", "native 5"]


def test_the_judge_on_the_routes_reaches_the_rule_context(
    monkeypatch, tmp_path, effective_settings, local_calls, rules
):
    from omrs.integrations.ocr_worker.routes import OcrRoutes

    _scan(monkeypatch)
    rule = rules("adder", _Rule(), 45, adds_pages=True)
    # A judge that cannot run: the built-in router reads only its status.
    judge = SimpleNamespace(status="unreachable")
    routes = OcrRoutes(routes=(_Worker({}),), judge=judge)

    _read(tmp_path, _settings(effective_settings), routes)

    assert rule.seen[0].judge is judge


def test_routes_without_a_judge_give_the_rule_none(
    monkeypatch, tmp_path, effective_settings, local_calls, rules
):
    _scan(monkeypatch)
    rule = rules("adder", _Rule(), 45, adds_pages=True)

    _read(tmp_path, _settings(effective_settings), _Worker({}))

    assert rule.seen[0].judge is None
