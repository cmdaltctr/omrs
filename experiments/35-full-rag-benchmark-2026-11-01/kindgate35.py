"""Claim-kind gate of Experiment 35 (pre-registration sections 11.1 and 12; review B2).

No claim-kind result is used until classifier gate 3 passes. A passed gate is
``gate.json`` (``refusals35.py gate``) with ``pass: true`` and the frozen
classifier ``version``; every saved kind a consumer reads must carry that
version. Until then the registered fallback applies (pre-freeze amendment,
2026-11-26): no kind filter, so faithfulness counts every cited claim and is
descriptive only, and the confirmatory analysis marks faithfulness rows 12,
13, 16 and 17 "not testable" (p = 1, kept in their Holm families).

Consumers: ``joinscores35.answer_scores``, ``faithpool35`` (the faithfulness
gate pool) and ``factorial35.write_confirmatory``. ``refusalreport35`` keeps
its own check: the refusal report needs a passed gate.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from outputs35 import read_rows

#: Faithfulness rows of H8a and H8b (pre-registration section 8), as ``labels35.FAITH_ROWS``.
FAITH_ROWS = (12, 13, 16, 17)
FALLBACK = "classifier gate not passed: every cited claim counts; faithfulness is descriptive"


class KindGateError(RuntimeError):
    """A saved kind has another version than the passed gate, or the join used other kinds."""


def gate_version(gate_path: Path | None) -> str | None:
    """Return the frozen classifier version when ``gate.json`` passed, else None (the fallback)."""
    path = Path(gate_path) if gate_path else None
    found = json.loads(path.read_text(encoding="utf-8")) if path and path.is_file() else {}
    return str(found["version"]) if found.get("pass") is True and found.get("version") else None


def check_versions(rows: Sequence[Mapping[str, Any]], version: str, where: Path) -> None:
    """Refuse saved kinds from another classifier version than the passed gate's.

    Raises:
        KindGateError: Names the folder and the versions found.
    """
    found = sorted({str(r.get("version")) for r in rows} - {version})
    if found:
        raise KindGateError(
            f"{where}: saved kinds of version {found}; the passed gate is {version}"
        )


def saved_kinds(run_dir: Path, version: str | None) -> dict[tuple[str, bool], str]:
    """Return ``(claim key, uncited) -> kind`` of a run folder; empty under the fallback."""
    if version is None:
        return {}
    rows = read_rows(run_dir / "claim-kinds.jsonl")
    check_versions(rows, version, run_dir)
    return {(r["claim_key"], bool(r.get("uncited"))): r["kind"] for r in rows}


def status(gate_path: Path | None) -> dict[str, Any]:
    """Return the record the join and the analysis write about the kinds they used."""
    version = gate_version(gate_path)
    return {
        "gate": str(gate_path) if gate_path else None,
        "pass": version is not None,
        "version": version,
        "rule": "claim kinds used" if version else FALLBACK,
    }


def confirmatory_rows(root: Path, gate_path: Path | None) -> dict[str, Any]:
    """Check the join used the gate's kinds; return the status and the fallback rows.

    Raises:
        KindGateError: ``<root>/join.json`` used another version, or holds no record.
    """
    found = status(gate_path)
    joined = json.loads((root / "join.json").read_text(encoding="utf-8")).get("claim_kinds")
    if not joined or joined.get("version") != found["version"]:
        raise KindGateError(
            f"{root / 'join.json'} used claim kinds {joined}; the gate gives version "
            f"{found['version']}: run join35.py --gate {gate_path} again"
        )
    return {**found, "not_testable_rows": [] if found["pass"] else list(FAITH_ROWS)}
