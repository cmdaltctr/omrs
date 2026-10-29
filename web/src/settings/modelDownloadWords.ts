import type { DownloadReason, ModelDownloadStatus } from "../api/modelDownloads";

/** One plain sentence for each fixed reason. The text comes from this table and never from the host or a library. */
export const REASON_SENTENCES: Record<DownloadReason, string> = {
  busy: "Another model download is already running. Wait for it to finish, or cancel it.",
  "no-space": "There is not enough free disk space for this file. Free some space or pick a smaller file, then try again.",
  gated: "This model needs a Hugging Face access token. Set HF_TOKEN, restart omrs web, then try again.",
  "not-found": "Hugging Face has no such model or no GGUF file in it. Search again.",
  network: "The model host could not be reached. Check the connection, then try again.",
  stalled: "No data arrived for 60 seconds, so the download ended. Try again.",
  "ollama-unreachable": "Ollama did not answer at its address. Start Ollama, then try again.",
  failed: "The download failed. The server log in Settings has the details. Try again.",
};

/** After a cancel the page says only that the download stopped. */
export const CANCELLED_LINE = "The download stopped.";

export const SIZE_UNKNOWN_LINE = "Size known after the pull starts";

export const SEARCH_HINT = "Type at least 2 characters to search.";

const UNITS = ["B", "KiB", "MiB", "GiB", "TiB"];

/** A size in words, such as `2.5 GiB`. */
export function formatBytes(bytes: number): string {
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return unit === 0 ? `${value} B` : `${value.toFixed(1)} ${UNITS[unit]}`;
}

/** The bytes line of a running download with a known total, such as `1.0 GiB of 4.0 GiB`. */
export function bytesLine(done: number, total: number): string {
  return `${formatBytes(done)} of ${formatBytes(total)}`;
}

/** The share done as a whole percent, or `null` while the total is unknown or zero. */
export function percentDone(status: ModelDownloadStatus): number | null {
  if (status.bytes_total === null || status.bytes_total === 0) return null;
  return Math.min(100, Math.round((status.bytes_done / status.bytes_total) * 100));
}

const REASONS = Object.keys(REASON_SENTENCES);

/** The fixed reason in the body of a refused start (409 or 404), or `null` for any other error body. */
export function reasonFromBody(body: unknown): DownloadReason | null {
  if (typeof body !== "object" || body === null) return null;
  const reason = (body as Record<string, unknown>).reason;
  return typeof reason === "string" && REASONS.includes(reason) ? (reason as DownloadReason) : null;
}

/** True when a provider's model list holds the value. A tagless Ollama name matches its `:latest` entry. */
export function isListed(models: string[], value: string): boolean {
  return models.includes(value) || models.includes(`${value}:latest`);
}

export const NEED_RESTART_LINE = "Saved. The server loads the new model after a restart.";

export const EXTERNAL_SERVER_NOTE =
  "Your own llama.cpp server must load this model. The Llama app lists new models only when it starts, so quit and reopen it, then press Refresh models.";

export const NOT_LISTED_LINE = "Your server does not list it yet. Quit and reopen the Llama app, then press Refresh models again.";

export const NO_ANSWER_LINE = "Your server did not answer at the chat address. Check that it runs, then press Refresh models.";
