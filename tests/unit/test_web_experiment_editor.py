"""Library "Open in marimo" route (open-experiment-in-marimo, task 6.2, design D3 to D5).

The app runs the production plugin host around the fake marimo executable,
so conversion and launch go through real (fake) processes. Real marimo is
never started. Every refusal leaves the experiment folder byte-identical.
"""

from __future__ import annotations

import json
import logging
import shutil
import socket
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit.test_plugin_marimo_manifest import MANIFEST  # noqa: E402
from tests.unit.test_web_documents_support import ORIGIN, bearer  # noqa: E402
from tests.unit.test_web_experiment_editor_support import (  # noqa: E402
    EditorApp,
    editor_app,
    make_venv,
    register_marimo,
    tree_digest,
)
from tests.unit.test_web_experiment_library_support import SECOND  # noqa: E402

from omrs.core.plugins.editor import ConvertResult, PluginLaunchError  # noqa: E402

ANALYSIS = "# %%\nfrom pathlib import Path\nEXP = Path(__file__).resolve().parent\n"


def _refused(response: Any, reason: str) -> dict[str, Any]:
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["status"] == "error" and body["reason"] == reason, body
    assert "/" not in body["message"].replace("`uv tool install", ""), body["message"]
    return body


def _no_launch(env: EditorApp) -> None:
    assert not (env.exe.parent / "record.json").exists()
    assert env.host.editors.sessions() == []


# ── Access and input ─────────────────────────────────────────────────────


def test_a_bearer_credential_cannot_launch(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch) as env:
        headers = {**ORIGIN, **bearer(env.policy, "graph", "read", "run")}
        response = env.client.post(env.url(), json={"consent": True}, headers=headers)
        assert response.status_code in (401, 403), response.text
        _no_launch(env)


def test_consent_false_is_refused_and_reads_nothing(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch) as env:
        (env.folder / "analysis.py").write_text(ANALYSIS)
        before = tree_digest(env.folder)
        response = env.open(consent=False)
        assert response.status_code == 403, response.text
        assert tree_digest(env.folder) == before
        _no_launch(env)


@pytest.mark.parametrize(
    "body", [{"consent": True, "notebook": "x.py"}, {"consent": "yes"}, {}], ids=str
)
def test_a_body_other_than_consent_is_a_validation_error(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch, body: dict
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch) as env:
        response = env.client.post(env.url(), json=body, headers=ORIGIN)
        assert response.status_code == 400, response.text
        _no_launch(env)


@pytest.mark.parametrize("folder", ["%2E%2E", "a%5Cb", ".hidden"])
def test_a_folder_name_with_a_path_escape_is_refused(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch, folder: str
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch) as env:
        response = env.open(folder)
        assert response.status_code == 400, response.text
        _no_launch(env)


def test_unknown_project_unlisted_folder_and_removed_project_are_404(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch) as env:
        unknown = env.client.post(
            env.url(project_id="nope"), json={"consent": True}, headers=ORIGIN
        )
        assert unknown.status_code == 404, unknown.text
        assert env.open("99-absent-2026-01-01").status_code == 404
        shutil.rmtree(env.root / "experiments")
        assert env.open().status_code == 404
        _no_launch(env)


# ── Refusals with a reason ───────────────────────────────────────────────


def test_marimo_not_registered_is_editor_unavailable(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch, register=False) as env:
        before = tree_digest(env.folder)
        _refused(env.open(), "editor_unavailable")
        assert tree_digest(env.folder) == before


def test_a_manifest_without_the_project_capability_is_editor_unsupported(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch, register=False) as env:
        data = json.loads(MANIFEST.read_text())
        del data["capabilities"]["project_environment"]
        old = tmp_path / "ws" / "plugins" / "marimo-old.json"
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_text(json.dumps(data))
        register_marimo(env.client, old, env.exe)
        before = tree_digest(env.folder)
        _refused(env.open(), "editor_unsupported")
        assert tree_digest(env.folder) == before
        _no_launch(env)


