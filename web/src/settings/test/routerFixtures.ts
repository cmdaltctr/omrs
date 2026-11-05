import type { DecisionKindOption, DecisionModelItem, DecisionModelList, DocumentRouterItem, DocumentRouterList } from "../../api/routerMaps";

/** Fixtures built from the `openapi.yaml` schemas for the decision model and router routes. */
export const KINDS: DecisionKindOption[] = [
  { name: "cloudflare", not_yet_tested: true },
  { name: "llamacpp", not_yet_tested: false },
  { name: "ollama", not_yet_tested: true },
  { name: "typesafe", not_yet_tested: false },
];

/** A managed local llama.cpp entry that sees images, named by router `handwriting`. */
export const CLEF_LOCAL: DecisionModelItem = {
  name: "clef-local",
  kind: "llamacpp",
  address: "http://127.0.0.1:8090",
  model: "clef-flash",
  images: true,
  server: "managed",
  model_file: "~/models/clef-flash-Q8_0.gguf",
  projector_file: "~/models/mmproj-clef-flash.gguf",
  model_sha256: "a".repeat(64),
  projector_sha256: "b".repeat(64),
  hosted: false,
  key_state: "not-needed",
  not_yet_tested: false,
  used_by: ["handwriting"],
};

/** A hosted TypeSafe entry with a key reference that resolves. */
export const JEV: DecisionModelItem = {
  name: "jev",
  kind: "typesafe",
  address: "https://api.typesafe.ai",
  model: "jev",
  images: true,
  server: null,
  model_file: null,
  projector_file: null,
  model_sha256: null,
  projector_sha256: null,
  hosted: true,
  key_state: "resolvable",
  not_yet_tested: false,
  used_by: [],
};

/** A hosted Ollama entry with no recorded live request. */
export const OLLAMA_ENTRY: DecisionModelItem = { ...JEV, name: "ollama-clef", kind: "ollama", address: "http://10.0.0.5:11434", model: "clef-q8", images: false, key_state: "not-set", not_yet_tested: true };

export function decisionModels(models: DecisionModelItem[] = [CLEF_LOCAL, JEV]): DecisionModelList {
  return { status: "ok", revision: "r1", kinds: KINDS, models };
}

export const HANDWRITING: DocumentRouterItem = {
  name: "handwriting",
  model: "clef-local",
  question: "Does the text match the text written or printed on the page image?",
  threshold: 0.172,
  images: true,
  max_chars: 2000,
  send_off_machine: false,
  model_kind: "llamacpp",
  hosted: false,
  experimental: false,
  will_run: true,
  will_not_run_reason: null,
  host: false,
  used_by: [],
};

/** A hosted image router with the opt-in off. */
export const HOSTED: DocumentRouterItem = {
  ...HANDWRITING,
  name: "hosted-check",
  model: "jev",
  model_kind: "typesafe",
  hosted: true,
  experimental: true,
  will_run: false,
  will_not_run_reason: "needs-opt-in",
};

export function documentRouters(routers: DocumentRouterItem[] = [HANDWRITING]): DocumentRouterList {
  return { status: "ok", revision: "r1", routers };
}
