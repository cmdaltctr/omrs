"""``GET /v1/llamacpp/router`` lists the roles that no list entry can serve.

The roles come from ``derive_roles`` alone; the route adds no hand list. A fake
router ``llama-server`` stands in for the real one and no model loads.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit import test_web_llamacpp_router_support as support  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import ContractChecker  # noqa: E402

from omrs.config.llamacpp_models import EMBED_MODEL  # noqa: E402

harness = support.harness
rig = support.rig

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")

OLD_EMBED = "qwen3-embedding:0.6b"


def test_a_default_install_has_no_problem(rig: Any) -> None:
    with rig() as r:
        assert r.get()["problems"] == []


def test_an_unlisted_embeddings_model_is_one_problem_with_the_rule_text(rig: Any) -> None:
    with rig(llamacpp_embed_model=OLD_EMBED) as r:
        assert r.get()["problems"] == [
            {
                "role": "embeddings",
                "reason": "model-not-listed",
                "text": "The embeddings model is not in the list.",
            }
        ]


def test_an_embedding_entry_in_a_text_role_is_a_role_mismatch(rig: Any) -> None:
    with rig(llamacpp_chat_model=EMBED_MODEL) as r:
        (problem,) = r.get()["problems"]
        assert (problem["role"], problem["reason"]) == ("classification", "role-mismatch")
        assert problem["text"] == "An embedding entry cannot serve the classification role."


def test_a_problem_text_never_names_the_model(rig: Any) -> None:
    with rig(llamacpp_embed_model=OLD_EMBED) as r:
        assert OLD_EMBED not in str(r.get()["problems"])


def test_an_external_router_reports_no_problem(rig: Any) -> None:
    with rig(llamacpp_router_server="external", llamacpp_embed_model=OLD_EMBED) as r:
        assert r.get()["problems"] == []


def test_every_router_answer_carries_the_problems_and_conforms(rig: Any) -> None:
    check = ContractChecker()
    with rig(llamacpp_embed_model=OLD_EMBED) as r:
        check.check(r.client.get(support.URL), 200)
        saved = r.put({"models_max": 2})
        check.check(saved, 200)
        assert saved.json()["problems"][0]["reason"] == "model-not-listed"
