# Design: a local OCR backend seam

## Context

See proposal.md for the why.

**Observed in the code (branch `feat/local-ocr-backends`, forked from `v3` at `4f6dac05`):**

- `integrations/pdf/page_routing.py` (480 lines) holds `local_ocr(file, pages, *, settings, script_check)`. It calls `pdf_inspector.process_pdf_with_ocr(..., mode="force", page_numbers=..., model_directory=..., offline=...)`, reads `markdown`, `provenance.ocr_confidence`, `provenance.ocr_model` and `provenance.hosted_recommended` for each page, and applies the escalation rule in one loop: `missing_page`, `empty_text`, `low_confidence`, `hosted_recommended`, and `non_latin_output` under `ocr_non_latin_routing=detect`.
- The same file holds the identity probe, `resolve_local_model_identity`. The probe OCRs one generated blank page, because pdf-inspector reports the model only in per-page provenance. A successful result is cached per `(ocr_local_model_directory, ocr_local_offline)`. A failure is not cached. A runtime panic switches the local tier off for the process (`switch_local_tier_off`).
- `integrations/pdf/ocr_routing.py` (463 lines) calls `local_ocr` at two places: the main split and the no-engine degradation path. It needs no change.
- `core/ingestion/ocr_identity.py` builds `local_tier = {"min_confidence": settings.ocr_local_min_confidence}` and adds `model` when the probe resolves.
- `ocr_local_min_confidence` is `float`, default 0.9, in `config/__init__.py` and `core/settings.py`. It is passed through `compose_settings.py`.
- `integrations/pdf/registry.py` is the pattern to copy: a name to import-path map, lazy `importlib`, declared metadata, no module-level import of any adapter.
- pdf-inspector 1.17.0 accepts no recogniser or language option (research report, 2026-11-04). The 0.9 cut comes from Experiment 39 and the archived change `raise-local-ocr-min-confidence-to-0-9`.
- Repo rules that bind this design: ONNX Runtime only in the base install; a new core dependency needs operator approval; registries dispatch, with no `if`/`elif` over names and no module-level import of a concrete strategy; settings are injected; no file over 500 lines; index identity must name what changes the text.

**Observed in the data (Experiments 33, 37, 45):** PP-OCRv6 Small reads 129 pages in Arabic, Bengali and Devanagari at recall 0.000, with local confidence from 0.454 to 0.805. Detection before OCR gives no verdict on scans (Experiment 45). So a backend cannot be chosen per page by script today. Any backend that serves non-Latin pages must also read Latin pages at least as well as PP-OCRv6, or a script chooser must exist first.

## Goals / Non-Goals

**Goals:**

- One place where a second local backend plugs in, proven by a fake backend in tests.
- A rule for how a backend gets its confidence cut, and a rule that blocks a backend with no measured cut.
- Current users see no change: same behaviour, same cut, same digest.
- An experiment that tests the candidates with a decision rule fixed before any run.

**Non-Goals:**

- No candidate backend in `src/` (Indra, Apple Vision). No new dependency, extra or download.
- No script chooser and no per-script backend selection.
- No Settings page row, Studio field or HTTP contract change.
- No change to the escalation reasons or to the engine routes.

## Decisions

### D1. A sibling registry, copied from the PDF reader registry

New module `integrations/pdf/local_ocr_registry.py`. It holds `register(name, import_path, *, min_confidence, calibrated_by)`, `describe(name)`, `get(name)` and `available()`. `get` imports the backend lazily. The module imports no backend at module level. The registration line for `pp-ocrv6-small` sits at the bottom of the file, like the readers in `registry.py`.

Alternative: add the backend to `pdf/registry.py`. Rejected: that registry maps a `PDF_READER` value to a reader class with `load_data`. A local OCR backend has another contract and another lifecycle.

Alternative: a plain function map in `page_routing.py`. Rejected: that file is near the 500-line ceiling and the invariant says a new strategy is one file and one `register()` line.

### D2. The contract is small and pure

