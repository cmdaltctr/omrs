import type { DecisionModelItem, DocumentRouterEntry, DocumentRouterItem } from "../api/routerMaps";
import { KIND_LABELS } from "./decisionModelWords";

/** The Experiment 43 template (spec document-routers, "Router from the Experiment 43 template"). */
export const TEMPLATE = {
  label: "Text matches the page image",
  question: "Does the text match the text written or printed on the page image?",
  images: true,
  max_chars: 2000,
  threshold: 0.172,
} as const;

/** Said beside the template threshold. */
export const THRESHOLD_NOTE = "Fitted on Experiment 33 documents, not confirmed.";

export const OPT_IN_LABEL = "Send pages off this machine";

export const EXPERIMENTAL = "Experimental";

/** What the router form edits. Numbers stay text until Save. */
export interface RouterDraft {
  name: string;
  model: string;
  question: string;
  threshold: string;
  images: boolean;
  max_chars: string;
  send_off_machine: boolean;
}

export const BLANK_ROUTER: RouterDraft = { name: "", model: "", question: "", threshold: "0.5", images: false, max_chars: "2000", send_off_machine: false };

/** A new router from the template, on the first local model that sees images, else the first model. */
export function templateDraft(models: DecisionModelItem[]): RouterDraft {
  const model = models.find((item) => item.images && !item.hosted) ?? models[0];
  return { ...BLANK_ROUTER, model: model?.name ?? "", question: TEMPLATE.question, threshold: String(TEMPLATE.threshold), images: TEMPLATE.images, max_chars: String(TEMPLATE.max_chars) };
}

export function routerDraftOf(item: DocumentRouterItem): RouterDraft {
  return { name: item.name, model: item.model, question: item.question, threshold: String(item.threshold), images: item.images, max_chars: String(item.max_chars), send_off_machine: item.send_off_machine };
}

/** The threshold as a number between 0 and 1, or `null`. */
export function thresholdOf(text: string): number | null {
  const value = Number(text.trim());
  return text.trim() !== "" && Number.isFinite(value) && value >= 0 && value <= 1 ? value : null;
}

/** The character limit as a whole number of 1 or more, or `null`. */
export function maxCharsOf(text: string): number | null {
  const value = Number(text.trim());
  return Number.isInteger(value) && value >= 1 ? value : null;
}

/** The entry a save writes, or `null` while a field breaks its rule. The opt-in goes only with a hosted model. */
export function routerEntryOf(draft: RouterDraft, hosted: boolean): DocumentRouterEntry | null {
  const threshold = thresholdOf(draft.threshold);
  const maxChars = maxCharsOf(draft.max_chars);
  if (draft.model === "" || draft.question.trim() === "" || threshold === null || maxChars === null) return null;
  return { model: draft.model, question: draft.question.trim(), threshold, images: draft.images, max_chars: maxChars, send_off_machine: hosted && draft.send_off_machine };
}

/** The host of an address, or the address when it does not parse. */
function hostOf(address: string): string {
  try {
    return new URL(address).host || address;
  } catch {
    return address;
  }
}

/** The third party a hosted model sends to, such as "TypeSafe at api.typesafe.ai". */
export function thirdParty(model: DecisionModelItem): string {
  return `${KIND_LABELS[model.kind]} at ${hostOf(model.address)}`;
}

/** The off-machine warning: what leaves (text, plus images when on) and who gets it. */
export function offMachineWarning(model: DecisionModelItem, images: boolean): string {
  const what = images ? "Page text and page images go" : "Page text goes";
  return `${what} to ${thirdParty(model)}, a third party off this machine.`;
}

/** Why a router will not run, as one line. */
export function willNotRunText(item: DocumentRouterItem): string {
  if (item.will_not_run_reason === "needs-opt-in") return `Will not run: ${OPT_IN_LABEL} is off.`;
  return `Will not run: omrs.jsonc holds no decision model named ${item.model}.`;
}
