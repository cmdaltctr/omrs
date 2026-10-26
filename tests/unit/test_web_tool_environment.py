"""marimo tool detection (install-marimo-from-integrations, tasks 2.1 and 2.2).

Every test uses a fake runner and fixture tool folders under ``tmp_path``.
No test runs the real ``uv`` or reads the real ``~/.local``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from omrs.core.plugins.versions import VersionRange
from omrs.core.workspace.experiment_editor import JUPYTEXT_HINT
from omrs.transports.api import tool_environment as te

RANGE = VersionRange((0, 25, 1), (0, 26, 0))
CARD_RECEIPT = (
    '[tool]\nrequirements = [{ name = "marimo", specifier = ">=0.25.1,<0.26.0" }, '
    '{ name = "jupytext" }]\n'
)


class FakeRunner:
    """Answers ``uv tool dir`` and ``uv tool dir --bin`` from fixture folders."""

    def __init__(self, tools: Path, bin_dir: Path, *, fail: BaseException | None = None) -> None:
        self.tools, self.bin_dir, self.fail = tools, bin_dir, fail
        self.calls: list[tuple[list[str], float]] = []
        self.code = 0

    def __call__(self, argv: Sequence[str], timeout: float) -> tuple[int, str]:
        self.calls.append((list(argv), timeout))
        if self.fail is not None:
            raise self.fail
        folder = self.bin_dir if "--bin" in argv else self.tools
        return self.code, f"{folder}\n"


def _tool(
    tmp_path: Path,
    *,
    marimo: str | None = "0.25.1",
    jupytext: bool = True,
    receipt: str | None = None,
) -> tuple[Path, Path]:
    """Write a fake marimo tool environment; return the tools and bin folders."""
    tools, bin_dir = tmp_path / "tools", tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    env = tools / "marimo"
    site = env / "lib" / "python3.14" / "site-packages"
    site.mkdir(parents=True)
    executable = bin_dir / "marimo"
    if receipt is None:
        receipt = (
            '[tool]\nrequirements = [{ name = "marimo" }]\nentrypoints = [\n'
            f'    {{ name = "marimo", install-path = "{executable}", from = "marimo" }},\n]\n'
        )
    (env / "uv-receipt.toml").write_text(receipt, encoding="utf-8")
    packages = {"marimo": marimo} if marimo else {}
    if jupytext:
        packages["jupytext"] = "1.17.3"
    for name, version in packages.items():
        info = site / f"{name}-{version}.dist-info"
        info.mkdir()
        (info / "METADATA").write_text(f"Name: {name}\nVersion: {version}\n", encoding="utf-8")
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    return tools, bin_dir


def _detector(runner: FakeRunner, uv: str | None = "/fake/uv") -> te.ToolDetector:
    return te.ToolDetector(runner=runner, find=lambda: uv, tested=lambda: RANGE)


# ── Commands (D1) ────────────────────────────────────────────────────────


def test_the_requirement_comes_from_the_shipped_manifest() -> None:
    assert te.requirement(te.shipped_range()) == "marimo>=0.25.1,<0.26.0"


def test_install_and_uninstall_argument_lists_are_fixed() -> None:
    assert te.install_argv("/x/uv", RANGE) == [
        "/x/uv",
        "tool",
        "install",
        "marimo>=0.25.1,<0.26.0",
        "--with",
        "jupytext",
    ]
    assert te.uninstall_argv("/x/uv") == ["/x/uv", "tool", "uninstall", "marimo"]


def test_the_library_hint_equals_the_card_command() -> None:
    assert JUPYTEXT_HINT == te.install_command(te.shipped_range())


def test_copy_commands_quote_the_requirement() -> None:
    assert te.install_command(RANGE) == 'uv tool install "marimo>=0.25.1,<0.26.0" --with jupytext'
    assert te.UNINSTALL_COMMAND == "uv tool uninstall marimo"


# ── Detection (D2) ───────────────────────────────────────────────────────


def test_no_receipt_is_not_installed(tmp_path: Path) -> None:
    (tmp_path / "tools").mkdir()
    status = _detector(FakeRunner(tmp_path / "tools", tmp_path / "bin")).detect()
    assert status.availability == "not-installed"
    assert status.version is None and status.executable is None
    assert status.problem is None


def test_marimo_with_jupytext_is_ready_with_version_and_executable(tmp_path: Path) -> None:
    tools, bin_dir = _tool(tmp_path)
    status = _detector(FakeRunner(tools, bin_dir)).detect()
    assert status.availability == "ready"
    assert status.version == "0.25.1"
    assert status.jupytext is True
    assert status.executable == str(bin_dir / "marimo")
    assert status.uv == "/fake/uv"


def test_marimo_without_jupytext_needs_jupytext(tmp_path: Path) -> None:
    tools, bin_dir = _tool(tmp_path, jupytext=False)
    status = _detector(FakeRunner(tools, bin_dir)).detect()
    assert status.availability == "needs-jupytext"
    assert status.jupytext is False and status.version == "0.25.1"


def test_a_version_above_the_range_is_outside_range(tmp_path: Path) -> None:
    tools, bin_dir = _tool(tmp_path, marimo="0.27.0")
    assert _detector(FakeRunner(tools, bin_dir)).detect().availability == "outside-range"


def test_no_uv_is_unknown_with_uv_not_found(tmp_path: Path) -> None:
    runner = FakeRunner(tmp_path, tmp_path)
    status = _detector(runner, uv=None).detect()
    assert status.availability == "unknown"
    assert status.problem == "uv-not-found"
    assert runner.calls == []


@pytest.mark.parametrize("fail", [OSError("no exec"), TimeoutError("slow")])
def test_a_runner_error_or_timeout_is_unknown(tmp_path: Path, fail: BaseException) -> None:
    status = _detector(FakeRunner(tmp_path, tmp_path, fail=fail)).detect()
    assert status.availability == "unknown"
    assert status.problem == "status-unknown"


def test_an_unreadable_receipt_is_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Python 3.12 raises PermissionError from is_file(); 3.14 returns False, so force it.
    tools, bin_dir = _tool(tmp_path)
    real = Path.is_file

    def deny(self: Path, *args: object, **kwargs: object) -> bool:
        if self.name == te.RECEIPT_NAME:
            raise PermissionError(13, "Permission denied", str(self))
        return real(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "is_file", deny)
    status = _detector(FakeRunner(tools, bin_dir)).detect()
    assert status.availability == "unknown"
    assert status.problem == "status-unknown"


def test_a_failed_uv_tool_dir_is_unknown(tmp_path: Path) -> None:
    runner = FakeRunner(tmp_path, tmp_path)
    runner.code = 2
    assert _detector(runner).detect().availability == "unknown"


def test_uv_tool_dir_runs_once_per_detector_with_a_ten_second_limit(tmp_path: Path) -> None:
    tools, bin_dir = _tool(tmp_path)
    runner = FakeRunner(tools, bin_dir)
    detector = _detector(runner)
    detector.detect()
    detector.detect()
    assert [argv for argv, _ in runner.calls] == [
        ["/fake/uv", "tool", "dir"],
        ["/fake/uv", "tool", "dir", "--bin"],
    ]
    assert {timeout for _, timeout in runner.calls} == {10.0}


def test_a_receipt_without_entrypoint_gives_no_executable(tmp_path: Path) -> None:
    tools, bin_dir = _tool(tmp_path, receipt=CARD_RECEIPT)
    status = _detector(FakeRunner(tools, bin_dir)).detect()
    assert status.availability == "ready"
    assert status.executable is None


def test_an_entrypoint_outside_the_uv_bin_folder_gives_no_executable(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere" / "marimo"
    receipt = (
        '[tool]\nrequirements = [{ name = "marimo" }]\nentrypoints = [\n'
        f'    {{ name = "marimo", install-path = "{elsewhere}", from = "marimo" }},\n]\n'
    )
    tools, bin_dir = _tool(tmp_path, receipt=receipt)
    status = _detector(FakeRunner(tools, bin_dir)).detect()
    assert status.availability == "ready"
    assert status.executable is None


def test_the_default_runner_passes_uv_folders_and_drops_api_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    class Done:
        returncode, stdout = 0, "/scratch/tools\n"

    def fake_run(argv: list[str], **kwargs: object) -> Done:
        seen.update(kwargs, argv=argv)
        return Done()

    monkeypatch.setenv("UV_TOOL_DIR", "/scratch/tools")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setattr(te.subprocess, "run", fake_run)
    assert te.run_uv(["/x/uv", "tool", "dir"], 10.0) == (0, "/scratch/tools\n")
    env = seen["env"]
    assert isinstance(env, dict)
    assert env["UV_TOOL_DIR"] == "/scratch/tools"
    assert "OPENAI_API_KEY" not in env
    assert seen["timeout"] == 10.0 and seen.get("shell") in (None, False)
    assert seen["stdin"] == te.subprocess.DEVNULL


# ── Installed by the card (D7) ───────────────────────────────────────────


def _receipt(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "uv-receipt.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_card_receipt_matches(tmp_path: Path) -> None:
    assert te.installed_by_card(_receipt(tmp_path, CARD_RECEIPT), RANGE) is True


def test_clause_order_does_not_matter(tmp_path: Path) -> None:
    text = CARD_RECEIPT.replace(">=0.25.1,<0.26.0", "<0.26.0, >=0.25.1")
    assert te.installed_by_card(_receipt(tmp_path, text), RANGE) is True


def test_marimo_without_a_specifier_does_not_match(tmp_path: Path) -> None:
    text = '[tool]\nrequirements = [{ name = "marimo" }]\n'
    assert te.installed_by_card(_receipt(tmp_path, text), RANGE) is False


def test_marimo_and_jupytext_without_the_range_do_not_match(tmp_path: Path) -> None:
    text = '[tool]\nrequirements = [{ name = "marimo" }, { name = "jupytext" }]\n'
    assert te.installed_by_card(_receipt(tmp_path, text), RANGE) is False


def test_a_third_requirement_does_not_match(tmp_path: Path) -> None:
    text = CARD_RECEIPT.replace('{ name = "jupytext" }', '{ name = "jupytext" }, { name = "x" }')
    assert te.installed_by_card(_receipt(tmp_path, text), RANGE) is False


def test_an_unreadable_receipt_does_not_match(tmp_path: Path) -> None:
    assert te.installed_by_card(_receipt(tmp_path, "[tool\nnot toml"), RANGE) is False
    assert te.installed_by_card(tmp_path / "missing.toml", RANGE) is False


def test_detection_reports_whether_the_card_installed_it(tmp_path: Path) -> None:
    tools, bin_dir = _tool(tmp_path, receipt=CARD_RECEIPT)
    assert _detector(FakeRunner(tools, bin_dir)).detect().installed_by_card is True
    other = tmp_path / "other"
    tools, bin_dir = _tool(other)
    assert _detector(FakeRunner(tools, bin_dir)).detect().installed_by_card is False


# ── Caution (D8) ─────────────────────────────────────────────────────────


def _status(availability: str, version: str | None) -> te.ToolStatus:
    return te.ToolStatus(availability=availability, version=version)


@pytest.mark.parametrize(
    ("availability", "version"), [("needs-jupytext", "0.25.1"), ("outside-range", "0.27.0")]
)
def test_the_caution_names_the_installed_version(availability: str, version: str) -> None:
    caution = te.install_caution(_status(availability, version), RANGE)
    assert caution == (
        f"Install replaces your marimo {version} tool environment with "
        "marimo >=0.25.1,<0.26.0 and jupytext."
    )


@pytest.mark.parametrize("availability", ["ready", "not-installed", "unknown"])
def test_no_caution_otherwise(availability: str) -> None:
    assert te.install_caution(_status(availability, None), RANGE) is None


def test_the_suite_never_lets_a_default_detector_find_the_real_uv() -> None:
    # The conftest guard: a runtime's default detector must not run `uv tool dir`.
    status = te.ToolDetector(tested=lambda: RANGE).detect()
    assert status.availability == "unknown" and status.problem == "uv-not-found"
