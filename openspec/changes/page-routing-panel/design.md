# Design: one Page routing panel in Settings and Studio

## Context

See proposal.md for the reason. Current state, read on `v3` at `79194bf2` (before `local-ocr-per-backend-cuts` lands):

- **Settings › Document reading** (`web/src/settings/DocumentReadingSection.tsx`, 164 lines) renders three cards: "PDF reading" (`pdf_readers`), "OCR" with four blocks in two columns (`OCR_BLOCKS`: "When to use OCR" = fallback, routing unit, non-Latin; "Maths pages"; "Local OCR"; "Engines" with the workers folder line), and "Router" (`DocumentRoutersCard.tsx`: the host `document_router` row plus the named routers). Each key is one `ReadingSettingRow` (value in force, source, default, help, Edit, Save, "Use default", "Restart to apply", lock line). Words and help lines live in `documentReadingWords.ts`.
- **Studio** renders each Read document parameter through `StepSettingsFields.tsx` in schema order. Lists use `ListParam.tsx` (Inherit or Set list, then `OrderedListControl`). Nullable booleans use a tri-state (Inherit, On, Off) and enums a select with Inherit (`ParamField.tsx`). `InheritNote` names the inherited host value but not its source.
- **Page rules** are descriptors in `core/reading_parts.py` (491 lines): `blank` 10 (no setting), `maths` 20 (`ocr_maths_routing_enabled`), `non_latin` 30 (`ocr_non_latin_routing`), `document_router` 40. `PAGE_RULE_KEYS` (`config/rules.py`), `READ_OCR_KEYS` (`core/ingestion/graph_adapters_catalogue.py`) and `_READ_STEP_OCR_KEYS` (`core/pipelines/levers.py`) derive from the descriptors' `settings`. `ReadParams` fields and `_READING_BOOLEANS` are hand-typed. `tests/unit/test_reading_parts_single_source.py` already moves the digest for every `enters_identity` field of a rule (`test_each_identity_setting_moves_the_source_digest`).
- **The blank rule** (`integrations/pdf/page_rules/blank.py`) always calls `blank_pages.find_blank_pages` on the routed pages. The test renders through LiteParse; failure is cheap (no page is blank). Its version enters the all-sources `ocr_routing` block (`ocr_identity.py:95`). The archived change `skip-blank-pages-before-worker` chose "no setting" as a non-goal; that choice lives in its design and in the `pdf-reader` requirement "The blank test has no setting", not in an ADR.
- **Identity blocks** (`core/ingestion/source_state.py`): `ocr_routing`, `ocr_worker_fingerprint` and `maths_routing` enter every source; `parser` entries from `reader_identity.pdf_parser_payload` enter PDF sources only. After `local-ocr-per-backend-cuts`, `ocr_routing` is `{enabled, routing_unit, blank_page_test}` and the local tier is in `parser`, schema 8.
- **pypdfium2** is a PDF reader descriptor (`extra="pdf-pypdfium2"`), not in `PDF_READERS_DEFAULT` (`pdf_inspector, liteparse, pypdf`). It is also the second page renderer for image routers (`integrations/pdf/page_images/registry.py`, after LiteParse) and the renderer inside the dots-mocr worker environment (`ocr-workers/engines/dots-mocr`). Today an uninstalled reader shows in the add menu as disabled, "(not installed)", with an Integrations link (`readerOptions`).
- File sizes near the 500-line ceiling: `core/settings.py` 489, `core/reading_parts.py` 491, `core/ingestion/graph_adapters_catalogue.py` 458, `config/rules.py` 432. `local-ocr-per-backend-cuts` changes the first two before this change starts.

## Goals / Non-Goals

**Goals:**

- One panel, one layout, used by Settings and by the Studio Read document step.
- The only backend change is the skip-blank switch, end to end.
- No digest moves on upgrade.

**Non-Goals:**

- No change to rule order, rule semantics, the blank threshold or its version.
- No new HTTP route. The router names come from the existing routers route.
- No change to the cut boxes, their validation or their words (owned by `local-ocr-per-backend-cuts`).
- No generated web lists from descriptors (ADR-112 keeps them hand-typed with drift tests).
- No change to other Settings sections or other Studio steps.

