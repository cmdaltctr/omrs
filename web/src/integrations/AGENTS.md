# web/src/integrations (Integrations page)

The page that lists optional integrations and installs or uninstalls an extra. It also installs marimo, an external tool, into its own `uv tool` environment.

## What belongs here

- `IntegrationsView.tsx` (the page and its section chips), `IntegrationCard.tsx` (one entry) and `sections.ts` (section ids, the section an `#/integrations/<name>` address opens, the red chip count).
- `InstallControls.tsx`, `UninstallControls.tsx` and `UninstallDialog.tsx`: the actions of one card.
- `InstallRefusal.tsx`: the line for a refused start (409).
- `useIntegrationInstall.ts`: the job state and the start actions. The API client is `../api/integrations.ts`.
- `RuntimeGroups.tsx`: one runtime section (OCR engines, model files or local servers) from `runtime`. `WorkersFolderField.tsx` writes `ocr_workers_dir` through the settings write route. The page only shows these parts; each fix is a copy command.
- `ToolCard.tsx`, `ToolInstallControls.tsx`, `ToolUninstallControls.tsx` and `ToolDialogs.tsx`: the marimo card in the Tools section.

## Rules

1. The server is the single source of truth. Read `pending_restart` for the restart badge and line. Never guess it from the last job, because a later job replaces that job.
2. `installPhase` ignores a job whose `action` is `uninstall`. `uninstallPhase` reads only that action. Keep each phase to its own action.
3. `busy` is true while a job runs or either start request is in flight. Disable every Install and Uninstall button with it.
4. Give each new 409 reason one line in `REFUSALS` or `UNINSTALL_REFUSALS` (`InstallRefusal.tsx`). An unknown reason falls back to `describeError`.
5. Hide `lasting_uninstall_command` while `uninstall_reason` is `in-use`. That command would remove an extra the next start needs.
6. Add a new contract field to `Integration` in `../api/integrations.ts` first. Then add it to every fixture typed `Integration`: the tests here, `../api/integrations.test.ts` and `../settings/ProviderIntegrationLink.test.tsx`.
7. Run `npm run typecheck` to find a fixture without the field. When a script adds the field, check that no fixture gets the key twice.
8. Keep each component under about 200 lines. Split a larger one by action, as the install and uninstall controls are split.

## marimo card (ADR-101)

1. Extras and tools share one job (a tool job has `tool: "marimo"`, `extra: null`). Match a job by `tool` as well as `extra`, so no card reacts to the other kind. `busy` covers both kinds.
2. A tool has no restart state. marimo goes into its own `uv tool` environment, not into the server's Python.
3. Keep the Install and Uninstall buttons, disabled, while the reason is `install-running` or `editor-running`.
4. Show Uninstall only for a receipt that the card installed. For `not-installed-by-app`, show `uninstall_command` as a copy command.
5. Install does not register marimo. After an install, link to Experiments, Code editor (`#/experiments/code-editor`) to register or recheck it.
6. The card id is `integration-marimo`, so `#/integrations/marimo` focuses it. Add a new `ExternalTool` field to every fixture typed `ExternalTool`.

## Links

- [Root AGENTS.md](../../../AGENTS.md)
- [Front-end source guide](../AGENTS.md)
- [HTTP transport guide](../../../src/omrs/transports/api/AGENTS.md)
- [ADR-096: uninstall from the app](../../../docs/adr/096-app-uninstalls-extras-it-can-install.md)
- [ADR-101: the app installs marimo as a separate uv tool](../../../docs/adr/101-app-installs-marimo-as-a-separate-uv-tool.md)
