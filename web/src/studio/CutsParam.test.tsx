import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { JsonSchema, JsonValue, OperationDescriptor } from "../api/pipelines";
import { readingState } from "../settings/test/fixtures";
import { documentsServer } from "../test/fakeDocumentsServer";
import { renderWithProviders } from "../test/providers";
import { CutsParam } from "./CutsParam";
import { paramFields } from "./schema";
import { CATALOGUE } from "./test/catalogueFixture";

/** The Read document step sets one confidence cut for each backend of its effective list (change local-ocr-per-backend-cuts, task 7.4). */
const MAP: JsonSchema = { anyOf: [{ type: "object", additionalProperties: { type: "number" } }, { type: "null" }], default: null };
const NAME = "ocr_local_cuts";
const INVALID = "The cut must be a number from 0 to 1.";

function field(inherited: JsonValue | undefined) {
  const operation: OperationDescriptor = {
    ...CATALOGUE[0]!,
    lever_params: {},
    inherited_values: inherited === undefined ? {} : { [NAME]: inherited },
    parameters: { type: "object", properties: { [NAME]: { ...MAP, title: NAME } } },
  };
  return paramFields(operation)[0]!;
}

const BACKENDS = [
  { name: "pp-ocrv6-small", available: true, reason: null, default_cut: 0.92 },
  { name: "indra", available: true, reason: null, default_cut: 0.94 },
];

function setup({ value = null, inherited, backends = ["pp-ocrv6-small", "indra"], disabled = false }: { value?: JsonValue | undefined; inherited?: JsonValue; backends?: string[]; disabled?: boolean } = {}) {
  const onChange = vi.fn();
  const state = readingState({}, { local_ocr_backends: BACKENDS });
  const server = documentsServer({ "GET /v1/settings/document-reading": () => state });
  renderWithProviders(<CutsParam field={field(inherited)} value={value} backends={backends} disabled={disabled} onChange={onChange} />, { fetchImpl: server.fetchImpl });
  return { onChange, user: userEvent.setup() };
}

const cut = (name: string) => screen.findByRole("spinbutton", { name: `Confidence cut for ${name}` });

