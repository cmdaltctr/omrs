# Proposal: decision models and named document-reading routers

## Why

When the rescue tiers return text for flagged pages, OMRS sets the flagged count to zero and never checks that text (TDR-024). So handwritten scans such as `rf06` keep junk text and stay out of OCR (issue #161). Experiment 43 showed that an image-based yes/no question to a decision model catches that junk. Under the old 10% document rule it also sent good documents to OCR. OMRS needs a way to ask that question per page, with a model and a privacy rule the operator chooses.

## What Changes

- **New provider kind: decision model.** Settings › Providers gets a Decision models card. Each entry has a name, a kind (`llamacpp` or `typesafe` in this change; `cloudflare` and `ollama` wait on Open Questions), an address, a model name, an "accepts images" flag and, for hosted kinds, a key reference (`env://`, `file://` or `keychain://`, never a literal key). A local llama.cpp entry can be external or managed by OMRS (ADR-109), with the model file and the vision projector (`mmproj`) file declared separately.
- **Model checks before use.** A local decision model must be 8-bit or higher (gotcha 16: Q8_0, F16, BF16, F32; Q4_K_M is refused). An image entry must have its projector loaded, proven by a smoke test: the same page image with the right text and with wrong text must give answers that differ in the expected direction (as in Experiment 43). A managed runtime checks its llama.cpp build.
- **Named routers under Settings › Document reading › Router.** A router is a recipe: name, decision model, question, threshold on P(yes), whether it sees the page image, which pages it judges (rescued pages only, or every page with native text), and the two actions. "Yes" keeps the page text. "No" sends that page to OCR. The operator can create several routers. The host default, Studio's Read document step and user profiles pick one by name. No router is selected by default.
- **Where a router runs.** After the rescue tiers return text, each rescued page is judged. This replaces the blind reset to zero of TDR-024 when a router is selected. A router can also judge pdf-inspector's own page text. A rejected page goes to OCR on its own: local tier first, then the OCR engine list. It never counts toward the 10% document rule, and one rejected page never sends the whole document to OCR (Experiment 42 lesson).
- **Privacy.** A router whose decision model is hosted sends page text, and page images when it sees images, to a third party. It runs only after the operator ticks an explicit "send pages off this machine" opt-in on that router. Settings shows a warning on every hosted router. Hosted image input is labelled experimental, because TypeSafe says image input is not production-ready. Local is the default.
- **Degradation.** A router that cannot run (model unreachable, check failed, opt-in missing) leaves the page as today and records why. No file fails because of a router.
- **Confirmation experiment.** A new experiment on new documents, with the threshold frozen from Experiment 43 and a stricter pass rule fixed before scoring, runs before anyone proposes a router as a default.
- **ADR-110 (Proposed)** records the provider kind and the router concept.
- **Open decision, not made here:** whether `OCR_ROUTING_UNIT=page` becomes the default and the 10% document rule goes. It waits on the page-mode re-test (see design.md).

## Capabilities

### New Capabilities

- `decision-model-providers`: decision model entries, kinds, key references, hosted detection and model checks.
- `document-routers`: router recipes, where they run, per-page actions, privacy opt-in, degradation, identity and diagnostics.

### Modified Capabilities

- `pdf-reader`: a rescue no longer zeroes the flagged count blindly when a router is selected.
- `llamacpp-runtimes`: a managed runtime role for a local decision model, with model and projector files.
- `settings-file`: `omrs.jsonc` holds the decision model and router maps.
- `pipeline-graphs`: the Read document step picks a router by name.
- `workspace-settings`: the Decision models card and the Router section with its warnings.
- `rescue-quality-evaluation`: the confirmation experiment on new documents.

## Impact

- **New code:** `core/providers/decision/` (registry plus one file per kind), `integrations/pdf/page_router.py` (runs a router on pages), a page-image renderer, `compose_decision.py` (builds clients and resolves key references).
- **Changed code:** `integrations/pdf/pdf_inspector.py` and `ocr_routing.py` (router hook; `ocr_routing.py` is at 500 lines, so logic goes in the new module), `integrations/llamacpp_runtime/spec.py` (role `decision`), `compose_runtimes.py`, `config/` (maps, `document_router`), `core/ingestion/ocr_identity.py`, `source_state.py`, `graph_adapters_catalogue.py`.
- **HTTP contract:** new routes for decision models and routers (list, save, test), new `openapi.yaml` schemas and `FAMILIES` entries.
- **Front end:** a Decision models card in Providers and a Router section in Document reading.
- **Dependencies:** none new in the base install. Image routers need a page renderer; see design Open Questions.
- **Cloud:** opt-in only, per router. Keys by reference only (gotcha 18).
- **Docs:** ADR-110, `docs/adr/ADR_README.md`, `docs/guides/configuration.md`, `docs/guides/providers.md`, `docs/guides/pipelines.md`, `docs/guides/web-workspace.md`, TDR-024 note.
