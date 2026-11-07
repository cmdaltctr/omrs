import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import type { JsonSchema, NodeSpec, OperationDescriptor } from "../api/pipelines";
import type { DocumentReadingKey, DocumentReadingSetting } from "../api/settingsDocumentReading";
import { PYPDFIUM2_READER } from "../settings/test/pdfReaderFixtures";
import { readingState, settingsServer } from "../settings/test/fixtures";
import { documentRouters } from "../settings/test/routerFixtures";
import { renderWithProviders } from "../test/providers";
import { emptyDraft, type Draft } from "./graph";
import { StepSettingsFields } from "./StepSettingsFields";
import { CATALOGUE_INGEST } from "./test/catalogueIngest";

const nullable = (schema: JsonSchema, title: string): JsonSchema => ({ anyOf: [schema, { type: "null" }], default: null, title });
const SWITCH: JsonSchema = { type: "boolean" };
const LIST: JsonSchema = { type: "array", items: { type: "string" } };

/** The Read document operation as the server describes it now: every key of the Page routing panel, the three old options and two other parameters. */
function readOperation(): OperationDescriptor {
  const found = CATALOGUE_INGEST.find((entry) => entry.operation_id === "read.document")!;
  const properties: Record<string, JsonSchema> = {
    strategy_fallback: nullable({ enum: ["markdown", "code", "sentence"], type: "string" }, "Strategy Fallback"),
    code_chunk_lines: nullable({ type: "integer", minimum: 1 }, "Code Chunk Lines"),
    pdf_reader: nullable({ enum: ["auto", "liteparse", "pypdf"], type: "string" }, "Pdf Reader"),
    pdf_readers: nullable(LIST, "Pdf Readers"),
    ocr_fallback_enabled: nullable(SWITCH, "Ocr Fallback Enabled"),
    ocr_routing_unit: nullable({ enum: ["page"], type: "string" }, "Ocr Routing Unit"),
    ocr_engines: nullable(LIST, "Ocr Engines"),
    ocr_engine_primary: nullable({ type: "string" }, "Ocr Engine Primary"),
    ocr_engine_fallback: nullable({ type: "string" }, "Ocr Engine Fallback"),
    ocr_skip_blank_pages: nullable(SWITCH, "Ocr Skip Blank Pages"),
    ocr_maths_routing_enabled: nullable(SWITCH, "Ocr Maths Routing Enabled"),
    ocr_non_latin_routing: nullable({ enum: ["off", "detect", "always"], type: "string" }, "Ocr Non Latin Routing"),
    ocr_local_backends: nullable(LIST, "Ocr Local Backends"),
    ocr_local_cuts: nullable({ type: "object", additionalProperties: { type: "number" } }, "Ocr Local Cuts"),
    document_router: nullable({ type: "string" }, "Document Router"),
  };
  return {
    ...found,
    inherited_values: { pdf_readers: ["pdf_inspector", "liteparse", "pypdf"], ocr_engines: ["dots-mocr", "paddleocr-vl"], ocr_local_backends: ["pp-ocrv6-small"], ocr_local_cuts: {}, ocr_skip_blank_pages: true, ocr_non_latin_routing: "off" },
    parameters: { ...found.parameters, properties },
    unavailable_options: {},
  };
}

const INTEGRATIONS = {
  status: "ok",
  install_type: "uv-tool",
  integrations: [],
  tools: [],
  pdf_readers: [{ name: "pdf_inspector", installed: true, extra: null, fix_command: null, used_by: [] }, { name: "pypdf", installed: true, extra: null, fix_command: null, used_by: [] }, PYPDFIUM2_READER],
  runtime: { ocr_engines: [], model_files: [], local_servers: [] },
};

type Rows = Partial<Record<DocumentReadingKey, Partial<DocumentReadingSetting>>>;

