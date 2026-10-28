/**
 * Typed client for `GET /v1/integrations` and the install routes.
 *
 * Shapes follow `src/omrs/transports/api/integrations_catalogue.py` and
 * `openapi.yaml`. The server reports availability for the running launch. An
 * entry with `installable: true` can be installed with
 * `POST /v1/integrations/{extra}/install`; the new packages work after a
 * restart. Every other entry is installed outside the app with its command.
 * An entry with `uninstallable: true` can be removed with
 * `POST /v1/integrations/{extra}/uninstall`; that also needs a restart.
 * The `tools` list holds external tools apart from the extras (today only
 * marimo, ADR-101). A tool goes into its own `uv tool` environment through
 * `POST /v1/integrations/tools/{tool}/install`, so it needs no restart.
 */
import type { ApiClient, CallOptions } from "./client";
import type { PluginStatus } from "./plugins";

export type IntegrationAvailability = "available" | "not-installed" | "unknown" | "restart-needed";

/** How the server itself was installed. It decides the copy command. */
export type InstallType = "uv-tool" | "checkout" | "other";

/** Why `installable` is false, or `null` when it is true. */
export type InstallReason = "not-installable-here" | "status-unknown" | "not-uv-tool" | "uv-not-found" | "already-installed" | "no-requirements";

/** Why `uninstallable` is false, or `null` when it is true. `in-use` comes with `uninstall_setting`. */
export type UninstallReason = "not-uninstallable-here" | "not-installed" | "nothing-to-remove" | "in-use" | "not-uv-tool" | "uv-not-found" | "install-running";

export interface Integration {
  id: string;
  name: string;
  /** One line about what the integration adds. */
  purpose: string;
  /** The pip extra, or null for an always-on integration. */
  extra: string | null;
  /** The copy command for this install type, or null when there is nothing to install. */
  install_command: string | null;
  /** `pip install "omrs[<name>]"`, or null when there is nothing to install. */
  pip_command: string | null;
  availability: IntegrationAvailability;
  /** True when `POST /v1/integrations/{extra}/install` would start an install now. */
  installable: boolean;
  install_reason: InstallReason | null;
  /** The requirements the extra adds, such as `llama-index-llms-anthropic>=0.11.0`. */
  packages: string[];
  /** A warning to read before the install, such as a package version it can change; null for most entries. */
  install_caution: string | null;
  /** True when every install already holds this entry; it has no install command. */
  base: boolean;
  /** True when `POST /v1/integrations/{extra}/uninstall` would start an uninstall now. */
  uninstallable: boolean;
  uninstall_reason: UninstallReason | null;
  /** The `omrs.jsonc` key of the setting that selects the extra, such as `vector_store`, when the reason is `in-use`; else null. */
  uninstall_setting: string | null;
  /** The installed packages an uninstall removes. Empty unless the entry is installed and is not base or `web`. */
  removes: string[];
  /** The extra's installed packages an uninstall keeps, because something else needs them. */
  keeps: string[];
  /** The reinstall command without this extra, set only when the uv tool receipt lists it; else null. */
  lasting_uninstall_command: string | null;
  /** The app action that succeeded for this extra in this launch and waits for a restart; null when nothing waits. */
  pending_restart: InstallAction | null;
  /** The saved user profile that uses the extra (reason `in-use`), or null when a global setting does or nothing does. */
  uninstall_profile: IntegrationProfileRef | null;
  /** Only llama.cpp and OpenRouter: whether a server answers or a key reference is set. */
  readiness?: IntegrationReadiness;
}

/** One readiness line: "Ready", "Not running at <address>" or "No key set". */
export interface IntegrationReadiness {
  ready: boolean;
  line: string;
}

export type RuntimeStatus = "ready" | "missing" | "not-configured" | "not-running" | "unknown";

/** One OCR engine, model file or local server that a setting depends on. Probes only read. */
export interface RuntimeItem {
  name: string;
  purpose: string;
  status: RuntimeStatus;
  reason: string | null;
  /** A copy command that fixes the item, or null. */
  fix: string | null;
  /** The settings in force at launch that need the item. */
  used_by: string[];
}

export interface RuntimeComponents {
  ocr_engines: RuntimeItem[];
  model_files: RuntimeItem[];
  local_servers: RuntimeItem[];
}

/** A saved user profile, named on an in-use entry or refusal. */
export interface IntegrationProfileRef {
  id: string;
  title: string;
}

export interface IntegrationList {
  install_type: InstallType;
  integrations: Integration[];
  /** External tools apart from the extras. Today only marimo. */
  tools: ExternalTool[];
  /** OCR engines, model files and local servers. Older fixtures may leave it out. */
  runtime?: RuntimeComponents;
}

/** The state of an external tool's `uv tool` environment. It does not depend on the server's install type. */
export type ToolAvailability = "ready" | "needs-jupytext" | "outside-range" | "not-installed" | "unknown";

