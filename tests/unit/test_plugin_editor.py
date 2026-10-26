"""Editor launch planning and supervision with a fake launcher (task 8.3)."""

from __future__ import annotations

import errno
import json
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from tests.unit.test_plugin_manifest import valid_manifest
from tests.unit.test_plugin_registration import FakeRunner, Output

from omrs.core.plugins import (
    ConvertResult,
    KernelEnvironment,
    NotebookEditorSupervisor,
    PluginConsentError,
    PluginLaunchError,
    PluginRegistry,
    build_launch_plan,
    parse_manifest,
)
from omrs.core.plugins.editor import NO_DOTENV_FILE_NAME
from omrs.integrations.workspace_sqlite import SqliteWorkspaceRepository


@dataclass
class FakeLauncher:
    """Records launch requests. Ports in ``busy`` look taken by another program."""

    root: Path
    busy: set[int] = field(default_factory=set)
    race: set[int] = field(default_factory=set)  # free at check, taken at start
    started: list[dict] = field(default_factory=list)
    stopped: list[str] = field(default_factory=list)

    def create_launch_dir(self) -> Path:
        path = self.root / f"launch-{len(self.started)}-{len(self.stopped)}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def discard_launch_dir(self, workdir: Path) -> None:
        pass

    def port_available(self, host: str, port: int) -> bool:
        return port not in self.busy

    def start(
        self,
        *,
        argv: Sequence[str],
        workdir: Path,
        host: str,
        port: int,
        files: Mapping[str, str],
        secrets: Sequence[str],
        environment: Mapping[str, str] | None = None,
    ) -> str:
        if port in self.race:
            raise OSError(errno.EADDRINUSE, "taken")
        self.started.append(
            {"argv": list(argv), "workdir": workdir, "host": host, "port": port,
             "files": dict(files), "secrets": list(secrets),
             "environment": dict(environment or {})}
        )  # fmt: skip
        return f"id-{len(self.started)}"

    def stop(self, launch_id: str) -> object:
        self.stopped.append(launch_id)
        return launch_id

    def stop_all(self) -> list[object]:
        return []


@pytest.fixture
def setup(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(valid_manifest()))
    exe = tmp_path / "fakeedit"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    notebook = tmp_path / "notes" / "nb.py"
    notebook.parent.mkdir()
    notebook.write_text("import marimo\n")
    registry = PluginRegistry(SqliteWorkspaceRepository(tmp_path / "ws.sqlite3"), FakeRunner())
    registry.register(manifest, exe, approved=True)
    launcher = FakeLauncher(tmp_path / "run")
    return registry, launcher, notebook, exe


def supervisor(registry, launcher, ports=(41001, 41002)) -> NotebookEditorSupervisor:
    return NotebookEditorSupervisor(registry, launcher, ports=ports, token_factory=lambda: "T0KEN")


def test_open_requires_consent(setup) -> None:
    registry, launcher, notebook, _ = setup
    with pytest.raises(PluginConsentError):
        supervisor(registry, launcher).open("fakeedit", notebook, consent=False)
    assert launcher.started == []


def test_open_rechecks_then_launches_loopback_with_token_file(setup) -> None:
    registry, launcher, notebook, exe = setup
    session = supervisor(registry, launcher).open("fakeedit", notebook, consent=True)
    call = launcher.started[0]
    argv = call["argv"]
    assert argv[0] == str(exe)
    assert call["host"] == "127.0.0.1" and argv[argv.index("--host") + 1] == "127.0.0.1"
    assert "--port=41001" in argv and str(notebook.resolve()) in argv
    assert not any("T0KEN" in arg for arg in argv)  # never in argv
    token_path = argv[argv.index("--token-password-file") + 1]
    assert Path(token_path).parent == call["workdir"]
    assert call["files"][Path(token_path).name] == "T0KEN"
    assert "auto_instantiate = false" in call["files"][".fakeedit.toml"]
    assert "--skip-update-check" in argv and "--no-sandbox" in argv
    assert call["secrets"] == ["T0KEN"]
    assert session.port == 41001 and session.token == "T0KEN"  # noqa: S105
    assert "T0KEN" not in repr(session)
    assert registry.state("fakeedit").status == "compatible"


