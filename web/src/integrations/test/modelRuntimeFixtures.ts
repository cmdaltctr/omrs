import type { ModelRuntime } from "../../api/modelRuntimes";

export const GIB = 1024 ** 3;

/** The title of the router row. */
export const ROUTER_TITLE = "llama.cpp router";

/** One runtime item as `GET /v1/runtimes` sends it. A test overrides the fields it cares about. */
export function runtimeItem(id: string, extra: Partial<ModelRuntime> = {}): ModelRuntime {
  const role = id === "router" ? "router" : "ocr";
  return {
    id,
    role,
    mode: "managed",
    state: "stopped",
    reason: null,
    reason_text: null,
    memory_bytes: null,
    clients: "none",
    other_clients: "none",
    used_by: [],
    address: null,
    files_checked: true,
    models: [],
    ...extra,
  };
}

/** The router running with no other client, one failed OCR runtime and one external OCR runtime. */
export const RUNTIMES: ModelRuntime[] = [
  runtimeItem("router", {
    state: "running",
    memory_bytes: 6 * GIB,
    used_by: ["embed_provider", "metadata_llm_provider", "answer.provider"],
    address: "127.0.0.1:8080",
    models: [
      { model: "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0", roles: ["embeddings"], state: "loaded", reason: null, memory_bytes: 4 * GIB },
      { model: "Qwen/Qwen3-4B-GGUF:Q8_0", roles: ["classification"], state: "unloaded", reason: null, memory_bytes: null },
    ],
  }),
  runtimeItem("ocr-dots-mocr-llamacpp", {
    state: "failed",
    reason: "file-changed",
    reason_text: "The model file dots-mocr-Q8_0.gguf changed since it was provisioned. Provision the engine again.",
    used_by: ["ocr_engine_primary"],
  }),
  runtimeItem("ocr-paddleocr-vl-llamacpp", { mode: "external", state: "running", used_by: ["ocr_engine_fallback"], address: "127.0.0.1:9100", files_checked: false }),
];

export const SESSION_WITH_MANAGE = { status: "ok", kind: "session", scopes: ["manage", "read", "run"], workspace: "/home/u/.omrs/workspace" };
export const SESSION_READ_ONLY = { status: "ok", kind: "session", scopes: ["read"], workspace: null };
