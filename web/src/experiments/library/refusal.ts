import { ApiError } from "../../api/client";
import { describeSaveError } from "../../lib/errors";
import { formatRoute } from "../../lib/routes";

/** The marimo card on the Integrations page, where marimo is installed with jupytext (ADR-101). */
export const MARIMO_CARD = formatRoute({ area: "integrations", entry: "marimo" });

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
  tool_install_running: "marimo is being installed or removed on the Integrations page. Wait until that job ends, then open again.",
} as const;

/** Refusals that the marimo card can fix or that come from its job. */
const MARIMO_CARD_REASONS = new Set(["converter_missing", "tool_install_running"]);

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

/** True when a refused "Open in marimo" points at the marimo card: jupytext is missing, or the card's job runs. */
export function refusalLinksToMarimoCard(error: unknown): boolean {
  const reason = refusalBody(error)?.reason;
  return typeof reason === "string" && MARIMO_CARD_REASONS.has(reason);
}

/** The page's own line for each 409 reason of a refused save of protocol.md or the report. */
export const SAVE_REFUSALS = {
  changed_on_disk: "This file changed on disk after you opened it. Copy your text, select Reload, then add your changes again.",
  edit_log_unusable: "edits.jsonl in this experiment folder is a link or not a regular file, so the app cannot record the edit. Replace it with a regular file.",
} as const;

/** The plain 500 lines of a failed save. Each one says whether the file changed, so the page shows it as it is. */
const SAVE_FAILURES = new Set([
  "The file was not saved.",
  "The file was not saved, because the app could not record the edit in edits.jsonl.",
  "The file was saved, but the edit was not recorded in edits.jsonl. Run git diff on the file to see the change.",
]);

/** The 409 reason of a refused save, or null for any other failure. */
export function saveRefusalReason(error: unknown): keyof typeof SAVE_REFUSALS | null {
  const reason = refusalBody(error)?.reason;
  return typeof reason === "string" && Object.hasOwn(SAVE_REFUSALS, reason) ? (reason as keyof typeof SAVE_REFUSALS) : null;
}

/**
 * One line for a failed save. A 409 reason shows the page's own line. A 500
 * shows the server line only when it is one of the known plain lines, which
 * say whether the file was saved. Every other failure goes through `refusalLine`.
 */
export function saveRefusalLine(error: unknown): string {
  const reason = saveRefusalReason(error);
  if (reason !== null) {
    console.error(error instanceof Error ? error.message : String(error), error);
    return SAVE_REFUSALS[reason];
  }
  if (error instanceof ApiError && error.kind === "http" && error.status === 500) {
    const message = typeof error.body === "object" && error.body !== null ? (error.body as { message?: unknown }).message : undefined;
    if (typeof message === "string" && SAVE_FAILURES.has(message)) {
      console.error(message, error);
      return message;
    }
  }
  return refusalLine(error);
}
