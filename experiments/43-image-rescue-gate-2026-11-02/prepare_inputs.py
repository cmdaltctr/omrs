"""Tasks 2.2 and 2.3: check the Experiment 33 inputs, extract rescued text, render pages.

1. Run Experiment 33 ``freeze.py --check`` in the source checkout (it must print
   ``freeze verified``) and confirm every PDF exists. A missing file stops the run.
2. Extract the LiteParse (OCR off) and pypdf page text with the shipped adapters and
   normaliser. Every page hash must equal the committed Experiment 38 row.
3. Render each page with poppler at 150 DPI, long side at most 1,568 px.

Page text and images go to gitignored ``output/.rescue_text`` and ``output/.renders``.
The committed ``output/inputs.json`` holds hashes, sizes and versions only.

    uv run --no-sync python prepare_inputs.py --source-exp <checkout>/experiments/33-... --resume
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import Any

from exp43_io import (
    EXP38,
    OUTPUT,
    RENDERS,
    TEXTS,
    atomic_json,
    log,
    plan,
    read_json,
    sha256,
    text_sha256,
)
from PIL import Image

TARGET = OUTPUT / "inputs.json"
TIERS = ("liteparse", "pypdf")
ISSUE_161_TEXT = "INT , L/ NUI a ¡NS SRA"


def page_texts(documents: list[Any], tier: str, count: int, normalise: Any) -> list[str]:
    """Map adapter documents to physical pages (Experiment 38 extract_rescue_text.page_texts).

    Copied, not imported: the Experiment 38 module imports the pre-rename package name.
    """
    if tier not in TIERS:
        raise ValueError("unknown rescue tier")
    if tier == "pypdf" and len(documents) != count:
        raise ValueError("pypdf page count differs from frozen source")
    texts = [""] * count
    seen = set()
    for index, document in enumerate(documents, start=1):
        page = document.metadata["page"] if tier == "liteparse" else index
        if not isinstance(page, int) or not 1 <= page <= count or page in seen:
            raise ValueError("adapter returned an invalid or duplicate physical page")
        seen.add(page)
        texts[page - 1] = normalise(document.text)
    return texts


def check_source(source: Path, current: dict) -> list[dict]:
    """Require the freeze check, the frozen file hashes and every PDF on disk."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "freeze.py", "--check"],
        cwd=source,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode or "freeze verified" not in result.stdout.splitlines():
        raise SystemExit(f"Experiment 33 freeze check failed: {result.stderr.strip()[:300]}")
    log("freeze verified")
    for item in current["frozen"]:
        rel = item.get("path", "")
        if rel.startswith("experiments/33-"):
            path = source / rel.split("/", 2)[2]
            if sha256(path) != item["sha256"]:
                raise SystemExit(f"source file differs from plan: {path.name}")
    documents = [
        d for d in read_json(source / "sources.json")["documents"] if d["stratum"] != "synthetic"
    ]
    for doc in documents:
        path = source / doc["local_path"]
        if not path.is_file():
            raise SystemExit(f"missing PDF: {path}")
    labels = read_json(source / "labels.json")["documents"]
    if len(documents) != 40 or set(labels) != {d["doc_id"] for d in documents}:
        raise SystemExit("documents and labels differ from the 40 frozen documents")
    if sum(d["page_count"] for d in documents) != current["source_data"]["pages"]:
        raise SystemExit("page count differs from the plan")
    log(f"inputs: {len(documents)} PDFs, {len(labels)} labels, all present")
    return documents


def render_document(pdf: Path, doc_id: str, pages: int, rules: dict) -> list[dict]:
    """Render every page at 150 DPI with pdftoppm; cap the long side with Lanczos."""
    folder = RENDERS / doc_id
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(  # noqa: S603
            ["pdftoppm", "-r", str(rules["dpi"]), "-png", str(pdf), str(Path(tmp) / "p")],  # noqa: S607
            check=True,
            capture_output=True,
        )
        files = sorted(Path(tmp).glob("p-*.png"), key=lambda p: int(p.stem.split("-")[1]))
        if len(files) != pages:
            raise SystemExit(f"{doc_id}: pdftoppm made {len(files)} images for {pages} pages")
        for number, path in enumerate(files, start=1):
            image = Image.open(path)
            image.load()
            width, height = image.size
            scale = rules["max_long_side_px"] / max(width, height)
            if scale < 1:
                size = (round(width * scale), round(height * scale))
                image = image.resize(size, Image.Resampling.LANCZOS)
            if min(image.size) < rules["min_side_px"]:
                raise SystemExit(f"{doc_id} page {number}: side under {rules['min_side_px']} px")
            target = folder / f"p{number:03d}.png"
            tmp_target = target.with_suffix(".png.tmp")
            image.save(tmp_target, format="PNG")
            tmp_target.replace(target)
            rows.append(
                {
                    "width": image.size[0],
                    "height": image.size[1],
                    "scaled": scale < 1,
                    "png_sha256": sha256(target),
                }
            )
    return rows


