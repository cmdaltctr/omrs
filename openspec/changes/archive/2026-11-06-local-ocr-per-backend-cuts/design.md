# Design: one confidence cut per local OCR backend

## Context

See proposal.md for the reason. Today's state, from the code on `v3` at `36965b6f`:

- The default cut of each backend lives twice: the descriptor in `core/reading_parts.py` (`LOCAL_OCR_BACKENDS`, `min_confidence`, `calibrated_by`) and its pinned `register()` line in `integrations/pdf/local_ocr/registry.py`. `tests/unit/test_reading_parts_pins.py` pins `min_confidence`, `calibrated_by` and `keeps_scripts` between the two. Integration code cannot import `core` (`integrations-are-leaves`), so this pair is the settled ADR-112 decision 1 shape.
- Two `effective_cut` functions read `ocr_local_min_confidence` as an override of every cut: `core/reading_parts.py:484` (identity, health) and `registry.py:89` (the chain).
- The script filter has three readers: `chain.escalation_reasons` (`script_not_kept`), `script_routing.non_latin_output_reason` (the `detect` post-check exemption, local-ocr-backends design D10) and `ocr_identity.local_backends_payload` (`keeps_scripts`, `output_script_version`). `script_routing.output_script` and its three constants serve only these.
- `ocr_routing` (with `local_tier.min_confidence`, the default backend's cut) enters the identity of every source. The non-default list block enters the PDF `parser` block only. The schema is 7 (`core/ingestion/source_state.py:45`).
- `core/settings.py` (489 lines) must not import any `omrs.core` module (`settings-models-are-pure-data`), so `EffectiveSettings` cannot compute descriptor defaults.
- Studio read options: `ReadParams` in `core/ingestion/graph_adapters_catalogue.py` holds each option with `_reading_rule(key)`, which runs `config/rules.document_reading_problem`. `READ_OCR_KEYS` and `READ_OPTION_KEYS` list them; `core/pipelines/levers.py` `_READ_STEP_OCR_KEYS` makes a graph-wide override host-owned. `graph_adapters_values.with_read_options` copies the step values onto the node's `EffectiveSettings`, and the identify step resolves `ocr_routing` and `local_ocr_backends` from that copy (`run_ocr_resolution`). So a step value enters the source identity through the same builders as the host value. A set option also enters the graph fingerprint and the `graph_shape` block (every source of that graph), except the options in `graph_fingerprint._UNHASHED_OPTIONS` (`document_router`, change document-reading-routers D9), which reach identify through `IngestionShape.step_options` only. `_ADDED_PARAMS` keeps later options out of saved fingerprints while unset.
- Retired keys: `config/legacy.py` (`_REMOVED_ENV_VARS` for another-shape replacements, start-up error) and `config/settings_file.py` (`_REMOVED_FILE_KEYS`, listed as `retired`, never blocks start-up), the ADR-108 D5 and page-routing-default precedents.

## Goals / Non-Goals

**Goals:**

- One number per backend, set in the Settings page, the environment or `omrs.jsonc`.
- Defaults that trace to a committed analysis.
- No language-specific code in the local tier.

**Non-Goals:**

- No change to saved Studio graph fingerprints.
- No change to `ocr_local_backends`, its default `["pp-ocrv6-small"]`, the escalation reasons other than `script_not_kept`, the non-Latin detector or `SCRIPT_DETECTOR_VERSION`.
- No move of the OCR routing switch, routing unit or blank-test version. They stay in the all-sources `ocr_routing` block.
- No new experiment run. The analysis reads saved results only.

## Decisions

### D1. One map key, `ocr_local_cuts`

Shape: `dict[str, float]`, each value `ge=0, le=1`, default `{}`, on `ReadingListMixin` in `config/reading_lists.py` beside `reading_part_options`. `EffectiveSettings` gets the same field with the same meaning (operator entries only). Compose copies it in `settings_to_effective`.

Rejected alternatives:

- **One flat key per backend** (`ocr_local_cut_pp_ocrv6_small`). A discovered backend cannot add a field, and backend names hold hyphens.
- **Nested block** (`ocr_local_cuts.indra`, env `OCR_LOCAL_CUTS__INDRA`). A nested block needs fixed fields; names with hyphens make bad environment names.
- **`reading_part_options`** (local-ocr-backends settled question 2 named it for a future per-backend override). Design D12 of that change keeps it for parts that have no flat keys, and validates it against declared `options`. A cut is a fact of every backend, with one rule. A dedicated map gives the Settings page one key to lock, save and show. The operator chose the dedicated map on 2026-11-06, which supersedes that settled question.

### D2. Environment form: a JSON object

`OCR_LOCAL_CUTS={"pp-ocrv6-small": 0.92, "indra": 0.94}`. pydantic-settings already parses a `dict` field from the environment as JSON. `READING_PART_OPTIONS` is the precedent. A comma form (`name=0.9,...`) would need a new parser and a second syntax to document. A set environment value locks the whole map on the Settings page, as for every other key.

### D3. Validation

- Value type and range: the field type (`Annotated[float, Field(ge=0, le=1)]`; booleans refused).
- Names: a model validator beside `_check_local_backends` refuses a name that `ocr_local_backends` could not list (unknown, or no default cut). Discovered names are accepted. Broken discovered names are accepted and ignored, the same rule as the list (PR #168 finding 4). The message names the accepted values and never the submitted value.
- File: `settings_file` runs the same name rule on `ocr_local_cuts` before model validation. A bad map is dropped whole and listed as `invalid`, so the file never stops start-up (settings-file spec).
- Page write: `config/rules.document_reading_problem` gains the rule for the key: `null` or an object, each name accepted, each value a number from 0 to 1. One shared function in `config/rules.py` serves all three call sites.

### D4. Defaults and evidence

| Backend | Default cut | `calibrated_by` |
| --- | ---: | --- |
| `pp-ocrv6-small` | 0.92 (was 0.9) | `46a-local-ocr-per-backend-cuts-2026-11-06` (was `39-local-tier-escalation-2026-09-30`) |
| `indra` | 0.94 (was 0.90) | `46a-local-ocr-per-backend-cuts-2026-11-06` (was `46-local-ocr-backends-2026-11-04`) |

The descriptor holds each default. The `register()` line keeps its pinned copy. No third copy exists: tests read the descriptor, and the docs name the descriptor. A grep task checks that `0.9`/`0.90` no longer appears as a cut literal in `src/omrs/`.

Evidence (read-only re-analysis on 2026-11-06 of Experiment 46's saved results; 229 pages; a page is bad when token recall < 0.5; limit: at most 5% of kept pages bad):

| PP-OCRv6 small alone | kept | bad | bad share |
| --- | ---: | ---: | ---: |
| cut 0.85 | 63 | 5 | 7.9% |
| cut 0.90 (today) | 56 | 3 | 5.4% |
| **cut 0.92** | **48** | **2** | **4.2%** |
| cut 0.94 | 35 | 2 | 5.7% |
| cut 0.96 | 23 | 0 | 0% |

| Indra alone, no script filter | kept | bad | note |
| --- | ---: | ---: | --- |
| cut 0.85 | 186 | 15 (8.1%) | Bengali 9, Latin print 6 |
| cut 0.90 | 138 | 6 (4.3%) | all Latin print |
| cut 0.92 | 117 | 3 | |
| **cut 0.94** | **97** | **0** | |
| cut 0.95 / 0.96 / 0.97 | 83 / 64 / 54 | 0 | |

| Chain PP-OCRv6 small then Indra at 0.94 | kept local | bad | bad share |
| --- | ---: | ---: | ---: |
| PP cut 0.90 | 110 | 3 | 2.7% |
| **PP cut 0.92** | **108** | **2** | **1.9%** |
| PP cut 0.94 | 106 | 2 | 1.9% |

How each default was chosen. Each backend can be listed alone, so each cut must meet the limit alone. PP-OCRv6 small: 0.92 is the lowest cut in the table above under the 5% limit. The full sweep in steps of 0.01 shows 0.91 also passes (53 kept, 2 bad, 3.8%). The operator chose 0.92 from the table (2026-11-06); the default stays 0.92 (amended 2026-11-06 when 46a was built). Indra: 0.90 is already under the limit (4.3%), but all 6 bad pages are Latin print, the case the old script filter hid. 0.94 is the lowest cut with no bad page, at a cost of 41 pages. The operator chose 0.94 (2026-11-06). In the chain, PP-OCRv6 at 0.92 then Indra at 0.94 keeps 52 more pages local than today's PP-OCRv6 alone at 0.90.

Limits: 229 pages from 9 documents (corrected 2026-11-06 from "13", which was Experiment 33's count; `pages.json` of Experiment 46 lists 9); the reference text comes from a vision model; the difference between 0.90 and 0.92 is one page. This is a setting choice, not a publication result. A later, larger set can move either default by editing one descriptor line and its experiment name.

### D5. The analysis record: `46a`, a Quick follow-up

`experiments/46a-local-ocr-per-backend-cuts-2026-11-06/` with `experiment.json` (size `Quick`, status `MEASURED`, category `ingestion`, purpose `optimisation`), `report.md` (plan at the top, then the three tables) and one `analysis.py`. The script imports Experiment 46's own row loader and recall rule from `summarise.py`, so the page rows, the recall function and the bad-page rule are byte-identical to Experiment 46. It reads Experiment 46's saved `output/` (gitignored; a `--source` folder argument points at the main checkout or the DATA copy) and writes `output/cut_sweep.json`. The report records the SHA-256 of each input file.

Why `46a` and not an addendum inside `46-local-ocr-backends-2026-11-04`: Experiment 46 has a fixed protocol and a PASS outcome. A post-hoc cut sweep inside it would blur which numbers were planned. `experiments/AGENTS.md` names the next free letter for a follow-up. Why not a new number: the work runs no OCR and reads only 46's outputs. `MEASURED`, not `PASS`, because the 5% limit was chosen after the data was seen.

If the rebuilt script gives a number that differs from the tables above, the implementer stops and reports the difference to the operator before any default changes.

### D6. Indra's script filter goes, and so does the generic filter

Remove: `LocalOcrBackendDescriptor.keeps_scripts`, the `keeps_scripts` argument of `registry.register` and `part_registry._register_backend`, the pin field, `script_not_kept` in `chain.escalation_reasons`, the exemption in `script_routing.non_latin_output_reason`, `script_routing.output_script` with `OUTPUT_SCRIPT_VERSION`, `OUTPUT_SCRIPT_MIN_LETTERS` and `OUTPUT_SCRIPT_SHARE`, and their tests.

Reason: after Indra's filter goes, no backend declares one. A capability with no user is an abstraction for a case nobody has (and the operator wants no language-specific code). The post-check keeps its `check(text, facts)` signature, because external page rules depend on it (ADR-112); `facts` simply no longer holds `keeps_scripts`.

Effect on `ocr_non_latin_routing=detect` (operator decision, 2026-11-06, option a): the `non_latin_output` post-check applies to every backend the same way, with no Indra exemption. With Indra listed, `detect` sends Indra's confident non-Latin pages to the OCR engine. The configuration and ingestion guides say: set `ocr_non_latin_routing` to `off` when Indra is listed, and let the cut decide. `always` and the pre-local `detect` check already skip Indra (local-ocr-backends D10). The live app's value is checked in the rollout (task 10.4).

External descriptors: a discovered descriptor that passes `keeps_scripts` raises `TypeError` on load and shows as broken, by the existing rule. The reading-parts guide gets a version note, as ADR-112 requires for a descriptor field change.

### D7. The single override is retired

- Environment and `.env`: `OCR_LOCAL_MIN_CONFIDENCE` joins `_REMOVED_ENV_VARS` with the replacement text `OCR_LOCAL_CUTS (a JSON object of backend name to cut)`. `OCR__LOCAL_MIN_CONFIDENCE` moves from `_NEVER_SHIPPED_ALIASES` (its flat field no longer exists) to the same table. Start-up fails with both names (gotcha 11).
- `omrs.jsonc`: `_REMOVED_FILE_KEYS["OCR_LOCAL_MIN_CONFIDENCE"] = "ocr_local_cuts"`. The key is listed as `retired` with the replacement and ignored. The server starts. The old value is not converted: it meant "every backend", which no longer exists, and a silent conversion would hide the change.
- Settings page: the Document reading body names retired reading keys found in the file (`retired_keys`). The Local OCR group shows the notice from the workspace-settings spec. "Remove it" sends a `PUT` of `ocr_local_cuts` with its saved value (or `null`). Every write of `ocr_local_cuts` removes `ocr_local_min_confidence` in the same atomic write, the way a list key save removes its old single keys today (`OLD_READING_KEYS`). The key is not added to `OLD_READING_KEYS`, because that table also means "still readable".
- Lifetime: flat rule. The entries stay while an upgrade path exists (`config/legacy.py` docstring).

### D8. Identity: the local tier moves to the PDF `parser` block, schema 7 to 8

Operator decision (2026-11-06): a cut change must re-index PDF sources only.

- `ocr_routing` (every source) becomes `{"enabled", "routing_unit", "blank_page_test"}`. The `local_tier` key goes, with both its cut and its model identity. The model moves too: it shapes PDF text only, and a `local_tier` that held only the model would keep a default-list special case for no reader.
- `parser.local_ocr_backends` (PDF sources only, through `reader_identity.pdf_parser_payload`) is present for every list, the default list included: `{"backends": [{"name", "min_confidence", "model"?}, ...]}` in list order. The keys `keeps_scripts` and `output_script_version` go. The `{}` short cut for the default list goes.
- `resolved_routing_payload` stops probing the local model; `local_backends_payload` already resolves each backend's model once per run when OCR routing is on. `run_ocr_resolution` keeps its two keys.
- Both builders read the effective cut through `core/reading_parts.effective_cut` on the settings copy they receive (host settings, or the Read step copy from `with_read_options`). An entry equal to the default gives the same bytes as no entry.
- `_INDEX_IDENTITY_SCHEMA` advances from 7 to 8.
- Result: every source in every collection re-indexes once on the next explicit ingest after the upgrade. After that, any cut change, from any source and for any backend, re-indexes PDF sources only. Markdown and code sources keep their digest.

Rejected: keeping `local_tier.min_confidence` in `ocr_routing` (the first draft). A PP-OCRv6 cut change then re-indexed every Markdown and code source, as `OCR_LOCAL_MIN_CONFIDENCE` did (likelihood 3, impact 2, score 6).

### D9. HTTP contract and pages

- `GET /v1/settings/document-reading`: `ocr_local_cuts` joins `DOCUMENT_READING_KEYS` (derived in `config/rules.py`; the web copy in `settingsDocumentReading.ts` has its drift test). Each `LocalBackendOption` gains `default_cut` (number). The body gains `retired_keys` (array of strings).
- `PUT`: `ocr_local_cuts` takes an object or `null`. `DocumentReadingValue` gains the object form.
- `GET /v1/integrations` `reading_parts.local_ocr_backends[].effective_cut`: unchanged field, new description ("the backend's `ocr_local_cuts` entry, else its default cut"). `reading_parts_health._cut` calls `core/reading_parts.effective_cut` instead of reading the old key.
- Web: `OrderedListControl` stays generic. It gains one optional per-row slot. A new small component, `LocalBackendCutInput`, renders the number input (`min=0 max=1 step=0.01`, placeholder "Default 0.92", label "Confidence cut for <label>"), validates on input and reports the value up. `DocumentReadingSection` saves `ocr_local_backends` and `ocr_local_cuts` in one `PUT`. No web file outside tests names `indra` (`tests/unit/test_indra_is_one_part.py`); the default comes from `default_cut`.
- `omrs config init`: the field gets `examples=[{"pp-ocrv6-small": 0.92}]`, so the template never shows `null` and never names `indra` in `src/omrs/`.

### D11. The Read document step option

Operator decision (2026-11-06): the cuts are also settable per pipeline in Studio.

- `ReadParams.ocr_local_cuts: Annotated[dict[str, float] | None, _reading_rule("ocr_local_cuts")] = None`. The rule is the same function as Settings (D3), so validation cannot drift. The key joins `READ_OCR_KEYS` (and so `READ_OPTION_KEYS`), `_READ_STEP_OCR_KEYS` (a graph-wide `overrides.ocr_local_cuts` is `host_owned_setting`) and the `option_params` map of `READ`.
- Merge, not replace: `with_read_options` sets `ocr_local_cuts = {**host, **step}`. A step entry replaces the host cut of its backend only; a backend without a step entry keeps the host's effective cut. Every other read option replaces its host value whole, but a map that replaced whole would silently drop host entries for backends the step did not touch, and the Studio boxes show per-backend inheritance.
- Identity: the key joins `_UNHASHED_OPTIONS`, the `document_router` precedent. The step map then never enters the graph fingerprint or the `graph_shape` block, which every source of the graph carries. It reaches the identify step through `IngestionShape.step_options`, `with_read_options` applies it, and the effective cuts enter the PDF `parser` block (D8). So a step cut change re-indexes PDF sources only, a step that repeats the host values keeps the standard identity, and saved graphs keep their fingerprint without an `_ADDED_PARAMS` entry. The other read options keep today's handling: they shape the read itself, for every source type.
- Studio: a new `web/src/studio/CutsParam.tsx` renders the option. `StepSettingsFields` passes it the step's effective backend list (the step's own `ocr_local_backends`, else the inherited host list). Each row reuses `LocalBackendCutInput` (D9). The placeholder is the inherited cut: the host entry from `field.inheritedValue`, else `default_cut` from the Document reading query that `ListParam` already uses for backend options. An empty box means inherit; with no entries left the step drops the key, as every cleared step option does (amended 2026-11-06 at apply). Built-in profiles render it read-only, as every step control.
- No web file outside tests names `indra`.

### D10. ADR: a new ADR that amends ADR-112 decision 4

ADR-112 is Accepted, so it stays as written except for a dated amendment note, the shape ADR-110 used on ADR-112 decision 3. The new ADR (the next free number, expected ADR-114, status Proposed until the merge) records: the `ocr_local_cuts` map and its Studio step option, the retirement of the override, the removal of script filters, the new defaults with 46a as evidence, the `detect` consequence, and the move of the local tier into the PDF identity so a cut change re-indexes PDF sources only. ADR-112's header gets "Amended by ADR-114" and decision 4 gets one dated note pointing to it. ADR-069's text on `OCR_LOCAL_MIN_CONFIDENCE` is history; the new ADR names it as superseded and ADR-069 is not edited.

## Risks / Trade-offs

- [Every collection re-indexes once after the upgrade] → Accepted by the operator. Release notes and the configuration guide's upgrade notes say so. Rollback restores the old digests, so a rollback also re-indexes once.
- [A stale `OCR_LOCAL_MIN_CONFIDENCE` stops start-up] → Intentional (gotcha 11). The message names `OCR_LOCAL_CUTS`. The live `.env` and the launch agent environment are checked in the rollout (task 10.3).
- [Indra under `detect` loses its non-Latin pages] → Documented; rollout checks the live value. The alternative, a per-backend "reads non-Latin" flag, is a script capability by another name, which the operator ruled out.
- [Identity pins move] Literal digest pins and the golden identity tests change with the payload. → Each re-pin names this change; a test proves a Markdown digest does not move on a cut change, and a mutation check puts the cut back in `ocr_routing` to prove the test catches it.
- [Step cuts are unhashed] A step cut does not change the graph fingerprint, so a reader of the fingerprint alone cannot see it. → The `document_router` precedent; the source identity still moves for PDF sources, which is what decides re-indexing.
- [Merge semantics differ from the other read options] → Stated in the Studio help text and the configuration guide; a test pins it.
- [Thin evidence] → 229 pages, one page between 0.90 and 0.92. Each default is one descriptor line; 46a states the limits.
- [Golden snapshots use fixed fake confidences] → A fake page between 0.90 and 0.92 would flip. The default-list snapshot test runs with an explicit cut of 0.9 (spec scenario), so the snapshots prove the chain logic did not move; a separate test proves the new default.
- [File sizes] `core/settings.py` 489, `config/__init__.py` 471, `core/reading_parts.py` 491, `config/settings_file.py` 466, `config/rules.py` 432. The new field lives in `config/reading_lists.py`. `reading_parts.py` loses the `keeps_scripts` lines before it gains any. Each task checks `tests/test_file_size_ceiling.py`.

## Migration Plan

1. Merge into `v3`. Every explicit ingest after the upgrade re-processes each source once.
2. Operator removes `OCR_LOCAL_MIN_CONFIDENCE` from the environment and `.env` if set. A leftover `ocr_local_min_confidence` in `omrs.jsonc` is ignored and can be removed from the Settings page.
3. Rollback: revert the merge commit. Old digests return, so sources re-index once more. A saved `ocr_local_cuts` key in `omrs.jsonc` is then listed as unknown and ignored.

The live-app steps are tasks group 10.

## Operator Decisions (2026-11-06)

1. `detect` post-check: the same for every backend, no Indra exemption. Guides say to set `ocr_non_latin_routing` to `off` when Indra is listed (D6).
2. The cuts move out of the all-sources identity block into the PDF-only block, so a cut change re-indexes PDF sources only (D8).
3. The pinned cut copy in the `register()` line stays, guarded by the pin test (D4).
4. The cuts are settable per pipeline on the Studio Read document step (D11).
5. The `local-ocr-backends` Purpose line is updated at archive (tasks, Workflow follow-up).

## Open Questions

None.
