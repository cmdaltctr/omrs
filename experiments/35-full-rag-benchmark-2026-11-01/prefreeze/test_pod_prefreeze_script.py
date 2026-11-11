"""Static checks on pod_prefreeze.sh (no shell run, no download)."""

from __future__ import annotations

from pathlib import Path

SCRIPT = (Path(__file__).parent / "pod_prefreeze.sh").read_text(encoding="utf-8")


def test_judge_download_uses_the_repo_environment() -> None:
    """The pod's system python3 has no huggingface_hub (pod run 2026-11-10), so the
    judge download must run in the repository's uv environment."""
    body = SCRIPT[SCRIPT.index("fetch_judges() {") :]
    body = body[: body.index("\n}\n")]
    assert "python3 -" not in body
    assert "uv run --no-sync python -" in body


def test_ragas_venv_pins_a_langchain_community_that_ragas_imports() -> None:
    """Ragas 0.4.3 imports langchain_community.chat_models.vertexai, removed in 0.4
    (pod run 2026-11-10); 0.3.31 imports cleanly with ragas 0.4.3."""
    body = SCRIPT[SCRIPT.index("stage_measure() {") :]
    body = body[: body.index("\n}\n")]
    assert '"langchain-community==0.3.31"' in body


def test_judge_preset_fits_a_whole_input_in_one_batch() -> None:
    """Clef-Flash on /v1/systemone needs the whole input in one physical batch; the
    llama.cpp default of 512 tokens failed 68% of rows (pod run 2026-11-10)."""
    import run_aggrefact as ra

    args = ra.SERVER_ARGS
    assert args["ubatch-size"] >= args["ctx-size"]
    assert args["batch-size"] >= args["ubatch-size"]


def test_judge_download_starts_after_setup_builds_the_environment() -> None:
    """fetch_judges uses `uv run --no-sync` in the repo, so it needs the venv that
    stage_setup builds; started earlier it failed on a fresh pod (2026-11-10)."""
    body = SCRIPT[SCRIPT.index("main() {") :]
    assert body.index("stage setup 1 stage_setup") < body.index("fetch_judges && mark judges")
