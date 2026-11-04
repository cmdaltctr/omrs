import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { JsonSchema, JsonValue, OperationDescriptor } from "../api/pipelines";
import { readingState } from "../settings/test/fixtures";
import { documentsServer } from "../test/fakeDocumentsServer";
import { renderWithProviders } from "../test/providers";
import { ParamField } from "./ParamField";
import { paramFields } from "./schema";
import { CATALOGUE } from "./test/catalogueFixture";

/** The Read document step edits `ocr_local_backends` with the same list control (change local-ocr-backends, task 6.4). */
const LIST: JsonSchema = { anyOf: [{ type: "array", items: { type: "string" } }, { type: "null" }], default: null };
const NAME = "ocr_local_backends";

function field(inherited: JsonValue | undefined) {
  const operation: OperationDescriptor = {
    ...CATALOGUE[0]!,
    lever_params: {},
    inherited_values: inherited === undefined ? {} : { [NAME]: inherited },
    parameters: { type: "object", properties: { [NAME]: { ...LIST, title: NAME } } },
  };
  return paramFields(operation)[0]!;
}

const BUILT_IN = [
  { name: "pp-ocrv6-small", available: true, reason: null },
  { name: "indra", available: false, reason: "Not installed." },
];

function serve(backends = BUILT_IN) {
  const state = readingState({}, { local_ocr_backends: backends });
  return documentsServer({ "GET /v1/settings/document-reading": () => state });
}

function setup(value: JsonValue | undefined, inherited?: JsonValue, backends = BUILT_IN) {
  const onChange = vi.fn();
  renderWithProviders(<ParamField field={field(inherited)} value={value} note={null} disabled={false} onChange={onChange} />, { fetchImpl: serve(backends).fetchImpl });
  return { onChange, user: userEvent.setup() };
}

describe("Read document step local OCR backends", () => {
  it("reads as a list field with its label", () => {
    expect(field(undefined)).toMatchObject({ kind: "stringList", label: "Local OCR backends" });
  });

  it("starts the step's own list from the host list", async () => {
    const { user, onChange } = setup(null, ["pp-ocrv6-small"]);
    await user.click(await screen.findByRole("radio", { name: "Set list" }));
    expect(onChange).toHaveBeenCalledWith(["pp-ocrv6-small"]);
  });

  it("edits the list with the shared control and offers only installed backends to add", async () => {
    const { user } = setup(["pp-ocrv6-small"]);
    const list = await screen.findByRole("list", { name: "Local OCR backends" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    await user.click(await screen.findByRole("combobox", { name: "Add backend" }));
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual(["indra (not installed)"]);
    expect(screen.getByRole("option", { name: "indra (not installed)" })).toHaveAttribute("aria-disabled", "true");
  });

  it("offers a backend that an installed package adds, from the server list", async () => {
    const { user } = setup(["pp-ocrv6-small"], undefined, [...BUILT_IN, { name: "fake-ocr", available: true, reason: null }]);
    await user.click(await screen.findByRole("combobox", { name: "Add backend" }));
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual(["indra (not installed)", "fake-ocr"]);
    expect(screen.getByRole("option", { name: "fake-ocr" })).not.toHaveAttribute("aria-disabled", "true");
  });
});
