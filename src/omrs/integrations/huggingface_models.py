"""Hugging Face model search, file list and download (add-model-search-and-download D3).

The search and the file list are fixed ``GET`` reads over ``httpx``. They
send no ``Authorization`` header and read no token, because the metadata of
a gated repository is public. Each read has a 10-second timeout, a body
limit and no redirect to another host. The download uses ``huggingface_hub``,
which is imported inside the functions that need it (ADR-024).

This module is a leaf: it imports no ``omrs.core`` and no ``omrs.transports``
module. The limits below copy those of ``transports/api/provider_fetch.py``.
No exception text, URL or header reaches an error message, so a path or a
token cannot leak through this code.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

#: The only host these reads talk to.
HOST = "huggingface.co"
#: Seconds one request may take (connect, read, write and pool).
FETCH_TIMEOUT_SECONDS = 10.0
#: Most bytes of one response body the adapter reads.
BODY_LIMIT = 8 * 1024 * 1024
#: Most redirects on the same host that one read follows.
MAX_REDIRECTS = 3
#: Results the search asks for.
SEARCH_LIMIT = 20

#: Free space that must remain after a download (spec "Free space is checked first").
SPACE_MARGIN_BYTES = 1024**3

_API = f"https://{HOST}/api/models"
_SEARCH_FIELDS = "&expand[]=downloads&expand[]=likes&expand[]=gated&expand[]=lastModified"


class ModelHostError(Exception):
    """A read of the model host failed.

    Attributes:
        reason: One of ``network``, ``not-found`` or ``gated``.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class DownloadCancelled(Exception):
    """The cancel event stopped a download.

    ``huggingface_hub`` 1.27 deletes the partial file when a download stops,
    so a later download of the same file starts from zero. There is no resume.
    """


@dataclass(frozen=True)
class RepoSummary:
    """One search hit."""

    id: str
    downloads: int
    likes: int
    gated: bool
    last_modified: str | None


@dataclass(frozen=True)
class RepoFiles:
    """The GGUF files of a repository at one pinned revision.

    Attributes:
        repo: The repository id, ``org/name``.
        revision: The commit hash that the file list was read at.
        gated: True when the repository needs an accepted licence.
        files: ``(path, size in bytes)`` for each ``.gguf`` file.
    """

    repo: str
    revision: str
    gated: bool
    files: tuple[tuple[str, int], ...]


def _fetch(client: httpx.Client, url: str) -> tuple[int, bytes]:
    """Return the status and the body (2xx only) of a ``GET`` to *url*.

    Follows a redirect only when the target is on the same host over HTTPS.

    Raises:
        ModelHostError: ``network`` for a transport error, an oversize body,
            a redirect to another host or too many redirects.
    """
    current = httpx.URL(url)
    for _ in range(MAX_REDIRECTS + 1):
        try:
            with client.stream(
                "GET",
                current,
                timeout=httpx.Timeout(FETCH_TIMEOUT_SECONDS),
                follow_redirects=False,
                auth=None,
            ) as response:
                if response.is_redirect:
                    current = current.join(response.headers["location"])
                    if current.scheme != "https" or current.host != HOST:
                        raise ModelHostError("network")
                    continue
                if not 200 <= response.status_code < 300:
                    return response.status_code, b""
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > BODY_LIMIT:
                        raise ModelHostError("network")
                    chunks.append(chunk)
                return response.status_code, b"".join(chunks)
        except ModelHostError:
            raise
        except Exception:  # noqa: BLE001 - the text may hold the URL; report only the reason
            raise ModelHostError("network") from None
    raise ModelHostError("network")


def _get_json(client: httpx.Client, url: str) -> Any:
    """Return the decoded JSON body of *url*.

    Raises:
        ModelHostError: ``not-found`` for a 404, else ``network`` for any
            other failure, including a body that is not JSON.
    """
    status, body = _fetch(client, url)
    if status == 404:
        raise ModelHostError("not-found")
    if not 200 <= status < 300:
        raise ModelHostError("network")
    try:
        return json.loads(body)
    except ValueError:
        raise ModelHostError("network") from None


def _count(value: object) -> int:
    """Return *value* as a count; a missing value is 0."""
    if value is None:
        return 0
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise ModelHostError("network")


def _summary(item: object) -> RepoSummary:
    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
        raise ModelHostError("network")
    modified = item.get("lastModified")
    return RepoSummary(
        id=item["id"],
        downloads=_count(item.get("downloads")),
        likes=_count(item.get("likes")),
        gated=bool(item.get("gated")),
        last_modified=modified if isinstance(modified, str) else None,
    )


