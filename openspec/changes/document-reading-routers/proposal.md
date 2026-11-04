# Proposal: decision models and named document-reading routers

## Why

Page routing sends the pages that the PDF scan flags to OCR. Some pages are not flagged and still carry junk text, for example handwritten scans such as `rf06` with a bad hidden text layer (issue #161). Nothing checks those pages. Experiment 43 showed that an image-based yes/no question to a decision model catches that junk. OMRS needs a way to ask that question per page, with a model and a privacy rule the operator chooses.

This change was first planned before `page-routing-default` (page is now the only routing unit) and before `local-ocr-backends` (ADR-112: page rules are registered parts). It is replanned for that code. See design.md, Context.

## What Changes

- **New provider kind: decision model.** Settings › Providers gets a Decision models card. Each entry has a name, a kind (`llamacpp`, `typesafe`, `cloudflare` or `ollama`; the last two are set up in this change but not yet checked on a live server, so Settings labels them "Not yet tested"), an address, a model name, an "accepts images" flag and, for hosted kinds, a key reference (`env://`, `file://` or `keychain://`, never a literal key). A local llama.cpp entry can be external or managed by OMRS (ADR-109), with the model file and the vision projector (`mmproj`) file declared separately.
- **Model checks before use.** A local decision model must be 8-bit or higher (gotcha 16: Q8_0, F16, BF16, F32; Q4_K_M is refused). An image entry must have its projector loaded, proven by a smoke test: the same page image with the right text and with wrong text must give answers that differ in the expected direction (as in Experiment 43). A managed runtime checks its llama.cpp build.
- **Named routers under Settings › Document reading › Router.** A router is a recipe: name, decision model, question, threshold on P(yes), whether it sees the page image, and the page character limit. "Yes" keeps the page text. "No" sends that page to OCR. The operator can create several routers. The host default, Studio's Read document step and user profiles pick one by name. No router is selected by default.
- **A router is a page rule at order 40.** It is one module, one descriptor entry and one `register()` line (ADR-112). It judges the pages that the scan did not flag and that have native text. A rejected page joins the pages that page routing already reads: local tier first, then the OCR engine list. The hook gains one field for this: a rule can add pages to the route (`RuleOutcome.add`). Flagged pages, the blank, maths and non-Latin rules and every digest stay as they are when no router is selected.
- **Privacy.** A router whose decision model is hosted sends page text, and page images when it sees images, to a third party. It runs only after the operator ticks an explicit "send pages off this machine" opt-in on that router. Settings shows a warning on every hosted router. Hosted image input is labelled experimental, because TypeSafe says image input is not production-ready. Local is the default.
- **Degradation.** A router that cannot run (model unreachable, check failed, opt-in missing) leaves the pages as today and records why. No file fails because of a router.
- **Confirmation experiment.** A new experiment on new documents, with the threshold frozen from Experiment 43 and a stricter page-based pass rule fixed before scoring, runs before anyone proposes a router as a default.
- **ADR-110 (Proposed)** records the provider kind and the router concept. It is updated to match the page-rule form.

## Capabilities

### New Capabilities

- `decision-model-providers`: decision model entries, kinds, key references, hosted detection and model checks.
- `document-routers`: router recipes, the page rule, per-page actions, privacy opt-in, degradation, identity and diagnostics.

### Modified Capabilities

- `page-routing-rules`: a rule may add pages to the route; the built-in order gains `document_router` (40); a rule receives the judge.
- `reading-parts`: the page rule descriptor declares `adds_pages`.
- `pdf-reader`: a page that a page rule adds goes through the local tier and the engine list; the scalar diagnostics keep their meaning with added pages.
- `llamacpp-runtimes`: a managed runtime role for a local decision model, with model and projector files.
- `settings-file`: `omrs.jsonc` holds the decision model and router maps.
- `pipeline-graphs`: the Read document step picks a router by name.
- `workspace-settings`: the Decision models card and the Router section with its warnings.
- `rescue-quality-evaluation`: the confirmation experiment on new documents.

## Impact

- **New code:** `core/providers/decision/` (registry plus one file per kind), `integrations/pdf/page_rules/document_router.py` (the rule), `integrations/pdf/page_images/` (page renderers behind `PartRegistry`), `compose_decision.py` (builds the judge and resolves key references).
- **Changed code:** `integrations/pdf/page_rules/{base,pipeline,registry}.py` (`add`, `judge`, `adds_pages`), `integrations/pdf/ocr_routing.py` (reads `plan.added`; stays under 500 lines), `core/reading_parts.py` (descriptor), `integrations/llamacpp_runtime/spec.py` (role `decision`), `compose_runtimes.py`, `config/` (maps, `document_router`), `core/ingestion/ocr_identity.py`, `reader_identity.py`, `embed_exclusions.py`, `graph_adapters_catalogue.py`, `core/ingestion/backends/local.py` and `integrations/pdf/factory.py` (judge seam).
- **HTTP contract:** new routes for decision models and routers (list, save, test), new `openapi.yaml` schemas and `FAMILIES` entries.
- **Front end:** a Decision models card in Providers and a Router section in Document reading.
- **Dependencies:** none new in the base install. Image routers render pages with LiteParse (always installed) or pypdfium2 (optional `pdf-pypdfium2` extra, when installed).
- **Cloud:** opt-in only, per router. Keys by reference only (gotcha 18).
- **Docs:** ADR-110, `docs/adr/ADR_README.md`, `docs/guides/reading-parts.md`, `docs/guides/configuration.md`, `docs/guides/providers.md`, `docs/guides/pipelines.md`, `docs/guides/web-workspace.md`, TDR-024 note.
