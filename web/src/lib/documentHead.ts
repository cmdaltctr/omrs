import type { ThemePreference } from "./preferences";

/** Browser chrome colour per colour scheme: the --surface-canvas value in tokens.css. */
const THEME_COLOURS = { light: "#fdfcfa", dark: "#120f0e" } as const;

export function themeColorFor(scheme: "light" | "dark"): string {
  return THEME_COLOURS[scheme];
}

/**
 * Sets every theme-color meta. index.html carries one meta per colour scheme,
 * selected by a prefers-color-scheme media query, so the `system` theme follows
 * the operating system without a listener. A chosen theme sets both metas.
 */
export function applyThemeColor(doc: Pick<Document, "querySelectorAll">, theme: ThemePreference): void {
  for (const meta of doc.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')) {
    const scheme = meta.getAttribute("media")?.includes("dark") ? "dark" : "light";
    meta.content = themeColorFor(theme === "system" ? scheme : theme);
  }
}
