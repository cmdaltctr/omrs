/**
 * The allow-listed preset values of a router list entry, one control each
 * (design D4). The server judges every value; the ranges here stop an obvious
 * mistake before the request. A value left out of the preset is "Not set".
 */
import { rangeRule } from "./validation";

export type PresetValue = string | number | boolean;

export interface PresetField {
  /** The preset key. */
  key: string;
  label: string;
  kind: "int" | "choice" | "bool" | "gpu-layers";
  min?: number;
  max?: number;
  /** The words a `choice` offers. The value sent is the word, or its number for `embd-normalize`. */
  choices?: readonly string[];
  /** A `bool` that accepts `true` only: to turn it off, leave the key out. */
  trueOnly?: boolean;
}

const CACHE_TYPES = ["f32", "f16", "bf16", "q8_0", "q4_0"] as const;

export const PRESET_FIELDS: readonly PresetField[] = [
  { key: "ctx-size", label: "Context size (tokens)", kind: "int", min: 512, max: 262144 },
  { key: "batch-size", label: "Batch size", kind: "int", min: 32, max: 65536 },
  { key: "ubatch-size", label: "Micro-batch size", kind: "int", min: 32, max: 65536 },
  { key: "parallel", label: "Parallel requests", kind: "int", min: 1, max: 16 },
  { key: "embeddings", label: "Embeddings only", kind: "bool", trueOnly: true },
  { key: "pooling", label: "Pooling", kind: "choice", choices: ["none", "mean", "cls", "last", "rank"] },
  { key: "embd-normalize", label: "Embedding normalisation", kind: "choice", choices: ["-1", "0", "1", "2"] },
  { key: "kv-unified", label: "Unified KV cache", kind: "bool" },
  { key: "flash-attn", label: "Flash attention", kind: "choice", choices: ["on", "off", "auto"] },
  { key: "n-gpu-layers", label: "GPU layers", kind: "gpu-layers", min: 0, max: 999 },
  { key: "fit", label: "Fit to memory", kind: "choice", choices: ["on", "off"] },
  { key: "cache-type-k", label: "Key cache type", kind: "choice", choices: CACHE_TYPES },
  { key: "cache-type-v", label: "Value cache type", kind: "choice", choices: CACHE_TYPES },
  { key: "cache-prompt", label: "Prompt cache", kind: "bool" },
  { key: "cache-reuse", label: "Cache reuse (tokens)", kind: "int", min: 0, max: 65536 },
  { key: "image-min-tokens", label: "Image minimum tokens", kind: "int", min: 1, max: 65536 },
  { key: "image-max-tokens", label: "Image maximum tokens", kind: "int", min: 1, max: 65536 },
];

/** The draft text of a field: `""` is "Not set". */
export function draftText(value: PresetValue | undefined): string {
  return value === undefined ? "" : String(value);
}

/** The message of a draft that breaks its field's rule, or `null`. */
export function draftProblem(field: PresetField, text: string): string | null {
  const trimmed = text.trim();
  if (trimmed === "" || field.kind === "choice" || field.kind === "bool") return null;
  if (field.kind === "gpu-layers" && (trimmed === "all" || trimmed === "auto")) return null;
  const value = /^-?\d+$/.test(trimmed) ? Number(trimmed) : Number.NaN;
  const inRange = Number.isInteger(value) && value >= (field.min ?? Number.NEGATIVE_INFINITY) && value <= (field.max ?? Number.POSITIVE_INFINITY);
  if (inRange) return null;
  return field.kind === "gpu-layers" ? `${rangeRule(field.min ?? null, field.max ?? null, true)} Or all, or auto.` : rangeRule(field.min ?? null, field.max ?? null, true);
}

/** The typed preset value of a draft; `undefined` when the draft is "Not set". */
export function presetValue(field: PresetField, text: string): PresetValue | undefined {
  const trimmed = text.trim();
  if (trimmed === "") return undefined;
  if (field.kind === "bool") return trimmed === "true";
  if (field.kind === "int" || field.kind === "gpu-layers") return /^-?\d+$/.test(trimmed) ? Number(trimmed) : trimmed;
  return field.key === "embd-normalize" ? Number(trimmed) : trimmed;
}