def test_a_manifest_without_the_convert_recipe_is_unsupported_only_when_needed(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch, register=False) as env:
        data = json.loads(MANIFEST.read_text())
        del data["recipes"]["convert_script"]
        old = tmp_path / "ws" / "plugins" / "marimo-noconvert.json"
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_text(json.dumps(data))
        register_marimo(env.client, old, env.exe)
        (env.folder / "analysis.py").write_text(ANALYSIS)
        _refused(env.open(), "editor_unsupported")
        assert env.open(SECOND).status_code == 201  # no analysis.py: no conversion needed


def test_a_project_without_a_venv_is_refused(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch, venv=False) as env:
        before = tree_digest(env.folder)
        body = _refused(env.open(), "no_project_environment")
        assert "uv sync" in body["message"]
        assert tree_digest(env.folder) == before
        _no_launch(env)


def test_a_different_python_without_marimo_is_python_mismatch(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch, venv=False) as env:
        make_venv(env.root, version="2.7")
        body = _refused(env.open(), "python_mismatch")
        assert "2.7" in body["message"]
        _no_launch(env)


def test_a_project_that_runs_cells_on_open_is_refused(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch) as env:
        (env.root / "pyproject.toml").write_text("[tool.marimo.runtime]\nauto_instantiate = true\n")
        before = tree_digest(env.folder)
        _refused(env.open(), "project_config_runs_on_open")
        assert tree_digest(env.folder) == before
        _no_launch(env)


def test_a_linked_notebook_is_refused(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch) as env:
        target = tmp_path / "elsewhere.py"
        target.write_text("import marimo\n")
        (env.folder / "analysis.marimo.py").symlink_to(target)
        _refused(env.open(), "notebook_not_regular")
        assert target.read_text() == "import marimo\n"
        _no_launch(env)


def test_missing_jupytext_is_converter_missing_and_leaves_no_file(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch) as env:
        (env.folder / "analysis.py").write_text(ANALYSIS)
        (env.exe.parent / "convert-fails-jupytext").write_text("")
        before = tree_digest(env.folder)
        body = _refused(env.open(), "converter_missing")
        assert "--with jupytext" in body["message"]
        assert tree_digest(env.folder) == before
        assert list((tmp_path / "ws" / "run" / "convert").iterdir()) == []
        _no_launch(env)


def test_another_conversion_failure_is_conversion_failed(
    tmp_path: Path,
    effective_settings: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch) as env:
        (env.folder / "analysis.py").write_text(ANALYSIS)
        monkeypatch.setattr(
            env.host.editors, "convert", lambda *a, **k: ConvertResult(1, "Traceback: boom")
        )
        before = tree_digest(env.folder)
        with caplog.at_level(logging.WARNING):
            _refused(env.open(), "conversion_failed")
        assert "boom" in caplog.text
        assert tree_digest(env.folder) == before
        _no_launch(env)


