import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { OrderedListControl, type ListOption } from "./OrderedListControl";

const OPTIONS: ListOption[] = [
  { value: "pdf_inspector", label: "pdf_inspector", disabled: false, note: null, link: null },
  { value: "liteparse", label: "liteparse", disabled: false, note: null, link: null },
  { value: "pypdf", label: "pypdf", disabled: false, note: null, link: null },
  { value: "pypdfium2", label: "pypdfium2 (not installed)", disabled: true, note: "Not installed.", link: { href: "#/integrations/pdf-readers", text: "See PDF readers in Integrations" } },
];

const positionNote = (index: number) => (index === 0 ? "Reads first." : "Retries when the readers above return no text.");

function Harness({ start, options = OPTIONS, onChange = () => undefined }: { start: string[]; options?: ListOption[]; onChange?: (next: string[]) => void }) {
  const [value, setValue] = useState(start);
  return (
    <OrderedListControl
      label="PDF readers"
      noun="reader"
      value={value}
      options={options}
      positionNote={positionNote}
      onChange={(next) => {
        setValue(next);
        onChange(next);
      }}
    />
  );
}

const names = () =>
  within(screen.getByRole("list", { name: "PDF readers" }))
    .getAllByRole("listitem")
    .map((item) => item.querySelector("code")?.textContent);

describe("OrderedListControl", () => {
  it("shows the list in order, each row saying what its position does", () => {
    render(<Harness start={["pdf_inspector", "liteparse", "pypdf"]} />);
    expect(names()).toEqual(["pdf_inspector", "liteparse", "pypdf"]);
    const [first, second] = within(screen.getByRole("list", { name: "PDF readers" })).getAllByRole("listitem");
    expect(first).toHaveTextContent("Reads first.");
    expect(second).toHaveTextContent("Retries when the readers above return no text.");
  });

  it("moves a name up and down", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness start={["pdf_inspector", "liteparse", "pypdf"]} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "Move pypdf up" }));
    expect(onChange).toHaveBeenLastCalledWith(["pdf_inspector", "pypdf", "liteparse"]);
    expect(names()).toEqual(["pdf_inspector", "pypdf", "liteparse"]);
    await user.click(screen.getByRole("button", { name: "Move pdf_inspector down" }));
    expect(onChange).toHaveBeenLastCalledWith(["pypdf", "pdf_inspector", "liteparse"]);
  });

  it("disables Move up on the first row and Move down on the last row", () => {
    render(<Harness start={["pdf_inspector", "liteparse", "pypdf"]} />);
    expect(screen.getByRole("button", { name: "Move pdf_inspector up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move pypdf down" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move liteparse up" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Move liteparse down" })).toBeEnabled();
  });

  it("removes a name", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness start={["pdf_inspector", "liteparse", "pypdf"]} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "Remove liteparse" }));
    expect(onChange).toHaveBeenCalledWith(["pdf_inspector", "pypdf"]);
  });

  it("refuses to empty the list: the last name cannot be removed and a line says why", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness start={["pypdf"]} onChange={onChange} />);
    const remove = screen.getByRole("button", { name: "Remove pypdf" });
    expect(remove).toBeDisabled();
    await user.click(remove);
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText("The list needs at least one reader.")).toBeInTheDocument();
  });

  it("adds a name from the known names, and offers only names not yet in the list", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness start={["pdf_inspector"]} onChange={onChange} />);
    await user.click(screen.getByRole("combobox", { name: "Add reader" }));
    const offered = (await screen.findAllByRole("option")).map((option) => option.textContent);
    expect(offered).toEqual(["liteparse", "pypdf", "pypdfium2 (not installed)"]);
    await user.click(screen.getByRole("option", { name: "pypdf" }));
    expect(onChange).toHaveBeenCalledWith(["pdf_inspector", "pypdf"]);
    expect(names()).toEqual(["pdf_inspector", "pypdf"]);
  });

  it("does not let a name that cannot run be added, and says why", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness start={["pdf_inspector"]} onChange={onChange} />);
    await user.click(screen.getByRole("combobox", { name: "Add reader" }));
    expect(await screen.findByRole("option", { name: "pypdfium2 (not installed)" })).toHaveAttribute("aria-disabled", "true");
  });

  it("links to where to fix a name that cannot be added, under the add choice and once", () => {
    const second: ListOption = { value: "other", label: "other (not installed)", disabled: true, note: "Not installed.", link: OPTIONS[3]!.link };
    render(<Harness start={["pdf_inspector"]} options={[...OPTIONS, second]} />);
    const links = screen.getAllByRole("link", { name: "See PDF readers in Integrations" });
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "#/integrations/pdf-readers");
  });

  it("shows no link under the add choice when every name that can be added can run", () => {
    render(<Harness start={["pdf_inspector"]} options={OPTIONS.slice(0, 3)} />);
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("hides the add choice when every name is in the list", () => {
    render(<Harness start={OPTIONS.map((option) => option.value)} />);
    expect(screen.queryByRole("combobox", { name: "Add reader" })).toBeNull();
  });

  it("shows the note of a listed name that cannot run, with a link to where to fix it", () => {
    render(<Harness start={["pdf_inspector", "pypdfium2"]} />);
    const row = within(screen.getByRole("list", { name: "PDF readers" })).getAllByRole("listitem")[1]!;
    expect(row).toHaveTextContent("Not installed.");
    expect(within(row).getByRole("link", { name: "See PDF readers in Integrations" })).toHaveAttribute("href", "#/integrations/pdf-readers");
  });

  it("gives every button an accessible name, so a screen reader can tell the rows apart", () => {
    render(<Harness start={["pdf_inspector", "liteparse"]} />);
    for (const button of screen.getAllByRole("button")) expect(button).toHaveAccessibleName(/\S/);
    expect(screen.getAllByRole("button").map((button) => button.getAttribute("aria-label"))).toEqual([
      "Move pdf_inspector up",
      "Move pdf_inspector down",
      "Remove pdf_inspector",
      "Move liteparse up",
      "Move liteparse down",
      "Remove liteparse",
    ]);
  });

  it("renders the per-row slot inside each row, with the name and the position", () => {
    render(
      <OrderedListControl
        label="PDF readers"
        noun="reader"
        value={["pdf_inspector", "pypdf"]}
        options={OPTIONS}
        positionNote={positionNote}
        onChange={() => undefined}
        renderRow={(name, index) => <span>{`slot ${name} ${index}`}</span>}
      />,
    );
    const [first, second] = within(screen.getByRole("list", { name: "PDF readers" })).getAllByRole("listitem");
    expect(first).toHaveTextContent("slot pdf_inspector 0");
    expect(second).toHaveTextContent("slot pypdf 1");
  });
});
