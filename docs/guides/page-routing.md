# Page routing

This guide is for operators who read PDFs with OMRS. It explains how OMRS decides, page by page, which part reads each page, and how to set each step in the Page routing panel.

The Page routing panel is in Settings > Document reading. The Studio Read document step shows the same panel. The panel puts the steps in the order that a page passes through them.

## How a page moves

This diagram shows the path of one PDF page. The numbers match the step numbers in the panel.

```text
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
       maths font? (step 2)         -> straight to [5]
         |
         v
       [3] router (optional): a "no" sends the page to [5]
```

The same path in words:

1. The first installed PDF reader reads the file and gives each page its native text. Native text is the text layer that is already in the PDF.
2. The page scan flags each page whose native text is missing or not usable. A flagged page needs OCR (optical character recognition: reading the text from the page image).
3. The page rules look at the flagged pages in a fixed order. A blank page keeps its native text and costs no OCR. A maths page or a non-Latin page goes straight to the OCR engines.
4. The maths rule also looks at the unflagged pages. An unflagged page with a maths font goes straight to the OCR engines.
5. The router, when you choose one, judges each other unflagged page with text. A "no" sends that page to the OCR engines.
6. The local OCR backends read the flagged pages that no rule claimed. A page that no backend reads well enough goes to the OCR engines.
7. The OCR engines read every page that reaches them.

The panel shows two rows above step 1:

- **OCR fallback.** The master switch. Off means that no page goes to OCR, so steps 2 to 5 have no effect. The panel then shows "OCR fallback is off. No page goes to OCR, so steps 2 to 5 have no effect." You can still edit every row.
- **OCR routing unit.** `page` is the only unit. OCR reads only the flagged pages, never the whole file.

## Defaults

This table shows the value of each row when no source sets it.

| Row | Key | Default |
| --- | --- | --- |
| OCR fallback | `ocr_fallback_enabled` | On |
| OCR routing unit | `ocr_routing_unit` | `page` |
| PDF readers | `pdf_readers` | `pdf_inspector`, `liteparse`, `pypdf` |
| Skip blank pages | `ocr_skip_blank_pages` | On |
| Maths pages | `ocr_maths_routing_enabled` | On |
| Non-Latin pages | `ocr_non_latin_routing` | `off` |
| Router | `document_router` | No router |
| Local OCR backends | `ocr_local_backends` | `pp-ocrv6-small` |
| Confidence cuts | `ocr_local_cuts` | 0.92 for `pp-ocrv6-small`, 0.94 for `indra` |
| OCR engines | `ocr_engines` | `dots-mocr`, `paddleocr-vl` |

