# Design: page reading built from replaceable reading parts

## Context

See proposal.md for the why and the terms.

**Observed in the code** (branch `feat/local-ocr-backends`, audit of 2026-11-04; paths are under `src/omrs/` unless stated):

- The local tier is one call: `page_routing.local_ocr` calls `pdf_inspector.process_pdf_with_ocr(mode="force", ...)` (`integrations/pdf/page_routing.py:195-206`). The shared escalation rule follows it (`:217-232`). The diagnostic producer name is `OCR_BACKEND_LOCAL_OCR = "pdf_inspector_ocr"` (`:45`).
- The page unit wires three rules by hand, in this order (`integrations/pdf/ocr_routing.py:188-198`): blank pages leave the route first; maths pages are detected on all pages and then lose the blank pages; non-Latin works on the routed pages only. Non-Latin adds a local post-check reason (`page_routing.py:231-232`) and has its own degrade path, `_local_fallback` (`ocr_routing.py:258-270`). Maths has none.
- The three rules use three identity shapes: the blank-test version inside the `ocr_routing` block (`core/ingestion/ocr_identity.py:96`); an always-present top-level maths block (`core/ingestion/source_state.py:193`); a non-Latin `parser` entry present only when the mode is not `off` and only for PDFs (`core/ingestion/reader_identity.py:37-43`), whose count key is left out of the excluded-key list (`core/ingestion/embed_exclusions.py:62`).
- 10 registries exist (9 in `core/`, 1 in `integrations/`), listed in `tests/test_strategy_registration_inventory.py:62-72`. Each repeats `_registry`, `_cache`, `get()` and an import-path loader. No shared helper exists. The PDF reader registry takes `register(name, import_path, probe_module, text_format=, page_provenance=, output_revision=)` (`integrations/pdf/registry.py:158-189`).
- `config/` cannot import `integrations/`, so `PDF_READER_NAMES` is a hand tuple (`config/rules.py:95`) pinned to the registry by a test (`tests/unit/test_document_reading_rules.py:54-55`).
- Import contracts (`pyproject.toml`): `config-is-leaf` (631-655) forbids `config` from importing `core.ingestion`, `core.retrieval`, `core.metadata`, `core.vectordb`, `core.profiles`, `core.providers`, `compose`, `transports`, `integrations` and `daemon`. Other `core` modules are allowed. `integrations-are-leaves` (660-689) forbids `integrations` from importing `core`, with three PERMANENT pure-data edges to `core.settings`. `settings-models-are-pure-data` (209-222) forbids `core.settings` from importing `omrs.core`.
- The only host-side use of `importlib.metadata` is `version` (`__init__.py:15,50`) and `distributions()` (`transports/api/uninstall_plan.py:128`). The OCR worker already discovers engines through `entry_points(group="omrs.ocr_engine")` (`ocr-workers/core/src/omrs_ocr_worker_core/engine.py:27,100,113`).
- Health: the local tier row is hand-coded for PP-OCRv6 (`transports/api/runtime_components.py:43-51,146-155,215-241`). The run-time switch-off `_LOCAL_TIER_BROKEN` (`page_routing.py:253-264`) has no reader outside `integrations/pdf/`. Page rules have no health row.
- Legacy engine keys: `ocr_engine_primary` and `ocr_engine_fallback` are documented input aliases that "stay readable in every source and are never retired" (`config/rules.py:108`). One live reader remains: `compose_runtimes._ocr_runtimes` loops over `OCR_ROUTE_SETTINGS` (`compose_runtimes.py:45,198-232`), so a third engine's `llama-server` runtime is missing from `GET /v1/runtimes`.
- `OCR_BACKEND_WORKER_PATH = "paddleocr_vl"` (`page_routing.py:46,57`) is the default producer for a worker page, but the page unit always passes a producer (`ocr_routing.py:280`), so the constant looks unreached.
- Files near the 500-line ceiling (`tests/test_file_size_ceiling.py:17,32`): `core/settings.py` 499, `config/settings_file.py` 499, `capabilities.py` 499, `core/ingestion/source_state.py` 498, `compose.py` 494, `page_routing.py` 480, `config/__init__.py` 469, `ocr_routing.py` 463.

