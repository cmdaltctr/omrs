import type { LlamacppRouterStatus, RouterField, RouterModel } from "../../api/llamacppRouter";

/** Fixtures built from the `openapi.yaml` schemas for the llama.cpp router routes. */

export const EMBED_MODEL = "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0";
export const TEXT_MODEL = "Qwen/Qwen3-4B-GGUF:Q8_0";

function routerField(id: string, label: string, kind: RouterField["kind"], value: string | number, change: Partial<RouterField> = {}): RouterField {
  const range = kind === "int" ? { min: 1, max: 16 } : { min: null, max: null };
  return { id, label, kind, value, default: value, ...range, source: "default", locked: false, lock_reason: null, ...change };
}

/** The shipped embedding entry: no file yet, so "Not downloaded". */
export const EMBED_ENTRY: RouterModel = {
  id: "qwen3-embedding-4b",
  model: EMBED_MODEL,
  roles: ["embeddings"],
  file: null,
  projector: null,
  ctx_size: 8192,
  preset: { embeddings: true, pooling: "last", "embd-normalize": 2, "ctx-size": 8192, "batch-size": 8192, "ubatch-size": 8192, parallel: 1, "kv-unified": false },
  state: "not-downloaded",
  reason: null,
  reason_text: null,
  note: null,
  reload_pending: false,
};

/** The shipped text entry: classification only. */
export const TEXT_ENTRY: RouterModel = {
  id: "qwen3-4b",
  model: TEXT_MODEL,
  roles: ["classification"],
  file: null,
  projector: null,
  ctx_size: 32768,
  preset: { "ctx-size": 32768, parallel: 2 },
  state: "not-downloaded",
  reason: null,
  reason_text: null,
  note: null,
  reload_pending: false,
};

/** An entry for tests, built from the text one with changed parts. */
export function routerEntry(change: Partial<RouterModel>): RouterModel {
  return { ...TEXT_ENTRY, ...change };
}

type SavedKey = keyof LlamacppRouterStatus["saved"];
const SAVED_KEYS: SavedKey[] = ["binary", "router_server", "router_url", "models_max", "memory_margin_mib"];

/** A fresh install: managed mode, nothing set, nothing running, the shipped two entries. */
export const ROUTER_STOPPED: LlamacppRouterStatus = {
  status: "ok",
  revision: "r1",
  state: "stopped",
  reason: null,
  reason_text: null,
  mode: "managed",
  address: "127.0.0.1:8080",
  running_with: null,
  pending_restart: false,
  program: { path: "", source: "none" },
  saved: {
    binary: routerField("llamacpp_server_binary", "Program path", "text", ""),
    router_server: routerField("llamacpp_router_server", "Who runs llama.cpp", "choice", "managed"),
    router_url: routerField("llamacpp_router_url", "Router address", "url", "http://127.0.0.1:8080/v1"),
    models_max: routerField("llamacpp_router_models_max", "Models loaded at once", "int", 4),
    memory_margin_mib: routerField("llamacpp_router_memory_margin_mib", "Free memory margin (MiB)", "int", 8192, { min: 0, max: 262144 }),
  },
  models: [EMBED_ENTRY, TEXT_ENTRY],
};

/** A router status built from the fresh one with changed parts. */
export function routerStatus(change: Partial<LlamacppRouterStatus>, saved: Partial<Record<SavedKey, Partial<RouterField>>> = {}): LlamacppRouterStatus {
  const merged = { ...ROUTER_STOPPED.saved };
  for (const key of SAVED_KEYS) merged[key] = { ...merged[key], ...saved[key] };
  return { ...ROUTER_STOPPED, ...change, saved: merged };
}

/** Managed router with a program, running with the saved limits. */
export const ROUTER_RUNNING = routerStatus({
  state: "running",
  program: { path: "/opt/omrs/llama-server", source: "provisioned" },
  running_with: { models_max: 4, memory_margin_mib: 8192 },
});

/** The same router in `external` mode, at a Llama app address. */
export const ROUTER_EXTERNAL = routerStatus(
  { mode: "external", address: "127.0.0.1:9931" },
  { router_server: { value: "external", source: "config-file" }, router_url: { value: "http://127.0.0.1:9931/v1", source: "config-file" } },
);

/** A session with `manage` and `credentials`, which the Router panel's saves need. */
export const WITH_CREDENTIALS = { "GET /v1/session": () => ({ status: "ok", kind: "session", scopes: ["credentials", "files", "graph", "manage", "read", "run"], workspace: "/home/u/.omrs/workspace" }) };
