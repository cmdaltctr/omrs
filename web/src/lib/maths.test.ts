/**
 * Guards for the shared maths configuration (web-ui-stack, "Maths renders
 * through one shared renderer in the base build").
 */
import { describe, expect, it } from "vitest";
import lockfile from "../../package-lock.json?raw";
import packageJson from "../../package.json?raw";
import { KATEX_OPTIONS, rehypeMathPlugins, remarkMathPlugins } from "./maths";

describe("KATEX_OPTIONS", () => {
  it("keeps trust off, so a formula cannot add a link, class, style or image", () => {
    expect(KATEX_OPTIONS.trust).toBe(false);
  });

  it("limits the size of a rule or box a formula may draw", () => {
    expect(KATEX_OPTIONS.maxSize).toBe(20);
  });

  it("colours a broken formula with the error token, not a literal colour", () => {
    expect(KATEX_OPTIONS.errorColor).toBe("var(--status-error-label)");
  });
});

describe("plugin lists", () => {
  it("hands the same KaTeX options to rehype-katex", () => {
    const [, options] = rehypeMathPlugins[0] as [unknown, unknown];
    expect(options).toBe(KATEX_OPTIONS);
  });

  it("lists remark-math and the dollar rule, then one rehype plugin", () => {
    expect(remarkMathPlugins).toHaveLength(2);
    expect(rehypeMathPlugins).toHaveLength(1);
  });
});

describe("package pins", () => {
  const dependencies = (JSON.parse(packageJson) as { dependencies: Record<string, string> }).dependencies;

  it.each([
    ["remark-math", "6.0.0"],
    ["rehype-katex", "7.0.1"],
    ["katex", "0.16.22"],
  ])("pins %s to the exact version %s in dependencies", (name, version) => {
    expect(dependencies[name]).toBe(version);
  });
});

describe("install", () => {
  it("has one copy of katex in the lockfile", () => {
    const lock = JSON.parse(lockfile) as { packages: Record<string, unknown> };
    expect(Object.keys(lock.packages).filter((name) => name.endsWith("node_modules/katex"))).toEqual(["node_modules/katex"]);
  });

  it("has no maths entry in the Integrations front end", () => {
    const pages = import.meta.glob<string>("../integrations/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true });
    for (const [path, source] of Object.entries(pages)) {
      if (/\.test\.tsx?$/.test(path)) continue;
      expect(source, path).not.toMatch(/katex|maths rendering/i);
    }
  });
});
