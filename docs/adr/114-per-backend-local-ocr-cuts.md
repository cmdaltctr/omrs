# ADR-114: Per-Backend Local OCR Cuts, No Script Filter, and Cuts in the PDF Identity

- **Date:** 2026-11-06
- **Status:** Proposed (2026-11-06; built in change `local-ocr-per-backend-cuts`; Accepted after merge to v3)
- **Deciders:** Maintainer
- **Amends:** [ADR-112](112-reading-parts-descriptor-pipeline-and-discovery.md) (decision 4: the cut override and `keeps_scripts`)
- **Related:** [ADR-069](069-page-level-ocr-routing-and-the-pdfium-runtime.md) (introduced `OCR_LOCAL_MIN_CONFIDENCE`; this ADR supersedes that setting and edits no text of ADR-069), [ADR-105](105-pipeline-steps-own-their-ocr-settings.md) (pipeline steps own OCR settings), [ADR-110](110-decision-models-and-named-document-routers.md) (the precedent for options that stay out of the graph fingerprint)

## Context

The local OCR tier reads flagged pages with one or more backends. A backend keeps a page only when it passes a confidence cut. Four facts made the old design wrong.

1. **One number served every backend.** `ocr_local_min_confidence` replaced the cut of every listed backend. Each backend reports confidence on its own scale, so one value cannot suit two backends.
2. **Indra carried a hardcoded script filter.** `keeps_scripts` limited Indra to Arabic and Devanagari output. A confident Indra read of a Latin or Bengali page was thrown away. The filter also put a language list into the escalation rule, in conflict with the rule that no part holds language-specific code.
3. **The cut sat in the identity of every source.** `local_tier.min_confidence` was in the OCR routing block that all sources carry. A cut change re-indexed Markdown and code sources that no OCR engine ever reads (likelihood 3, impact 2, score 6).
4. **The defaults had thin support.** Both backends used 0.90 from earlier experiments (39 and 46) that measured one backend at a time with the filter in place.

Experiment 46a re-read the saved results of Experiment 46 (229 pages from 9 documents) with a cut for each backend and no script filter. It ran no OCR. The results below come from `output/cut_sweep.json` of that folder.

A page is bad when its token recall against the reference text is below 0.5. The limit is that at most 5% of the kept pages are bad. The operator chose this limit after the data was seen, so the result is a setting choice and not a test result.

PP-OCRv6 small alone:

| Cut | Kept | Bad | Bad share |
| --- | ---: | ---: | ---: |
| 0.85 | 63 | 5 | 7.9% |
| 0.90 (old default) | 56 | 3 | 5.4% |
| 0.91 | 53 | 2 | 3.8% |
| **0.92** | **48** | **2** | **4.2%** |
| 0.94 | 35 | 2 | 5.7% |
| 0.96 | 23 | 0 | 0% |

Indra alone, no script filter:

| Cut | Kept | Bad | Where the bad pages are |
| --- | ---: | ---: | --- |
| 0.85 | 186 | 15 (8.1%) | Bengali 9, Latin print 6 |
| 0.90 (old default) | 138 | 6 (4.3%) | all Latin print |
| 0.92 | 117 | 3 | Latin |
| **0.94** | **97** | **0** | none |
| 0.95 / 0.96 / 0.97 | 83 / 64 / 54 | 0 | none |

Chain: PP-OCRv6 small at its cut, then Indra at 0.94 on the pages left:

| PP-OCRv6 small cut | Kept local | Bad | Bad share |
| --- | ---: | ---: | ---: |
| 0.90 | 110 | 3 | 2.7% |
| **0.92** | **108** | **2** | **1.9%** |
| 0.94 | 106 | 2 | 1.9% |

The chain at 0.92 and 0.94 keeps 108 pages local with 2 bad pages. PP-OCRv6 small alone at the old cut of 0.90 keeps 56 pages with 3 bad pages.

**Limits of the evidence.** The sample is 229 pages from 9 documents (four non-Latin and five Latin). The reference text comes from a vision model, not from a person. The step from 0.90 to 0.92 for PP-OCRv6 small changes one bad page (3 against 2). On the 0.01 grid, 0.91 also passes the limit; the operator chose 0.92. The chain table fixes Indra at 0.94 and does not sweep it. A larger sample can move either default by one descriptor line.

## Decision

