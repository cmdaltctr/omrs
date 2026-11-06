# Proposal: one Page routing panel in Settings and Studio

## Why

The settings that decide where a PDF page goes are spread over four blocks of Settings › Document reading ("When to use OCR", "Maths pages", "Local OCR", "Engines") plus a separate Router card, and the Studio Read document step lists the same options in schema order. Nobody can see the real page flow from these screens, so an operator cannot tell which setting acts first or which one sends a page to OCR. The blank-page drop is also always on, so the operator cannot turn it off for a collection where the blank test is wrong. The operator approved one panel laid out as the page flow on 2026-11-06.

## Dependency

This change builds on the planned change `local-ocr-per-backend-cuts` (artifacts in the sibling worktree `omrs-feat-local-ocr-per-backend-cuts`). That change adds the `ocr_local_cuts` map, the per-backend cut boxes (`LocalBackendCutInput` in Settings, `CutsParam` in Studio) and the defaults 0.92 and 0.94. This change places those boxes in the panel and does not redefine them. **Apply starts only after `local-ocr-per-backend-cuts` is merged into `v3`.** Task 0 rebases this branch on that `v3`.

## What Changes

- **One "Page routing" panel** replaces the OCR card blocks "When to use OCR", "Maths pages", "Local OCR" and "Engines", the PDF reading card, and the host router row of the Router card. The panel shows the page flow top to bottom:
  1. **PDF readers**: the ordered `pdf_readers` list. The optional reader `pypdfium2` shows in the add menu, marked optional. When it is not installed, step 1 shows an "Install" button that starts the existing extra install job for `pdf-pypdfium2`. Studio shows the reader disabled, with a link to Settings.
  2. **Pages with no usable text**: switches for Skip blank pages (new), Maths pages (`ocr_maths_routing_enabled`) and a choice for Non-Latin pages (`ocr_non_latin_routing`, `off` labelled as the default).
  3. **Pages that look fine**: the router picker (`document_router`: no router or a named router), with a link to the Router section where routers are defined.
  4. **Local OCR backends**: the ordered `ocr_local_backends` list with the per-backend cut boxes of `local-ocr-per-backend-cuts`.
  5. **OCR engines**: the ordered `ocr_engines` list, with the OCR engines folder line under it.
- **Lists where order matters, switches where it does not.** The three page rules (blank, maths, non-Latin) are not reorderable. The panel says that they run in a fixed order.
- **`ocr_fallback_enabled` and `ocr_routing_unit`** move to the top of the panel, above step 1, because they decide whether the flow runs at all. The Router card keeps the named routers and loses only the host choice row.
- **Each row** keeps a short plain help line and its source (default, `omrs.jsonc`, or locked by the environment), as rows do today.
- **Studio** reuses the same panel layout in the Read document step, with "Inherit" states. In Studio, the inherited value is the Settings value; the panel says so.
- **New setting `ocr_skip_blank_pages`** (environment `OCR_SKIP_BLANK_PAGES`), default `true`. It is a `SettingField` on the `blank` page rule descriptor. Off, the blank rule drops no page and runs no blank test. It is writable from Settings › Document reading and settable on a Read document step. **BREAKING (spec only):** the requirement "The blank test has no setting" is removed. Behaviour for every current install is unchanged, because the default keeps today's drop.
- **Identity.** Off, the switch adds `skip_blank_pages: false` to the PDF-only `parser` block. On (the default) it adds nothing, so no digest moves and the identity schema stays as `local-ocr-per-backend-cuts` leaves it. A step value reaches the identity the same way and stays out of the graph fingerprint.
- **HTTP API.** `openapi.yaml` and the Document reading routes gain `ocr_skip_blank_pages` in the key enums. No new route.
- **Docs.** A new user guide `docs/guides/page-routing.md` explains the whole flow with a plain ASCII diagram, each step and setting, the defaults, where `pypdfium2` sits, how Settings and Studio values interact, when documents re-index, and the evidence (Experiments 33, 43, 46, 46a, 47). The guides index in `README.md`, `configuration.md`, `ingestion.md`, `reading-parts.md` point to it. The panel has no "Learn more" link and no guide address constant.
- **ADR.** A new ADR (ADR-116 expected, confirmed at apply time; design D11) records the skip-blank switch and why the page rules keep a fixed order. It amends ADR-112 decision 3 with a dated one-line note. It is a task in this change, written at apply time.

## Capabilities

### New Capabilities

- `page-routing-panel`: the one panel that shows the page flow in five steps, in Settings › Document reading and in the Studio Read document step: step order, lists against switches, fixed rule order, help and source per row, inherit states in Studio (the panel has no guide link), the pypdfium2 install button, and desktop and phone widths.

### Modified Capabilities

- `workspace-settings`: Document reading shows its rows inside the Page routing panel; non-Latin routing and the host router move into panel steps; the Router section keeps the router definitions; the new Skip blank pages row; the reader list offers an Install button for a reader that is not installed; the routes carry the new key.
- `settings-file`: the page may write `ocr_skip_blank_pages`.
- `pdf-reader`: the blank test gets one on/off switch; blank pages skip both OCR tiers only while it is on; the switch joins the PDF identity when off.
- `page-routing-rules`: the built-in rules keep a fixed order that no setting changes; the blank rule's identity shape gains the PDF-only switch entry.
- `pipeline-graphs`: the Read document step accepts `ocr_skip_blank_pages`; a step value enters the PDF identity only.

## Impact

- Backend (small): `core/reading_parts.py` (blank `SettingField`), `config/ocr_routes.py`, `core/settings.py`, `compose_settings.py`, `config/rules.py` (`_READING_BOOLEANS`), `integrations/pdf/page_rules/blank.py`, `core/ingestion/ocr_identity.py` and `reader_identity.py` (PDF `parser` entry), `core/ingestion/graph_adapters_catalogue.py` (`ReadParams`, the `READ` option map), `core/ingestion/graph_fingerprint.py` (`_UNHASHED_OPTIONS`), `transports/api/openapi.yaml`, `.env.example`. `READ_OCR_KEYS`, `_READ_STEP_OCR_KEYS`, `PAGE_RULE_KEYS` and `DOCUMENT_READING_KEYS` derive from the descriptor and need no hand edit.
- Front end (most of the work): a new `web/src/pageRouting/` folder (panel layout and words), `web/src/settings/DocumentReadingSection.tsx`, `DocumentRoutersCard.tsx`, `documentReadingWords.ts`, `web/src/api/settingsDocumentReading.ts`, and the Studio Read document step (`StepSettingsFields.tsx`, `ListParam.tsx`, `ParamField.tsx`). Existing tests that find rows by the old block titles change.
- Docs: new `docs/guides/page-routing.md`; links and short edits in `README.md`, `configuration.md`, `ingestion.md`, `reading-parts.md`, `pipelines.md`; the new ADR (`docs/adr/`, with a row in `docs/adr/ADR_README.md`) and a dated note in ADR-112.
- Operators: no setting changes value; no index re-reads on upgrade. Turning Skip blank pages off re-indexes PDF sources only, on the next explicit ingest after a restart (Settings) or on the next run (Studio step).
- Live app: nothing to roll out beyond the normal reinstall after merge.
