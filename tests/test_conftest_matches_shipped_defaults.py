"""Test, CI and local-CI provider values equal the shipped defaults (one-llamacpp-router, 9.2).

``tests/conftest.py``, ``.github/workflows/ci.yml`` and ``scripts/local_ci.sh`` may
set provider, model and URL values. Each value must equal the shipped default,
which this test reads from ``Settings`` (field defaults and ``defaults.yaml``) in
a clean environment. A copy of a default in the test would drift, so none exists.
No file sets a value that names Ollama; the opt-in ``ollama_backend`` and
``ollama_embed_model`` fixtures of ``conftest.py`` are the only places that may.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from omrs.config import Settings, provenance

ROOT = Path(__file__).resolve().parent.parent
CONFTEST = ROOT / "tests" / "conftest.py"
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"
LOCAL_CI = ROOT / "scripts" / "local_ci.sh"

#: Environment names that choose a provider, a model or a URL. API keys are secrets, not choices.
KEY_PATTERN = re.compile(r"(PROVIDER|BACKEND|MODEL|URL)$")
#: The conftest fixtures that may set Ollama values (opt-in per test).
OPT_IN_FIXTURES = ("ollama_backend", "ollama_embed_model")
#: Name of the conftest dict that holds the environment every test starts with.
ENV_DICT = "LOCAL_ENV"


def is_choice(name: str) -> bool:
    """Return True when *name* is a provider, model or URL environment name."""
    return bool(KEY_PATTERN.search(name)) and "API_KEY" not in name


def conftest_values(source: str) -> dict[str, str]:
    """Return the provider, model and URL values *source* (a conftest) sets.

    Reads the module-level ``LOCAL_ENV`` dict and every ``setenv``/``setdefault``
    call with two string literals. Code inside the opt-in Ollama fixture is skipped.
    """
    tree = ast.parse(source)
    found: dict[str, str] = {}
    skipped = {
        id(node)
        for fixture in ast.walk(tree)
        if isinstance(fixture, ast.FunctionDef) and fixture.name in OPT_IN_FIXTURES
        for node in ast.walk(fixture)
    }
    for node in ast.walk(tree):
        if id(node) in skipped:
            continue
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == ENV_DICT for t in node.targets
        ):
            found.update(ast.literal_eval(node.value))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            args = node.args
            if (
                node.func.attr in ("setenv", "setdefault")
                and len(args) >= 2
                and all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in args[:2])
            ):
                found[args[0].value] = args[1].value  # type: ignore[attr-defined]
    return {name: value for name, value in found.items() if is_choice(name)}


def ci_values(text: str) -> dict[str, str]:
    """Return the provider, model and URL values every ``env:`` block of a workflow sets."""
    found: dict[str, str] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "env" and isinstance(value, dict):
                    found.update({str(k): str(v) for k, v in value.items()})
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(yaml.safe_load(text))
    return {name: value for name, value in found.items() if is_choice(name)}


_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)=(\S*)", re.MULTILINE)


def shell_values(text: str) -> dict[str, str]:
    """Return the provider, model and URL values a shell script assigns."""
    found = {name: value.strip("\"'") for name, value in _ASSIGNMENT.findall(text)}
    return {name: value for name, value in found.items() if is_choice(name)}


@pytest.fixture
def shipped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Return a resolver for the shipped default of an environment name.

    The settings load with no environment value for the name, no ``.env`` and an
    empty ``omrs.jsonc`` folder, so only field defaults and ``defaults.yaml`` apply.
    """
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))

    for name in list(os.environ):
        if is_choice(name) or name.startswith(("ANSWER__", "METADATA__")):
            monkeypatch.delenv(name)

    def default_of(name: str) -> str:
        value: Any = Settings(_env_file=None)
        for part in name.lower().split("__"):
            if not hasattr(value, part):
                raise AssertionError(f"{name} names no setting ({part!r} is unknown)")
            value = getattr(value, part)
        return str(value)

    return default_of


def mismatches(values: dict[str, str], default_of: Any) -> list[str]:
    """Return one line for each value that differs from its shipped default."""
    lines = []
    for name, value in sorted(values.items()):
        if "ollama" in name.lower() or "ollama" in value.lower():
            lines.append(f"{name}={value!r} names Ollama")
            continue
        expected = default_of(name)
        if value != expected:
            lines.append(f"{name}={value!r}, shipped default is {expected!r}")
    return lines


def test_conftest_sets_the_llamacpp_defaults(shipped) -> None:
    values = conftest_values(CONFTEST.read_text(encoding="utf-8"))
    assert {"EMBED_PROVIDER", "LOCAL_BACKEND", "LLAMACPP_EMBED_MODEL"} <= set(values), values
    assert mismatches(values, shipped) == []


def test_ci_workflow_sets_only_shipped_defaults(shipped) -> None:
    values = ci_values(CI_YML.read_text(encoding="utf-8"))
    assert mismatches(values, shipped) == []


def test_local_ci_script_sets_only_shipped_defaults(shipped) -> None:
    values = shell_values(LOCAL_CI.read_text(encoding="utf-8"))
    assert mismatches(values, shipped) == []


def test_slow_gate_message_names_the_default_router_address(shipped) -> None:
    """The slow-suite skip message and the default router URL agree."""
    default = shipped("LLAMACPP_ROUTER_URL")
    address = re.search(r"//([^/]+)/", default).group(1)  # type: ignore[union-attr]
    assert f"Slow tests skipped: no llama.cpp router at {address}" in CI_YML.read_text(
        encoding="utf-8"
    )


# The cases below pin the scanners, so a mismatch in any of the three files is caught.


@pytest.mark.parametrize(
    ("scan", "text"),
    [
        (conftest_values, 'import os\nLOCAL_ENV = {"LOCAL_BACKEND": "ollama"}\n'),
        (conftest_values, 'def f(m):\n    m.setenv("EMBED_PROVIDER", "cloud")\n'),
        (conftest_values, 'os.environ.setdefault("LLAMACPP_EMBED_MODEL", "other")\n'),
        (ci_values, "jobs:\n  a:\n    steps:\n      - env:\n          LOCAL_BACKEND: ollama\n"),
        (ci_values, "jobs:\n  a:\n    env:\n      EMBED_PROVIDER: cloud\n"),
        (shell_values, "LOCAL_BACKEND=ollama \\\n  uv run pytest\n"),
        (shell_values, "export LLAMACPP_ROUTER_URL=http://127.0.0.1:9/v1\n"),
    ],
)
def test_scanners_find_a_wrong_value(scan, text, shipped) -> None:
    found = mismatches(scan(text), shipped)
    assert found, f"{scan.__name__} missed a wrong value in {text!r}"


def test_opt_in_fixture_is_the_only_place_ollama_may_appear(shipped) -> None:
    source = (
        'def ollama_backend(m):\n    m.setenv("LOCAL_BACKEND", "ollama")\n'
        'def other(m):\n    m.setenv("LOCAL_BACKEND", "ollama")\n'
    )
    assert conftest_values(source) == {"LOCAL_BACKEND": "ollama"}
    only_fixture = 'def ollama_backend(m):\n    m.setenv("LOCAL_BACKEND", "ollama")\n'
    assert conftest_values(only_fixture) == {}


def test_a_name_with_no_setting_is_refused(shipped) -> None:
    with pytest.raises(AssertionError, match="names no setting"):
        shipped("NO_SUCH_PROVIDER")
