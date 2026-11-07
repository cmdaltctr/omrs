import type { ChatSettings, Connection, ConnectionList, JudgeSettings, LogRecord, McpState, ProviderField, WebPortState } from "../../api/settings";
import { DOCUMENT_READING_KEYS, type DocumentReadingKey, type DocumentReadingSetting, type DocumentReadingState } from "../../api/settingsDocumentReading";
import { documentsServer, type Handler } from "../../test/fakeDocumentsServer";
import { IDLE } from "./downloadFixtures";
import { DOWNLOADS_NEEDED_NONE, ROUTER_STOPPED } from "./llamacppFixtures";
import { IDLE_INSTALL, integrationsBody } from "./pdfReaderFixtures";
import { decisionModels, documentRouters } from "./routerFixtures";

/** Fixtures built from the `openapi.yaml` schemas for the Settings routes. */
export const CONFIG_DIR = "/srv/omrs project";

const NO_KEY = { min: null, max: null, value: null, required: true, set: false, last4: null, state: null, locked: false, lock_reason: null, group: null, follows: null } as const;

export function urlField(id: string, label: string, value: string, source: ProviderField["source"] = "default", lock?: string): ProviderField {
  return { id, label, kind: "url", group: null, follows: null, min: null, max: null, value, source, locked: lock !== undefined, lock_reason: lock ?? null, required: true, set: false, last4: null, state: null };
}

export function intField(id: string, label: string, value: number, source: ProviderField["source"] = "default", lock?: string): ProviderField {
  return { id, label, kind: "int", group: null, follows: null, min: 2048, max: 262144, value, source, locked: lock !== undefined, lock_reason: lock ?? null, required: true, set: true, last4: null, state: null };
}

export { EMBED_ENTRY, EMBED_MODEL, ROUTER_EXTERNAL, ROUTER_RUNNING, ROUTER_STOPPED, routerEntry, routerStatus, TEXT_ENTRY, TEXT_MODEL, WITH_CREDENTIALS } from "./llamacppFixtures";

export const OLLAMA: Connection = {
  provider: "ollama",
  display_name: "Ollama",
  locality: "local",
  installed: true,
  install_hint: null,
  model_source: "ollama-pull",
  fields: [urlField("base_url", "Address", "http://127.0.0.1:11434")],
  read_only: [{ label: "Answer model", value: "qwen3", group: null }],
  roles: ["answers", "metadata"],
};

export const LLAMACPP: Connection = {
  provider: "llamacpp",
  display_name: "llama.cpp",
  locality: "local",
  installed: true,
  install_hint: null,
  model_source: "huggingface-gguf",
  fields: [urlField("router_url", "Router address", "http://127.0.0.1:8080/v1")],
  read_only: [
    { label: "Router mode", value: "managed", group: null },
    { label: "Embedding model", value: "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0", group: null },
    { label: "Text model (classification)", value: "Qwen/Qwen3-4B-GGUF:Q8_0", group: null },
  ],
  roles: ["embeddings"],
};

export const OPENROUTER: Connection = {
  provider: "openrouter",
  display_name: "OpenRouter",
  locality: "cloud",
  installed: true,
  install_hint: null,
  model_source: null,
  fields: [
    { id: "api_key", label: "API key", kind: "secret", source: "keychain", ...NO_KEY, set: true, last4: "wxyz" },
  ],
  read_only: [{ label: "Verification model", value: "openai/gpt-5-mini", group: null }],
  roles: ["verification"],
};

export const CONNECTIONS: ConnectionList = { status: "ok", revision: "r1", config_dir: CONFIG_DIR, user_config_dir: "~/.config/omrs", keychain: "available", connections: [OLLAMA, LLAMACPP, OPENROUTER] };

export const CHAT_READY: ChatSettings = {
  status: "ok",
  revision: "r1",
  provider: "ollama",
  model: "qwen3:4b",
  source: "config-file",
  locked: false,
  lock_reason: null,
  enabled: true,
  ready: true,
  reason: null,
};

/** The claim check judge when no source sets it: the `cloud` alias with no model. */
export const JUDGE_DEFAULT: JudgeSettings = {
  status: "ok",
  revision: "r1",
  provider: "cloud",
  resolved_provider: "openrouter",
  model: "",
  source: "default",
  locked: false,
  lock_reason: null,
  enabled: true,
  ready: false,
  reason: "no-model",
};

/** A judge saved in `omrs.jsonc`, with an OpenRouter key set. */
export const JUDGE_SAVED: JudgeSettings = { ...JUDGE_DEFAULT, provider: "openrouter", model: "openai/gpt-5-mini", source: "config-file", ready: true, reason: null };

export const MCP_OFF: McpState = {
  status: "ok",
  revision: "r1",
  enabled: false,
  source: "default",
  url: "http://127.0.0.1:8765/mcp",
  token: { exists: false, created_at: null },
};

