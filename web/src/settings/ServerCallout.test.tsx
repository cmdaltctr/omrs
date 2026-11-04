import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ServerCallout } from "./ServerCallout";

describe("ServerCallout", () => {
  it("shows an info icon beside an info note", () => {
    render(<ServerCallout text="A fact." />);
    const note = screen.getByRole("note");
    expect(note.querySelector("svg.lucide-info")).not.toBeNull();
    expect(note).toHaveTextContent("A fact.");
  });

  it("shows a warning icon beside a warning note", () => {
    render(<ServerCallout tone="warning" text="A risk." />);
    const note = screen.getByRole("note");
    expect(note.querySelector("svg.lucide-triangle-alert")).not.toBeNull();
    expect(note.querySelector("svg.lucide-info")).toBeNull();
  });

  it("hides the icon from screen readers", () => {
    render(<ServerCallout text="A fact." />);
    expect(screen.getByRole("note").querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
});
