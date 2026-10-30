import { ApiError } from "../api/client";
import type { LlamacppServerStatus, ServerConflictReason, ServerReason, ServerState } from "../api/llamacppServer";

export const STATE_NAMES: Record<ServerState, string> = {
  stopped: "Stopped",
  starting: "Starting",
  running: "Running",
  failed: "Failed",
};

const REASON_SENTENCES: Record<Exclude<ServerReason, "exited" | "not-configured">, string> = {
  "binary-invalid": "The program path is not a runnable file named llama-server.",
  "model-invalid": "The Chat model is not an existing .gguf file or a Hugging Face id.",
  "not-loopback": "The chat address is not on this machine, so omrs will not start a server for it.",
  "port-in-use": "Another program already uses the chat port. omrs did not touch it.",
  timeout: "The server did not become ready in time and was stopped.",
};

const LOG_HINT = "See llamacpp-server.log in the workspace folder.";

/** One plain sentence for a failure reason. The text comes from this table and never from the process. */
export function reasonSentence(status: LlamacppServerStatus): string {
  const reason = status.reason;
  if (reason === null) return "";
  if (reason === "exited") {
    return status.exit_code === null ? `The server stopped by itself. ${LOG_HINT}` : `The server stopped by itself with exit code ${status.exit_code}. ${LOG_HINT}`;
  }
  if (reason === "not-configured") return status.saved.binary.value === "" ? "Set the program path first." : "Choose llama.cpp and a Chat model in Settings > Chat first.";
  return REASON_SENTENCES[reason] ?? "The server could not start.";
}

/** The status line: the state in words and, for a failure, its sentence. */
export function statusLine(status: LlamacppServerStatus): string {
  const name = STATE_NAMES[status.state];
  return status.state === "failed" ? `${name}: ${reasonSentence(status)}` : name;
}

/** The warning while classification goes to OMRS's own Chat server, in the panel and in the Classification block (design D6). */
export const SHARED_ADDRESS_WARNING =
  "Classification goes to OMRS's own Chat server, which loads only the Chat model. The Text model is not used. Set a Classification address, for example the Llama app, to keep them apart.";

/** One plain line for each 409 reason of the server routes. */
export const CONFLICT_SENTENCES: Record<ServerConflictReason, string> = {
  "external-server": "OMRS does not start a server while the Chat server is the Llama app or another server you run.",
  "server-running": "Stop OMRS's own server first, then choose another server.",
};

/** The reason of a 409 from a server route, or `null` for any other failure (a locked field or a stale revision has none). */
export function conflictReason(error: unknown): ServerConflictReason | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const reason = (error.body as { reason?: unknown } | null | undefined)?.reason;
  return reason === "external-server" || reason === "server-running" ? reason : null;
}
