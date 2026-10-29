/**
 * Typed client for the model search and download routes under
 * `/v1/model-downloads`. Shapes follow `openapi.yaml` (`searchModels`,
 * `listModelFiles`, `startModelDownload`, `getModelDownload`,
 * `cancelModelDownload`). A failure is one fixed reason, never text from a
 * library or from Hugging Face.
 */
import { queryOptions } from "@tanstack/react-query";
import type { ApiClient, CallOptions } from "./client";
import { listProviderModels } from "./settings";

/** Where a provider gets models from. `null` on a connection means the provider has no model source. */
export type ModelSource = "huggingface-gguf" | "ollama-pull";

export interface ModelSearchResult {
  /** `org/name`, a built-in Ollama library name, or (in an `ollama` search) `hf.co/org/name`. */
  id: string;
  source: "huggingface" | "ollama-library";
  downloads: number | null;
  likes: number | null;
  /** The repo needs `HF_TOKEN` for a download. */
  gated: boolean;
  last_modified: string | null;
}

export interface ModelSearchReply {
  status: "ok";
  provider: string;
  results: ModelSearchResult[];
  /** `network` when Hugging Face did not answer. */
  reason: "network" | null;
}

export interface ModelFileEntry {
  /** The quantisation label, such as `Q4_K_M`. */
  label: string;
  files: string[];
  size_bytes: number;
  /** The label to preselect. */
  recommended: boolean;
  /** `Q8_0`. */
  closest_to_full: boolean;
}

export interface ModelFileList {
  status: "ok";
  repo: string;
  /** The commit the entries come from; a download sends it back. `null` when `reason` is `network`. */
  revision: string | null;
  gated: boolean;
  entries: ModelFileEntry[];
  reason: "network" | null;
}

/** The fixed reasons of a `failed` job (and of a refused start: `busy`, `no-space`, `gated`). */
export type DownloadReason = "busy" | "no-space" | "gated" | "not-found" | "network" | "stalled" | "ollama-unreachable" | "failed";

export type DownloadState = "idle" | "running" | "succeeded" | "failed" | "cancelled";

export interface ModelDownloadStatus {
  status: "ok";
  state: DownloadState;
  provider: string | null;
  /** `org/name:LABEL` or the pull name, for display. */
  model: string | null;
  /** The value to save as the model. Set only when `state` is `succeeded`. */
  model_value: string | null;
  bytes_done: number;
  /** `null` while unknown (an Ollama pull before its first layer reports a size). */
  bytes_total: number | null;
  reason: DownloadReason | null;
  /** For llama.cpp, the folder that holds the files, with `~` for home. */
  cache_folder: string | null;
}

/** `llamacpp`: repo, revision and label. `ollama`: repo and label, or a library name alone. */
export interface StartModelDownload {
  provider: string;
  repo?: string;
  revision?: string;
  label?: string;
  name?: string;
}

const PATH = "/v1/model-downloads";

export function searchModels(api: ApiClient, provider: string, q: string, options: CallOptions = {}): Promise<ModelSearchReply> {
  return api.request<ModelSearchReply>("GET", `${PATH}/search`, { query: { provider, q }, signal: options.signal });
}

export function listModelFiles(api: ApiClient, provider: string, repo: string, options: CallOptions = {}): Promise<ModelFileList> {
  return api.request<ModelFileList>("GET", `${PATH}/files`, { query: { provider, repo }, signal: options.signal });
}

export function startModelDownload(api: ApiClient, request: StartModelDownload, options: CallOptions = {}): Promise<ModelDownloadStatus> {
  return api.request<ModelDownloadStatus>("POST", PATH, { body: request, signal: options.signal });
}

export function getModelDownload(api: ApiClient, options: CallOptions = {}): Promise<ModelDownloadStatus> {
  return api.request<ModelDownloadStatus>("GET", `${PATH}/current`, { signal: options.signal });
}

export function cancelModelDownload(api: ApiClient, options: CallOptions = {}): Promise<ModelDownloadStatus> {
  return api.request<ModelDownloadStatus>("DELETE", `${PATH}/current`, { signal: options.signal });
}

export const modelDownloadKeys = {
  current: () => ["model-downloads", "current"] as const,
  search: (provider: string, q: string) => ["model-downloads", "search", provider, q] as const,
  files: (provider: string, repo: string) => ["model-downloads", "files", provider, repo] as const,
  /** The models a running provider holds, as `POST /v1/connections/{provider}/models` lists them. */
  providerModels: (provider: string) => ["connections", provider, "models"] as const,
};

/** Interval between reads of the current download while it runs. */
export const DOWNLOAD_POLL_MS = 1000;

export const modelDownloadQuery = (api: ApiClient) =>
  queryOptions({
    queryKey: modelDownloadKeys.current(),
    queryFn: ({ signal }) => getModelDownload(api, { signal }),
    // Poll only while a job runs: every other state is final until the next start.
    refetchInterval: (query) => (query.state.data?.state === "running" ? DOWNLOAD_POLL_MS : false),
  });

export const modelSearchQuery = (api: ApiClient, provider: string, q: string) =>
  queryOptions({ queryKey: modelDownloadKeys.search(provider, q), queryFn: ({ signal }) => searchModels(api, provider, q, { signal }), staleTime: 60_000 });

export const modelFilesQuery = (api: ApiClient, provider: string, repo: string) =>
  queryOptions({ queryKey: modelDownloadKeys.files(provider, repo), queryFn: ({ signal }) => listModelFiles(api, provider, repo, { signal }), staleTime: 60_000 });

/** The model names a provider lists now. Contacts the provider, so callers enable it on purpose. */
export const providerModelsQuery = (api: ApiClient, provider: string) =>
  queryOptions({ queryKey: modelDownloadKeys.providerModels(provider), queryFn: ({ signal }) => listProviderModels(api, provider, {}, { signal }) });
