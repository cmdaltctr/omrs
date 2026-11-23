"""Prepare the Experiment 35 passage files once, before any index build (task 5.4c, design D20).

OMRS builds each chunk ID from the absolute file path, so the passage files
must sit at one fixed path that every index build and the G2 rebuild read. This
tool writes them into ``<passages-dir>/<dataset>/``, outside every run output
folder, with ``passages-tree.json`` (the SHA-256 of each file and of the tree).
Mount that folder at the same absolute path on every pod.

* BioASQ and Legal RAG Bench: one ``<id>.md`` per passage. Legal holds the
  title, the text and the footnotes when present, one blank line apart. A ``#``
  at the start of any line is escaped, so no passage text reads as a heading.
* FreshStack: one ``.md`` per corpus row, named by a short hash of the corpus
  ID. The file holds the published row text only (task 13.5, R-4): a ``.md``
  or ``.mdx`` row is written unchanged; every other row is wrapped in a
  backtick fence one backtick longer than its longest backtick run, at least
  three, with no info string. ``manifest.jsonl`` maps each file to its corpus
  ID, source URL, start and end byte, extension and whether it was fenced.

A second run reuses a file whose bytes are equal and refuses a file whose
bytes differ. Each file is written under a per-process temporary name, then
renamed. Usage::

    uv run --no-sync python prepare35.py --dataset bioasq --passages-dir /workspace/passages
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
for _folder in (EXP_DIR.parent.parent, EXP_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import datasets35  # noqa: E402

_HEADING = re.compile(r"^#", re.MULTILINE)
_TICKS = re.compile(r"`+")
_EXTENSION = re.compile(r"(\.[A-Za-z0-9]+)_\d+_\d+$")
_MARKDOWN = (".md", ".mdx")
#: The published row fields the manifest records beside the ID (pre-registration section 4).
_SOURCE = ("url", "start_byte", "end_byte")


def escape_headings(text: str) -> str:
    """Return *text* with a backslash before a ``#`` that starts a line."""
    return _HEADING.sub(r"\\#", text)


def _ending(text: str) -> str:
    return text if text.endswith("\n") else text + "\n"


def legal_text(passage: Mapping[str, str]) -> str:
    """Return one Legal passage file: title, text and footnotes when present."""
    parts = [passage["title"], passage["text"], passage["footnotes"]]
    return _ending(escape_headings("\n\n".join(p for p in parts if p.strip())))


def export_row(corpus_id: str, text: str) -> tuple[str, str, bool]:
    """Return one FreshStack file text, its source extension and whether it was fenced.

    The extension comes from the corpus ID path (``repo/a.py_0_60`` gives
    ``.py``; a path with no extension gives ``""``).
    """
    found = _EXTENSION.search(corpus_id)
    extension = found.group(1).lower() if found else ""
    if extension in _MARKDOWN:
        return text, extension, False
    longest = max((len(run) for run in _TICKS.findall(text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}\n{_ending(text)}{fence}\n", extension, True


def _freshstack_name(corpus_id: str) -> str:
    return hashlib.sha256(corpus_id.encode("utf-8")).hexdigest()[:16] + ".md"


def _files(dataset: str, root: Path, plan: Mapping[str, Any]) -> Iterator[tuple[str, str, dict]]:
    if dataset == "bioasq":
        for pid, text in sorted(datasets35.bioasq_passages(root).items()):
            yield f"{pid}.md", _ending(escape_headings(text)), {}
    elif dataset == "legal":
        for pid, passage in sorted(datasets35.legal_passages(root).items()):
            yield f"{pid}.md", legal_text(passage), {}
    else:
        pin = datasets35.freshstack_pin(plan)
        for corpus_id, text, source in datasets35.freshstack_corpus(root, pin):
            body, extension, fenced = export_row(corpus_id, text)
            name = _freshstack_name(corpus_id)
            row = {"freshstack_id": corpus_id, "extension": extension, "fenced": fenced}
            yield name, body, {**row, **{k: source[k] for k in _SOURCE}}


def _write_once(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise datasets35.DatasetError(
                f"{path.name} in {path.parent} differs from the prepared text; it is never "
                "reused or replaced. Move the folder away and prepare again."
            )
        return
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def prepare(dataset: str, root: Path, passages_dir: Path, *, plan: Mapping[str, Any]) -> Path:
    """Write the passage files of *dataset* and their tree record; return the folder.

    Raises:
        DatasetError: An existing file differs, or an input does not match its pin.
    """
    folder = passages_dir / dataset
    folder.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    manifest: list[dict[str, Any]] = []
    for name, text, extra in _files(dataset, root, plan):
        data = text.encode("utf-8")
        _write_once(folder / name, data)
        hashes[name] = hashlib.sha256(data).hexdigest()
        if extra:
            manifest.append({"file": name, **extra})
    if manifest:
        lines = "".join(json.dumps(row, sort_keys=True) + "\n" for row in manifest)
        _write_once(folder / datasets35.MANIFEST_FILE, lines.encode("utf-8"))
        hashes[datasets35.MANIFEST_FILE] = hashlib.sha256(lines.encode("utf-8")).hexdigest()
    record = {"files": dict(sorted(hashes.items())), "tree_sha256": datasets35.tree_hash(hashes)}
    body = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _write_once(folder / datasets35.TREE_FILE, body)
    datasets35.verify_tree(folder)
    return folder


def main(argv: Sequence[str] | None = None) -> int:
    """Prepare one dataset's passage files; print the tree hash; return 0, or 2 on an error."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", required=True, choices=datasets35.PASSAGE_DATASETS)
    parser.add_argument("--passages-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    plan = json.loads((EXP_DIR / "plan.json").read_text(encoding="utf-8"))
    try:
        folder = prepare(
            args.dataset, datasets35.data_root(), args.passages_dir.resolve(), plan=plan
        )
    except datasets35.DatasetError as error:
        print(f"[error] {error}", flush=True)
        return 2
    print(f"[prepare] {folder}: tree_sha256 {datasets35.verify_tree(folder)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
