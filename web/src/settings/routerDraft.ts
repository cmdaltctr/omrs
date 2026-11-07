import type { RouterModel } from "../api/llamacppRouter";
import { draftProblem, draftText, PRESET_FIELDS, presetValue, type PresetValue } from "./routerPresetFields";

export type Draft = Record<string, string>;

/** The draft a model opens its edit form with: each preset value as text. */
export function openDraft(entry: RouterModel): Draft {
  return Object.fromEntries(PRESET_FIELDS.map((field) => [field.key, draftText(entry.preset[field.key])]));
}

/** The first message of each field whose draft breaks its rule. */
export function problems(draft: Draft): Record<string, string> {
  const found: Record<string, string> = {};
  for (const field of PRESET_FIELDS) {
    const message = draftProblem(field, draft[field.key] ?? "");
    if (message !== null) found[field.key] = message;
  }
  return found;
}

/** The whole preset to save. A field left "Not set" is left out of it. */
export function presetOf(draft: Draft): Record<string, PresetValue> {
  const preset: Record<string, PresetValue> = {};
  for (const field of PRESET_FIELDS) {
    const value = presetValue(field, draft[field.key] ?? "");
    if (value !== undefined) preset[field.key] = value;
  }
  return preset;
}
