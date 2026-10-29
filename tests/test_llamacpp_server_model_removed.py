"""The separate model of OMRS's own llama.cpp server is gone (ADR-108, design D5).

OMRS's server loads the Chat model, so the old setting could only drift from
it. A leftover variable fails start-up and names its replacement, as the
removal of ``OCR_WORKER_COMMAND`` does.
"""

from __future__ import annotations

import pytest

from omrs.config import Settings, check_legacy_env_vars
from omrs.core.settings import EffectiveSettings


def test_a_leftover_variable_fails_and_names_the_replacement() -> None:
    with pytest.raises(ValueError) as refused:
        check_legacy_env_vars({"LLAMACPP_SERVER_MODEL": "/models/old.gguf"})

    message = str(refused.value)
    for name in ("LLAMACPP_SERVER_MODEL", "ANSWER__PROVIDER", "ANSWER__MODEL"):
        assert name in message
    assert "LLAMACPP_CHAT_SERVER" in message
    assert "/models/old.gguf" not in message


def test_neither_settings_model_has_the_field() -> None:
    assert "llamacpp_server_model" not in Settings.model_fields
    assert "llamacpp_server_model" not in EffectiveSettings.model_fields