```python
class LocalOcrBackend(Protocol):
    def read_pages(self, file: Path, pages: list[int], *, settings: Any) -> list[BackendPage]: ...
    def identity(self, settings: Any) -> str | None: ...


@dataclass(frozen=True)
class BackendPage:
    page: int  # 1-based
    text: str  # Markdown or plain text
    confidence: float | None  # one number in [0, 1], or None
    model: str | None  # "name@revision"
    hosted_recommended: bool = False
```

`read_pages` raises on a runtime failure, as `local_ocr` does today, and the caller keeps its current handling (the page goes to the worker, and a non-`Exception` panic switches the tier off). A page the backend skips is simply absent from the list. `identity` returns the model identity without reading a user page, or `None`.

The names are proposals. `hosted_recommended` keeps today's reason name so the reason strings and the tests stay the same.

### D3. The shared rule stays in `local_ocr`

`local_ocr` keeps its signature and its escalation loop. The only change inside it is the call: it resolves the backend from `settings.ocr_local_backend`, calls `read_pages`, and feeds the `BackendPage` list into the same loop. The loop reads `.text`, `.confidence`, `.model` and `.hosted_recommended` where it read provenance fields. The two call sites in `ocr_routing.py` are untouched.

`resolve_local_model_identity` keeps its lock, its success-only cache and its panic handling. It calls `backend.identity(settings)` and adds the backend name to the cache key: `(backend, model_directory, offline)`.

### D4. The pdf-inspector call moves to its own module

`integrations/pdf/local_ocr_pp_ocrv6.py` holds a class with `read_pages` (the `process_pdf_with_ocr` call and the provenance reads) and `identity` (the blank-page probe and `_model_identity`). The move removes about 70 lines from `page_routing.py`, which ends near 420 lines. Test patch targets follow the function (AGENTS gotcha 8b): tests that patch `page_routing._probe_local_model_identity` or `pdf_inspector.process_pdf_with_ocr` must patch the new location. The task list names the tests to check.

### D5. The page confidence rule for line-based backends

Every candidate except pdf-inspector reports a confidence per line or per word. The contract needs one number per page. The fixed rule is the mean of line confidences weighted by character count. It is the simplest rule that does not let one short noisy line, such as a page number, decide a page. Experiment 46 reports two alternatives as exploratory (the minimum over lines of at least 10 characters, and the share of characters on lines at or above 0.8). A different rule needs a recorded experiment and a spec change, because the rule changes the text a collection keeps.

### D6. The cut belongs to the backend

The 0.9 cut is a property of PP-OCRv6 Small and its confidence scale (Experiments 33, 37, 39). Another backend reports confidence on another scale. Reusing 0.9 would be a guess.

- `register(..., min_confidence=0.9, calibrated_by="39-local-tier-escalation-2026-09-30")` for `pp-ocrv6-small`.
- A backend may register `min_confidence=None`. Registration with a cut and no `calibrated_by` raises `ValueError`, like `registry.register` does for a missing `text_format`.
- `ocr_local_backend` accepts only registered backends with a cut. An uncalibrated backend can exist in the registry for an experiment or a test and cannot be selected. This enforces "a backend without a measured cut is not offered".
- `ocr_local_min_confidence` becomes `float | None`, default `None` (proposed; see Open Questions). A helper `effective_min_confidence(settings)` returns the set value, else the backend's cut. `local_ocr` and `ocr_identity` both call it, so the identity records the resolved cut. With the default backend and no operator value the result is 0.9, so the digest is unchanged.
- How a new backend gets its cut: an experiment picks the cut on held-out documents (Experiment 46 uses leave-one-document-out), the follow-up change registers it with the experiment folder name, and the experiment's report is the evidence.

Alternative: keep `ocr_local_min_confidence` at 0.9 and add the backend cut later. Rejected: a registry with a global cut is incoherent, and the later change would have to retype the setting under the first real backend. The retype touches five files and is the largest part of this change. The retype is an open operator decision (question 1); the registry still works with a global cut for one backend.

Alternative: a map `ocr_local_min_confidence_by_backend`. Rejected: more surface than one optional override.

### D7. Identity

