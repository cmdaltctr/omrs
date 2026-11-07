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

## marimo tool, model downloads and the llama.cpp router (ADR-101, ADR-106, ADR-109, ADR-115)

12. Build the marimo argument lists only in `tool_environment.py`, from the shipped manifest range. Run them through the same `InstallJob` (`start_tool`) with the same guards. A tool job runs the check function, not `uv pip check`, and sets no `restart_needed`.
13. Offer Uninstall only for a card-shaped receipt (marimo with the manifest range, jupytext, nothing else); else `not-installed-by-app`. Never register marimo from the install route (D4).
14. Model downloads use the one `ModelDownloadJob` on `WebRuntime`, behind `require_session("manage")` (search too: it contacts an outside host). Keep its guards: one job, no subprocess, an adapter table keyed by `ModelSourceKind`, fixed reasons only, no exception text or `HF_TOKEN` in a status, response or log, names checked with `core/providers/model_sources.py` before any request, and no host contact at start-up.
15. The llama.cpp router (ADR-115). A change of the program or the router mode (`llamacpp_server_binary`, `llamacpp_router_server`), of an entry's `model`, `file`, `projector` or SHA-256, and the removal of an entry need `credentials`. The address, the two limits, preset values, Start, Stop, Restart and the install need `manage`. All of them need the browser session; a bearer credential never passes. Writes to `llamacpp_models` go through `write_llamacpp_models` (revision check, atomic replace), and `PUT /v1/settings/configuration` never writes it. A Chat save that names an embedding entry gets 400 `role-mismatch`; a llama.cpp Chat save changes no model file, so it needs `manage` only. The manager in `integrations/llamacpp_runtime/` starts the router (ADR-109, ADR-115). Call it through `run_in_threadpool`. `llamacpp_server.py` only maps its status to the route body and runs the lifespan hook; a status read opens no lease and starts nothing. The install job calls `provision.install_pinned_build` and nothing else. `POST /v1/runtimes/{runtime_id}/stop` needs `require_session("manage")` and refuses a bearer credential. An external runtime gives 409 `external-runtime`. `GET /v1/runtimes` starts nothing and writes nothing. The routes may read and write the runtime state files under the state folder (`OMRS_STATE_DIR`). Every OMRS process writes those files, not only `omrs web`. They hold no settings and no secrets. `GET /v1/llamacpp/router/downloads-needed` contacts the model host, so it needs `require_session("manage")`; a status read never contacts the host.

## Size and tests

16. Keep each file under 500 lines (`tests/test_file_size_ceiling.py`). Put new logic in a sibling module, as `uninstall_plan.py` sits next to `integrations_catalogue.py`.
17. A new fast test changes the pins in `tests/test_clean_base_tripwire.py`. Count it with `pytest --collect-only -q` before and after, and compare the test IDs. A test that needs fastapi changes both `_BASE_EXECUTED` and `_WEB_EXTRA_CASES`.

## Links

- [Root AGENTS.md](../../../../AGENTS.md)
- [Transports guide](../AGENTS.md)
- [HTTP transport README](README.md)
- [ADR-094: install from the app](../../../../docs/adr/094-app-installs-allowed-extras-into-itself.md) and [ADR-096: uninstall](../../../../docs/adr/096-app-uninstalls-extras-it-can-install.md)
- [ADR-101: marimo as a separate uv tool](../../../../docs/adr/101-app-installs-marimo-as-a-separate-uv-tool.md), [ADR-106: model search and download](../../../../docs/adr/106-app-searches-and-downloads-local-models.md) and [ADR-108: local Chat and classification](../../../../docs/adr/108-local-chat-and-classification-stay-apart.md) and [ADR-109: OMRS owns local model runtimes](../../../../docs/adr/109-omrs-owns-local-model-runtimes-components-are-clients.md) and [ADR-115: one llama.cpp router](../../../../docs/adr/115-one-llamacpp-router.md)
