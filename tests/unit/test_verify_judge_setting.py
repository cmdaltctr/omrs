"""The ``answer.verify_judge`` setting (task 8.3; spec ``claim-judge-strategies``).

It defaults to ``chat``, resolves through the normal source order with
``ANSWER__VERIFY_JUDGE`` as its environment name, follows the profile overlay
of the other ``verify_*`` values, locks on its own and is refused at startup
when no strategy of that name is registered.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omrs.compose_providers import locked_fields
from omrs.config import Settings
from omrs.config.settings_file_write import ALLOWED_KEYS
from omrs.core.answer.settings import AnswerSettings
from omrs.core.settings import AnswerBlock, EffectiveSettings


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("model", [AnswerSettings, AnswerBlock])
def test_the_default_is_the_chat_judge(model: type) -> None:
    assert model().verify_judge == "chat"


def test_omrs_jsonc_sets_the_judge(config_dir: Path) -> None:
    (config_dir / "omrs.jsonc").write_text(json.dumps({"answer": {"verify_judge": "clef_flash"}}))
    assert Settings(_env_file=None).answer.verify_judge == "clef_flash"


def test_the_environment_sets_and_locks_only_the_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANSWER__VERIFY_JUDGE", "granite_guardian")
    settings = Settings(_env_file=None)
    assert settings.answer.verify_judge == "granite_guardian"
    locked = locked_fields(settings, settings.provider_explicit)
    assert locked.get("answer.verify_judge") == "environment"
    assert "answer.verify_model" not in locked and "answer.verify_provider" not in locked


def test_the_page_may_write_the_judge() -> None:
    assert "answer.verify_judge" in ALLOWED_KEYS


def test_the_judge_reaches_effective_settings() -> None:
    from omrs.compose import settings_to_effective

    settings = Settings(_env_file=None, answer={"verify_judge": "clef_flash"})
    assert settings_to_effective(settings).answer.verify_judge == "clef_flash"


def test_a_profile_overlays_the_judge() -> None:
    from omrs.core.profiles.resolver import _bundle_to_effective

    base = EffectiveSettings()
    overlaid = _bundle_to_effective(
        "documents", {"answer": {"verify_judge": "clef_flash"}}, base=base
    )
    assert overlaid.answer.verify_judge == "clef_flash"
    kept = _bundle_to_effective("documents", {"answer": {}}, base=base)
    assert kept.answer.verify_judge == "chat"


def test_the_environment_beats_the_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    from omrs.core.profiles.resolver import _bundle_to_effective

    monkeypatch.setenv("ANSWER__VERIFY_JUDGE", "granite_guardian")
    overlaid = _bundle_to_effective(
        "documents", {"answer": {"verify_judge": "clef_flash"}}, base=None
    )
    assert overlaid.answer.verify_judge == "granite_guardian"


def test_an_unknown_judge_fails_startup_naming_every_strategy() -> None:
    """Scenario "Unknown strategy"."""
    from omrs.compose_answer import validate_verify_provider

    settings = Settings(_env_file=None, answer={"verify_judge": "foo"})
    with pytest.raises(ValueError) as caught:
        validate_verify_provider(settings)
    message = str(caught.value)
    assert "foo" in message
    assert all(name in message for name in ("chat", "clef_flash", "granite_guardian"))


def test_a_known_judge_passes_startup() -> None:
    from omrs.compose_answer import validate_verify_provider

    validate_verify_provider(Settings(_env_file=None, answer={"verify_judge": "clef_flash"}))