`ocr_identity.ocr_routing_payload` builds `local_tier` as `{"min_confidence": <resolved cut>}`, plus `model` when the probe resolves, plus `backend: <name>` only when the backend is not `pp-ocrv6-small`. The default digest does not change, and the existing digest-pin tests prove it. The schema number does not advance, because no default payload changes. A test pins the default digest before the code change, as `non-latin-script-routing` did.

A backend swap or a cut change reindexes PDF sources once, as for any identity change.

### D8. Only PP-OCRv6 ships; the experiment holds the candidates

Option A: ship the seam and the PP-OCRv6 backend; run the candidates only inside the experiment folder; build a candidate adapter in a follow-up change if the experiment supports it.

Option B: ship the seam and experiment-only adapters in `src/` behind optional extras.

Proposed: A. Reasons:

1. B needs a decision on new optional dependencies, a licence read for Indra and a compatible-extras test (the `floors` job) before any measurement exists.
2. The experiment needs each arm in its own scratch environment anyway, because the arms have conflicting dependencies and must not touch the repository `.venv` or `uv.lock`.
3. An adapter written for the experiment would be rewritten for `src/` once the real contract and the real cut are known. The experiment runner uses the same `read_pages(file, pages) -> (page, text, confidence)` shape, so a follow-up can lift the code.

Cost of A: the contract is proven only by a fake backend in tests, not by a real second backend. The follow-up change must be ready to adjust the contract.

### D9. Experiment design in one paragraph

Experiment 46 reads stored evidence (Experiment 33 images, reference transcriptions and PP-OCRv6 outputs; Experiment 37 dots.mocr text) and runs two candidate arms (Indra OCR and Apple Vision) on 229 pages; Apple Vision is not run on the 60 Bengali pages, so a pass for it can cover only Arabic and Devanagari: 129 non-Latin and 100 Latin. It scores token recall, seconds per page and confidence calibration, with the cut chosen by leave-one-document-out. The decision rule has four gates (read quality per script, confidence, Latin non-regression, speed) and is fixed in `plan.json` before any run. See `experiments/46-local-ocr-backends-2026-11-04/protocol.md`.

## Risks / Trade-offs

- [The reference transcriptions are from a vision model, not a person] The Experiment 33 reference is Gemini 3.8 Flash (temperature 0), not a human transcript. It can be wrong on Arabic and Bengali, and a backend that reads better than the reference is scored down. The protocol reports recall against dots.mocr as a second view and offers an operator spot-check. The report states this limit.
- [The seam may sit unused] If the experiment finds no candidate that passes, `pp-ocrv6-small` stays the only backend. The seam costs one registry file and a move of existing code, and it has tests. Whether to merge the seam in that case is an open operator decision (question 2).
- [Retyping `ocr_local_min_confidence`] A `None` default may reach a place that assumed a float: the Settings page, the config template, the HTTP contract. Task 2.3 lists the places and a test for each.
- [Patch targets move] Tests that patch the pdf-inspector call or the probe in `page_routing` stop patching anything. The AGENTS gotcha 8b applies. Task 1.1 finds them first.
- [Confidence scales differ between backends] The cut is per backend and the registration requires an experiment name. Nothing stops a bad experiment, so the follow-up review reads the report.
- [Apple Vision is macOS only] It cannot run in CI and may use the Neural Engine. The experiment records this. A follow-up decides if it can ship as an optional backend.

## Migration Plan

No data migration. Existing indexes keep their digest. Rollback is a revert of the change; the setting has one accepted value.

## Operator Decisions (2026-11-04)

1. Retype of `ocr_local_min_confidence`: deferred to the follow-up change that adds the first second backend. Until then the global cut stays 0.9 and D6 does not apply.
2. Seam on FAIL: not merged. Only the Experiment 46 report merges, and the code part is descoped.
3. Latin margin: G3 stays at -0.02 (strata -0.05).
4. Order: Experiment 46 runs first. Code groups 1 to 3 and 5 start only after a PASS.
5. Indra licence: the operator reads the full text before the Indra arm runs.

Considered and dropped by the operator on 2026-11-04: RapidOCR and Tesseract as experiment arms.
