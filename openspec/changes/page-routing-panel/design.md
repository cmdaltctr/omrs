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
         |  maths font? (step 2) -> straight to [5]
         v
       [3] router (optional): a "no" sends the page to [5]
```

Placement:

| Key or item | Where | Why |
| --- | --- | --- |
| `ocr_fallback_enabled` | Top of the panel, above step 1 | It decides whether steps 2 to 5 act at all. |
| `ocr_routing_unit` | Top of the panel, under the fallback row | One legal value (`page`); it describes the whole flow, not a step. The row stays so its lock and source still show. |
| `pdf_readers` | Step 1 | Readers act before the scan. |
| `ocr_skip_blank_pages`, `ocr_maths_routing_enabled`, `ocr_non_latin_routing` | Step 2, in rule order | They decide pages by their content. Blank and non-Latin act on flagged pages; the maths rule also acts on unflagged pages (checked in `pipeline.py` on 2026-11-07). |
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

- `PageRoutingPanel.tsx`: the card, the top rows, the five numbered steps, the fixed-order line, the OCR-off line. It has no "Learn more" link. It renders no control itself. It takes `renderRow(key)` and `renderCuts()` props and the current `ocr_fallback_enabled` value.
- `pageRoutingWords.ts`: step titles, step intro lines, the fixed-order line, the OCR-off line, and the key order of each step (`PANEL_STEPS`). Row labels and help lines stay in `documentReadingWords.ts` (`READING_ROWS`), which both renderers already read.
- Settings renderer (in `DocumentReadingSection.tsx`): `ReadingSettingRow` for each key, as today; the cut boxes from `local-ocr-per-backend-cuts` in step 4; the workers folder line in step 5; the Install button for an optional reader in step 1 (D8).
- Studio renderer (new `web/src/studio/ReadStepRouting.tsx`): `ParamField` or `ListParam` for each key the step's schema has, `CutsParam` in step 4. `StepSettingsFields.tsx` skips the panel keys in its generic loop for `read.document` and renders `ReadStepRouting` after the other parameters. The old single-value options keep today's rule (hidden when unset, shown when a saved graph sets them). For a reader that is not installed it shows the disabled choice with a link to Settings, and no Install button (D8).

Why props and not two copies: the step order, titles and fixed-order line must be the same in both places, and a test can pin them once. Why not one component with a `mode` flag: the save paths differ (one `PUT` per row in Settings, a draft graph in Studio), and a flag would put both inside one file.

Each new file stays well under 200 lines. `DocumentReadingSection.tsx` gets shorter.

### D7. Inherit wording in Studio, default wording in Settings

- Settings: the non-Latin select reads "off (default)", "detect", "always". Switches show the default in the source line, as every row does today.
- Studio: each Inherit choice reads "Inherit from Settings: <value in force> (<source>)", for example "Inherit from Settings: On (default)". The source comes from the Document reading query that `ListParam` already makes for backends. The panel intro in Studio says: "Inherit uses the value from Settings › Document reading. A value set here applies to this pipeline only." No Studio choice carries the word "default" except as the source inside an Inherit choice, so "default" never names a Studio value.
- The router select in Studio: "Inherit from Settings: <router or No router>", "No router" (saves `none`), then the router names.

### D8. pypdfium2 in step 1: show it, and install it from the panel

`pypdfium2` always shows in the add choice of step 1. The label is "pypdfium2 (optional)" when installed and "pypdfium2 (optional, not installed)" when not. A not-installed choice is disabled until the server reports the reader installed. The step help adds: "pypdfium2 is optional. OMRS also uses it to draw page images for the router and the dots-mocr engine; that is not a reading step."

Operator decision, 2026-11-06 (gate G0): the panel can install it. The earlier draft only linked to Integrations.

- **Install button (Settings only).** Under the disabled choice, step 1 shows an "Install" button. It starts the existing extra install job: `POST /v1/integrations/pdf-pypdfium2/install` (`installIntegration` in `web/src/api/integrations.ts`). The job is `src/omrs/transports/api/install_job.py`, "the single job that adds or removes an allowed extra". The panel adds no route and no job. The extra name comes from the `extra` field of the reader item in `GET /v1/integrations` (`pdf_reader_items.py` sets it from the package metadata), so the web code holds no extra name.
- **Allow-list check (done on this branch, 2026-11-06).** `install_environment.py` keeps a deny-list, not an allow-list: `EXCLUDED_EXTRAS = {"web"}`. `install_reason` refuses an extra only when it is excluded, its availability is `unknown`, it is already installed, it adds no packages, the server is not a `uv-tool` install, or `uv` is missing. `pdf-pypdfium2` is in `pyproject.toml` with one requirement (`pypdfium2>=4.0.0`) and is none of these. So the extra is already allowed and the change needs no backend edit for it. Task 3.5 pins this with a test, and fixes the allow rule only if the test fails.
- **When the button shows.** It follows `installable` and `install_reason` of the `pdf-pypdfium2` entry of `GET /v1/integrations`. When the entry is not installable (for example `not-uv-tool` on a checkout install), step 1 shows the reason text and the copy command that the Integrations page already shows, and no button. A 409 `install-running` shows the existing refusal text. The running, failed and ready states reuse the wording of `web/src/integrations/InstallControls.tsx`, so both places read the same.
- **After the job ends.** The panel reads the integrations state again. The job puts every successfully installed extra into `restart_needed`, so the panel shows "Restart to apply" beside the reader row. The reader becomes addable once the readers block reports `pypdfium2` installed. If the block still reports it not installed, the choice stays disabled and the panel says "Installed. Restart OMRS to use it." Task 6.1 tests both outcomes. The saved `pdf_readers` list applies after a restart in any case, like every Document reading key.
- **Studio.** The Read document step shows the not-installed reader disabled, with a link to Settings › Document reading (where the Install button is). Studio has no Install button. This keeps Studio simple. `readerOptions` gets a Studio variant of its link.
- **Optional label.** The reader options of the Document reading route carry no `extra` field, and adding one would change the contract for one word. So `pageRoutingWords.ts` holds `OPTIONAL_READERS = ["pypdfium2"]`, and `tests/unit/test_reading_parts_drift.py` (which already reads two web files) gains a check that this list equals the PDF reader descriptors whose `extra` is not `None`.

### D9. HTTP contract

No new route. `ocr_skip_blank_pages` joins the Document reading key enums in `openapi.yaml` (request and answer). The Read document operation schema comes from `ReadParams`, so the Studio catalogue shows the option with no contract edit beyond what the conformance tests ask for. Order in the enums follows `DOCUMENT_READING_KEYS`.

### D10. Docs

- New `docs/guides/page-routing.md`, user-facing, plain British English, STE style: the diagram from D1; one section per step with each setting, its default, and what it costs; the defaults (cuts 0.92 and 0.94 from `local-ocr-per-backend-cuts`, router off, non-Latin `off`, maths on, skip blank on); where pypdfium2 sits; Settings against Studio (inherit, step values apply to that pipeline only, Settings values apply after a restart, step values on the next run); when documents re-index (a table: fallback, maths and engines touch every source; skip blank, non-Latin, router, local backends and cuts touch PDF sources only; the readers list touches PDF sources only, except that a change of the first installed reader touches every source; verify each row against `source_state.py` at write time); why the rules are not reorderable (D2); evidence: Experiment 33 (blank test calibration on 1,123 pages, routing), 43 (router template and cost), 46 and 46a (local backends and cuts), 47 (router recall 0.52, so the router stays off by default).
- Links from the `README.md` guides table, `configuration.md` ("Document reading values" and the OCR sections), `ingestion.md` ("Page rules"), `reading-parts.md` ("See also") and `web-workspace.md`.
- The panel has no "Learn more" link and no guide address constant (operator decision, 2026-11-06). Nothing is added to `web/src/components/NavFoot.tsx`. The guide is reached from the README and the other guides.
- The guide has a short section on installing pypdfium2 from step 1 (D8): what the button does, why a restart is needed, and what Studio shows instead.
- Lint: `python3 ~/.agents/skills/s-documentation/scripts/doc_lint.py docs README.md`.

### D11. A new ADR records the skip-blank switch and the fixed rule order

Operator decision, 2026-11-06 (gate G0). The first draft of this design recorded no ADR. The operator rejected that. The ADR is a task (8.4 and 8.5), not part of this planning update.

- **What it records.** The `ocr_skip_blank_pages` switch (D3): a flat plain-`bool` setting, default on, with a PDF-only identity entry when off (D4), and the rejected alternatives. The fixed rule order (D2): the three reasons why no setting reorders the page rules. The reversal of the earlier "no setting" choice of `skip-blank-pages-before-worker`, which lived only in that change and in a spec requirement.
- **Number.** ADR-116 is expected, with status Proposed until the merge. `docs/adr/` on this branch ends at ADR-113. Other planned changes reserve numbers: `local-ocr-per-backend-cuts` writes ADR-114 (its design D10 and task 8.1), and `one-llamacpp-router` reserves ADR-115 (its proposal and task 10.1). ADR-116 is the next free number. The number is confirmed at apply time: task 8.4 first lists `docs/adr/` and the ADR numbers that open changes name. If another change took 116, use the next free number and update this change's artifacts.
- **ADR-112 amendment.** ADR-112 is Accepted, so its text stays except for two small edits: a dated one-line note under decision 3 ("Amended by ADR-116: the blank rule gains the `ocr_skip_blank_pages` switch. The rule order stays fixed."), and "Amended by ADR-116" on its status line. This is the shape ADR-110 used. `local-ocr-per-backend-cuts` edits the same status line for ADR-114, so rebase after it merges and keep both entries.
- **Index.** The new ADR gets a row in `docs/adr/ADR_README.md`.

Rejected by the operator: no ADR, with the trace kept only in this design.

### D12. Dependency on `local-ocr-per-backend-cuts`

This change uses, and does not redefine: the `ocr_local_cuts` key, `LocalBackendCutInput`, `CutsParam`, the `default_cut` field of each backend option, the schema 8 identity and the defaults 0.92 and 0.94. `local-ocr-per-backend-cuts` is merged and archived (PRs #183 and #184, archive `4bf0c206`). Its two placement requirements in the main specs named the old location. Task 0.3 is done: this change carries a MODIFIED block of each, "Document reading edits the confidence cut of each local OCR backend" (workspace-settings) and "Studio shows a cut box beside each backend of the Read document step" (pipeline-graphs), which name panel step 4.

## Risks / Trade-offs

- [Operators look for the old block names] → The panel keeps every label and help line; the guide has a "Where did my setting go" table; the Settings section intro names the panel.
- [Existing Vitest tests find rows by block title or card] → Expected churn. Tests that assert behaviour keep their assertions and change only the query. Each changed test is listed in the PR.
- [Turning skip blank off costs OCR time] → Default on; the help line and the guide state the cost.
- [The step value is unhashed] → A reader of the graph fingerprint alone cannot see it. The source identity still moves for PDF sources, which decides re-indexing (the `document_router` precedent).
- [File size] `core/reading_parts.py` and `core/settings.py` sit near 500 after the cuts change. The blank `SettingField` is about 8 lines; the `EffectiveSettings` field 2 lines. → Each task runs `tests/test_file_size_ceiling.py`. If `reading_parts.py` crosses 500, move helpers that are not part of the descriptor table into a sibling module that callers import directly (a re-export cannot work: `test_module_imports_nothing_from_omrs` bars `reading_parts.py` from importing the package), in its own commit, before adding the field.
- [Spec text of the cuts change names the old location] → D12 and task 0.3.
- [The number ADR-116 is taken by another change before apply] → Task 8.4 lists `docs/adr/` and the ADR numbers that open changes name. If 116 is taken, use the next free number and update this change's artifacts with `openspec-update-change`.
- [The Install button runs `uv pip install` in the server] → It reuses the existing install job and its safeguards (no shell, no request text in the command, redacted output, timeout). On an install that is not a uv tool install, the panel shows the reason and the copy command, and no button.

## Migration Plan

1. Merge `local-ocr-per-backend-cuts` into `v3` first.
2. Rebase, build, merge this change into `v3`. No digest moves; no re-index on upgrade.
3. Rollback: revert the merge commit. A saved `ocr_skip_blank_pages` in `omrs.jsonc` is then listed as unknown and ignored; an environment value is ignored as unknown by pydantic. A PDF source indexed with the switch off re-indexes once after the rollback, because the entry leaves its identity.

## Operator decisions (2026-11-06, gate G0)

The operator answered the three Open Questions at gate G0. Each answer is a decision. D6, D8, D10 and D11 hold the detail.

1. **pypdfium2 when not installed: changed.** Step 1 shows "pypdfium2 (optional, not installed)" with an "Install" button. The button starts the existing extra install job for the `pdf-pypdfium2` extra. The extra needs no allow-list change (D8). After the job ends, the reader becomes addable and the panel shows "Restart to apply". Studio shows the reader disabled, with a link to Settings. Studio has no Install button, to keep it simple.
2. **"Learn more" link: removed.** The panel has no "Learn more" link and no guide address constant. The `NavFoot.tsx` and `REPOSITORY_URL` item is dropped. The guide `docs/guides/page-routing.md` is still written. The README and the other guides link to it (D10).
3. **ADR trace: add an ADR.** A new ADR records the skip-blank switch and why the page rules keep a fixed order. It amends ADR-112 decision 3 with a dated one-line note. The ADR is a task, written at apply time. The expected number is ADR-116, confirmed at apply time (D11). The first draft said "no ADR". The operator rejected that.
4. **Every decision is visible in the web GUI.** The Skip blank pages row shows in Settings and in Studio (spec `page-routing-panel`, scenarios "Skip blank pages row in Settings" and "Skip blank pages choices in Studio"). The fixed rule order shows as a line in step 2. The pypdfium2 install shows as a button in step 1. The ADR and the guide are documents, and the guide states each decision in plain words.

## Open Questions

None left (see Operator decisions).