def test_unrelated_port_is_skipped_not_adopted(setup) -> None:
    registry, launcher, notebook, _ = setup
    launcher.busy = {41001}
    launcher.race = {41002}
    sup = supervisor(registry, launcher, ports=(41001, 41002, 41003))
    session = sup.open("fakeedit", notebook, consent=True)
    assert session.port == 41003
    assert launcher.stopped == []  # nothing on the busy ports was touched


def test_all_ports_busy_fails_clearly(setup) -> None:
    registry, launcher, notebook, _ = setup
    launcher.busy = {41001, 41002}
    with pytest.raises(PluginLaunchError, match="41001, 41002.*not stop"):
        supervisor(registry, launcher).open("fakeedit", notebook, consent=True)
    assert launcher.started == [] and launcher.stopped == []


def test_incompatible_plugin_is_not_launched(setup) -> None:
    registry, launcher, notebook, _ = setup
    registry._runner.version = "fakeedit 9.0"  # updated outside OMRS
    with pytest.raises(PluginLaunchError, match="outside the tested range"):
        supervisor(registry, launcher).open("fakeedit", notebook, consent=True)
    assert launcher.started == []


def test_missing_notebook_is_refused(setup, tmp_path: Path) -> None:
    registry, launcher, _, _ = setup
    with pytest.raises(PluginLaunchError, match="notebook"):
        supervisor(registry, launcher).open("fakeedit", tmp_path / "x.py", consent=True)


def test_stop_only_targets_owned_sessions(setup) -> None:
    registry, launcher, notebook, _ = setup
    sup = supervisor(registry, launcher)
    session = sup.open("fakeedit", notebook, consent=True)
    with pytest.raises(KeyError):
        sup.stop("someone-else")
    sup.stop(session.launch_id)
    assert launcher.stopped == [session.launch_id]
    assert sup.sessions() == []


def test_build_launch_plan_rejects_non_loopback(tmp_path: Path) -> None:
    manifest = parse_manifest(json.dumps(valid_manifest()).encode())
    with pytest.raises(ValueError, match="loopback"):
        build_launch_plan(
            manifest, "/bin/x", notebook=tmp_path / "n.py", host="0.0.0.0",  # noqa: S104
            port=1, launch_dir=tmp_path, token="t",  # noqa: S106
        )  # fmt: skip


def test_supervisor_needs_a_port(setup) -> None:
    registry, launcher, _, _ = setup
    with pytest.raises(ValueError, match="port"):
        NotebookEditorSupervisor(registry, launcher, ports=())


def test_start_failure_other_than_port_is_reported(setup) -> None:
    registry, launcher, notebook, _ = setup

    def broken(**_: object) -> str:
        raise OSError(errno.ENOEXEC, "exec format error")

    launcher.start = broken  # type: ignore[method-assign]
    with pytest.raises(PluginLaunchError, match="failed to start"):
        supervisor(registry, launcher).open("fakeedit", notebook, consent=True)


def test_stop_all_stops_owned_sessions(setup) -> None:
    registry, launcher, notebook, _ = setup
    sup = supervisor(registry, launcher, ports=(41001,))
    first = sup.open("fakeedit", notebook, consent=True)
    assert sup.stop_all() == [first.launch_id]
    assert launcher.stopped == [first.launch_id] and sup.sessions() == []


# --- project kernel environment and conversion (design D2, D4, D7) ------------

VENV = Path("/projects/demo/.venv")


def project_manifest() -> dict:
    data = valid_manifest()
    data["capabilities"]["project_environment"] = {"config": "venv.path"}
    data["recipes"]["convert_script"] = {
        "args": ["convert", "{source_path}", "-o", "{output_path}"]
    }
    return data


def plan_for(data: dict, tmp_path: Path, kernel: KernelEnvironment | None = None):
    return build_launch_plan(
        parse_manifest(json.dumps(data).encode()), "/bin/fakeedit",
        notebook=tmp_path / "n.py", host="127.0.0.1", port=2719, launch_dir=tmp_path,
        token="t", kernel_environment=kernel,  # noqa: S106
    )  # fmt: skip


