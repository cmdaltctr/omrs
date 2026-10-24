# web/src/integrations (Integrations page)

The page that lists optional integrations and installs or uninstalls an extra.

## What belongs here

- `IntegrationsView.tsx` (the page) and `IntegrationCard.tsx` (one entry).
- `InstallControls.tsx`, `UninstallControls.tsx` and `UninstallDialog.tsx`: the actions of one card.
- `InstallRefusal.tsx`: the line for a refused start (409).
- `useIntegrationInstall.ts`: the job state and the start actions. The API client is `../api/integrations.ts`.

## Rules

1. The server is the single source of truth. Read `pending_restart` for the restart badge and line. Never guess it from the last job, because a later job replaces that job.
2. `installPhase` ignores a job whose `action` is `uninstall`. `uninstallPhase` reads only that action. Keep each phase to its own action.
3. `busy` is true while a job runs or either start request is in flight. Disable every Install and Uninstall button with it.
4. Give each new 409 reason one line in `REFUSALS` or `UNINSTALL_REFUSALS` (`InstallRefusal.tsx`). An unknown reason falls back to `describeError`.
5. Hide `lasting_uninstall_command` while `uninstall_reason` is `in-use`. That command would remove an extra the next start needs.
6. Add a new contract field to `Integration` in `../api/integrations.ts` first. Then add it to every fixture typed `Integration`: the tests here, `../api/integrations.test.ts` and `../settings/ProviderIntegrationLink.test.tsx`.
7. Run `npm run typecheck` to find a fixture without the field. When a script adds the field, check that no fixture gets the key twice.
8. Keep each component under about 200 lines. Split a larger one by action, as the install and uninstall controls are split.

## Links

- [Root AGENTS.md](../../../AGENTS.md)
- [Front-end source guide](../AGENTS.md)
- [HTTP transport guide](../../../src/omrs/transports/api/AGENTS.md)
- [ADR-096: uninstall from the app](../../../docs/adr/096-app-uninstalls-extras-it-can-install.md)
