import type { IntegrationList, RuntimeComponents, RuntimeItem } from "../api/integrations";

/** The Integrations sections, in the order the chips show them. */
export const INTEGRATION_SECTIONS = ["extras", "tools", "ocr-engines", "model-files", "local-servers"] as const;

export type IntegrationSection = (typeof INTEGRATION_SECTIONS)[number];

export type RuntimeSection = Exclude<IntegrationSection, "extras" | "tools">;

export const SECTION_LABELS: Record<IntegrationSection, string> = {
  extras: "Extras",
  tools: "Tools",
  "ocr-engines": "OCR engines",
  "model-files": "Model files",
  "local-servers": "Local servers",
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

/** The sections this server has content for. Tools and the runtime sections need the server to list them. */
export function sectionsFor(list: IntegrationList | undefined): IntegrationSection[] {
  return INTEGRATION_SECTIONS.filter((section) => {
    if (section === "extras") return true;
    if (section === "tools") return list === undefined || list.tools.length > 0;
    return list === undefined || list.runtime !== undefined;
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
  if (isSection(segment)) return segment;
  return list?.tools.some((tool) => tool.id === segment) ? "tools" : "extras";
}

/** A part that a setting in force needs and that is not ready. These show in red. */
export function needsAttention(item: RuntimeItem): boolean {
  return item.status !== "ready" && item.used_by.length > 0;
}

/** How many parts in a section need attention. Only runtime sections count. */
export function attentionCount(section: IntegrationSection, list: IntegrationList | undefined): number {
  if (!isRuntimeSection(section) || list?.runtime === undefined) return 0;
  return list.runtime[RUNTIME_FIELDS[section]].filter(needsAttention).length;
}