def test_kernel_environment_renders_venv_and_dotenv(tmp_path: Path) -> None:
    plan = plan_for(project_manifest(), tmp_path, KernelEnvironment(VENV))
    config = tomllib.loads(plan.files[".fakeedit.toml"])
    assert config["venv"] == {"path": str(VENV), "writable": False}
    # marimo 0.25.1 drops an empty user-layer `dotenv` list (`_drop_hollow_dotenv`) and
    # then loads the project .env, so the list names an empty private file instead.
    assert config["runtime"] == {
        "auto_instantiate": False, "on_cell_change": "lazy",
        "dotenv": [str(tmp_path / NO_DOTENV_FILE_NAME)],
    }  # fmt: skip
    assert plan.files[NO_DOTENV_FILE_NAME] == ""
    assert plan.files[".fakeedit.toml"].count("[runtime]") == 1


def test_without_kernel_environment_no_dotenv_file_is_written(tmp_path: Path) -> None:
    assert NO_DOTENV_FILE_NAME not in plan_for(project_manifest(), tmp_path).files


def test_kernel_environment_keeps_argv_unchanged(tmp_path: Path) -> None:
    with_env = plan_for(project_manifest(), tmp_path, KernelEnvironment(VENV))
    without = plan_for(project_manifest(), tmp_path)
    assert with_env.argv == without.argv
    assert not any(str(VENV) in arg for arg in with_env.argv)


def test_without_kernel_environment_config_is_byte_identical(tmp_path: Path) -> None:
    expected = '[runtime]\nauto_instantiate = false\non_cell_change = "lazy"\n'
    assert plan_for(valid_manifest(), tmp_path).files[".fakeedit.toml"] == expected
    assert plan_for(project_manifest(), tmp_path).files[".fakeedit.toml"] == expected


@pytest.mark.parametrize(
    "name", ['quote".venv', "back\\slash", "space and ünï", "emoji-\U0001f600", "x'y"]
)
def test_kernel_path_is_escaped_as_toml(tmp_path: Path, name: str) -> None:
    venv = Path("/p") / name / ".venv"
    plan = plan_for(project_manifest(), tmp_path, KernelEnvironment(venv))
    assert tomllib.loads(plan.files[".fakeedit.toml"])["venv"]["path"] == str(venv)


@pytest.mark.parametrize("bad", ["new\nline", "tab\there", "nul\x00", "del\x7f", "cr\r"])
def test_kernel_path_with_control_character_is_refused(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ValueError, match="control character"):
        plan_for(project_manifest(), tmp_path, KernelEnvironment(Path("/p") / bad))