## Decisions

### D1. One panel in flow order, and where every key goes

The panel follows the path of a page. ASCII form, the same diagram the guide uses:

```
PDF file
  |
  v
[1] PDF readers (pdf_readers, first installed reader reads)
  |
  v
page scan: flag the pages that need OCR
  |
  +--> flagged pages
  |      |
  |      v
  |    [2] page rules, fixed order
  |        blank (skip blank pages) -> keep native text, no OCR
  |        maths                    -> straight to [5]
  |        non-Latin                -> straight to [5]
  |      |
  |      v
  |    [4] local OCR backends (in order, one cut each)
  |      |  page below every cut
  |      v
  |    [5] OCR engines (in order)
  |
  +--> unflagged pages with text
         |
         v
       [3] router (optional): a "no" sends the page to [5]
```

Placement:

| Key or item | Where | Why |
| --- | --- | --- |
| `ocr_fallback_enabled` | Top of the panel, above step 1 | It decides whether steps 2 to 5 act at all. |
| `ocr_routing_unit` | Top of the panel, under the fallback row | One legal value (`page`); it describes the whole flow, not a step. The row stays so its lock and source still show. |
| `pdf_readers` | Step 1 | Readers act before the scan. |
| `ocr_skip_blank_pages`, `ocr_maths_routing_enabled`, `ocr_non_latin_routing` | Step 2, in rule order | They decide flagged pages. |
| `document_router` | Step 3 | It judges unflagged pages with text. |
| `ocr_local_backends` + cut boxes | Step 4 | Local OCR reads the flagged pages no rule claimed. |
| `ocr_engines` + workers folder line | Step 5 | The folder line explains why no engine can run. |
| Named routers (create, edit, rename, delete) | Router section, below the panel | A definition is not a step. Step 3 links to it. |

The PDF reading card and the OCR card go. The Router card stays with its router list and loses the host row. The panel is one full-width card with the steps stacked in one column, because a flow reads top to bottom; the old two-column OCR grid goes (omrs-design layout rule 2 applies to tall cards, and a flow split into columns no longer reads as a flow).

Rejected: keep the cards and add a diagram above them. The diagram and the controls would drift, and the operator asked for the controls themselves in flow order.

### D2. Lists where order matters, switches where it does not, and no rule reordering

Readers, local backends and engines are fallback lists: order decides which part reads first. They stay `OrderedListControl`. The three rule settings are switches or one choice.

The page rules are not reorderable, for three reasons the panel guide states:

1. Maths and non-Latin both send a page to the OCR engines. Swapping them cannot change where any page goes, only which rule is named first.
2. Blank must run first. A later blank rule would see a page that maths or non-Latin had already sent to OCR, so a blank page would cost engine time.
3. A reorder setting would enter the index identity and the tests for no benefit. ADR-112 decision 3 already fixes the order, and the descriptor `order` field is unique by construction.

Step 2 shows the line "These checks run in a fixed order. Blank pages are checked first." The router (order 40) is also fixed; it is step 3 on its own.

### D3. The skip-blank setting

