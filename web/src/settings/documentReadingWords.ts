import type { DocumentReadingKey, DocumentReadingState, DocumentReadingValue, OcrEngineOption, ReaderOption } from "../api/settingsDocumentReading";
import { formatRoute } from "../lib/routes";
import type { ListOption } from "./OrderedListControl";

/** How a row edits its value: an ordered list of readers or engines, a select of units, or a switch. */
export type ReadingKind = "readers" | "unit" | "engines" | "switch";

/** The two list kinds. */
export type ListKind = "readers" | "engines";

export interface ReadingRowWords {
  label: string;
  kind: ReadingKind;
  /** One plain line on what the setting does. */
  help: string;
}

/**
 * The rows the page shows. The three old single-value keys have no row: the
 * page writes the list keys, and the server removes the old keys on a save.
 */
export const READING_ROWS: Partial<Record<DocumentReadingKey, ReadingRowWords>> = {
  pdf_readers: { label: "PDF readers", kind: "readers", help: "The first installed reader reads each PDF. A later reader runs when the readers above are not installed or return no text." },
  ocr_fallback_enabled: { label: "OCR fallback", kind: "switch", help: "Off means no PDF goes to an OCR engine." },
  ocr_routing_unit: { label: "OCR routing unit", kind: "unit", help: "Page is the only unit. OCR reads only the flagged pages." },
  ocr_engines: { label: "OCR engines", kind: "engines", help: "The first available engine reads. A later engine runs only when every engine above is unavailable before the request starts." },
  ocr_maths_routing_enabled: { label: "Maths routing", kind: "switch", help: "Finds maths fonts and sends those pages to OCR." },
};

export const ROUTING_UNITS = ["page"] as const;

/** What a list says about itself: the add choice, the empty-list line and what each position does. */
export const LIST_WORDS: Record<ListKind, { noun: string; position: (index: number) => string; integrations: { entry: string; text: string } }> = {
  readers: {
    noun: "reader",
    position: (index) => (index === 0 ? "Reads first, when installed." : "Retries when the readers above are not installed or return no text."),
    integrations: { entry: "pdf-readers", text: "See PDF readers in Integrations" },
  },
  engines: {
    noun: "engine",
    position: (index) => (index === 0 ? "Reads first, when available." : "Runs only when every engine above is unavailable."),
    integrations: { entry: "ocr-engines", text: "See OCR engines in Integrations" },
  },
};

/** One option of a select row. A disabled option cannot be chosen. */
export interface ReadingChoice {
  value: string;
  label: string;
  disabled: boolean;
}

/** The options of the routing unit select. Lists and switches have none. */
export function readingChoices(kind: ReadingKind): ReadingChoice[] {
  return kind === "unit" ? ROUTING_UNITS.map((unit) => ({ value: unit, label: unit, disabled: false })) : [];
}

/** The reader names a list can hold. `auto` is not a name for a list. An uninstalled reader can be listed already but not added. */
export function readerOptions(readers: ReaderOption[]): ListOption[] {
  const link = { href: formatRoute({ area: "integrations", entry: LIST_WORDS.readers.integrations.entry }), text: LIST_WORDS.readers.integrations.text };
  return readers
    .filter((reader) => reader.name !== "auto")
    .map(({ name, available }) => ({ value: name, label: available ? name : `${name} (not installed)`, disabled: !available, note: available ? null : "Not installed.", link: available ? null : link }));
}

/** The engine names a list can hold. An engine that is not provisioned can be added, because a later engine only runs when the ones above cannot. */
export function engineOptions(engines: OcrEngineOption[]): ListOption[] {
  const link = { href: formatRoute({ area: "integrations", entry: LIST_WORDS.engines.integrations.entry }), text: LIST_WORDS.engines.integrations.text };
  return engines.map(({ name, available, reason }) => ({
    value: name,
    label: available ? name : `${name} (${reason?.startsWith("Not provisioned") ? "not provisioned" : "not available"})`,
    disabled: false,
    note: available ? null : reason,
    link: available ? null : link,
  }));
}

/** The options of a list row, from what the server reports. */
export function listOptions(kind: ListKind, state: DocumentReadingState): ListOption[] {
  return kind === "readers" ? readerOptions(state.pdf_readers) : engineOptions(state.ocr.engines);
}

/** True for a kind that holds a list. */
export function isListKind(kind: ReadingKind): kind is ListKind {
  return kind === "readers" || kind === "engines";
}

/** The lines for listed names that cannot run, such as `pypdfium2: Not installed.`. */
export function listNotes(list: string[], options: ListOption[]): string[] {
  return list.flatMap((name) => {
    const note = options.find((option) => option.value === name)?.note;
    return note ? [`${name}: ${note}`] : [];
  });
}

/** Design Risks: `pdf_inspector` alone never retries, so a PDF with no text layer indexes nothing. */
export function readerListWarning(list: string[]): string | null {
  return list.length === 1 && list[0] === "pdf_inspector" ? "pdf_inspector alone has no retry: a PDF with no text layer indexes nothing. Add liteparse or pypdf." : null;
}

/** A value as the row shows it. A list reads in order, separated by commas. */
export function readingText(value: DocumentReadingValue | null): string {
  if (value === null) return "Not set";
  if (typeof value === "boolean") return value ? "On" : "Off";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

/** What the editor holds: the names of a list, `true` or `false` for a switch, the name as text otherwise. */
export type ReadingDraft = string | string[];

/** The editor value of a saved or running value. */
export function draftOf(value: DocumentReadingValue | null): ReadingDraft {
  if (Array.isArray(value)) return value;
  return value === null ? "" : String(value);
}

export function sameDraft(a: ReadingDraft, b: ReadingDraft): boolean {
  return typeof a === "string" || typeof b === "string" ? a === b : a.length === b.length && a.every((name, index) => name === b[index]);
}

/** The editor value as the JSON value the route takes. */
export function draftValue(kind: ReadingKind, draft: ReadingDraft): DocumentReadingValue {
  if (typeof draft !== "string") return draft;
  return kind === "switch" ? draft === "true" : draft;
}
