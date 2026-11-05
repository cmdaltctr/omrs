import type { DecisionKind, DecisionModelEntry, DecisionModelItem, DecisionTestResult, KeyState } from "../api/routerMaps";

/** The kind names as the page shows them. */
export const KIND_LABELS: Record<DecisionKind, string> = {
  llamacpp: "llama.cpp",
  typesafe: "TypeSafe",
  cloudflare: "Cloudflare Workers AI",
  ollama: "Ollama",
};

/** Said for a kind with no recorded live request (design D2). */
export const NOT_YET_TESTED = "Not yet tested";

/** Said on an entry until the user presses Test. */
export const NOT_TESTED = "Not tested";

/** The key state without the key. The list never returns the key. */
export const KEY_STATE_WORDS: Record<KeyState, string> = {
  "not-needed": "Key: not needed",
  "not-set": "Key: missing",
  "reference-set": "Key: set (keychain reference, not read here)",
  resolvable: "Key: set",
  unresolvable: "Key: missing (the reference does not resolve)",
};

/** The check results as one plain line each. */
export const TEST_WORDS: Record<DecisionTestResult, string> = {
  ok: "Working",
  "unknown-model": "The file holds no valid entry of this name.",
  unreachable: "The server did not answer.",
  "quantisation-refused": "The model file is below 8-bit, so it is refused.",
  "projector-not-loaded": "The server has no projector loaded, so it cannot see images.",
  "wrong-build": "The llama.cpp build is too old.",
  "request-failed": "The test request failed.",
  "malformed-reply": "The server sent a reply OMRS cannot read.",
};

/** The prefixes a key field accepts. A literal key is refused. */
export const KEY_PREFIXES = ["env://", "file://", "keychain://"] as const;

export const KEY_RULE = "Type a reference only: env://NAME, file://~/.config/omrs/secrets/<name>.key or keychain://<provider>. Never type the key itself.";

/** Said when an edit opens on an entry that holds a reference. */
export const KEY_RETYPE = "The saved reference is not shown. Leave the field blank to keep it.";

/** True for a blank field or a reference. */
export function isKeyReference(text: string): boolean {
  const value = text.trim();
  return value === "" || KEY_PREFIXES.some((prefix) => value.startsWith(prefix) && value.length > prefix.length);
}

/** True when the entry holds a key reference. */
export function hasKeyReference(state: KeyState): boolean {
  return state === "reference-set" || state === "resolvable" || state === "unresolvable";
}

/** What the form edits: every field as text or a flag. */
export interface DecisionDraft {
  name: string;
  kind: DecisionKind;
  address: string;
  model: string;
  images: boolean;
  key: string;
  /** `unset` leaves `server` out of the entry. */
  server: "unset" | "external" | "managed";
  model_file: string;
  projector_file: string;
  model_sha256: string;
  projector_sha256: string;
}

export const BLANK_DRAFT: DecisionDraft = { name: "", kind: "llamacpp", address: "http://127.0.0.1:8090", model: "", images: false, key: "", server: "unset", model_file: "", projector_file: "", model_sha256: "", projector_sha256: "" };

/** The form values of a listed entry. The key field opens blank, because the list never returns it. */
export function draftOf(item: DecisionModelItem): DecisionDraft {
  return {
    name: item.name,
    kind: item.kind,
    address: item.address,
    model: item.model,
    images: item.images,
    key: "",
    server: item.server ?? "unset",
    model_file: item.model_file ?? "",
    projector_file: item.projector_file ?? "",
    model_sha256: item.model_sha256 ?? "",
    projector_sha256: item.projector_sha256 ?? "",
  };
}

/** The entry a save writes. Blank optional fields are left out; the file fields go only with a managed server. */
export function entryOf(draft: DecisionDraft): DecisionModelEntry {
  const entry: DecisionModelEntry = { kind: draft.kind, address: draft.address.trim(), model: draft.model.trim(), images: draft.images };
  if (draft.key.trim() !== "") entry.key = draft.key.trim();
  if (draft.kind === "llamacpp" && draft.server !== "unset") entry.server = draft.server;
  if (entry.server !== "managed") return entry;
  for (const field of ["model_file", "projector_file", "model_sha256", "projector_sha256"] as const) {
    if (draft[field].trim() !== "") entry[field] = draft[field].trim();
  }
  return entry;
}
