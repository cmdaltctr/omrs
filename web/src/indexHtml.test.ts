/**
 * Guards the static page head in web/index.html. The browser tab, search
 * engines and the phone home screen read these tags before any script runs.
 * Prettier can wrap a long tag, so the patterns allow any whitespace.
 */
import { describe, expect, it } from "vitest";
import indexHtml from "../index.html?raw";

const touchIcon = import.meta.glob("../public/apple-touch-icon.png");

function meta(name: string): string[] {
  const pattern = new RegExp(`<meta\\s+name="${name}"[^>]*?\\scontent="([^"]*)"`, "g");
  return [...indexHtml.matchAll(pattern)].map((match) => match[1] ?? "");
}

describe("index.html head", () => {
  it("names OMRS in capitals in the title", () => {
    const title = /<title>\s*([^<]*?)\s*<\/title>/.exec(indexHtml)?.[1];
    expect(title).toBe("OMRS workspace");
    expect(title).not.toMatch(/omrs/);
  });

  it("declares British English", () => {
    expect(indexHtml).toMatch(/<html\s+lang="en-GB"/);
  });

  it("has a one-sentence description", () => {
    expect(meta("description")).toEqual([expect.stringMatching(/^[A-Z][^.]+\.$/)]);
  });

  it("keeps the local app out of search engines", () => {
    expect(meta("robots")).toEqual(["noindex, nofollow"]);
  });

  it("lists the default dark scheme first", () => {
    expect(meta("color-scheme")).toEqual(["dark light"]);
  });

  it("has a theme colour for each colour scheme", () => {
    expect(indexHtml).toMatch(
      /<meta\s+name="theme-color"\s+media="\(prefers-color-scheme: light\)"\s+content="#fdfcfa"/,
    );
    expect(indexHtml).toMatch(
      /<meta\s+name="theme-color"\s+media="\(prefers-color-scheme: dark\)"\s+content="#120f0e"/,
    );
  });

  it("links an apple touch icon that exists", () => {
    expect(indexHtml).toMatch(/<link\s+rel="apple-touch-icon"\s+href="\/apple-touch-icon.png"/);
    expect(Object.keys(touchIcon)).toHaveLength(1);
  });
});
