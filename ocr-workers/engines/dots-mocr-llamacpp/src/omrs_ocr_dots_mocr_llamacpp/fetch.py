"""``omrs-ocr-fetch``: download the pinned model files and llama.cpp release.

``provision.py dots-mocr-llamacpp --accept-model-licence`` runs this console
script inside the engine environment after ``uv sync --locked``. It is the
only place the engine touches the network. A parse never downloads.

Steps (design D3, D4):

1. download the model file and the image projector from the private
   Hugging Face repository at the pinned revision;
2. download the llama.cpp release archive for the host platform;
3. check the SHA-256 of every download, and stop with the file name on a
   mismatch.

Every download goes to a temporary name. A file takes its final name only
after its hash matches, so a failed run leaves no partial file. Running the
step twice downloads nothing the second time.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

from . import pins
from .paths import cache_dir, llama_dir, models_dir

#: Marker inside the unpacked release: the SHA-256 of the archive it came from.
ARCHIVE_MARKER = ".omrs-archive-sha256"

_CHUNK = 1024 * 1024
_LOGIN_HINT = "Run `hf auth login` or set the HF_TOKEN environment variable, then run again."


class FetchError(Exception):
    """A download or hash check failed; the message names the file."""


def sha256_of(path: Path) -> str:
    """Return the SHA-256 hex digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


# ── Seams (tests replace these) ────────────────────────────────────────────


def get_token() -> str | None:
    """Return the Hugging Face token from ``HF_TOKEN`` or a saved login, or None."""
    from huggingface_hub import get_token as hub_get_token  # engine environment only

    return hub_get_token()


def download_model_file(repo: str, revision: str, name: str, token: str, local_dir: Path) -> Path:
    """Download one file of a Hugging Face repository into *local_dir*; return its path."""
    from huggingface_hub import hf_hub_download  # engine environment only

    downloaded = hf_hub_download(
        repo_id=repo, filename=name, revision=revision, token=token, local_dir=local_dir
    )
    return Path(downloaded)


def download_url(url: str, destination: Path) -> None:
    """Stream a URL to *destination* (a temporary name)."""
    with urllib.request.urlopen(url, timeout=60) as response, destination.open("wb") as handle:  # noqa: S310 - pinned https URL
        shutil.copyfileobj(response, handle, _CHUNK)


# ── Model files ────────────────────────────────────────────────────────────


def fetch_models() -> list[Path]:
    """Download and check the model file and the projector.

    Returns:
        The final paths of both files.

    Raises:
        FetchError: If the revision is not pinned, no token is available,
            a download fails, or a hash does not match.
    """
    if pins.MODEL_REVISION == pins.MODEL_REVISION_PLACEHOLDER:
        raise FetchError(
            "the model revision is not pinned yet: upload the converted files to "
            f"{pins.MODEL_REPO} and set MODEL_REVISION in pins.py to the commit"
        )
    folder = models_dir()
    folder.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []
    token: str | None = None
    for pinned in pins.MODEL_FILES:
        final = folder / pinned.name
        results.append(final)
        if final.is_file() and sha256_of(final) == pinned.sha256:
            continue
        token = token or get_token()
        if not token:
            raise FetchError(
                f"no Hugging Face token for the private repository {pins.MODEL_REPO}. {_LOGIN_HINT}"
            )
        _fetch_model_file(pinned, final, token)
    return results


def _fetch_model_file(pinned: pins.PinnedFile, final: Path, token: str) -> None:
    """Download one file to a temporary folder, check it, and move it into place."""
    scratch = final.parent / f".download-{pinned.name}.tmp"
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True)
    try:
        try:
            downloaded = download_model_file(
                pins.MODEL_REPO, pins.MODEL_REVISION, pinned.name, token, scratch
            )
        except Exception as exc:  # noqa: BLE001 - any failure must name the file
            raise FetchError(
                f"download of {pinned.name} from {pins.MODEL_REPO} failed: "
                f"{type(exc).__name__}: {exc}. {_LOGIN_HINT}"
            ) from exc
        actual = sha256_of(downloaded)
        if actual != pinned.sha256:
            raise FetchError(
                f"{pinned.name} does not match its pinned SHA-256 "
                f"(expected {pinned.sha256}, got {actual}); the file was removed"
            )
        os.replace(downloaded, final)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ── llama.cpp release ──────────────────────────────────────────────────────


def fetch_llama() -> Path:
    """Download, check and unpack the llama.cpp release for this platform.

    Returns:
        The folder that holds ``llama-server``.

    Raises:
        FetchError: If no archive is pinned for this platform, the download
            fails, or the archive hash does not match.
    """
    archive = pins.llama_archive()
    if archive is None:
        raise FetchError(
            f"no llama.cpp release is pinned for this platform ({sys.platform}); "
            "the engine supports macOS on Apple silicon and Linux on x86-64"
        )
    target = llama_dir()
    marker = target / ARCHIVE_MARKER
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == archive.sha256:
        return target
    root = cache_dir()
    root.mkdir(parents=True, exist_ok=True)
    download = root / f"{archive.name}.tmp"
    unpack = root / "llama.cpp.tmp"
    try:
        try:
            download_url(archive.url, download)
        except Exception as exc:  # noqa: BLE001 - any failure must name the file
            raise FetchError(
                f"download of {archive.name} failed: {type(exc).__name__}: {exc}"
            ) from exc
        actual = sha256_of(download)
        if actual != archive.sha256:
            raise FetchError(
                f"{archive.name} does not match its pinned SHA-256 "
                f"(expected {archive.sha256}, got {actual}); the file was removed"
            )
        shutil.rmtree(unpack, ignore_errors=True)
        unpack.mkdir()
        with tarfile.open(download, "r:gz") as tar:
            tar.extractall(unpack, filter="data")
        source = _single_top_folder(unpack)
        (source / ARCHIVE_MARKER).write_text(archive.sha256 + "\n", encoding="utf-8")
        shutil.rmtree(target, ignore_errors=True)
        os.replace(source, target)
    finally:
        download.unlink(missing_ok=True)
        shutil.rmtree(unpack, ignore_errors=True)
    return target


def _single_top_folder(folder: Path) -> Path:
    """Return the one folder inside *folder*, or *folder* itself when there is not exactly one."""
    entries = list(folder.iterdir())
    if len(entries) == 1 and entries[0].is_dir() and not entries[0].is_symlink():
        return entries[0]
    return folder


# ── Entry point ────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001 - console-script signature
    """Console-script entry point; prints a one-line summary to standard error."""
    try:
        models = fetch_models()
        llama = fetch_llama()
    except FetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"dots.mocr llama.cpp engine ready: {len(models)} model files in {models[0].parent}; "
        f"llama.cpp {pins.LLAMA_TAG} in {llama}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