1. **One map setting, `ocr_local_cuts`.** It maps a backend name to a cut from 0 to 1. The environment form is `OCR_LOCAL_CUTS` as a JSON object, for example `{"indra": 0.96}`. The `omrs.jsonc` form is the object `"ocr_local_cuts": {"indra": 0.96}`. The default is an empty map. A backend with no entry uses its descriptor default. An entry changes the cut of its own backend only. An entry for a backend that is not listed is accepted and has no effect. The map is on `ReadingListMixin` beside `reading_part_options`.
2. **Start-up refuses a bad map.** An unknown backend name, a value that is not a number (a boolean is not a number) or a value outside 0 to 1 stops start-up. The message names the key, the rule and the accepted backend names. It never repeats the submitted value. In `omrs.jsonc`, the settings-file check drops a bad map whole and lists it as invalid, so the file never stops start-up.
3. **New defaults from Experiment 46a.** `pp-ocrv6-small` 0.92 and `indra` 0.94. Both descriptors name `46a-local-ocr-per-backend-cuts-2026-11-06` in `calibrated_by`. The descriptor in `core/reading_parts.py` holds each default. The `register()` line keeps its pinned copy (ADR-112 decision 1), and the pin test fails when the two differ. No other file holds a cut value.
4. **The single override is retired.** `OCR_LOCAL_MIN_CONFIDENCE` and `OCR__LOCAL_MIN_CONFIDENCE` in the environment or `.env` stop start-up. The message names `OCR_LOCAL_CUTS`. In `omrs.jsonc`, `ocr_local_min_confidence` is ignored and listed as retired with the replacement `ocr_local_cuts`. The server still starts. OMRS does not convert the old value, because it meant "every backend" and that meaning no longer exists. Every save of `ocr_local_cuts` removes the old key from the file.
5. **Indra's script filter is removed, and no backend has one.** The descriptor field `keeps_scripts`, the escalation reason `script_not_kept`, the output-script rule `output_script` and its constants are deleted. Confidence alone decides whether a backend keeps a page. A discovered descriptor that still passes `keeps_scripts` raises `TypeError` when it loads, and health shows the part as broken.
6. **Consequence for `ocr_non_latin_routing=detect`.** The post-check of `detect` now applies to every backend, Indra included, because no backend is exempt by script. Under `detect`, every mostly non-Latin result of Indra escalates to the OCR engines. The guides tell the operator to set `ocr_non_latin_routing` to `off` when `indra` is listed. A per-backend flag "reads non-Latin" was ruled out: it is a script capability under another name.
7. **Studio: a Read document step option.** The step takes an optional `ocr_local_cuts`, validated by the same rule. A step entry replaces the cut of its own backend in that pipeline only. A backend with no step entry keeps the effective cut of the host. This is a merge. Every other read option replaces the host value as a whole, but a whole replacement would drop host entries for backends that the step did not touch. Clearing the last step cut removes the key (inherit). A graph-wide `overrides.ocr_local_cuts` is refused as host-owned (`host_owned_setting`). The option joins `_UNHASHED_OPTIONS`, as `document_router` did in ADR-110, so it never enters the graph fingerprint and saved graphs keep their fingerprint.
8. **The cuts move into the PDF identity, and the schema advances from 7 to 8.** The OCR routing block that every source carries is now `{enabled, routing_unit, blank_page_test}`. The effective cut of each listed backend and the resolved local model identity move into the PDF-only `parser` block, which lists every backend in list order (the default list too). An entry equal to the default cut gives the same bytes as no entry. A change to a cut, from any source including a Studio step, re-indexes PDF sources only. Markdown and code sources keep their digest.
9. **One re-index at upgrade, accepted.** The payload change moves every source digest once. The next explicit ingest after the upgrade processes every source. A second ingest with no change processes none. Rollback restores the old digests, so a rollback re-indexes once more.
10. **Web and API.** Settings > Document reading > Local OCR gives each backend row a "Confidence cut" input. An empty input shows the default and means "use the default". The Document reading routes accept and return `ocr_local_cuts`, each backend option carries `default_cut`, and the body lists `retired_keys`. The Integrations reading-parts row reports the effective cut.

## Consequences

### Positive

- Each backend gets a cut that matches its own confidence scale and its own evidence.
- The chain keeps 108 pages local with 2 bad pages (1.9%) instead of 56 pages with 3 bad pages for PP-OCRv6 small alone at the old cut.
- A new backend adds no script logic. The escalation rule has no language list.
- A cut change re-indexes PDF sources only, so Markdown and code collections no longer re-index for an OCR setting.
- The operator can set a cut on the Settings page and per pipeline in Studio, with no edit of `omrs.jsonc` by hand.

### Negative

