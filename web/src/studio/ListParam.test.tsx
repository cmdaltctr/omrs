import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PdfReaderItem, RuntimeItem } from "../api/integrations";
import type { JsonSchema, JsonValue, OperationDescriptor } from "../api/pipelines";
import { documentsServer } from "../test/fakeDocumentsServer";
import { renderWithProviders } from "../test/providers";
import { ParamField } from "./ParamField";
import { paramFields } from "./schema";
import { CATALOGUE } from "./test/catalogueFixture";

const LIST: JsonSchema = { anyOf: [{ type: "array", items: { type: "string" } }, { type: "null" }], default: null };

function field(name: string, inherited: JsonValue | undefined) {
  const operation: OperationDescriptor = {
    ...CATALOGUE[0]!,
    lever_params: {},
    inherited_values: inherited === undefined ? {} : { [name]: inherited },
    parameters: { type: "object", properties: { [name]: { ...LIST, title: name } } },
  };
  return paramFields(operation)[0]!;
}

const READERS: PdfReaderItem[] = [
  { name: "pdf_inspector", installed: true, extra: "pdf-inspector", fix_command: null, used_by: [] },
  { name: "liteparse", installed: true, extra: "liteparse", fix_command: null, used_by: [] },
  { name: "pypdfium2", installed: false, extra: "pdf-pypdfium2", fix_command: "uv sync --extra pdf-pypdfium2", used_by: [] },
  { name: "pypdf", installed: true, extra: null, fix_command: null, used_by: [] },
];

function engine(name: string, status: RuntimeItem["status"]): RuntimeItem {
  return { name, purpose: "", status, reason: status === "ready" ? null : `Not provisioned. Run python3 ocr-workers/provision.py ${name}.`, fix: null, used_by: [] };
}

function serve() {
  return documentsServer({
    "GET /v1/integrations": () => ({
      status: "ok",
      install_type: "checkout",
      integrations: [],
      tools: [],
      pdf_readers: READERS,
      runtime: { ocr_engines: [engine("dots-mocr", "ready"), engine("paddleocr-vl", "missing"), engine("local OCR tier", "ready")], model_files: [], local_servers: [] },
    }),
  });
}

function setup(name: string, value: JsonValue | undefined, inherited?: JsonValue, disabled = false) {
  const onChange = vi.fn();
  renderWithProviders(<ParamField field={field(name, inherited)} value={value} note={null} disabled={disabled} onChange={onChange} />, { fetchImpl: serve().fetchImpl });
  return { onChange, user: userEvent.setup() };
}

describe("schema", () => {
  it("reads an array of strings as a list", () => {
    expect(field("pdf_readers", undefined)).toMatchObject({ kind: "stringList", nullable: true, label: "PDF readers" });
    expect(field("ocr_engines", undefined)).toMatchObject({ kind: "stringList", label: "OCR engines" });
  });
});

describe("Read document step lists", () => {
  it("inherits by default and shows the host list in the note", async () => {
    setup("pdf_readers", null, ["pdf_inspector", "liteparse", "pypdf"]);
    expect(await screen.findByRole("radio", { name: "Inherit" })).toBeChecked();
    expect(screen.getByText("Inherit uses the host value: pdf_inspector, liteparse, pypdf.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "PDF readers" })).toBeNull();
  });

  it("starts the step's own list from the host list when Set list is chosen", async () => {
    const { user, onChange } = setup("pdf_readers", null, ["pdf_inspector", "liteparse", "pypdf"]);
    await user.click(await screen.findByRole("radio", { name: "Set list" }));
    expect(onChange).toHaveBeenCalledWith(["pdf_inspector", "liteparse", "pypdf"]);
  });

  it("starts the engine list from the first ready engine when the host reports no list", async () => {
    const { user, onChange } = setup("ocr_engines", null);
    await user.click(await screen.findByRole("radio", { name: "Set list" }));
    expect(onChange).toHaveBeenCalledWith(["dots-mocr"]);
  });

  it("returns to Inherit with null", async () => {
    const { user, onChange } = setup("pdf_readers", ["pypdf"]);
    await user.click(await screen.findByRole("radio", { name: "Inherit" }));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("edits the reader list in order with the shared control", async () => {
    const { user, onChange } = setup("pdf_readers", ["pdf_inspector", "pypdf"]);
    const list = await screen.findByRole("list", { name: "PDF readers" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "Move pypdf up" }));
    expect(onChange).toHaveBeenLastCalledWith(["pypdf", "pdf_inspector"]);
    await user.click(screen.getByRole("combobox", { name: "Add reader" }));
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual(["liteparse", "pypdfium2 (optional, not installed)"]);
    expect(screen.getByRole("option", { name: "pypdfium2 (optional, not installed)" })).toHaveAttribute("aria-disabled", "true");
  });

  it("refuses to empty the step's list", async () => {
    const { user, onChange } = setup("pdf_readers", ["pypdf"]);
    await screen.findByRole("list", { name: "PDF readers" });
    expect(screen.getByRole("button", { name: "Remove pypdf" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Remove pypdf" }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("offers the worker engines, not the local OCR tier, and marks one that is not provisioned", async () => {
    const { user, onChange } = setup("ocr_engines", ["dots-mocr"]);
    await user.click(await screen.findByRole("combobox", { name: "Add engine" }));
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual(["paddleocr-vl (not provisioned)"]);
    await user.click(screen.getByRole("option"));
    expect(onChange).toHaveBeenCalledWith(["dots-mocr", "paddleocr-vl"]);
  });

  it("warns when pdf_inspector is the step's only reader", async () => {
    setup("pdf_readers", ["pdf_inspector"]);
    expect(await screen.findByText(/pdf_inspector alone has no retry/)).toBeInTheDocument();
  });

  it("shows the list without a way to change it on a read-only graph", async () => {
    setup("pdf_readers", ["pdf_inspector", "pypdf"], undefined, true);
    expect(await screen.findByRole("combobox", { name: "Add reader" })).toBeDisabled();
    for (const button of screen.getAllByRole("button")) expect(button).toBeDisabled();
    expect(screen.getByRole("radio", { name: "Inherit" })).toBeDisabled();
  });
});

