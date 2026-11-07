# ADR-116: A Switch for the Blank Page Rule, and a Fixed Page-Rule Order

- **Date:** 2026-11-07
- **Status:** Proposed (2026-11-07; built in change `page-routing-panel`; Accepted after merge to v3)
- **Deciders:** Maintainer
- **Amends:** [ADR-112](112-reading-parts-descriptor-pipeline-and-discovery.md) (decision 3: the `blank` rule gains a switch; the order stays fixed)
- **Related:** [ADR-110](110-decision-models-and-named-document-routers.md) (the router rule, order 40, and the precedent for a step option that stays out of the graph fingerprint), [ADR-114](114-per-backend-local-ocr-cuts.md) (the precedent for a PDF-only identity entry)
- **Change:** `openspec/changes/page-routing-panel/`
- **Experiment:** [Experiment 33](../../experiments/33-ocr-routing-natural-positive-2026-09-17/report.md) (the 1,123 labelled pages that calibrated the blank test)

## Context

The page rules decide what happens to the pages that the page scan flags for OCR. ADR-112 decision 3 made them an ordered pipeline: `blank` (order 10), `maths` (20), `non_latin` (30), and later `document_router` (40, ADR-110).

The `blank` rule drops a flagged page with no ink before any OCR tier reads it. The page keeps its native text and counts in `ocr_pages_blank`. The archived change `skip-blank-pages-before-worker` measured the cost: an OCR engine took 33 to 51 s for each blank page, and the blank test took about 0.28 s for each flagged page. That change chose "no setting" as a non-goal. The choice lived only in its design and in the `pdf-reader` requirement "The blank test has no setting", never in an ADR.

Change `page-routing-panel` puts every document-reading setting into one panel, in the order that a page passes through them. Two questions followed:

1. **Should the blank drop have an off switch?** The operator decided on 2026-11-06 (gate G0) that it should. A collection where the blank test is wrong needs a way to send every flagged page to OCR, from Settings and from a Read document step.
2. **Should the panel let the operator reorder the page rules?** The readers, the local OCR backends and the OCR engines are ordered lists that the operator can reorder. The page rules look like a list too.

The first draft of the change recorded no ADR. The operator rejected that at gate G0, so this ADR records both decisions and the reversal.

## Decision

1. **One flat boolean switch.** The setting is `ocr_skip_blank_pages`: environment `OCR_SKIP_BLANK_PAGES`, `omrs.jsonc` key `ocr_skip_blank_pages`, default `true`. It sits beside `ocr_maths_routing_enabled` in `config/ocr_routes.py`, flat like every OCR key. Its type is plain `bool`, not `LegacyBool`. `LegacyBool` reads only the text `true` as on, so a typo such as `ture` would turn the drop off with no error (likelihood 2, impact 2, score 4). With plain `bool`, any text that is not a boolean stops start-up with a message that names the field. A bad value in `omrs.jsonc` is listed as invalid and ignored, as for every key in that file.
2. **Off means the rule returns an empty outcome in its place.** `BlankRule.run` returns an empty `RuleOutcome` before it calls the blank test. No page renders, `ocr_pages_blank` is 0, and each blank page follows the flagged route. The pipeline, the page unit and the counts do not change. The threshold stays a versioned code constant. No setting tunes it.
3. **The switch enters the identity of PDF sources only, and only when off.** Off adds `parser.skip_blank_pages: false` through `skip_blank_payload(settings)` in `core/ingestion/ocr_identity.py`, joined in `reader_identity.pdf_parser_payload`. On adds nothing. So a default install keeps every digest, no schema version moves, and turning the switch off re-indexes PDF sources only. The `blank` descriptor keeps its identity shape (`blank_page_test` inside `ocr_routing`). Its new `SettingField` carries `enters_identity=True`.
4. **The Read document step can set it.** `ReadParams.ocr_skip_blank_pages` is `bool | None`; `None` inherits the host value. The option joins `_UNHASHED_OPTIONS` in `core/ingestion/graph_fingerprint.py`, as `document_router` and `ocr_local_cuts` did. It reaches the source identity through the PDF `parser` block, so saved graphs keep their fingerprint.
5. **The page rules keep a fixed order.** No setting, part option, Settings control or Read document step option changes the order. A rule that a setting switches off keeps its place. Three reasons:
   - Maths and non-Latin both send a page to the OCR engines. A swap cannot change where any page goes, only which rule is named first.
   - Blank must run first. A later blank rule would see pages that maths or non-Latin had already sent to OCR, so a blank page would cost engine time.
   - An order setting would enter the index identity and the tests for no benefit. The descriptor `order` field is unique by construction.

   The panel states the rule in step 2: "These checks run in a fixed order. Blank pages are checked first."

