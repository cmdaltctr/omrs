"""The router example in the configuration guide parses and loads (document-reading-routers, 2.5).

The test takes the ``jsonc`` block under "Decision models and document routers"
in ``docs/guides/configuration.md``, writes it as ``omrs.jsonc`` in a temporary
config folder and reads it the way the server does.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from omrs.config import Settings, provenance
from omrs.config.settings_file import read_settings_file
from omrs.config.user_config import parse_jsonc

GUIDE = Path(__file__).resolve().parents[2] / "docs" / "guides" / "configuration.md"
HEADING = "#### Decision models and document routers"


def example_block() -> str:
    text = GUIDE.read_text(encoding="utf-8")
    section = text.split(HEADING, 1)[1].split("\n### ", 1)[0]
    found = re.search(r"```jsonc\n(?P<body>.*?)\n```", section, re.S)
    assert found is not None, "no jsonc block under the router heading"
    return found["body"]


@pytest.fixture(autouse=True)
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.delenv("DOCUMENT_ROUTER", raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return root


def test_the_example_is_json_with_comments() -> None:
    data = parse_jsonc(example_block())
    assert sorted(data) == ["decision_models", "document_router", "document_routers"]


def test_the_example_loads_with_no_problem(folder: Path) -> None:
    (folder / "omrs.jsonc").write_text(example_block(), encoding="utf-8")

    settings = Settings(_env_file=None)

    assert read_settings_file().problems == ()
    assert sorted(settings.decision_models) == ["clef-local", "jev"]
    assert settings.decision_models["jev"].key == "env://TYPESAFE_API_KEY"
    router = settings.document_routers["handwriting"]
    assert (router.model, router.threshold, router.send_off_machine) == ("clef-local", 0.172, False)
    assert settings.document_router == "handwriting"
    assert router.model in settings.decision_models
