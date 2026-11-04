"""Fake installed distributions for the reading-part discovery tests (design D11).

No package is installed. :func:`fake_parts_builder` writes ``<name>-<version>.dist-info``
folders (``METADATA`` and ``entry_points.txt``) and plain modules into a
temporary folder on ``sys.path``. ``importlib.metadata`` then finds them like
any installed distribution.

The builder also saves and restores the three page-reading registries, the
discovery cache and the discovered descriptors, so a test leaves no part behind.
"""

from __future__ import annotations

import importlib
import itertools
import sys
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path

import pytest

from omrs.core import reading_parts
from omrs.integrations import part_registry
from omrs.integrations.pdf import registry as reader_registry
from omrs.integrations.pdf.local_ocr import registry as backend_registry
from omrs.integrations.pdf.page_rules import registry as rule_registry

_COUNTER = itertools.count()

#: A good local OCR backend descriptor. ``{impl}`` is the implementation module.
BACKEND_DESCRIPTOR = """\
from omrs.core.reading_parts import LocalOcrBackendDescriptor

BACKEND = LocalOcrBackendDescriptor(
    name="fake-ocr",
    import_path="{impl}:BACKEND",
    label="Fake OCR",
    help_key="local_ocr_backend.fake-ocr",
    producer="fake_ocr",
    min_confidence=0.5,
    calibrated_by="fake-calibration",
)
"""

#: A fake backend implementation that records each call in ``CALLS``.
BACKEND_IMPLEMENTATION = """\
from omrs.integrations.pdf.local_ocr.base import BackendPage

CALLS = []


class _Backend:
    def read_pages(self, file, pages, *, settings):
        CALLS.append(list(pages))
        return [
            BackendPage(page=p, text=f"fake text {p}", confidence=0.99, model="fake@1")
            for p in pages
        ]

    def identity(self, settings):
        return "fake@1"


BACKEND = _Backend()
"""

#: A PDF reader descriptor. ``{name}`` is the reader name.
READER_DESCRIPTOR = """\
from omrs.core.reading_parts import PdfReaderDescriptor

READER = PdfReaderDescriptor(
    name="{name}",
    import_path="{impl}:Reader",
    label="Fake reader",
    help_key="pdf_reader.fake",
    text_format="plain",
    page_provenance=False,
)
"""

#: A page rule descriptor with one identity option and one plain option.
RULE_DESCRIPTOR = """\
from omrs.core.reading_parts import PageRuleDescriptor, SettingField

RULE = PageRuleDescriptor(
    name="stamp-check",
    import_path="{impl}:RULE",
    label="Stamp check",
    help_key="page_rule.stamp-check",
    order=25,
    options=(
        SettingField(name="strictness", env="", default="low", accepted=("low", "high"),
                     enters_identity=True),
        SettingField(name="note", env="", default=""),
        SettingField(name="limit", env="", default=3),
    ),
)
"""

#: A fake page rule that records each run in ``RUNS``.
RULE_IMPLEMENTATION = """\
from omrs.integrations.pdf.page_rules.base import RuleOutcome

RUNS = []


class _Rule:
    def run(self, ctx):
        RUNS.append(sorted(ctx.routed))
        return RuleOutcome()


RULE = _Rule()
"""

Builder = Callable[..., "FakeDistribution"]


class FakeDistribution:
    """One fake distribution: its name and the unique module names it owns."""

    def __init__(self, root: Path, name: str, prefix: str) -> None:
        self.root = root
        self.name = name
        self.prefix = prefix

    def module(self, suffix: str) -> str:
        """Return the unique module name for *suffix*."""
        return f"{self.prefix}_{suffix}"


def _write_distribution(
    root: Path,
    name: str,
    version: str,
    entry_points: Mapping[str, Mapping[str, str]],
) -> None:
    info = root / f"{name}-{version}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n", encoding="utf-8"
    )
    lines: list[str] = []
    for group, entries in entry_points.items():
        lines.append(f"[{group}]")
        lines += [f"{entry} = {value}" for entry, value in entries.items()]
        lines.append("")
    (info / "entry_points.txt").write_text("\n".join(lines), encoding="utf-8")


def fake_parts_builder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Builder]:
    """Yield ``build(name, entry_points, modules, version="1.0")``; wrap it in a fixture.

    *entry_points* maps a group to ``{entry name: "module:attr"}``; the text
    ``{mod:<suffix>}`` in a value or a module source names the unique module
    ``<prefix>_<suffix>``. *modules* maps a suffix to its source.
    """
    root = tmp_path / "site"
    root.mkdir()
    monkeypatch.syspath_prepend(str(root))
    saved = [r.snapshot() for r in (reader_registry.READERS, backend_registry.BACKENDS)]
    saved_rules = rule_registry.RULES.snapshot()
    part_registry.reset_discovery()
    reading_parts.reset_discovered()
    owned: list[str] = []

    def build(
        name: str,
        entry_points: Mapping[str, Mapping[str, str]],
        modules: Mapping[str, str] = {},  # noqa: B006 - read only
        version: str = "1.0",
    ) -> FakeDistribution:
        dist = FakeDistribution(root, name, f"fakepart{next(_COUNTER)}")

        def fill(text: str) -> str:
            for suffix in modules:
                text = text.replace(f"{{mod:{suffix}}}", dist.module(suffix))
            return text

        for suffix, source in modules.items():
            (root / f"{dist.module(suffix)}.py").write_text(fill(source), encoding="utf-8")
            owned.append(dist.module(suffix))
        filled = {
            group: {entry: fill(value) for entry, value in entries.items()}
            for group, entries in entry_points.items()
        }
        _write_distribution(root, name, version, filled)
        importlib.invalidate_caches()
        return dist

    yield build
    reader_registry.READERS.restore(saved[0])
    backend_registry.BACKENDS.restore(saved[1])
    rule_registry.RULES.restore(saved_rules)
    part_registry.reset_discovery()
    reading_parts.reset_discovered()
    for module in owned:
        sys.modules.pop(module, None)
    importlib.invalidate_caches()


def run_discovery() -> tuple[part_registry.DiscoveredPart, ...]:
    """Run discovery the way the composition root does."""
    from omrs.compose_settings import discover_reading_parts

    return discover_reading_parts()


def backend_distribution(build: Builder, name: str = "fakeocr") -> FakeDistribution:
    """Build a distribution with the good ``fake-ocr`` backend."""
    return build(
        name,
        {"omrs.local_ocr_backends": {"fake-ocr": "{mod:desc}:BACKEND"}},
        {
            "desc": BACKEND_DESCRIPTOR.replace("{impl}", "{mod:impl}"),
            "impl": BACKEND_IMPLEMENTATION,
        },
    )


def rule_distribution(build: Builder, name: str = "stampcheck") -> FakeDistribution:
    """Build a distribution with the ``stamp-check`` page rule."""
    return build(
        name,
        {"omrs.page_rules": {"stamp-check": "{mod:desc}:RULE"}},
        {"desc": RULE_DESCRIPTOR.replace("{impl}", "{mod:impl}"), "impl": RULE_IMPLEMENTATION},
    )
