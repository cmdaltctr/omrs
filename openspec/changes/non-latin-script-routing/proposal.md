# Proposal: route non-Latin pages straight to the OCR engine

## Why

The local OCR tier (PP-OCRv6 Small) has no recogniser for Arabic, Bengali or Devanagari: Experiment 33 measured recall 0.000 on all 129 such pages (`io01`, `io02`, `io03`, `io07`). dots.mocr reads them well (Experiment 37: median recall 0.873 to 0.985). Under page routing these pages first waste a local pass. They reach the engine only because their confidence falls below the 0.9 cut. The operator wants a setting that sends them straight to the engine.

## What Changes

- **New setting `ocr_non_latin_routing`** (env `OCR_NON_LATIN_ROUTING`, flat like the other OCR keys). Values:
  - `off` (default): today's behaviour.
  - `detect`: a flagged page whose available text is mostly non-Latin letters skips the local tier. A local OCR result that is mostly non-Latin letters escalates whatever its confidence.
  - `always`: every flagged page skips the local tier. This is for a collection the operator knows is non-Latin.
- **What it can detect, stated plainly.** A read-only probe on 2026-11-02 found that all four Experiment 33 non-Latin PDFs are pure scans: every page is flagged `scanned`, the page Markdown is empty, there are no fonts, and the only text items are Latin (7 letters a page on three of them, more on `io01`), which look like stamp or catalogue text. So no cheap signal exists before OCR for these pages. `detect` can act only where text exists: a text layer on the flagged page, or the local OCR output. For scans, `always` is the only way to skip the local tier.
- **Page unit only.** Under the `document` unit the whole PDF already goes to the engine, so the setting changes nothing there.
- **Maths and confidence.** A page that is both a maths page and a non-Latin page goes direct once. The `ocr_local_min_confidence` cut still applies to every page that the local tier reads.
- **Degradation.** When no OCR engine is available before dispatch, the pages run through the local tier as today, so no text is lost.
- **Studio and Settings.** The Read document step and Settings › Document reading show the setting.
- **Default stays `off`.** Experiment 33 shows the 0.9 cut already escalates all 129 measured non-Latin pages. A new experiment on the Experiment 33 and 37 pages measures the setting before any default changes.

## Capabilities

### New Capabilities

- `script-page-routing`: detection of non-Latin pages from available text, the routing of those pages under the page unit, and its identity and diagnostics.

### Modified Capabilities

- `pipeline-graphs`: the Read document step accepts `ocr_non_latin_routing`, and the step identity records it.
- `workspace-settings`: Document reading shows the setting; the row list names the keys in force after change A.
- `settings-file`: the page may write `ocr_non_latin_routing`.

## Impact

- **Settings:** `config/__init__.py` (field and accepted values), `config/rules.py` (`DOCUMENT_READING_KEYS`, `ACCEPTED`), `core/settings.py`.
- **Routing:** a new `integrations/pdf/script_routing.py` beside `maths_routing.py`; small changes in `integrations/pdf/ocr_routing.py` (`_page_unit_documents`) and `page_routing.py` (escalation reason). `ocr_routing.py` sits at 500 lines, so new logic goes in the new module.
- **Identity:** `core/ingestion/ocr_identity.py` and `source_state.py` add a block only under the page unit with a mode other than `off`.
- **Metadata:** a `pages_non_latin` count in the central embedding exclusion set.
- **HTTP contract and front end:** document-reading key enum in `openapi.yaml`, `web/src/settings/documentReadingWords.ts`, the Studio read-step form.
- **Docs:** `docs/guides/configuration.md` ("OCR routing unit and the local OCR tier"), `docs/guides/pipelines.md`, the architecture integration inventory.
- **Experiment:** a new numbered experiment folder that reads stored Experiment 33 and 37 outputs. No model run is needed for its core questions.
- **Order with change A:** `ordered-reader-and-ocr-lists` merged first (PR #166). The deltas are rebased onto its specs. Direct pages go to the ordered `ocr_engines` list; this change adds no single-value engine key.
