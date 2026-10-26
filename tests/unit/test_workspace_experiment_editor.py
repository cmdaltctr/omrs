"""Pre-launch checks for a Library notebook (open-experiment-in-marimo D2, D3).

Every test builds a temporary project with a fake ``.venv`` and a fake marimo
tool environment. No test reads the real tool environment or starts a process.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from omrs.core.workspace.experiment_editor import (
    EditorRefusal,
    ProjectEnvironment,
    check_project_environment,
    check_runs_on_open,
)


def _site_packages(env: Path, python: str) -> Path:
    path = env / "lib" / f"python{python}" / "site-packages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _add_distributions(site: Path, packages: dict[str, str]) -> None:
    for name, version in packages.items():
        (site / f"{name}-{version}.dist-info").mkdir()


def _venv(
    root: Path,
    *,
    python: str = "3.14",
    key: str = "version_info",
    packages: dict[str, str] | None = None,
    config: bool = True,
    interpreter: bool = True,
) -> Path:
    venv = root / ".venv"
    (venv / "bin").mkdir(parents=True)
    if config:
        (venv / "pyvenv.cfg").write_text(
            f"home = /opt/python/bin\nimplementation = CPython\n{key} = {python}.1\n",
            encoding="utf-8",
        )
    if interpreter:
        (venv / "bin" / "python").write_text("", encoding="utf-8")
    _add_distributions(_site_packages(venv, python), packages or {})
    return venv


def _tool(
    base: Path,
    *,
    python: str = "3.14",
    packages: dict[str, str] | None = None,
) -> Path:
    """Make a fake uv tool environment and return its ``marimo`` script."""
    env = base / "tools" / "marimo"
    (env / "bin").mkdir(parents=True)
    (env / "pyvenv.cfg").write_text(f"home = /opt/python\nversion_info = {python}.0\n", "utf-8")
    (env / "bin" / "python").write_text("", encoding="utf-8")
    _add_distributions(_site_packages(env, python), {"marimo": "0.25.1", **(packages or {})})
    script = env / "bin" / "marimo"
    script.write_text(f"#!{env / 'bin' / 'python'}\nimport sys\n", encoding="utf-8")
    return script


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "experiments").mkdir(parents=True)
    return root


# --- check_project_environment: the .venv folder -----------------------------------


def test_missing_venv_is_refused_with_uv_sync_hint(tmp_path: Path) -> None:
    root = _project(tmp_path)
    with pytest.raises(EditorRefusal) as caught:
        check_project_environment(root, _tool(tmp_path))
    assert caught.value.reason == "no_project_environment"
    assert "uv sync" in caught.value.message
    assert str(tmp_path) not in caught.value.message
    assert caught.value.output_tail == ""
    assert str(caught.value) == caught.value.message


def test_venv_without_pyvenv_cfg_is_refused(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _venv(root, config=False)
    with pytest.raises(EditorRefusal) as caught:
        check_project_environment(root, _tool(tmp_path))
    assert caught.value.reason == "no_project_environment"


def test_venv_without_bin_python_is_refused(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _venv(root, interpreter=False)
    with pytest.raises(EditorRefusal) as caught:
        check_project_environment(root, _tool(tmp_path))
    assert caught.value.reason == "no_project_environment"


def test_venv_that_is_a_file_is_refused(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / ".venv").write_text("not a folder", encoding="utf-8")
    with pytest.raises(EditorRefusal) as caught:
        check_project_environment(root, _tool(tmp_path))
    assert caught.value.reason == "no_project_environment"


def test_venv_link_is_resolved(tmp_path: Path) -> None:
    root = _project(tmp_path)
    real = _venv(tmp_path / "elsewhere")
    (root / ".venv").symlink_to(real, target_is_directory=True)
    result = check_project_environment(root, _tool(tmp_path))
    assert result.venv == Path(os.path.realpath(real))
    assert result.python == "3.14"


def test_dangling_venv_link_is_refused(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / ".venv").symlink_to(tmp_path / "gone", target_is_directory=True)
    with pytest.raises(EditorRefusal) as caught:
        check_project_environment(root, _tool(tmp_path))
    assert caught.value.reason == "no_project_environment"


def test_matching_environment_returns_the_details(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _venv(root, packages={"numpy": "2.3.0"})
    result = check_project_environment(root, _tool(tmp_path, packages={"numpy": "2.3.0"}))
    assert result == ProjectEnvironment(
        venv=Path(os.path.realpath(root / ".venv")),
        python="3.14",
        marimo_in_project=False,
        shadowed=(),
    )


# --- check_project_environment: Python versions ----------------------------------


def test_python_mismatch_names_both_versions(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _venv(root, python="3.12")
    with pytest.raises(EditorRefusal) as caught:
        check_project_environment(root, _tool(tmp_path, python="3.14"))
    refusal = caught.value
    assert refusal.reason == "python_mismatch"
    assert "3.12" in refusal.message
    assert "3.14" in refusal.message
    assert "dev dependencies" in refusal.message
    assert str(tmp_path) not in refusal.message


def test_version_key_from_standard_venv_is_read(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _venv(root, python="3.13", key="version")
    with pytest.raises(EditorRefusal) as caught:
        check_project_environment(root, _tool(tmp_path, python="3.14"))
    assert caught.value.reason == "python_mismatch"
    assert "3.13" in caught.value.message


def test_executable_link_is_followed_to_its_tool_environment(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _venv(root, python="3.12")
    script = _tool(tmp_path, python="3.14")
    shim = tmp_path / "bin" / "marimo"
    shim.parent.mkdir()
    shim.symlink_to(script)
    with pytest.raises(EditorRefusal) as caught:
        check_project_environment(root, shim)
    assert caught.value.reason == "python_mismatch"


def test_no_mismatch_check_when_marimo_is_in_the_project(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _venv(root, python="3.12", packages={"marimo": "0.25.1", "starlette": "1.6.0"})
    result = check_project_environment(
        root, _tool(tmp_path, python="3.14", packages={"starlette": "1.8.0"})
    )
    assert result.marimo_in_project is True
    assert result.python == "3.12"
    assert result.shadowed == ()


def test_check_is_skipped_when_project_version_is_unreadable(tmp_path: Path) -> None:
    root = _project(tmp_path)
    venv = _venv(root, python="3.12")
    (venv / "pyvenv.cfg").write_text("home = /opt/python\n", encoding="utf-8")
    result = check_project_environment(root, _tool(tmp_path, python="3.14"))
    assert result.python is None


def test_check_is_skipped_when_project_config_cannot_be_opened(tmp_path: Path) -> None:
    root = _project(tmp_path)
    venv = _venv(root, python="3.12")
    config = venv / "pyvenv.cfg"
    config.chmod(0)
    try:
        result = check_project_environment(root, _tool(tmp_path, python="3.14"))
    finally:
        config.chmod(0o644)
    assert result.python is None


def test_check_is_skipped_when_project_config_is_not_text(tmp_path: Path) -> None:
    root = _project(tmp_path)
    venv = _venv(root, python="3.12")
    (venv / "pyvenv.cfg").write_bytes(b"version_info = \xff\xfe\n")
    result = check_project_environment(root, _tool(tmp_path, python="3.14"))
    assert result.python is None


def test_check_is_skipped_when_executable_has_no_shebang(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _venv(root, python="3.12")
    binary = tmp_path / "marimo"
    binary.write_bytes(b"\xcf\xfa\xed\xfe binary")
    result = check_project_environment(root, binary)
    assert result.python == "3.12"
    assert result.shadowed == ()


def test_check_is_skipped_when_executable_is_missing(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _venv(root, python="3.12")
    result = check_project_environment(root, tmp_path / "missing")
    assert result.python == "3.12"


def test_check_is_skipped_for_a_relative_shebang(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _venv(root, python="3.12")
    script = tmp_path / "marimo"
    script.write_text("#!python\n", encoding="utf-8")
    result = check_project_environment(root, script)
    assert result.python == "3.12"


def test_check_is_skipped_when_tool_config_is_missing(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _venv(root, python="3.12")
    script = _tool(tmp_path, python="3.14")
    (script.parent.parent / "pyvenv.cfg").unlink()
    result = check_project_environment(root, script)
    assert result.python == "3.12"


# --- check_project_environment: shadowed distributions ------------------------------


def test_shadowed_names_differ_in_version_and_are_sorted(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _venv(
        root,
        packages={"starlette": "1.6.0", "uvicorn": "0.52.1", "anyio": "4.9.0", "numpy": "2.3.0"},
    )
    tool = _tool(
        tmp_path,
        packages={"uvicorn": "0.54.0", "starlette": "1.8.0", "anyio": "4.9.0", "pyyaml": "6.0"},
    )
    result = check_project_environment(root, tool)
    assert result.shadowed == ("starlette", "uvicorn")


def test_shadowed_names_are_normalised(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _venv(root, packages={"Typing_Extensions": "4.12.0", "zope.interface": "7.0"})
    tool = _tool(tmp_path, packages={"typing_extensions": "4.15.0", "zope_interface": "7.2"})
    result = check_project_environment(root, tool)
    assert result.shadowed == ("typing-extensions", "zope-interface")


def test_shadowed_names_are_capped_at_twenty(tmp_path: Path) -> None:
    root = _project(tmp_path)
    names = [f"pkg{index:02d}" for index in range(25)]
    _venv(root, packages=dict.fromkeys(names, "1.0"))
    result = check_project_environment(root, _tool(tmp_path, packages=dict.fromkeys(names, "2.0")))
    assert result.shadowed == tuple(names[:20])


def test_non_distribution_entries_are_ignored(tmp_path: Path) -> None:
    root = _project(tmp_path)
    venv = _venv(root, packages={"starlette": "1.6.0"})
    site = venv / "lib" / "python3.14" / "site-packages"
    (site / "starlette").mkdir()
    (site / "broken.dist-info").mkdir()
    (site / "_virtualenv.pth").write_text("", encoding="utf-8")
    tool = _tool(tmp_path, packages={"starlette": "1.8.0", "broken": "1.0"})
    result = check_project_environment(root, tool)
    assert result.shadowed == ("starlette",)


# --- check_runs_on_open ----------------------------------------------------------


def _experiment(root: Path) -> Path:
    folder = root / "experiments" / "1-demo-2026-10-25"
    folder.mkdir(parents=True)
    return folder


def test_no_pyproject_is_accepted(tmp_path: Path) -> None:
    folder = _experiment(_project(tmp_path))
    check_runs_on_open(folder)


def test_pyproject_without_marimo_settings_is_accepted(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")
    check_runs_on_open(_experiment(root))


def test_auto_instantiate_false_is_accepted(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "pyproject.toml").write_text(
        "[tool.marimo.runtime]\nauto_instantiate = false\n", encoding="utf-8"
    )
    check_runs_on_open(_experiment(root))


def test_nearest_pyproject_with_auto_instantiate_is_refused(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "pyproject.toml").write_text(
        "[tool.marimo.runtime]\nauto_instantiate = true\n", encoding="utf-8"
    )
    with pytest.raises(EditorRefusal) as caught:
        check_runs_on_open(_experiment(root))
    assert caught.value.reason == "project_config_runs_on_open"
    assert "auto_instantiate" in caught.value.message
    assert str(tmp_path) not in caught.value.message


def test_pyproject_in_the_experiment_folder_wins(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "pyproject.toml").write_text(
        "[tool.marimo.runtime]\nauto_instantiate = false\n", encoding="utf-8"
    )
    folder = _experiment(root)
    (folder / "pyproject.toml").write_text(
        "[tool.marimo.runtime]\nauto_instantiate = true\n", encoding="utf-8"
    )
    with pytest.raises(EditorRefusal) as caught:
        check_runs_on_open(folder)
    assert caught.value.reason == "project_config_runs_on_open"


def test_nearer_safe_pyproject_hides_a_farther_one(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.marimo.runtime]\nauto_instantiate = true\n", encoding="utf-8"
    )
    root = _project(tmp_path)
    (root / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")
    check_runs_on_open(_experiment(root))


def test_invalid_toml_is_refused(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "pyproject.toml").write_text("[tool.marimo\nbroken", encoding="utf-8")
    with pytest.raises(EditorRefusal) as caught:
        check_runs_on_open(_experiment(root))
    assert caught.value.reason == "project_config_runs_on_open"
    assert "TOML" in caught.value.message


def test_unreadable_pyproject_is_refused(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "pyproject.toml").mkdir()
    with pytest.raises(EditorRefusal) as caught:
        check_runs_on_open(_experiment(root))
    assert caught.value.reason == "project_config_runs_on_open"


def test_marimo_table_of_the_wrong_type_is_accepted(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / "pyproject.toml").write_text('[tool]\nmarimo = "x"\n', encoding="utf-8")
    check_runs_on_open(_experiment(root))


def test_check_is_skipped_when_executable_is_text_without_shebang(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _venv(root, python="3.12")
    script = tmp_path / "marimo"
    script.write_text("echo marimo\n", encoding="utf-8")
    result = check_project_environment(root, script)
    assert result.python == "3.12"


def test_config_lines_without_a_value_are_ignored(tmp_path: Path) -> None:
    root = _project(tmp_path)
    venv = _venv(root, python="3.12")
    (venv / "pyvenv.cfg").write_text("# comment\n\nversion = 3.12.4\n", encoding="utf-8")
    with pytest.raises(EditorRefusal) as caught:
        check_project_environment(root, _tool(tmp_path, python="3.14"))
    assert caught.value.reason == "python_mismatch"


def test_unreadable_site_packages_lists_nothing(tmp_path: Path) -> None:
    root = _project(tmp_path)
    venv = _venv(root, packages={"starlette": "1.6.0"})
    site = venv / "lib" / "python3.14" / "site-packages"
    site.chmod(0)
    try:
        result = check_project_environment(root, _tool(tmp_path, packages={"starlette": "1.8.0"}))
    finally:
        site.chmod(0o755)
    assert result.shadowed == ()
