# src/omrs/transports/api (HTTP transport)

The local HTTP API for `omrs web`. `openapi.yaml` is its OpenAPI 3.1 contract. Route groups live in `routes/`.

## Contract first

1. Change `openapi.yaml` before the route.
2. Add each new `operationId` to a family in `FAMILIES` (`tests/unit/test_web_openapi_conformance_support.py`). `test_response_flows_cover_every_operation` fails otherwise.
3. Response schemas such as `Integration` set `additionalProperties: false`. A new response field fails the conformance tests until the contract declares it.
4. Give each 409 a `reason` and a plain-English line in the route's message map, for example `UNINSTALL_REASONS` in `routes/integrations.py`. Add the reason to the contract enum and to `web/src/integrations/InstallRefusal.tsx`.

## Install and uninstall (ADR-094, ADR-096)

5. Guard these routes with `require_session("manage")`. A bearer credential never gets `manage`.
6. Use the one `InstallJob` on `WebRuntime`. Keep its guards: one job at a time, 600 s limit, no `*_API_KEY` variable, the last 40 redacted lines, and an argument list with no shell.
7. Take package names from the installed metadata. No request text reaches a command.
8. D1 (`uninstall_plan.py`): remove only the extra's own packages that nothing else installed needs. A requirement behind another package's extra counts only when something asks for that extra.
9. D2: `IN_USE` maps backend settings to extras. Provider settings come from `extra_for()` in the provider registries. Saved user profiles are walked in `uninstall_profiles.py` (Read document `pdf_reader`, profile `embed_provider`). A new node parameter that names an extra must extend `PROFILE_READER_OPERATIONS` and that walk.
10. A new non-base extra needs an `IN_USE` entry, or `test_every_non_base_catalogue_extra_has_an_in_use_entry` fails. Use `()` when no setting selects it.
11. Add the extra's modules to `HIDDEN_MODULES` in `tests/unit/test_web_extras_modularity.py`. No test enforces this.

## marimo tool (ADR-101)

12. Build the marimo argument lists only in `tool_environment.py`, from the shipped manifest range. Run them through the same `InstallJob` (`start_tool`) with the same guards. A tool job runs the check function, not `uv pip check`, and sets no `restart_needed`.
13. Offer Uninstall only for a card-shaped receipt (marimo with the manifest range, jupytext, nothing else); else `not-installed-by-app`. Never register marimo from the install route (D4).

## Model download job (ADR-106)

17. Guard the five `/v1/model-downloads` routes with `require_session("manage")`. A bearer credential never gets `manage`. Search needs `manage` too, because each call makes the server contact an outside host.
18. Use the one `ModelDownloadJob` on `WebRuntime` (`model_download_job.py`). Keep its guards: one job at a time, no subprocess, no shell, and an adapter table keyed by `ModelSourceKind` with no branch on a provider name. Blocking adapters run in `asyncio.to_thread`. `shutdown_runtime()` cancels the job and waits up to 5 seconds.
19. Give a failed job one of the fixed reasons only: `not-found`, `gated`, `network`, `stalled`, `ollama-unreachable`, `failed`. The 409 reasons are `busy`, `no-space` and `gated`. No status, response or log line above debug level holds exception text or the `HF_TOKEN` value. Run log text through `security.redact`.
20. Check every name with `core/providers/model_sources.py` before any request or file path. The client sends no file name. Search and file-list calls contact the host only when the route runs, never at start-up.

## Size and tests

14. Keep each file under 500 lines (`tests/test_file_size_ceiling.py`). Put new logic in a sibling module, as `uninstall_plan.py` sits next to `integrations_catalogue.py`.
15. A new fast test changes the pins in `tests/test_clean_base_tripwire.py`. Count it with `pytest --collect-only -q` before and after, and compare the test IDs.
16. A new test that needs fastapi changes both `_BASE_EXECUTED` and `_WEB_EXTRA_CASES`.

## Links

- [Root AGENTS.md](../../../../AGENTS.md)
- [Transports guide](../AGENTS.md)
- [HTTP transport README](README.md)
- [ADR-094: install from the app](../../../../docs/adr/094-app-installs-allowed-extras-into-itself.md)
- [ADR-096: uninstall from the app](../../../../docs/adr/096-app-uninstalls-extras-it-can-install.md)
- [ADR-101: marimo as a separate uv tool](../../../../docs/adr/101-app-installs-marimo-as-a-separate-uv-tool.md)
- [ADR-106: model search and download](../../../../docs/adr/106-app-searches-and-downloads-local-models.md)
