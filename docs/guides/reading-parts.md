# Reading parts

This guide explains what a reading part is and shows contributors how to add a PDF reader, a local OCR backend, a page rule or an OCR engine.

## The short version

- A reading part is one replaceable piece of PDF page reading. It is a PDF reader, a local OCR backend or a page rule.
- Each part has a part descriptor: a frozen data record in `src/omrs/core/reading_parts.py`.
- Each built-in part also has one lazy `register()` line in its integration registry. A pin test compares the descriptor and the line.
- An installed package can add a part through an entry point. The part does nothing until the operator names it in a setting.
- OCR engines are not reading parts. They run out of process. [Add an OCR engine](#add-an-ocr-engine) links their guide.

## What a reading part is

OMRS reads a PDF in stages. A PDF reader extracts the text of each page. A page rule decides which pages skip OCR or go straight to an OCR engine. A local OCR backend reads the flagged pages on the machine before an OCR engine is asked.

| Kind | Descriptor class | Built-in parts | Setting that names the parts |
| --- | --- | --- | --- |
| PDF reader | `PdfReaderDescriptor` | `liteparse`, `pdf_inspector`, `pypdfium2`, `pypdf` | `pdf_readers` |
| Local OCR backend | `LocalOcrBackendDescriptor` | `pp-ocrv6-small`, `indra` | `ocr_local_backends` |
| Page rule | `PageRuleDescriptor` | `blank` (order 10), `maths` (order 20), `non_latin` (order 30), `document_router` (order 40) | Each rule has its own setting |

The default `ocr_local_backends` list holds the first backend of the table, `pp-ocrv6-small`. `indra` needs the `local-ocr-indra` extra and stays out of the default list.

This guide uses two words with fixed meanings:

- **Reading part**: a PDF reader, a local OCR backend or a page rule.
- **Part descriptor**: the data record that describes one reading part.

## The part descriptor

`src/omrs/core/reading_parts.py` holds the descriptors. The module imports only the standard library, so `config/`, `core/ingestion/`, the composition root and the transports can read a part's facts without importing the part. A test reads the module's syntax tree and fails on any `omrs` import.

Every descriptor has these fields:

| Field | Meaning |
| --- | --- |
| `name` | Part name. Unique within its kind. |
| `kind` | `pdf_reader`, `local_ocr_backend` or `page_rule`. The subclass sets it. |
| `import_path` | `module:attr` of the implementation. OMRS imports it on first use. |
| `label` | Short name for the user interface. |
| `help_key` | Key of the help text. |
| `extra` | Optional-dependency group that installs the part, or `None` for a part in the base install. |
| `probe_module` | Top-level module that the installed check looks for without importing it. |
| `settings` | Flat settings that the part reads, each a `SettingField` with a name, an environment variable, a default, optional accepted values and an `enters_identity` flag. |
| `options` | Settings of a part that has no flat keys. See [Part options](#part-options). |
| `identity` | Where the part adds to the index identity: the block, the keys and when the block is present. `None` when it adds nothing. |
| `version` | Integer that the part raises when its output changes. |
| `health` | Model file names, cache folder and licence note for health checks. |
| `source` | `built-in`, or the name of the distribution that adds the part. |

Each kind adds fields:

| Kind | Added fields |
| --- | --- |
| PDF reader | `text_format` (`plain` or `markdown`), `page_provenance` (true when each document carries its page number), `output_revision` (a change re-ingests PDF sources) |
| Local OCR backend | `min_confidence` (the escalation cut), `calibrated_by` (the experiment folder that measured the cut), `keeps_scripts` (script names the backend may keep, or `None`), `producer` (the `ocr_backend` value of kept pages), `model` (`name@revision`) |
| Page rule | `order` (unique among page rules), `drops_pages`, `sends_direct`, `has_post_check`, `has_degrade`, `adds_pages` |

The descriptor classes refuse two mistakes when the module loads:

- A local OCR backend with a cut and no `calibrated_by` experiment.
- A table with a repeated name within a kind, or a repeated page rule `order`.

A backend with no cut cannot be listed in `ocr_local_backends`.

### The register line

Integration code cannot import `core/reading_parts.py`. Each built-in part therefore has a second record: a lazy `register()` line in the registry of its kind. Importing a registry imports no part.

| Kind | Registry module |
| --- | --- |
| PDF reader | `src/omrs/integrations/pdf/registry.py` |
| Local OCR backend | `src/omrs/integrations/pdf/local_ocr/registry.py` |
| Page rule | `src/omrs/integrations/pdf/page_rules/registry.py` |

The three registries share one helper, `PartRegistry`, in `src/omrs/integrations/part_registry.py`. It stores the import string and the declared facts, imports the part on first use, probes for the dependency without importing it, and records a per-process switch-off reason. `tests/unit/test_reading_parts_pins.py` fails when a descriptor has no line, a line has no descriptor, or a shared fact differs.

### What a part must do

A PDF reader has a `load_data(file, *args, **kwargs)` method that returns a list of documents.

A local OCR backend is an object with two methods. It reads pages and reports what it read. It never decides escalation. The shared rule in `src/omrs/integrations/pdf/local_ocr/chain.py` decides, with the backend's cut.

- `read_pages(file, pages, *, settings)` returns one `BackendPage` per page: page number, text, confidence between 0 and 1 (or `None`), model identity and a hosted-engine hint.
- `identity(settings)` returns the model identity as `name@revision`, or `None`.

A page rule is an object with `run(ctx)`. It returns a `RuleOutcome`: pages to drop (`drop`), pages to send direct to the OCR engine list (`direct`), pages to add to the OCR route (`add`), and optional state. Three optional hooks exist. The registration declares them with `has_post_check` and `has_degrade`; `stamp` runs when the rule has one.

- `post_check(ctx, outcome)` returns a check that the shared escalation rule runs on each local OCR result.
- `degrade(ctx, outcome, unread)` returns the pages the local tier must read when no engine read a page that this rule sent direct.
- `stamp(metadata, ctx, outcome, escalated)` writes the rule's diagnostic count.

The context `ctx` holds the file, the page scan (`evidence`), the flagged pages, the routed pages, the settings and the OCR engine routes. It also holds two fields for rules that add pages:

- `claimed`: the pages that earlier rules dropped, sent direct or added. A rule that adds pages skips them.
- `judge`: the page judge of the selected document router, or `None`. Only the router reads it.

`drop` and `direct` can name only routed pages, which are flagged pages. `add` can name unflagged pages. Only a rule whose registration declares `adds_pages` can return `add`. A valid added page is in the page scan, has non-blank text, is not flagged and is not in `claimed`. Any other added page is a bad outcome: a built-in rule fails the file, and a discovered rule is skipped with one warning and switched off.

The page rule pipeline in `src/omrs/integrations/pdf/page_rules/pipeline.py` runs the rules in ascending `order` with four fixed semantics:

1. A page dropped by an earlier rule leaves the routed set of every later rule.
2. A rule's direct set loses the pages that earlier rules dropped.
3. The direct pages are the union of every rule's reduced direct set and added pages, minus every dropped page. A page that two rules name goes to the OCR engine list once. The local tier reads the routed pages that are not direct. `pages_needing_ocr` stays the count of flagged pages.
4. A rule's `degrade` hook sees only the pages that the rule was first to send direct.

The local backend list runs in list order. The first backend that can run reads every page. A page that the backend does not keep passes to the next backend. A page with no escalation reason is kept and carries the backend's `producer`. A backend that declares `keeps_scripts` does not keep a page whose output script is outside that set (reason `script_not_kept`).

## The document router

The document router is the fourth built-in page rule, `document_router`, at order 40. It runs after the blank, maths and non-Latin rules. It declares `adds_pages` and `has_degrade`.

A router asks a decision model, one page at a time, whether the native text of a page can stay. The setting `document_router` (environment `DOCUMENT_ROUTER`) names one entry of the `document_routers` map in `omrs.jsonc`. An empty value means no router. This is the default. The composition root builds the page judge from the router entry and its decision model entry, and the page unit puts it on `ctx.judge`.

The router judges each page that has non-blank native text, that the scan did not flag and that is not in `claimed`. It does not judge a flagged page, because a flagged page already goes to OCR. It does not judge OCR output. It sends the page text, cut to the router's character limit, and the page image when the router sees images. A page with P(yes) below the router threshold goes to the OCR engine list in `add`.

Cost: the router judges every unflagged text page that no earlier rule claimed. That is about 3.6 s per judged page with the local model. In Experiment 43, about 2.7% of healthy pages (15 of 565) went to OCR by mistake. No setting changes which pages the router judges.

Worked example. A 20-page PDF has page 2 flagged, and its blank test drops nothing. A router with threshold 0.17 is selected.

1. The blank, maths and non-Latin rules run. Page 2 is routed. No rule claims another page.
2. The router judges pages 1 and 3 to 20, one request at a time. It skips page 2, because page 2 is flagged.
3. Page 7 gets P(yes) 0.05. That is below 0.17, so the router returns `add = {7}`. The other 18 pages keep their native text.
4. The page unit sends pages 2 and 7 to the OCR engine list in one page-listed request. When no engine is available, the router's `degrade` hook sends page 7 to the local tier, with one warning.
5. The document carries `router_pages_judged: 19`, `router_pages_accepted: 18`, `router_pages_rejected: 1`, `router_pages_unjudged: 0` and `router_status: "ok"`. `pages_needing_ocr` stays 1.

When the router cannot run, the rule returns an empty outcome and reads no page. Reading behaves as with no router, and `router_status` holds the reason: `unknown-model`, `unreachable`, `quantisation-refused`, `projector-not-loaded`, `wrong-build`, `renderer-missing`, `needs-opt-in`, `request-failed` or `malformed-reply`. A single failed request keeps the page's native text and counts it in `router_pages_unjudged`. After 3 failed requests in a row, the rule stops asking for that file. The pages left keep their text and count as unjudged. When no page was judged, `router_status` is `unreachable`. With no router, the rule stamps no key. The five keys are diagnostics: they never reach the embedding text and do not enter the index identity key list.

With a router selected, the `parser` block of a PDF source holds a `document_router` entry: the question, threshold, image flag, character limit, the decision model kind and model identity, the rule version and `runnable`. `runnable` is true only when the router can judge pages now: OCR routing wraps the PDF reader, the decision model check passed, and an image router has a renderer. A source read while the router could not run is read again on the next explicit ingest after the router can run. This includes a router that fails during the read: the source is stored with `runnable` false when its `router_status` is not `ok`. The router name, address, key and opt-in stay out, so a rename does not re-ingest. A change to the threshold re-ingests PDF sources on the next explicit ingest.

## Part options

A part without flat settings reads its options from `reading_part_options`. The environment form is `READING_PART_OPTIONS`, a JSON map keyed by part name. In `omrs.jsonc` it is an object.

```jsonc
{
  "reading_part_options": {
    "my_rule": { "enabled": true }
  }
}
```

Start-up checks every entry against the descriptor. The key must name a built-in or discovered part. Each option must appear in the descriptor's `options`, with a value of the declared type and an accepted value. Every page rule also takes `enabled`. A built-in rule ignores it. A discovered rule runs only when `enabled` is `true`.

Options marked `enters_identity` change the PDF source identity, but only for a part in use: a listed reader or backend, or a discovered rule with `enabled` true. An empty map adds nothing, so a default install keeps every digest.

## Health

`GET /v1/integrations` returns a `reading_parts` block. The Integrations page shows it. Every check only reads: no check imports a part, downloads a file or starts a process.

| Section | One row per | Facts |
| --- | --- | --- |
| `local_ocr_backends` | Backend in `ocr_local_backends`, in list order | Installed, model files present, switched off and why, effective cut |
| `page_rules` | Registered page rule, in rule order | Enabled, version, source |
| `discovered_parts` | Entry point that discovery found | Name, kind, distribution, version, problem |

The effective cut is the backend's own `min_confidence`. When the operator sets `ocr_local_min_confidence`, that value replaces the cut of every listed backend.

A section whose check raises is an empty list. The detail goes to the log. Rows come from the descriptors, so a new part appears with no edit to the health code.

Settings > Document reading and the Studio Read document step edit `ocr_local_backends` the same way they edit the PDF reader list.

## Entry-point groups and failure rules

An installed package adds a reading part through one of three entry-point groups. The value names a descriptor object, not the implementation.

| Group | Part kind |
| --- | --- |
| `omrs.pdf_readers` | PDF reader |
| `omrs.local_ocr_backends` | Local OCR backend |
| `omrs.page_rules` | Page rule |

Discovery runs once per process in the composition root (`compose_settings.discover_reading_parts()`), before `Settings` resolves. Importing `config/` discovers nothing. Discovery loads the descriptor only. The implementation loads on first use through `import_path`.

The following example shows the entry point of a package `omrs-fake-ocr` that adds a local OCR backend. The package would declare this in its own `pyproject.toml`:

```toml
[project.entry-points."omrs.local_ocr_backends"]
fake-ocr = "omrs_fake_ocr.parts:DESCRIPTOR"
```

The module `omrs_fake_ocr/parts.py` holds the descriptor. The name `fake-ocr` is a placeholder:

```python
from omrs.core.reading_parts import LocalOcrBackendDescriptor

DESCRIPTOR = LocalOcrBackendDescriptor(
    name="fake-ocr",
    import_path="omrs_fake_ocr.backend:BACKEND",
    label="Fake OCR",
    help_key="local_ocr_backend.fake-ocr",
    probe_module="omrs_fake_ocr",
    min_confidence=0.8,
    calibrated_by="00-fake-calibration",
    producer="fake_ocr",
)
```

After the operator installs the package, `fake-ocr` is a valid value of `ocr_local_backends`. The entry-point name on the left (`fake-ocr` in the example) is free. The descriptor's `name` is the part name.

Discovery never stops start-up. These rules apply:

| Case | Result |
| --- | --- |
| The entry point fails to import | Skipped. The `discovered_parts` health row shows the problem. |
| The loaded object has the wrong descriptor class | Refused, with one warning. |
| The name belongs to a built-in part of the same kind | Refused, with one warning. The built-in stays. |
| An earlier distribution already took the name | Refused, with one warning. |
| A discovered part is installed but no setting names it | It does nothing. |
| A discovered page rule has no `"enabled": true` option | It does not run. |
| A discovered page rule raises on a file | Skipped for that file, with one warning. The registry switches it off with the reason. |
| A local backend raises on a call | Skipped for that call, with one warning per process when another backend reads. |
| A built-in page rule raises | The file fails. |

## How reading parts differ from plugins

The word "plugin" has one meaning in this repository. ADR-075 defines a plugin as a user-registered external executable with a hashed manifest. The operator registers and enables it as an explicit trust decision. The marimo notebook plugin is the shipped example. The workspace database records plugin registrations, and `GET /v1/plugins` lists them.

A reading part differs in four ways:

- It is Python code that runs inside the OMRS process, not a separate executable.
- A descriptor object describes it. No manifest or hash exists.
- An installed Python package adds it through an entry point. The operator does not register it in the workspace.
- The operator turns it on with a list setting or a part option, not a registration.

[ADR-112](../adr/112-reading-parts-descriptor-pipeline-and-discovery.md) records the decision and keeps the word "plugin" for ADR-075. Do not call a reading part a plugin in code, settings or documents.

## Procedures

Run every command from the repository root. Use British English in docstrings and comments. Keep each file under 500 lines.

### Add a PDF reader

Before you start, decide the reader name, whether it emits `plain` or `markdown`, and whether it knows page numbers.

1. Create `src/omrs/integrations/pdf/<module>.py`.
2. Add a class with `load_data(self, file, *args, **kwargs)`. Return a list of documents.
3. Import the reader's packages inside `load_data`, not at module level.
4. Add a `PdfReaderDescriptor` to `PDF_READERS` in `src/omrs/core/reading_parts.py`.
5. Set `name`, `import_path`, `label`, `help_key`, `probe_module`, `text_format` and `page_provenance`. Set `output_revision` when the output changes.
6. Put the entry where you want the reader in the `PDF_READER_NAMES` order.
7. Add one `register()` line at the end of `src/omrs/integrations/pdf/registry.py` with the same facts.
8. If the reader needs a package outside the base install, get approval for it first.
9. Add an extra under `[project.optional-dependencies]` in `pyproject.toml`. Set `extra=` in the descriptor.
10. Add the extra to the `floors-scope` list in `.github/workflows/ci.yml`. Run `uv lock`.
11. Add a test in `tests/unit/` that runs the reader on a small PDF fixture.
12. Update the literal pins in `tests/unit/test_reading_parts_list_pins.py` and the `ReaderOption` name list in `src/omrs/transports/api/openapi.yaml`.
13. Check: run the command below. Each failure names the copy to change.

```bash
uv run pytest tests/unit/test_reading_parts_pins.py tests/unit/test_reading_parts_list_pins.py tests/unit/test_reading_parts_drift.py -q
```

The command ends with a `passed` line and no `failed` line.

### Add a local OCR backend

Before you start, run an experiment that measures the escalation cut. The descriptor requires the experiment folder name in `calibrated_by`. Use the `s-experiment` skill. Experiment 46 is the model: `experiments/46-local-ocr-backends-2026-11-04/report.md`.

1. Create `src/omrs/integrations/pdf/local_ocr/<module>.py`.
2. Add a class with `read_pages(self, file, pages, *, settings)` and `identity(self, settings)`.
3. Return one `BackendPage` per page. Compute the page confidence with `page_confidence` from `base.py`.
4. Import the backend's packages inside the methods, not at module level.
5. Add a module-level `BACKEND` object.
6. Add a `LocalOcrBackendDescriptor` at the end of `LOCAL_OCR_BACKENDS` in `src/omrs/core/reading_parts.py`. The first entry is the default list, so do not put the new entry first.
7. Set `name`, `import_path`, `label`, `help_key`, `probe_module`, `min_confidence`, `calibrated_by`, `keeps_scripts`, `producer` and `model`.
8. Set `health` to the model file names and the licence note.
9. Add one `register()` line at the end of `src/omrs/integrations/pdf/local_ocr/registry.py` with the same facts.
10. If the backend needs a package, get approval for it first. Add the extra to `pyproject.toml`, set `extra=` in the descriptor, and add it to the `floors-scope` list in `.github/workflows/ci.yml`. Pin the version the cut was measured on. Run `uv lock`.
11. Add a test in `tests/unit/` that stubs the package in `sys.modules` and checks the pages that `read_pages` returns.
12. Copy `tests/unit/test_indra_is_one_part.py` and replace `indra` with your backend name. The copy proves that the name appears in only three places: the backend module, the `register()` line and the descriptor.
13. Check: run the command below. Then run `uv run omrs config show` with `OCR_LOCAL_BACKENDS=pp-ocrv6-small,<name>` set, and read the value of `ocr_local_backends`.

```bash
uv run pytest tests/unit/test_reading_parts_pins.py tests/unit/test_reading_parts_catalogue.py tests/unit/test_<name>_is_one_part.py -q
```

The integrations catalogue row, the health row and the uninstall plan come from the descriptor. They need no edit.

### Add a page rule

Before you start, decide the rule's `order`. No other page rule may use it. Choose which of the five flags the rule needs.

1. Create `src/omrs/integrations/pdf/page_rules/<module>.py`.
2. Add a class with `run(self, ctx)`. Return a `RuleOutcome`.
3. Add the hook methods that the rule needs: `post_check`, `degrade` or `stamp`.
4. Add a module-level `RULE` object.
5. Add a `PageRuleDescriptor` to `PAGE_RULES` in `src/omrs/core/reading_parts.py`.
6. Set `name`, `import_path`, `label`, `help_key`, `order` and the flags `drops_pages`, `sends_direct`, `has_post_check`, `has_degrade` and `adds_pages`.
7. If the rule has a setting, add a `SettingField` to `settings`. Add the field to the `Settings` model in `src/omrs/config/ocr_routes.py` and to `EffectiveSettings` in `src/omrs/core/settings.py`. Pass it in `src/omrs/compose_settings.py`.
8. If the rule changes the index identity, set `identity` and add a builder in `src/omrs/core/ingestion/ocr_identity.py`.
9. If the rule stamps a page count, add the metadata key to `EXCLUDED_EMBED_METADATA_KEYS` in `src/omrs/core/ingestion/embed_exclusions.py`.
10. Add one `register()` line to `src/omrs/integrations/pdf/page_rules/registry.py` with the same order and flags.
11. Add a test in `tests/unit/` for `run` and for each hook.
12. Add the rule's metadata key to `_RULE_METADATA_KEYS` in `tests/unit/test_reading_parts_single_source.py`. That test fails until you do.
13. Check: run the command below.

```bash
uv run pytest tests/unit/test_reading_parts_pins.py tests/unit/test_reading_parts_single_source.py tests/unit/test_page_rule_pipeline.py -q
```

The key lists that name the document-reading settings derive from the descriptors, so they need no edit. Hand-typed copies in `openapi.yaml` and under `web/src/` do. `tests/unit/test_reading_parts_drift.py` names each copy that differs.

A rule in an external package follows steps 1 to 4 and 6 only. Its descriptor goes in the package, and the operator turns it on with `"enabled": true` in `reading_part_options`.

### Add an OCR engine

An OCR engine is not a reading part. It runs as a separate process in its own environment, and OMRS talks to it over JSON Lines. It has no part descriptor and no `register()` line. The engine list is the `ocr_engines` setting.

1. Open [`ocr-workers/README.md`](../../ocr-workers/README.md). Find the section "Add an engine".
2. Follow its steps. They create `engines/<name>/` with a `pyproject.toml`, an `ENGINE` object and a lock file.
3. Provision the engine with `python3 ocr-workers/provision.py <name>`.
4. Add the engine name to `ocr_engines`, for example `OCR_ENGINES=dots-mocr,<name>`.
5. Check: call `GET /v1/runtimes`. The response lists a runtime for every engine in `ocr_engines`, with `used_by` set to `["ocr_engines"]`.

## Troubleshooting

| What you see | Cause and fix |
| --- | --- |
| `descriptor without register():` or `register() without descriptor:` in `test_reading_parts_pins.py` | The descriptor and the `register()` line do not match. Add the missing one, then run the pin test again. |
| `duplicate page rule order 20: 'maths' and 'my_rule'` when OMRS imports | Two page rules share an `order`. Give the new rule an unused order, then import again. |
| `has a cut (0.9) but no calibrated_by experiment` | The backend descriptor has a cut and no experiment. Add `calibrated_by` with the experiment folder name. |
| `A backend with no calibrated confidence cut cannot be listed.` | `ocr_local_backends` names a backend with no cut. Remove it, or measure and set the cut. |
| `Part 'my_rule' has no option 'x'. Its options: ...` | `reading_part_options` has a key the descriptor does not declare. Use a listed key, or add the option to the descriptor. |
| `Reading part ... was refused:` in the log | Discovery refused an entry point. Read the reason after "refused". Fix the descriptor class or rename the part. Restart OMRS. |
| A `discovered_parts` health row with a `problem` | The entry point failed to import. Install the package's dependencies, then restart OMRS. |
| `local OCR backend 'x' could not be imported` | The backend module or one of its packages is missing. Install the extra named in the descriptor. |

## See also

- [ADR-112](../adr/112-reading-parts-descriptor-pipeline-and-discovery.md): the decision and its reasons.
- [Experiment 46](../../experiments/46-local-ocr-backends-2026-11-04/report.md): the evidence for the Indra cut.
- [Architecture](architecture.md): the registry rules and the integration inventory.
- [Ingestion](ingestion.md): OCR routing, page-level routing and the routing identity.
- [Configuration](configuration.md): the settings that name the parts.
- [OCR workers](../../ocr-workers/README.md): provisioning and the engine contract.