def search_models(query: str, *, client: httpx.Client | None = None) -> list[RepoSummary]:
    """Search GGUF repositories, most downloaded first.

    Args:
        query: The search text. The route has already checked it.
        client: An ``httpx`` client, for tests. A default client is built
            and closed when it is ``None``.

    Returns:
        Up to 20 hits.

    Raises:
        ModelHostError: ``network`` for a timeout, an HTTP error, an oversize
            body or an unexpected response shape.
    """
    url = (
        f"{_API}?search={quote(query, safe='')}&filter=gguf&sort=downloads"
        f"&direction=-1&limit={SEARCH_LIMIT}{_SEARCH_FIELDS}"
    )
    payload = _with_client(client, lambda c: _get_json(c, url))
    if not isinstance(payload, list):
        raise ModelHostError("network")
    return [_summary(item) for item in payload]


def list_repo_files(repo: str, *, client: httpx.Client | None = None) -> RepoFiles:
    """List the ``.gguf`` files of *repo* at its current revision.

    Two reads: the model (for the revision hash and the gated flag), then the
    recursive file tree at that hash. Sizes come from the tree.

    Args:
        repo: A repository id, ``org/name``. The route has already checked it.
        client: An ``httpx`` client, for tests.

    Returns:
        The pinned revision, the gated flag and the GGUF files with sizes.

    Raises:
        ModelHostError: ``not-found`` for a 404 or a repository with no GGUF
            file; ``network`` for any other failure.
    """
    path = quote(repo, safe="/")

    def read(c: httpx.Client) -> RepoFiles:
        info = _get_json(c, f"{_API}/{path}?expand[]=sha&expand[]=gated")
        if not isinstance(info, dict) or not isinstance(info.get("sha"), str):
            raise ModelHostError("network")
        sha: str = info["sha"]
        tree = _get_json(c, f"{_API}/{path}/tree/{quote(sha, safe='')}?recursive=true")
        if not isinstance(tree, list):
            raise ModelHostError("network")
        files = tuple(_gguf_entries(tree))
        if not files:
            raise ModelHostError("not-found")
        return RepoFiles(repo=repo, revision=sha, gated=bool(info.get("gated")), files=files)

    return _with_client(client, read)


def _gguf_entries(tree: list[Any]) -> list[tuple[str, int]]:
    """Return ``(path, size)`` for each ``.gguf`` file in a tree listing."""
    entries: list[tuple[str, int]] = []
    for item in tree:
        if not isinstance(item, dict):
            raise ModelHostError("network")
        name = item.get("path")
        if item.get("type") != "file" or not isinstance(name, str) or not name.endswith(".gguf"):
            continue
        size = item.get("size")
        if not isinstance(size, int) or isinstance(size, bool):
            raise ModelHostError("network")
        entries.append((name, size))
    return entries


def _with_client(client: httpx.Client | None, action: Any) -> Any:
    """Run ``action(client)`` and close a client that this function built."""
    if client is not None:
        return action(client)
    with httpx.Client(timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=False) as own:
        return action(own)


def hub_cache_folder() -> str:
    """Return the folder that the download writes to.

    This is ``HF_HUB_CACHE``, else ``HF_HOME/hub``, else
    ``~/.cache/huggingface/hub``; ``huggingface_hub`` resolves the order.
    """
    from huggingface_hub import constants

    return str(constants.HF_HUB_CACHE)


def _hub_error(error: Exception) -> ModelHostError:
    """Map a ``huggingface_hub`` or transport error to a fixed reason.

    401 and 403 give ``gated``; 404 and the not-found error classes give
    ``not-found``; everything else gives ``network``. The error text is
    dropped.
    """
    from huggingface_hub import errors

    status = getattr(getattr(error, "response", None), "status_code", None)
    if isinstance(error, errors.GatedRepoError) or status in (401, 403):
        return ModelHostError("gated")
    if isinstance(error, errors.LocalEntryNotFoundError):
        return ModelHostError("network")
    not_found = (
        errors.RepositoryNotFoundError,
        errors.RevisionNotFoundError,
        errors.EntryNotFoundError,
    )
    if isinstance(error, not_found) or status == 404:
        return ModelHostError("not-found")
    return ModelHostError("network")


