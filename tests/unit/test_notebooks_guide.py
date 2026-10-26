"""Notebook guide, plugin absence and no embedded editor (task 8.7).

The workspace starts and serves document and graph routes when no plugin
is registered, and starts no process. Plugin routes then report "not
registered" without an error. No source under ``web/src`` or
``src/omrs/transports`` embeds the editor, and no document claims an
embedded editor. Every path, route, port, variable and command that the
notebook guide cites exists in the code it describes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    lance_store,
    login,
    make_engine,
    seed,
)
from tests.unit.test_web_guides_support import (  # noqa: E402
    GUIDES,
    REPO,
    broken_links,
    code_spans,
    links_to,
    missing_repository_paths,
    undeclared_routes,
)

from omrs.core.workspace.experiment_editor import JUPYTEXT_HINT  # noqa: E402
from omrs.integrations import process_launcher  # noqa: E402
from omrs.transports.api.app import create_app  # noqa: E402
from omrs.transports.api.lifespan import DEFAULT_PLUGIN_PORTS, WebConfig  # noqa: E402
from omrs.transports.api.runs_wiring import run_service_factory  # noqa: E402
from omrs.transports.api.security import AccessPolicy  # noqa: E402
from omrs.transports.api.tool_environment import ToolDetector  # noqa: E402

GUIDE = GUIDES / "notebooks.md"
PLUGIN = REPO / "plugins" / "marimo"
# The manifest ships inside the package (ADR-099); the README and starter stay in PLUGIN.
MANIFEST = REPO / "src" / "omrs" / "core" / "plugins" / "shipped" / "marimo" / "manifest.json"
RECORDS_GUIDE = GUIDES / "experiment-records.md"
FULL_ACCESS = "## Full access from the Library"
CONSENT_TEXT = (
    "This opens `analysis.marimo.py` in marimo in a new tab. The notebook runs in this "
    "project's Python environment with your full file and network access, like any "
    "program you start. OMRS does not sandbox it. Cells do not run until you run them. "
    "OMRS adds `analysis.marimo.py` and marimo adds `__marimo__/` in the experiment "
    "folder. Add both to your `.gitignore`."
)
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")
_EMBED = re.compile(r"\bembed(?:s|ded)?\b", re.I)
_EDITOR = re.compile(r"\b(?:editor|notebook|marimo)\b", re.I)
_NEGATION = re.compile(r"\b(?:never|not|no|without)\b", re.I)


def _text() -> str:
    return GUIDE.read_text(encoding="utf-8")


# ── The application works without the plugin ──────────────────────────


def _app(tmp_path: Path, engine: Any) -> tuple[Any, AccessPolicy]:
    config = WebConfig(workspace=tmp_path / "ws", port=8765, static_dir=None)
    policy = AccessPolicy.for_launch(config.host, config.port)
    app = create_app(
        config,
        policy=policy,
        engine_factory=lambda: engine,
        run_service_factory=run_service_factory,
    )
    return app, policy


def test_workspace_serves_documents_and_graphs_without_a_plugin(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No registered plugin: ordinary routes work and no process starts."""

    def no_process(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the workspace started a process without a plugin request")

    monkeypatch.setattr(process_launcher.subprocess, "Popen", no_process)
    store = lance_store(tmp_path)
    seed(store, "notes", str(tmp_path / "a.md"), 2)
    app, policy = _app(tmp_path, make_engine(store, effective_settings()))
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        # The marimo card's `uv tool dir` lookup is a separate, tested process.
        client.app.state.runtime.tools = ToolDetector(find=lambda: None)  # type: ignore[attr-defined]
        plugins = client.get("/v1/plugins")
        recheck = client.post("/v1/plugins/marimo/recheck", headers=ORIGIN)
        collections = client.get("/v1/collections")
        documents = client.get("/v1/collections/notes/documents")
        operations = client.get("/v1/pipeline-operations")
        pipelines = client.get("/v1/pipelines")
        templates = client.get("/v1/pipeline-templates")
        runs = client.get("/v1/runs")
    body = plugins.json()
    assert plugins.status_code == 200
    assert body["plugins"] == [] and body["editors"] == []
    assert JUPYTEXT_HINT in body["install_hint"]
    assert body["trust_notice"]
    assert recheck.status_code == 404
    assert recheck.json() == {"status": "error", "message": "Unknown plugin."}
    for response in (collections, documents, operations, pipelines, templates, runs):
        assert response.status_code == 200, response.text
    assert [row["name"] for row in collections.json()] == ["notes"]
    assert operations.json()["operations"]
    assert {t["name"] for t in templates.json()["templates"]} >= {"search", "answer"}


# ── The editor is never embedded ───────────────────────────────────────


def _source_files() -> list[Path]:
    web = [
        path
        for path in (REPO / "web" / "src").rglob("*")
        if path.suffix in {".ts", ".tsx", ".js", ".jsx", ".css", ".html"}
    ]
    transports = [
        path
        for path in (REPO / "src" / "omrs" / "transports").rglob("*")
        if path.suffix in {".py", ".yaml", ".md"} and "static" not in path.parts
    ]
    return [*web, REPO / "web" / "index.html", *transports]


def test_no_source_embeds_the_editor() -> None:
    """No frame or embed element in the frontend or transport sources."""
    files = _source_files()
    assert any(path.suffix == ".tsx" for path in files)
    pattern = re.compile(r"<\s*(?:iframe|frame|embed|object)\b|['\"]iframe['\"]", re.I)
    offenders = [
        str(path.relative_to(REPO))
        for path in files
        if pattern.search(path.read_text(encoding="utf-8", errors="replace"))
    ]
    assert offenders == []


def _documents() -> list[Path]:
    return [
        *sorted(GUIDES.glob("*.md")),
        REPO / "README.md",
        PLUGIN / "README.md",
        REPO / "src" / "omrs" / "transports" / "api" / "README.md",
        *[path for path in (REPO / "web" / "src").rglob("*.tsx")],
    ]


def test_no_document_or_view_claims_an_embedded_editor() -> None:
    """A sentence that joins "embed" and "editor" must deny the embedding."""
    claims = []
    for path in _documents():
        for sentence in _SENTENCE.findall(path.read_text(encoding="utf-8")):
            if _EMBED.search(sentence) and _EDITOR.search(sentence):
                if not _NEGATION.search(sentence):
                    claims.append(f"{path.relative_to(REPO)}: {sentence.strip()}")
    assert claims == []


def test_guides_say_the_editor_opens_in_a_separate_tab() -> None:
    for text in (_text(), (PLUGIN / "README.md").read_text(encoding="utf-8")):
        assert "separate browser tab" in text
        assert "never embeds the editor" in text


# ── Every citation of the guide exists ─────────────────────────────────


def test_cited_paths_routes_and_links_exist() -> None:
    text = _text()
    assert missing_repository_paths(text) == []
    assert undeclared_routes(text) == []
    assert broken_links(GUIDE) == []
    assert broken_links(PLUGIN / "README.md") == []


def test_cited_ports_variables_and_range_match_the_code() -> None:
    text = _text()
    ports = [int(port) for port in re.findall(r"\b(27\d\d)\b", text)]
    assert tuple(ports) == DEFAULT_PLUGIN_PORTS
    notebook = (PLUGIN / "starter_notebook.py").read_text(encoding="utf-8")
    variables = {span for span in code_spans(text) if span.startswith("OMRS_")}
    manual = {"OMRS_API_URL", "OMRS_TOKEN_FILE", "OMRS_TOKEN", "OMRS_EXPERIMENT_CONTEXT"}
    assert variables == {*manual, "OMRS_CONNECTION_FILE"}
    assert all(name in notebook for name in variables)
    assert all(name not in process_launcher.ENV_ALLOWLIST for name in variables)
    # OMRS delivers only the connection file path to the editor it starts.
    assert process_launcher.LAUNCH_ENV_ALLOWLIST == ("OMRS_CONNECTION_FILE",)
    assert "omrs_connection.json" in text and "omrs_connection.json" in notebook
    assert "gap" not in text.lower()
    assert "chmod 600" in notebook and 'output" / "runs"' in notebook
    tested = json.loads(MANIFEST.read_text(encoding="utf-8"))["tool"]
    expected = f">={tested['tested_versions']['minimum']},<{tested['tested_versions']['below']}"
    assert f"`{expected}`" in text


def _install_command() -> str:
    """The card's install command, built from the shipped manifest range."""
    tested = json.loads(MANIFEST.read_text(encoding="utf-8"))["tool"]["tested_versions"]
    return f'uv tool install "marimo>={tested["minimum"]},<{tested["below"]}" --with jupytext'


def test_cited_commands_match_the_plugin_and_the_cli() -> None:
    text = _text()
    readme = (PLUGIN / "README.md").read_text(encoding="utf-8")
    install = _install_command()
    assert install == JUPYTEXT_HINT
    for command in (install, "uv tool upgrade marimo", "uv tool uninstall marimo"):
        assert command in text and command in readme
    assert "command -v marimo" in text and "command -v marimo" in readme
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    probe = manifest["recipes"]["probe"]
    assert f"marimo {' '.join(probe['version_args'])}" in text
    assert f"marimo {' '.join(probe['help_args'])}" in text
    assert "omrs web --experiment-root" in text


def _section(text: str, heading: str) -> str:
    assert heading in text, f"no section {heading!r}"
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


@pytest.mark.parametrize("document", [GUIDE, PLUGIN / "README.md"], ids=["guide", "readme"])
def test_install_section_puts_the_card_first_and_the_command_second(document: Path) -> None:
    """The card step comes first; the terminal command and its path lookup follow."""
    text = document.read_text(encoding="utf-8")
    section = _section(text, "\n## Install marimo\n")
    card = section.find("marimo card")
    command = section.find(_install_command())
    lookup = section.find("command -v marimo")
    assert -1 < card < command < lookup, (card, command, lookup)
    assert "**External tools**" in section and "**Install**" in section
    assert "Integrations" in section and "Code editor" in section
    for retired in ("never installs, upgrades or replaces marimo", "never runs `uvx`"):
        assert retired not in text
    assert "## Install marimo outside OMRS" not in text


def test_guides_say_the_app_never_registers_and_upgrade_keeps_the_range() -> None:
    for text in (_text(), (PLUGIN / "README.md").read_text(encoding="utf-8")):
        assert "never registers marimo on its own" in text
        assert "uv keeps the version range of the install" in text
        assert "found" in _section(text, "## Register")
    assert "`detected_executables`" in _text()
    assert "`tool_install_running`" in _text() and "`editor-running`" in _text()


def test_guide_is_linked_from_the_web_guide_and_the_plugin_readme() -> None:
    assert links_to(GUIDES / "web-workspace.md", "notebooks.md")
    assert links_to(PLUGIN / "README.md", "notebooks.md")
    assert links_to(REPO / "README.md", "notebooks.md")


# ── Full access from the Library (ADR-099) ─────────────────────────────


def _full_access_section() -> str:
    text = _text()
    assert FULL_ACCESS in text, f"the guide has no section {FULL_ACCESS!r}"
    return text.split(FULL_ACCESS, 1)[1].split("\n## ", 1)[0]


def test_guide_names_the_shipped_manifest_and_new_registration() -> None:
    text = _text()
    assert "`src/omrs/core/plugins/shipped/marimo/manifest.json`" in text
    assert "`shipped_manifests`" in text
    assert "register" in text and "after an upgrade" in text


def test_full_access_section_states_the_rules_of_a_library_launch() -> None:
    section = " ".join(_full_access_section().split())
    for phrase in (
        CONSENT_TEXT,
        JUPYTEXT_HINT,
        "experiments/**/analysis.marimo.py",
        "experiments/**/__marimo__/",
        "dotenv = []",
        "runtime.dotenv",
        "`python_mismatch`",
        "`project_config_runs_on_open`",
        "package panel",
        "PYTHONPATH",
        "analysis.py changed after this notebook was made",
    ):
        assert phrase in section, f"the section does not say {phrase!r}"


def test_changed_guides_have_no_em_dash() -> None:
    for path in (GUIDE, RECORDS_GUIDE, PLUGIN / "README.md"):
        assert "\u2014" not in path.read_text(encoding="utf-8"), path.name


def test_experiment_records_guide_links_to_the_full_access_section() -> None:
    text = RECORDS_GUIDE.read_text(encoding="utf-8")
    assert "### Open an experiment in marimo" in text
    assert "(notebooks.md#full-access-from-the-library)" in text
    assert broken_links(RECORDS_GUIDE) == []
