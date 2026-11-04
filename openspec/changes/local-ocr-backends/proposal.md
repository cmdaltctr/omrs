# Proposal: a local OCR backend seam, and an experiment on the backends that could use it

## Why

The local OCR tier has one recogniser: PP-OCRv6 Small, inside pdf-inspector. pdf-inspector 1.17.0 pins that model set and has no option to change it. The model covers Chinese, Japanese, English and 46 Latin-script languages. It has no recogniser for Arabic, Bengali or Devanagari. Experiments 33 and 45 measured recall 0.000 on all 129 such pages (`io01`, `io02`, `io03`, `io07`). The confidence cut sends all of them to the OCR engine (local confidence 0.454 to 0.805), so no text is lost. The cost is time: the engine takes a median 37.0 s per page (Experiment 37) and the local tier takes about a second.

Candidate local backends exist that cover these scripts and need no PyTorch. A short research pass on 2026-11-04 found Indra OCR 1.1.2 and Apple Vision (macOS only, no Bengali). The operator kept these two for the experiment (RapidOCR and Tesseract were considered and dropped on 2026-11-04). Neither is measured on OMRS pages. Two facts block a direct switch:

1. The 0.9 confidence cut was calibrated on PP-OCRv6 Small only (Experiments 33, 37, 39). Another backend reports confidence on another scale, so it needs its own cut.
2. There is no place in the code to put a second backend. `page_routing.local_ocr` calls pdf-inspector directly.

This change adds the place (one small registry) and an experiment that measures the candidates before any of them ships.

## What Changes

- **New setting `ocr_local_backend`** (env `OCR_LOCAL_BACKEND`, flat like the other OCR keys). Default `pp-ocrv6-small`, the pdf-inspector path in use today. Only that value is accepted in this change. Behaviour, escalation reasons, index identity and digests stay the same for every current user.
- **A local OCR backend registry** in `integrations/pdf/`, copied from the PDF reader registry pattern: one file per backend and one `register()` line. A backend reads a PDF's pages and returns, for each page, the text, one page confidence and the model identity. The shared escalation rule (missing page, empty text, low confidence, hosted recommendation, and the non-Latin post-check) stays in `page_routing.local_ocr`. No backend carries its own escalation rule.
- **The confidence cut belongs to the backend.** A backend registers a calibrated cut, or none. `ocr_local_min_confidence` becomes optional: unset, it resolves to the backend's cut (0.9 for `pp-ocrv6-small`); set, it overrides. A backend with no calibrated cut is not accepted as a value of `ocr_local_backend`.
- **Identity.** The local tier block names the backend when it is not the default, and keeps the resolved model identity and the resolved cut. The default digest does not change.
- **Only the PP-OCRv6 backend ships.** The candidate backends are not built here. The experiment runs them from its own folder, in scratch environments outside the repository. A follow-up change adds a backend only if the experiment supports it. This keeps new dependencies, licence questions and per-backend calibration out of `src/` until there is a measured reason.
- **Experiment 46** measures two candidates (Indra OCR and Apple Vision) against the stored PP-OCRv6 output on the 129 non-Latin pages and a stratified Latin sample of 100 pages. It fixes the decision rule before any run.
- **Not in this change:** Settings and Studio rows (one accepted value gives nothing to choose; a follow-up adds them with the first second backend), a pre-OCR script chooser, any new dependency, any model download.

## Capabilities

### New Capabilities

- `local-ocr-backends`: the registry, the backend contract, the per-backend confidence cut, the setting and the identity block.

### Modified Capabilities

- `pdf-reader`: the requirement that sets the local tier's escalation cut. The default 0.9 becomes the default of the default backend, and an operator value still replaces it.

## Impact

- **New code:** `integrations/pdf/local_ocr_registry.py` (registry, helper for the effective cut) and `integrations/pdf/local_ocr_pp_ocrv6.py` (the pdf-inspector call and the identity probe, moved out of `page_routing.py`).
- **Changed code:** `integrations/pdf/page_routing.py` (`local_ocr` and `resolve_local_model_identity` dispatch through the registry; the file shrinks from 480 lines), `core/ingestion/ocr_identity.py` (resolved cut and backend name), `config/__init__.py`, `config/rules.py` and `core/settings.py` (the new key; `ocr_local_min_confidence` becomes optional), `compose_settings.py` (pass the new key).
- **Not touched:** `ocr_routing.py` (the two call sites keep calling `local_ocr`), the OCR engine routes, the maths and non-Latin routing modules, Settings and Studio.
- **Tests:** `tests/unit/test_local_ocr_tier.py`, `tests/test_ocr_identity_reingestion.py`, `tests/unit/test_effective_settings.py`, `tests/unit/test_settings_file_editable_keys.py`, plus new registry tests. The clean-base tripwire pin changes by test IDs.
- **Docs:** `docs/guides/configuration.md` and `docs/guides/ingestion.md` (the cut is per backend), the architecture integration inventory.
- **Experiment:** a new folder `experiments/46-local-ocr-backends-2026-11-04/` (planned in this change; its run needs operator approval for downloads and, for Indra, a licence read).
- **Risk to current users:** none by design. The default value, the default cut and the default digest are pinned by tests.