function setup(params: NodeSpec["params"], { readOnly = false, rows = {}, routers = [] as string[] }: { readOnly?: boolean; rows?: Rows; routers?: string[] } = {}) {
  const node: NodeSpec = { id: "rd", operation: "read.document", version: 1, params };
  const base = emptyDraft();
  const seen = { draft: { ...base, graph: { ...base.graph, nodes: [node] } } as Draft };
  const server = settingsServer({
    "GET /v1/settings/document-reading": () => readingState(rows),
    "GET /v1/settings/document-routers": () => documentRouters(routers.map((name) => ({ name }) as never)),
    "GET /v1/integrations": () => INTEGRATIONS,
  });
  function Harness() {
    const [draft, setDraft] = useState(seen.draft);
    seen.draft = draft;
    return <StepSettingsFields draft={draft} nodeId="rd" operation={readOperation()} controls={{}} readOnly={readOnly} onChange={(change) => setDraft((d) => change(d))} />;
  }
  renderWithProviders(<Harness />, { fetchImpl: server.fetchImpl });
  return { seen, user: userEvent.setup() };
}

const panel = () => screen.getByRole("region", { name: "Page routing" });
const stepHeadings = () => within(panel()).getAllByRole("heading", { level: 4 });
const step = (number: number) => stepHeadings()[number - 1]!.closest<HTMLElement>("[data-slot='page-routing-step']")!;
const legendsIn = (element: HTMLElement) => within(element).queryAllByRole("group").map((group) => group.querySelector(":scope > legend")?.textContent);
const group = (name: string) => within(panel()).getByRole("group", { name });
const params = (seen: { draft: Draft }) => seen.draft.graph.nodes[0]?.params;

