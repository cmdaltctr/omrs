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

## Size and tests

12. Keep each file under 500 lines (`tests/test_file_size_ceiling.py`). Put new logic in a sibling module, as `uninstall_plan.py` sits next to `integrations_catalogue.py`.
13. A new fast test changes the pins in `tests/test_clean_base_tripwire.py`. Count it with `pytest --collect-only -q` before and after, and compare the test IDs.
14. A new test that needs fastapi changes both `_BASE_EXECUTED` and `_WEB_EXTRA_CASES`.

## Links

- [Root AGENTS.md](../../../../AGENTS.md)
- [Transports guide](../AGENTS.md)
- [HTTP transport README](README.md)
- [ADR-094: install from the app](../../../../docs/adr/094-app-installs-allowed-extras-into-itself.md)
- [ADR-096: uninstall from the app](../../../../docs/adr/096-app-uninstalls-extras-it-can-install.md)