describe("CutsParam", () => {
  it("reads as an object field with its label", () => {
    expect(field(undefined)).toMatchObject({ kind: "json", label: "Confidence cuts" });
  });

  it("shows one cut input for each backend of the list it is given", async () => {
    setup({ backends: ["pp-ocrv6-small"] });
    expect(await cut("pp-ocrv6-small")).toBeInTheDocument();
    expect(screen.queryByRole("spinbutton", { name: "Confidence cut for indra" })).toBeNull();
    expect(screen.getAllByRole("spinbutton")).toHaveLength(1);
  });

  it("shows the host entry in an empty input, and the backend's default when the host has none", async () => {
    setup({ inherited: { indra: 0.96 } });
    expect(await cut("indra")).toHaveAttribute("placeholder", "Host 0.96");
    expect(await screen.findByRole("spinbutton", { name: "Confidence cut for pp-ocrv6-small" })).toHaveAttribute("placeholder", "Default 0.92");
    expect(await cut("indra")).toHaveValue(null);
  });

  it("shows the step's own cut in its input", async () => {
    setup({ value: { "pp-ocrv6-small": 0.88 }, inherited: {} });
    expect(await cut("pp-ocrv6-small")).toHaveValue(0.88);
    expect(await cut("indra")).toHaveValue(null);
  });

  it("saves a typed cut as a map", async () => {
    const { user, onChange } = setup({ inherited: {} });
    await user.type(await cut("pp-ocrv6-small"), "0.88");
    expect(onChange).toHaveBeenLastCalledWith({ "pp-ocrv6-small": 0.88 });
  });

  it("adds a cut beside the cuts already set", async () => {
    const { user, onChange } = setup({ value: { indra: 0.9 }, inherited: {} });
    await user.type(await cut("pp-ocrv6-small"), "0.88");
    expect(onChange).toHaveBeenLastCalledWith({ indra: 0.9, "pp-ocrv6-small": 0.88 });
  });

  it("keeps the cut of a backend that is not in the list", async () => {
    const { user, onChange } = setup({ value: { gone: 0.7 }, inherited: {}, backends: ["pp-ocrv6-small"] });
    await user.type(await cut("pp-ocrv6-small"), "0.88");
    expect(onChange).toHaveBeenLastCalledWith({ gone: 0.7, "pp-ocrv6-small": 0.88 });
  });

  it("saves null when the last cut is cleared", async () => {
    const { user, onChange } = setup({ value: { "pp-ocrv6-small": 0.88 }, inherited: {} });
    await user.clear(await cut("pp-ocrv6-small"));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("refuses 1.4 beside the input and saves nothing", async () => {
    const { onChange } = setup({ inherited: {} });
    fireEvent.change(await cut("pp-ocrv6-small"), { target: { value: "1.4" } });
    expect(screen.getByText(INVALID)).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("says a step entry replaces the host cut of its own backend only", async () => {
    setup({ inherited: {} });
    await cut("indra");
    expect(screen.getByText(/replaces the host cut for its own backend in this pipeline only/)).toBeInTheDocument();
  });

  it("makes every input read-only on a built-in profile", async () => {
    setup({ value: { indra: 0.9 }, inherited: {}, disabled: true });
    for (const name of ["pp-ocrv6-small", "indra"]) expect(await cut(name)).toHaveAttribute("readonly");
  });

  it("says so when the step reads with no local backend", async () => {
    setup({ backends: [] });
    expect(await screen.findByText("This step has no local OCR backend, so there is no cut to set.")).toBeInTheDocument();
    expect(screen.queryByRole("spinbutton")).toBeNull();
  });
});

/** Holds the draft as the step editor does, so a test reads what a save would carry. */
function Draft({ initial, backends }: { initial: JsonValue; backends: string[] }) {
  const [value, setValue] = useState<JsonValue>(initial);
  return (
    <>
      <CutsParam field={field({})} value={value} backends={backends} onChange={setValue} />
      <output aria-label="draft">{JSON.stringify(value)}</output>
    </>
  );
}

function setupDraft(initial: JsonValue = null, backends = ["pp-ocrv6-small", "indra"]) {
  const server = documentsServer({ "GET /v1/settings/document-reading": () => readingState({}, { local_ocr_backends: BACKENDS }) });
  renderWithProviders(<Draft initial={initial} backends={backends} />, { fetchImpl: server.fetchImpl });
  return { user: userEvent.setup(), draft: () => screen.getByLabelText("draft").textContent };
}

describe("CutsParam draft while a box is bad", () => {
  it("leaves no cut in the draft when 1.4 is typed key by key", async () => {
    const { user, draft } = setupDraft();
    await user.type(await cut("pp-ocrv6-small"), "1.4");
    expect(screen.getByText(INVALID)).toBeInTheDocument();
    expect(draft()).toBe("null");
  });

  it("drops only the bad backend and keeps the other cuts", async () => {
    const { user, draft } = setupDraft({ indra: 0.9 });
    await user.type(await cut("pp-ocrv6-small"), "1.4");
    expect(draft()).toBe(JSON.stringify({ indra: 0.9 }));
  });

  it("drops the earlier cut of a box that turns bad, and takes the new cut once it is good", async () => {
    const { user, draft } = setupDraft({ "pp-ocrv6-small": 1 });
    await user.type(await cut("pp-ocrv6-small"), ".5");
    expect(screen.getByText(INVALID)).toBeInTheDocument();
    expect(draft()).toBe("null");
    await user.clear(await cut("pp-ocrv6-small"));
    await user.type(await cut("pp-ocrv6-small"), "0.8");
    expect(screen.queryByText(INVALID)).toBeNull();
    expect(draft()).toBe(JSON.stringify({ "pp-ocrv6-small": 0.8 }));
  });
});
