"""Experiment 35 setup table (design D28) and the scratch ``omrs.jsonc`` values of one setup.

Four factors make the setups (pre-registration section 3):

* embedder ``0.6b``, ``4b`` or ``8b`` (Qwen3-Embedding);
* chunk size ``512``, ``1024`` or ``2048`` Qwen3 tokens, overlap 15%;
* reranker ``off``, ``0.6b``, ``4b`` or ``8b`` (Qwen3-Reranker on llama.cpp);
* hybrid search ``off`` or ``on`` (BM25 with reciprocal rank fusion).

A setup is named ``e<embedder>-c<chunk>-r<reranker>-h<hybrid>``. The embedder
and the chunk size make its index ``e<embedder>-c<chunk>``: 9 indexes, each
searched by 8 setups, 72 search setups in all. The 15 answer setups use the
embedder and reranker sizes the selection rule picks (section 14.1): 12 crossed
setups and 3 token-matched ``-t20k`` setups (reranker on, hybrid on).

Fixed in every setup: answers from ``deepseek/deepseek-v4.1-flash-1017`` on
OpenRouter at temperature 0, one round of 131,072 characters; metadata
extraction ``disabled``; the ``documents`` profile; the Qwen3 tokenizer. Seeds
and the P10 and P11 pins are read from ``plan.json`` (``seeds`` and ``pins``),
never from code. Key fields hold ``env://`` references only. Local models come
from the plan ``runtime`` block by role.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments._lib import router_env

TEMPERATURE = 0.0
TOP_K = 10
ANSWER_MODEL = "deepseek/deepseek-v4.1-flash-1017"
OPENROUTER_KEY_REF = "env://OPENROUTER_API_KEY"
#: GLM-5.3 on the Z.ai Coding Plan, the ``chat`` claim checker.
GLM_MODEL = "glm-5.3"
GLM_BASE_URL = "https://api.z.ai/api/coding/paas/v4"
GLM_KEY_ENV = "OMRS_EXP35_ZAI_KEY"  # gitleaks:allow - a variable name, not a key
GLM_REASONING = "low"
#: The token-aware tokenizer (ADR-063). Every setup chunks with it.
TOKENIZER_MODEL = "Qwen/Qwen3-Embedding-4B"
TOKENIZER_REVISION = "5cf2132abc99cad020ac570b19d031efec650f2b"  # gitleaks:allow (HF revision)
#: Answer budget (design D30): one round, 131,072 characters.
ANSWER_CONTEXT_WINDOW = 131072
ANSWER_MAX_ROUNDS = 1

#: Starting concurrency and attempt values (design D18). Task 9.2 replaces them
#: with the measured values before the freeze.
CONCURRENCY_DEFAULTS: Mapping[str, int] = {
    "answer_concurrency": 16,
    "chat_concurrency": 4,
    "ragas_concurrency": 16,
    "classify_concurrency": 16,
    "rate_limit_attempts": 6,
}

EMBEDDERS = ("0.6b", "4b", "8b")
CHUNKS = (512, 1024, 2048)
RERANKERS = ("off", "0.6b", "4b", "8b")
HYBRIDS = ("off", "on")
#: Chunk overlap at 15% of the chunk size.
OVERLAPS: Mapping[int, int] = {512: 77, 1024: 154, 2048: 307}
EMBED_ROLES: Mapping[str, str] = {
    "0.6b": "embedding-0.6b",
    "4b": "embedding-baseline-4b",
    "8b": "embedding-8b",
}
RERANK_ROLES: Mapping[str, str] = {s: f"reranker-{s}" for s in ("0.6b", "4b", "8b")}

JUDGE_NAMES = ("clef_flash", "chat")
#: The main claim checker (GLM-5.3).
MAIN_JUDGE = "chat"
#: Plan ``runtime`` role of each local judge model. ``chat`` is hosted.
JUDGE_ROLES: Mapping[str, str] = {"clef_flash": "judge-clef-flash"}

#: The kind of each stage ``run_arms.py`` can run: ``index`` (one index, shared
#: by its 8 setups), ``search`` or ``answer`` (one setup, own folder). A later
#: stage adds one line here and one line to ``run_arms.STAGE_TABLE``.
STAGE_KINDS: Mapping[str, str] = {"ingest": "index", "seal": "index"}
STAGES = tuple(STAGE_KINDS)
INDEX_STAGES = frozenset(s for s, kind in STAGE_KINDS.items() if kind == "index")

_SETUP = re.compile(r"^e(0\.6b|4b|8b)-c(512|1024|2048)-r(off|0\.6b|4b|8b)-h(off|on)(-t20k)?$")
_INDEX = re.compile(r"^e(0\.6b|4b|8b)-c(512|1024|2048)$")


class ArmConfigError(RuntimeError):
    """A setup cannot be configured. The message names the setup, role, key or judge."""


@dataclass(frozen=True)
class Setup:
    """One setup of the factorial.

    Attributes:
        embedder: ``0.6b``, ``4b`` or ``8b``.
        chunk: Chunk size in Qwen3 tokens.
        reranker: ``off`` or a reranker size.
        hybrid: ``off`` or ``on``.
        t20k: A token-matched answer setup (evidence cut at 20,480 tokens).
    """

    embedder: str
    chunk: int
    reranker: str
    hybrid: str
    t20k: bool = False

    @property
    def name(self) -> str:
        """Return ``e<embedder>-c<chunk>-r<reranker>-h<hybrid>[-t20k]``."""
        tail = "-t20k" if self.t20k else ""
        return f"e{self.embedder}-c{self.chunk}-r{self.reranker}-h{self.hybrid}{tail}"

    @property
    def index(self) -> str:
        """Return the index name ``e<embedder>-c<chunk>``."""
        return f"e{self.embedder}-c{self.chunk}"

    @property
    def rerank(self) -> bool:
        """Return the ``rerank`` argument of every search and answer call."""
        return self.reranker != "off"

    @property
    def hybrid_on(self) -> bool:
        """Return the ``hybrid`` argument of every search and answer call."""
        return self.hybrid == "on"

    @property
    def embed_role(self) -> str:
        """Return the plan role of the embedder."""
        return EMBED_ROLES[self.embedder]

    def collection(self, dataset: str) -> str:
        """Return the collection of this setup's index on *dataset* (dots removed)."""
        return f"exp35_{dataset}_e{self.embedder.replace('.', '')}_c{self.chunk}"


