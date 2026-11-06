# Proposal: one confidence cut per local OCR backend

## Why

Each local OCR backend has its own confidence scale, but the operator can only set one number, `ocr_local_min_confidence`, and it replaces the cut of every listed backend. Indra also carries a hardcoded script filter (Arabic and Devanagari only), so a confident Indra read of a Latin or Bengali page is thrown away. A read-only re-analysis of Experiment 46's saved results (2026-11-06, 229 pages) shows that confidence alone is enough when each backend has its own cut: PP-OCRv6 small at 0.92 then Indra at 0.94 keeps 108 pages local with 2 bad (1.9%), against 56 pages for PP-OCRv6 alone at today's 0.90. The operator decided on 2026-11-06 to make the cuts per backend, editable in the web Settings page and per pipeline in Studio, with no shortcuts.

## What Changes

- **New map setting `ocr_local_cuts`.** It holds one cut per backend name, for example `{"pp-ocrv6-small": 0.92}`. Environment form: `OCR_LOCAL_CUTS` as a JSON object, like `READING_PART_OPTIONS`. Each value is from 0 to 1. A backend with no entry uses its descriptor default.
- **New defaults from evidence.** PP-OCRv6 small 0.92 and Indra 0.94. The descriptor in `core/reading_parts.py` holds each default and the experiment that measured it. The integration `register()` line keeps its pinned copy (ADR-112 decision 1), and the pin test fails when the two differ. No other file holds a cut value.
- **BREAKING: `ocr_local_min_confidence` is retired.** `OCR_LOCAL_MIN_CONFIDENCE` in the environment or `.env` stops start-up with a message that names `OCR_LOCAL_CUTS`. In `omrs.jsonc` the key is ignored and listed as retired with the replacement `ocr_local_cuts`. The server still starts. A save of the cuts on the Settings page removes the old key from the file.
- **Indra's script filter is removed.** Confidence alone decides for every backend. The descriptor field `keeps_scripts`, the reason `script_not_kept`, the output-script classifier and its version go, because nothing else uses them. Under `ocr_non_latin_routing=detect`, the `non_latin_output` post-check now applies to every backend the same way, with no Indra exemption (operator decision, 2026-11-06). The guides say: set `ocr_non_latin_routing` to `off` when Indra is listed.
- **Settings page.** Settings › Document reading › Local OCR › "Local OCR backends": each backend row gets a "Confidence cut" number input. An empty input shows the backend's default and means "use the default". The save goes through the existing Document reading write path (allowed keys, revision check, atomic replace, comments kept).
- **Studio.** The Read document step gets an optional `ocr_local_cuts` option, validated by the same rule. Studio shows a cut box beside each backend of the step's list, with the inherited cut shown when the box is empty. A step entry replaces the host cut of its backend for that pipeline only. A graph-wide override stays host-owned.
- **HTTP API.** `openapi.yaml` and the Document reading routes accept and return `ocr_local_cuts`, and each backend option carries its default cut. The Integrations reading-parts health row reports the effective cut from the map or the default.
- **The cuts move to the PDF identity.** The local OCR cuts (and the local model identity) leave the OCR routing block that every source carries and enter the PDF-only `parser` block, for every list. After the upgrade, a cut change from Settings, the environment, `omrs.jsonc` or a Studio step re-indexes PDF sources only. Markdown and code sources keep their digest.
- **One re-index, accepted.** The payload change moves every source digest once. The identity schema advances from 7 to 8.
- **Traceable defaults.** A small committed analysis, `experiments/46a-local-ocr-per-backend-cuts-2026-11-06`, reproduces the numbers from Experiment 46's saved results. The descriptors cite it.
- **ADR.** A new ADR records the per-backend cut map, the Studio step option, the script-filter removal and the move of the cuts to the PDF identity. It amends ADR-112 decision 4 with a dated note in ADR-112.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `local-ocr-backends`: the cut comes from `ocr_local_cuts` or the descriptor default; the single override and the script filter are removed; new defaults 0.92 and 0.94; the cuts and the local model move to the PDF identity and lose the kept scripts.
- `pdf-reader`: the local tier escalation requirement names the per-backend cut and the new default; the escalation reasons lose `script_not_kept`.
- `script-page-routing`: the `detect` post-check applies to every backend; no backend is exempt by script.
- `reading-parts`: a discovered descriptor that still passes kept scripts loads as broken; health shows the effective cut from the map or the default.
- `settings-file`: a retired `ocr_local_min_confidence` in `omrs.jsonc` is listed with its replacement and ignored.
- `workspace-settings`: Document reading shows and saves a cut for each listed backend, and offers to remove the retired key.
- `pipeline-graphs`: the Read document step accepts `ocr_local_cuts`; step cuts enter the PDF identity only; Studio shows a cut box per backend of the step.

## Impact

- Code: `core/reading_parts.py` (defaults, `calibrated_by`, `effective_cut`, no `keeps_scripts`), `config/__init__.py` and `config/reading_lists.py` (new field, validation), `config/legacy.py` and `config/settings_file.py` (retirement), `core/settings.py` and `compose_settings.py` (resolved cuts), `config/rules.py` (write rule), `integrations/pdf/local_ocr/{chain,registry}.py`, `integrations/part_registry.py`, `integrations/pdf/script_routing.py`, `core/ingestion/ocr_identity.py`, `core/ingestion/source_state.py` (schema 8), `transports/api/{document_reading,reading_parts_health}.py`, `transports/api/openapi.yaml`, `core/ingestion/{graph_adapters_catalogue,graph_adapters_values,graph_fingerprint}.py`, `core/pipelines/levers.py`, `web/src/settings/`, `web/src/studio/` and `web/src/api/settingsDocumentReading.ts`, `.env.example`.
- Operators: an `OCR_LOCAL_MIN_CONFIDENCE` value in the environment or `.env` stops start-up until it is removed. Every collection (all source types) re-indexes once on the next ingest after the upgrade, because the identity payload changes. After that, a cut change re-indexes PDF sources only. Operators who list Indra must set `ocr_non_latin_routing` to `off`; under `detect`, Indra's non-Latin pages go to the OCR engine.
- Saved Studio graphs keep their fingerprint. A step that sets cuts changes the PDF identity of that pipeline only.
- External parts: a discovered descriptor that passes `keeps_scripts` fails to load and shows as broken. The reading-parts guide states the field change.
- Evidence: Experiment 46 saved results, re-analysed in `46a`. Limits: 229 pages from 9 documents, reference text from a vision model, and the 0.90 against 0.92 difference is one page. This is a setting choice, not a publication result.
- Live app: the rollout after merge is an operator step (tasks group 10). This change touches no live state.
