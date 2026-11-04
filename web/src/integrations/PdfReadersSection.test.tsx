import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { PdfReaderItem } from "../api/integrations";
import { documentsServer } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { attentionCount, sectionsFor } from "./sections";

function reader(name: string, extra: Partial<PdfReaderItem> = {}): PdfReaderItem {
  return { name, installed: true, extra: null, fix_command: null, used_by: [], ...extra };
}

const READERS: PdfReaderItem[] = [
  reader("pdf_inspector", { extra: "pdf-inspector", used_by: ["First in Settings > Document reading"] }),
  reader("liteparse", { installed: false, extra: "liteparse", fix_command: "uv sync --extra liteparse", used_by: ["Second in Settings > Document reading"] }),
  reader("pypdfium2", { installed: false, extra: "pdf-pypdfium2", fix_command: "uv sync --extra pdf-pypdfium2" }),
  reader("pypdf", { fix_command: null, used_by: ["Third in Settings > Document reading", "Profile Papers"] }),
];

function serve(pdfReaders: PdfReaderItem[] = READERS) {
  return documentsServer({
    "GET /v1/integrations": () => ({ status: "ok", install_type: "checkout", integrations: [], tools: [], pdf_readers: pdfReaders }),
  });
}

const group = async () => screen.findByRole("region", { name: "PDF readers" });
const row = async (name: string) => {
  const items = within(await group()).getAllByRole("listitem");
  const found = items.find((entry) => within(entry).queryByRole("heading", { name }) !== null);
  if (found === undefined) throw new Error(`No row ${name}`);
  return found;
};

describe("Integrations PDF readers", () => {
  it("tells where to change the reader list, with a link to Document reading", async () => {
    startApp("#/integrations/pdf-readers", serve());
    const note = within(await group())
      .getAllByRole("note")
      .find((element) => /change which readers are used/i.test(element.textContent ?? ""));
    if (note === undefined) throw new Error("no Document reading note");
    expect(note).toHaveTextContent("To change which readers are used and in what order, go to Settings › Document reading.");
    expect(within(note).getByRole("link", { name: "Settings › Document reading" })).toHaveAttribute("href", "#/settings/document-reading");
  });

  it("shows one row for each reader in server order, built on the shared entry list", async () => {
    startApp("#/integrations/pdf-readers", serve());
    const list = within(await group()).getByRole("list", { name: "PDF readers" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows.map((entry) => within(entry).getByRole("heading").textContent)).toEqual(["pdf_inspector", "liteparse", "pypdfium2", "pypdf"]);
    for (const entry of rows) expect(entry).toHaveAttribute("data-slot", "entry-row");
  });

  it("says Installed or Not installed on each row", async () => {
    startApp("#/integrations/pdf-readers", serve());
    expect(within(await row("pdf_inspector")).getByText("Installed", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(within(await row("pypdfium2")).getByText("Not installed", { selector: "[data-slot=badge]" })).toBeInTheDocument();
  });

  it("shows where a reader is used, and says so when nothing uses it", async () => {
    startApp("#/integrations/pdf-readers", serve());
    expect(await row("pdf_inspector")).toHaveTextContent("First in Settings > Document reading");
    const pypdf = await row("pypdf");
    expect(pypdf).toHaveTextContent("Third in Settings > Document reading");
    expect(pypdf).toHaveTextContent("Profile Papers");
    expect(await row("pypdfium2")).toHaveTextContent("Nothing uses it.");
  });

  it("gives a missing reader a copy command and an installed reader none", async () => {
    startApp("#/integrations/pdf-readers", serve());
    const missing = await row("pypdfium2");
    expect(within(missing).getByText("uv sync --extra pdf-pypdfium2")).toBeInTheDocument();
    expect(within(missing).getByRole("button", { name: "Copy install command for pypdfium2" })).toBeInTheDocument();
    expect(within(await row("pdf_inspector")).queryByRole("button")).toBeNull();
  });

  it("shows a missing reader that is in use in the error colour, and an unused one without it", async () => {
    startApp("#/integrations/pdf-readers", serve());
    expect(within(await row("liteparse")).getByText("Not installed", { selector: "[data-slot=badge]" })).toHaveClass("text-status-error-label");
    expect(within(await row("pypdfium2")).getByText("Not installed", { selector: "[data-slot=badge]" })).not.toHaveClass("text-status-error-label");
  });

  it("shows a reader that a later release registers, with no page change", async () => {
    startApp("#/integrations/pdf-readers", serve([...READERS, reader("docling", { installed: false, extra: "docling", fix_command: "uv sync --extra docling" })]));
    const added = await row("docling");
    expect(added).toHaveTextContent("Not installed");
    expect(within(added).getByText("uv sync --extra docling")).toBeInTheDocument();
  });

  it("puts a chip for the section in the chip row with the count of readers in use and missing", async () => {
    startApp("#/integrations/pdf-readers", serve());
    expect(await screen.findByRole("button", { name: "PDF readers, 1 needs attention" })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("PDF readers section rules", () => {
  const list = (pdfReaders?: PdfReaderItem[]) => ({ install_type: "checkout" as const, integrations: [], tools: [], ...(pdfReaders ? { pdf_readers: pdfReaders } : {}) });

  it("lists the section only when the server reports readers", () => {
    expect(sectionsFor(list(READERS))).toContain("pdf-readers");
    expect(sectionsFor(list([]))).not.toContain("pdf-readers");
    expect(sectionsFor(list())).not.toContain("pdf-readers");
    expect(sectionsFor(undefined)).not.toContain("pdf-readers");
  });

  it("counts a reader that is in use and missing, and no other", () => {
    expect(attentionCount("pdf-readers", list(READERS))).toBe(1);
    expect(attentionCount("pdf-readers", list([reader("pypdfium2", { installed: false })]))).toBe(0);
    expect(attentionCount("pdf-readers", list([reader("pypdf", { used_by: ["x"] })]))).toBe(0);
    expect(attentionCount("pdf-readers", undefined)).toBe(0);
  });
});
