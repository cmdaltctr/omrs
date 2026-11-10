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