/** Why a tool's `installable` is false, or `null` when it is true. */
export type ToolInstallReason = "uv-not-found" | "status-unknown" | "already-installed" | "install-running" | "editor-running";

/** Why a tool's `uninstallable` is false, or `null` when it is true. `not-installed-by-app`: the card did not install it. */
export type ToolUninstallReason = "uv-not-found" | "status-unknown" | "not-installed" | "not-installed-by-app" | "install-running" | "editor-running";

/** An external tool that the Integrations page can install into its own `uv tool` environment (ADR-101). */
export interface ExternalTool {
  id: "marimo";
  name: string;
  /** One line about what the tool adds. */
  purpose: string;
  availability: ToolAvailability;
  /** The installed version, or null. */
  version: string | null;
  /** Whether jupytext is in the tool environment. */
  jupytext: boolean;
  /** Absolute path of the executable from the uv receipt, or null. */
  executable: string | null;
  /** The requirement the card installs, such as `marimo>=0.25.1,<0.26.0`. */
  requirement: string;
  /** The copy-ready install command for a terminal. */
  install_command: string;
  /** The copy-ready uninstall command for a terminal. */
  uninstall_command: string;
  /** True when `POST /v1/integrations/tools/{tool}/install` would start an install now. */
  installable: boolean;
  install_reason: ToolInstallReason | null;
  /** Set for `needs-jupytext` and `outside-range`: Install replaces the tool environment. Null otherwise. */
  install_caution: string | null;
  /** True when `POST /v1/integrations/tools/{tool}/uninstall` would start an uninstall now. */
  uninstallable: boolean;
  uninstall_reason: ToolUninstallReason | null;
  /** The state of the plugin registration for this tool, or null when it is not registered. */
  plugin_status: PluginStatus | null;
}

export type InstallState = "idle" | "running" | "succeeded" | "failed";

/** Whether a job adds or removes its extra. */
export type InstallAction = "install" | "uninstall";

/** The running or last install or uninstall job of this launch. */
export interface IntegrationInstall {
  state: InstallState;
  /** Whether the job installs or uninstalls its extra; null when idle. */
  action: InstallAction | null;
  /** The extra of the running or last install; null when idle or for a tool job. */
  extra: string | null;
  /** The external tool of the running or last job; null when idle or for an extras job. */
  tool: ExternalTool["id"] | null;
  started_at: string | null;
  finished_at: string | null;
  /** Why the install failed; null unless `state` is `failed`. `check-failed`: installed, but `uv pip check` found a clash. */
  reason: "exit-code" | "check-failed" | "timed-out" | "start-failed" | null;
  exit_code: number | null;
  /** The last output lines (at most 40), redacted by the server. */
  output: string[];
}

export async function listIntegrations(api: ApiClient, options: CallOptions = {}): Promise<IntegrationList> {
  const reply = await api.request<IntegrationList>("GET", "/v1/integrations", { signal: options.signal });
  const list: IntegrationList = { install_type: reply.install_type, integrations: reply.integrations, tools: reply.tools };
  return reply.runtime === undefined ? list : { ...list, runtime: reply.runtime };
}

export async function getIntegrationInstall(api: ApiClient, options: CallOptions = {}): Promise<IntegrationInstall> {
  const reply = await api.request<{ install: IntegrationInstall }>("GET", "/v1/integrations/install", { signal: options.signal });
  return reply.install;
}

/** Starts an install of `extra`. The server answers 202 with the running state, or 409 with a `reason`. */
export async function installIntegration(api: ApiClient, extra: string): Promise<IntegrationInstall> {
  const reply = await api.request<{ install: IntegrationInstall }>("POST", `/v1/integrations/${encodeURIComponent(extra)}/install`);
  return reply.install;
}

/** Starts an uninstall of `extra`. The server answers 202 with the running state, or 409 with a `reason` (and a `setting` for `in-use`). */
export async function uninstallIntegration(api: ApiClient, extra: string): Promise<IntegrationInstall> {
  const reply = await api.request<{ install: IntegrationInstall }>("POST", `/v1/integrations/${encodeURIComponent(extra)}/uninstall`);
  return reply.install;
}

/** Starts an install of the external `tool`. The server answers 202 with the running state, or 409 with a `reason`. */
export async function installTool(api: ApiClient, tool: string): Promise<IntegrationInstall> {
  const reply = await api.request<{ install: IntegrationInstall }>("POST", `/v1/integrations/tools/${encodeURIComponent(tool)}/install`);
  return reply.install;
}

/** Starts an uninstall of the external `tool`. The server answers 202 with the running state, or 409 with a `reason`. */
export async function uninstallTool(api: ApiClient, tool: string): Promise<IntegrationInstall> {
  const reply = await api.request<{ install: IntegrationInstall }>("POST", `/v1/integrations/tools/${encodeURIComponent(tool)}/uninstall`);
  return reply.install;
}