**Observed in the data:** Experiment 46 report (Indra passes G1 to G4 for Arabic and Devanagari, cut 0.90; Bengali median recall 0.59 fails G1) and `evidence/ordered-list-simulation.md` (output script correct on 229 of 229 pages; the list `[indra keeps arabic, devanagari; pp-ocrv6-small]` keeps 58 Arabic and Devanagari pages with 0 bad and leaves Latin and Bengali as today).

## Goals / Non-Goals

**Goals:**

- A new PDF reader, local OCR backend or page rule needs its own file, one descriptor entry and one `register()` line, plus its tests and, if it has new dependencies, its extra.
- Each part can be diagnosed alone: installed, model present, on or off, switched off at run time, external or built-in, broken and why.
- Current users see no change: every existing digest pin and every new pin stays byte-identical.
- Indra ships as the proof, not in the default list.

**Non-Goals:**

- No generated web or OpenAPI lists. Drift tests pin them.
- No migration of the nine `core/` registries (chunking, retrieval, sparse retrieval, metadata, embeddings, LLM, community, document backends, vector stores). They adopt the helper in later changes.
- No change to OCR engines. They already plug in through the worker entry point (ADR-072).
- No Bengali backend, no pre-OCR script chooser, no default change.

## Decisions

### D1. Scope of "reading part"

Three kinds: `pdf_reader`, `local_ocr_backend`, `page_rule`. OCR engines are not reading parts in this change. They live out of process and the worker already discovers them. The guide (task 8.1) explains how to add one and links `ocr-workers/README.md`.

### D2. The part descriptor is pure data in `core/reading_parts.py`

One frozen dataclass per kind, built on one common base. The module imports only the standard library, like `core/reading_lists.py`. A test reads its syntax tree and fails on any `omrs` import.

Common fields: `name`, `kind`, `import_path` (`"module:attr"`), `label`, `help_key`, `extra` (or `None`), `probe_module` (or `None`), `settings` (a tuple of `SettingField(name, env, default, accepted, enters_identity)`), `options` (a tuple of `SettingField` for parts that have no flat keys, see D12), `identity` (an `IdentitySpec` that names the block, the keys and when the block is present), `version` (an integer the part bumps when its output changes), `health` (model files, cache folder, licence note), `source` (`"built-in"` or a distribution name).

Kind fields:

- `PdfReaderDescriptor`: `text_format`, `page_provenance`, `output_revision` (today on the integration `register()` line).
- `LocalOcrBackendDescriptor`: `min_confidence`, `calibrated_by` (experiment folder), `keeps_scripts` (a frozenset of lower-case Unicode script names, or `None` for no script filter), `producer` (the `ocr_backend` value of pages it keeps), `model` (expected `name@revision`).
- `PageRuleDescriptor`: `order` (integer, unique), `drops_pages`, `sends_direct`, `has_post_check`, `has_degrade`.

Who imports it: `config/` (accepted names, defaults, derived key lists), `core/ingestion/` and `core/pipelines/` (identity builders, Read-step keys), `compose*.py` (discovery, validation), `transports/` (health, catalogue). Not `integrations/` (contract `integrations-are-leaves`) and not `core/settings.py` (contract `settings-models-are-pure-data`).

### D3. The integration side keeps lazy `register()` lines, pinned to the descriptors

Integration code cannot import `core`. Each page-reading registry keeps one lazy `register()` line per part on the shared helper (D4). The line carries the name, the import path and the facts that integration code reads at call time: for a backend the cut, `calibrated_by`, `keeps_scripts` and `producer`; for a rule its order; for a PDF reader its three facts as today. A pin test (`tests/unit/test_reading_parts_pins.py`) asserts, for every built-in, that the descriptor and the registration agree on every shared field. This is the precedent at `tests/unit/test_document_reading_rules.py:54-55`.