Each key, its environment variable and the values it accepts are in [Configuration](configuration.md#document-reading-values).

## Step 1: PDF readers

The PDF readers list sets which reader reads each PDF. The first installed reader in the list reads the file. A later reader runs when the readers above it are not installed or return no text.

To change the order, select the up or down arrow on a reader. To add a reader, choose it in the add control. To remove a reader, select its X. The page refuses an empty list.

### pypdfium2

`pypdfium2` is an optional reader. It is not in the default list. The add control always offers it:

- "pypdfium2 (optional)" when it is installed.
- "pypdfium2 (optional, not installed)" when it is not installed. You cannot add it until it is installed.

OMRS also uses pypdfium2 to draw page images. An image router can use it to draw the page that it sends to its decision model. The dots-mocr engine uses its own copy inside its worker environment. Neither use is a reading step, so neither use needs pypdfium2 in this list.

### Install pypdfium2 from step 1

Prerequisites:

- `omrs web` runs as a uv tool install. On other installs, step 1 shows the reason and a copy command, and no Install button.
- No other install job runs.

Procedure:

1. Open Settings > Document reading.
2. In step 1, select Install under the pypdfium2 choice.
3. Wait until the install job ends. The button stays disabled while the job runs.
4. Restart OMRS. Select "Restart now" in the restart dialog, or restart `omrs web` yourself.
5. In step 1, select Edit and add pypdfium2 to the list.
6. Select Save, then restart OMRS again.

Check: the PDF readers row shows `pypdfium2` in the value in force.

Studio has no Install button. In a Read document step, the not-installed reader is disabled and shows a link to Settings > Document reading. Install it there, then return to Studio.

## Step 2: pages decided by their content

Step 2 holds three page rules. They run in a fixed order. The panel says: "These checks run in a fixed order. Blank pages are checked first."

### Skip blank pages

On: a flagged page with no ink keeps its native text and costs no OCR. The blank test renders each flagged page and looks for ink. On the test machine it took about 0.28 s for each flagged page. An OCR engine took 33 to 51 s for each blank page.

Off: blank pages go to OCR like any flagged page. The blank test then renders no page. Turn it off only for a collection where the blank test is wrong.

The blank test never reads unflagged pages. It has no threshold setting.

### Maths pages

On: a page that uses a maths font goes straight to the OCR engines. It skips the local OCR backends. This applies to flagged and unflagged pages. The test reads the font names of each page. It renders no page and calls no model.

Off: maths pages follow the normal route.

### Non-Latin pages

This choice sends pages in a non-Latin script, for example Arabic or Devanagari, past the local OCR backends.

| Choice | What it does |
| --- | --- |
| `off` | No page goes direct. This is the default. |
| `detect` | A flagged page whose text layer is mostly non-Latin goes straight to the OCR engines. A local OCR result that is mostly non-Latin goes to the OCR engines too. `detect` sees only text that already exists, so it does not catch scanned pages. |
| `always` | Every flagged page goes straight to the OCR engines. Use it for a collection that you know is non-Latin. |

### Why you cannot reorder the rules

Step 2 has no move buttons, for three reasons:

1. Maths and non-Latin both send a page to the OCR engines. A swap cannot change where any page goes.
2. Blank must run first. A later blank rule would see pages that already went to OCR, so blank pages would cost engine time.
3. An order setting would enter the index identity and the tests, and it gives no benefit.

The router also has a fixed place. It runs after the three rules.

## Step 3: pages that look fine

A router asks a decision model, page by page, whether an unflagged page can keep its native text. A "yes" keeps the text. A "no" sends that page alone to the OCR engines. The router judges only unflagged pages with text that no rule claimed.

The step offers "No router" and the names of the routers you defined. To define a router, use the link "Define routers in the Router section". The Router section is below the panel in Settings > Document reading.

Cost: about 3.6 s for each judged page with the local model. The default is "No router", because the router caught only about half of the bad pages on new documents (Experiment 47).

## Step 4: local OCR backends

The local OCR backends read the flagged pages that no rule claimed. They run on this machine. The list order decides which backend reads first.

Each backend has a confidence cut. A backend keeps a page when its confidence is at or above its cut. A page that a backend does not keep goes to the next backend. A page below every cut goes to the OCR engines.

Each listed backend has a cut box beside it. A backend with no cut set uses its default cut.

## Step 5: OCR engines

The OCR engines read the pages that reach them. The first engine reads. A later engine runs only when every engine above it is unavailable before the request starts.

The step shows the OCR engines folder. When `OCR_WORKERS_DIR` is not set, the step says "OCR_WORKERS_DIR is not set, so no OCR engine can run."

## Settings and Studio

The panel looks the same in both places. The values apply in different ways.

| | Settings > Document reading | Studio Read document step |
| --- | --- | --- |
| Where the value goes | `omrs.jsonc` | The pipeline of one user profile |
| What it changes | Every ingest that uses the host settings | Only that pipeline |
| When it applies | After a restart of `omrs web`. The router choice applies to the next request. | On the next run of the pipeline |
| Each row shows | The value in force, its source and the default | "Inherit" or a value for this step |

In Studio, each row offers "Inherit". It uses the value from Settings > Document reading. The choice names that value and its source, for example "Inherit from Settings: On (default)". A step value never changes the Settings value.

A value set in the environment or `.env` locks its Settings row. The row names the variable to remove. A built-in profile (`documents`, `codebase`) is read-only in Studio.

## When documents re-index

Each source has an index identity. It is a digest of the settings that shape its chunks. When a setting change moves the digest, the next ingest reads that source again. A setting change re-indexes nothing by itself.

| Row | Sources that re-index when you change it |
| --- | --- |
| OCR fallback | Every source |
| Maths pages | Every source |
| OCR engines | Every source |
| PDF readers | PDF sources. When the change gives a different first installed reader, every source. |
| Skip blank pages | PDF sources. Only Off adds an entry, so a default install keeps every digest. |
| Non-Latin pages | PDF sources |
| Router | PDF sources. The router recipe enters the digest. Its name does not, so a rename re-indexes nothing. |
| Local OCR backends | PDF sources |
| Confidence cuts | PDF sources |

A Studio step value works in a different way. A step that sets PDF readers, maths pages, non-Latin pages, local OCR backends or OCR engines changes the pipeline shape. Every source that the pipeline reads then re-indexes. A step that sets skip blank pages, the router or a cut re-indexes PDF sources only.

## Where did my setting go

Settings > Document reading had separate cards before the panel. This table maps each old block to its place in the panel.

| Old block | Rows in it | Now |
| --- | --- | --- |
| PDF reading | PDF readers | Step 1 |
| When to use OCR | OCR fallback, OCR routing unit | Top of the panel, above step 1 |
| When to use OCR | Non-Latin routing | Step 2, Non-Latin pages |
| Maths pages | Maths routing | Step 2, Maths pages |
| Local OCR | Local OCR backends and cut boxes | Step 4 |
| Engines | OCR engines and the workers folder line | Step 5 |
| Router card | Host router row | Step 3 |
| Router card | Named routers | Router section, below the panel |

Skip blank pages is a new row in step 2.

## Troubleshooting

### "pypdfium2 (optional, not installed)" stays disabled after the install

- **Cause:** the server reads the installed readers when it starts. The panel says "Installed. Restart OMRS to use it."
- **Fix:** restart OMRS.
- **Check:** the choice reads "pypdfium2 (optional)" and you can add it.

### "Another install is running. Wait for it to finish, then try again."

- **Cause:** one install or uninstall job runs at a time.
- **Fix:** wait until the other job ends. Integrations shows its state. Then select Install again.
- **Check:** the button shows the running state of your job.

### Step 1 shows a reason and a command, and no Install button

- **Cause:** the server cannot install extras on this install type, for example a source checkout.
- **Fix:** run the command that step 1 shows, then restart OMRS.
- **Check:** the pypdfium2 choice reads "pypdfium2 (optional)".

### "Remove OCR_SKIP_BLANK_PAGES from the environment or .env to edit it here."

- **Cause:** the environment or `.env` sets the key, and that value wins over `omrs.jsonc`.
- **Fix:** remove the variable, then restart OMRS.
- **Check:** the row offers Edit and shows its source.

### Start-up stops with a message that names `ocr_skip_blank_pages`

- **Cause:** `OCR_SKIP_BLANK_PAGES` holds text that is not a boolean, for example `sometimes`.
- **Fix:** set it to `true` or `false`, or remove it.
- **Check:** `omrs web` starts.

## Evidence

- [Experiment 33](../../experiments/33-ocr-routing-natural-positive-2026-09-17/report.md): the page labels on 1,123 pages that calibrated the blank test, and the routing study.
- [Experiment 43](../../experiments/43-image-rescue-gate-2026-11-02/report.md): the router template and its cost.
- [Experiment 46](../../experiments/46-local-ocr-backends-2026-11-04/report.md): the local OCR backends for non-Latin scripts.
- [Experiment 46a](../../experiments/46a-local-ocr-per-backend-cuts-2026-11-06/report.md): the cuts 0.92 and 0.94.
- [Experiment 47](../../experiments/47-router-confirmation-2026-11-05/report.md): router recall 0.52 on new documents, so the router stays off by default.

## See also

- [ADR-116](../adr/116-skip-blank-switch-and-fixed-page-rule-order.md): the skip blank pages switch and the fixed rule order.
- [Configuration](configuration.md#document-reading-values): every key, its environment variable and the rules that a save checks.
- [Pipeline graphs](pipelines.md#pdf-readers-on-the-read-document-step): the Read document step options.
- [Ingestion](ingestion.md#page-rules): how the page rules combine their results.
- [Reading parts](reading-parts.md): how to add a reader, a local OCR backend or a page rule.
- [Web workspace](web-workspace.md#document-reading): the Settings page.