def parse_setup(name: str) -> Setup:
    """Return the setup of *name*.

    Raises:
        ArmConfigError: The name is not on the setup grid.
    """
    found = _SETUP.match(name)
    if not found:
        raise ArmConfigError(
            f"unknown setup {name!r}; names are e<0.6b|4b|8b>-c<512|1024|2048>"
            "-r<off|0.6b|4b|8b>-h<off|on>[-t20k]"
        )
    embedder, chunk, reranker, hybrid, t20k = found.groups()
    return Setup(embedder, int(chunk), reranker, hybrid, bool(t20k))


SEARCH_SETUPS: Mapping[str, Setup] = {
    s.name: s
    for s in (
        Setup(e, c, r, h) for e in EMBEDDERS for c in CHUNKS for r in RERANKERS for h in HYBRIDS
    )
}
INDEXES = tuple(f"e{e}-c{c}" for e in EMBEDDERS for c in CHUNKS)


def index_setup(index: str) -> Setup:
    """Return the setup that configures the index stages of *index*.

    Every ingest and seal of one index uses ``<index>-roff-hon``, so the index
    has one configuration hash whichever setup named it, and the hybrid pin is
    checked at ingest.

    Raises:
        ArmConfigError: *index* is not one of the 9 indexes.
    """
    found = _INDEX.match(index)
    if not found:
        raise ArmConfigError(f"unknown index {index!r}; choose from {', '.join(INDEXES)}")
    return Setup(found.group(1), int(found.group(2)), "off", "on")


def index_setups(index: str) -> list[Setup]:
    """Return the 8 search setups of *index*, in table order."""
    index_setup(index)
    return [s for s in SEARCH_SETUPS.values() if s.index == index]


def answer_setups(embedder: str, reranker: str) -> list[Setup]:
    """Return the 15 answer setups for the chosen embedder and reranker sizes."""
    crossed = [Setup(embedder, c, r, h) for c in CHUNKS for r in ("off", reranker) for h in HYBRIDS]
    return crossed + [Setup(embedder, c, reranker, "on", True) for c in CHUNKS]


def parse_judges(text: str) -> tuple[str, ...]:
    """Return the judge names of a comma list, in order, without repeats.

    Raises:
        ArmConfigError: A name is not a registered judge.
    """
    names = [part.strip() for part in text.split(",") if part.strip()]
    unknown = [name for name in names if name not in JUDGE_NAMES]
    if unknown:
        raise ArmConfigError(f"unknown judge {unknown}; choose from {', '.join(JUDGE_NAMES)}")
    return tuple(dict.fromkeys(names))


def plan_role(plan: Mapping[str, Any], role: str) -> Mapping[str, Any]:
    """Return the plan ``runtime`` model of *role*.

    Raises:
        ArmConfigError: The plan pins no model for the role.
    """
    for model in plan["runtime"]["models"]:
        if model["role"] == role:
            return model
    raise ArmConfigError(
        f"plan.json runtime block has no model with role {role!r}; add its "
        "file, SHA-256 and build before this stage runs"
    )


def _plan_block(plan: Mapping[str, Any], *path: str) -> Any:
    value: Any = plan
    for depth, part in enumerate(path):
        if not isinstance(value, Mapping) or part not in value:
            raise ArmConfigError(
                f"plan.json has no {'.'.join(path[: depth + 1])}; record it (P9 to P11) "
                "before this stage runs"
            )
        value = value[part]
    return value


