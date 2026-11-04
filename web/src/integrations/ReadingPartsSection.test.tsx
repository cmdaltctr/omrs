import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ReadingPartsHealth } from "../api/integrations";
import { documentsServer } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { attentionCount, sectionsFor } from "./sections";

/** The Integrations page shows the health of each reading part (change local-ocr-backends, task 6.3). */
const PARTS: ReadingPartsHealth = {
  local_ocr_backends: [
    { name: "pp-ocrv6-small", label: "PP-OCRv6 small", installed: true, model_present: true, off_reason: "PanicException: lock poisoned", effective_cut: 0.9, source: "built-in" },
    { name: "indra", label: "Indra OCR", installed: false, model_present: null, off_reason: null, effective_cut: 0.9, source: "built-in" },
  ],
  page_rules: [
    { name: "blank", label: "Blank pages", enabled: true, version: 1, source: "built-in" },
    { name: "maths", label: "Maths pages", enabled: true, version: 1, source: "built-in" },
    { name: "non_latin", label: "Non-Latin scripts", enabled: false, version: 1, source: "built-in" },
  ],
  discovered_parts: [
    { name: "stamp-check", kind: "page_rule", distribution: "omrs-stamp", version: "0.1.0", problem: null },
    { name: null, kind: "local_ocr_backend", distribution: "omrs-broken", version: "2.0.0", problem: "ImportError: no module named omrs_broken" },
  ],
};

function serve(parts: ReadingPartsHealth = PARTS) {
  return documentsServer({
    "GET /v1/integrations": () => ({ status: "ok", install_type: "checkout", integrations: [], tools: [], reading_parts: parts }),
  });
}

const region = async () => screen.findByRole("region", { name: "Reading parts" });
const entry = async (list: string, name: string) => {
  const items = within(within(await region()).getByRole("list", { name: list })).getAllByRole("listitem");
  const found = items.find((item) => within(item).queryByRole("heading", { name }) !== null);
  if (found === undefined) throw new Error(`No row ${name} in ${list}`);
  return found;
};

describe("Integrations reading parts", () => {
  it("lists the local OCR backends in list order", async () => {
    startApp("#/integrations/reading-parts", serve());
    const list = within(await region()).getByRole("list", { name: "Local OCR backends" });
    expect(within(list).getAllByRole("listitem").map((item) => within(item).getByRole("heading").textContent)).toEqual(["PP-OCRv6 small", "Indra OCR"]);
  });

  it("shows a backend switched off with the reason, its cut and its model files", async () => {
    startApp("#/integrations/reading-parts", serve());
    const row = await entry("Local OCR backends", "PP-OCRv6 small");
    expect(within(row).getByText("Switched off", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(row).toHaveTextContent("PanicException: lock poisoned");
    expect(row).toHaveTextContent("Confidence cut: 0.9");
    expect(row).toHaveTextContent("Model files are on this machine.");
  });

  it("says a backend is not installed and has no model files to check", async () => {
    startApp("#/integrations/reading-parts", serve());
    const row = await entry("Local OCR backends", "Indra OCR");
    expect(within(row).getByText("Not installed", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(row).not.toHaveTextContent("Model files");
  });

  it("shows each page rule on or off with its version", async () => {
    startApp("#/integrations/reading-parts", serve());
    expect(within(await entry("Page rules", "Maths pages")).getByText("On", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    const nonLatin = await entry("Page rules", "Non-Latin scripts");
    expect(within(nonLatin).getByText("Off", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(nonLatin).toHaveTextContent("Version 1");
  });

  it("shows each discovered part with its distribution, or broken with the reason", async () => {
    startApp("#/integrations/reading-parts", serve());
    const good = await entry("Discovered parts", "stamp-check");
    expect(good).toHaveTextContent("omrs-stamp 0.1.0");
    const broken = await entry("Discovered parts", "omrs-broken");
    expect(within(broken).getByText("Broken", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(broken).toHaveTextContent("ImportError: no module named omrs_broken");
  });

  it("says when no installed package adds a part", async () => {
    startApp("#/integrations/reading-parts", serve({ ...PARTS, discovered_parts: [] }));
    expect(await region()).toHaveTextContent("No installed package adds a reading part.");
  });

  it("shows the section only when the server reports it, and counts what needs attention", () => {
    const list = { install_type: "checkout" as const, integrations: [], tools: [] };
    expect(sectionsFor(list)).not.toContain("reading-parts");
    expect(sectionsFor({ ...list, reading_parts: PARTS })).toContain("reading-parts");
    // The switched-off backend, the backend that is not installed and the broken part.
    expect(attentionCount("reading-parts", { ...list, reading_parts: PARTS })).toBe(3);
  });
});
