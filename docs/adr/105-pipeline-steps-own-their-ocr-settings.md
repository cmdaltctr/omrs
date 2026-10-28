# ADR-105: Pipeline Steps Own Their OCR Settings

- **Date:** 2026-10-28
- **Status:** Accepted (2026-10-28; built and merged to v3 at PR #137, merge commit `24961fa5`)
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Amends:** design D5 of the archived change `add-pdf-reader-step-setting` (OCR settings stay host-owned)
- **Related:** [ADR-072](072-modular-ocr-engines-dots-mocr-primary-and-maths-routing.md) (engine routes and maths routing), [ADR-069](069-page-level-ocr-routing-and-the-pdfium-runtime.md) (routing unit), [ADR-080](080-profiles-own-pipelines.md) (built-in profiles run no saved pipeline)
- **Change:** `openspec/changes/archive/2026-10-28-integrations-show-runtime-components/` (design D4 to D7)

## Context

A user-profile pipeline can choose its PDF reader on the Read document step. It cannot choose its OCR engine or OCR routing. The change `add-pdf-reader-step-setting` kept every OCR setting host-owned on purpose (its design D5): one OCR resource per run, built from the first node that enables OCR, so one engine served every node.

The operator now wants every document-reading setting editable in user-profile pipelines, so that one profile can read scanned papers with PaddleOCR-VL while another keeps dots.mocr. Built-in profiles keep the server settings.

Two OCR engines can be large at the same time. Experiment 37 measured a peak of about 22 GiB for dots.mocr and about 15 GiB for PaddleOCR-VL.

## Decision

1. **The Read document step takes the eight OCR settings (design D4).** `ocr_fallback_enabled`, `ocr_fallback_min_confidence`, `ocr_fallback_page_fraction`, `ocr_routing_unit`, `ocr_engine_primary`, `ocr_engine_fallback`, `ocr_maths_routing_enabled` and `ocr_maths_page_fraction` are option parameters of `read.document`, like `pdf_reader`. `null` inherits the host value. A set value passes the same rule as on Settings › Document reading. An engine that is not provisioned under the host workers folder fails admission with `option_unavailable`, naming the node, the engine and the provision command.
2. **Graph-wide overrides stay host-owned.** `overrides.<key>` for any of the eight keys fails with `host_owned_setting`, and the message tells the user to set it on the Read document step.
3. **The step settings enter the index identity.** A node that sets an OCR value records it in the source identity, so a changed value reprocesses the source on the next ingest. A node that inherits every value keeps the identity of the standard ingest path.
4. **One OCR client pool per Engine (design D5).** The Engine owns one lazy worker client per resolved engine command. Nodes with the same engine, and the host routes, share that client. One pool-wide lock lets only one engine parse at a time, so two engines do not hold peak memory together. A started worker stays loaded until the Engine closes or the worker fails; the worker has no idle exit.
5. **The old explicit worker command is removed (design D7).** `OCR_WORKER_COMMAND` and `OCR_WORKER_ENV_DIR` overrode the primary engine, so a step's chosen engine could be replaced without a sign. Routes now resolve only from the workers folder and an engine name. Start-up refuses either variable and names `OCR_WORKERS_DIR` with `OCR_ENGINE_PRIMARY`. The command never entered the index identity, so nothing reindexes.
6. **The step never changes the host.** A node cannot change the workers folder, an engine command or any host setting. Built-in profiles keep Settings › Document reading.

## Consequences

- A pipeline that mixes engines keeps both workers loaded until the Engine closes, about 37 GiB in the worst case. The configuration guide states this.
- Changing a step OCR value reprocesses the whole collection on the next ingest. Studio shows the existing reindex notice for index-shaping parameters.
- Rollback: revert the change. Graphs saved with step OCR values then fail validation with `invalid_parameter`, and the user clears the values.
- Experiment 35 needs no change. It uses built-in profile settings through its own scratch configuration.
