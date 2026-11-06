import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { EffectiveControl, JsonValue, NodeSpec, OperationDescriptor } from "../api/pipelines";
import { documentsServer } from "../test/fakeDocumentsServer";
import { renderWithProviders } from "../test/providers";
import { emptyDraft, type Draft } from "./graph";
import { StepSettingsFields } from "./StepSettingsFields";
import { CATALOGUE } from "./test/catalogueFixture";
import { CATALOGUE_INGEST } from "./test/catalogueIngest";

function draftWith(node: NodeSpec): Draft {
  const base = emptyDraft();
  return { ...base, graph: { ...base.graph, nodes: [node] } };
}

function setup(node: NodeSpec, { readOnly = false, controls = {}, change }: { readOnly?: boolean; controls?: Record<string, EffectiveControl[]>; change?: (operation: OperationDescriptor) => OperationDescriptor } = {}) {
  const found = [...CATALOGUE, ...CATALOGUE_INGEST].find((entry) => entry.operation_id === node.operation)!;
  const operation = change ? change(found) : found;
  const seen = { draft: draftWith(node) };
  function Harness() {
    const [draft, setDraft] = useState(seen.draft);
    seen.draft = draft;
    return <StepSettingsFields draft={draft} nodeId={node.id} operation={operation} controls={controls} readOnly={readOnly} onChange={(change) => setDraft((d) => change(d))} />;
  }
  renderWithProviders(<Harness />, { fetchImpl: documentsServer().fetchImpl });
  return { seen, user: userEvent.setup() };
}

const legends = () => screen.getAllByRole("group").map((group) => group.querySelector("legend")?.textContent);

describe("StepSettingsFields", () => {
  it("shows the Prepare query settings with their plain labels", () => {
    setup({ id: "pq", operation: "retrieve.prepare_query", version: 1 });
    expect(legends()).toEqual(expect.arrayContaining(["Number of results", "Minimum similarity", "Reranker", "Candidates to fetch", "Collection"]));
    expect(screen.queryByRole("checkbox", { name: "Bypass this step" })).toBeNull();
  });

  it("shows the value note from the latest check", () => {
    const controls = { pq: [{ lever: "retrieval.top_k", value: 10, source: "profile", detail: "profile 'documents'" }] };
    setup({ id: "pq", operation: "retrieve.prepare_query", version: 1 }, { controls });
    expect(within(screen.getByRole("group", { name: "Number of results" })).getByText("Value in use: 10 (from profile)")).toBeInTheDocument();
  });

  it("writes a metadata filter to the draft and clears it", async () => {
    const { seen, user } = setup({ id: "pq", operation: "retrieve.prepare_query", version: 1 });
    const field = screen.getByRole("textbox", { name: "Metadata filter value" });
    await user.click(field);
    await user.paste('{"file_type": "pdf"}');
    expect(seen.draft.graph.nodes[0]?.params).toEqual({ metadata_filter: { file_type: "pdf" } });
    await user.clear(field);
    expect(seen.draft.graph.nodes[0]).not.toHaveProperty("params.metadata_filter");
  });

  it("offers the bypass switch for Cross-encoder rerank and writes it to the draft", async () => {
    const { seen, user } = setup({ id: "rr", operation: "select.rerank", version: 1 });
    await user.click(screen.getByRole("checkbox", { name: "Bypass this step" }));
    expect(seen.draft.graph.nodes[0]?.enabled).toBe(false);
    expect(screen.getByRole("group", { name: "Reranker" })).toBeInTheDocument();
  });

  it("disables every control on a read-only graph", () => {
    setup({ id: "rr", operation: "select.rerank", version: 1, params: { enabled: false } }, { readOnly: true });
    expect(screen.getByRole("checkbox", { name: "Bypass this step" })).toBeDisabled();
    for (const radio of within(screen.getByRole("group", { name: "Reranker" })).getAllByRole("radio")) expect(radio).toBeDisabled();
    expect(within(screen.getByRole("group", { name: "Reranker" })).getByRole("radio", { name: "Off" })).toBeChecked();
  });

  it("shows the list options of Read document and hides the single-value options the step does not set", () => {
    setup({ id: "rd", operation: "read.document", version: 1 });
    expect(legends()).toEqual(expect.arrayContaining(["PDF readers", "OCR engines"]));
    expect(legends()).not.toContain("PDF reader");
  });

  it("offers Non-Latin routing on Read document with Inherit and writes the chosen value", async () => {
    const { seen, user } = setup({ id: "rd", operation: "read.document", version: 1 });
    const field = screen.getByRole("group", { name: "Non-Latin routing" });
    expect(field).toHaveTextContent("Inherit uses the host value: off.");
    await user.click(within(field).getByRole("combobox", { name: "Non-Latin routing value" }));
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual(["Inherit", "off", "detect", "always"]);
    await user.click(screen.getByRole("option", { name: "always" }));
    expect(seen.draft.graph.nodes[0]?.params).toEqual({ ocr_non_latin_routing: "always" });
    await user.click(within(field).getByRole("combobox", { name: "Non-Latin routing value" }));
    await user.click(await screen.findByRole("option", { name: "Inherit" }));
    expect(seen.draft.graph.nodes[0]).not.toHaveProperty("params.ocr_non_latin_routing");
  });

  it("keeps the old PDF reader control, with its unavailable choices, on a saved step that still sets it", async () => {
    const { user } = setup({ id: "rd", operation: "read.document", version: 1, params: { pdf_reader: "liteparse" } });
    expect(legends()).toContain("PDF reader");
    await user.click(within(screen.getByRole("group", { name: "PDF reader" })).getByRole("combobox", { name: "PDF reader value" }));
    expect(await screen.findByRole("option", { name: /pypdfium2 \(not installed\)/ })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("The package 'pypdfium2' is not installed.")).toBeInTheDocument();
  });

  it("clears the old options in the same update that sets their list, so the step never sets both forms", async () => {
    const saved = { pdf_reader: "liteparse", ocr_engine_primary: "dots-mocr", ocr_engine_fallback: "paddleocr-vl" };
    const { seen, user } = setup({ id: "rd", operation: "read.document", version: 1, params: saved });
    await user.click(within(screen.getByRole("group", { name: "PDF readers" })).getByRole("radio", { name: "Set list" }));
    await user.click(within(screen.getByRole("group", { name: "OCR engines" })).getByRole("radio", { name: "Set list" }));
    const params = seen.draft.graph.nodes[0]?.params ?? {};
    expect(params.pdf_readers).toBeDefined();
    expect(params.ocr_engines).toBeDefined();
    expect(params).not.toHaveProperty("pdf_reader");
    expect(params).not.toHaveProperty("ocr_engine_primary");
    expect(params).not.toHaveProperty("ocr_engine_fallback");
  });
});

