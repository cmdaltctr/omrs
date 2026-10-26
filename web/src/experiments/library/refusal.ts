import { ApiError } from "../../api/client";
import { describeSaveError } from "../../lib/errors";

/**
 * One line for a refused library request. A 400 or 409 shows the server's
 * reason, which names the rule (for example a missing `experiments`
 * directory or a folder that exists). Every other failure keeps the generic
 * friendly line, and the raw text goes to the console.
 */
export function refusalLine(error: unknown): string {
  return describeSaveError(error).message;
}

/** The page's own line for each refusal of "Open in marimo" that needs no detail from the server. */
export const EDITOR_REFUSALS = {
  editor_unavailable: "marimo is not ready to open notebooks. Check it in Experiments, Code editor.",
  editor_unsupported: "The registered marimo manifest cannot open Library notebooks. Register marimo again with the shipped manifest.",
  no_project_environment: "This project has no usable .venv folder. Run uv sync in the project folder, then try again.",
  project_config_runs_on_open: "The project pyproject.toml runs notebook cells on open, or cannot be read. Turn off auto_instantiate, then try again.",
  notebook_not_regular: "analysis.marimo.py in this folder is a link or not a regular file. Remove it, then try again.",
  editor_running: "marimo is already open for this experiment.",
  conversion_failed: "marimo could not convert analysis.py. Check the script, then try again.",
  no_free_port: "Ports 2719 to 2721 are busy. Stop another editor, then try again.",
  launch_failed: "marimo did not start. Recheck it in Experiments, Code editor, then try again.",
} as const;

function refusalBody(error: unknown): { reason?: unknown; launch_id?: unknown } | null {
  if (!(error instanceof ApiError) || error.kind !== "http" || error.status !== 409) return null;
  return typeof error.body === "object" && error.body !== null ? (error.body as { reason?: unknown; launch_id?: unknown }) : null;
}

/**
 * One line for a refused "Open in marimo". A known reason shows the page's
 * own line and sends the server text to the console. Every other refusal,
 * `python_mismatch` and `converter_missing` among them, goes through
 * `refusalLine`, so the server line names the two Python versions or the
 * install command.
 */
export function editorRefusalLine(error: unknown): string {
  const reason = refusalBody(error)?.reason;
  if (typeof reason === "string" && Object.hasOwn(EDITOR_REFUSALS, reason)) {
    console.error(error instanceof Error ? error.message : String(error), error);
    return EDITOR_REFUSALS[reason as keyof typeof EDITOR_REFUSALS];
  }
  return refusalLine(error);
}

/** The launch id of the editor that already runs, from an `editor_running` refusal. */
export function refusalLaunchId(error: unknown): string | null {
  const body = refusalBody(error);
  if (body?.reason !== "editor_running") return null;
  return typeof body.launch_id === "string" ? body.launch_id : null;
}
