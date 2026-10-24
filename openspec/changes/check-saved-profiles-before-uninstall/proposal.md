# Proposal

## Why

The Integrations page can uninstall an optional extra, and it refuses when a setting in `omrs.jsonc` or the effective settings still selects that extra (ADR-096). Saved user profiles are not checked. A user profile can select an extra in two ways: the PDF reader on its Read document step, and its embedding provider. If the user uninstalls that extra, the app still starts, but every ingestion through that profile fails. ADR-096 records this as a known gap.

## What Changes

- The uninstall in-use check also reads every user profile that is not deleted, through the web server's profile catalogue.
- A profile uses an extra when an enabled `read.document` step in its ingest pipeline names a PDF reader that the in-use map ties to that extra (today `pypdfium2` for `pdf-pypdfium2`), or when its `embed_provider` names a provider whose registry entry declares the extra.
- A profile in use refuses the uninstall with the same reason `in-use`. The entry and the 409 body also name the profile: new field `uninstall_profile` (`{id, title}`) on the entry, and `profile` on the 409 body. `uninstall_setting` names the setting inside the profile (`pdf_reader` or `embed_provider`).
- The card says which profile uses the extra and links to it in Studio. No Uninstall button shows.
- A global setting still wins: when both a setting and a profile use the extra, the card names the setting first.
- Built-in profiles run on host settings, so the existing global check already covers them.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `integration-install`: the in-use check covers saved user profiles.
- `workspace-integrations`: the card names the profile that uses the extra.

## Impact

- Server: `transports/api/uninstall_plan.py` (profile walk), `integrations_catalogue.py` and `routes/integrations.py` (new field, 409 body), `install_job.py` (a profile catalogue reader that tests can replace), `openapi.yaml`.
- Web: `web/src/api/integrations.ts`, `web/src/integrations/UninstallControls.tsx`, `InstallRefusal.tsx`, tests.
- Docs: `docs/guides/web-workspace.md`, ADR-096 (the known gap is closed).
- No data migration. The check only reads the workspace.