So a new built-in part touches its own file, one descriptor entry and one `register()` line. The pin test fails when one of the two lines is missing.

Alternative considered: one PERMANENT pure-data ignore edge per importing integration module (`omrs.integrations.pdf.<module> -> omrs.core.reading_parts`), so that integration registries read the descriptors and the `register()` line disappears. Not chosen: it needs three new edges in a contract whose comment warns that each ignore hides every chain from that module (`pyproject.toml:680-688`), and the pin-test precedent already works. Open question 1 asks the operator.

### D4. A shared registry helper, `integrations/part_registry.py`

`PartRegistry(kind)` offers `register(name, import_path, *, probe_module=None, **facts)`, `describe(name)`, `names()`, `get(name)` (imports on first call, caches the object), `installed(name)` (probe with `importlib.util.find_spec`, no import), `switch_off(name, reason)`, `off_reason(name)`, `add_external(...)` (D11) and `broken()` (D11). It imports no part at module level, so `tests/test_no_module_level_strategy_imports.py` keeps passing.

This change moves only the PDF reader registry onto it and builds the local OCR backend and page rule registries on it. The nine `core/` registries adopt it later. `core` may import `integrations` (no contract forbids it; `core/ingestion/ocr_identity.py` already does), so their later move needs no contract edit.

### D5. The page-rule interface

A rule receives a `RuleContext` and returns a `RuleOutcome`.

- `RuleContext`: `file`, `evidence` (the page scan), `flagged` (pages that need OCR), `routed` (flagged pages that earlier rules did not drop), `settings`, `routes` (OCR engine availability).
- `RuleOutcome`: `drop` (pages that leave the route, keep native text and count blank), `direct` (pages sent to the OCR engine without the local tier), `state` (anything the rule needs later for stamping or degrade).

Optional hooks, each declared by a flag on the descriptor:

- `post_check(ctx, outcome) -> Callable[[str, BackendFacts], str | None] | None`: a check the shared escalation rule runs on each local result. It returns an escalation reason or `None`.
- `degrade(ctx, outcome, unread) -> list[int]`: pages the rule sent direct that no engine read and that must go to the local tier instead.
- `stamp(metadata, ctx, outcome, escalated) -> None`: writes the rule's diagnostic count.

The pipeline (`integrations/pdf/page_rules/pipeline.py`) runs the rules in `order` and applies four fixed semantics that reproduce today:

1. A page dropped by an earlier rule leaves the `routed` set of every later rule.
2. A rule's `direct` set is reduced by the pages earlier rules dropped. (Maths detects on all pages, then loses blank pages.)
3. `direct` is the union of every rule's reduced `direct` set. The local tier reads `routed - direct`. This is `split_page_routes` today.
4. `degrade` gets only pages for which this rule is the first claimant in `direct`. (Non-Latin degrades `script_direct - active_maths`, `ocr_routing.py:258-270`.)

`post_check` callables run inside the shared escalation rule in rule order. Their reasons keep today's names.

### D6. The three built-in rules

| Rule | Order | Setting | Hooks | File |
| --- | ---: | --- | --- | --- |
| `blank` | 10 | none | drop | `integrations/pdf/page_rules/blank.py`, calling `blank_pages.find_blank_pages` |
| `maths` | 20 | `ocr_maths_routing_enabled` | direct, stamp | `integrations/pdf/page_rules/maths.py`, calling `maths_routing.detect_maths_pages` |
| `non_latin` | 30 | `ocr_non_latin_routing` | direct, post-check, degrade, stamp | `integrations/pdf/page_rules/non_latin.py`, calling `script_routing` |

Routers (change `document-reading-routers`) take order 40. Each rule calls its detector through the detector's module at call time, so a test that patches the detector module attribute takes effect (D17).