def test_kernel_path_must_be_absolute(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute"):
        plan_for(project_manifest(), tmp_path, KernelEnvironment(Path("rel/.venv")))


@pytest.fixture
def project_setup(tmp_path: Path):
    manifest = tmp_path / "project-manifest.json"
    manifest.write_text(json.dumps(project_manifest()))
    exe = tmp_path / "fakeedit"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    notebook = tmp_path / "exp" / "analysis.marimo.py"
    notebook.parent.mkdir()
    notebook.write_text("import marimo\n")
    runner = ConvertingRunner()
    registry = PluginRegistry(SqliteWorkspaceRepository(tmp_path / "ws-project.sqlite3"), runner)
    registry.register(manifest, exe, approved=True)
    return registry, FakeLauncher(tmp_path / "run"), notebook, exe, runner


@dataclass
class ConvertingRunner(FakeRunner):
    """Answers probes like :class:`FakeRunner` and records conversion argv."""

    convert_output: Output = field(default_factory=lambda: Output(0, "converted", ""))
    timeouts: list[float] = field(default_factory=list)

    def run(self, argv: Sequence[str], *, timeout: float) -> Output:
        if "convert" not in argv:
            return super().run(argv, timeout=timeout)
        self.calls.append(tuple(argv))
        self.timeouts.append(timeout)
        if self.raises is not None:
            raise self.raises
        return self.convert_output


def test_open_with_kernel_environment_passes_plan(project_setup) -> None:
    registry, launcher, notebook, _, _ = project_setup
    sup = supervisor(registry, launcher)
    sup.open("fakeedit", notebook, consent=True, kernel_environment=KernelEnvironment(VENV))
    config = tomllib.loads(launcher.started[0]["files"][".fakeedit.toml"])
    assert config["venv"]["path"] == str(VENV)
    (dotenv,) = config["runtime"]["dotenv"]
    assert dotenv.endswith(NO_DOTENV_FILE_NAME)
    assert launcher.started[0]["files"][NO_DOTENV_FILE_NAME] == ""


def test_open_with_kernel_environment_needs_the_capability(setup) -> None:
    registry, launcher, notebook, _ = setup
    with pytest.raises(PluginLaunchError) as caught:
        supervisor(registry, launcher).open(
            "fakeedit", notebook, consent=True, kernel_environment=KernelEnvironment(VENV)
        )
    assert caught.value.reason == "editor_unsupported"
    assert launcher.started == []


def test_open_without_kernel_environment_keeps_old_config(project_setup) -> None:
    registry, launcher, notebook, _, _ = project_setup
    supervisor(registry, launcher).open("fakeedit", notebook, consent=True)
    assert "venv" not in tomllib.loads(launcher.started[0]["files"][".fakeedit.toml"])


def test_launch_error_reasons(setup) -> None:
    registry, launcher, notebook, _ = setup
    assert PluginLaunchError("x").reason == "launch_failed" and str(PluginLaunchError("x")) == "x"
    launcher.busy = {41001, 41002}
    with pytest.raises(PluginLaunchError) as busy:
        supervisor(registry, launcher).open("fakeedit", notebook, consent=True)
    assert busy.value.reason == "no_free_port"
    registry._runner.version = "fakeedit 9.0"
    with pytest.raises(PluginLaunchError) as stale:
        supervisor(registry, launcher).open("fakeedit", notebook, consent=True)
    assert stale.value.reason == "editor_unavailable"


def test_convert_runs_recipe_with_both_substitutions(project_setup, tmp_path: Path) -> None:
    registry, launcher, _, exe, runner = project_setup
    registry.recheck("fakeedit")
    runner.convert_output = Output(0, "out\n" * 50, "warn")
    source, output = tmp_path / "exp" / "analysis.py", tmp_path / "private" / "nb.py"
    result = supervisor(registry, launcher).convert("fakeedit", source, output, timeout=7.5)
    assert runner.calls[-1] == (str(exe), "convert", str(source), "-o", str(output))
    assert runner.timeouts == [7.5]
    assert result == ConvertResult(0, "\n".join(["out"] * 39 + ["warn"]))
    assert launcher.started == []


def test_convert_default_timeout_and_failure_tail(project_setup, tmp_path: Path) -> None:
    registry, launcher, _, _, runner = project_setup
    registry.recheck("fakeedit")
    message = "Error: Converting py:percent format requires jupytext"
    runner.convert_output = Output(1, "", message)
    result = supervisor(registry, launcher).convert("fakeedit", tmp_path / "a", tmp_path / "b")
    assert result == ConvertResult(1, message) and runner.timeouts == [120.0]


@pytest.mark.parametrize("error", [OSError("cannot start"), TimeoutError("too slow")])
def test_convert_reports_start_errors(project_setup, tmp_path: Path, error) -> None:
    registry, launcher, _, _, runner = project_setup
    registry.recheck("fakeedit")
    runner.raises = error
    result = supervisor(registry, launcher).convert("fakeedit", tmp_path / "a", tmp_path / "b")
    assert result == ConvertResult(-1, str(error))


def test_convert_refusals(project_setup, setup, tmp_path: Path) -> None:
    registry, launcher, _, _, runner = project_setup
    sup = supervisor(registry, launcher)
    with pytest.raises(PluginLaunchError) as unknown:
        sup.convert("nobody", tmp_path / "a", tmp_path / "b")
    assert unknown.value.reason == "editor_unavailable"
    with pytest.raises(PluginLaunchError) as unchecked:  # registered, never checked
        sup.convert("fakeedit", tmp_path / "a", tmp_path / "b")
    assert unchecked.value.reason == "editor_unavailable"
    plain_registry, plain_launcher, _, _ = setup
    plain_registry.recheck("fakeedit")
    with pytest.raises(PluginLaunchError) as unsupported:
        supervisor(plain_registry, plain_launcher).convert(
            "fakeedit", tmp_path / "a", tmp_path / "b"
        )
    assert unsupported.value.reason == "editor_unsupported"
    assert not any("convert" in call for call in runner.calls)
