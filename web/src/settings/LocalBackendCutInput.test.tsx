import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LocalBackendCutInput } from "./LocalBackendCutInput";

const INVALID = "The cut must be a number from 0 to 1.";

function setup(props: Partial<Parameters<typeof LocalBackendCutInput>[0]> = {}) {
  const onChange = vi.fn();
  const onInvalid = vi.fn();
  render(<LocalBackendCutInput backend="pp-ocrv6-small" value={null} placeholder="Default 0.92" onChange={onChange} onInvalid={onInvalid} {...props} />);
  return { onChange, onInvalid, input: screen.getByRole("spinbutton", { name: "Confidence cut for pp-ocrv6-small" }), user: userEvent.setup() };
}

describe("LocalBackendCutInput", () => {
  it("is empty and shows the default when no cut is set", () => {
    const { input } = setup();
    expect(input).toHaveValue(null);
    expect(input).toHaveAttribute("placeholder", "Default 0.92");
    expect(input).toHaveAttribute("min", "0");
    expect(input).toHaveAttribute("max", "1");
    expect(input).toHaveAttribute("step", "0.01");
  });

  it("names its backend in the label", () => {
    render(<LocalBackendCutInput backend="fake-ocr" value={null} placeholder="Default 0.9" onChange={vi.fn()} />);
    expect(screen.getByRole("spinbutton", { name: "Confidence cut for fake-ocr" })).toBeInTheDocument();
  });

  it("shows the cut it is given", () => {
    const { input } = setup({ value: 0.95 });
    expect(input).toHaveValue(0.95);
  });

  it("reports a typed cut as a number", async () => {
    const { input, user, onChange } = setup();
    await user.type(input, "0.95");
    expect(onChange).toHaveBeenLastCalledWith(0.95);
    expect(screen.queryByText(INVALID)).toBeNull();
  });

  it("reports an emptied input as no value", async () => {
    const { input, user, onChange } = setup({ value: 0.95 });
    await user.clear(input);
    expect(onChange).toHaveBeenLastCalledWith(null);
    expect(screen.queryByText(INVALID)).toBeNull();
  });

  it.each(["1.5", "-0.1"])("refuses %s with the reason beside the input and reports no value", (text) => {
    const { input, onChange, onInvalid } = setup();
    fireEvent.change(input, { target: { value: text } });
    expect(screen.getByText(INVALID)).toBeInTheDocument();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription(INVALID);
    expect(onChange).not.toHaveBeenCalled();
    expect(onInvalid).toHaveBeenCalledTimes(1);
  });

  it("refuses text the browser could not read as a number", () => {
    // jsdom drops non-numeric text, so the test sets the flag a browser sets for "abc".
    const { input, onChange, onInvalid } = setup({ value: 0.5 });
    Object.defineProperty(input, "validity", { value: { badInput: true } });
    fireEvent.change(input, { target: { value: "" } });
    expect(screen.getByText(INVALID)).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
    expect(onInvalid).toHaveBeenCalledTimes(1);
  });

  it("drops the reason when the next value is good", () => {
    const { input, onChange } = setup();
    fireEvent.change(input, { target: { value: "1.5" } });
    fireEvent.change(input, { target: { value: "0.9" } });
    expect(screen.queryByText(INVALID)).toBeNull();
    expect(onChange).toHaveBeenLastCalledWith(0.9);
  });

  it("is read-only when locked", async () => {
    const { input, user, onChange } = setup({ value: 0.95, readOnly: true });
    expect(input).toHaveAttribute("readonly");
    await user.type(input, "1");
    expect(onChange).not.toHaveBeenCalled();
  });
});
