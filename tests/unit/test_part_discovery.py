"""Entry-point discovery of reading parts (change local-ocr-backends, tasks 5.1 and 5.4).

Spec reading-parts: "Installed packages SHALL be able to add reading parts
through entry points" and "A bad external part SHALL never stop start-up".
Every test uses a fake distribution (``test_part_discovery_support``); no
package is installed.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_part_discovery_support import (
    BACKEND_DESCRIPTOR,
    READER_DESCRIPTOR,
    backend_distribution,
    fake_parts_builder,
    rule_distribution,
    run_discovery,
)

from omrs.core import reading_parts
from omrs.integrations import part_registry
from omrs.integrations.pdf import registry as reader_registry
from omrs.integrations.pdf.local_ocr import registry as backend_registry
from omrs.integrations.pdf.page_rules import registry as rule_registry


@pytest.fixture
def fake_parts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Yield the fake-distribution builder of ``test_part_discovery_support``."""
    yield from fake_parts_builder(tmp_path, monkeypatch)


_LOGGER = "omrs.integrations.part_registry"


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


def _ours(found: tuple[part_registry.DiscoveredPart, ...], dist: str) -> list[Any]:
    return [part for part in found if part.distribution == dist]


# ── 5.1: a good part in each group ───────────────────────────────────────


def test_a_good_backend_is_discovered_and_registered(fake_parts) -> None:
    backend_distribution(fake_parts)

    found = run_discovery()

    [part] = _ours(found, "fakeocr")
    assert part.name == "fake-ocr"
    assert part.kind == "local_ocr_backend"
    assert part.group == "omrs.local_ocr_backends"
    assert part.version == "1.0"
    assert part.problem is None
    assert isinstance(part.descriptor, reading_parts.LocalOcrBackendDescriptor)
    assert part.descriptor.source == "fakeocr"
    facts = backend_registry.describe("fake-ocr")
    assert facts["producer"] == "fake_ocr"
    assert facts["min_confidence"] == 0.5
    assert reading_parts.local_backend("fake-ocr") is part.descriptor


def test_a_good_reader_is_discovered_and_registered(fake_parts) -> None:
    fake_parts(
        "fakereader",
        {"omrs.pdf_readers": {"fake-reader": "{mod:desc}:READER"}},
        {"desc": READER_DESCRIPTOR.replace("{name}", "fake-reader").replace("{impl}", "x.y")},
    )

    [part] = _ours(run_discovery(), "fakereader")

    assert (part.name, part.kind, part.problem) == ("fake-reader", "pdf_reader", None)
    assert reader_registry.describe("fake-reader")["text_format"] == "plain"
    assert "fake-reader" in reader_registry.available()


def test_a_good_page_rule_is_discovered_with_its_distribution_as_source(fake_parts) -> None:
    rule_distribution(fake_parts)

    [part] = _ours(run_discovery(), "stampcheck")

    assert (part.name, part.kind, part.problem) == ("stamp-check", "page_rule", None)
    facts = rule_registry.describe("stamp-check")
    assert facts["order"] == 25
    assert facts["source"] == "stampcheck"


# ── 5.1: refusals and failures ──────────────────────────────────────────


def test_a_name_clash_with_a_built_in_is_refused_with_one_warning(fake_parts, caplog) -> None:
    fake_parts(
        "clashing",
        {"omrs.pdf_readers": {"pypdf": "{mod:desc}:READER"}},
        {"desc": READER_DESCRIPTOR.replace("{name}", "pypdf").replace("{impl}", "evil.mod")},
    )
    before = reader_registry.describe("pypdf")

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        [part] = _ours(run_discovery(), "clashing")

    assert part.descriptor is None
    assert "built-in" in part.problem
    assert reader_registry.describe("pypdf") == before
    [warning] = _warnings(caplog)
    assert "clashing" in warning
    assert "'pypdf'" in warning
    assert "built-in" in warning


def test_a_name_taken_by_another_distribution_is_refused_naming_both(fake_parts, caplog) -> None:
    backend_distribution(fake_parts, "firstocr")
    backend_distribution(fake_parts, "secondocr")

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        found = run_discovery()

    accepted = [p for p in found if p.descriptor is not None]
    refused = [p for p in found if p.problem is not None]
    assert len(accepted) == 1
    assert len(refused) == 1
    [warning] = _warnings(caplog)
    assert "firstocr" in warning
    assert "secondocr" in warning


