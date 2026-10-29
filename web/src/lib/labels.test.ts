import { describe, expect, it } from "vitest";
import { availabilityLabel, chunkPosition, formatScore, pageText, plural, scoreKindLabel } from "./labels";

describe("labels", () => {
  it("names one page, or the first and last page a merged row spans", () => {
    expect(pageText("5", ["5", "6"])).toBe("Pages 5–6");
    expect(pageText("5", ["5", "6", "7"])).toBe("Pages 5–7");
    expect(pageText("12", ["12"])).toBe("Page 12");
    expect(pageText("3")).toBe("Page 3");
    expect(pageText(null)).toBeNull();
  });

  it("names the score kind and keeps the raw identifier", () => {
    expect(scoreKindLabel("rrf_v1")).toBe("Reciprocal rank fusion (rrf_v1)");
    expect(scoreKindLabel("new_kind_v9")).toBe("Unknown score kind (new_kind_v9)");
  });

  it("formats scores to four places", () => {
    expect(formatScore(0.81234)).toBe("0.8123");
  });

  it("never reads an unknown availability as lost", () => {
    expect(availabilityLabel(true)).toBe("Missing on this machine");
    expect(availabilityLabel(false)).toBe("Present on this machine");
    expect(availabilityLabel(null)).toBe("Unknown on this machine");
  });

  it("pluralises and positions", () => {
    expect(plural(1, "chunk")).toBe("1 chunk");
    expect(plural(2, "chunk")).toBe("2 chunks");
    expect(chunkPosition(2, 4)).toBe("Chunk 3 of 4");
    expect(chunkPosition(2, null)).toBe("Chunk 3");
    expect(chunkPosition(null, null)).toBe("Position unknown");
  });
});
