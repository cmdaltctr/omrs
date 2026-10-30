import { afterEach, describe, expect, it } from "vitest";
import { applyAppearance, applyTheme, DEFAULT_PREFERENCES, PREFERENCES_KEY, readPreferences, THEME_STYLE_ID, themeStylesheet, updatePreferences } from "./preferences";

const APPEARANCE = { lightTheme: "omrs-light", darkTheme: "omrs-dark", uiFont: "system", codeFont: "system", textSize: 100 };

afterEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
  document.getElementById(THEME_STYLE_ID)?.remove();
  document.documentElement.removeAttribute("style");
});

describe("preferences", () => {
  it("defaults to the dark mode, the OMRS themes, System fonts, 100 % text and no last collection", () => {
    expect(readPreferences()).toEqual({ theme: "dark", lastCollection: null, ...APPEARANCE });
    expect(DEFAULT_PREFERENCES).toEqual({ theme: "dark", lastCollection: null, ...APPEARANCE });
  });

  it("stores the preferences under one key", () => {
    updatePreferences({ theme: "dark" });
    updatePreferences({ lastCollection: "papers", darkTheme: "nord-dark" });
    expect(PREFERENCES_KEY).toBe("omrs-preferences");
    const stored = { theme: "dark", lastCollection: "papers", ...APPEARANCE, darkTheme: "nord-dark" };
    expect(JSON.parse(window.localStorage.getItem("omrs-preferences") ?? "null")).toEqual(stored);
    expect(readPreferences()).toEqual(stored);
  });

  it("keeps a value stored before the appearance options, filling them with defaults", () => {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ theme: "light", lastCollection: "papers" }));
    expect(readPreferences()).toEqual({ theme: "light", lastCollection: "papers", ...APPEARANCE });
  });

  it("brings a stored text size outside 80 to 150 back into range", () => {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ theme: "dark", lastCollection: null, textSize: 400 }));
    expect(readPreferences().textSize).toBe(150);
  });

  it("falls back to defaults and removes a value that fails validation", () => {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ theme: "neon", lastCollection: 4 }));
    expect(readPreferences()).toEqual(DEFAULT_PREFERENCES);
    expect(window.localStorage.getItem(PREFERENCES_KEY)).toBeNull();
  });

  it("falls back to defaults for malformed JSON", () => {
    window.localStorage.setItem(PREFERENCES_KEY, "{oops");
    expect(readPreferences()).toEqual(DEFAULT_PREFERENCES);
  });

  it("does not read the retired workspace keys", () => {
    window.localStorage.setItem("omrs-workspace-ui", JSON.stringify({ version: 1, view: "runs", theme: "dark", inspectorOpen: true }));
    expect(readPreferences()).toEqual(DEFAULT_PREFERENCES);
  });

  it("applies and clears the theme on the document root", () => {
    applyTheme("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    applyTheme("system");
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("updates the theme-color meta with the canvas of the chosen theme", () => {
    const meta = document.createElement("meta");
    meta.name = "theme-color";
    meta.setAttribute("media", "(prefers-color-scheme: light)");
    document.head.append(meta);
    try {
      applyAppearance({ ...DEFAULT_PREFERENCES, theme: "dark" });
      expect(meta.content).toBe("#120f0e");
      applyAppearance({ ...DEFAULT_PREFERENCES, theme: "system" });
      expect(meta.content).toBe("#fdfcfa");
      applyAppearance({ ...DEFAULT_PREFERENCES, theme: "system", lightTheme: "nord-light" });
      expect(meta.content).not.toBe("#fdfcfa");
    } finally {
      meta.remove();
    }
  });

  it("adds no theme stylesheet for the OMRS themes", () => {
    expect(themeStylesheet("omrs-light", "omrs-dark")).toBe("");
    applyAppearance(DEFAULT_PREFERENCES);
    expect(document.getElementById(THEME_STYLE_ID)).toBeNull();
  });

  it("writes the dark theme for System and Dark, and the light theme for the root, so System follows the operating system", () => {
    const css = themeStylesheet("github-light", "dracula-dark");
    expect(css).toMatch(/:root, :root\[data-theme="light"\] \{[^}]*--surface-canvas: #/);
    expect(css).toMatch(/@media \(prefers-color-scheme: dark\) \{\n:root:not\(\[data-theme="light"\]\) \{[^}]*--accent: #bd93f9/);
    expect(css).toMatch(/:root\[data-theme="dark"\] \{[^}]*--accent: #bd93f9/);
    applyAppearance({ ...DEFAULT_PREFERENCES, lightTheme: "github-light", darkTheme: "dracula-dark" });
    expect(document.getElementById(THEME_STYLE_ID)?.textContent).toBe(css);
    applyAppearance(DEFAULT_PREFERENCES);
    expect(document.getElementById(THEME_STYLE_ID)).toBeNull();
  });

  it("treats an unknown theme id as the OMRS default", () => {
    expect(themeStylesheet("gone-light", "gone-dark")).toBe("");
  });

  it("sets the font stacks and text size on the root, and removes them for System and 100 %", () => {
    const root = document.documentElement;
    applyAppearance({ ...DEFAULT_PREFERENCES, uiFont: "inter", codeFont: "jetbrains-mono", textSize: 115 });
    expect(root.style.getPropertyValue("--font-sans")).toMatch(/^"Inter Variable", /);
    expect(root.style.getPropertyValue("--font-mono")).toMatch(/^"JetBrains Mono Variable", /);
    expect(root.style.fontSize).toBe("115%");
    applyAppearance(DEFAULT_PREFERENCES);
    expect(root.style.getPropertyValue("--font-sans")).toBe("");
    expect(root.style.getPropertyValue("--font-mono")).toBe("");
    expect(root.style.fontSize).toBe("");
  });
});