def test_a_descriptor_of_the_wrong_type_is_refused_with_one_warning(fake_parts, caplog) -> None:
    # A backend descriptor in the page-rule group.
    fake_parts(
        "wrongtype",
        {"omrs.page_rules": {"fake-ocr": "{mod:desc}:BACKEND"}},
        {"desc": BACKEND_DESCRIPTOR.replace("{impl}", "x.y")},
    )

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        [part] = _ours(run_discovery(), "wrongtype")

    assert part.descriptor is None
    assert "PageRuleDescriptor" in part.problem
    assert "fake-ocr" not in rule_registry.available()
    assert len(_warnings(caplog)) == 1


def test_a_module_that_raises_import_error_is_listed_broken(fake_parts, caplog) -> None:
    fake_parts(
        "brokenpart",
        {"omrs.local_ocr_backends": {"broken": "{mod:desc}:BACKEND"}},
        {"desc": "raise ImportError('needs the moon package')\n"},
    )
    backend_distribution(fake_parts)

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        found = run_discovery()

    [broken] = _ours(found, "brokenpart")
    # The entry-point name, known before loading (review of PR #168, finding 4).
    assert broken.name == "broken"
    assert broken.broken is True
    assert broken.descriptor is None
    assert "ImportError" in broken.problem
    assert "needs the moon package" in broken.problem
    # Start-up continues: the good part of the other distribution still loads.
    [good] = _ours(found, "fakeocr")
    assert good.problem is None
    [warning] = _warnings(caplog)
    assert "brokenpart" in warning


def test_one_log_line_names_the_discovered_parts(fake_parts, caplog) -> None:
    backend_distribution(fake_parts)
    rule_distribution(fake_parts)

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        run_discovery()

    infos = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert len(infos) == 1
    assert "fake-ocr" in infos[0]
    assert "stamp-check" in infos[0]


def test_nothing_discovered_logs_nothing(fake_parts, caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        assert run_discovery() == ()

    assert caplog.records == []


# ── 5.1: once per process, and never from config ─────────────────────────


def test_discovery_runs_once_per_process(fake_parts, monkeypatch) -> None:
    backend_distribution(fake_parts)
    calls: list[str] = []
    real = part_registry.entry_points

    def spy(*, group: str) -> Any:
        calls.append(group)
        return real(group=group)

    monkeypatch.setattr(part_registry, "entry_points", spy)

    first = run_discovery()
    second = run_discovery()

    assert first is second
    assert sorted(calls) == sorted(part_registry.GROUPS)
    assert part_registry.discovered_parts() is first


def test_discovered_parts_is_empty_before_discovery_and_never_runs_it(
    fake_parts, monkeypatch
) -> None:
    monkeypatch.setattr(part_registry, "entry_points", _forbidden)

    assert part_registry.discovered_parts() == ()


def _forbidden(**_: Any) -> Any:
    raise AssertionError("entry points were read")


def test_get_settings_outside_compose_reads_no_entry_point(fake_parts, monkeypatch) -> None:
    import omrs.config as config

    monkeypatch.setattr(part_registry, "entry_points", _forbidden)
    monkeypatch.setattr(config, "_settings", None)

    config.get_settings()
    config.Settings()

    assert part_registry.discovered_parts() == ()


def test_importing_config_reads_no_entry_point_group(tmp_path: Path) -> None:
    """A fresh process imports ``omrs.config`` and builds settings without compose."""
    script = textwrap.dedent(
        """
        import importlib.metadata as metadata, json, sys
        seen = []
        real = metadata.entry_points
        def spy(*args, **kwargs):
            seen.append(kwargs.get("group"))
            return real(*args, **kwargs)
        metadata.entry_points = spy
        import omrs.config
        omrs.config.get_settings()
        print(json.dumps({
            "groups": [g for g in seen if g and g.startswith("omrs.")],
            "loaded": "omrs.integrations.part_registry" in sys.modules,
        }))
        """
    )
    env = {**os.environ, "OMRS_CONFIG_DIR": str(tmp_path / "config")}
    done = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )

    result = json.loads(done.stdout.strip().splitlines()[-1])
    assert result == {"groups": [], "loaded": False}


# ── 5.4: the descriptor module loads, the implementation does not ────────


def test_discovery_loads_the_descriptor_module_only(fake_parts) -> None:
    dist = backend_distribution(fake_parts)

    run_discovery()

    assert dist.module("desc") in sys.modules
    assert dist.module("impl") not in sys.modules
    backend = backend_registry.BACKENDS.get("fake-ocr")
    assert dist.module("impl") in sys.modules
    assert backend is sys.modules[dist.module("impl")].BACKEND
