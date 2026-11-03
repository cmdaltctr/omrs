"""The ``pdf_readers`` block of ``GET /v1/integrations``.

Change ordered-reader-and-ocr-lists, task 4.2 (design D8). The builder imports
no web framework. Every probe is faked, and no test installs or starts
anything.
"""

from __future__ import annotations

from typing import Any

import pytest
from tests.unit.test_web_integration_uninstall_profiles import FakeCatalogue, profile

from omrs import capabilities
from omrs.integrations.pdf import registry
from omrs.transports.api import pdf_reader_items as module
from omrs.transports.api.install_environment import CHECKOUT, OTHER, UV_TOOL, InstallEnvironment
from omrs.transports.api.pdf_reader_items import pdf_reader_items

REQUIRES = [
    "pypdf>=6.16.1",
    "liteparse>=2.0.0",
    "pdf-inspector>=1.17.0",
    'pypdfium2>=4.0.0; extra == "pdf-pypdfium2"',
    'pdf-inspector>=1.17.0; extra == "pdf-inspector"',
    'rank-bm25>=0.2.2; extra == "hybrid"',
]
EXTRAS = ["pdf-pypdfium2", "pdf-inspector", "hybrid"]
CHECKOUT_ENV = InstallEnvironment(install_type=CHECKOUT, uv="/bin/uv")


@pytest.fixture(autouse=True)
def packages(monkeypatch: pytest.MonkeyPatch) -> None:
    """The installed ``omrs`` metadata, replaced by a fixed one."""
    monkeypatch.setattr(module, "_metadata", lambda: (REQUIRES, EXTRAS))
    options = {
        "liteparse": None,
        "pdf_inspector": None,
        "pypdf": None,
        "pypdfium2": "The package 'pypdfium2' is not installed.",
    }
    monkeypatch.setattr(capabilities, "pdf_reader_options", lambda: dict(options))


def _items(settings: Any = None, env: InstallEnvironment = CHECKOUT_ENV, catalogue: Any = None):
    return {item["name"]: item for item in pdf_reader_items(settings, env, catalogue)}


def _read_step(params: dict[str, Any], enabled: bool = True) -> dict[str, Any]:
    return {"id": "read", "operation": "read.document", "params": params, "enabled": enabled}


def test_one_item_per_registered_reader_in_registry_order() -> None:
    items = pdf_reader_items(None, CHECKOUT_ENV, None)
    assert [item["name"] for item in items] == ["liteparse", "pdf_inspector", "pypdf", "pypdfium2"]
    assert set(items[0]) == {"name", "installed", "extra", "fix_command", "used_by"}


def test_a_reader_registered_later_appears_with_no_other_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options = capabilities.pdf_reader_options()
    options["docling"] = "The package 'docling' is not installed."
    monkeypatch.setattr(capabilities, "pdf_reader_options", lambda: dict(options))
    real = registry.describe
    monkeypatch.setattr(
        registry,
        "describe",
        lambda name: {"probe_module": name} if name == "docling" else real(name),
    )
    item = _items()["docling"]
    assert item["installed"] is False and item["extra"] is None


def test_installed_follows_the_import_probe() -> None:
    found = {name: item["installed"] for name, item in _items().items()}
    assert found == {"liteparse": True, "pdf_inspector": True, "pypdf": True, "pypdfium2": False}


def test_a_reader_in_an_extra_names_the_extra_and_a_base_reader_names_none() -> None:
    found = {name: item["extra"] for name, item in _items().items()}
    assert found == {
        "liteparse": None,
        "pdf_inspector": None,  # the pdf-inspector extra only keeps an old command working
        "pypdf": None,
        "pypdfium2": "pdf-pypdfium2",
    }


def test_a_missing_reader_in_an_extra_gets_the_extra_command() -> None:
    assert _items()["pypdfium2"]["fix_command"] == "uv sync --extra pdf-pypdfium2"


