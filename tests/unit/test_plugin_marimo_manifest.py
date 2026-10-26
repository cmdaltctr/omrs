"""The separately distributed marimo manifest (task 8.2).

A fake ``marimo`` executable stands in for the real tool. marimo is not
installed, and these tests install nothing.
"""

from __future__ import annotations

import ast
import importlib.resources
import json
import shutil
import subprocess
import tomllib
import zipfile
from pathlib import Path

import pytest
from tests.unit.test_process_launcher_support import make_fake_editor

from omrs.core.plugins import (
    PROJECT_ENVIRONMENT,
    REQUIRED_LAUNCH_CAPABILITIES,
    NotebookEditorSupervisor,
    PluginLaunchError,
    PluginRegistry,
    parse_manifest,
)
from omrs.core.plugins.shipped import empty_notebook_text, shipped_manifests
from omrs.integrations.process_launcher import OwnedProcessLauncher, SubprocessProbeRunner
from omrs.integrations.workspace_sqlite import SqliteWorkspaceRepository

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = ROOT / "plugins" / "marimo"  # README and starter notebook (source only)
SHIPPED_DIR = ROOT / "src" / "omrs" / "core" / "plugins" / "shipped" / "marimo"
MANIFEST = SHIPPED_DIR / "manifest.json"

# Flags confirmed in the marimo CLI reference (docs.marimo.io/cli, via Context7).
CONFIRMED_EDIT_FLAGS = {
    "--headless", "--host", "--port", "--token-password-file", "--skip-update-check",
    "--no-sandbox",
}  # fmt: skip


def test_shipped_manifest_is_valid_and_complete() -> None:
    manifest = parse_manifest(MANIFEST.read_bytes())
    assert manifest.plugin_id == "marimo" and manifest.executable_name == "marimo"
    assert manifest.missing_capabilities == ()
    assert set(REQUIRED_LAUNCH_CAPABILITIES) <= set(manifest.capabilities)
    assert manifest.probe.version_args == ("--version",)
    assert manifest.probe.help_args == ("edit", "--help")
    args = manifest.launch.args
    assert args[:2] == ("edit", "{notebook_path}")
    flags = {arg for arg in args if arg.startswith("--")}
    assert flags == CONFIRMED_EDIT_FLAGS
    assert "--sandbox" not in args and "-y" not in args and "--yes" not in args
    config = manifest.launch.config_file
    assert config is not None and config.name == ".marimo.toml"
    assert config.lookup("runtime.auto_instantiate") == (True, False)
    assert config.lookup("runtime.on_cell_change") == (True, "lazy")


def test_readme_documents_external_install_and_lifecycle() -> None:
    text = (PLUGIN_DIR / "README.md").read_text()
    install = 'uv tool install "marimo>=0.25.1,<0.26.0" --with jupytext'
    for phrase in (install, "marimo card", "own uv tool environment", "Stop", "recheck", "0o600"):
        assert phrase in text
    assert "—" not in text  # house style: no em dashes


def test_plugin_payload_lives_outside_the_package() -> None:
    assert not (ROOT / "src" / "omrs" / "plugins").exists()
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    wheel = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert wheel["packages"] == ["src/omrs"]
    included = [
        *wheel.get("force-include", {}),
        *wheel.get("include", []),
        *wheel.get("artifacts", []),
    ]
    assert not any(str(entry).startswith("plugins") for entry in included)
    assert "marimo" not in str(pyproject["project"].get("dependencies", []))
    assert "marimo" not in str(pyproject["project"].get("optional-dependencies", {}))


