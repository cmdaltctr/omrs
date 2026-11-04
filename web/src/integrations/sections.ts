import type { DiscoveredPartHealth, IntegrationList, LocalOcrBackendHealth, PdfReaderItem, RuntimeComponents, RuntimeItem } from "../api/integrations";

/** The Integrations sections, in the order the chips show them. */
export const INTEGRATION_SECTIONS = ["extras", "tools", "pdf-readers", "reading-parts", "ocr-engines", "model-files", "local-servers", "model-runtimes"] as const;

export type IntegrationSection = (typeof INTEGRATION_SECTIONS)[number];

export type RuntimeSection = Exclude<IntegrationSection, "extras" | "tools" | "pdf-readers" | "reading-parts" | "model-runtimes">;

export const SECTION_LABELS: Record<IntegrationSection, string> = {
  extras: "Extras",
  tools: "Tools",
  "pdf-readers": "PDF readers",
  "reading-parts": "Reading parts",
  "ocr-engines": "OCR engines",
  "model-files": "Model files",
  "local-servers": "Local servers",
  "model-runtimes": "Model runtimes",
};

/** The runtime block field each runtime section shows. */
export const RUNTIME_FIELDS: Record<RuntimeSection, keyof RuntimeComponents> = {
  "ocr-engines": "ocr_engines",
  "model-files": "model_files",
  "local-servers": "local_servers",
};

export function isRuntimeSection(section: IntegrationSection): section is RuntimeSection {
  return section in RUNTIME_FIELDS;
}

function isSection(value: string): value is IntegrationSection {
  return (INTEGRATION_SECTIONS as readonly string[]).includes(value);
}

/**
 * The sections this server has content for. Until the list loads, only
 * Extras is known; Tools and the runtime sections need the server to list them.
 */
export function sectionsFor(list: IntegrationList | undefined): IntegrationSection[] {
  return INTEGRATION_SECTIONS.filter((section) => {
    if (section === "extras") return true;
    if (list === undefined) return false;
    if (section === "tools") return list.tools.length > 0;
    if (section === "pdf-readers") return (list.pdf_readers?.length ?? 0) > 0;
    if (section === "reading-parts") return list.reading_parts !== undefined;
    // The runtimes come from their own route, so this section needs no `runtime` block.
    if (section === "model-runtimes") return true;
    return list.runtime !== undefined;
  });
}

/**
 * The section to show for the address segment. `#/integrations/<section>`
 * names a section. Any other segment names an entry, as links from Settings
 * and the Library do (`#/integrations/anthropic`, `#/integrations/marimo`):
 * a tool opens Tools, anything else opens Extras.
 */
export function sectionFor(segment: string | null, list: IntegrationList | undefined): IntegrationSection {
  if (segment === null) return "extras";
  if (!isSection(segment)) return list?.tools.some((tool) => tool.id === segment) ? "tools" : "extras";
  // A section this server does not report opens Extras once the list is in.
  return list === undefined || sectionsFor(list).includes(segment) ? segment : "extras";
}

/** A part that a setting in force needs and that is not ready. These show in red. */
export function needsAttention(item: RuntimeItem): boolean {
  return item.status !== "ready" && item.used_by.length > 0;
}

/** A reader that a setting in force lists and that is not installed. These show in red. */
export function readerNeedsAttention(reader: PdfReaderItem): boolean {
  return !reader.installed && reader.used_by.length > 0;
}

/** A listed backend that cannot read now: switched off, not installed or without its model files. These show in red. */
export function backendNeedsAttention(backend: LocalOcrBackendHealth): boolean {
  return backend.off_reason !== null || !backend.installed || backend.model_present === false;
}

/** A discovered part that was refused or failed to load. */
export function partNeedsAttention(part: DiscoveredPartHealth): boolean {
  return part.problem !== null;
}

/** How many parts in a section need attention. Only runtime sections, PDF readers and reading parts count. */
export function attentionCount(section: IntegrationSection, list: IntegrationList | undefined): number {
  if (section === "pdf-readers") return list?.pdf_readers?.filter(readerNeedsAttention).length ?? 0;
  if (section === "reading-parts") {
    const parts = list?.reading_parts;
    return parts === undefined ? 0 : parts.local_ocr_backends.filter(backendNeedsAttention).length + parts.discovered_parts.filter(partNeedsAttention).length;
  }
  if (!isRuntimeSection(section) || list?.runtime === undefined) return 0;
  return list.runtime[RUNTIME_FIELDS[section]].filter(needsAttention).length;
}
