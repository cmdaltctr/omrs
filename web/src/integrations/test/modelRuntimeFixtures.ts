import type { ModelRuntime } from "../../api/modelRuntimes";

const GIB = 1024 ** 3;

/** One runtime item as `GET /v1/runtimes` sends it. A test overrides the fields it cares about. */
export function runtimeItem(id: string, extra: Partial<ModelRuntime> = {}): ModelRuntime {
  const role = id === "chat" ? "chat" : id === "embeddings" ? "embeddings" : "ocr";
  return {
    id,
    role,
    mode: "managed",
    state: "stopped",
    reason: null,
    reason_text: null,
    memory_bytes: null,
    clients: "none",
    used_by: [],
    address: null,
    files_checked: true,
    ...extra,
  };
}

/** Chat running with no other client, embeddings running with a client, one failed OCR runtime and one external OCR runtime. */
export const RUNTIMES: ModelRuntime[] = [
  runtimeItem("chat", { state: "running", memory_bytes: 6 * GIB, used_by: ["llamacpp_chat_server"], address: "127.0.0.1:8081" }),
  runtimeItem("embeddings", { state: "running", memory_bytes: GIB / 2, clients: "some", used_by: ["llamacpp_embed_server"], address: "127.0.0.1:8080" }),
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
