import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { SearchHit } from "../api/documents";
import { EQ01_CHUNKS } from "../test/eq01Fixture";
import { ResultList } from "./ResultList";

function hit(text: string, overrides: Partial<SearchHit> = {}): SearchHit {
  return {
    score: 0.8123, score_kind: "dense_similarity_v1", source: "/srv/docs/eq01.pdf", page_label: null, text,
    reranked: false, metadata: {}, source_id: "sid-1", source_version: "v1", chunk_id: "c-1", source_chunk_index: 1, source_chunk_count: 4,
    ...overrides,
  } as SearchHit;
}

function show(hits: SearchHit[]) {
  return render(<ResultList hits={hits} sources={undefined} onShowChunk={vi.fn()} />);
}

describe("search result passages", () => {
  it.each(EQ01_CHUNKS.map((chunk) => [chunk.chunk_id.slice(0, 8), chunk] as const))(
    "shows every formula of eq01 chunk %s as maths with no KaTeX error",
    (_id, chunk) => {
      const { container } = show([hit(chunk.text)]);
      expect(container.querySelectorAll(".katex-error")).toHaveLength(0);
      expect(container.querySelectorAll(".katex").length).toBeGreaterThanOrEqual(chunk.formulas);
    },
  );

  it("shows Markdown signs as written and the formula as one rendered formula", () => {
    const { container } = show([hit("*a* # b [d](e) $x$")]);
    const passage = container.querySelector("li .whitespace-pre-wrap") as HTMLElement;
    expect(passage.firstElementChild?.textContent).toBe("*a* # b [d](e) ");
    expect(container.querySelectorAll(".katex")).toHaveLength(1);
    expect(container.querySelector("em, h1, a")).toBeNull();
  });

  it("keeps the line breaks of a passage", () => {
    const { container } = show([hit("first line\nsecond line")]);
    expect((container.querySelector("li .whitespace-pre-wrap") as HTMLElement).textContent).toBe("first line\nsecond line");
  });

  it("still shows the rank, the score and the Show chunk button", () => {
    show([hit("Body")]);
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show chunk" })).toBeInTheDocument();
  });
});
