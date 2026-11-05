/**
 * Typed client for the decision model and document router routes
 * (`listDecisionModels`, `saveDecisionModel`, `deleteDecisionModel`,
 * `testDecisionModel`, `listDocumentRouters`, `saveDocumentRouter`,
 * `deleteDocumentRouter`, `renameDocumentRouter` in `openapi.yaml`, ADR-110).
 * No answer holds a key: `key_state` says whether a reference is set.
 */
import type { ApiClient, CallOptions } from "./client";
import type { SaveOptions } from "./settings";

export type DecisionKind = "cloudflare" | "llamacpp" | "ollama" | "typesafe";

export type KeyState = "not-needed" | "not-set" | "reference-set" | "resolvable" | "unresolvable";

export interface DecisionKindOption {
  name: DecisionKind;
  /** No live request of this kind is recorded. Settings shows "Not yet tested". */
  not_yet_tested: boolean;
}

export interface DecisionModelItem {
  name: string;
  kind: DecisionKind;
  address: string;
  model: string;
  images: boolean;
  server: "external" | "managed" | null;
  model_file: string | null;
  projector_file: string | null;
  model_sha256: string | null;
  projector_sha256: string | null;
  /** The address is not a loopback address. */
  hosted: boolean;
  key_state: KeyState;
  not_yet_tested: boolean;
  /** The routers that name this entry, sorted. */
  used_by: string[];
}

export interface DecisionModelList {
  status: "ok";
  revision: string;
  kinds: DecisionKindOption[];
  models: DecisionModelItem[];
}

/** The fields a save writes. `key` holds a reference only: `env://`, `file://` or `keychain://`. */
export interface DecisionModelEntry {
  kind: DecisionKind;
  address: string;
  model: string;
  images?: boolean;
  key?: string;
  server?: "external" | "managed";
  model_file?: string;
  projector_file?: string;
  model_sha256?: string;
  projector_sha256?: string;
}

export type DecisionTestResult = "ok" | "unknown-model" | "unreachable" | "quantisation-refused" | "projector-not-loaded" | "wrong-build" | "request-failed" | "malformed-reply";

export interface DecisionModelTest {
  status: "ok";
  name: string;
  result: DecisionTestResult;
  quantisation: string;
  projector: string | null;
  build: string | null;
}

export interface DocumentRouterItem {
  name: string;
  /** The decision model entry name. */
  model: string;
  question: string;
  threshold: number;
  images: boolean;
  max_chars: number;
  send_off_machine: boolean;
  model_kind: DecisionKind | null;
  hosted: boolean;
  /** A hosted router that sends page images. */
  experimental: boolean;
  will_run: boolean;
  will_not_run_reason: "unknown-model" | "needs-opt-in" | null;
  /** The saved `document_router` names this router. */
  host: boolean;
  /** Titles of the saved user profiles whose Read document step names this router. */
  used_by: string[];
}

export interface DocumentRouterList {
  status: "ok";
  revision: string;
  routers: DocumentRouterItem[];
}

export interface DocumentRouterEntry {
  model: string;
  question: string;
  threshold: number;
  images: boolean;
  max_chars: number;
  send_off_machine: boolean;
}

const MODELS = "/v1/settings/decision-models";
const ROUTERS = "/v1/settings/document-routers";
const named = (base: string, name: string) => `${base}/${encodeURIComponent(name)}`;

export function listDecisionModels(api: ApiClient, options: CallOptions = {}): Promise<DecisionModelList> {
  return api.request<DecisionModelList>("GET", MODELS, { signal: options.signal });
}

export function saveDecisionModel(api: ApiClient, name: string, entry: DecisionModelEntry, options: SaveOptions = {}): Promise<DecisionModelList> {
  return api.request<DecisionModelList>("PUT", named(MODELS, name), { body: { entry, revision: options.revision }, signal: options.signal });
}

/** A router that names the entry gets 409 `in-use`, and the message names the router. */
export function deleteDecisionModel(api: ApiClient, name: string, options: SaveOptions = {}): Promise<DecisionModelList> {
  return api.request<DecisionModelList>("DELETE", named(MODELS, name), { body: { revision: options.revision }, signal: options.signal });
}

/** Contacts the entry's server, which can be hosted. */
export function testDecisionModel(api: ApiClient, name: string, options: CallOptions = {}): Promise<DecisionModelTest> {
  return api.request<DecisionModelTest>("POST", `${named(MODELS, name)}/test`, { signal: options.signal });
}

export function listDocumentRouters(api: ApiClient, options: CallOptions = {}): Promise<DocumentRouterList> {
  return api.request<DocumentRouterList>("GET", ROUTERS, { signal: options.signal });
}

export function saveDocumentRouter(api: ApiClient, name: string, entry: DocumentRouterEntry, options: SaveOptions = {}): Promise<DocumentRouterList> {
  return api.request<DocumentRouterList>("PUT", named(ROUTERS, name), { body: { entry, revision: options.revision }, signal: options.signal });
}

/** The host setting or a saved profile that names the router gets 409 `in-use`, and the message names it. */
export function deleteDocumentRouter(api: ApiClient, name: string, options: SaveOptions = {}): Promise<DocumentRouterList> {
  return api.request<DocumentRouterList>("DELETE", named(ROUTERS, name), { body: { revision: options.revision }, signal: options.signal });
}

export function renameDocumentRouter(api: ApiClient, name: string, newName: string, options: SaveOptions = {}): Promise<DocumentRouterList> {
  return api.request<DocumentRouterList>("POST", `${named(ROUTERS, name)}/rename`, { body: { new_name: newName, revision: options.revision }, signal: options.signal });
}