def test_busy_ports_are_no_free_port(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        held.listen()
        port = held.getsockname()[1]
        with editor_app(tmp_path, effective_settings(), monkeypatch, ports=(port,)) as env:
            (env.folder / "analysis.py").write_text(ANALYSIS)
            before = tree_digest(env.folder)
            _refused(env.open(), "no_free_port")
            assert env.host.editors.sessions() == []
            assert tree_digest(env.folder) == before  # the new notebook is removed again


def test_a_failed_launch_keeps_an_existing_notebook(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch) as env:
        (env.folder / "analysis.marimo.py").write_text("import marimo\napp = marimo.App()\n")

        def fail(*_: Any, **__: Any) -> Any:
            raise PluginLaunchError("marimo failed to start", reason="launch_failed")

        monkeypatch.setattr(env.host.editors, "open", fail)
        before = tree_digest(env.folder)
        _refused(env.open(), "launch_failed")
        assert tree_digest(env.folder) == before


def test_a_launch_failure_is_launch_failed(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch) as env:

        def fail(*_: Any, **__: Any) -> Any:
            raise PluginLaunchError("marimo failed to start", reason="launch_failed")

        monkeypatch.setattr(env.host.editors, "open", fail)
        before = tree_digest(env.folder)
        _refused(env.open(), "launch_failed")
        assert env.host.editor_experiments == {}
        assert tree_digest(env.folder) == before  # the created notebook is removed again


# ── Success ──────────────────────────────────────────────────────────────


def test_open_converts_once_returns_the_token_once_and_logs_no_token(
    tmp_path: Path,
    effective_settings: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch) as env:
        (env.folder / "analysis.py").write_text(ANALYSIS)
        before = tree_digest(env.folder)
        with caplog.at_level(logging.DEBUG):
            response = env.open()
        assert response.status_code == 201, response.text
        body = response.json()
        token = body["token_delivery"]["token"]
        assert body["notebook_state"] == "converted" and body["notebook"] == "analysis.marimo.py"
        assert body["project_id"] == env.project_id and body["folder"] == env.folder.name
        assert body["environment"]["kind"] == "project"
        assert token not in body["url_without_token"] and token not in caplog.text
        after = tree_digest(env.folder)
        assert set(after) - set(before) == {"analysis.marimo.py"}
        assert {name: after[name] for name in before} == before
        listed = env.client.get("/v1/plugins").json()
        assert token not in json.dumps(listed)
        (editor,) = listed["editors"]
        assert (editor["project_id"], editor["folder"]) == (env.project_id, env.folder.name)
        again = env.open()
        assert _refused(again, "editor_running")["launch_id"] == body["launch_id"]
        stopped = env.client.delete(f"/v1/plugin-editors/{body['launch_id']}", headers=ORIGIN)
        assert stopped.status_code == 200, stopped.text
        assert env.host.editor_experiments == {}
        reopened = env.open()
        assert reopened.status_code == 201, reopened.text
        assert reopened.json()["notebook_state"] == "existing"
        assert tree_digest(env.folder)["analysis.marimo.py"] == after["analysis.marimo.py"]


def test_open_without_analysis_creates_the_packaged_notebook(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch) as env:
        response = env.open()
        assert response.status_code == 201, response.text
        assert response.json()["notebook_state"] == "created"
        assert "marimo.App" in (env.folder / "analysis.marimo.py").read_text()


def test_the_kernel_gets_the_project_venv_and_no_dotenv(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch) as env:
        assert env.open().status_code == 201
        record = json.loads((env.exe.parent / "record.json").read_text())
        assert f'path = "{(env.root / ".venv").resolve()}"' in record["config"]
        assert "writable = false" in record["config"]
        assert 'dotenv = ["' in record["config"] and "dotenv = []" not in record["config"]
        assert "OMRS_CONNECTION_FILE" not in record["env"]
        assert record["argv"][1] == str((env.folder / "analysis.marimo.py").resolve())


def test_open_responses_conform_to_the_contract(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker

    check = ContractChecker()
    with editor_app(tmp_path, effective_settings(), monkeypatch) as env:
        check.check(env.open(consent=False), 403)
        check.check(env.open(".hidden"), 400)
        check.check(env.open("99-absent-2026-01-01"), 404)
        opened = check.check(env.open(), 201)
        check.check(env.open(), 409)
        check.check(env.client.get("/v1/plugins"), 200)
        check.check(
            env.client.delete(f"/v1/plugin-editors/{opened['launch_id']}", headers=ORIGIN), 200
        )
    assert "openExperimentEditor" in FAMILIES["experiment_library"]


def test_the_plugin_list_names_the_shipped_manifest(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch, register=False) as env:
        listed = env.client.get("/v1/plugins").json()
        assert listed["shipped_manifests"] == [str(MANIFEST.resolve())]
