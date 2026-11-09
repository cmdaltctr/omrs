"""Label-equality and process-cache tests for the in-process Magika API.

Tasks 2.1 and 2.2 of the ``ingest-per-file-overhead-reduction`` OpenSpec
change. Both tests fail on the current code on purpose: today
``scan_with_magika`` shells out to the Magika CLI, and the change replaces
that call with the in-process ``magika.Magika`` API. The implementation
lands in a later step; these tests pin the contract first.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from omrs.integrations import magika as omrs_magika
from omrs.integrations.magika import _resolve_magika, scan_with_magika

_REPO_ROOT = Path(__file__).resolve().parent.parent

# The frozen 16-file acceptance corpus of ADR-068, paths updated after the
# omrg to omrs rename. Detection is content-based, so copies of these files
# are valid probes.
_CORPUS: tuple[str, ...] = (
    "experiments/2-embedding-model-comparison-2026-05-19/corpus/Ghazali-Mustasfa.pdf",
    "experiments/2-embedding-model-comparison-2026-05-19/corpus/"
    "Kalai et al. - 2025 - Why Language Models Hallucinate.pdf",
    "experiments/2-embedding-model-comparison-2026-05-19/corpus/"
    "Popat and Starkey - 2019 - Learning to code or coding to learn A systematic review.pdf",
    "tests/fixtures/pdf_baseline/calibration/cal_clean_text.pdf",
    "tests/fixtures/pdf_baseline/calibration/cal_table_text.pdf",
    "src/omrs/compose.py",
    "src/omrs/core/ingestion/pipeline.py",
    "src/omrs/integrations/magika.py",
    "src/omrs/core/codebase/codebase_map.py",
    "README.md",
    "AGENTS.md",
    "docs/guides/architecture.md",
    "docs/guides/ingestion.md",
    "experiments/20-citation-faithfulness-2026-09-02/corpus/source-01-aurora.txt",
    "experiments/20-citation-faithfulness-2026-09-02/corpus/source-02-birch.txt",
    "experiments/19-lancedb-lifecycle-qualification-2026-08-21/fixtures/"
    "corpus_replacement/bravo_harbour.txt",
)
assert len(_CORPUS) == 16, "ADR-068 acceptance corpus must stay at 16 files"


def _inline_normalise(group: str, label: str, is_text: bool) -> tuple[str, str]:
    """Apply the OMRS boundary rules inline, deliberately NOT via production.

    This copy is a mutation check: importing ``_normalise_detected`` from
    production would let a mutation that removes or changes the alias rules
    pass unnoticed, because both sides of the comparison would use the same
    mutated code. The rules mirror the pinned boundary:

    - ``is_text`` false and group outside ``document``, ``code``, ``text``
      becomes ``binary``; the label is preserved.
    - ``is_text`` true and group ``text``: label ``markdown`` maps to
      ``document/markdown``, label ``txt`` maps to ``document/text``.
    - Every other group and label passes through unchanged.
    """
    if is_text is False and group not in {"document", "code", "text"}:
        return "binary", label
    if is_text is True and group == "text":
        if label == "markdown":
            return "document", "markdown"
        if label == "txt":
            return "document", "text"
    return group, label


def _collect_cli_ground_truth(corpus_dir: Path, program: str) -> dict[str, tuple[str, str, bool]]:
    """Run the Magika CLI over the corpus and return normalised labels.

    Only ``result.status == "ok"`` rows are accepted; anything else fails
    loudly. Group, label and ``is_text`` come from ``result.value.output``
    and then go through the inline boundary normalisation.
    """
    proc = subprocess.run(
        [program, "-r", str(corpus_dir), "--jsonl"],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    ground_truth: dict[str, tuple[str, str, bool]] = {}
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        result = row["result"]
        assert result["status"] == "ok", f"Magika CLI row is not ok: {line[:80]!r}"
        output = result["value"]["output"]
        group, label, is_text = output["group"], output["label"], output["is_text"]
        group, label = _inline_normalise(group, label, is_text)
        rel = str(Path(row["path"]).relative_to(corpus_dir))
        assert rel not in ground_truth, f"duplicate CLI row for {rel}"
        ground_truth[rel] = (group, label, is_text)
    return ground_truth


def _assert_entries_match(ground_truth: dict[str, tuple[str, str, bool]], entries: list) -> None:
    """Assert path-set identity and exact label triples against the CLI."""
    observed: dict[str, tuple[str, str, bool]] = {}
    for entry in entries:
        assert entry.path not in observed, f"duplicate entry path: {entry.path}"
        observed[entry.path] = (entry.group, entry.label, entry.is_text)
    assert set(observed) == set(ground_truth), (
        f"path sets differ; missing={sorted(set(ground_truth) - set(observed))} "
        f"extra={sorted(set(observed) - set(ground_truth))}"
    )
    for rel in sorted(ground_truth):
        assert observed[rel] == ground_truth[rel], (
            f"{rel}: scan_with_magika gave {observed[rel]}, CLI gave {ground_truth[rel]}"
        )


def test_scan_with_magika_labels_match_cli_ground_truth(
    tmp_path: Path,
    effective_settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 2.1: the API path must equal the CLI labels on the ADR-068 corpus.

    Purpose: pin the label-equality contract between ``scan_with_magika``
    and the Magika CLI over the frozen 16-file ADR-068 acceptance corpus
    (PDFs, Python sources, markdown, plain text). The CLI is the ground
    truth; the seam under test is ``omrs.integrations.magika.scan_with_magika``.

    The inline normalisation copy above is a mutation check: if production
    drops or changes the binary-boundary or alias rules, the two sides
    diverge and this test fails. A mismatch blocks the change.

    The second scan runs with stdlib ``subprocess.run`` patched to raise,
    proving the scan is in-process. On the current subprocess code this
    test fails there; that is the intended pre-change failure.
    """
    settings = effective_settings()
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    for rel in _CORPUS:
        source = _REPO_ROOT / rel
        assert source.is_file(), f"corpus file missing from worktree: {rel}"
        shutil.copy2(source, corpus_dir / source.name)

    program = _resolve_magika(settings)
    assert program is not None, "magika CLI program not found; ground truth unavailable"

    ground_truth = _collect_cli_ground_truth(corpus_dir, program)
    assert len(ground_truth) == len(_CORPUS), (
        f"CLI classified {len(ground_truth)} files, corpus has {len(_CORPUS)}"
    )

    entries = scan_with_magika(str(corpus_dir), settings=settings)
    _assert_entries_match(ground_truth, entries)

    def _forbid_subprocess(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess spawned during scan")

    monkeypatch.setattr(subprocess, "run", _forbid_subprocess)
    try:
        in_process_entries = scan_with_magika(str(corpus_dir), settings=settings)
    except AssertionError as exc:
        pytest.fail(
            "scan_with_magika still spawns a subprocess; the in-process "
            f"magika.Magika switch has not landed (caught: {exc})"
        )
    _assert_entries_match(ground_truth, in_process_entries)


def test_scan_with_magika_builds_one_magika_instance_per_process(
    tmp_path: Path,
    effective_settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 2.2: two scans in one process construct ``magika.Magika`` once.

    The counting fake patches ``magika.Magika`` on the magika PACKAGE,
    because the future implementation imports the class lazily inside its
    cached wrapper; patching ``omrs.integrations.magika`` would not
    intercept that import. ``_is_magika_available`` is patched to True so
    the availability gate passes.

    On the CURRENT code this test fails because nothing ever constructs
    ``magika.Magika``: the counter stays at 0 while the assertion demands
    exactly 1. That is the intended pre-change failure.

    Cache hygiene: ``_get_magika_instance`` is cleared before and after
    (try/finally). The label-equality test may have cached a real instance
    earlier in this worker process, and this fake must not leak into later
    test files.
    """
    counts = {"constructed": 0, "identify_calls": 0}

    class FakeMagika:
        """Counting stand-in mirroring the ``magika.Magika`` call shape."""

        def __init__(self) -> None:
            counts["constructed"] += 1

        def identify_paths(self, files: list[str]) -> list:
            counts["identify_calls"] += 1
            rows = []
            for path in files:
                # Alias-rule exercise: markdown and txt both sit in group
                # "text" and must normalise into the "document" group.
                label = "markdown" if str(path).endswith(".md") else "txt"
                rows.append(
                    SimpleNamespace(
                        ok=True,
                        status="ok",
                        path=path,
                        output=SimpleNamespace(group="text", label=label, is_text=True),
                    )
                )
            return rows

    cache = getattr(omrs_magika, "_get_magika_instance", None)
    if cache is not None and hasattr(cache, "cache_clear"):
        cache.cache_clear()
    try:
        monkeypatch.setattr("magika.Magika", FakeMagika)
        monkeypatch.setattr(omrs_magika, "_is_magika_available", lambda settings=None: True)

        scan_dir = tmp_path / "scan"
        scan_dir.mkdir()
        (scan_dir / "note.md").write_text(
            "# Notes\n\nA markdown heading with enough words to classify.\n", encoding="utf-8"
        )
        (scan_dir / "plain.txt").write_text(
            "A plain paragraph of prose for the detector to read.\n", encoding="utf-8"
        )
        settings = effective_settings()

        first = scan_with_magika(str(scan_dir), settings=settings)
        second = scan_with_magika(str(scan_dir), settings=settings)

        assert counts["constructed"] == 1, (
            f"expected exactly one Magika() construction across both scans, "
            f"got {counts['constructed']}"
        )
        assert counts["identify_calls"] == 2, (
            f"the cached instance must serve both scans, got "
            f"{counts['identify_calls']} identify_paths calls"
        )
        observed = {entry.path: (entry.group, entry.label) for entry in first + second}
        assert observed == {
            "note.md": ("document", "markdown"),
            "plain.txt": ("document", "text"),
        }, f"alias normalisation not applied to fake labels: {observed}"
    finally:
        if cache is not None and hasattr(cache, "cache_clear"):
            cache.cache_clear()
