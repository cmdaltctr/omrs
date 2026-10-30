import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { PREFERENCES_KEY, THEME_STYLE_ID } from "../lib/preferences";
import { startApp } from "../test/startApp";
import { settingsServer } from "./test/fixtures";

afterEach(() => {
  document.getElementById(THEME_STYLE_ID)?.remove();
  document.documentElement.removeAttribute("style");
});

async function openAppearance(stored: Record<string, unknown> = { theme: "dark", lastCollection: null }) {
  window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify(stored));
  startApp("#/settings/appearance", settingsServer());
  const section = await screen.findByRole("region", { name: "Appearance" });
  return { section, user: userEvent.setup() };
}

function stored(): Record<string, unknown> {
  return JSON.parse(window.localStorage.getItem(PREFERENCES_KEY) ?? "{}") as Record<string, unknown>;
}

function textCard() {
  return screen.getByRole("heading", { name: "Text" }).closest("[data-slot='card']") as HTMLElement;
}

function list(name: "Light theme" | "Dark theme") {
  return screen.getByRole("group", { name });
}

describe("Appearance", () => {
  it("lists 30 light and 30 dark themes, with the OMRS default chosen and the dark list on screen", async () => {
    await openAppearance();
    expect(within(list("Light theme")).getAllByRole("radio")).toHaveLength(30);
    expect(within(list("Dark theme")).getAllByRole("radio")).toHaveLength(30);
    expect(within(list("Dark theme")).getByRole("radio", { name: /^OMRS/ })).toBeChecked();
    expect(within(list("Dark theme")).getByText("On screen now")).toBeInTheDocument();
    expect(within(list("Light theme")).queryByText("On screen now")).toBeNull();
  });

  it("keeps the hidden radios inside each scrolling list, so they do not stretch the page", async () => {
    await openAppearance();
    for (const name of ["Light theme", "Dark theme"] as const) {
      const scroll = list(name).querySelector("[data-slot='theme-scroll']") as HTMLElement;
      expect(scroll.className).toMatch(/\brelative\b/);
      expect(scroll.className).toMatch(/\boverflow-y-auto\b/);
      for (const radio of within(scroll).getAllByRole("radio")) expect(radio).toHaveClass("sr-only");
    }
  });

  it("applies and stores a dark theme at once", async () => {
    const { user } = await openAppearance();
    await user.click(within(list("Dark theme")).getByRole("radio", { name: /Dracula/ }));
    expect(stored().darkTheme).toBe("dracula-dark");
    expect(document.getElementById(THEME_STYLE_ID)?.textContent).toContain("--accent: #bd93f9");
    expect(within(list("Dark theme")).getByRole("radio", { name: /Dracula/ })).toBeChecked();
  });

  it("filters both lists by name and says when nothing matches", async () => {
    const { user, section } = await openAppearance();
    await user.type(within(section).getByRole("searchbox", { name: "Filter themes" }), "nord");
    expect(within(list("Light theme")).getAllByRole("radio").map((radio) => radio.getAttribute("value"))).toEqual(["nord-light"]);
    await user.type(within(section).getByRole("searchbox", { name: "Filter themes" }), "zzz");
    expect(within(list("Dark theme")).getByText("No theme matches.")).toBeInTheDocument();
  });

  it("changes the text size in 5 % steps within 80 to 150 %, and Reset returns to 100 %", async () => {
    const { user } = await openAppearance({ theme: "dark", lastCollection: null, textSize: 145 });
    const text = textCard();
    expect(document.documentElement.style.fontSize).toBe("145%");
    await user.click(within(text).getByRole("button", { name: "Larger text" }));
    expect(stored().textSize).toBe(150);
    expect(within(text).getByRole("button", { name: "Larger text" })).toBeDisabled();
    await user.click(within(text).getByRole("button", { name: "Reset" }));
    expect(stored().textSize).toBe(100);
    expect(document.documentElement.style.fontSize).toBe("");
  });

  it("offers bundled interface and code fonts and applies the choice", async () => {
    const { user } = await openAppearance();
    const text = textCard();
    await user.click(within(text).getByRole("combobox", { name: "Interface font" }));
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual(["System", "Inter", "Geist", "Atkinson Hyperlegible", "Source Sans 3"]);
    await user.click(screen.getByRole("option", { name: "Inter" }));
    expect(stored().uiFont).toBe("inter");
    expect(document.documentElement.style.getPropertyValue("--font-sans")).toMatch(/^"Inter Variable"/);
  });
});