/** The Read document step with the local OCR list and the cuts option (change local-ocr-per-backend-cuts, task 7.4). */
function withCuts(hostBackends: JsonValue, hostCuts: JsonValue): (operation: OperationDescriptor) => OperationDescriptor {
  const list = { anyOf: [{ type: "array", items: { type: "string" } }, { type: "null" }], default: null };
  const map = { anyOf: [{ type: "object", additionalProperties: { type: "number" } }, { type: "null" }], default: null };
  return (operation) => ({
    ...operation,
    inherited_values: { ...operation.inherited_values, ocr_local_backends: hostBackends, ocr_local_cuts: hostCuts },
    parameters: { ...operation.parameters, properties: { ...operation.parameters.properties, ocr_local_backends: { ...list, title: "Ocr Local Backends" }, ocr_local_cuts: { ...map, title: "Ocr Local Cuts" } } },
  });
}

describe("StepSettingsFields confidence cuts", () => {
  const spin = (name: string) => screen.findByRole("spinbutton", { name: `Confidence cut for ${name}` });

  it("shows a cut input for each backend of the inherited host list", async () => {
    setup({ id: "rd", operation: "read.document", version: 1 }, { change: withCuts(["pp-ocrv6-small", "indra"], { indra: 0.96 }) });
    expect(await spin("pp-ocrv6-small")).toBeInTheDocument();
    expect(await spin("indra")).toHaveAttribute("placeholder", "Host 0.96");
    expect(within(screen.getByRole("group", { name: "Confidence cuts" })).getAllByRole("spinbutton")).toHaveLength(2);
  });

  it("shows a cut input for each backend of the step's own list instead", async () => {
    setup({ id: "rd", operation: "read.document", version: 1, params: { ocr_local_backends: ["indra"] } }, { change: withCuts(["pp-ocrv6-small", "indra"], {}) });
    expect(await spin("indra")).toBeInTheDocument();
    expect(screen.queryByRole("spinbutton", { name: "Confidence cut for pp-ocrv6-small" })).toBeNull();
  });

  it("writes a typed cut to the step and removes the option when it is cleared", async () => {
    const { seen, user } = setup({ id: "rd", operation: "read.document", version: 1 }, { change: withCuts(["pp-ocrv6-small"], {}) });
    const input = await spin("pp-ocrv6-small");
    await user.type(input, "0.88");
    expect(seen.draft.graph.nodes[0]?.params).toEqual({ ocr_local_cuts: { "pp-ocrv6-small": 0.88 } });
    await user.clear(input);
    // A cleared option leaves the step, as every other option does, so the step inherits.
    expect(seen.draft.graph.nodes[0]).not.toHaveProperty("params.ocr_local_cuts");
  });

  it("makes the cut inputs read-only on a read-only graph", async () => {
    setup({ id: "rd", operation: "read.document", version: 1 }, { readOnly: true, change: withCuts(["pp-ocrv6-small"], {}) });
    expect(await spin("pp-ocrv6-small")).toHaveAttribute("readonly");
  });

  it("names the host cuts in the inherit note, and says nothing when the host holds none", async () => {
    setup({ id: "rd", operation: "read.document", version: 1 }, { change: withCuts(["indra"], { indra: 0.96 }) });
    expect(await screen.findByText("Inherit uses the host value: indra 0.96.")).toBeInTheDocument();
  });

  it("shows no inherit note for an empty host map", async () => {
    setup({ id: "rd", operation: "read.document", version: 1 }, { change: withCuts(["indra"], {}) });
    await spin("indra");
    expect(screen.queryByText(/Inherit uses the host value: \./)).toBeNull();
  });
});

