"""Build the page judge of a document router (change document-reading-routers, D12).

This is the only module outside ``core/providers/decision/`` that reaches a
concrete decision model adapter, through the lazy registry. The router page
rule gets the built :class:`PageJudge` on ``RuleContext.judge`` and imports no
provider.

- A router names a decision model entry. An entry whose address is not a
  loopback address is hosted. A hosted router without ``send_off_machine``
  gets ``needs-opt-in`` and sends nothing (design D7).
- Key references resolve through the provider key rules of ``omrs.jsonc``
  (ADR-083, gotcha 18): ``env://``, ``file://`` inside ``secrets/`` and
  ``keychain://``. A literal key is never used.
- The checks of design D6 (quantisation, a text probe, the projector smoke
  test) run on the first read of ``PageJudge.status``, under the entry's own
  lock. A pass is kept for the process, a failure for ``FAILED_CHECK_SECONDS``
  only, so a server started later is found. :func:`reset_decision_checks`
  clears them.
- A managed ``llamacpp`` entry sends every request through the lease of its
  runtime ``decision-<name>``, which starts ``llama-server`` on the first
  request. A build below the floor reads ``wrong-build``.
- Logs hold fixed reasons and counts only: never page text, images, keys or
  reply bodies.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic
from types import ModuleType
from typing import Any

import httpx

from .core.providers.decision import base, checks, registry
from .integrations.llamacpp_runtime import RuntimeRequestFailed, RuntimeUnavailable

logger = logging.getLogger(__name__)

UNKNOWN_MODEL = "unknown-model"
UNREACHABLE = "unreachable"
NEEDS_OPT_IN = "needs-opt-in"
REQUEST_FAILED = "request-failed"
WRONG_BUILD = "wrong-build"
#: The router name that means "no router".
NO_ROUTER = "none"
#: Seconds one request may take. Experiment 43 measured about 4 s per image page.
REQUEST_TIMEOUT = 120.0
#: The one-question text request of the check: content free, so nothing private leaves.
PROBE_QUESTION = "Is this sentence written in English?"
PROBE_TEXT = "This is a short test sentence."

#: Seconds a failed check result is kept before the next read checks again.
FAILED_CHECK_SECONDS = 60.0
#: Entry fingerprint to (check result, clock time), and to the lock its checks run under.
_checks: dict[str, tuple[CheckResult, float]] = {}
_entry_locks: dict[str, threading.Lock] = {}
#: Guards ``_checks``, ``_entry_locks`` and ``_judges``. Held for lookups only.
_checks_lock = threading.Lock()
#: The judges :func:`page_judge_for` built, by router recipe and entry fingerprint.
_judges: dict[str, PageJudge | None] = {}


@dataclass(frozen=True)
class CheckResult:
    """The result of the design D6 checks for one entry.

    Attributes:
        status: ``None`` when ready, else the fixed reason.
        quantisation: The quantisation line the entry and the router test show.
    """

    status: str | None
    quantisation: str


def reset_decision_checks() -> None:
    """Forget every cached check result (a test seam; the Test button re-runs checks)."""
    with _checks_lock:
        _checks.clear()
        _entry_locks.clear()
        _judges.clear()


def _kept(fingerprint: str) -> tuple[CheckResult | None, threading.Lock]:
    """Return the kept result of *fingerprint* (a pass, or a recent failure) and its lock."""
    with _checks_lock:
        result, made = _checks.get(fingerprint, (None, 0.0))
        lock = _entry_locks.setdefault(fingerprint, threading.Lock())
    if result is None or (result.status and monotonic() - made >= FAILED_CHECK_SECONDS):
        return None, lock
    return result, lock


def _field(entry: Any, name: str, default: Any = None) -> Any:
    """Return field *name* of a settings map entry given as a mapping or an object."""
    if isinstance(entry, Mapping):
        return entry.get(name, default)
    return getattr(entry, name, default)


def resolve_key_reference(reference: str | None, *, keychain: Any = None) -> str | None:
    """Return the key that *reference* names, or ``None``.

    Args:
        reference: ``env://NAME``, ``file://<path inside secrets/>`` or
            ``keychain://<provider>``. A literal key resolves to ``None``.
        keychain: The keychain store to read; ``None`` builds a ``KeychainStore``
            when a ``keychain://`` reference needs one.
    """
    if not reference:
        return None
    from .config.user_config import (
        CONFIG_FILE,
        SECRETS_DIR,
        KeychainRef,
        _resolve_reference,
        user_config_dir,
    )

    folder = user_config_dir()
    resolved, _problem = _resolve_reference(
        "key", reference, folder / SECRETS_DIR, folder / CONFIG_FILE
    )
    if not isinstance(resolved, KeychainRef):
        return resolved
    from .integrations.keychain import KeychainStore, KeychainUnavailableError

    store = keychain if keychain is not None else KeychainStore()
    try:
        secret = store.read(resolved.provider) if store.available else None
    except KeychainUnavailableError:
        return None
    return secret.reveal() if secret is not None else None


def _identity(entry: Any) -> dict[str, Any]:
    """Return the kind and model identity of *entry* (design D9)."""
    identity = {"kind": _field(entry, "kind"), "model": _field(entry, "model")}
    if _field(entry, "server") == "managed":
        identity["model_sha256"] = _field(entry, "model_sha256")
        identity["projector_sha256"] = _field(entry, "projector_sha256")
    return identity


_FINGERPRINT_FIELDS = (
    "kind", "address", "model", "images", "key", "server",
    "model_file", "projector_file", "model_sha256", "projector_sha256",
)  # fmt: skip


def _fingerprint(entry: Any, images: bool) -> str:
    """Return the cache key of the checks: the entry fields (a key reference, never a key)."""
    data = {name: _field(entry, name) for name in _FINGERPRINT_FIELDS}
    data["router_images"] = images
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


class PageJudge:
    """Ask one router's decision model whether a page's text can be kept.

    Attributes:
        name: The router name.
        question: The router question.
        threshold: P(yes) below this rejects the page's text.
        images: Whether the page image goes with the text.
        max_chars: The page text is cut to this many characters.
        hosted: Whether the decision model is not on a loopback address.
        identity: The decision model kind and model identity (design D9).
    """

    def __init__(
        self,
        *,
        name: str,
        router: Any,
        entry: Any,
        adapter: ModuleType | None,
        status: str | None,
        key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        runtime: Any = None,
    ) -> None:
        """Hold the router recipe, the entry and a fixed reason when it cannot run.

        *runtime* is the managed entry's ``RuntimeSpec``, the reason it cannot
        be built, or ``None`` for an entry OMRS does not start.
        """
        self.name = name
        self.question = str(_field(router, "question", ""))
        self.threshold = float(_field(router, "threshold", 0.0))
        self.images = bool(_field(router, "images", False))
        self.max_chars = int(_field(router, "max_chars", 2000))
        address = str(_field(entry, "address", "") or "")
        self.hosted = bool(address) and not base.is_loopback(address)
        self.identity = _identity(entry) if entry is not None else {}
        # The adapter is None only with a fixed reason, and then nothing is sent.
        self._adapter: Any = adapter
        self._entry, self._address = entry, address
        self._static_status, self._key, self._transport = status, key, transport
        self._runtime = runtime

    def __repr__(self) -> str:
        """Show the router name and kind only."""
        return f"PageJudge(name={self.name!r}, kind={self.identity.get('kind')!r})"

    @property
    def status(self) -> str | None:
        """``None`` when the judge can run, else the fixed reason. Runs the checks once."""
        return self._check().status

    @property
    def quantisation(self) -> str:
        """The quantisation line of the checks ("Quantisation not checked" when unknown)."""
        return self._check().quantisation

    def judge(self, text: str, image: bytes | None) -> float | None:
        """Return P(yes) for one page, or ``None`` when it cannot run or the request failed.

        Never raises. Sends nothing when :attr:`status` holds a reason.
        """
        try:
            if self.status is not None:
                return None
            return self._score(self.question, text[: self.max_chars], image)
        except Exception as error:  # noqa: BLE001 - a router never fails a file (design D8)
            logger.debug("A decision model request failed: %s.", _reason(error))
            return None

    # ── Requests ────────────────────────────────────────────────────────

    def _post(self, question: str, text: str, image: bytes | None) -> Any:
        """Send one request (through the runtime lease of a managed entry). Raises on failure."""
        if self._runtime is None:
            return self._send(self._address, question, text, image)
        from .compose_runtime_manager import runtime_manager

        lease = runtime_manager().lease(self._runtime)
        return lease.request(lambda address: self._send(address, question, text, image))

    def _send(self, address: str, question: str, text: str, image: bytes | None) -> Any:
        request = self._adapter.build_request(
            address=address,
            model=str(_field(self._entry, "model", "")),
            question=question,
            text=text,
            image=image,
            key=self._key,
            hosted=self.hosted,
        )
        with httpx.Client(
            transport=self._transport, timeout=REQUEST_TIMEOUT, trust_env=self.hosted
        ) as client:
            response = client.post(request.url, json=request.body, headers=request.headers)
            response.raise_for_status()
            return response.json()

    def _score(self, question: str, text: str, image: bytes | None) -> float:
        return float(self._adapter.read_reply(self._post(question, text, image)))

    def _ask(self, question: str, text: str, image: bytes) -> float | None:
        """Ask for the smoke test; ``None`` on any failure."""
        try:
            return self._score(question, text, image)
        except Exception:  # noqa: BLE001 - a failed answer fails the smoke test
            return None

    # ── Checks (design D6) ──────────────────────────────────────────────

    def _check(self) -> CheckResult:
        if self._static_status is not None:
            return CheckResult(self._static_status, checks.NOT_CHECKED_TEXT)
        fingerprint = _fingerprint(self._entry, self.images)
        result, lock = _kept(fingerprint)
        if result is None:
            with lock:
                result, _ = _kept(fingerprint)  # another thread may have checked meanwhile
                if result is None:
                    result = self._run_checks()
                    with _checks_lock:
                        _checks[fingerprint] = (result, monotonic())
                    if result.status is not None:
                        kind = self.identity["kind"]
                        logger.warning("The %s decision model cannot run: %s.", kind, result.status)
        return result

    def _run_checks(self) -> CheckResult:
        local = bool(getattr(self._adapter, "LOCAL_RUNTIME", False))
        managed = local and _field(self._entry, "server") == "managed"
        quant = checks.QuantisationResult(checks.NOT_CHECKED, None, checks.NOT_CHECKED_TEXT)
        if managed and _field(self._entry, "model_file"):
            quant = checks.quantisation_from_file(str(_field(self._entry, "model_file")))
        if quant.status == checks.REFUSED:
            return CheckResult(checks.QUANTISATION_REFUSED, quant.message)
        if self.images and not _field(self._entry, "images", False):
            return CheckResult(checks.PROJECTOR_NOT_LOADED, quant.message)
        if self.images and managed and not _field(self._entry, "projector_file"):
            return CheckResult(checks.PROJECTOR_NOT_LOADED, quant.message)
        if isinstance(self._runtime, str):  # the managed runtime cannot be built
            return CheckResult(UNREACHABLE, quant.message)
        try:
            reply = self._post(PROBE_QUESTION, PROBE_TEXT, None)
            self._adapter.read_reply(reply)
        except RuntimeUnavailable as error:
            reason = WRONG_BUILD if error.reason == WRONG_BUILD else UNREACHABLE
            return CheckResult(reason, quant.message)
        except (httpx.TransportError, RuntimeRequestFailed):
            return CheckResult(UNREACHABLE, quant.message)
        except Exception:  # noqa: BLE001 - HTTP error or malformed reply
            return CheckResult(REQUEST_FAILED, quant.message)
        if local and quant.status == checks.NOT_CHECKED:
            name = self._adapter.reported_model(reply) or str(_field(self._entry, "model", ""))
            quant = checks.quantisation_from_name(name)
            if quant.status == checks.REFUSED:
                return CheckResult(checks.QUANTISATION_REFUSED, quant.message)
        if self.images:
            smoke = checks.run_smoke_test(self._ask)
            if smoke is not None:
                return CheckResult(smoke, quant.message)
        return CheckResult(None, quant.message)


def _reason(error: Exception) -> str:
    """Return the fixed reason of a failed request; never the error text."""
    if isinstance(error, base.MalformedReplyError | json.JSONDecodeError):
        return base.MALFORMED_REPLY
    if isinstance(error, httpx.TransportError):
        return UNREACHABLE
    return REQUEST_FAILED


def build_page_judge(
    settings: Any, *, router_name: str | None = None, transport: httpx.BaseTransport | None = None
) -> PageJudge | None:
    """Build the page judge of the selected router, or ``None`` with no router.

    Building sends nothing; the checks run on the first read of ``status``.

    Args:
        settings: ``Settings`` or ``EffectiveSettings``. Read through
            ``document_router``, ``document_routers`` and ``decision_models``.
        router_name: The router to use. ``None`` means ``settings.document_router``;
            ``""`` or ``"none"`` means no router.
        transport: An ``httpx`` transport for every request (tests pass a
            ``MockTransport``).

    Returns:
        ``None`` when no router is selected or the name is not a router entry,
        else a :class:`PageJudge` whose ``status`` is ``None`` or a fixed reason.
    """
    name = getattr(settings, "document_router", "") if router_name is None else router_name
    name = (name or "").strip()
    if name in ("", NO_ROUTER):
        return None
    router = (getattr(settings, "document_routers", None) or {}).get(name)
    if router is None:
        logger.warning("The selected document router is not defined, so no router runs.")
        return None
    model = _field(router, "model")
    entry = (getattr(settings, "decision_models", None) or {}).get(model)
    runtime = _runtime_of(settings, str(model), entry)
    opt_in = bool(_field(router, "send_off_machine", False))
    return _make_judge(name, router, entry, transport, opt_in=opt_in, runtime=runtime)


def _runtime_of(settings: Any, model: str, entry: Any) -> Any:
    """Return the runtime of a managed ``llamacpp`` entry (spec or reason), else ``None``."""
    from .compose_runtimes import decision_runtime_for

    return decision_runtime_for(settings, model, entry)


def _make_judge(
    name: str,
    router: Any,
    entry: Any,
    transport: httpx.BaseTransport | None,
    *,
    opt_in: bool,
    runtime: Any = None,
) -> PageJudge:
    """Build a judge of *entry* for *router*; a hosted entry needs *opt_in* to send."""
    kind = _field(entry, "kind") if entry is not None else None
    adapter = registry.get(kind) if kind in registry.kinds() else None
    common = {"name": name, "router": router, "entry": entry, "transport": transport}
    if adapter is None:
        return PageJudge(adapter=None, status=UNKNOWN_MODEL, **common)
    judge = PageJudge(adapter=adapter, status=None, **common)
    if judge.hosted and not opt_in:
        return PageJudge(adapter=adapter, status=NEEDS_OPT_IN, **common)
    reference = _field(entry, "key")
    key = resolve_key_reference(reference) if reference else None
    if reference and key is None:
        return PageJudge(adapter=adapter, status=REQUEST_FAILED, **common)
    return PageJudge(adapter=adapter, status=None, key=key, runtime=runtime, **common)


_ROUTER_FIELDS = ("model", "question", "threshold", "images", "max_chars", "send_off_machine")


def _judge_key(settings: Any, name: str) -> str:
    """Return the cache key of a judge: the router name, its recipe and its entry."""
    router = (getattr(settings, "document_routers", None) or {}).get(name)
    model = _field(router, "model") if router is not None else None
    entry = (getattr(settings, "decision_models", None) or {}).get(model) if model else None
    recipe = {f: _field(router, f) for f in _ROUTER_FIELDS} if router is not None else None
    data = {"name": name, "router": recipe, "entry": _fingerprint(entry, False)}
    return json.dumps(data, sort_keys=True, default=str)


def page_judge_for(settings: Any) -> PageJudge | None:
    """Return the page judge of ``settings.document_router``, one object per recipe.

    The composition root calls this each time it builds OCR routes for
    ingestion. Settings that name the same router with the same recipe and
    decision model entry share one judge, so a key reference resolves once.
    :func:`reset_decision_checks` forgets the judges.

    Args:
        settings: ``Settings`` or ``EffectiveSettings``. A step overlay has
            already put the step's router in ``document_router``.

    Returns:
        ``None`` with no router, else the shared :class:`PageJudge`.
    """
    name = (getattr(settings, "document_router", "") or "").strip()
    if name in ("", NO_ROUTER):
        return None
    key = _judge_key(settings, name)
    with _checks_lock:
        if key in _judges:
            return _judges[key]
    judge = build_page_judge(settings, router_name=name)
    with _checks_lock:
        return _judges.setdefault(key, judge)


PROJECTOR_PASSED = "Projector smoke test passed."
PROJECTOR_FAILED = "Projector smoke test failed: the model did not read the page image."
PROJECTOR_NOT_CHECKED = "Projector not checked."


def test_decision_model(
    settings: Any, name: str, *, transport: httpx.BaseTransport | None = None
) -> dict[str, Any]:
    """Run the checks of decision model entry *name* again (the Test button, design D6).

    Test forgets the cached result of the entry first, so the routers that use
    it see the new result too. The probe holds no page content, so a hosted
    entry is tested without a router's opt-in.

    Args:
        settings: Anything with ``decision_models``.
        name: The entry name.
        transport: An ``httpx`` transport for every request (tests).

    Returns:
        ``status`` (``ok`` or the fixed reason), ``quantisation`` (text),
        ``projector`` (text, ``None`` for a text entry) and ``build`` (text,
        ``None`` when no build is checked).
    """
    entry = (getattr(settings, "decision_models", None) or {}).get(name)
    images = bool(_field(entry, "images", False)) if entry is not None else False
    with _checks_lock:
        for flag in (False, True):
            _checks.pop(_fingerprint(entry, flag), None)
    recipe = {"question": PROBE_QUESTION, "threshold": 0.0, "images": images}
    runtime = _runtime_of(settings, name, entry)
    judge = _make_judge(name, recipe, entry, transport, opt_in=True, runtime=runtime)
    result = judge._check()
    projector = None
    if images:
        projector = PROJECTOR_NOT_CHECKED
        if result.status is None:
            projector = PROJECTOR_PASSED
        elif result.status == checks.PROJECTOR_NOT_LOADED:
            projector = PROJECTOR_FAILED
    return {
        "status": result.status or "ok",
        "quantisation": result.quantisation,
        "projector": projector,
        "build": _build_line(runtime),
    }


def _build_line(runtime: Any) -> str | None:
    from .compose_runtimes import decision_build_line

    return decision_build_line(runtime)


# The name starts with "test"; this keeps pytest from collecting it where it is imported.
test_decision_model.__test__ = False  # type: ignore[attr-defined]
