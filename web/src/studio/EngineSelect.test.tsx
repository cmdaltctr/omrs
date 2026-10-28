import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { RuntimeItem } from "../api/integrations";
import { documentsServer } from "../test/fakeDocumentsServer";
import { renderWithProviders } from "../test/providers";
import { fieldLabel } from "./labels";
import { ParamField } from "./ParamField";
import type { ParamField as Field } from "./schema";

const ENGINE: Field = {
  name: "ocr_engine_primary",
  title: "Ocr Engine Primary",
  label: fieldLabel({ name: "ocr_engine_primary", title: "Ocr Engine Primary" }),
  description: "",
  kind: "string",
  nullable: true,
  options: [],
  defaultValue: null,
  unavailableOptions: {},
  inheritedValue: "dots-mocr",
  isCollection: false,
};

function engine(name: string, status: RuntimeItem["status"]): RuntimeItem {
  return { name, purpose: "", status, reason: null, fix: null, used_by: [] };
}

function serve() {
  return documentsServer({
    "GET /v1/integrations": () => ({
      status: "ok",
      install_type: "checkout",
      integrations: [],
      tools: [],
      runtime: {
        ocr_engines: [engine("dots-mocr", "missing"), engine("paddleocr-vl", "ready"), engine("local OCR tier", "ready")],
        model_files: [],
        local_servers: [],
      },
    }),
  });
}

describe("OCR engine choice on the Read document step", () => {
  it("uses the plain label", () => {
    expect(ENGINE.label).toBe("Primary OCR engine");
  });

  it("offers Inherit and the worker engines, each marked ready or not", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderWithProviders(<ParamField field={ENGINE} value={null} note={null} onChange={onChange} />, { fetchImpl: serve().fetchImpl });
    await user.click(await screen.findByRole("combobox", { name: "Primary OCR engine value" }));
    const options = (await screen.findAllByRole("option")).map((option) => option.textContent);
    expect(options).toEqual(["Inherit", "dots-mocr (not provisioned)", "paddleocr-vl (ready)"]);
    expect(screen.getByRole("option", { name: "dots-mocr (not provisioned)" })).toHaveAttribute("aria-disabled", "true");
    await user.click(screen.getByRole("option", { name: "paddleocr-vl (ready)" }));
    expect(onChange).toHaveBeenLastCalledWith("paddleocr-vl");
  });
});