export const WEB_PORT: WebPortState = { status: "ok", revision: "r1", saved: null, bound: 8765 };

/** The rows the page shows. The three old single-value keys can stay valid in requests, and the server may leave their rows out. */
const READING_DEFAULTS: Partial<Record<DocumentReadingKey, DocumentReadingSetting["value"]>> = {
  pdf_readers: ["pdf_inspector", "liteparse", "pypdf"],
  ocr_fallback_enabled: true,
  ocr_routing_unit: "page",
  ocr_engines: ["dots-mocr", "paddleocr-vl"],
  ocr_skip_blank_pages: true,
  ocr_maths_routing_enabled: true,
  ocr_non_latin_routing: "off",
  document_router: "",
  ocr_local_backends: ["pp-ocrv6-small"],
  ocr_local_cuts: {},
};

/** `GET /v1/settings/document-reading` with every key at its default, nothing saved and one engine not provisioned. */
export const DOCUMENT_READING: DocumentReadingState = {
  status: "ok",
  revision: "r1",
  settings: DOCUMENT_READING_KEYS.filter((key) => key in READING_DEFAULTS).map((key) => ({
    key,
    value: READING_DEFAULTS[key]!,
    saved: null,
    source: "default",
    locked: false,
    lock_reason: null,
    restart_pending: false,
    default: READING_DEFAULTS[key]!,
  })),
  pdf_readers: [
    { name: "auto", available: true, reason: null },
    { name: "pypdf", available: true, reason: null },
    { name: "pypdfium2", available: false, reason: "The package 'pypdfium2' is not installed." },
    { name: "liteparse", available: true, reason: null },
    { name: "pdf_inspector", available: true, reason: null },
  ],
  pdf_reader_in_use: "pdf_inspector",
  local_ocr_backends: [{ name: "pp-ocrv6-small", available: true, reason: null, default_cut: 0.92 }],
  retired_keys: [],
  ocr: {
    workers_dir: "~/ocr-workers",
    engines: [
      { name: "dots-mocr", available: true, reason: null },
      { name: "paddleocr-vl", available: false, reason: "Not provisioned. Run python3 ocr-workers/provision.py paddleocr-vl." },
    ],
  },
};

/** The default document reading state with changed rows and top-level parts. */
export function readingState(rows: Partial<Record<DocumentReadingKey, Partial<DocumentReadingSetting>>> = {}, change: Partial<DocumentReadingState> = {}): DocumentReadingState {
  return { ...DOCUMENT_READING, ...change, settings: DOCUMENT_READING.settings.map((row) => ({ ...row, ...rows[row.key] })) };
}

export function logRecord(seq: number, level: LogRecord["level"], message: string, logger = "omrs.server"): LogRecord {
  return { seq, time: `2026-10-14T09:30:${String(seq).padStart(2, "0")}Z`, level, logger, message };
}

/** The documents server plus a default answer for every route Settings reads. */
export function settingsServer(handlers: Record<string, Handler> = {}) {
  return documentsServer({
    "GET /v1/health": () => ({ status: "ok", ready: true, version: "2.0.0" }),
    "GET /v1/session": () => ({ status: "ok", kind: "session", scopes: ["files", "graph", "read", "run"], workspace: "/home/u/.omrs/workspace" }),
    "GET /v1/pipeline-operations": () => ({
      status: "ok",
      operations: [
        { operation_id: "retrieve.dense", title: "Dense retrieval", available: true, capabilities: [] },
        { operation_id: "rerank.cross_encoder", title: "Cross-encoder rerank", available: false, capabilities: ["reranker"] },
      ],
    }),
    "GET /v1/connections": () => CONNECTIONS,
    "GET /v1/llamacpp/router": () => ROUTER_STOPPED,
    "GET /v1/llamacpp/router/downloads-needed": () => DOWNLOADS_NEEDED_NONE,
    "GET /v1/model-downloads/current": () => IDLE,
    "GET /v1/settings/chat": () => CHAT_READY,
    "GET /v1/settings/judge": () => JUDGE_DEFAULT,
    "GET /v1/logs": () => ({ status: "ok", records: [], last_seq: 0 }),
    "GET /v1/mcp": () => MCP_OFF,
    "GET /v1/settings/web-port": () => WEB_PORT,
    "GET /v1/settings/document-reading": () => DOCUMENT_READING,
    "GET /v1/settings/decision-models": () => decisionModels([]),
    "GET /v1/settings/document-routers": () => documentRouters([]),
    "GET /v1/integrations": () => integrationsBody(),
    "GET /v1/integrations/install": () => ({ status: "ok", install: IDLE_INSTALL }),
    ...handlers,
  });
}
