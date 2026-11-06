/**
 * Typed client for the local model runtimes (the llama.cpp router and OCR).
 * Shapes follow `openapi.yaml` (`listRuntimes`, `stopRuntime`). No response
 * holds log text or text from a server: a failure is one fixed reason.
 */
import type { ApiClient, CallOptions } from "./client";
import type { RouterModelState, RouterRole } from "./llamacppRouter";

export type ModelRuntimeRole = "router" | "ocr";

/** `external` is a server the user runs. `managed` is a `llama-server` that OMRS starts and stops. */
export type ModelRuntimeMode = "external" | "managed";

export type ModelRuntimeState = "running" | "starting" | "stopped" | "failed";

/** The fixed reasons of a `failed` state. */
export type ModelRuntimeReason =
  | "binary-invalid"
  | "model-invalid"
  | "not-loopback"
  | "port-in-use"
  | "exited"
  | "timeout"
  | "not-configured"
  | "not-supported"
  | "version-busy"
  | "bind-failed"
  | "wrong-build"
  | "file-changed"
  | "not-provisioned";

export interface ModelRuntime {
  /** `router`, or `ocr-` and the engine folder name. */
  id: string;
  role: ModelRuntimeRole;
  mode: ModelRuntimeMode;
  state: ModelRuntimeState;
  reason: ModelRuntimeReason | null;
  /** A plain line for the reason. For `file-changed` it names the changed file. */
  reason_text: string | null;
  /** Resident memory of the server process, or `null` when it does not run. */
  memory_bytes: number | null;
  /** `some` when another OMRS process holds the runtime open. */
  clients: "some" | "none";
  /** The settings in force that use the runtime. */
  used_by: string[];
  /** Host and port, or `null`. */
  address: string | null;
  /** False for an external OCR runtime: OMRS cannot check the model files of a server it did not start. */
  files_checked: boolean;
  /** For the `router` item, one row per list entry. Empty for any other runtime. */
  models: RuntimeModel[];
}

/** One model of the router as `GET /v1/runtimes` lists it. */
export interface RuntimeModel {
  model: string;
  roles: RouterRole[];
  state: RouterModelState;
  reason: string | null;
  /** The router's own memory figure for the model, when it reports one. */
  memory_bytes: number | null;
}

export function listModelRuntimes(api: ApiClient, options: CallOptions = {}): Promise<ModelRuntime[]> {
  return api.request<{ runtimes: ModelRuntime[] }>("GET", "/v1/runtimes", { signal: options.signal }).then((body) => body.runtimes);
}

/** Stops a managed runtime and returns the item after the stop. An external runtime gets 409 `external-runtime`. */
export function stopModelRuntime(api: ApiClient, id: string, options: CallOptions = {}): Promise<ModelRuntime> {
  return api.request<ModelRuntime>("POST", `/v1/runtimes/${encodeURIComponent(id)}/stop`, { signal: options.signal });
}