@pytest.mark.slow
def test_built_wheel_ships_the_manifest_but_no_plugins_folder(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not available to build the wheel")
    subprocess.run(  # noqa: S603
        [uv, "build", "--wheel", "--offline", "-o", str(tmp_path)],
        cwd=ROOT, check=True, capture_output=True, timeout=600,
    )  # fmt: skip
    (wheel,) = tmp_path.glob("*.whl")
    names = zipfile.ZipFile(wheel).namelist()
    assert "omrs/core/plugins/shipped/marimo/manifest.json" in names
    assert "omrs/core/plugins/shipped/marimo/empty_notebook.py.template" in names
    assert not any(name.startswith("plugins/") for name in names)


def test_shipped_manifests_returns_the_packaged_file() -> None:
    paths = shipped_manifests()
    assert len(paths) == 1
    (path,) = paths
    assert isinstance(path, Path) and path.is_file()
    package = Path(str(importlib.resources.files("omrs")))
    assert path.resolve().is_relative_to(package.resolve())
    assert path.resolve() == MANIFEST.resolve()
    assert parse_manifest(path.read_bytes()).plugin_id == "marimo"


def test_shipped_manifest_is_a_package_resource() -> None:
    resource = importlib.resources.files("omrs.core.plugins") / "shipped" / "marimo"
    assert (resource / "manifest.json").is_file()
    assert (resource / "empty_notebook.py.template").is_file()
    assert not (ROOT / "plugins" / "marimo" / "manifest.json").exists()


def test_shipped_manifests_skips_a_resource_that_is_not_on_disk(monkeypatch, caplog) -> None:
    import omrs.core.plugins.shipped as shipped

    class ZipEntry:
        def __truediv__(self, _: str) -> ZipEntry:
            return self

        def is_file(self) -> bool:
            return True

    monkeypatch.setattr(shipped, "files", lambda _: ZipEntry())
    with caplog.at_level("WARNING", logger=shipped.__name__):
        assert shipped.shipped_manifests() == ()
    assert len(caplog.records) == 1


def test_shipped_manifest_declares_project_environment_and_conversion() -> None:
    manifest = parse_manifest(MANIFEST.read_bytes())
    assert manifest.plugin_version == "0.3.0"
    capability = manifest.capabilities[PROJECT_ENVIRONMENT]
    assert capability.config == "venv.path" and capability.value is None
    assert manifest.convert is not None
    assert manifest.convert.args == ("convert", "{source_path}", "-o", "{output_path}")
    raw = json.loads(MANIFEST.read_text())
    assert raw["capabilities"][PROJECT_ENVIRONMENT] == {"config": "venv.path"}


def test_empty_notebook_template_is_a_marimo_notebook() -> None:
    text = empty_notebook_text()
    tree = ast.parse(text)
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "App" and getattr(node.func.value, "id", "") == "marimo"
    ]  # fmt: skip
    assert calls, "the template must create marimo.App"
    assert '__generated_with = "0.25.1"' in text
    assert "Path(__file__).resolve().parent" in text and "experiment.json" in text
    assert "{" not in text and "}" not in text  # nothing left to substitute


@pytest.fixture
def host(tmp_path: Path):
    exe = make_fake_editor(tmp_path / "tool")
    registry = PluginRegistry(
        SqliteWorkspaceRepository(tmp_path / "ws" / "workspace.sqlite3"), SubprocessProbeRunner()
    )
    launcher = OwnedProcessLauncher(tmp_path / "rt", grace_seconds=1.0, ready_timeout=10.0)
    notebook = tmp_path / "nb.py"
    notebook.write_text("import marimo\n")
    yield registry, launcher, exe, notebook
    launcher.stop_all()


def test_independent_registration_with_shipped_manifest(host) -> None:
    registry, _, exe, _ = host
    record = registry.register(MANIFEST, exe, approved=True)
    assert record["name"] == "marimo" and record["compatibility_status"] == "unchecked"
    state = registry.recheck("marimo")
    assert state.status == "compatible" and state.version == "0.25.1"


def test_external_version_change_triggers_recheck(host, tmp_path: Path) -> None:
    registry, launcher, exe, notebook = host
    registry.register(MANIFEST, exe, approved=True)
    assert registry.recheck("marimo").launchable
    # Updated outside OMRS. The shim file is unchanged, as with a tool
    # environment upgrade that keeps the same entry-point script.
    (exe.parent / "version.txt").write_text("0.26.0\n")
    assert registry.state("marimo").launchable  # cached result; no process run
    supervisor = NotebookEditorSupervisor(registry, launcher, ports=[_port()])
    with pytest.raises(PluginLaunchError, match="0.26.0 is outside the tested range"):
        supervisor.open("marimo", notebook, consent=True)
    assert registry.state("marimo").status == "incompatible"
    assert launcher.owned_ids() == []
    # A supported version passes the next recheck without any OMRS change.
    (exe.parent / "version.txt").write_text("0.25.9\n")
    assert registry.recheck("marimo").version == "0.25.9"
    assert registry.state("marimo").launchable


def test_edited_shipped_manifest_needs_new_approval(host, tmp_path: Path) -> None:
    registry, _, exe, _ = host
    copy = tmp_path / "manifest.json"
    copy.write_bytes(MANIFEST.read_bytes())
    registry.register(copy, exe, approved=True)
    copy.write_text(copy.read_text().replace('"0.26.0"', '"9.0.0"'))
    assert registry.recheck("marimo").status == "needs_approval"


def _port() -> int:
    from tests.unit.test_process_launcher_support import free_port

    return free_port()
