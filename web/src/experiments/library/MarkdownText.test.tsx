import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownText } from "./MarkdownText";

describe("experiment Markdown links", () => {
  it("shows javascript: and data: links as text, with no link element", () => {
    const { container } = render(<MarkdownText text={"[x](javascript:alert(1)) and [y](data:text/html,hi)"} fileNames={new Set()} onOpenFile={() => undefined} />);
    expect(screen.getByText("x")).toBeInTheDocument();
    expect(screen.getByText("y")).toBeInTheDocument();
    expect(container.querySelector("a")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("experiment Markdown maths", () => {
  const show = (text: string) => render(<MarkdownText text={text} fileNames={new Set()} onOpenFile={() => undefined} />);

  it("renders a display formula on its own lines as one display formula", () => {
    const { container } = show("Bound:\n\n$$\n\\log p_{\\theta}(\\mathbf{x})\n$$\n");
    expect(container.querySelectorAll(".katex-display")).toHaveLength(1);
    expect(container.querySelectorAll(".katex-error")).toHaveLength(0);
    expect(container).not.toHaveTextContent("$");
  });

  it("renders inline maths next to Markdown", () => {
    const { container } = show("The **loss** is $x^2$.");
    expect(container.querySelectorAll(".katex")).toHaveLength(1);
    expect(container.querySelector("strong")).toHaveTextContent("loss");
  });

  it("renders a formula next to a script tag and creates no script element", () => {
    const { container } = show("$x$ <script>window.__x = 1</script>");
    expect(container.querySelectorAll(".katex")).toHaveLength(1);
    expect(container.querySelector("script")).toBeNull();
    expect(container).toHaveTextContent("<script>window.__x = 1</script>");
  });
});
