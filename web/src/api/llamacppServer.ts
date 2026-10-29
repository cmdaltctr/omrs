/**
 * Typed client for the llama.cpp server that `omrs web` starts and owns.
 * Shapes follow `openapi.yaml` (`getLlamacppServer`, `saveLlamacppServer`,
 * `startLlamacppServer`, `stopLlamacppServer`, `restartLlamacppServer`).
 * No response holds log text or text from the process: a failure is one fixed
 * reason.
 */
import type { ApiClient, CallOptions } from "./client";
import type { SaveOptions } from "./settings";

export type ServerState = "stopped" | "starting" | "running" | "failed";

/** The fixed reasons of a `failed` state. */
export type ServerReason = "binary-invalid" | "model-invalid" | "not-loopback" | "port-in-use" | "exited" | "timeout" | "not-configured";

/** Who runs the llama.cpp Chat server: a server the user runs (such as the Llama app) or OMRS's own `llama-server`. */
export type ChatServerChoice = "external" | "managed";

/** Why a server route refused with 409. Absent on a save refused for a locked field or a stale revision. */
export type ServerConflictReason = "external-server" | "server-running";

export interface ServerField {
  id: string;
  label: string;
  /** `choice` is the Chat server choice: `external` or `managed`. */
  kind: "text" | "int" | "choice";
  /** The program path (empty when not set), the Chat server choice, the context window or the idle sleep. */
  value: string | number;
  min: number | null;
  max: number | null;
  source: "env" | "dotenv" | "config-file" | "default";
  locked: boolean;
  lock_reason: string | null;
}

export interface LlamacppServerStatus {
  status: "ok";
  /** Stamp of `omrs.jsonc` at this read. A save sends it back. */
  revision: string;
  state: ServerState;
  reason: ServerReason | null;
  exit_code: number | null;
  pid_running: boolean;
  /** What the live process was started with, or `null` when none is owned. */
  running_with: { context_window: number; model_kind: "file" | "hf" } | null;
  /** The saved program, window or idle sleep, or the Chat model in force, differ from the live process. */
  pending_restart: boolean;
  saved: { binary: ServerField; chat_server: ServerField; context_window: ServerField; idle_sleep: ServerField };
  /** The Chat choice in force. OMRS's own server loads this model while the choice is `managed`. */
  chat_model: {
    provider: string;
    model: string;
    /** The provider is `llamacpp` and the model is an existing `.gguf` file or a Hugging Face id. */
    usable: boolean;
  };
  /** The choice is `managed` and classification uses the Chat address, so the owned server answers it with the Chat model. */
  shared_with_classification: boolean;
}

/** Keys to save. An absent key stays as it is; `null` clears the saved value. */
export interface LlamacppServerChange {
  binary?: string | null;
  /** `null` clears the saved value, so `external` applies. */
  chat_server?: ChatServerChoice | null;
  context_window?: number | null;
  /** Seconds before the server frees its model; 0 turns sleep off. */
  idle_sleep?: number | null;
}

const PATH = "/v1/llamacpp/server";

export function getLlamacppServer(api: ApiClient, options: CallOptions = {}): Promise<LlamacppServerStatus> {
  return api.request<LlamacppServerStatus>("GET", PATH, { signal: options.signal });
}

/** Saves the program, the Chat server choice, the window or the idle sleep. A running server keeps running. */
export function saveLlamacppServer(api: ApiClient, change: LlamacppServerChange, options: SaveOptions = {}): Promise<LlamacppServerStatus> {
  return api.request<LlamacppServerStatus>("PUT", PATH, { body: { ...change, revision: options.revision }, signal: options.signal });
}

export function startLlamacppServer(api: ApiClient, options: CallOptions = {}): Promise<LlamacppServerStatus> {
  return api.request<LlamacppServerStatus>("POST", `${PATH}/start`, { signal: options.signal });
}

export function stopLlamacppServer(api: ApiClient, options: CallOptions = {}): Promise<LlamacppServerStatus> {
  return api.request<LlamacppServerStatus>("POST", `${PATH}/stop`, { signal: options.signal });
}

export function restartLlamacppServer(api: ApiClient, options: CallOptions = {}): Promise<LlamacppServerStatus> {
  return api.request<LlamacppServerStatus>("POST", `${PATH}/restart`, { signal: options.signal });
}
