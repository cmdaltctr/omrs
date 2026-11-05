"""Fixtures for the Experiment 47 tests: a temporary output folder and fake inputs.

No test reads a PDF, starts llama-server or calls a hosted API. Decision model
requests go to an ``httpx.MockTransport``. The shipped page rules, page judge
and adapters run unchanged; only the PDF readers (scan, maths and blank tests,
page render) are replaced, because the fake PDFs are not real files.
"""

from __future__ import annotations

import contextlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import exp47_io  # noqa: E402

MODULES = ("exp47_io", "prepare_inputs", "label_pages", "score_router", "analysis")
KEY = "stand-in-key-for-tests"
#: Fake documents: (id, group, pages as (markdown, needs_ocr)).
DOCS = (
    ("jone", "JUNK", [("junk INT , L/ NUI a NS SRA", False), ("junk ¡NS INT", False)]),
    (
        "gone",
        "GOOD",
        [
            ("A clean page of printed text about the old mill by the river.", False),
            ("Another clean page with ten or more plain words on it.", False),
        ],
    ),
)


def fake_pdf(doc_id: str) -> bytes:
    return f"%PDF-fake-{doc_id}".encode()


def fake_png(name: str, page: int) -> bytes:
    return f"png-{name}-{page}".encode()


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """Point every module of the experiment at a temporary output and corpus folder."""
    out = tmp_path / "output"
    private = out / ".private"
    values = {
        "OUTPUT": out,
        "PRIVATE": private,
        "PRIVATE_DIRS": {k: private / k for k in exp47_io.PRIVATE_DIRS},
        "INPUTS": out / "inputs.json",
        "LABELS": out / "labels.json",
        "LABEL_REVIEW": out / "label_review.json",
        "REFERENCE_STATE": out / "reference_state.json",
        "SET_CHECK": out / "set_check.json",
        "CORPUS": tmp_path / "corpus",
        "MANIFEST": tmp_path / "corpus_manifest.json",
    }
    for name in MODULES:
        module = importlib.import_module(name)
        for key, value in values.items():
            if hasattr(module, key):
                monkeypatch.setattr(module, key, value)
    values["CORPUS"].mkdir()
    texts = {}
    documents = []
    for doc_id, group, pages in DOCS:
        data = fake_pdf(doc_id)
        (values["CORPUS"] / f"{doc_id}.pdf").write_bytes(data)
        texts[f"{doc_id}.pdf"] = list(pages)  # tests change their own copy
        documents.append(
            {
                "id": doc_id,
                "group": group,
                "file": f"{doc_id}.pdf",
                "source_url": f"https://example.org/{doc_id}.pdf",
                "licence": "public-domain",
                "sha256": exp47_io.sha256_bytes(data),
                "page_range": [1, len(pages)],
            }
        )
    manifest = {"format": "omrs-exp47-corpus/1", "documents": documents}
    values["MANIFEST"].write_text(json.dumps(manifest))

    def scan(pdf: Path) -> list:
        return [
            SimpleNamespace(page=n, markdown=t, needs_ocr=f, reason=None)
            for n, (t, f) in enumerate(texts[pdf.name], start=1)
        ]

    def render(pdf: Path, page: int) -> bytes:
        return fake_png(pdf.stem, page)

    return SimpleNamespace(
        root=tmp_path, manifest=manifest, texts=texts, scan=scan, render=render, **values
    )


@pytest.fixture
def current():
    """The real plan.json with every required decision approved (tests only)."""
    plan = exp47_io.plan(require_approved=False)
    for entry in plan["decision_register"]:
        if entry.get("scope") != "hosted_reference_arm":
            entry.update(status="APPROVED (test)", date="2026-11-05")
    return plan


def approve_hosted(plan: dict) -> None:
    """Add the dated hosted approval to *plan*."""
    for entry in plan["decision_register"]:
        if entry.get("scope") == "hosted_reference_arm":
            entry.update(status="APPROVED (test)", date="2026-11-05")


def prepared(ws) -> dict:
    """Run step 1 on the fake corpus."""
    import prepare_inputs

    return prepare_inputs.prepare(
        ws.manifest,
        resume=False,
        ident={"test": 1},
        scan=ws.scan,
        render=ws.render,
        corpus=ws.CORPUS,
        target=ws.INPUTS,
    )


def frozen_labels(ws, classes: dict | None = None) -> None:
    """Write frozen labels, a complete review and a passing set check."""
    inputs = exp47_io.read_json(ws.INPUTS)
    rows = []
    for doc_id, doc in inputs["documents"].items():
        for row in doc["rows"]:
            label = (classes or {}).get(
                (doc_id, row["page"]), "junk" if doc_id == "jone" else "healthy"
            )
            rows.append(
                {
                    "doc_id": doc_id,
                    "page": row["page"],
                    "needs_ocr": row["needs_ocr"],
                    "class": label,
                }
            )
    exp47_io.atomic_json(ws.LABELS, {"inputs_sha256": exp47_io.sha256(ws.INPUTS), "rows": rows})
    exp47_io.atomic_json(
        ws.LABEL_REVIEW,
        {
            "reviewer": "operator",
            "date": "2026-11-05",
            "pages": [{"doc_id": "jone", "page": 1, "verdict": "agree"}],
        },
    )
    exp47_io.atomic_json(ws.SET_CHECK, {"pass": True})


def passing_check(plan: dict, arm: str, **overrides) -> None:
    """Write a passing runtime check record for the current identity."""
    checks = {"R4_shipped_checks": {"pass": True}, "R5_no_projector": {"pass": True}}
    record = {"identity": exp47_io.check_identity(plan, arm), "checks": checks, "passed": True}
    record.update(overrides)
    exp47_io.atomic_json(exp47_io.OUTPUT / f"runtime_check_{arm}.json", record)


class FakeModel:
    """A System One server: passes the probe and the smoke test, rejects junk text."""

    def __init__(self, on_request=None) -> None:
        self.page_texts: list[str] = []
        self.requests = 0
        self.on_request = on_request
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        from omrs.core.providers.decision import checks

        self.requests += 1
        if self.on_request:
            self.on_request(request)
        body = json.loads(request.content)
        text = body["state"]["text"]
        if text == checks.SMOKE_RIGHT_TEXT:
            p = 0.9
        elif text == checks.SMOKE_WRONG_TEXT:
            p = 0.1
        elif text == "This is a short test sentence.":
            p = 0.8
        else:
            self.page_texts.append(text)
            p = 0.05 if "junk" in text else 0.9
        reply = {"model": "Clef-Flash-Q8_0.gguf", "answers": {"fidelity": {"noul": p}}}
        return httpx.Response(200, json=reply)


@pytest.fixture
def shipped_readers(monkeypatch, ws):
    """Replace only the PDF readers the page rules call; the rules themselves are unchanged."""
    from omrs.integrations.pdf import blank_pages, maths_routing, page_images

    monkeypatch.setattr(maths_routing, "detect_maths_pages", lambda file, settings: set())
    monkeypatch.setattr(blank_pages, "find_blank_pages", lambda file, pages: frozenset())
    monkeypatch.setattr(page_images, "available", lambda: True)
    monkeypatch.setattr(page_images, "render_page", ws.render)
    monkeypatch.setenv("TYPESAFE_API_KEY", KEY)


@contextlib.contextmanager
def fake_server(plan: dict, projector: bool = True):
    yield "http://127.0.0.1:18931", None
