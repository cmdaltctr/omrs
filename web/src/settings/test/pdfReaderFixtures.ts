import type { Integration, IntegrationInstall, PdfReaderItem } from "../../api/integrations";

/** The catalogue entry of the optional pypdfium2 reader: not installed, and installable from the app. */
export const PYPDFIUM2_ENTRY: Integration = {
  id: "pdf-pypdfium2",
  name: "PDF reader: pypdfium2",
  purpose: "Reads PDF pages with the pypdfium2 library.",
  extra: "pdf-pypdfium2",
  install_command: 'uv tool install --reinstall "omrs[web,pdf-pypdfium2] @ ~/src/omrs"',
  pip_command: 'pip install "omrs[pdf-pypdfium2]"',
  availability: "not-installed",
  installable: true,
  install_reason: null,
  packages: ["pypdfium2>=4.0.0"],
  install_caution: null,
  base: false,
  uninstallable: false,
  uninstall_reason: "not-installed",
  uninstall_setting: null,
  removes: [],
  keeps: [],
  lasting_uninstall_command: null,
  pending_restart: null,
  uninstall_profile: null,
};

/** The same entry on a server that cannot install from the app, such as a source checkout. */
export const PYPDFIUM2_CHECKOUT: Integration = { ...PYPDFIUM2_ENTRY, installable: false, install_reason: "not-uv-tool", install_command: "uv sync --extra pdf-pypdfium2" };

/** The same entry after an install job succeeded and the server waits for a restart. */
export const PYPDFIUM2_RESTART: Integration = { ...PYPDFIUM2_ENTRY, availability: "restart-needed", installable: false, install_reason: "already-installed", pending_restart: "install" };

export const PYPDFIUM2_READER: PdfReaderItem = { name: "pypdfium2", installed: false, extra: "pdf-pypdfium2", fix_command: "uv sync --extra pdf-pypdfium2", used_by: [] };

export const IDLE_INSTALL: IntegrationInstall = { state: "idle", action: null, extra: null, tool: null, started_at: null, finished_at: null, reason: null, exit_code: null, output: [] };
export const RUNNING_INSTALL: IntegrationInstall = { ...IDLE_INSTALL, state: "running", action: "install", extra: "pdf-pypdfium2", started_at: "2026-11-07T10:00:00Z", output: ["Resolving"] };
export const SUCCEEDED_INSTALL: IntegrationInstall = { ...RUNNING_INSTALL, state: "succeeded", finished_at: "2026-11-07T10:00:30Z", exit_code: 0, output: ["Installed 1 package"] };

/** `GET /v1/integrations` with one entry: the pypdfium2 reader row of the catalogue. */
export function integrationsBody(entry: Integration = PYPDFIUM2_ENTRY, installType: "uv-tool" | "checkout" = "uv-tool") {
  return { status: "ok", install_type: installType, integrations: [entry], tools: [], pdf_readers: [PYPDFIUM2_READER] };
}
