"""The Library editor refusal reasons agree across layers (open-experiment-in-marimo, D5).

The contract enum, the route's message map and the reasons that the core
launch checks raise must stay in step: a reason in one list and not the
other reaches the browser without a plain line or fails the contract.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

pytest.importorskip("fastapi")

from omrs.transports.api.routes.experiment_editor import EDITOR_REASONS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "src" / "omrs" / "transports" / "api" / "openapi.yaml"
CORE = ROOT / "src" / "omrs" / "core" / "workspace" / "experiment_editor.py"


def _contract_reasons() -> set[str]:
    schemas = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))["components"]["schemas"]
    return set(schemas["ExperimentEditorRefused"]["properties"]["reason"]["enum"])


def _core_reasons() -> set[str]:
    """Return the first string argument of every ``EditorRefusal(...)`` call in the core module."""
    tree = ast.parse(CORE.read_text(encoding="utf-8"))
    return {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "EditorRefusal"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }


def test_route_messages_cover_exactly_the_contract_reasons() -> None:
    assert set(EDITOR_REASONS) == _contract_reasons()


def test_every_core_refusal_reason_has_a_route_message() -> None:
    core = _core_reasons()
    assert core, "no EditorRefusal reasons found in the core module"
    assert core <= set(EDITOR_REASONS)
