import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { EffectiveControl, NodeSpec } from "../api/pipelines";
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

function setup(node: NodeSpec, { readOnly = false, controls = {} }: { readOnly?: boolean; controls?: Record<string, EffectiveControl[]> } = {}) {
  const operation = [...CATALOGUE, ...CATALOGUE_INGEST].find((entry) => entry.operation_id === node.operation)!;
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