Failure: a built-in rule that raises behaves as today (the exception reaches the existing handling). An external rule that raises is skipped for that file with one warning, and the registry marks it broken with the reason (D11).

### D7. The local OCR backend contract

```python
class LocalOcrBackend(Protocol):
    def read_pages(self, file: Path, pages: list[int], *, settings: Any) -> list[BackendPage]: ...
    def identity(self, settings: Any) -> str | None: ...


@dataclass(frozen=True)
class BackendPage:
    page: int  # 1-based
    text: str
    confidence: float | None  # one number in [0, 1], or None
    model: str | None  # "name@revision"
    hosted_recommended: bool = False
```

`read_pages` raises on a runtime failure. A page it does not return counts as missing. A backend never decides escalation. A backend that reports confidence per line gives the page confidence as the mean of line confidences weighted by character count (the rule Experiment 46 used, task 0.2). `pp_ocrv6_small.py` imports `pdf_inspector` inside `read_pages`, because `tests/unit/test_local_ocr_tier.py:70-77` stubs `sys.modules["pdf_inspector"]`.

### D8. The ordered local list

Setting `ocr_local_backends` (env `OCR_LOCAL_BACKENDS`), a `NameList` like `ocr_engines` and `pdf_readers` (`config/reading_lists.py`). Default `("pp-ocrv6-small",)`, taken from the descriptor table. An unknown name, or a backend without a calibrated cut, stops start-up with a message naming the accepted values.

The chain (`integrations/pdf/local_ocr/chain.py`), called by `page_routing.local_ocr` (the name stays, D17):

