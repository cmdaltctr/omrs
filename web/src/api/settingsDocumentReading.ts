/**
 * Typed client for the Document reading routes (`getDocumentReadingSettings`,
 * `setDocumentReadingSettings` in `openapi.yaml`, design D10 of the
 * `document-reading-settings` change). Every key applies at the next launch.
 */
import type { ApiClient, CallOptions } from "./client";
import type { SaveOptions } from "./settings";

/**
 * The keys, in the order the server lists them and the order of lock precedence.
 * `pdf_readers`, `ocr_engines` and `ocr_local_backends` hold ordered lists and
 * `ocr_local_cuts` holds a map from backend name to confidence cut. The page
 * writes the list keys; the three single-value keys stay valid in answers and requests,
 * and the server removes them from `omrs.jsonc` when a list key is saved.
 */
export const DOCUMENT_READING_KEYS = [
  "pdf_readers",
  "pdf_reader",
  "ocr_fallback_enabled",
  "ocr_routing_unit",
  "ocr_engines",
  "ocr_engine_primary",
  "ocr_engine_fallback",
  "ocr_maths_routing_enabled",
  "ocr_non_latin_routing",
  "document_router",
  "ocr_local_backends",
  "ocr_local_cuts",
] as const;

export type DocumentReadingKey = (typeof DOCUMENT_READING_KEYS)[number];

/** A boolean key holds `true` or `false`, a list key an array of names, the cuts key a map from backend name to cut and the others text. */
export type DocumentReadingValue = string | number | boolean | string[] | Record<string, number>;

export interface DocumentReadingSetting {
  key: DocumentReadingKey;
  /** The value in force since this launch. A list key holds an array of names. For `pdf_reader` this is the configured name, which can be `auto`. */
  value: DocumentReadingValue;
  /** The valid value `omrs.jsonc` holds now, or `null` when the file does not set it or holds a value that breaks its rule. */
  saved: DocumentReadingValue | null;
  source: "env" | "dotenv" | "config-file" | "default";
  /** True when `source` is `env` or `dotenv`. */
  locked: boolean;
  /** "Remove <ENV_NAME> from the environment or .env to edit it here." when locked. */
  lock_reason: string | null;
  /** The file value differs from the value captured at launch. */
  restart_pending: boolean;
  default: DocumentReadingValue;
}

export interface ReaderOption {
  name: string;
  /** The reader's package imports. `auto` is always available. */
  available: boolean;
  /** Why it cannot run, or `null` when available. */
  reason: string | null;
}

/** A local OCR backend that `ocr_local_backends` can name. */
export interface LocalBackendOption {
  name: string;
  /** The backend's package can be found. */
  available: boolean;
  /** Why it cannot run (`Not installed.`), or `null` when available. */
  reason: string | null;
  /** The cut that applies when `ocr_local_cuts` has no entry for this backend. */
  default_cut: number;
}

export interface OcrEngineOption {
  name: string;
  /** The engine has a command now. */
  available: boolean;
  /** Why it cannot run, or `null` when available. */
  reason: string | null;
}

export interface DocumentReadingState {
  status: "ok";
  revision: string;
  settings: DocumentReadingSetting[];
  /** `auto` first, then each registered reader. */
  pdf_readers: ReaderOption[];
  /** The reader the running engine uses after resolution, or `null` when it cannot be computed. */
  pdf_reader_in_use: string | null;
  /** Each backend a local OCR list can name, in descriptor order. */
  local_ocr_backends: LocalBackendOption[];
  /** Keys that `omrs.jsonc` holds and OMRS ignores, such as `ocr_local_min_confidence`. */
  retired_keys: string[];
  ocr: {
    /** Launch `ocr_workers_dir` with `~` for the home folder, or `null` when unset. */
    workers_dir: string | null;
    /** Sorted by name. */
    engines: OcrEngineOption[];
  };
}

/** One or more keys. `null` removes a key from `omrs.jsonc`, so its default applies. */
export type DocumentReadingValues = Partial<Record<DocumentReadingKey, DocumentReadingValue | null>>;

export function getDocumentReadingSettings(api: ApiClient, options: CallOptions = {}): Promise<DocumentReadingState> {
  return api.request<DocumentReadingState>("GET", "/v1/settings/document-reading", { signal: options.signal });
}

/** Writes all values or none, for the next launch. The values in force do not change. */
export function saveDocumentReadingSettings(api: ApiClient, values: DocumentReadingValues, options: SaveOptions = {}): Promise<DocumentReadingState> {
  return api.request<DocumentReadingState>("PUT", "/v1/settings/document-reading", { body: { values, revision: options.revision }, signal: options.signal });
}
