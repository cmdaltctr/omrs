"""Release check for ``output/shareable/`` (Experiment 35, task 2.10).

A release holds scores, question IDs and rebuild scripts. It never holds corpus
text or personal identifiers (design D10). This module checks a folder against
two rules and lists every offending file:

- ``corpus-text``: a file shares a run of ``ngram_words`` consecutive words
  with a document in the corpus folder. Words are lower-cased runs of letters,
  digits and underscores, so line wraps, spacing and case do not hide a copy.
  JSON and JSON-lines files are compared on their string values.
- ``home-path``: a file names a home folder (``/Users/<name>/``,
  ``/home/<name>/`` or ``C:\\Users\\<name>\\``). A placeholder such as
  ``<name>`` is allowed.

The check streams the corpus and indexes only the shareable files, so memory
use follows the size of the shareable folder.

Run it before any upload::

    uv run --no-sync python experiments/_lib/release_check.py \\
        output/shareable --corpus output/corpus

Standard library only. The exit code is 0 for a clean folder, 1 for findings
and 2 when the check cannot run (missing folder, empty corpus).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = ["DEFAULT_NGRAM_WORDS", "Finding", "check_shareable", "main"]

# Twelve words is longer than a quoted phrase or a title and shorter than a
# sentence, so a copied sentence fails and a short shared term does not.
DEFAULT_NGRAM_WORDS = 12

_JSON_SUFFIXES = {".json", ".jsonl"}
_WORD = re.compile(r"\w+")
# The name part excludes "<" and ">" so a documented placeholder passes.
_HOME_PATH = re.compile(
    r"/(?:Users|home)/[^/\s\"'<>]+"
    r"|[A-Za-z]:\\+Users\\+[^\\/\s\"'<>]+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Finding:
    """One rule failure in one file.

    Attributes:
        path: The offending file.
        rule: ``"corpus-text"`` or ``"home-path"``.
        line: First offending line (1-based), or None for a JSON file's
            corpus-text finding, which has no line of its own.
        detail: A short description. It never repeats the matched text.
    """

    path: Path
    rule: str
    line: int | None
    detail: str


def _json_strings(value: object) -> Iterator[str]:
    """Yield every string value in a parsed JSON document."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _json_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _json_strings(item)


def _comparable_text(path: Path) -> tuple[str, bool]:
    """Return the text to compare for *path* and whether it keeps file lines.

    JSON and JSON-lines files give their string values, one per line, so JSON
    escapes do not split words. A file that does not parse is read as text.
    """
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() in _JSON_SUFFIXES:
        try:
            documents = (
                [json.loads(line) for line in raw.splitlines() if line.strip()]
                if path.suffix.lower() == ".jsonl"
                else [json.loads(raw)]
            )
        except json.JSONDecodeError:
            return raw, True
        return "\n".join(s for doc in documents for s in _json_strings(doc)), False
    return raw, True


def _words(text: str) -> list[tuple[str, int]]:
    """Return ``(word, line)`` pairs: lower-cased words with 1-based lines."""
    return [
        (word, number)
        for number, line in enumerate(text.splitlines(), start=1)
        for word in _WORD.findall(line.lower())
    ]


def _files(folder: Path) -> list[Path]:
    """Return every file under *folder*, sorted."""
    return sorted(p for p in folder.rglob("*") if p.is_file())


def _home_path_findings(path: Path) -> list[Finding]:
    """Return one finding per line of *path* that names a home folder."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [
        Finding(path, "home-path", number, "home-folder path")
        for number, line in enumerate(text.splitlines(), start=1)
        if _HOME_PATH.search(line)
    ]


def _corpus_text_findings(
    shareable_files: Sequence[Path], corpus_dir: Path, ngram_words: int
) -> list[Finding]:
    """Return a finding for each shareable file that copies corpus text."""
    # window hash -> (file, window index, line) for every shareable window.
    index: dict[int, list[tuple[Path, int, int]]] = {}
    keeps_lines: dict[Path, bool] = {}
    for path in shareable_files:
        text, keeps_lines[path] = _comparable_text(path)
        words = _words(text)
        for i in range(len(words) - ngram_words + 1):
            key = hash(tuple(w for w, _ in words[i : i + ngram_words]))
            index.setdefault(key, []).append((path, i, words[i][1]))

    matched: dict[Path, dict[int, int]] = {}
    readable = 0
    for corpus_file in _files(corpus_dir):
        text, _ = _comparable_text(corpus_file)
        words = [w for w, _ in _words(text)]
        if len(words) < ngram_words:
            continue
        readable += 1
        for i in range(len(words) - ngram_words + 1):
            for path, window, line in index.get(hash(tuple(words[i : i + ngram_words])), ()):
                matched.setdefault(path, {})[window] = line
    if readable == 0:
        raise ValueError(f"no readable corpus text under {corpus_dir}")

    return [
        Finding(
            path,
            "corpus-text",
            min(windows.values()) if keeps_lines[path] else None,
            f"{len(windows)} window(s) of {ngram_words} words match the corpus",
        )
        for path, windows in sorted(matched.items())
    ]


def check_shareable(
    shareable_dir: Path, corpus_dir: Path, *, ngram_words: int = DEFAULT_NGRAM_WORDS
) -> list[Finding]:
    """Check a shareable folder for corpus text and home-folder paths.

    Args:
        shareable_dir: The folder that a release would upload.
        corpus_dir: Folder of the corpus documents (text, JSON or JSON lines).
        ngram_words: A shared run of this many words counts as corpus text.

    Returns:
        Every finding, ordered by rule and path. An empty list means clean.

    Raises:
        FileNotFoundError: *shareable_dir* or *corpus_dir* is not a folder.
        ValueError: The corpus holds no readable text. An empty corpus would
            pass every file, so the check stops instead.
    """
    for folder in (shareable_dir, corpus_dir):
        if not folder.is_dir():
            raise FileNotFoundError(f"not a folder: {folder}")
    files = _files(shareable_dir)
    findings = _corpus_text_findings(files, corpus_dir, ngram_words)
    for path in files:
        findings.extend(_home_path_findings(path))
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    """Run the check from the command line and print findings to stderr.

    Args:
        argv: Arguments, or None to read ``sys.argv``.

    Returns:
        0 when clean, 1 when there are findings, 2 when the check cannot run.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("shareable", type=Path, help="folder to release, e.g. output/shareable")
    parser.add_argument("--corpus", type=Path, required=True, help="folder of corpus documents")
    parser.add_argument("--ngram-words", type=int, default=DEFAULT_NGRAM_WORDS)
    args = parser.parse_args(argv)
    try:
        findings = check_shareable(args.shareable, args.corpus, ngram_words=args.ngram_words)
    except (FileNotFoundError, ValueError) as exc:
        print(f"release check cannot run: {exc}", file=sys.stderr)
        return 2
    for f in findings:
        where = f"{f.path}:{f.line}" if f.line else str(f.path)
        print(f"{where}: {f.rule}: {f.detail}", file=sys.stderr)
    print(f"release check: {len(findings)} finding(s)", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
