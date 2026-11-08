"""Shared fixtures for the Experiment 48 harness tests."""

from __future__ import annotations

import importlib
import os
import sys

import pytest


def _import(name, monkeypatch):
    monkeypatch.setattr(os, "environ", dict(os.environ))
    monkeypatch.setattr(sys, "path", list(sys.path))
    sys.modules.pop(name, None)
    module = importlib.import_module(name)
    monkeypatch.setitem(sys.modules, name, module)
    return module


@pytest.fixture
def part_a(monkeypatch, tmp_path):
    module = _import("run_part_a", monkeypatch)
    monkeypatch.setattr(module, "OUTPUT", tmp_path / "output")
    return module


@pytest.fixture
def timing(monkeypatch, tmp_path):
    module = _import("run_timing", monkeypatch)
    monkeypatch.setattr(module, "OUTPUT", tmp_path / "output")
    (tmp_path / "output").mkdir()
    # The frozen FinanceBench selection the extrapolation reads its slice pages from.
    (tmp_path / "output" / "financebench-selection.json").write_text(
        '[{"doc_name": "A", "pages": 60}, {"doc_name": "B", "pages": 40}]', encoding="utf-8"
    )
    return module
