/**
 * The words of the Router panel, the model table and the Chat model choice
 * (change one-llamacpp-router). They live in one file so tests pin them.
 */
import { ApiError } from "../api/client";
import type { LlamacppRouterStatus, RouterConflictReason, RouterMode, RouterModel, RouterModelState, RouterRole, RouterState } from "../api/llamacppRouter";

export const STATE_NAMES: Record<RouterState, string> = {
  stopped: "Stopped",
  starting: "Starting",
  running: "Running",
  failed: "Failed",
};

/** The label of the mode row. The server's own label is longer. */
export const MODE_LABEL = "Who runs llama.cpp";

export const MODE_NAMES: Record<RouterMode, string> = {
  managed: "OMRS runs llama.cpp",
  external: "Use this address",
};

/** Said while the mode is `external`: OMRS does not start the router or read its files. */
export const EXTERNAL_NOTE = "External server: OMRS does not check model files or presets.";

export const NEEDS_CREDENTIALS = "Changing this needs a session with the credentials scope.";

/** One plain line of help under each router limit. */
export const LIMIT_HELP: Record<"models_max" | "memory_margin_mib", string> = {
  models_max: "How many models the router keeps in memory at the same time.",
  memory_margin_mib: "Memory that the router leaves free, in MiB.",
};

/** Said after each problem line. The line itself is the server's own text. */
export const PROBLEM_ACTION = "Edit the list below or choose another model.";

/** One plain line for each 409 reason of the router routes. */
export const CONFLICT_SENTENCES: Record<RouterConflictReason, string> = {
  "external-server": "OMRS does not start a router while the mode is Use this address.",
  "in-use": "This model holds a role. Give the role to another model first.",
  busy: "An install is already running. Wait for it to finish.",
};

/** The reason of a 409 from a router route, or `null` for any other failure (a locked field or a stale revision has none). */
export function conflictReason(error: unknown): RouterConflictReason | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const reason = (error.body as { reason?: unknown } | null | undefined)?.reason;
  return reason === "external-server" || reason === "in-use" || reason === "busy" ? reason : null;
}

/** The status line: the state in words and, for a failure, its plain reason line. */
export function statusLine(status: LlamacppRouterStatus): string {
  const name = STATE_NAMES[status.state];
  return status.state === "failed" ? `${name}: ${status.reason_text ?? "The router could not start."}` : name;
}

export const MODEL_STATE_NAMES: Record<RouterModelState, string> = {
  "not-downloaded": "Not downloaded",
  unloaded: "Unloaded",
  loading: "Loading",
  loaded: "Loaded",
  failed: "Failed",
};

export const ROLE_NAMES: Record<RouterRole, string> = {
  embeddings: "Embeddings",
  classification: "Classification",
  chat: "Chat",
  judge: "Claim check",
  decision: "Decision",
};

export const SHARED_ROW_WARNING = "Shared by Chat and classification";

/** The note in Settings > Chat while Chat uses the classification model. */
export const SHARED_NOTE = "Chat and classification share this model. A long Chat answer can slow classification during an ingest. A context size change reloads the model for both.";

/** True when the entry holds both the Chat and the classification role. */
export function isSharedEntry(entry: RouterModel): boolean {
  return entry.roles.includes("chat") && entry.roles.includes("classification");
}