1. Backend 1 reads every page the local tier must read, in one call.
2. The shared escalation rule runs on each result with this backend's effective cut (D9): `missing_page`, `empty_text`, `low_confidence`, `hosted_recommended`, then each rule post-check (`non_latin_output`, subject to D10).
3. When the backend declares `keeps_scripts`, the output script is classified (D10). A page whose output script is not in the set, or gets no verdict, gets the reason `script_not_kept`.
4. A page with no reason is kept. Its producer is the backend's `producer`.
5. Every other page passes to the next backend in one call. The last backend's reasons are the page's escalation reasons, and the page goes to the OCR engine list as today.
6. When an escalated page is not resolved (no engine, empty engine text), it keeps the text of the first backend in list order that returned non-empty text. Experiment 46 supports this order: Indra reads Arabic, Bengali and Latin old print and handwriting better than PP-OCRv6.
7. A listed backend that is not installed is skipped with one warning per process. A backend that raises a non-`Exception` panic is switched off for the process (today's `_LOCAL_TIER_BROKEN` rule, now per backend). The tier counts as unavailable only when every listed backend is skipped or off. Then today's missing-runtime rule applies.

With the default list, steps 3, 5 and 6 do nothing new, so the outcome is today's.

Settings › Document reading and the Read document step edit the list like the PDF reader list (task 6.4). The key joins `_ADDED_PARAMS` (`core/ingestion/graph_fingerprint.py:59`), so saved graph fingerprints do not move.

### D9. The cut belongs to the backend; the setting becomes an optional override

`ocr_local_min_confidence` becomes `float | None`, default `None` (the retype deferred in protocol section 9 lands here, because a second cut now exists). The effective cut of a backend is the override when set, else its registered cut. The override applies to every listed backend. Registration with a cut and no `calibrated_by` raises `ValueError`. A backend registered without a cut cannot be listed. `pp-ocrv6-small` keeps 0.9 (`39-local-tier-escalation-2026-09-30`). Indra registers 0.90 (`46-local-ocr-backends-2026-11-04`).

Places that read the field: `config/__init__.py`, `core/settings.py`, `compose_settings.py`, `core/ingestion/ocr_identity.py`, `page_routing.py`. `omrs config init` and `omrs config show` print an unset value as unset, never as `null`.

Identity (`core/ingestion/ocr_identity.py:85-98`): with the default list, `local_tier` stays `{"min_confidence": <effective cut>}` plus `model` once resolved, byte for byte as today. With any other list it becomes `{"backends": [{"name", "min_confidence", "model", "keeps_scripts"}, ...], "output_script_version": 1}`, in list order. The identity schema number does not advance, because no default payload changes.

### D10. Output script, kept scripts and `ocr_non_latin_routing=detect`

A new function `script_routing.output_script(text) -> str | None` returns the lower-case Unicode script name (first word of the letter's Unicode name) when the text holds at least 40 letters and one script holds at least half of them, else `None`. These are the floor and share of the shipped detector and of the simulation. It has its own constant `OUTPUT_SCRIPT_VERSION = 1`. `is_non_latin` and `SCRIPT_DETECTOR_VERSION` do not change, so `detect` and `always` digests do not move.

Under `detect`, the `non_latin_output` post-check does not fire when the backend's `keeps_scripts` contains the page's output script. `pp-ocrv6-small` declares `keeps_scripts = None`, so its non-Latin output still escalates exactly as today. Indra's Arabic or Devanagari output at or above its cut is kept. Its Bengali output gets `script_not_kept` and passes on.

`always` and the pre-local `detect` check are unchanged. They send pages direct before any local backend reads them, Indra included. The guide states this: with Indra listed, use `off` or `detect`.

### D11. Entry-point discovery

Groups: `omrs.pdf_readers`, `omrs.local_ocr_backends`, `omrs.page_rules`. An entry point names a descriptor object (`package.module:DESCRIPTOR`). Discovery loads the descriptor only, never the implementation. The implementation loads on first use through `import_path`.

Rules:

1. Discovery runs once per process, in compose, before `get_settings()`. Importing `config` never runs it. The logic lives in `integrations/part_registry.py`; `compose_settings.py` calls it; `compose.py` gets one call line.
2. A descriptor that is not the right type for its group, or whose name clashes with a built-in, is refused with one warning.
3. A part that fails to load is skipped with one warning and listed as broken with the reason. Start-up never fails because of an external part.
4. Compose passes the discovered names to `get_settings()`, so the list settings accept them. With nothing discovered, the accepted set and every message equal today's.
5. A discovered part does nothing until the operator names it: in a list setting (readers, backends), or by `enabled: true` in its part options (rules, D12).
6. Discovered parts appear in health (D14) and in one start-up log line.

Tests use a fake distribution: a temporary `dist-info` folder with `entry_points.txt` on `sys.path`. No real package is installed.

### D12. Part options for parts without flat keys

Built-in parts keep their flat keys (`ocr_maths_routing_enabled`, `ocr_non_latin_routing`, `ocr_local_*`), so names, env vars and saved Studio fingerprints do not move. A part with no flat key declares `options` in its descriptor. Their values live in one map, `reading_part_options` (`omrs.jsonc` key; env `READING_PART_OPTIONS` as JSON), keyed by part name. Compose validates each entry against the descriptor (type, accepted values, default) and refuses unknown parts or keys. Options marked `enters_identity` enter the identity. An empty map adds nothing, so digests do not move. Every page rule that is not built-in has an implicit `enabled` option, default `false`.

### D13. Legacy engine keys stay as input aliases

`ocr_engine_primary` and `ocr_engine_fallback` stay readable (`config/rules.py:108`; retiring them would move saved Studio graph fingerprints, `tests/unit/test_read_step_lists.py:36-39,152`). Their one internal reader goes: `compose_runtimes._ocr_runtimes` loops over `engine_list(settings)` and labels `used_by` from `ocr_engines`; `OCR_ROUTE_SETTINGS` is deleted. This fixes the missing third-engine runtime (likelihood 2, impact 3, score 6). `OCR_BACKEND_WORKER_PATH` and its `_SOURCE_BACKENDS` entry are deleted only after a test proves every worker page carries a producer.

### D14. Diagnosis from descriptors

New module `transports/api/reading_parts_health.py` (not `capabilities.py`, which is at 499 lines). It builds rows from descriptors and registries:

- Local tier: one entry per listed backend, in order, with installed (probe), model present (descriptor health facts), switched off at run time with the reason, and the effective cut.
- Page rules: one entry per rule with on or off (from settings or options), version and source.
- Discovered parts: name, kind, distribution and version, and broken with the reason.

`runtime_components.py` stops hand-coding the PP-OCRv6 file names and reads them from the descriptor. The Integrations page shows the rows. A page kept by a backend names that backend's `producer` in its metadata; `ocr_backend` becomes `mixed` when two local backends produced text (`page_routing.py:439-447`).

### D15. Single source for hand-typed lists

Derived from descriptors where contracts allow: `PDF_READER_NAMES` and `DOCUMENT_READING_KEYS` (`config/rules.py:95,139-146`), `READ_OCR_KEYS` (`graph_adapters_catalogue.py:128-136`), `_READ_STEP_OCR_KEYS` (`core/pipelines/levers.py:87-95`), the rule metadata keys (`embed_exclusions.py:38,41,62`), the identity builders (`ocr_identity.py:85-98,187-215`, `reader_identity.py:37-43`, `source_state.py:193`), and the extras catalogue rows for reading parts (`transports/api/integrations_catalogue.py:142-153`). Each derived value equals the literal pinned in group 1. Copies that cannot import Python get one drift test each: the `openapi.yaml` enums (`:5311`, `:11414-11420`, `:11466`, `:11511-11518`), `web/src/api/settingsDocumentReading.ts:15-25` and `web/src/settings/documentReadingWords.ts:24-33,106`. Generating these copies is out of scope.

### D16. Behaviour pins first

Group 1 adds, on unchanged code:

1. Literal digest pins for non-Latin `detect` and `always`, for a resolved local model (`local_tier.model`), for maths routing off, and for a third engine (audit Q5 gaps 1 to 3).
2. Literal pins of today's key lists (D15).
3. Golden end-to-end snapshots: a committed fixture PDF with one page of each kind (native text, scanned flagged, blank flagged, maths font, Arabic text layer) through `OcrRoutedPdfInspector`. The page scan, blank test, maths detector and script detector run for real. Local OCR and the OCR engine are fakes with fixed outputs. One snapshot per combination: maths on or off, non-Latin `off`, `detect` or `always`, engine available or not, plus local tier missing and local tier panic. Each snapshot holds every page text and every metadata key.

Every later group keeps all existing pins and these new ones byte-identical. A mutation check proves each snapshot fails when one rule is switched off in code.

### D17. Patch targets that move (gotcha 8b)

The audit counts tests that patch module attributes (audit Q5, constraint 1). The plan:

| Today's target | Tests | After this change |
| --- | ---: | --- |
| `ocr_routing.local_ocr` | 6 | stays: `ocr_routing` still calls `page_routing.local_ocr` by that name |
| `page_routing.resolve_local_model_identity` | 1 + 3 string targets | stays as a public name that delegates to the backend; cache key gains the backend name |
| `ocr_routing.find_blank_pages` | 15 | moves to `blank_pages.find_blank_pages` |
| `ocr_routing.detect_maths_pages` | 3 | moves to `maths_routing.detect_maths_pages` |
| `maths_routing.maths_font_pages` | 3 | stays |
| `script_routing.SCRIPT_DETECTOR_VERSION` | 2 | stays |
| `page_routing._LOCAL_TIER_BROKEN` | 4 | moves to the local OCR registry off state (`switch_off`, `off_reason`); `page_routing.local_tier_off_reason()` stays |

`ocr_routing.py` stops importing `find_blank_pages` and `detect_maths_pages`, so a stale patch raises `AttributeError` instead of passing silently.

### D18. File sizes

| File | Lines | Plan |
| --- | ---: | --- |
| `core/settings.py` | 499 | Task 4.1 moves `classification_url` and `provider_secret_values` (module helpers that `EffectiveSettings` does not use) to a new module before any field is added. Callers follow. |
| `capabilities.py` | 499 | No edit. Health code goes in `transports/api/reading_parts_health.py`. |
| `config/settings_file.py` | 499 | No edit expected: editable keys are computed from the model (`config/settings_file_write.py:126-128`). If an edit is needed, split first. |
| `core/ingestion/source_state.py` | 498 | The maths block call is replaced by the derived builder (net zero or fewer lines). No new code. |
| `compose.py` | 494 | One call line for discovery. Logic in `compose_settings.py` (129 lines). |
| `page_routing.py` | 480 | Shrinks: the pdf-inspector call, probe and escalation loop move to `integrations/pdf/local_ocr/`. |
| `ocr_routing.py` | 463 | Shrinks: rule calls and `_local_fallback` move to `page_rules/`. |

Each code task verifies that the files it touches stay at or under 500 lines.

### D19. Indra as one backend

`integrations/pdf/local_ocr/indra.py`, one `register()` line, one descriptor entry, tests, and the extra `local-ocr-indra` (`indra-ocr==1.1.2`; it pulls onnxruntime and opencv-python-headless; no PyTorch). Descriptor: cut 0.90, `calibrated_by = "46-local-ocr-backends-2026-11-04"`, `keeps_scripts = {"arabic", "devanagari"}`, `producer = "indra_ocr"`, model `datalab-to/indra-ocr@bd02167fdf2005a19962cc15188f8496a2c87d3b` (tag v1.1.0), weights tree hash `1a9ef1fc65c0546f63b89eed936e524077ba94dcd1d7689de89265b158b9324f`, offline use through `INDRA_OCR_MODEL_DIR`, licence note (code Apache-2.0 on PyPI; weights under a modified OpenRAIL-M licence, read by the operator on 2026-11-04). Not in the default list. The operator approves the extra before `pyproject.toml` and `uv.lock` change (AGENTS.md "Ask" boundary). The new extra also needs its `floors-scope` entry in `.github/workflows/ci.yml` (gotcha 13).

The one-file check (`tests/unit/test_indra_is_one_part.py`): the text `indra` (any case) appears in `src/omrs/` and `web/src/` only in `local_ocr/indra.py`, its `register()` line, its descriptor entry and the derived catalogue output. The PR lists `git diff --stat` of the Indra commit, which may touch only those files, `pyproject.toml`, `uv.lock`, the CI floors list, the docs inventory rows that doc tests require, and tests.

## Alternatives

- **The stevedore library.** Rejected: it adds a core dependency for about 30 lines of `importlib.metadata.entry_points` code, and the worker already uses the standard library form.
- **A new top-level package for parts (for example `omrs/parts/`).** Rejected: it fails `tests/unit/test_verification_gaps_boundaries.py:70`, which pins the top-level modules.
- **Per-rule settings wired by hand, as today.** Rejected: each rule touched 15 to 21 production files (audit headline), and an external rule could not add a field at all. Built-ins keep their flat keys; new parts use descriptor options (D12).
- **A user-facing ordered rule list setting.** Rejected: rule order is a correctness constraint (D5), and a new key would move saved Studio fingerprints.
- **Descriptors inside `integrations/`.** Rejected: `config-is-leaf` forbids `config` from importing `integrations`.
- **Permanent ignore edges instead of pinned `register()` lines.** Not chosen (D3); open question 1.
- **One global cut for every backend.** Rejected: a cut belongs to a confidence scale (Experiments 39 and 46).
- **A script chooser before OCR.** Rejected: scans give no script verdict before OCR (Experiment 45). The output script after OCR is correct on 229 of 229 pages.

## Risks / Trade-offs

- [Patch targets move] Three targets move (D17). Mitigation: stale patches fail loudly; task 1.1 lists every test first.
- [Golden snapshots are brittle] A deliberate later change must update them. Mitigation: snapshots are JSON with sorted keys, and a failing snapshot prints the first differing key.
- [One override for two scales] `ocr_local_min_confidence` replaces the cut of every listed backend. Mitigation: the guide says so; health shows each effective cut. Open question 2.
- [Indra evidence is thin] Arabic recall 0.75 against a gate of 0.70; one Devanagari and two Arabic documents; vision-model reference. Mitigation: Indra stays out of the default list; a live check on operator approval (task 7.5).
- [`always` skips Indra] An operator who lists Indra and sets `always` gets no Indra reads. Mitigation: documented (D10).
- [External parts are code] Discovery imports descriptor modules from installed packages. Mitigation: only the operator installs packages; a discovered part acts only when named (D11 rule 5); health names its distribution.
- [The descriptor type becomes a contract] External packages import `omrs.core.reading_parts`. Mitigation: ADR-112 records it; the guide marks the fields stable; a field change needs a version note.
- [ADR-110 overlap] Routers are the next rule. Mitigation: task 8.6 amends `document-reading-routers` design item 0 at apply time.
- [onnxruntime conflict] Indra pulls onnxruntime, which the base install already has. Mitigation: the floors job runs the extra (gotcha 13); task 7.1 checks the lock resolves to one version.

## Migration Plan

No data migration. Default installs keep every digest. An operator who lists Indra re-indexes PDF sources once. Rollback: revert the merge; the default list needs no setting.

## Operator Decisions (2026-11-04)

Earlier, kept: Experiment 46 ran first (it passed); G3 Latin margin -0.02 (strata -0.05); the operator read the full Indra licence before arm B; RapidOCR and Tesseract arms were dropped.

New, recorded and not reopened:

1. Page reading becomes plug-and-play, done once in this change.
2. The term is "reading part" and "part descriptor", not "plugin".
3. Descriptors are pure data in `core/` (D2, D3).
4. One shared registry helper, page-reading registries only (D4).
5. Blank, maths and non-Latin become ordered page rules on one hook; routers are next (D5, D6).
6. An ordered local OCR list with per-backend cut and kept scripts; the cut setting becomes an override (D8 to D10).
7. Indra is the proof, behind an approved extra, not in the default list (D19).
8. Entry-point discovery with the standard library, prepared now (D11).
9. Legacy engine keys stay as aliases; their internal reader goes (D13).
10. Health comes from descriptors (D14).
11. Python lists derive from descriptors; other copies get drift tests (D15).
12. Pins and golden snapshots come before any refactor (D16).
13. Files stay under 500 lines with planned splits (D18).
14. Docs and ADR-112 are tasks (group 8).
15. Group order 0 to 9, tests first (tasks.md).

## Settled Questions (2026-11-04, decided by the orchestrator on the operator's instruction to settle once)

The operator asked for these to be settled once and not reopened. The operator's approval of this proposal confirms them.

1. **D3: two pinned lines per part.** A part keeps a descriptor entry and a lazy `register()` line, and a test pins the two. Reason: permanent ignore edges hide every import chain from the module they cover (`pyproject.toml:680-688`), which weakens the leaf contracts for every later part. A pin test fails loudly and costs one line. The one-file check (task 7.x) counts the descriptor entry and the `register()` line as the part's own lines.
2. **D9: the override applies to every listed backend.** Reason: one number with one meaning. An operator who sets `ocr_local_min_confidence` asks for that cut everywhere. A per-backend override, if ever needed, goes into `reading_part_options` (D12), not into this key.
3. **D19: exact pin `indra-ocr==1.1.2`.** Reason: Indra is new (v1.0 in October 2026) and its weights revision is pinned by hash; the cut 0.90 was measured on 1.1.2 only. A version change needs a re-run of the Experiment 46 gates. Precedent for an exact pin of a fixed release: `magika==1.0.3` (`pyproject.toml:88`). The floors test treats an exact pin as floor equals lock.

## Open Questions

None.
