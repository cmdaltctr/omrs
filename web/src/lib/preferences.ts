import { applyThemeColor } from "./documentHead";
import { CODE_FONTS, findFont, TEXT_SIZE, UI_FONTS } from "./fonts";
import { readStored, writeStored } from "./storage";
import { DEFAULT_DARK_THEME, DEFAULT_LIGHT_THEME, findTheme, isDefaultTheme, themeTokens } from "./themes/catalogue";

/**
 * Per-browser preferences: the theme mode, the light and dark theme, fonts,
 * text size, and the last collection as a navigation default. Nothing here is
 * a source of truth for workspace data.
 */
export const PREFERENCES_KEY = "omrs-preferences";

export const THEMES = ["system", "light", "dark"] as const;
export type ThemePreference = (typeof THEMES)[number];

export interface Preferences {
  theme: ThemePreference;
  lastCollection: string | null;
  lightTheme: string;
  darkTheme: string;
  uiFont: string;
  codeFont: string;
  /** Percent of the browser's root text size. */
  textSize: number;
}

export const DEFAULT_PREFERENCES: Preferences = {
  theme: "dark",
  lastCollection: null,
  lightTheme: DEFAULT_LIGHT_THEME,
  darkTheme: DEFAULT_DARK_THEME,
  uiFont: "system",
  codeFont: "system",
  textSize: TEXT_SIZE.default,
};

function isTheme(value: unknown): value is ThemePreference {
  return typeof value === "string" && (THEMES as readonly string[]).includes(value);
}

/** The stored core: theme and last collection. Values stored before the appearance options were added pass too. */
function isStored(value: unknown): value is Partial<Preferences> & Pick<Preferences, "theme" | "lastCollection"> {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return isTheme(record.theme) && (record.lastCollection === null || typeof record.lastCollection === "string");
}

function stringOr(value: unknown, fallback: string): string {
  return typeof value === "string" && value !== "" ? value : fallback;
}

function textSizeOr(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value)) return TEXT_SIZE.default;
  return Math.min(TEXT_SIZE.max, Math.max(TEXT_SIZE.min, value));
}

export function readPreferences(): Preferences {
  const stored = readStored(PREFERENCES_KEY, isStored);
  if (stored === null) return DEFAULT_PREFERENCES;
  return {
    theme: stored.theme,
    lastCollection: stored.lastCollection,
    lightTheme: stringOr(stored.lightTheme, DEFAULT_LIGHT_THEME),
    darkTheme: stringOr(stored.darkTheme, DEFAULT_DARK_THEME),
    uiFont: stringOr(stored.uiFont, "system"),
    codeFont: stringOr(stored.codeFont, "system"),
    textSize: textSizeOr(stored.textSize),
  };
}

/** Merges a change into the stored preferences and returns the result. */
export function updatePreferences(change: Partial<Preferences>): Preferences {
  const next: Preferences = { ...readPreferences(), ...change };
  writeStored(PREFERENCES_KEY, next);
  return next;
}

/** Applies a theme preference to the document root. `system` follows the operating system. */
export function applyTheme(theme: ThemePreference): void {
  const root = document.documentElement;
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;
}

export const THEME_STYLE_ID = "omrs-theme";

function block(selector: string, tokens: Record<string, string>): string {
  return `${selector} {\n${Object.entries(tokens)
    .map(([name, value]) => `  ${name}: ${value};`)
    .join("\n")}\n}`;
}

/**
 * The stylesheet of the chosen light and dark themes. It repeats the selectors
 * of tokens.css and comes after it, so System mode still switches between the
 * two themes with the operating system. A default theme adds no rule.
 */
export function themeStylesheet(lightId: string, darkId: string): string {
  const light = findTheme(lightId, "light");
  const dark = findTheme(darkId, "dark");
  const rules: string[] = [];
  if (!isDefaultTheme(light)) rules.push(block(':root, :root[data-theme="light"]', { ...themeTokens(light.colours), "color-scheme": "light" }));
  if (!isDefaultTheme(dark)) {
    const tokens = { ...themeTokens(dark.colours), "color-scheme": "dark" };
    rules.push(`@media (prefers-color-scheme: dark) {\n${block(':root:not([data-theme="light"])', tokens)}\n}`);
    rules.push(block(':root[data-theme="dark"]', tokens));
  }
  return rules.join("\n");
}

/** Applies the themes, fonts and text size to the document. */
export function applyAppearance(preferences: Preferences): void {
  const doc = document;
  let style = doc.getElementById(THEME_STYLE_ID);
  const css = themeStylesheet(preferences.lightTheme, preferences.darkTheme);
  if (css === "") style?.remove();
  else {
    if (style === null) {
      style = doc.createElement("style");
      style.id = THEME_STYLE_ID;
      doc.head.append(style);
    }
    style.textContent = css;
  }
  applyThemeColor(doc, preferences.theme, {
    light: findTheme(preferences.lightTheme, "light").colours.canvas,
    dark: findTheme(preferences.darkTheme, "dark").colours.canvas,
  });

  const root = doc.documentElement;
  const ui = findFont(UI_FONTS, preferences.uiFont);
  const code = findFont(CODE_FONTS, preferences.codeFont);
  for (const [token, font] of [["--font-sans", ui], ["--font-mono", code]] as const) {
    if (font.load === undefined) root.style.removeProperty(token);
    else {
      void font.load().catch(() => undefined);
      root.style.setProperty(token, font.stack);
    }
  }
  if (preferences.textSize === TEXT_SIZE.default) root.style.removeProperty("font-size");
  else root.style.fontSize = `${preferences.textSize}%`;
}
