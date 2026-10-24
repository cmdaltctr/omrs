"""What an uninstall removes, when a setting blocks it, and its reasons (task 2.1, D1, D2).

Every test passes its own requirement lines, installed packages and settings.
No test reads the real ``~/.config/omrs`` or runs ``uv``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from omrs.config.settings_file import check_setting
from omrs.core.settings import EffectiveSettings
from omrs.transports.api.install_environment import InstallEnvironment, is_base_extra
from omrs.transports.api.integrations_catalogue import CATALOGUE
from omrs.transports.api.uninstall_plan import (
    IN_USE,
    in_use_setting,
    installed_requirements,
    lasting_uninstall_command,
    packages_to_remove,
    saved_settings,
    uninstall_reason,
)

REQUIRES = [
    "lancedb>=0.20",
    "pdf-inspector>=1.17.0",
    'chromadb>=1.0.0; extra == "chroma"',
    'llama-index-vector-stores-chroma>=0.5.0; extra == "chroma"',
    'rank-bm25>=0.2.2; extra == "hybrid"',
    'pdf-inspector>=1.17.0; extra == "pdf-inspector"',
    'shared-lib>=1; extra == "alpha"',
    'alpha-only>=1; extra == "alpha"',
    'shared-lib>=1; extra == "beta"',
    'beta-only>=1; extra == "beta"',
]


def installed(*names: str, **requires: set[str]) -> dict[str, frozenset[str]]:
    """Return an installed map: each name requires nothing unless listed in *requires*."""
    found = {name: frozenset() for name in ("omrs", "lancedb", "pdf-inspector", *names)}
    found.update({name.replace("_", "-"): frozenset(value) for name, value in requires.items()})
    return found


# ── D1: packages to remove ───────────────────────────────────────────────


def test_only_installed_requirements_are_listed() -> None:
    removes, keeps = packages_to_remove("chroma", installed("chromadb"), REQUIRES)
    assert (removes, keeps) == (["chromadb"], [])


def test_every_installed_unshared_requirement_is_removed() -> None:
    found = installed("chromadb", "llama-index-vector-stores-chroma")
    assert packages_to_remove("chroma", found, REQUIRES) == (
        ["chromadb", "llama-index-vector-stores-chroma"],
        [],
    )


def test_a_base_requirement_is_kept() -> None:
    assert packages_to_remove("pdf-inspector", installed(), REQUIRES) == ([], ["pdf-inspector"])


def test_a_package_another_installed_extra_lists_is_kept() -> None:
    found = installed("shared-lib", "alpha-only", "beta-only")
    assert packages_to_remove("alpha", found, REQUIRES) == (["alpha-only"], ["shared-lib"])


def test_a_package_of_an_extra_that_is_not_installed_is_removed() -> None:
    found = installed("shared-lib", "alpha-only")
    assert packages_to_remove("alpha", found, REQUIRES) == (["shared-lib", "alpha-only"], [])


def test_a_package_another_installed_distribution_requires_is_kept() -> None:
    found = installed("chromadb", "llama-index-vector-stores-chroma", other_tool={"chromadb"})
    removes, keeps = packages_to_remove("chroma", found, REQUIRES)
    assert removes == ["llama-index-vector-stores-chroma"] and keeps == ["chromadb"]


def test_a_package_required_only_by_a_removed_package_is_still_kept() -> None:
    # Conservative: the requirer is removed too, but its edge still counts.
    found = installed("chromadb", llama_index_vector_stores_chroma={"chromadb"})
    assert packages_to_remove("chroma", found, REQUIRES) == (
        ["llama-index-vector-stores-chroma"],
        ["chromadb"],
    )


def test_omrs_itself_never_keeps_a_package() -> None:
    found = installed("rank-bm25")
    found["omrs"] = frozenset({"rank-bm25"})
    assert packages_to_remove("hybrid", found, REQUIRES) == (["rank-bm25"], [])


def test_an_unknown_extra_removes_nothing() -> None:
    assert packages_to_remove("no-such", installed("chromadb"), REQUIRES) == ([], [])


class FakeDistribution:
    """Just the two attributes ``installed_requirements`` reads."""

    def __init__(self, name: str | None, requires: list[str] | None) -> None:
        self.metadata = {"Name": name}
        self.requires = requires


def test_the_installed_map_reads_names_without_markers() -> None:
    found = installed_requirements(
        [
            FakeDistribution("LanceDB", ["Sentence_Transformers>=2.2.0 ; extra == 'embeddings'"]),
            FakeDistribution("rank_bm25", None),
            FakeDistribution(None, ["ignored"]),
        ]
    )
    assert found == {"lancedb": frozenset({"sentence-transformers"}), "rank-bm25": frozenset()}


def test_a_marker_edge_keeps_the_package() -> None:
    lines = [*REQUIRES, 'sentence-transformers>=5; extra == "torch"']
    found = installed_requirements(
        [
            FakeDistribution("omrs", lines),
            FakeDistribution("lancedb", ["sentence-transformers>=2 ; extra == 'embeddings'"]),
            FakeDistribution("sentence-transformers", []),
        ]
    )
    assert packages_to_remove("torch", found, lines) == ([], ["sentence-transformers"])


# ── D2: the in-use map ───────────────────────────────────────────────────


def test_every_non_base_catalogue_extra_has_an_in_use_entry() -> None:
    missing = [
        item.extra
        for item in CATALOGUE
        if item.extra is not None and item.extra != "web" and not is_base_extra(item.extra)
    ]
    assert missing, "the catalogue should have non-base extras"
    assert [extra for extra in missing if extra not in IN_USE] == []


@pytest.mark.parametrize(
    ("path", "value"), [row for rows in IN_USE.values() for row in rows], ids=str
)
def test_each_in_use_row_names_a_real_setting_and_value(path: str, value: str) -> None:
    _, rule = check_setting(path, value)
    assert rule is None, (path, rule)
    block, _, leaf = path.rpartition(".")
    owner = getattr(EffectiveSettings(), block) if block else EffectiveSettings()
    assert leaf in type(owner).model_fields, path


def _settings(path: str, value: str) -> EffectiveSettings:
    block, _, leaf = path.rpartition(".")
    data: dict[str, Any] = {block: {leaf: value}} if block else {leaf: value}
    return EffectiveSettings.model_validate(data)


ROWS = [
    ("chroma", "vector_store", "chroma"),
    ("torch", "retrieval.rerank_backend", "torch"),
    ("pdf-pypdfium2", "pdf_reader", "pypdfium2"),
    ("azure", "document_backend", "azure"),
    ("community-leiden", "community_algorithm", "leiden"),
    ("anthropic", "answer.provider", "anthropic"),
    ("anthropic", "answer.verify_provider", "anthropic"),
]


@pytest.mark.parametrize(("extra", "path", "value"), ROWS)
def test_an_effective_setting_blocks_its_extra(extra: str, path: str, value: str) -> None:
    assert in_use_setting(extra, _settings(path, value), {}) == path
    assert in_use_setting(extra, EffectiveSettings(), {}) is None


@pytest.mark.parametrize(("extra", "path", "value"), ROWS)
def test_a_saved_setting_blocks_its_extra(extra: str, path: str, value: str) -> None:
    assert in_use_setting(extra, EffectiveSettings(), {path: value}) == path
    assert in_use_setting(extra, None, {path: value}) == path


def test_hybrid_is_never_in_use() -> None:
    assert IN_USE["hybrid"] == ()
    everything = {path: value for _, path, value in ROWS}
    assert in_use_setting("hybrid", EffectiveSettings(), everything) is None


def test_the_first_matching_key_is_named() -> None:
    both = {"answer.provider": "anthropic", "answer.verify_provider": "anthropic"}
    assert in_use_setting("anthropic", None, both) == "answer.provider"
    saved = {"answer.verify_provider": "anthropic"}
    assert in_use_setting("anthropic", EffectiveSettings(), saved) == "answer.verify_provider"


def test_the_default_verify_provider_is_not_anthropic() -> None:
    # ``cloud`` resolves to ``cloud_backend``, which accepts only ``openrouter``.
    assert EffectiveSettings().answer.verify_provider == "cloud"
    assert check_setting("cloud_backend", "anthropic")[1] is not None


def test_saved_settings_read_the_isolated_config_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    folder = Path(os.environ["OMRS_CONFIG_DIR"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "omrs.jsonc").write_text(
        '{\n  // saved\n  "vector_store": "chroma",\n'
        '  "retrieval": {"rerank_backend": "torch"}\n}\n',
        encoding="utf-8",
    )
    saved = saved_settings()
    assert saved["vector_store"] == "chroma"
    assert saved["retrieval.rerank_backend"] == "torch"


# ── Reasons and the lasting command ──────────────────────────────────────

UV = InstallEnvironment("uv-tool", ("web", "hybrid"), "~/src/omrs", uv="/bin/uv")


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"base": True}, "not-uninstallable-here"),
        ({"extra": "web"}, "not-uninstallable-here"),
        ({"extra": None}, "not-uninstallable-here"),
        ({"base": True, "availability": "not-installed"}, "not-uninstallable-here"),
        ({"availability": "not-installed"}, "not-installed"),
        ({"availability": "unknown"}, "not-installed"),
        ({"availability": "restart-needed", "setting": "vector_store"}, "not-installed"),
        ({"availability": "not-installed", "removes": []}, "not-installed"),
        ({"removes": []}, "nothing-to-remove"),
        ({"removes": [], "setting": "vector_store"}, "nothing-to-remove"),
        ({"setting": "vector_store", "environment": InstallEnvironment("other")}, "in-use"),
        ({"environment": InstallEnvironment("checkout", uv="/bin/uv")}, "not-uv-tool"),
        ({"environment": InstallEnvironment("uv-tool"), "running": True}, "uv-not-found"),
        ({"running": True}, "install-running"),
        ({}, None),
    ],
)
def test_uninstall_reasons_run_in_the_contract_order(kwargs: dict[str, Any], reason: str) -> None:
    args: dict[str, Any] = {
        "extra": "chroma",
        "base": False,
        "availability": "available",
        "removes": ["chromadb"],
        "setting": None,
        "environment": UV,
        "running": False,
    }
    args.update(kwargs)
    assert uninstall_reason(**args) == reason


def test_the_lasting_command_drops_the_extra_from_the_receipt() -> None:
    assert lasting_uninstall_command(UV, "hybrid", base=False) == (
        'uv tool install --reinstall "omrs[web] @ ~/src/omrs"'
    )


def test_the_lasting_command_keeps_editable_and_skips_an_unknown_source() -> None:
    editable = InstallEnvironment("uv-tool", ("hybrid", "web"), "~/src/omrs", True, "/bin/uv")
    assert lasting_uninstall_command(editable, "hybrid", base=False) == (
        'uv tool install --reinstall --editable "omrs[web] @ ~/src/omrs"'
    )
    index = InstallEnvironment("uv-tool", ("hybrid", "chroma"))
    assert lasting_uninstall_command(index, "chroma", base=False) == (
        'uv tool install --reinstall "omrs[hybrid]"'
    )


def test_the_lasting_command_has_no_brackets_when_no_extra_remains() -> None:
    only = InstallEnvironment("uv-tool", ("hybrid",), "~/src/omrs")
    assert lasting_uninstall_command(only, "hybrid", base=False) == (
        'uv tool install --reinstall "omrs @ ~/src/omrs"'
    )


@pytest.mark.parametrize(
    ("environment", "extra", "base"),
    [
        (UV, "chroma", False),
        (UV, "web", False),
        (InstallEnvironment("uv-tool", ("web", "pdf-inspector")), "pdf-inspector", True),
        (InstallEnvironment("checkout", ("hybrid",)), "hybrid", False),
        (InstallEnvironment("other"), "hybrid", False),
    ],
)
def test_no_lasting_command_outside_the_receipt_or_for_base_and_web(
    environment: InstallEnvironment, extra: str, base: bool
) -> None:
    assert lasting_uninstall_command(environment, extra, base=base) is None