def identity() -> dict:
    """Bind resume to the readers, adapters, normaliser, poppler and this runner."""
    import omrs.core.ingestion.normalise as normaliser
    import omrs.integrations.pdf.liteparse as liteparse_adapter
    import omrs.integrations.pdf.pypdf as pypdf_adapter

    poppler = subprocess.run(  # noqa: S603
        ["pdftoppm", "-v"], capture_output=True, text=True, check=False  # noqa: S607
    ).stderr.splitlines()[0]
    return {
        "reader_versions": {name: version(name) for name in TIERS},
        "pillow": version("pillow"),
        "poppler": poppler.strip(),
        "normaliser_version": normaliser.NORMALISER_VERSION,
        "adapter_sha256": {
            "liteparse": sha256(Path(liteparse_adapter.__file__)),
            "pypdf": sha256(Path(pypdf_adapter.__file__)),
            "normaliser": sha256(Path(normaliser.__file__)),
        },
        "runner_sha256": sha256(Path(__file__)),
    }


def main() -> None:
    """Check, extract and render every document; checkpoint after each."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-exp", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    current = plan()
    source = args.source_exp.resolve()
    documents = check_source(source, current)

    from omrs.core.ingestion.normalise import normalise_reader_text
    from omrs.integrations.pdf.liteparse import LiteParseReader
    from omrs.integrations.pdf.pypdf import PyPDFReader

    expected = {
        (r["doc_id"], r["page"], r["tier"]): r
        for r in read_json(EXP38 / "output" / "rescue_text.json")["rows"]
    }
    ident = identity()
    if TARGET.exists() and not args.resume:
        raise SystemExit("output/inputs.json exists; use --resume")
    payload = read_json(TARGET) if TARGET.exists() else {"identity": ident, "rows": [], "done": []}
    if payload["identity"] != ident:
        raise SystemExit("inputs identity changed; resume refused")
    readers = {"liteparse": LiteParseReader(ocr_enabled=False), "pypdf": PyPDFReader()}
    for doc in documents:
        doc_id, count = doc["doc_id"], doc["page_count"]
        if doc_id in payload["done"]:
            log(f"[resume] {doc_id}")
            continue
        pdf = source / doc["local_path"]
        texts = {}
        for tier, reader in readers.items():
            texts[tier] = page_texts(reader.load_data(pdf), tier, count, normalise_reader_text)
            for page, text in enumerate(texts[tier], start=1):
                if text_sha256(text) != expected[(doc_id, page, tier)]["text_sha256"]:
                    raise SystemExit(f"text differs from Experiment 38: {doc_id} p{page} {tier}")
            atomic_json(TEXTS / doc_id / f"{tier}.json", texts[tier])
        renders = render_document(pdf, doc_id, count, current["render"])
        for page in range(1, count + 1):
            row = expected[(doc_id, page, "liteparse")]
            text = texts["liteparse"][page - 1]
            payload["rows"].append(
                {
                    "doc_id": doc_id,
                    "page": page,
                    "class": row["class"],
                    "exclusion_reason": row["exclusion_reason"],
                    "liteparse_sha256": text_sha256(text),
                    "pypdf_sha256": text_sha256(texts["pypdf"][page - 1]),
                    "liteparse_chars": len(text),
                    "scored": bool(text.strip()),
                    **renders[page - 1],
                }
            )
        payload["done"].append(doc_id)
        atomic_json(TARGET, payload)
        log(f"[prepare] {doc_id}: {count} pages, text matches Experiment 38, rendered")
    # Issue #161 quotes the pypdf order; LiteParse holds the same junk tokens in another order.
    pypdf = re.sub(r"\s+", " ", read_json(TEXTS / "rf06" / "pypdf.json")[28])
    liteparse = read_json(TEXTS / "rf06" / "liteparse.json")[28]
    check = {
        "pypdf_holds_issue_quote": ISSUE_161_TEXT in pypdf,
        "liteparse_holds_junk_tokens": all(t in liteparse for t in ("INT", "¡NS", "SRA")),
    }
    payload["rf06_p29_issue_161"] = check
    atomic_json(TARGET, payload)
    scored = sum(r["scored"] for r in payload["rows"])
    log(
        f"[prepare] complete: {len(payload['rows'])} pages, {scored} with text; "
        f"rf06 p29 junk layer as in issue #161: {check}"
    )
    if not all(check.values()):
        raise SystemExit("rf06 page 29 text does not read as in issue #161: stop")


if __name__ == "__main__":
    main()