- Name `ocr_skip_blank_pages`, environment `OCR_SKIP_BLANK_PAGES`, `omrs.jsonc` key `ocr_skip_blank_pages`, type plain `bool` (pydantic's standard parse), default `True`, beside `ocr_maths_routing_enabled` in `config/ocr_routes.py`. Flat on purpose, like every OCR key (configuration guide).

Why not `LegacyBool`, which `ocr_maths_routing_enabled` uses: it reads only the text `true` (any case) as on, so an environment typo such as `ture` would turn the drop off with no error, cost OCR time on every blank page and re-index PDF sources (likelihood 2, impact 2, score 4). With plain `bool`, `true/false/1/0/yes/no/on/off` parse and any other text stops start-up with a message naming the field. A bad value in `omrs.jsonc` is listed as invalid and ignored, the existing settings-file rule. `ocr_maths_routing_enabled` keeps `LegacyBool`; changing it is out of scope.
- Descriptor: the `blank` rule gains `settings=(SettingField(name="ocr_skip_blank_pages", env="OCR_SKIP_BLANK_PAGES", default=True, enters_identity=True),)`. `PAGE_RULE_KEYS`, `DOCUMENT_READING_KEYS`, `READ_OCR_KEYS` and `_READ_STEP_OCR_KEYS` pick it up from the descriptor, in rule order (so it comes before `ocr_maths_routing_enabled`). Hand copies: `EffectiveSettings` field and the `settings_to_effective` copy in `compose_settings.py`, `_READING_BOOLEANS` in `config/rules.py`, `ReadParams`, the web `DOCUMENT_READING_KEYS` and the OpenAPI enums. Each has a drift or pin test today (`test_reading_parts_drift.py`, `settingsDocumentReading.test.ts`, the OpenAPI conformance tests).
- Rule: `BlankRule.run` returns an empty `RuleOutcome` when `ctx.settings.ocr_skip_blank_pages` is false, before it calls the blank test. No page renders, so turning it off also saves the render time. The pipeline, the page unit and the counts need no change: with no drop, `ocr_pages_blank` is 0 and each blank page follows the flagged route.
- The router is not affected. It judges unflagged pages with non-blank native text, which is a different test.
- Help line: "On: a flagged page with no ink keeps its native text and costs no OCR. Off: blank pages go to OCR like any flagged page." The guide adds the cost figure from the archived change (33 to 51 s of engine time per blank page).

Rejected: a reading part option (`reading_part_options.blank.enabled`). Built-in rules ignore `enabled` by design (design D12 of change `local-ocr-backends`; reading-parts guide, "Part options"), and the Settings page and Studio show flat keys, not part options.

### D4. Identity of the switch: a PDF-only entry when off

- Off adds `parser.skip_blank_pages: false` through a new builder `skip_blank_payload(settings)` in `core/ingestion/ocr_identity.py`, joined in `reader_identity.pdf_parser_payload`. On adds nothing.
- So: no digest moves on upgrade, no schema bump, and turning the switch off re-indexes PDF sources only on the next explicit ingest. Markdown and code sources keep their digest.
- The `blank` descriptor keeps `identity=IdentitySpec(block="ocr_routing", keys=("blank_page_test",), presence="always")`. The switch is described by its `SettingField.enters_identity`, which the single-source test already turns into a digest check.

Rejected:

- **The switch in `ocr_routing`.** That block enters every source, so a toggle would re-index every Markdown and code source for no text change. `local-ocr-per-backend-cuts` D8 moved the cuts out of that block for the same reason.
- **Drop `blank_page_test` from `ocr_routing` when off.** Same all-sources re-index, and it couples two facts.
- **Widen `IdentitySpec` to several blocks.** A descriptor field change for external parts (ADR-112 asks for a version note) to describe one key.

### D5. The Read document step option

- `ReadParams.ocr_skip_blank_pages: Annotated[bool | None, _reading_rule("ocr_skip_blank_pages")] = None`, and the key joins the `option_params` map of `READ`. `READ_OCR_KEYS` and `_READ_STEP_OCR_KEYS` already derive it (D3), so a graph-wide `overrides.ocr_skip_blank_pages` is `host_owned_setting` with no extra edit.
- The key joins `_UNHASHED_OPTIONS` in `core/ingestion/graph_fingerprint.py`, the `document_router` and `ocr_local_cuts` precedent. The step value never enters the graph fingerprint or the `graph_shape` block (which every source of the graph carries). It reaches identify through `IngestionShape.step_options`, `with_read_options` copies it onto the node settings, and D4 puts it in the PDF `parser` block. Saved graphs keep their fingerprint without an `_ADDED_PARAMS` entry.
- A step that repeats the host value gives the standard identity.

### D6. One layout component, two row renderers

New folder `web/src/pageRouting/`:

- `PageRoutingPanel.tsx`: the card, the top rows, the five numbered steps, the fixed-order line, the OCR-off line, the "Learn more" link. It renders no control itself. It takes `renderRow(key)` and `renderCuts()` props and the current `ocr_fallback_enabled` value.
- `pageRoutingWords.ts`: step titles, step intro lines, the fixed-order line, the OCR-off line, the guide address, and the key order of each step (`PANEL_STEPS`). Row labels and help lines stay in `documentReadingWords.ts` (`READING_ROWS`), which both renderers already read.
- Settings renderer (in `DocumentReadingSection.tsx`): `ReadingSettingRow` for each key, as today; the cut boxes from `local-ocr-per-backend-cuts` in step 4; the workers folder line in step 5.
- Studio renderer (new `web/src/studio/ReadStepRouting.tsx`): `ParamField` or `ListParam` for each key the step's schema has, `CutsParam` in step 4. `StepSettingsFields.tsx` skips the panel keys in its generic loop for `read.document` and renders `ReadStepRouting` after the other parameters. The old single-value options keep today's rule (hidden when unset, shown when a saved graph sets them).

Why props and not two copies: the step order, titles and fixed-order line must be the same in both places, and a test can pin them once. Why not one component with a `mode` flag: the save paths differ (one `PUT` per row in Settings, a draft graph in Studio), and a flag would put both inside one file.

Each new file stays well under 200 lines. `DocumentReadingSection.tsx` gets shorter.

### D7. Inherit wording in Studio, default wording in Settings

- Settings: the non-Latin select reads "off (default)", "detect", "always". Switches show the default in the source line, as every row does today.
- Studio: each Inherit choice reads "Inherit from Settings: <value in force> (<source>)", for example "Inherit from Settings: On (default)". The source comes from the Document reading query that `ListParam` already makes for backends. The panel intro in Studio says: "Inherit uses the value from Settings › Document reading. A value set here applies to this pipeline only." No Studio choice carries the word "default", because there "default" would mean the Settings value, not the code default.
- The router select in Studio: "Inherit from Settings: <router or No router>", "No router" (saves `none`), then the router names.

### D8. pypdfium2 in step 1

`pypdfium2` always shows in the add choice of step 1 with the label "pypdfium2 (optional)" when installed and "pypdfium2 (optional, not installed)" with the Integrations link when not. The not-installed choice stays disabled, the existing reader rule ("An uninstalled reader can be listed already but not added"). The step help adds: "pypdfium2 is optional. OMRS also uses it to draw page images for the router and the dots-mocr engine; that is not a reading step." The reader options in the API carry no `extra` field, and adding one would change the contract for one word. So `pageRoutingWords.ts` holds `OPTIONAL_READERS = ["pypdfium2"]`, and `tests/unit/test_reading_parts_drift.py` (which already reads two web files) gains a check that this list equals the PDF reader descriptors whose `extra` is not `None`.

### D9. HTTP contract

No new route. `ocr_skip_blank_pages` joins the Document reading key enums in `openapi.yaml` (request and answer) and the `DocumentReadingValue` boolean group. The Read document operation schema comes from `ReadParams`, so the Studio catalogue shows the option with no contract edit beyond what the conformance tests ask for. Order in the enums follows `DOCUMENT_READING_KEYS`.

### D10. Docs

- New `docs/guides/page-routing.md`, user-facing, plain British English, STE style: the diagram from D1; one section per step with each setting, its default, and what it costs; the defaults (cuts 0.92 and 0.94 from `local-ocr-per-backend-cuts`, router off, non-Latin `off`, maths on, skip blank on); where pypdfium2 sits; Settings against Studio (inherit, step values apply to that pipeline only, Settings values apply after a restart, step values on the next run); when documents re-index (a table: fallback, maths and engines touch every source; readers list, skip blank, non-Latin, router, local backends and cuts touch PDF sources only; verify each row against `source_state.py` at write time); why the rules are not reorderable (D2); evidence: Experiment 33 (blank test calibration on 1,123 pages, routing), 43 (router template and cost), 46 and 46a (local backends and cuts), 47 (router recall 0.52, so the router stays off by default).
- Links from the `README.md` guides table, `configuration.md` ("Document reading values" and the OCR sections), `ingestion.md` ("Page rules"), `reading-parts.md` ("See also") and the panel's "Learn more".
- Guide address: `https://github.com/cmdaltctr/omrs/blob/main/docs/guides/page-routing.md`, beside `REPOSITORY_URL` in `web/src/components/NavFoot.tsx`. See Open Questions.
- Lint: `python3 ~/.agents/skills/s-documentation/scripts/doc_lint.py docs README.md`.

### D11. No ADR

The two decisions are recorded here, not in an ADR:

- **Fixed rule order** is already ADR-112 decision 3 ("run in a fixed order"). D2 only explains it to the user.
- **The skip-blank switch** adds one flat setting to an existing rule within the descriptor model. It adds no pattern, dependency or boundary. The earlier "no setting" choice was a non-goal of an OpenSpec change and a `pdf-reader` requirement; the spec delta removes that requirement with its reason, which is the record.

ADR-112 is not edited. If the operator wants a trace in the ADR, the smallest form is one dated amendment line under decision 3; that is an Open Question, not a task.

### D12. Dependency on `local-ocr-per-backend-cuts`

This change uses, and does not redefine: the `ocr_local_cuts` key, `LocalBackendCutInput`, `CutsParam`, the `default_cut` field of each backend option, the schema 8 identity and the defaults 0.92 and 0.94. Task 0 rebases on `v3` with that change merged. That change's two placement requirements name the old location ("Settings › Document reading › Local OCR" and the Studio step list). If its specs are archived before this change archives, task 0.3 turns this change's placement into MODIFIED blocks of those requirements; until then the `page-routing-panel` requirement "The Page routing panel shows the page flow in five steps" carries the new placement.

## Risks / Trade-offs

- [Operators look for the old block names] → The panel keeps every label and help line; the guide has a "Where did my setting go" table; the Settings section intro names the panel.
- [Existing Vitest tests find rows by block title or card] → Expected churn. Tests that assert behaviour keep their assertions and change only the query. Each changed test is listed in the PR.
- [Turning skip blank off costs OCR time] → Default on; the help line and the guide state the cost.
- [The step value is unhashed] → A reader of the graph fingerprint alone cannot see it. The source identity still moves for PDF sources, which decides re-indexing (the `document_router` precedent).
- [File size] `core/reading_parts.py` and `core/settings.py` sit near 500 after the cuts change. The blank `SettingField` is about 8 lines; the `EffectiveSettings` field 2 lines. → Each task runs `tests/test_file_size_ceiling.py`. If `reading_parts.py` crosses 500, move the page rule table into a sibling module `core/reading_parts_rules.py` re-exported by `reading_parts.py`, in its own commit, before adding the field.
- [Spec text of the cuts change names the old location] → D12 and task 0.3.
- [Learn more points at a branch that lacks the guide until release] → Open Question 2.

## Migration Plan

1. Merge `local-ocr-per-backend-cuts` into `v3` first.
2. Rebase, build, merge this change into `v3`. No digest moves; no re-index on upgrade.
3. Rollback: revert the merge commit. A saved `ocr_skip_blank_pages` in `omrs.jsonc` is then listed as unknown and ignored; an environment value is ignored as unknown by pydantic. A PDF source indexed with the switch off re-indexes once after the rollback, because the entry leaves its identity.

## Open Questions

1. **pypdfium2 when not installed.** D8 keeps it disabled with an install link, like every reader today. The operator wrote "show as addable". If that means "addable even when not installed" (like an unprovisioned engine), D8 changes one rule and one scenario. Default: disabled until installed.
2. **"Learn more" target.** GitHub `main` gets the guide only at the next release; `v3` has it at merge. A copy served by `omrs web` would always match the installed version but adds a static route. Default: GitHub `main`.
3. **ADR trace.** D11 records no ADR. Should ADR-112 decision 3 get a one-line dated note naming the switch? Default: no.
