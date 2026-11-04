# ADR-110: Decision Models and Named Document-Reading Routers

- **Date:** 2026-11-02
- **Status:** Proposed (2026-11-02; draft written with the change, not accepted)
- **Deciders:** Maintainer
- **Amends:** [ADR-112](112-reading-parts-descriptor-pipeline-and-discovery.md) decision 3 (the page rule outcome gains `add`, and the descriptor gains `adds_pages`). Page routing (`page-routing-default`) already replaced the TDR-024 zero as the routing input; this ADR adds a note to TDR-024 saying so.
- **Related:** [ADR-066](066-tiered-reader-fallback-chain.md) (rescue tiers), [ADR-069](069-page-level-ocr-routing-and-the-pdfium-runtime.md) (page routing), [ADR-112](112-reading-parts-descriptor-pipeline-and-discovery.md) (a router is a page rule), [ADR-074](074-run-local-decision-models-through-llama-cpp-q8-0-gguf.md) (8-bit decision models), [ADR-087](087-settings-live-in-omrg-jsonc.md) (`omrs.jsonc`), [ADR-105](105-pipeline-steps-own-their-ocr-settings.md) (step OCR settings), [ADR-108](108-local-chat-and-classification-stay-apart.md) (classification address), [ADR-109](109-omrs-owns-local-model-runtimes-components-are-clients.md) (managed runtimes), root `AGENTS.md` gotchas 16 and 18
- **Change:** `openspec/changes/document-reading-routers/`

## Context

Page routing sends the pages that the PDF scan flags to OCR. A page that the scan does not flag keeps its native text, even when that text is junk. Handwritten scans such as `rf06` keep junk text and never reach OCR (issue #161). Text-only checks failed in Experiments 38 and 42. Experiment 43 asked a decision model, with the page image, whether the text matches the page. It caught most junk pages, but it was scored under the old 10% document rule, which also sent good documents to OCR. Its threshold was fitted on the same documents it was tested on.

This ADR was first written before `page-routing-default` and `local-ocr-backends`. It was revised on 2026-11-04 for page routing as the only unit and for page rules as registered parts (ADR-112).

OMRS has no provider for a model that answers yes/no questions about a page. Classification has one address and one model, and speaks chat completions.

## Decision

1. **A new provider kind: decision model.** Named entries in `omrs.jsonc` (`decision_models`), each with a kind, address, model, an image flag and, for hosted kinds, a key reference. Kinds come from a registry (`llamacpp` and `typesafe` first). All kinds send the same System One yes/no request and return P(yes).
2. **Local decision models run at 8-bit or higher.** Managed entries check the GGUF header before start; Q4_K_M and other sub-8-bit types are refused. Image entries must pass a right-text against wrong-text smoke test, which proves the vision projector is loaded. A managed entry declares its model and projector files separately and runs under ADR-109 as runtime `decision-<name>`.
3. **Named routers.** A router is a recipe in `omrs.jsonc` (`document_routers`): decision model, question, threshold, image flag, character limit. "Yes" keeps the page text; "no" sends that page to OCR. The host default (`document_router`), Studio's Read document step and user profiles pick a router by name. No router is selected by default.
4. **A router is a page rule at order 40.** It judges the pages that the scan did not flag and that have native text, one request at a time. A rejected page joins the route through a new `RuleOutcome.add` set and goes alone through the local tier and the OCR engine list. One rejected page never sends a whole document to OCR. With no router selected the rule does nothing, and every digest and output stays as before.
5. **Local by default, hosted by explicit opt-in.** A router on a hosted decision model runs only when its own "send pages off this machine" opt-in is on. Settings warns on every hosted router and labels hosted image input experimental.
6. **A router that cannot run changes nothing.** Reading falls back to the behaviour without a router, with a fixed reason in the diagnostics.
7. **Confirmation before any default.** A router becomes a default only after an experiment on new documents passes a page-based rule fixed before scoring.

## Consequences

### Positive

- Junk native text on pages the scan did not flag can reach OCR page by page, at the cost of the rejected pages only.
- The operator chooses the model, the question and the privacy trade-off, and can keep several routers.
- The 8-bit and projector rules are enforced in code, not only in the guide.

### Negative

- A router adds about 0.84 s a page for text and more for images on a local model, for every unflagged text page.
- Two new settings maps make `omrs.jsonc` larger and need a file-only shape.
- Selecting or editing a router reprocesses PDF sources once.

### Neutral

- Routing of flagged pages and the blank, maths and non-Latin rules do not change.
- The `cloudflare` and `ollama` kinds ship untested and carry a "Not yet tested" label until a live request passes.

## Alternatives Considered

- **Flat decision model settings like ADR-108.** Rejected: routers need more than one model (local and hosted arms).
- **Routers in the workspace database.** Rejected: settings live in `omrs.jsonc` (gotcha 18), and the CLI must resolve the host router without the web server.
- **A judge that moves a request to the next OCR engine on a bad answer.** Rejected for now: the engine list keeps the "unavailable before dispatch" rule.
- **Ship the Experiment 43 threshold as a default router.** Rejected: fitted and tested on the same documents.

## Verification

- Pinned digests show no identity change without a router.
- Tests show a rejected page goes through the local tier and the engine list alone, and `pages_needing_ocr` stays the scan count.
- A hosted router without opt-in sends zero requests.
- The confirmation experiment report states PASS or FAIL by its frozen rule.

## References

- Issue #161; Experiments 33, 38, 42, 43 and 44; TDR-024; `openspec/changes/document-reading-routers/design.md`.
