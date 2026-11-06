/**
 * Typed client for the llama.cpp router that `omrs web` starts and owns, and
 * for its model list. Shapes follow `openapi.yaml` (`getLlamacppRouter`,
 * `saveLlamacppRouter`, `saveLlamacppRouterModel`, `deleteLlamacppRouterModel`,
 * `startLlamacppRouter`, `stopLlamacppRouter`, `restartLlamacppRouter`).
 * No response holds log text or text from a process: a failure is one fixed
 * reason.
 */
import type { ApiClient, CallOptions } from "./client";
import type { SaveOptions } from "./settings";

export type RouterState = "stopped" | "starting" | "running" | "failed";

/** The fixed reasons of a `failed` router. */
export type RouterReason =
  | "binary-invalid"
  | "model-invalid"
  | "not-loopback"
  | "port-in-use"
  | "exited"
  | "timeout"
  | "not-configured"
  | "not-supported"
  | "version-busy"
  | "wrong-build"
  | "file-changed"
  | "bind-failed"
  | "not-provisioned"
  | "not-downloaded";

/** Who runs the router: `managed` is OMRS's own `llama-server`; `external` is an address the user runs. */
export type RouterMode = "managed" | "external";

/** Why a router route refused with 409. Absent on a save refused for a locked field or a stale revision. */
export type RouterConflictReason = "external-server" | "in-use" | "busy";

/** The roles that the role settings give a list entry. Never stored. */
export type RouterRole = "embeddings" | "classification" | "chat" | "judge" | "decision";

export type RouterModelState = "not-downloaded" | "unloaded" | "loading" | "loaded" | "failed";

export interface RouterField {
  /** The `omrs.jsonc` key, such as `llamacpp_router_models_max`. */
  id: string;
  label: string;
  kind: "text" | "url" | "int" | "choice";
  /** The value in force. An unset program is the empty string. */
  value: string | number;
  /** The code default, for Use default. */
  default: string | number;
  min: number | null;
  max: number | null;
  source: "env" | "dotenv" | "config-file" | "default";
  locked: boolean;
  /** Names the environment variable that locks the field. */
  lock_reason: string | null;
}

/** One `llamacpp_models` entry as the router status lists it. */
export interface RouterModel {
  id: string;
  /** The request name and preset section name, `org/name:QUANT`. */
  model: string;
  roles: RouterRole[];
  /** Absolute path of the model file; `null` until downloaded. */
  file: string | null;
  projector: string | null;
  /** The `ctx-size` preset value, in tokens. */
  ctx_size: number | null;
  /** The allow-listed preset keys with their values. */
  preset: Record<string, string | number | boolean>;
  state: RouterModelState;
  reason: "model-invalid" | "file-changed" | "preset-invalid" | "model-load-failed" | "model-not-listed" | "role-mismatch" | "version-busy" | null;
  reason_text: string | null;
  note: string | null;
  /** The saved entry differs from the running router's `models.ini`. */
  reload_pending: boolean;
}

/** A role that no list entry can serve. `text` is the server's own plain line and never names the model. */
export interface RouterProblem {
  role: RouterRole;
  reason: "model-not-listed" | "role-mismatch" | "preset-invalid";
  text: string;
}

export interface LlamacppRouterStatus {
  status: "ok";
  /** Stamp of `omrs.jsonc` read. A save sends it back. */
  revision: string;
  state: RouterState;
  reason: RouterReason | null;
  reason_text: string | null;
  mode: RouterMode;
  /** Host and port of the router address. */
  address: string | null;
  /** What the live process started with, or `null` when none is owned. */
  running_with: { models_max: number; memory_margin_mib: number } | null;
  /** The saved router arguments differ from the live process. Restart applies them. */
  pending_restart: boolean;
  program: { path: string; source: "user" | "provisioned" | "none" };
  saved: {
    binary: RouterField;
    router_server: RouterField;
    router_url: RouterField;
    models_max: RouterField;
    memory_margin_mib: RouterField;
  };
  models: RouterModel[];
  /** Empty while the mode is `external`. */
  problems: RouterProblem[];
}

/** Keys of a router save. An absent key stays as it is; `null` clears the saved value. */
export interface LlamacppRouterChange {
  binary?: string | null;
  router_server?: RouterMode | null;
  router_url?: string | null;
  models_max?: number | null;
  memory_margin_mib?: number | null;
}

/** Keys of a list-entry save. An absent key stays as it is; `preset` replaces the whole preset. */
export interface RouterModelChange {
  model?: string | null;
  file?: string | null;
  projector?: string | null;
  sha256?: string | null;
  projector_sha256?: string | null;
  preset?: Record<string, string | number | boolean> | null;
}

const PATH = "/v1/llamacpp/router";

export function getLlamacppRouter(api: ApiClient, options: CallOptions = {}): Promise<LlamacppRouterStatus> {
  return api.request<LlamacppRouterStatus>("GET", PATH, { signal: options.signal });
}

/** Saves program, mode, address or the two router limits. A running router keeps running. */
export function saveLlamacppRouter(api: ApiClient, change: LlamacppRouterChange, options: SaveOptions = {}): Promise<LlamacppRouterStatus> {
  return api.request<LlamacppRouterStatus>("PUT", PATH, { body: { ...change, revision: options.revision }, signal: options.signal });
}

/** Sets fields of list entry `id`, or adds the entry. The router reloads that one model. */
export function saveLlamacppRouterModel(api: ApiClient, id: string, change: RouterModelChange, options: SaveOptions = {}): Promise<LlamacppRouterStatus> {
  return api.request<LlamacppRouterStatus>("PUT", `${PATH}/models/${encodeURIComponent(id)}`, { body: { ...change, revision: options.revision }, signal: options.signal });
}

/** Removes entry `id`. The server refuses with 409 `in-use` while the entry holds a role. */
export function deleteLlamacppRouterModel(api: ApiClient, id: string, options: SaveOptions = {}): Promise<LlamacppRouterStatus> {
  return api.request<LlamacppRouterStatus>("DELETE", `${PATH}/models/${encodeURIComponent(id)}`, { query: options.revision === undefined ? undefined : { revision: options.revision }, signal: options.signal });
}

export function startLlamacppRouter(api: ApiClient, options: CallOptions = {}): Promise<LlamacppRouterStatus> {
  return api.request<LlamacppRouterStatus>("POST", `${PATH}/start`, { signal: options.signal });
}

export function stopLlamacppRouter(api: ApiClient, options: CallOptions = {}): Promise<LlamacppRouterStatus> {
  return api.request<LlamacppRouterStatus>("POST", `${PATH}/stop`, { signal: options.signal });
}

export function restartLlamacppRouter(api: ApiClient, options: CallOptions = {}): Promise<LlamacppRouterStatus> {
  return api.request<LlamacppRouterStatus>("POST", `${PATH}/restart`, { signal: options.signal });
}
