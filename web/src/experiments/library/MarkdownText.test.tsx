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
