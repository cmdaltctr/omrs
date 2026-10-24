# Proposal

## Why

The Integrations page can install an optional extra, but it cannot remove one. A user who tries Chroma, Azure or PyTorch has no way back from the app. OMRS is meant to be modular: each extra adds one capability, and the app must keep working when the extra is gone. This change adds Uninstall and checks that promise for every extra.

## What Changes

- An installed entry that is not a base entry shows **Uninstall**. Base entries (Magika, pdf-inspector, llama.cpp, OpenRouter) and `web` never do.
- Uninstall opens a dialog. It lists the packages that go and the ones that stay because something else needs them. The user confirms, the server runs `uv pip uninstall` in its own environment, then `uv pip check`, and the entry waits for a restart.
- The server removes only the extra's own top-level packages. It keeps any package that the base install, another installed extra or another installed package still needs. A requirement behind another package's extra counts only when something asks for that extra, as in `pip check`. Packages that only the removed ones pulled in stay in place; a later reinstall from the lasting command drops them.
- The server refuses an extra that a setting or a collection still uses, and names the setting. Examples: `vector_store` is `chroma`, `retrieval.rerank_backend` is `torch`, `pdf_reader` is `pypdfium2`, `document_backend` is `azure`, `community_algorithm` is `leiden`. Every provider setting counts through the provider registry: `answer.provider`, `answer.verify_provider`, `metadata_llm_provider` (and a provider-named `metadata.extraction_mode`), `embed_provider`, `local_backend` and `cloud_backend`, so a provider such as Anthropic, or any later provider with an extra, blocks its extra.
- When the extra is in the install receipt (for example `hybrid` in `omrs[web,hybrid]`) and no setting uses it, the card also shows the lasting command without it, because a later reinstall would add it back.
- Each entry reports `pending_restart` (`install` or `uninstall`) for an action that succeeded in this launch, so a card stays right after a later job.
- Uninstall uses the install job: one job at a time, the same `manage` session guard, 600 s limit, no `*_API_KEY` in the process, 40 redacted output lines.
- **Modularity check:** a test starts the web app with each non-base extra's modules hidden and checks that it starts, lists integrations and serves a search. A browser check removes extras one by one from a scratch `uv tool` install and restarts the app after each.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `integration-install`: the server can uninstall an allowed, installed, unused extra from its own environment, with the same guards as install.
- `workspace-integrations`: an installed non-base entry shows Uninstall with a confirm dialog, the in-use reason, and the lasting command when the extra is in the receipt.

## Impact

- Server: `transports/api/install_environment.py` (uninstall reason, packages to remove), `install_job.py` (an uninstall action), `routes/integrations.py` (`POST /v1/integrations/{extra}/uninstall`), `integrations_catalogue.py` (`uninstallable`, `uninstall_reason`), `openapi.yaml`.
- Web: `web/src/integrations/` (Uninstall button, dialog, progress), `api/integrations.ts`.
- Tests: route, environment and job tests; a modularity test for each extra; tripwire pins.
- Docs: `docs/guides/web-workspace.md`, a new ADR next to ADR-094.
- The live app is only touched when the user presses Uninstall.
