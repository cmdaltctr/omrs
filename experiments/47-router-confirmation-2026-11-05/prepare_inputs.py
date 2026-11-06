"""Step 1: check the corpus manifest, scan each page with the shipped reader, render it.

    uv run --no-sync python prepare_inputs.py --validate   # manifest only, no PDF read
    uv run --no-sync python prepare_inputs.py              # first run
    uv run --no-sync python prepare_inputs.py --resume     # after a stop, or in a fresh clone

Reads only committed files (``plan.json``, ``corpus_manifest.json`` and the
committed source lists of Experiments 33 and 42) and the gitignored ``corpus/``
folder. It never reads the gitignored output of another experiment.

For each document it checks the PDF SHA-256, refuses any overlap with
Experiments 33, 38, 42, 43 and 44, runs the shipped page scan
(``page_routing.page_evidence``, the evidence the router sees) and renders each
page in the range with the shipped renderer (``page_images.render_page``). Page
text and images go to ``output/.private/``. The committed ``output/inputs.json``
holds hashes and counts only and is replaced after each document.

A resume trusts a document only when its private files exist and match the
committed hashes. Otherwise the document is read again, and its new hashes
must equal the committed ones (issue #171, point 11).
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path
from typing import Any

from exp47_io import (
    CORPUS,
    EXPERIMENTS,
    INPUTS,
    MANIFEST,
    atomic_json,
    log,
    plan,
    private_path,
    read_json,
    sha256,
    sha256_bytes,
    text_sha256,
    write_private_bytes,
)

MANIFEST_FORMAT = "omrs-exp47-corpus/1"
GROUPS = ("JUNK", "GOOD")
_ID = re.compile(r"[a-z][a-z0-9]{1,15}")
_SHA = re.compile(r"[0-9a-f]{64}")
_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.pdf")
_DOC_KEYS = {
    "id", "group", "file", "source_url", "licence", "sha256", "page_range", "title", "language"
}
_OPTIONAL = {"title", "language"}

Scan = Callable[[Path], list[Any]]
Render = Callable[[Path, int], bytes]


# ---------------------------------------------------------------- manifest


def validate_manifest(manifest: Any, allowed_licences: list[str]) -> list[str]:
    """Return every problem with the corpus manifest; an empty list means valid."""
    if not isinstance(manifest, dict) or manifest.get("format") != MANIFEST_FORMAT:
        return [f"format must be {MANIFEST_FORMAT}"]
    documents = manifest.get("documents")
    if not isinstance(documents, list) or not documents:
        return ["documents must be a non-empty list"]
    problems: list[str] = []
    for index, doc in enumerate(documents):
        where = f"documents[{index}]"
        if not isinstance(doc, dict):
            problems.append(f"{where} must be an object")
            continue
        unknown = set(doc) - _DOC_KEYS
        missing = _DOC_KEYS - _OPTIONAL - set(doc)
        problems += [f"{where}.{k} is not a field" for k in sorted(unknown)]
        problems += [f"{where}.{k} is required" for k in sorted(missing)]
        if missing:
            continue
        if not isinstance(doc["id"], str) or not _ID.fullmatch(doc["id"]):
            problems.append(f"{where}.id must be 2 to 16 lower-case letters and digits")
        if doc["group"] not in GROUPS:
            problems.append(f"{where}.group must be JUNK or GOOD")
        if not isinstance(doc["file"], str) or not _FILE.fullmatch(doc["file"]):
            problems.append(f"{where}.file must be a plain .pdf file name")
        if not str(doc["source_url"]).startswith("https://"):
            problems.append(f"{where}.source_url must be an https address")
        if doc["licence"] not in allowed_licences:
            problems.append(f"{where}.licence must be one of {allowed_licences}")
        if not isinstance(doc["sha256"], str) or not _SHA.fullmatch(doc["sha256"]):
            problems.append(f"{where}.sha256 must be 64 lower-case hexadecimal characters")
        pages = doc["page_range"]
        if not (
            isinstance(pages, list)
            and len(pages) == 2
            and all(isinstance(p, int) and not isinstance(p, bool) for p in pages)
            and 1 <= pages[0] <= pages[1]
        ):
            problems.append(f"{where}.page_range must be [first, last] with 1 <= first <= last")
        if "language" in doc and not (isinstance(doc["language"], str) and doc["language"]):
            problems.append(f"{where}.language must be a non-empty string")
    for key in ("id", "file", "sha256", "source_url"):
        values = [d.get(key) for d in documents if isinstance(d, dict)]
        repeated = sorted({str(v) for v in values if values.count(v) > 1})
        problems += [f"{key} {v} appears more than once" for v in repeated]
    return problems


def prior_documents(current: dict, root: Path) -> dict[str, set[str]]:
    """Hashes, file names and addresses of every document of Experiments 33 to 44.

    Experiments 38, 43 and 44 used the Experiment 33 documents (their plans
    say so), so the committed source lists of 33 and 42 cover all five.
    """
    seen: dict[str, set[str]] = {"sha256": set(), "file": set(), "url": set()}
    for entry in current["overlap_sources"]:
        path = root / entry["path"]
        if sha256(path) != entry["sha256"]:
            raise SystemExit(f"overlap source differs from plan: {entry['path']}")
        for doc in read_json(path)["documents"]:
            seen["sha256"].add(doc["sha256"])
            seen["file"].add(Path(doc["local_path"]).name)
            seen["url"].update(u for u in (doc.get("pdf_url"), doc.get("landing_url")) if u)
    return seen


def overlap_problems(manifest: dict, seen: dict[str, set[str]]) -> list[str]:
    """Name each manifest document that an earlier experiment already used."""
    problems = []
    for doc in manifest["documents"]:
        if doc["sha256"] in seen["sha256"]:
            problems.append(f"{doc['id']}: SHA-256 matches an earlier experiment document")
        if doc["file"] in seen["file"]:
            problems.append(f"{doc['id']}: file name {doc['file']} matches an earlier document")
        if doc["source_url"] in seen["url"]:
            problems.append(f"{doc['id']}: source address matches an earlier document")
    return problems


def checked_manifest(current: dict, root: Path, path: Path = MANIFEST) -> dict:
    """Read the manifest; stop on any schema problem or overlap."""
    manifest = read_json(path)
    problems = validate_manifest(manifest, current["corpus"]["allowed_licences"])
    if not problems:
        problems = overlap_problems(manifest, prior_documents(current, root))
    if problems:
        raise SystemExit("corpus_manifest.json refused:\n- " + "\n- ".join(problems))
    return manifest


# ---------------------------------------------------------------- pages


def shipped_scan(pdf: Path) -> list[Any]:
    """The shipped page scan the router reads (pdf-inspector page Markdown)."""
    from omrs.integrations.pdf.page_routing import page_evidence

    return page_evidence(pdf)


def shipped_render(pdf: Path, page: int) -> bytes:
    """The shipped page image of an image router (150 DPI, long side at most 1,568 px)."""
    from omrs.integrations.pdf.page_images import render_page

    return render_page(pdf, page)


def identity() -> dict:
    """Bind a resume to the scanner, the renderer and their shipped code."""
    from omrs.integrations.pdf import page_images, page_routing

    renderer = page_images._first_available()
    return {
        "pdf_inspector": version("pdf-inspector"),
        "renderer": renderer,
        "renderer_version": version(renderer) if renderer else None,
        "page_routing_sha256": sha256(Path(page_routing.__file__)),
        "page_images_sha256": sha256(Path(page_images.__file__)),
    }


def read_document(doc: dict, pdf: Path, scan: Scan, render: Render) -> tuple[list[dict], dict]:
    """Scan and render the pages of one document; return committed rows and private text."""
    if sha256(pdf) != doc["sha256"]:
        raise SystemExit(f"{doc['id']}: PDF SHA-256 differs from the manifest")
    evidence = {entry.page: entry for entry in scan(pdf)}
    first, last = doc["page_range"]
    if last > len(evidence):
        raise SystemExit(f"{doc['id']}: page range ends after page {len(evidence)}")
    rows, texts = [], {}
    for page in range(first, last + 1):
        entry = evidence[page]
        markdown = entry.markdown or ""
        png = render(pdf, page)
        write_private_bytes("renders", png, doc["id"], f"p{page:03d}.png")
        texts[str(page)] = markdown
        rows.append(
            {
                "doc_id": doc["id"],
                "page": page,
                "group": doc["group"],
                "markdown_sha256": text_sha256(markdown),
                "markdown_chars": len(markdown),
                "has_text": bool(markdown.strip()),
                "needs_ocr": bool(entry.needs_ocr),
                "ocr_reason": entry.reason,
                "png_sha256": sha256_bytes(png),
            }
        )
    return rows, texts


def private_files_match(doc_id: str, rows: list[dict]) -> bool:
    """True when the private text and images of *doc_id* exist and match *rows*."""
    text_file = private_path("text", f"{doc_id}.json")
    if not text_file.is_file():
        return False
    texts = read_json(text_file)
    for row in rows:
        png = private_path("renders", doc_id, f"p{row['page']:03d}.png")
        if text_sha256(texts.get(str(row["page"]), "\0")) != row["markdown_sha256"]:
            return False
        if not png.is_file() or sha256(png) != row["png_sha256"]:
            return False
    return True


def prepare(
    manifest: dict,
    *,
    resume: bool,
    ident: dict,
    scan: Scan = shipped_scan,
    render: Render = shipped_render,
    corpus: Path = CORPUS,
    target: Path = INPUTS,
) -> dict:
    """Read every manifest document once; checkpoint after each document."""
    if target.exists() and not resume:
        raise SystemExit(f"{target.name} exists; use --resume")
    manifest_sha = text_sha256(json.dumps(manifest, sort_keys=True))
    fresh = {"identity": ident, "manifest_sha256": manifest_sha, "documents": {}}
    payload = read_json(target) if target.exists() else fresh
    if payload["identity"] != ident or payload["manifest_sha256"] != manifest_sha:
        raise SystemExit("scanner, renderer or manifest changed since the last run; resume refused")
    for doc in manifest["documents"]:
        done = payload["documents"].get(doc["id"])
        if done and private_files_match(doc["id"], done["rows"]):
            log(f"[resume] {doc['id']}: private files match")
            continue
        pdf = corpus / doc["file"]
        if not pdf.is_file():
            raise SystemExit(f"missing PDF in corpus/: {doc['file']}")
        rows, texts = read_document(doc, pdf, scan, render)
        if done and rows != done["rows"]:
            raise SystemExit(f"{doc['id']}: page hashes differ from the committed inputs.json")
        text_file = private_path("text", f"{doc['id']}.json")
        atomic_json(text_file, texts)
        payload["documents"][doc["id"]] = {"pdf_sha256": doc["sha256"], "rows": rows}
        atomic_json(target, payload)
        log(f"[prepare] {doc['id']}: {len(rows)} pages scanned and rendered")
    return payload


def main() -> None:
    """Validate the manifest, or check, scan and render every document."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true", help="check the manifest only")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    current = plan(require_approved=not args.validate)
    manifest = checked_manifest(current, EXPERIMENTS.parent)
    if args.validate:
        log(f"manifest valid: {len(manifest['documents'])} documents, no overlap")
        return
    payload = prepare(manifest, resume=args.resume, ident=identity())
    pages = sum(len(d["rows"]) for d in payload["documents"].values())
    log(f"[prepare] complete: {len(payload['documents'])} documents, {pages} pages")


if __name__ == "__main__":
    main()