describe("Read document step, Page routing panel", () => {
  it("shows the OCR options in the five steps, in order, and keeps the other parameters outside the panel", async () => {
    setup(undefined);
    await screen.findAllByRole("radio", { name: "Inherit from Settings: On (default)" });
    expect(stepHeadings().map((heading) => heading.textContent)).toEqual(["1 PDF readers", "2 Pages decided by their content", "3 Pages that look fine", "4 Local OCR backends", "5 OCR engines"]);
    expect(legendsIn(step(1))).toEqual(["PDF readers"]);
    expect(legendsIn(step(2))).toEqual(["Skip blank pages", "Maths page routing", "Non-Latin routing"]);
    expect(legendsIn(step(3))).toEqual(["Router"]);
    expect(legendsIn(step(4))).toEqual(["Local OCR backends", "Confidence cuts"]);
    expect(legendsIn(step(5))).toEqual(["OCR engines"]);
    // The two rows above step 1 come first in the panel.
    const top = within(panel()).getAllByRole("group").filter((row) => !step(1).contains(row) && !step(2).contains(row) && !step(3).contains(row) && !step(4).contains(row) && !step(5).contains(row));
    expect(top.map((row) => row.querySelector(":scope > legend")?.textContent)).toEqual(["OCR fallback", "OCR routing unit"]);
    // The generic list of step options skips every panel option, so each shows once on the page.
    for (const name of ["OCR fallback", "OCR routing unit", "PDF readers", "Skip blank pages", "Maths page routing", "Non-Latin routing", "Router", "Local OCR backends", "Confidence cuts", "OCR engines"]) {
      expect(screen.getAllByRole("group", { name })).toHaveLength(1);
    }
    for (const outside of ["Fallback chunking", "Lines per code chunk"]) {
      const row = screen.getByRole("group", { name: outside });
      expect(panel().contains(row)).toBe(false);
    }
  });

  it("says in the panel that Inherit uses the Settings value and that a value set here applies to this pipeline only", () => {
    setup(undefined);
    expect(within(panel()).getByText("Inherit uses the value from Settings › Document reading. A value set here applies to this pipeline only.")).toBeInTheDocument();
  });

  it("names the Settings value and its source in each Inherit choice", async () => {
    setup(undefined, { rows: { ocr_skip_blank_pages: { value: false, source: "config-file" }, ocr_maths_routing_enabled: { value: true, source: "env" }, ocr_fallback_enabled: { value: true, source: "dotenv" } } });
    expect(await within(group("Skip blank pages")).findByRole("radio", { name: "Inherit from Settings: Off (omrs.jsonc)" })).toBeChecked();
    expect(within(group("Maths page routing")).getByRole("radio", { name: "Inherit from Settings: On (environment)" })).toBeInTheDocument();
    expect(within(group("OCR fallback")).getByRole("radio", { name: "Inherit from Settings: On (.env)" })).toBeInTheDocument();
    expect(within(group("PDF readers")).getByRole("radio", { name: "Inherit from Settings: pdf_inspector, liteparse, pypdf (default)" })).toBeInTheDocument();
    expect(within(group("OCR engines")).getByRole("radio", { name: "Inherit from Settings: dots-mocr, paddleocr-vl (default)" })).toBeInTheDocument();
    expect(within(group("Local OCR backends")).getByRole("radio", { name: "Inherit from Settings: pp-ocrv6-small (default)" })).toBeInTheDocument();
    // The Inherit choice already names the value, so the old "Inherit uses the host value" line would say it twice.
    expect(within(panel()).queryByText(/Inherit uses the host value/)).toBeNull();
  });

  it("names the Settings value in the first choice of the select rows", async () => {
    const { user } = setup(undefined, { rows: { ocr_non_latin_routing: { value: "detect", source: "config-file" } } });
    await user.click(await within(group("Non-Latin routing")).findByRole("combobox", { name: "Non-Latin routing value" }));
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual(["Inherit from Settings: detect (omrs.jsonc)", "off", "detect", "always"]);
  });

  it("carries the word default in no choice except the source of an Inherit choice", async () => {
    // Every row holds a saved value, so no Inherit choice names the source "default" either.
    const saved = { source: "config-file" as const };
    const rows: Rows = { ocr_fallback_enabled: saved, ocr_routing_unit: saved, pdf_readers: saved, ocr_engines: saved, ocr_skip_blank_pages: saved, ocr_maths_routing_enabled: saved, ocr_non_latin_routing: saved, document_router: saved, ocr_local_backends: saved };
    const { user } = setup(undefined, { rows, routers: ["handwriting"] });
    await within(group("Skip blank pages")).findByRole("radio", { name: "Inherit from Settings: On (omrs.jsonc)" });
    for (const radio of within(panel()).getAllByRole("radio")) expect(radio.closest("label")?.textContent).not.toMatch(/default/i);
    for (const name of ["OCR routing unit value", "Non-Latin routing value", "Router value"]) {
      await user.click(within(panel()).getByRole("combobox", { name }));
      for (const option of await screen.findAllByRole("option")) expect(option.textContent).not.toMatch(/default/i);
      await user.keyboard("{Escape}");
    }
  });

  it("sets ocr_skip_blank_pages to false on the node when Off is chosen, and clears it on Inherit", async () => {
    const { seen, user } = setup(undefined);
    await within(group("Skip blank pages")).findByRole("radio", { name: "Inherit from Settings: On (default)" });
    await user.click(within(group("Skip blank pages")).getByRole("radio", { name: "Off" }));
    expect(params(seen)).toEqual({ ocr_skip_blank_pages: false });
    await user.click(within(group("Skip blank pages")).getByRole("radio", { name: "Inherit from Settings: On (default)" }));
    expect(seen.draft.graph.nodes[0]).not.toHaveProperty("params.ocr_skip_blank_pages");
  });

  it("shows the same help line as the Settings row", async () => {
    setup(undefined);
    expect(await within(group("Skip blank pages")).findByText(/On: a flagged page with no ink keeps its native text and costs no OCR/)).toBeInTheDocument();
  });

  it("offers Inherit with the host router, No router (saved as none) and the router names", async () => {
    const { seen, user } = setup(undefined, { routers: ["handwriting", "forms"], rows: { document_router: { value: "forms", source: "config-file" } } });
    const select = await within(group("Router")).findByRole("combobox", { name: "Router value" });
    await user.click(select);
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual(["Inherit from Settings: forms", "No router", "handwriting", "forms"]);
    await user.click(screen.getByRole("option", { name: "No router" }));
    expect(params(seen)).toEqual({ document_router: "none" });
    await user.click(select);
    await user.click(await screen.findByRole("option", { name: "handwriting" }));
    expect(params(seen)).toEqual({ document_router: "handwriting" });
    await user.click(select);
    await user.click(await screen.findByRole("option", { name: "Inherit from Settings: forms" }));
    expect(seen.draft.graph.nodes[0]).not.toHaveProperty("params.document_router");
  });

  it("reads Inherit from Settings: No router when the host holds no router", async () => {
    const { user } = setup(undefined);
    await user.click(await within(group("Router")).findByRole("combobox", { name: "Router value" }));
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual(["Inherit from Settings: No router", "No router"]);
  });

  it("shows the confidence cuts of the local backends in step 4", async () => {
    setup(undefined);
    expect(await within(step(4)).findByRole("spinbutton", { name: "Confidence cut for pp-ocrv6-small" })).toBeInTheDocument();
    expect(within(step(4)).getByRole("group", { name: "Confidence cuts" })).toBeInTheDocument();
  });

  it("hides the old single-value options while the step does not set them", async () => {
    setup(undefined);
    await within(group("Skip blank pages")).findByRole("radio", { name: "Inherit from Settings: On (default)" });
    for (const name of ["PDF reader", "Primary OCR engine", "Fallback OCR engine"]) expect(screen.queryByRole("group", { name })).toBeNull();
  });

  it("shows an old single-value option in the step of its list when the step sets it", () => {
    setup({ pdf_reader: "liteparse", ocr_engine_primary: "dots-mocr" });
    expect(within(step(1)).getByRole("group", { name: "PDF reader" })).toBeInTheDocument();
    expect(within(step(5)).getByRole("group", { name: "Primary OCR engine" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Fallback OCR engine" })).toBeNull();
  });

  it("turns the OCR-off line on when the step sets OCR fallback off", async () => {
    setup({ ocr_fallback_enabled: false });
    expect(await screen.findByText(/OCR fallback is off/)).toBeInTheDocument();
  });

  it("turns the OCR-off line on when Settings holds OCR fallback off and the step inherits", async () => {
    setup(undefined, { rows: { ocr_fallback_enabled: { value: false } } });
    expect(await screen.findByText(/OCR fallback is off/)).toBeInTheDocument();
  });

  it("makes every control read-only on a built-in profile", async () => {
    setup({ pdf_readers: ["pypdf"], ocr_local_backends: ["pp-ocrv6-small"], ocr_engines: ["dots-mocr"], ocr_local_cuts: { "pp-ocrv6-small": 0.9 } }, { readOnly: true, routers: ["handwriting"] });
    await within(group("Skip blank pages")).findByRole("radio", { name: "Inherit from Settings: On (default)" });
    const controls = [...within(panel()).queryAllByRole("radio"), ...within(panel()).queryAllByRole("combobox"), ...within(panel()).queryAllByRole("button")];
    expect(controls.length).toBeGreaterThan(10);
    for (const control of controls) expect(control).toBeDisabled();
    const cut = await within(step(4)).findByRole("spinbutton", { name: "Confidence cut for pp-ocrv6-small" });
    expect(cut).toHaveAttribute("readonly");
  });

  it("shows a reader that is not installed as disabled, with a link to Settings and no Install button", async () => {
    const { user } = setup({ pdf_readers: ["pypdf"] });
    await user.click(await within(step(1)).findByRole("combobox", { name: "Add reader" }));
    expect(await screen.findByRole("option", { name: "pypdfium2 (optional, not installed)" })).toHaveAttribute("aria-disabled", "true");
    await user.keyboard("{Escape}");
    const link = within(step(1)).getByRole("link", { name: /Settings › Document reading/ });
    expect(link).toHaveAttribute("href", "#/settings/document-reading");
    expect(screen.queryByRole("button", { name: /install/i })).toBeNull();
  });
});
