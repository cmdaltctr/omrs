import { describe, expect, it } from "vitest";
import tokensCss from "../styles/tokens.css?raw";
import { applyThemeColor, themeColorFor } from "./documentHead";

/** Reads --surface-canvas from the first CSS block that opens with `selector`. */
function canvasColour(selector: string): string {
  const start = tokensCss.indexOf(`${selector} {`);
  const block = tokensCss.slice(start, tokensCss.indexOf("}", start));
  const value = /--surface-canvas:\s*([^;]+);/.exec(block)?.[1];
  if (start < 0 || value === undefined) throw new Error(`No --surface-canvas under ${selector}`);
  return value.trim();
}

function fakeDocument(): Document {
  return new DOMParser().parseFromString(
    `<head>
      <meta name="theme-color" media="(prefers-color-scheme: light)" content="" />
      <meta name="theme-color" media="(prefers-color-scheme: dark)" content="" />
    </head>`,
    "text/html",
  );
}

function themeColours(doc: Document): string[] {
  return [...doc.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')].map((meta) => meta.content);
}

describe("themeColorFor", () => {
  it("equals each theme's canvas colour in tokens.css", () => {
    expect(themeColorFor("light")).toBe(canvasColour(":root"));
    expect(themeColorFor("dark")).toBe(canvasColour(':root[data-theme="dark"]'));
  });
});

describe("applyThemeColor", () => {
  it("lets each meta follow its own scheme for the system theme", () => {
    const doc = fakeDocument();
    applyThemeColor(doc, "system");
    expect(themeColours(doc)).toEqual([themeColorFor("light"), themeColorFor("dark")]);
  });

  it("sets both metas to the chosen theme", () => {
    const doc = fakeDocument();
    applyThemeColor(doc, "dark");
    expect(themeColours(doc)).toEqual([themeColorFor("dark"), themeColorFor("dark")]);
    applyThemeColor(doc, "light");
    expect(themeColours(doc)).toEqual([themeColorFor("light"), themeColorFor("light")]);
  });
});
