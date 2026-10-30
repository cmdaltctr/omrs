import { THEME_DATA } from "./themeData";
import type { ThemeColours, ThemeDefinition } from "./types";

/**
 * The OMRS default pair. It has no colours of its own: `tokens.css` holds
 * them, so choosing it removes every override.
 */
export const DEFAULT_LIGHT_THEME = "omrs-light";
export const DEFAULT_DARK_THEME = "omrs-dark";

/** The values of `tokens.css`, for the swatch of the default theme only. */
const OMRS_LIGHT: ThemeColours = {
  canvas: "#fdfcfa", elevated: "#f8f7f5", muted: "#f7f6f4", text: "#393a34", textSecondary: "#5c5c54",
  border: "#e5e1de", borderHover: "#cbc7c2", accent: "#b35017", accentHover: "#9a4310", accentActive: "#85390c",
  selection: "#a9998f2b", hover: "#0000000d", active: "#00000014", focus: "#b35017",
  error: "#b7493f", warning: "#8d6c15", success: "#5f8d3d", info: "#2d72c4",
};
const OMRS_DARK: ThemeColours = {
  canvas: "#120f0e", elevated: "#181715", muted: "#171615", text: "#c9c5ba", textSecondary: "#8f8b81",
  border: "#242323", borderHover: "#504e4c", accent: "#da7c47", accentHover: "#eb8c57", accentActive: "#fd9b66",
  selection: "#c8c6c52b", hover: "#ffffff12", active: "#ffffff1f", focus: "#da7c47",
  error: "#da5b4a", warning: "#c67f13", success: "#76ad4f", info: "#479fe6",
};

export const THEMES: readonly ThemeDefinition[] = [
  { id: DEFAULT_LIGHT_THEME, name: "OMRS", variant: "light", colours: OMRS_LIGHT },
  { id: DEFAULT_DARK_THEME, name: "OMRS", variant: "dark", colours: OMRS_DARK },
  ...THEME_DATA,
];

export function themesOf(variant: "light" | "dark"): ThemeDefinition[] {
  return THEMES.filter((theme) => theme.variant === variant);
}

/** The theme with this id and variant, or the OMRS default of that variant. */
export function findTheme(id: string, variant: "light" | "dark"): ThemeDefinition {
  return THEMES.find((theme) => theme.id === id && theme.variant === variant) ?? THEMES.find((theme) => theme.id === (variant === "light" ? DEFAULT_LIGHT_THEME : DEFAULT_DARK_THEME))!;
}

export function isDefaultTheme(theme: ThemeDefinition): boolean {
  return theme.id === DEFAULT_LIGHT_THEME || theme.id === DEFAULT_DARK_THEME;
}

/** Each OMRS token a theme sets, with its value. Tints and labels mix from the theme's own colours. */
export function themeTokens(colours: ThemeColours): Record<string, string> {
  return {
    "--surface-canvas": colours.canvas,
    "--surface-elevated": colours.elevated,
    "--surface-muted": colours.muted,
    "--text-primary": colours.text,
    "--text-secondary": colours.textSecondary,
    "--border": colours.border,
    "--border-hover": colours.borderHover,
    "--accent": colours.accent,
    "--accent-hover": colours.accentHover,
    "--accent-active": colours.accentActive,
    "--accent-label": "color-mix(in srgb, var(--accent) 70%, var(--text-primary))",
    "--accent-tint": "color-mix(in srgb, var(--accent) 12%, transparent)",
    "--accent-tint-hover": "color-mix(in srgb, var(--accent) 18%, transparent)",
    "--accent-tint-active": "color-mix(in srgb, var(--accent) 25%, transparent)",
    "--accent-tint-border": "color-mix(in srgb, var(--accent) 32%, transparent)",
    "--selection": colours.selection,
    "--interactive-hover": colours.hover,
    "--interactive-active": colours.active,
    "--focus-ring": colours.focus,
    "--status-error": colours.error,
    "--status-warning": colours.warning,
    "--status-success": colours.success,
    "--status-info": colours.info,
  };
}
