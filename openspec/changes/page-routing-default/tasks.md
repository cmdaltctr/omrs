# Tasks

## 1. Settings and refusal (tests first)

- [x] 1.1 Write failing tests: the default `ocr_routing_unit` resolves to `page`; a `document` value (env and settings file) fails at start-up with a message naming `page`; the removed keys `OCR_FALLBACK_PAGE_FRACTION`, `OCR_FALLBACK_MIN_CONFIDENCE` and `OCR_MATHS_PAGE_FRACTION` fail at start-up naming their removal; `OCR_ROUTING_UNITS` is `("page",)`. Verify: the tests fail on the current code.
- [x] 1.2 Remove `ocr_fallback_page_fraction`, `ocr_fallback_min_confidence` and `ocr_maths_page_fraction` from the Settings model, `config/` validation and rules, and add the refusal messages. Verify: the tests from 1.1 pass.

## 2. The document unit goes (tests first)

- [x] 2.1 Write failing tests: the document-unit branch, `_worker_document` and `maths_condition` no longer exist; `ocr_required_by_gate` is gone; the pdf-inspector seam always routes page by page; a clean text PDF with no flagged pages dispatches nothing. Update the seam tests that drive the document unit. Verify: the tests fail on the current code.
- [x] 2.2 Delete the document-unit path from `ocr_routing.py` and the gate from `ocr_policy.py`. Keep the maths split and the ADR-066 rescue in the page path. Verify: the tests from 2.1 pass and `uv run pytest tests/test_file_size_ceiling.py -q` passes.
- [x] 2.3 Write failing tests, then implement: with the local OCR runtime unavailable, flagged pages go to the worker in one page-listed request and never keep native text; with no worker either, the existing degradation applies and one warning names both tiers. Update the seam test that pins the old native-text fallback. Verify: the new test fails first.

## 3. Identity and surfaces

- [x] 3.1 Write failing tests: the routing payload is `{enabled, routing_unit, blank_page_test, local_tier}`; the unconditional types and gate values are gone; `PAGE_ROUTING_ONLY_EMBED_KEYS` is empty; `_INDEX_IDENTITY_SCHEMA` is 7; every source's identity changes once. Verify: the tests fail on the current code.
- [x] 3.2 Apply the payload and exclusion changes in `core/ingestion/ocr_identity.py` and `core/ingestion/embed_exclusions.py`; remove the three keys from `core/pipelines/levers.py` and `core/ingestion/graph_adapters_catalogue.py`; update the identity baseline pins with a dated comment. Verify: the tests from 3.1 pass.
- [x] 3.3 Update the Settings page rows and the settings-file write rule for the removed keys and the `page`-only unit rule, with the refusals from the spec. Verify: the web gates and the settings-file tests pass.
- [x] 3.4 Drift check: grep `docs/guides/` and `.env.example` for the `document` unit, `OCR_FALLBACK_PAGE_FRACTION`, `OCR_FALLBACK_MIN_CONFIDENCE`, `OCR_MATHS_PAGE_FRACTION` and the 10% rule; fix what the change makes wrong. Verify: `grep -rn "ocr_fallback_page_fraction" docs/ .env.example` finds nothing stale.
- [x] 3.5 Add a dated amendment note to ADR-069: `page` is the only routing unit, the document gate and its settings and the maths page fraction are gone, and a missing local runtime escalates to the worker. Verify: the note names this change and the master flow D2 decision.

## 4. Gates and PR

- [x] 4.1 Re-pin `tests/test_clean_base_tripwire.py` `_BASE_EXECUTED` by test-ID diff. Ask before `./scripts/local_ci.sh`; run `openspec validate page-routing-default --strict`. Verify: both pass, with no `SKIPPED` step.
- [ ] 4.2 Open a pull request from `feat/page-routing-default` into `v3`. Do not merge; wait for the operator. GATE G2.
