import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../test/providers";
import { ParamField } from "./ParamField";
import { paramFields } from "./schema";
import { CATALOGUE } from "./test/catalogueFixture";

const NOT_READY = "granite_guardian needs a judge model. Set answer.verify_model in Settings > Chat.";

function judgeField(unavailable: Record<string, string> = {}) {
  const verify = CATALOGUE.find((operation) => operation.operation_id === "verify.claims");
  if (verify === undefined) throw new Error("verify.claims missing from the fixture");
  const operation = { ...verify, unavailable_options: { verify_judge: unavailable } };
  const field = paramFields(operation).find((candidate) => candidate.name === "verify_judge");
  if (field === undefined) throw new Error("verify_judge missing from the fixture");
  return field;
}

describe("Claim judge on the Verify claims step", () => {
  it("sits beside Check claims with the plain label", () => {
    const verify = CATALOGUE.find((operation) => operation.operation_id === "verify.claims")!;
    expect(paramFields(verify).map((field) => field.label)).toEqual(["Check claims", "Claim judge"]);
  });

  it("offers the server's strategies and marks a not-ready one", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const field = judgeField({ granite_guardian: NOT_READY });
    renderWithProviders(<ParamField field={field} value={null} note={null} onChange={onChange} />);
    await user.click(screen.getByRole("combobox", { name: "Claim judge value" }));
    const options = screen.getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(["Inherit", "Chat model", "Clef-Flash decision model", "Granite Guardian (not ready)"]);
    expect(screen.getByRole("option", { name: "Granite Guardian (not ready)" })).toHaveAttribute("aria-disabled", "true");
    await user.click(screen.getByRole("option", { name: "Clef-Flash decision model" }));
    expect(onChange).toHaveBeenLastCalledWith("clef_flash");
  });

  it("names the missing setting under the field", () => {
    renderWithProviders(<ParamField field={judgeField({ clef_flash: NOT_READY })} value={null} note={null} onChange={() => undefined} />);
    expect(screen.getByText(NOT_READY, { exact: false })).toBeInTheDocument();
  });

  it("removes the override with Inherit", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderWithProviders(<ParamField field={judgeField()} value="clef_flash" note={null} onChange={onChange} />);
    await user.click(screen.getByRole("combobox", { name: "Claim judge value" }));
    await user.click(screen.getByRole("option", { name: "Inherit" }));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });
});
