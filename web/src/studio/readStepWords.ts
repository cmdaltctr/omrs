import type { DocumentReadingSetting } from "../api/settingsDocumentReading";
import { readingText, type ReadingKind } from "../settings/documentReadingWords";

/** The line under the title of the Page routing panel in a Read document step (change page-routing-panel, design D7). */
export const READ_STEP_INTRO = "Inherit uses the value from Settings › Document reading. A value set here applies to this pipeline only.";

/** Short words for where a Settings value comes from. A source not listed shows as the server names it. */
const SOURCE_WORDS: Record<string, string> = { default: "default", "config-file": "omrs.jsonc", env: "environment", dotenv: ".env" };

/**
 * The words of an Inherit choice: the Settings value in force and where it
 * comes from, such as "Inherit from Settings: On (default)". The router names no
 * source. Without the Settings row, for example while it loads, the choice
 * reads "Inherit" (`undefined`).
 */
export function inheritLabel(setting: DocumentReadingSetting | undefined, kind: ReadingKind): string | undefined {
  if (setting === undefined) return undefined;
  const value = `Inherit from Settings: ${readingText(setting.value, kind)}`;
  return kind === "router" ? value : `${value} (${SOURCE_WORDS[setting.source] ?? setting.source})`;
}
