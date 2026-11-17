"""Release check for ``output/shareable/`` (Experiment 35, task 2.10).

A release holds scores, question IDs and rebuild scripts. It never holds corpus
text or personal identifiers (design D10). This module checks a folder against
these rules and lists every offending file:

- ``corpus-text``: a file shares a run of ``ngram_words`` consecutive words
  with a document in the corpus folder. Words are lower-cased runs of letters,
  digits and underscores, so line wraps, spacing and case do not hide a copy.
  JSON and JSON-lines files are compared on their string values.
- ``home-path``: a file names a home folder (``/Users/<name>/``,
  ``/home/<name>/`` or ``C:\\Users\\<name>\\``). A placeholder such as
  ``<name>`` is allowed.
- ``email``: a file holds an email address.
- ``login-name``: a file holds, as a whole word in any case, one of the
  login or personal names the operator passes (``--name``).

Released answers sit in their own folder (pre-registration section 19). They
may quote evidence, so that folder gets the identifier rules only
(``home-path``, ``email``, ``login-name``), never the corpus-text rule::

    uv run --no-sync python experiments/_lib/release_check.py \\
        output/release-answers --answers --name <login>

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

__all__ = ["DEFAULT_NGRAM_WORDS", "Finding", "check_answer_release", "check_shareable", "main"]

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
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


@dataclass(frozen=True)
class Finding:
    """One rule failure in one file.

    Attributes:
        path: The offending file.
        rule: ``"corpus-text"``, ``"home-path"``, ``"email"`` or ``"login-name"``.
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


def _identifier_findings(path: Path, names: Sequence[str]) -> list[Finding]:
    """Return one finding per rule and line of *path* that names a person or a home folder."""
    rules = [("home-path", _HOME_PATH, "home-folder path"), ("email", _EMAIL, "email address")]
    if names:
        words = "|".join(re.escape(name) for name in names)
        pattern = re.compile(rf"(?<!\w)(?:{words})(?!\w)", re.IGNORECASE)
        rules.append(("login-name", pattern, "login or personal name"))
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [
        Finding(path, rule, number, detail)
        for rule, pattern, detail in rules
        for number, line in enumerate(text.splitlines(), start=1)
        if pattern.search(line)
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
    shareable_dir: Path,
    corpus_dir: Path,
    *,
    ngram_words: int = DEFAULT_NGRAM_WORDS,
    names: Sequence[str] = (),
) -> list[Finding]:
    """Check a shareable folder for corpus text, home-folder paths, emails and names.

    Args:
        shareable_dir: The folder that a release would upload.
        corpus_dir: Folder of the corpus documents (text, JSON or JSON lines).
        ngram_words: A shared run of this many words counts as corpus text.
        names: Login and personal names that no file may hold.

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
        findings.extend(_identifier_findings(path, names))
    return findings


def check_answer_release(answers_dir: Path, *, names: Sequence[str] = ()) -> list[Finding]:
    """Check the answer release folder with the identifier rules only.

    Released answers may quote evidence, so the corpus-text rule does not run.

    Args:
        answers_dir: The folder of released answers.
        names: Login and personal names that no file may hold.

    Returns:
        Every finding, ordered by path. An empty list means clean.

    Raises:
        FileNotFoundError: *answers_dir* is not a folder.
    """
    if not answers_dir.is_dir():
        raise FileNotFoundError(f"not a folder: {answers_dir}")
    return [f for path in _files(answers_dir) for f in _identifier_findings(path, names)]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the check from the command line and print findings to stderr.

    Args:
        argv: Arguments, or None to read ``sys.argv``.

    Returns:
        0 when clean, 1 when there are findings, 2 when the check cannot run.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("shareable", type=Path, help="folder to release, e.g. output/shareable")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--corpus", type=Path, help="folder of corpus documents")
    mode.add_argument(
        "--answers", action="store_true", help="answer release folder: identifier rules only"
    )
    parser.add_argument("--ngram-words", type=int, default=DEFAULT_NGRAM_WORDS)
    parser.add_argument(
        "--name", action="append", default=[], help="a login or personal name (repeat)"
    )
    args = parser.parse_args(argv)
    try:
        if args.answers:
            findings = check_answer_release(args.shareable, names=args.name)
        else:
            findings = check_shareable(
                args.shareable, args.corpus, ngram_words=args.ngram_words, names=args.name
            )
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
