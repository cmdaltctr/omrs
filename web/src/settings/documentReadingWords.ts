import type { DocumentReadingKey, DocumentReadingState, DocumentReadingValue } from "../api/settingsDocumentReading";

/** How a row edits its value: a select of readers, units or engines, or a switch. */
export type ReadingKind = "reader" | "unit" | "engine" | "switch";

export interface ReadingRowWords {
  label: string;
  kind: ReadingKind;
  /** One plain line on what the setting does. */
  help: string;
}

export const READING_ROWS: Record<DocumentReadingKey, ReadingRowWords> = {
  pdf_reader: { label: "PDF reader", kind: "reader", help: "Reads the text of each PDF. auto tries LiteParse, then pypdfium2, then pypdf." },
  ocr_fallback_enabled: { label: "OCR fallback", kind: "switch", help: "Off means no PDF goes to an OCR engine." },
  ocr_routing_unit: { label: "OCR routing unit", kind: "unit", help: "Page is the only unit. OCR reads only the flagged pages." },
  ocr_engine_primary: { label: "Primary engine", kind: "engine", help: "The OCR engine for every request." },
  ocr_engine_fallback: { label: "Fallback engine", kind: "engine", help: "The OCR engine to use when the primary engine cannot run." },
  ocr_maths_routing_enabled: { label: "Maths routing", kind: "switch", help: "Finds maths fonts and sends those pages to OCR." },
};

export const ROUTING_UNITS = ["page"] as const;

/** One option of a select row. A disabled option cannot be chosen; `reason` says why it cannot run. */
export interface ReadingChoice {
  value: string;
  label: string;
  disabled: boolean;
  reason: string | null;
}

/** The options of a select row, from what the server reports. A switch row has none. */
export function readingChoices(kind: ReadingKind, state: DocumentReadingState): ReadingChoice[] {
  if (kind === "reader") {
    return state.pdf_readers.map(({ name, available, reason }) => ({ value: name, label: available ? name : `${name} (not installed)`, disabled: !available, reason }));
  }
  if (kind === "engine") {
    return state.ocr.engines.map(({ name, available, reason }) => ({
      value: name,
      label: available ? name : `${name} (${reason?.startsWith("Not provisioned") ? "not provisioned" : "not available"})`,
      disabled: false,
      reason: available ? null : reason,
    }));
  }
  if (kind === "unit") return ROUTING_UNITS.map((unit) => ({ value: unit, label: unit, disabled: false, reason: null }));
  return [];
}

/**
 * A value as the row shows it. An empty engine name can only be in force from `OCR_ENGINE_FALLBACK=`
 * in the environment or `.env`, and means no fallback. The route never sends `""` as a saved value (design D8).
 */
export function readingText(value: DocumentReadingValue | null): string {
  if (value === null) return "Not set";
  if (typeof value === "boolean") return value ? "On" : "Off";
  if (value === "") return "None (no fallback)";
  return String(value);
}

/** The editor text of a value: `true` or `false` for a switch, the name as text otherwise. */
export function draftText(value: DocumentReadingValue | null): string {
  return value === null ? "" : String(value);
}

/** The editor text as the JSON value the route takes. */
export function draftValue(kind: ReadingKind, text: string): DocumentReadingValue {
  if (kind === "switch") return text === "true";
  return text;
}
