"""Experiment 35 arm table (design D3) and the scratch ``omrs.jsonc`` values of one arm.

Six arms. Each ablation changes one component against the baseline:

* ``embedding-0.6b`` and ``embedding-8b`` change the embedding model, and build
  their own index;
* ``chunking-off`` empties the tokenizer identity, so the legacy Markdown path
  runs (ADR-063), and builds its own index;
* ``reranker-off`` and ``hybrid`` change one search argument and search the
  baseline index (no new embedding).

Fixed in every arm (model matrix, archived change D12): answers from
``deepseek/deepseek-v4.1-flash-1017`` on OpenRouter at temperature 0 with the
plan seed and one pinned host; metadata extraction ``disabled``; the
``documents`` profile. Key fields hold ``env://`` references only. The local
models come from the plan ``runtime`` block by role, so a model the plan does
not pin cannot run.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments._lib import router_env

BASELINE = "documents-profile-4b"
SEED = 20261101
TEMPERATURE = 0.0
TOP_K = 10
ANSWER_MODEL = "deepseek/deepseek-v4.1-flash-1017"
OPENROUTER_KEY_REF = "env://OPENROUTER_API_KEY"
#: GLM-5.3 on the Z.ai Coding Plan, the ``chat`` panel judge (as the pre-freeze runner).
GLM_MODEL = "glm-5.3"
GLM_BASE_URL = "https://api.z.ai/api/coding/paas/v4"
GLM_KEY_ENV = "OMRS_EXP35_ZAI_KEY"  # gitleaks:allow - a variable name, not a key
GLM_REASONING = "low"
#: The token-aware tokenizer (ADR-063). The Qwen3 embedding family shares it, so
#: every arm keeps this identity and only ``chunking-off`` empties it.
TOKENIZER_MODEL = "Qwen/Qwen3-Embedding-4B"
TOKENIZER_REVISION = "5cf2132abc99cad020ac570b19d031efec650f2b"  # gitleaks:allow (HF revision)
#: One router model at a time: the two judges never load together on 24 GB (D13).
ROUTER_MODELS_MAX = 1

JUDGE_NAMES = ("clef_flash", "granite_guardian", "chat")
#: The main claim checker (GLM-5.3). A failed call stops the run; the others keep an error row.
MAIN_JUDGE = "chat"
#: Plan ``runtime`` role of each local judge model. ``chat`` is hosted.
JUDGE_ROLES: Mapping[str, str] = {
    "clef_flash": "judge-clef-flash",
    "granite_guardian": "judge-granite-guardian",
}
STAGES = ("ingest", "search", "answer", "determinism")


class ArmConfigError(RuntimeError):
    """An arm cannot be configured. The message names the arm, role or judge."""


@dataclass(frozen=True)
class Arm:
    """One arm of the benchmark.

    Attributes:
        name: The arm name, as ``plan.json`` writes it.
        embed_role: The plan ``runtime`` role of the embedding model.
        rerank: The ``rerank`` argument of every search and answer call.
        hybrid: The ``hybrid`` argument of every search and answer call.
        token_aware: Model-token-aware Markdown chunking on (ADR-063).
        index_of: The arm whose index this arm searches.
    """

    name: str
    embed_role: str
    rerank: bool
    hybrid: bool
    token_aware: bool
    index_of: str

    @property
    def owns_index(self) -> bool:
        """True when this arm builds its own index."""
        return self.index_of == self.name


ARMS: dict[str, Arm] = {
    arm.name: arm
    for arm in (
        Arm(BASELINE, "embedding-baseline-4b", True, False, True, BASELINE),
        Arm("embedding-0.6b", "embedding-0.6b", True, False, True, "embedding-0.6b"),
        Arm("embedding-8b", "embedding-8b", True, False, True, "embedding-8b"),
        Arm("reranker-off", "embedding-baseline-4b", False, False, True, BASELINE),
        Arm("chunking-off", "embedding-baseline-4b", True, False, False, "chunking-off"),
        Arm("hybrid", "embedding-baseline-4b", True, True, True, BASELINE),
    )
}


def collection(dataset: str, arm: Arm) -> str:
    """Return the collection an arm searches: one per dataset and index-owning arm."""
    owner = arm.index_of.replace(".", "").replace("-", "_")
    return f"exp35_{dataset}_{owner}"


def search_kwargs(arm: Arm) -> dict[str, bool]:
    """Return the ``rerank`` and ``hybrid`` arguments of every search and answer call."""
    return {"rerank": arm.rerank, "hybrid": arm.hybrid}


def parse_judges(text: str) -> tuple[str, ...]:
    """Return the judge names of a comma list, in order, without repeats.

    Raises:
        ArmConfigError: A name is not a registered 35a judge.
    """
    names = [part.strip() for part in text.split(",") if part.strip()]
    unknown = [name for name in names if name not in JUDGE_NAMES]
    if unknown:
        raise ArmConfigError(f"unknown judge {unknown}; choose from {', '.join(JUDGE_NAMES)}")
    return tuple(dict.fromkeys(names))


def plan_role(plan: Mapping[str, Any], role: str) -> Mapping[str, Any]:
    """Return the plan ``runtime`` model of *role*.

    Raises:
        ArmConfigError: The plan pins no model of that role.
    """
    for model in plan["runtime"]["models"]:
        if model["role"] == role:
            return model
    raise ArmConfigError(
        f"plan.json runtime block has no model with role {role!r}; add it with its "
        "file, SHA-256 and build before this stage runs"
    )


def stage_roles(arm: Arm, stage: str, judges: Sequence[str]) -> list[str]:
    """Return the plan roles a stage loads on the router, in load order."""
    if stage in ("ingest", "search"):
        return [arm.embed_role]
    if stage == "answer":
        return [arm.embed_role, *(JUDGE_ROLES[j] for j in judges if j in JUDGE_ROLES)]
    return []


def settings_values(
    arm: Arm,
    plan: Mapping[str, Any],
    gguf_folder: Path,
    *,
    answer_host: str,
    judges: Sequence[str],
) -> dict[str, Any]:
    """Return the scratch ``omrs.jsonc`` values of one arm.

    Args:
        arm: The arm.
        plan: The parsed ``plan.json``.
        gguf_folder: The folder that holds the GGUF files (``SWEEP_GGUF_DIR``).
        answer_host: The one OpenRouter host that serves every answer.
        judges: The claim judges the answer stage runs.

    Raises:
        ArmConfigError: The plan pins no model for a role this arm needs.
        RouterConfigError: A GGUF file is missing, or OMRS refuses a preset.
    """
    embed = plan_role(plan, arm.embed_role)
    local = [plan_role(plan, JUDGE_ROLES[j]) for j in judges if j in JUDGE_ROLES]
    entries = router_env.model_entries({"runtime": {"models": [embed, *local]}}, gguf_folder)
    tokenizer = (TOKENIZER_MODEL, TOKENIZER_REVISION) if arm.token_aware else ("", "")
    values: dict[str, Any] = {
        "embed_provider": "llamacpp",
        "local_backend": "llamacpp",
        "llamacpp_router_server": "managed",
        "llamacpp_router_url": router_env.ROUTER_URL,
        "llamacpp_router_models_max": ROUTER_MODELS_MAX,
        "llamacpp_embed_model": router_env.model_name(embed),
        "rag_profile": "documents",
        # The resolved identity the arm needs. The file reads a blank value as not
        # set, so ``chunking-off`` gets its blanks from :func:`env_overrides`.
        "embedding": {"tokenizer_model": tokenizer[0], "tokenizer_revision": tokenizer[1]},
        "metadata": {"extraction_mode": "disabled"},
        "openrouter_api_key": OPENROUTER_KEY_REF,
        "answer": {
            "provider": "openrouter",
            "model": ANSWER_MODEL,
            "temperature": TEMPERATURE,
            "seed": SEED,
            "allowed_hosts": answer_host,
            "verify_claims": False,
        },
        "llamacpp_models": entries,
    }
    if "chat" in judges:
        values["openai_compatible_base_url"] = GLM_BASE_URL
        values["openai_compatible_api_key"] = f"env://{GLM_KEY_ENV}"
    return values


def env_overrides(arm: Arm) -> dict[str, str]:
    """Return the environment values an arm needs beyond the scratch file.

    ``omrs.jsonc`` reads a blank value as not set, so only the environment can
    empty the tokenizer identity (ADR-063: both fields empty give the legacy path).
    """
    if arm.token_aware:
        return {}
    return {"EMBEDDING__TOKENIZER_MODEL": "", "EMBEDDING__TOKENIZER_REVISION": ""}


def without_keys(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return *values* without key fields.

    OMRS resolves a key reference to the key itself, so a resolved-value check
    must never see a key field: the comparison means nothing and its message
    would print the key (the Experiment 48 fix of 2026-11-10).
    """
    return {k: v for k, v in values.items() if not k.endswith("_api_key")}


def judge_block(answer_block: Any, name: str, plan: Mapping[str, Any]) -> Any:
    """Return a copy of the answer block that runs the claim judge *name*.

    The local judges keep the strategy defaults, as the pre-freeze AggreFact
    runs did. The ``chat`` judge is GLM-5.3 at temperature 0, the plan seed and
    reasoning ``low`` (D12).
    """
    if name in JUDGE_ROLES:
        model = router_env.model_name(plan_role(plan, JUDGE_ROLES[name]))
        update: dict[str, Any] = {"verify_provider": "local", "verify_model": model}
    else:
        update = {
            "verify_provider": "openai_compatible",
            "verify_model": GLM_MODEL,
            "verify_reasoning": GLM_REASONING,
            "verify_temperature": TEMPERATURE,
            "verify_seed": SEED,
        }
    return answer_block.model_copy(update={"verify_claims": True, "verify_judge": name, **update})
