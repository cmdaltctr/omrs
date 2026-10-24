# Tasks

## 1. Server

- [ ] 1.1 Add the profile walk (D1, D2, D4) to `uninstall_plan.py` and a `profiles` reader on `InstallJob` (D5). Verify: unit tests fail first, then pass, for a `pypdfium2` Read document step, a disabled step, a deleted profile, a profile `embed_provider` with an extra (registered test provider), a global setting named first, and no catalogue.
- [ ] 1.2 Add `uninstall_profile` to the catalogue entry and `profile` to the 409 body, in `openapi.yaml` first (D3). Verify: route tests with a real profile saved through the profile service, and contract conformance.

## 2. Page

- [ ] 2.1 Load `omrs-design`. Show the profile line with its Studio link, and name the profile in a refused uninstall (D6). Verify: Vitest cases from the `workspace-integrations` scenarios fail first, then pass.
- [ ] 2.2 Update `docs/guides/web-workspace.md`, ADR-096 (close the known gap) and the `transports/api` folder guide. Verify: docs and guide tests pass.

## 3. Checks

- [ ] 3.1 Re-pin the tripwire, run `./scripts/local_ci.sh`, the web gates and `openspec validate check-saved-profiles-before-uninstall --strict`. Verify: all pass; record the counts here.