## Consequences

### Positive

- An operator can send blank pages to OCR for one collection, from Settings or from one pipeline, with no code change.
- The upgrade moves no digest. Only an operator who turns the switch off re-indexes, and only PDF sources.
- A typo in the environment value fails at start-up and does not silently change routing.
- The fixed order has a recorded decision with reasons, so the panel and the guide can state it.

### Negative

- Off costs OCR engine time on every blank flagged page (33 to 51 s each in the measurement).
- `ocr_skip_blank_pages` and `ocr_maths_routing_enabled` parse booleans in different ways. Changing `ocr_maths_routing_enabled` is out of scope.
- One more hand copy of a key (the `EffectiveSettings` field, `_READING_BOOLEANS`, `ReadParams`, the web key list, the OpenAPI enums). Each copy has a drift or pin test.

### Neutral

- The router is not affected. It judges unflagged pages with non-blank text, which is a different test.
- The step value stays out of the graph fingerprint, so the fingerprint alone cannot see it. The source identity still moves PDF sources, as for `document_router`.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| **No switch (the `skip-blank-pages-before-worker` choice)** | The operator needs an off switch for a collection where the blank test is wrong. |
| **A reading part option (`reading_part_options.blank.enabled`)** | Built-in rules ignore `enabled` by design (change `local-ocr-backends`, design D12). The Settings page and Studio show flat keys, not part options. |
| **`LegacyBool` like `ocr_maths_routing_enabled`** | An environment typo would turn the drop off with no error. |
| **The switch inside the `ocr_routing` block** | That block enters every source, so a toggle would re-index Markdown and code sources for no text change. ADR-114 moved the cuts out of that block for the same reason. |
| **Drop `blank_page_test` from `ocr_routing` when off** | The same re-index of every source, and it couples two facts. |
| **Widen `IdentitySpec` to several blocks** | A descriptor field change for external parts, to describe one key. |
| **A setting that reorders the page rules** | No benefit (decision 5), and it would enter the identity and the tests. |
| **No ADR, with the trace kept in the change design** | The operator rejected it at gate G0. The earlier "no setting" choice had no ADR, so its reversal needs one. |

## Verification

1. The existing digest pins (default install, maths off, non-Latin `detect` and `always`) keep their values.
2. A new pin for `ocr_skip_blank_pages=false` moves the PDF digest. A Markdown source under the same settings keeps the default digest.
3. With the switch off, a PDF with a blank flagged page renders no page in the blank test, and `ocr_pages_blank` is 0.
4. `OCR_SKIP_BLANK_PAGES=sometimes` stops start-up with a message that names `ocr_skip_blank_pages`.
5. No document-reading key and no Read document step option names or changes the order of the page rules.

## References

- `src/omrs/core/reading_parts.py` (the `blank` descriptor and `order` values)
- `src/omrs/integrations/pdf/page_rules/blank.py` and `src/omrs/integrations/pdf/page_rules/pipeline.py`
- `src/omrs/core/ingestion/ocr_identity.py` and `src/omrs/core/ingestion/reader_identity.py`
- `openspec/changes/archive/` (change `skip-blank-pages-before-worker`: the blank test and its measured cost)
- [Page routing guide](../guides/page-routing.md)
- [ADR-112](112-reading-parts-descriptor-pipeline-and-discovery.md), [ADR-110](110-decision-models-and-named-document-routers.md), [ADR-114](114-per-backend-local-ocr-cuts.md)
