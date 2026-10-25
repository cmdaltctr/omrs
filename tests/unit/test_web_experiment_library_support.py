"""Shared helpers for the experiment library route tests (experiments-in-web-workspace).

Not a test module. It builds a temporary project with real experiment records,
starts the app on a temporary workspace and signs the client in.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    build_app,
    lance_store,
    login,
    make_engine,
)

from omrs.core.experiment_records.index import INDEX_END, INDEX_START  # noqa: E402
from omrs.core.experiment_records.record import Category, Size  # noqa: E402
from omrs.core.experiment_records.scaffold import create_experiment  # noqa: E402

FIRST = "1-first-run-2026-01-01"
SECOND = "2-second-run-2026-02-01"
README = f"# Experiments\n\n{INDEX_START}\n{INDEX_END}\n"
RESERVED = {
    "format": "omrs-experiment-reservations/1",
    "reservations": [{"number": "9", "reason": "Planned later", "ref": "task 9"}],
}


def make_project(base: Path, name: str = "omrs", *, readme: str | None = README) -> Path:
    """Create a project folder with two experiments and return the project root.

    ``1-first-run`` is a Standard experiment with a review page and an
    ``output/`` folder. ``2-second-run`` is a Quick experiment.
    """
    experiments = base / name / "experiments"
    experiments.mkdir(parents=True)
    create_experiment(
        experiments,
        slug="first-run",
        title="First run",
        category=Category.RETRIEVAL,
        size=Size.STANDARD,
        day=date(2026, 1, 1),
    )
    create_experiment(
        experiments,
        slug="second-run",
        title="Second run",
        category=Category.INGESTION,
        size=Size.QUICK,
        day=date(2026, 2, 1),
    )
    first = experiments / FIRST
    (first / "review.html").write_text("<script>alert(1)</script>", encoding="utf-8")
    (first / "output").mkdir()
    (first / "output" / "scores.json").write_text("{}", encoding="utf-8")
    (first / "output" / "chroma_index").mkdir()
    (experiments / "reserved.json").write_text(json.dumps(RESERVED), encoding="utf-8")
    if readme is not None:
        (experiments / "EXP_README.md").write_text(readme, encoding="utf-8")
    return base / name


@contextmanager
def open_client(tmp_path: Path, settings: Any) -> Iterator[tuple[TestClient, Any, Any]]:
    """Start the app on a temporary workspace and yield ``(client, policy, app)``."""
    engine = make_engine(lance_store(tmp_path), settings)
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        yield client, policy, app


def add_project(client: TestClient, root: Path, name: str = "OMRS") -> dict[str, Any]:
    """Add *root* as a project and return the stored project."""
    response = client.post(
        "/v1/experiment-projects", json={"path": str(root), "name": name}, headers=ORIGIN
    )
    assert response.status_code == 201, response.text
    return response.json()["project"]
