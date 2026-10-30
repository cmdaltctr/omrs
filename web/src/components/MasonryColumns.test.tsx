import { act, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MasonryColumns } from "./MasonryColumns";

/**
 * Fakes layout sizes: the masonry area is *width* pixels wide and each card has
 * the height given for its title. Returns a function that sets new heights and
 * one that restores the real method.
 */
function fakeSizes(width: number, heights: Record<string, number> = {}) {
  const original = HTMLElement.prototype.getBoundingClientRect;
  let current = heights;
  HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
    let w = 0;
    let h = 0;
    if (this.dataset.testid === "masonry") w = width;
    if (this.dataset.masonryItem !== undefined) h = current[this.querySelector("h3")?.textContent ?? ""] ?? 0;
    return { width: w, height: h, top: 0, left: 0, right: w, bottom: h, x: 0, y: 0, toJSON: () => ({}) } as DOMRect;
  };
  return {
    setHeights: (next: Record<string, number>) => {
      current = next;
    },
    restore: () => {
      HTMLElement.prototype.getBoundingClientRect = original;
    },
  };
}

/** Replaces the no-op ResizeObserver stub with one whose callbacks the test can fire. */
function fakeResizeObserver() {
  const original = globalThis.ResizeObserver;
  const callbacks = new Set<() => void>();
  const observed = new Set<Element>();
  globalThis.ResizeObserver = class {
    private readonly callback: () => void;
    constructor(callback: () => void) {
      this.callback = callback;
      callbacks.add(callback);
    }
    observe(target: Element) {
      observed.add(target);
    }
    unobserve(target: Element) {
      observed.delete(target);
    }
    disconnect() {
      callbacks.delete(this.callback);
      observed.clear();
    }
  } as unknown as typeof ResizeObserver;
  return {
    observed,
    fire: () => callbacks.forEach((callback) => callback()),
    restore: () => {
      globalThis.ResizeObserver = original;
    },
  };
}

const FIVE = ["Ollama", "llama.cpp", "OpenRouter", "OpenAI-compatible", "Anthropic"];
const THREE = FIVE.slice(0, 3);
const TALL_LLAMA = { Ollama: 400, "llama.cpp": 1000, OpenRouter: 380, "OpenAI-compatible": 450, Anthropic: 370 };

function renderCards(titles: string[]) {
  render(
    <MasonryColumns>
      {titles.map((title) => (
        <section key={title}>
          <h3>{title}</h3>
          <input aria-label={title} />
        </section>
      ))}
    </MasonryColumns>,
  );
}

function names(column: HTMLElement) {
  return within(column).getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent);
}

const firstColumn = () => names(screen.getAllByTestId("masonry-column")[0]!);

describe("MasonryColumns", () => {
  it("fits as many 300 px columns as the area allows, up to three", async () => {
    const sizes = fakeSizes(700);
    try {
      renderCards(THREE);
      await waitFor(() => expect(screen.getAllByTestId("masonry-column")).toHaveLength(2));
      const columns = screen.getAllByTestId("masonry-column");
      expect(names(columns[0]!)).toEqual(["Ollama", "OpenRouter"]);
      expect(names(columns[1]!)).toEqual(["llama.cpp"]);
    } finally {
      sizes.restore();
    }
  });

  it("puts each card in the shortest column, so a short card does not sit under a tall one", async () => {
    const sizes = fakeSizes(1000, TALL_LLAMA);
    try {
      renderCards(FIVE);
      // Dealt in turn, Anthropic would sit under the 1000 px llama.cpp card.
      await waitFor(() => expect(firstColumn()).toEqual(["Ollama", "Anthropic"]));
      const columns = screen.getAllByTestId("masonry-column");
      expect(columns).toHaveLength(3);
      expect(names(columns[1]!)).toEqual(["llama.cpp"]);
      expect(names(columns[2]!)).toEqual(["OpenRouter", "OpenAI-compatible"]);
    } finally {
      sizes.restore();
    }
  });

  it("does not move a card while focus is inside the cards, and places them again when focus leaves", async () => {
    const sizes = fakeSizes(1000, TALL_LLAMA);
    const resizes = fakeResizeObserver();
    try {
      renderCards(FIVE);
      await waitFor(() => expect(firstColumn()).toEqual(["Ollama", "Anthropic"]));
      // Ollama grows while the user edits it; Anthropic would now fit better under OpenRouter.
      const field = screen.getByRole("textbox", { name: "Ollama" });
      act(() => field.focus());
      sizes.setHeights({ ...TALL_LLAMA, Ollama: 900 });
      await act(async () => {
        resizes.fire();
        await new Promise((resolve) => requestAnimationFrame(resolve));
      });
      expect(firstColumn()).toEqual(["Ollama", "Anthropic"]);
      act(() => field.blur());
      await waitFor(() => expect(firstColumn()).toEqual(["Ollama"]));
    } finally {
      resizes.restore();
      sizes.restore();
    }
  });

  it("keeps watching a card's size after it moves to another column", async () => {
    const sizes = fakeSizes(1000, TALL_LLAMA);
    const resizes = fakeResizeObserver();
    try {
      renderCards(FIVE);
      await waitFor(() => expect(firstColumn()).toEqual(["Ollama", "Anthropic"]));
      // Ollama grows (a panel finished loading) with three columns still in place: Anthropic
      // moves to the OpenRouter column, so React gives it a new element.
      sizes.setHeights({ ...TALL_LLAMA, Ollama: 900 });
      await act(async () => {
        resizes.fire();
        await new Promise((resolve) => requestAnimationFrame(resolve));
      });
      await waitFor(() => expect(firstColumn()).toEqual(["Ollama"]));
      const items = Array.from(document.querySelectorAll("[data-masonry-item]"));
      expect(items).toHaveLength(5);
      for (const item of items) expect(resizes.observed.has(item)).toBe(true);
    } finally {
      resizes.restore();
      sizes.restore();
    }
  });

  it("stacks every card in one column on a phone", () => {
    const sizes = fakeSizes(358);
    try {
      renderCards(THREE);
      expect(screen.getAllByTestId("masonry-column")).toHaveLength(1);
    } finally {
      sizes.restore();
    }
  });
});
