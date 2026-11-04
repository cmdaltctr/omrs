"""Tests for the shared page-reading registry helper.

Spec reading-parts: "Page-reading registries SHALL share one registry
helper". The helper registers lazy parts, describes them, imports on first
use, probes without importing and records a per-process switch-off reason.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from omrs.integrations.part_registry import PartRegistry

_MODULE_SOURCE = """\
from pathlib import Path

Path({log!r}).open("a", encoding="utf-8").write("x")


class Thing:
    \"\"\"A planted part.\"\"\"
"""


@pytest.fixture()
def planted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[[str], tuple[str, Path]]]:
    """Write a throw-away module on ``sys.path`` that logs each import.

    Returns a factory ``plant(name) -> (import_path, log_file)``. The log
    file gains one character each time the module body runs.
    """
    monkeypatch.syspath_prepend(str(tmp_path))
    planted_names: list[str] = []

    def plant(name: str) -> tuple[str, Path]:
        log = tmp_path / f"{name}.log"
        (tmp_path / f"{name}.py").write_text(_MODULE_SOURCE.format(log=str(log)), encoding="utf-8")
        planted_names.append(name)
        return f"{name}:Thing", log

    yield plant
    for name in planted_names:
        sys.modules.pop(name, None)


def _registry() -> PartRegistry:
    return PartRegistry("PDF reader")


def test_register_describe_and_names() -> None:
    reg = _registry()
    reg.register("b", "pkg.mod_b:Cls", text_format="plain", output_revision=2)
    reg.register("a", "pkg.mod_a:Cls", probe_module="dep_a")

    assert reg.names() == ["a", "b"]
    assert reg.describe("a") == {
        "import_path": "pkg.mod_a:Cls",
        "probe_module": "dep_a",
    }
    assert reg.describe("b") == {
        "import_path": "pkg.mod_b:Cls",
        "probe_module": "pkg.mod_b",
        "text_format": "plain",
        "output_revision": 2,
    }


def test_describe_returns_a_fresh_copy() -> None:
    reg = _registry()
    reg.register("a", "pkg.mod_a:Cls", cut=0.5)

    first = reg.describe("a")
    first["cut"] = 99
    first["extra"] = True

    assert reg.describe("a")["cut"] == 0.5
    assert "extra" not in reg.describe("a")


def test_get_imports_once_and_returns_cached_object(planted) -> None:
    path, log = planted("prt_once")
    reg = _registry()
    reg.register("thing", path)

    first = reg.get("thing")
    second = reg.get("thing")

    assert first is second
    assert first.__name__ == "Thing"
    assert log.read_text(encoding="utf-8") == "x"
    assert reg.cache == {"thing": first}


def test_get_serves_the_cache_not_the_module_attribute(planted) -> None:
    """A cached part stays put even when the module attribute changes.

    Python's own ``sys.modules`` cache hides a missing registry cache when
    only the import count is checked, so this test swaps the attribute.
    """
    path, _ = planted("prt_attr")
    reg = _registry()
    reg.register("thing", path)
    first = reg.get("thing")

    sys.modules["prt_attr"].Thing = object()

    assert reg.get("thing") is first


def test_reregister_replaces_entry_and_drops_cached_object(planted) -> None:
    path_one, _ = planted("prt_one")
    path_two, _ = planted("prt_two")
    reg = _registry()
    reg.register("thing", path_one, cut=1)
    first = reg.get("thing")

    reg.register("thing", path_two, cut=2)

    assert "thing" not in reg.cache
    assert reg.describe("thing")["cut"] == 2
    second = reg.get("thing")
    assert second is not first
    assert second.__module__ == "prt_two"


@pytest.mark.parametrize("method", ["describe", "get", "probe", "installed"])
def test_unknown_name_raises_key_error_with_available_names(method: str) -> None:
    reg = _registry()
    reg.register("pypdf", "pypdf:Cls")
    reg.register("alpha", "alpha:Cls")

    with pytest.raises(KeyError) as excinfo:
        getattr(reg, method)("nope")

    assert excinfo.value.args[0] == ("Unknown PDF reader 'nope'. Available: ['alpha', 'pypdf']")


def test_switch_off_unknown_name_raises_key_error() -> None:
    reg = _registry()

    with pytest.raises(KeyError, match="Unknown PDF reader 'nope'. Available: \\[\\]"):
        reg.switch_off("nope", "reason")


def test_get_import_failure_message_is_chained() -> None:
    reg = _registry()
    reg.register("ghost", "prt_missing_module_xyz:Cls")

    with pytest.raises(ImportError) as excinfo:
        reg.get("ghost")

    message = str(excinfo.value)
    assert message.startswith(
        "PDF reader 'ghost' could not be imported (module 'prt_missing_module_xyz'): "
    )
    assert "prt_missing_module_xyz" in message.split("): ", 1)[1]
    assert isinstance(excinfo.value.__cause__, ImportError)
    assert "ghost" not in reg.cache


def test_probe_succeeds_and_failure_message_is_chained() -> None:
    reg = _registry()
    reg.register("ok", "pkg.mod:Cls", probe_module="json")
    reg.register("bad", "pkg.mod:Cls", probe_module="prt_absent_dependency")

    reg.probe("ok")
    with pytest.raises(ImportError) as excinfo:
        reg.probe("bad")

    assert str(excinfo.value).startswith(
        "PDF reader 'bad' dependency 'prt_absent_dependency' is not importable: "
    )
    assert isinstance(excinfo.value.__cause__, ImportError)


def test_probe_defaults_to_the_module_part_of_the_import_path(planted) -> None:
    path, log = planted("prt_probe_default")
    reg = _registry()
    reg.register("thing", path)

    reg.probe("thing")

    assert reg.describe("thing")["probe_module"] == "prt_probe_default"
    assert log.read_text(encoding="utf-8") == "x"


def test_installed_does_not_import_the_module(planted) -> None:
    path, log = planted("prt_installed")
    reg = _registry()
    reg.register("thing", path)

    assert reg.installed("thing") is True

    assert "prt_installed" not in sys.modules
    assert not log.exists()


def test_installed_is_false_for_a_missing_module() -> None:
    reg = _registry()
    reg.register("ghost", "prt_missing_module_xyz:Cls")
    reg.register("deep", "x:Cls", probe_module="prt_missing_parent.child")

    assert reg.installed("ghost") is False
    assert reg.installed("deep") is False


def test_switch_off_off_reason_and_reset_off() -> None:
    reg = _registry()
    reg.register("a", "pkg.a:Cls")
    reg.register("b", "pkg.b:Cls")
    assert reg.off_reason("a") is None

    reg.switch_off("a", "PanicException: lock poisoned")
    reg.switch_off("b", "second")

    assert reg.off_reason("a") == "PanicException: lock poisoned"
    assert reg.off_reason("b") == "second"
    reg.reset_off()
    assert reg.off_reason("a") is None
    assert reg.off_reason("b") is None


def test_snapshot_and_restore_round_trip(planted) -> None:
    path, _ = planted("prt_snap")
    reg = _registry()
    reg.register("keep", path, cut=1)
    reg.get("keep")
    reg.switch_off("keep", "before")
    live_cache = reg.cache
    state = reg.snapshot()

    reg.register("keep", "other:Cls", cut=2)
    reg.register("planted", "other:Cls")
    reg.switch_off("planted", "after")
    reg.reset_off()
    describe_after = reg.describe("keep")
    assert describe_after["cut"] == 2

    reg.restore(state)

    assert reg.names() == ["keep"]
    assert reg.describe("keep")["cut"] == 1
    assert reg.off_reason("keep") == "before"
    assert reg.cache is live_cache
    assert set(reg.cache) == {"keep"}


def test_snapshot_is_isolated_from_later_changes() -> None:
    reg = _registry()
    reg.register("a", "pkg.a:Cls", cut=1)
    state = reg.snapshot()

    reg.register("a", "pkg.a:Cls", cut=5)
    reg.restore(state)
    reg.register("a", "pkg.a:Cls", cut=9)
    reg.restore(state)

    assert reg.describe("a")["cut"] == 1


def test_cache_property_returns_the_same_live_dict(planted) -> None:
    path, _ = planted("prt_cache")
    reg = _registry()
    reg.register("thing", path)
    cache = reg.cache

    reg.get("thing")
    assert reg.cache is cache
    assert "thing" in cache

    cache.clear()
    assert reg.get("thing").__name__ == "Thing"
    assert "thing" in reg.cache


def test_module_has_no_omrs_or_third_party_module_level_imports() -> None:
    import omrs.integrations.part_registry as module

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import found"
            imported.add((node.module or "").split(".")[0])

    assert "omrs" not in imported
    assert imported <= set(sys.stdlib_module_names)


def test_public_names_match_the_contract() -> None:
    """The public names stay exactly as later groups code against them."""
    expected = (
        "register describe names get probe installed switch_off off_reason "
        "snapshot restore reset_off cache"
    ).split()

    for name in expected:
        assert hasattr(PartRegistry, name), name