def test_an_installed_reader_has_no_fix_command() -> None:
    assert _items()["pypdf"]["fix_command"] is None


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        (CHECKOUT_ENV, "uv sync"),
        (InstallEnvironment(install_type=OTHER), 'pip install --force-reinstall "omrs"'),
        (
            InstallEnvironment(install_type=UV_TOOL, receipt_extras=("hybrid",)),
            'uv tool install --reinstall "omrs[hybrid]"',
        ),
    ],
)
def test_a_missing_base_reader_gets_the_base_command(
    env: InstallEnvironment, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    options = {
        **capabilities.pdf_reader_options(),
        "pypdf": "The package 'pypdf' is not installed.",
    }
    monkeypatch.setattr(capabilities, "pdf_reader_options", lambda: dict(options))
    assert _items(env=env)["pypdf"]["fix_command"] == expected


def test_a_missing_metadata_leaves_every_reader_in_the_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "_metadata", lambda: ([], []))
    assert _items()["pypdfium2"]["extra"] is None


def test_the_host_list_gives_one_position_line_per_reader(effective_settings: Any) -> None:
    settings = effective_settings(pdf_readers=("pdf_inspector", "liteparse", "pypdf"))
    found = {name: item["used_by"] for name, item in _items(settings).items()}
    assert found["pdf_inspector"] == ["First in Settings > Document reading"]
    assert found["liteparse"] == ["Second in Settings > Document reading"]
    assert found["pypdf"] == ["Third in Settings > Document reading"]
    assert found["pypdfium2"] == []


def test_a_list_read_from_the_single_value_setting_counts(effective_settings: Any) -> None:
    settings = effective_settings(pdf_reader="pypdf")
    assert _items(settings)["pypdf"]["used_by"] == ["First in Settings > Document reading"]


def test_a_saved_profile_step_adds_a_profile_line_for_each_reader_it_lists() -> None:
    papers = profile("p1", "Papers", _read_step({"pdf_readers": ["pypdfium2", "pypdf"]}))
    found = _items(catalogue=FakeCatalogue(papers))
    assert found["pypdfium2"]["used_by"] == ["Profile Papers"]
    assert found["pypdf"]["used_by"] == ["Profile Papers"]
    assert found["liteparse"]["used_by"] == []


def test_an_old_single_reader_option_counts_as_its_expansion() -> None:
    old = profile("p1", "Old", _read_step({"pdf_reader": "pdf_inspector"}))
    found = _items(catalogue=FakeCatalogue(old))
    assert {n for n, i in found.items() if i["used_by"]} == {"pdf_inspector", "liteparse", "pypdf"}


def test_a_profile_is_named_once_and_after_the_host_line(effective_settings: Any) -> None:
    twice = profile(
        "p1",
        "Twice",
        _read_step({"pdf_readers": ["pypdf"]}),
        {**_read_step({"pdf_readers": ["pypdf"]}), "id": "read2"},
    )
    settings = effective_settings(pdf_readers=("pypdf",))
    used = _items(settings, catalogue=FakeCatalogue(twice))["pypdf"]["used_by"]
    assert used == ["First in Settings > Document reading", "Profile Twice"]


def test_a_disabled_step_and_a_deleted_profile_add_nothing() -> None:
    off = profile("p1", "Off", _read_step({"pdf_readers": ["pypdf"]}, enabled=False))
    gone = {**profile("p2", "Gone", _read_step({"pdf_readers": ["pypdf"]})), "archived_at": "x"}
    found = _items(catalogue=FakeCatalogue(off, gone))
    assert all(item["used_by"] == [] for item in found.values())


def test_an_unreadable_profile_catalogue_leaves_the_host_lines(effective_settings: Any) -> None:
    class Broken:
        def list_profiles(self) -> list[Any]:
            raise RuntimeError("detail /Users/someone")

    settings = effective_settings(pdf_readers=("pypdf",))
    found = _items(settings, catalogue=Broken())
    assert found["pypdf"]["used_by"] == ["First in Settings > Document reading"]


def test_the_block_imports_nothing_that_installs_or_starts_a_process() -> None:
    source = open(module.__file__, encoding="utf-8").read()
    assert "subprocess" not in source and "InstallJob" not in source
    assert registry.available()  # the registry is the only source of reader names
