import { describe, expect, it } from "vitest";
import { experiment } from "../test/libraryServer";
import { findingCounts, formatSize, matches, NO_FILTERS, purposeLabel, PURPOSES, statusVariant, STATUSES } from "./labels";

describe("library labels", () => {
  it("maps each status to the badge colour of design D8, and an unknown one to neutral", () => {
    expect(Object.fromEntries(STATUSES.map((status) => [status, statusVariant(status)]))).toEqual({
      PLANNED: "info",
      ACTIVE: "warning",
      PASS: "success",
      FAIL: "error",
      INCONCLUSIVE: "warning",
      MEASURED: "info",
      SUPERSEDED: "neutral",
    });
    expect(statusVariant("pass")).toBe("neutral");
  });

  it("counts errors and warnings, not info findings", () => {
    const finding = (severity: "error" | "warning" | "info") => ({ severity, code: "c", folder: null, message: "m" });
    expect(findingCounts([finding("error"), finding("warning"), finding("warning"), finding("info")])).toEqual({ errors: 1, warnings: 2 });
  });

  it("filters by status and category and searches the number, title and finding", () => {
    const item = experiment("12-ocr-2026-10-25", "FAIL", { category: "ingestion", title: "OCR text quality", finding: "Tesseract lost tables." });
    expect(matches(item, NO_FILTERS)).toBe(true);
    expect(matches(item, { ...NO_FILTERS, status: "FAIL" })).toBe(true);
    expect(matches(item, { ...NO_FILTERS, status: "PASS" })).toBe(false);
    expect(matches(item, { ...NO_FILTERS, category: "retrieval" })).toBe(false);
    expect(matches(item, { ...NO_FILTERS, search: "12" })).toBe(true);
    expect(matches(item, { ...NO_FILTERS, search: "ocr TEXT" })).toBe(true);
    expect(matches(item, { ...NO_FILTERS, search: "tables" })).toBe(true);
    expect(matches(item, { ...NO_FILTERS, search: "2026-10" })).toBe(false);
  });

  it("names the purposes, Optimisation first, and reads a missing purpose as Optimisation", () => {
    expect(PURPOSES.map(purposeLabel)).toEqual(["Optimisation", "Publication"]);
    expect(purposeLabel(undefined)).toBe("Optimisation");
  });

  it("formats sizes", () => {
    expect(formatSize(1)).toBe("1 byte");
    expect(formatSize(900)).toBe("900 bytes");
    expect(formatSize(2048)).toBe("2.0 KiB");
    expect(formatSize(3 * 1024 * 1024)).toBe("3.0 MiB");
  });
});
