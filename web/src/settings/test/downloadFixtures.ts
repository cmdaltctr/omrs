import type { ModelDownloadStatus, ModelFileList, ModelSearchReply, ModelSearchResult } from "../../api/modelDownloads";

/** Fixtures built from the `openapi.yaml` schemas for the model download routes. */
export const REVISION = "0123456789abcdef0123456789abcdef01234567";

export const IDLE: ModelDownloadStatus = {
  status: "ok",
  state: "idle",
  provider: null,
  model: null,
  model_value: null,
  bytes_done: 0,
  bytes_total: null,
  reason: null,
  cache_folder: null,
};

/** A download status built from the idle one with changed parts. */
export function downloadStatus(change: Partial<ModelDownloadStatus>): ModelDownloadStatus {
  return { ...IDLE, ...change };
}

export function searchResult(change: Partial<ModelSearchResult> & { id: string }): ModelSearchResult {
  return { source: "huggingface", downloads: 1200, likes: 10, gated: false, last_modified: "2026-10-01T09:00:00Z", ...change };
}

export function searchReply(provider: string, results: ModelSearchResult[], reason: ModelSearchReply["reason"] = null): ModelSearchReply {
  return { status: "ok", provider, results, reason };
}

const GIB = 1024 ** 3;

/** Three labels: the recommended Q4_K_M, a small Q2_K and the Q8_0 closest to full quality. */
export const FILES: ModelFileList = {
  status: "ok",
  repo: "unsloth/Qwen3-4B-GGUF",
  revision: REVISION,
  gated: false,
  reason: null,
  entries: [
    { label: "Q2_K", files: ["Qwen3-4B-Q2_K.gguf"], size_bytes: Math.round(1.5 * GIB), recommended: false, closest_to_full: false },
    { label: "Q4_K_M", files: ["Qwen3-4B-Q4_K_M.gguf"], size_bytes: Math.round(2.5 * GIB), recommended: true, closest_to_full: false },
    { label: "Q8_0", files: ["Qwen3-4B-Q8_0.gguf"], size_bytes: Math.round(4.2 * GIB), recommended: false, closest_to_full: true },
  ],
};