def bytes_to_download(
    repo: str,
    revision: str,
    filenames: Sequence[str],
    *,
    token: str | None,
) -> int:
    """Return the bytes still to download for *filenames* at *revision*.

    Each file is checked with ``hf_hub_download(dry_run=True)``. A file that
    is already in the cache counts as 0 bytes.

    Args:
        repo: A repository id, ``org/name``.
        revision: The pinned commit hash from :func:`list_repo_files`.
        filenames: The files of the chosen set.
        token: The token from the environment of ``omrs web``, or ``None``.
            ``None`` turns the library's stored-token lookup off.

    Returns:
        The sum of the sizes of the files that will download.

    Raises:
        ModelHostError: ``gated`` for 401 or 403, ``not-found`` for 404,
            ``network`` for any other failure.
    """
    from huggingface_hub import hf_hub_download

    total = 0
    for filename in filenames:
        try:
            info = hf_hub_download(
                repo_id=repo,
                filename=filename,
                revision=revision,
                token=token if token else False,
                dry_run=True,
            )
        except Exception as error:  # noqa: BLE001 - mapped to a fixed reason below
            raise _hub_error(error) from None
        if info.will_download:
            total += info.file_size
    return total


def has_room(needed_bytes: int, free_bytes: int) -> bool:
    """Return True when the cache disk can take *needed_bytes*.

    The free space must cover the size plus a 1 GiB margin. A set that is
    fully cached (0 bytes) always has room.
    """
    return needed_bytes == 0 or free_bytes >= needed_bytes + SPACE_MARGIN_BYTES


def _watch_for_cancel(cancel: threading.Event, done: threading.Event) -> None:
    """Abort the Xet session when *cancel* is set before *done* is.

    ``hf_xet`` swallows errors that the progress callback raises, so a Xet
    transfer ignores the cancel check in the progress class. The private
    ``abort_xet_session`` stops it from another thread. When the function is
    missing in a later library version, only this fast stop is lost.
    """
    while not done.wait(0.1):
        if cancel.is_set():
            try:
                from huggingface_hub.utils._xet import abort_xet_session

                abort_xet_session()
            except (ImportError, AttributeError):
                pass
            return


def download_files(
    repo: str,
    revision: str,
    filenames: Sequence[str],
    *,
    on_bytes: Callable[[int], None],
    cancel: threading.Event,
    token: str | None,
) -> str:
    """Download *filenames* into the Hugging Face cache and block until done.

    Call this in a worker thread. Each file is one ``hf_hub_download`` at the
    pinned *revision*. Byte counts reach *on_bytes* through a progress class.
    A set *cancel* event raises from the progress class (stops the HTTP path)
    and, through a short-lived watcher thread, aborts the Xet session.

    Args:
        repo: A repository id, ``org/name``.
        revision: The pinned commit hash from :func:`list_repo_files`.
        filenames: The files of the chosen set, in download order.
        on_bytes: Called with the bytes of each progress step.
        cancel: Set to stop the download. It is also checked between files.
        token: The token from the environment of ``omrs web``, or ``None``.
            ``None`` turns the library's stored-token lookup off.

    Returns:
        The local path of the first file.

    Raises:
        DownloadCancelled: *cancel* was set. The partial file is lost.
        ModelHostError: ``gated`` for 401 or 403, ``not-found`` for 404,
            ``network`` for any other failure.
    """
    from huggingface_hub import hf_hub_download
    from huggingface_hub.utils import tqdm as hub_tqdm

    class _Progress(hub_tqdm):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs["disable"] = True
            super().__init__(*args, **kwargs)

        def update(self, n: float | None = 1) -> Any:
            if cancel.is_set():
                raise DownloadCancelled
            if not n:
                return None
            on_bytes(int(n))
            return super().update(n)

    done = threading.Event()
    watcher = threading.Thread(target=_watch_for_cancel, args=(cancel, done), daemon=True)
    watcher.start()
    first: str | None = None
    try:
        for filename in filenames:
            if cancel.is_set():
                raise DownloadCancelled
            try:
                path = hf_hub_download(
                    repo_id=repo,
                    filename=filename,
                    revision=revision,
                    tqdm_class=_Progress,
                    token=token if token else False,
                )
            except DownloadCancelled:
                raise
            except Exception as error:  # noqa: BLE001 - mapped to a fixed reason below
                if cancel.is_set():
                    raise DownloadCancelled from None
                raise _hub_error(error) from None
            first = first or str(path)
    finally:
        done.set()
        watcher.join(timeout=1.0)
    return first or ""
