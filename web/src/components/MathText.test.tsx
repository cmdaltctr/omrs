import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EQ01_CHUNKS } from "../test/eq01Fixture";
import { MathText } from "./MathText";

describe("MathText", () => {
  it("shows Markdown signs and HTML as written", () => {
    const text = "*a* # b <i>c</i> [d](e)";
    const { container } = render(<MathText text={text} />);
    expect(container).toHaveTextContent(text);
    expect(container.textContent).toBe(text);
    expect(container.querySelector("em, h1, i, a")).toBeNull();
  });

  it("keeps headings, list markers, quotes, rules, code marks and escapes as text", () => {
    const text = "# h\n- item\n> quote\n1. one\n`code` &amp; \\*x\\*\n---";
    const { container } = render(<MathText text={text} />);
    expect(container.textContent).toBe(text);
    expect(container.querySelector("h1, ul, ol, blockquote, code, hr, em")).toBeNull();
  });

  it("renders $x$ as one inline formula", () => {
    const { container } = render(<MathText text="$x$" />);
    expect(container.querySelectorAll(".katex")).toHaveLength(1);
    expect(container).not.toHaveTextContent("$");
  });

  it("renders a display formula and keeps the text around it", () => {
    const { container } = render(<MathText text={"Before\n\n$$\n\\sum_i y_i\n$$\n\nAfter"} />);
    expect(container.querySelectorAll(".katex-display")).toHaveLength(1);
    expect(container).toHaveTextContent("Before");
    expect(container).toHaveTextContent("After");
  });

  it.each(EQ01_CHUNKS.map((chunk) => [chunk.chunk_id.slice(0, 8), chunk] as const))(
    "renders eq01 chunk %s with no KaTeX error",
    (_id, chunk) => {
      const { container } = render(<MathText text={chunk.text} />);
      expect(container.querySelectorAll(".katex-error")).toHaveLength(0);
      expect(container.querySelectorAll(".katex").length).toBeGreaterThanOrEqual(chunk.formulas);
    },
  );

  it("keeps indentation, trailing spaces, tabs and runs of blank lines exactly", () => {
    const text = "def f(x):\n    if x:\n        return 1\n\n\n\ttabbed \nlast  ";
    const { container } = render(<MathText text={text} />);
    expect(container.textContent).toBe(text);
    expect(container.firstElementChild).toHaveClass("whitespace-pre-wrap");
  });

  it("keeps text around a formula exactly, including its line breaks", () => {
    const { container } = render(<MathText text={"  one $x$ two  \n three"} />);
    expect(container.querySelectorAll(".katex")).toHaveLength(1);
    expect(container.firstElementChild?.firstElementChild?.textContent).toBe("  one ");
    expect(container.textContent?.endsWith(" two  \n three")).toBe(true);
  });

  it("shows shell and PHP dollar signs as written", () => {
    const text = "echo $HOME and $PATH\n<?php $name = $user->name; ?>";
    const { container } = render(<MathText text={text} />);
    expect(container.querySelector(".katex")).toBeNull();
    expect(container.textContent).toBe(text);
  });

  it("shows dollar amounts as written, with every space", () => {
    const text = "It costs $5 and $10, or $40 more. A ton of coal is another $";
    const { container } = render(<MathText text={text} />);
    expect(container.querySelector(".katex")).toBeNull();
    expect(container.textContent).toBe(text);
  });

  it("shows an escaped dollar sign as written", () => {
    const { container } = render(<MathText text={"\\$5 and \\$10"} />);
    expect(container.querySelector(".katex-error")).toBeNull();
    expect(container.textContent).toBe("\\$5 and \\$10");
  });

  it("still renders formulas with no space inside their dollar signs", () => {
    const { container } = render(<MathText text={"a $x$, b $y$."} />);
    expect(container.querySelectorAll(".katex")).toHaveLength(2);
  });

  it("shows a formula that cannot be parsed as its source and keeps the rest", () => {
    const { container } = render(<MathText text={"Before $\\frac{a}{$ after"} />);
    const errors = container.querySelectorAll(".katex-error");
    expect(errors).toHaveLength(1);
    expect(errors[0]).toHaveTextContent("\\frac{a}{");
    expect(container).toHaveTextContent("after");
  });

  it("creates no element from HTML or a link command", () => {
    const { container } = render(<MathText text={"$\\href{javascript:alert(1)}{x}$ <script>window.__x = 1</script>"} />);
    expect(container.querySelector("a, script")).toBeNull();
    expect(container).toHaveTextContent("<script>window.__x = 1</script>");
  });
});