- Every collection re-indexes once after the upgrade. The operator accepted this on 2026-11-06.
- A leftover `OCR_LOCAL_MIN_CONFIDENCE` in the environment or `.env` stops start-up until the operator removes it.
- Under `detect`, Indra keeps no Arabic or Devanagari page. The operator must set `off` to use Indra's strength on those scripts.
- The merge rule of the step option differs from every other read option. Studio help text and the guides state it, and a test pins it.
- The defaults rest on 229 pages from 9 documents with model-made reference text, and the gap between 0.90 and 0.92 is one page.
- A step cut does not change the graph fingerprint, so the reader fingerprint alone cannot see it. Source identity still moves PDF sources, and that decides re-indexing.

### Neutral

- `ocr_local_backends`, its default `["pp-ocrv6-small"]`, the other escalation reasons, the non-Latin detector and `SCRIPT_DETECTOR_VERSION` do not change.
- ADR-069 keeps its text on `OCR_LOCAL_MIN_CONFIDENCE` as history. This ADR names the setting as superseded.
- At archive, the Purpose line of `openspec/specs/local-ocr-backends/spec.md` loses the clause on the output scripts that a backend may keep.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| **One flat key per backend** (`ocr_local_cut_pp_ocrv6_small`) | A discovered backend cannot add a field to the settings model, and backend names hold hyphens. |
| **A nested block** (`ocr_local_cuts.indra`, env `OCR_LOCAL_CUTS__INDRA`) | A nested block needs fixed fields. Hyphens make bad environment names. |
| **`reading_part_options`** (the future override named in the `local-ocr-backends` design) | That map keeps parts without flat keys and validates against declared `options`. The cut is a fact of every backend, and a dedicated map gives the Settings page one key to lock, save and show. The operator chose the dedicated map. |
| **Comma form in the environment** (`indra=0.96,...`) | `READING_PART_OPTIONS` uses JSON, and a JSON object keeps one parsing rule and one validation path. |
| **Keep `ocr_local_min_confidence` beside the map** | Two settings would answer one question. A precedence rule would hide which one applies. |
| **Convert the old value on upgrade** | The old value meant "every backend". A silent conversion would hide the change. |
| **Keep Indra's script filter** | The filter threw away confident Latin and Bengali reads. It also put a language list in the escalation rule. |
| **A per-backend "reads non-Latin" flag** | It is a script capability under another name. The operator ruled it out. |
| **Keep `local_tier` in the all-sources routing block** | A cut change would re-index Markdown and code sources that no OCR engine reads. |
| **A new experiment run for the defaults** | The analysis needs no OCR. It reads saved results, which cost nothing to re-run. |
| **Do nothing** | Without the script filter, a shared cut of 0.90 lets Indra keep 6 bad Latin pages (4.3% of its kept pages) that the filter used to hide. It also leaves the re-index problem. |

## Verification

1. **Evidence.** Re-run `experiments/46a-local-ocr-per-backend-cuts-2026-11-06/analysis.py` on the saved Experiment 46 output. The three tables above match `output/cut_sweep.json`.
2. **Pins.** `tests/unit/test_reading_parts_pins.py` fails when a descriptor default and its `register()` copy differ.
3. **Identity.** A cut change moves the digest of a PDF source and keeps the digest of a Markdown source. A mutation that puts the cut back into the routing block fails the Markdown test.
4. **Retirement.** `OCR_LOCAL_MIN_CONFIDENCE=0.9` stops start-up with a message that names `OCR_LOCAL_CUTS`. `ocr_local_min_confidence` in `omrs.jsonc` is listed as retired and ignored.
5. **Script filter.** With `OCR_LOCAL_BACKENDS=indra,pp-ocrv6-small`, Indra keeps a Latin page and a Bengali page at confidence 0.95. No page carries `script_not_kept`.

## References

- [Experiment 46a report](../../experiments/46a-local-ocr-per-backend-cuts-2026-11-06/report.md) (the cut sweep and its limits)
- [Experiment 46 report](../../experiments/46-local-ocr-backends-2026-11-04/report.md) (the saved results that 46a re-reads)
- `openspec/changes/local-ocr-per-backend-cuts/` (proposal, design D1 to D11, tasks)
- [Configuration guide: Local OCR backends](../guides/configuration.md#local-ocr-backends)
- [Configuration guide: Per-backend local OCR cuts](../guides/configuration.md#per-backend-local-ocr-cuts) (upgrade notes)
- [Pipelines guide: Local OCR cuts on Read document step](../guides/pipelines.md#local-ocr-cuts-on-read-document-step)
- [Reading parts guide](../guides/reading-parts.md)
- [ADR-112](112-reading-parts-descriptor-pipeline-and-discovery.md), [ADR-069](069-page-level-ocr-routing-and-the-pdfium-runtime.md), [ADR-105](105-pipeline-steps-own-their-ocr-settings.md), [ADR-110](110-decision-models-and-named-document-routers.md)