def plan_seed(plan: Mapping[str, Any], use: str) -> int:
    """Return the ``plan.json`` seed of *use* (``seeds.<use>``).

    Uses: ``answer``, ``glm``, ``ragas_judge``, ``classifier``,
    ``question_order`` and ``smoke_sample`` (pre-registration section 16).

    Raises:
        ArmConfigError: The plan records no such seed; the message names the key.
    """
    return int(_plan_block(plan, "seeds", use))


def recorded_pins(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return the P11 pins that OMRS has no setting for (``pins.recorded``).

    The reranker instruction and the BM25 and fusion parameters are fixed by
    the pinned OMRS and llama.cpp code; the harness records them in each trace.
    """
    return dict(_plan_block(plan, "pins", "recorded"))


def stage_roles(setup: Setup, stage: str, judges: Sequence[str]) -> list[str]:
    """Return the plan roles a stage loads on the router, in load order."""
    roles = [setup.embed_role]
    if stage in INDEX_STAGES:
        return roles
    if setup.rerank:
        roles.append(RERANK_ROLES[setup.reranker])
    return roles + [JUDGE_ROLES[j] for j in judges if j in JUDGE_ROLES]


def _merge(values: dict[str, Any], pins: Mapping[str, Any]) -> None:
    for key, value in pins.items():
        if isinstance(value, Mapping):
            values.setdefault(key, {}).update(value)
        else:
            values[key] = value


def settings_values(
    setup: Setup,
    plan: Mapping[str, Any],
    gguf_folder: Path,
    *,
    answer_host: str,
    judges: Sequence[str],
) -> dict[str, Any]:
    """Return the scratch ``omrs.jsonc`` values of one setup.

    Args:
        setup: The setup.
        plan: The parsed ``plan.json``.
        gguf_folder: The folder that holds the GGUF files (``SWEEP_GGUF_DIR``).
        answer_host: The one OpenRouter host that serves the answer model.
        judges: The claim judges the stage runs.

    Raises:
        ArmConfigError: The plan pins no model for a role the setup needs, or
            has no ``seeds.answer`` or ``pins.settings``.
        RouterConfigError: A GGUF file is missing, or OMRS refuses a preset.
    """
    embed = plan_role(plan, setup.embed_role)
    local = [plan_role(plan, r) for r in stage_roles(setup, "answer", judges)[1:]]
    entries = router_env.model_entries({"runtime": {"models": [embed, *local]}}, gguf_folder)
    retrieval: dict[str, Any] = {}
    if setup.rerank:
        retrieval["rerank_backend"] = "llamacpp"
        retrieval["rerank_model"] = router_env.model_name(local[0])
    if setup.hybrid_on:
        retrieval["hybrid_sparse_backend"] = "bm25"
    values: dict[str, Any] = {
        "embed_provider": "llamacpp",
        "local_backend": "llamacpp",
        "llamacpp_router_server": "managed",
        "llamacpp_router_url": router_env.ROUTER_URL,
        "llamacpp_router_models_max": 2 if setup.rerank else 1,
        "llamacpp_embed_model": router_env.model_name(embed),
        "rag_profile": "documents",
        "embedding": {"tokenizer_model": TOKENIZER_MODEL, "tokenizer_revision": TOKENIZER_REVISION},
        "chunking": {
            "chunk_size": setup.chunk,
            "markdown_chunk_size": setup.chunk,
            "chunk_overlap": OVERLAPS[setup.chunk],
        },
        "metadata": {"extraction_mode": "disabled"},
        "openrouter_api_key": OPENROUTER_KEY_REF,
        "answer": {
            "provider": "openrouter",
            "model": ANSWER_MODEL,
            "temperature": TEMPERATURE,
            "seed": plan_seed(plan, "answer"),
            "allowed_hosts": answer_host,
            "verify_claims": False,
            "context_window": ANSWER_CONTEXT_WINDOW,
            "max_rounds": ANSWER_MAX_ROUNDS,
        },
        "llamacpp_models": entries,
    }
    if retrieval:
        values["retrieval"] = retrieval
    _merge(values, _plan_block(plan, "pins", "settings"))
    if "chat" in judges:
        values["openai_compatible_base_url"] = GLM_BASE_URL
        values["openai_compatible_api_key"] = f"env://{GLM_KEY_ENV}"
    return values


def without_keys(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return *values* without key fields.

    OMRS resolves a key reference to the key itself, so a resolved-value check
    must never see a key field: the comparison means nothing and its message
    would print the key (the Experiment 48 fix of 2026-11-10).
    """
    return {k: v for k, v in values.items() if not k.endswith("_api_key")}


def judge_block(answer_block: Any, name: str, plan: Mapping[str, Any]) -> Any:
    """Return a copy of the answer block that runs the claim judge *name*.

    The local judge keeps the strategy defaults, as the pre-freeze AggreFact
    runs did. The ``chat`` judge is GLM-5.3 at temperature 0, reasoning
    ``low`` and the ``plan.json`` seed ``seeds.glm`` (pre-registration section 16).
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
            "verify_seed": plan_seed(plan, "glm"),
        }
    return answer_block.model_copy(update={"verify_claims": True, "verify_judge": name, **update})
