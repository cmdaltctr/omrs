import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { PageRoutingPanel } from "./PageRoutingPanel";
import type { PanelKey } from "./pageRoutingWords";

// The expected flow is typed out here, not read from PANEL_STEPS, so a change to the step order fails these tests.
const STEP_HEADINGS = ["1 PDF readers", "2 Pages decided by their content", "3 Pages that look fine", "4 Local OCR backends", "5 OCR engines"];
const STEP_KEYS: readonly (readonly string[])[] = [
  ["pdf_readers"],
  ["ocr_skip_blank_pages", "ocr_maths_routing_enabled", "ocr_non_latin_routing"],
  ["document_router"],
  ["ocr_local_backends"],
  ["ocr_engines"],
];
const TOP_KEYS = ["ocr_fallback_enabled", "ocr_routing_unit"];
const FIXED_ORDER = "These checks run in a fixed order. Blank pages are checked first.";
const OCR_OFF = "OCR fallback is off. No page goes to OCR, so steps 2 to 5 have no effect.";
const PYPDFIUM2 = "pypdfium2 is optional. OMRS also uses it to draw page images for the router and the dots-mocr engine; that is not a reading step.";

interface Options {
  ocrFallbackEnabled?: boolean;
  renderExtra?: (step: number) => ReactNode;
  description?: string;
}

/** Renders the panel with stub rows and returns the keys in the order the panel asked for them. */
function renderPanel({ ocrFallbackEnabled = true, renderExtra, description }: Options = {}) {
  const asked: PanelKey[] = [];
  render(
    <PageRoutingPanel
      ocrFallbackEnabled={ocrFallbackEnabled}
      renderRow={(key) => {
        asked.push(key);
        return <p data-testid={`row-${key}`}>{key}</p>;
      }}
      renderCuts={() => <p data-testid="cuts">cut boxes</p>}
      renderExtra={renderExtra}
      description={description}
    />,
  );
  return asked;
}

const stepHeadings = () => screen.getAllByRole("heading", { level: 4 });
const heading = (number: number) => stepHeadings()[number - 1]!;
const step = (number: number) => heading(number).closest<HTMLElement>("[data-slot='page-routing-step']")!;
const rowsIn = (element: HTMLElement) => within(element).queryAllByTestId(/^row-/).map((row) => row.textContent);
const precedes = (a: Node, b: Node) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;

describe("PageRoutingPanel", () => {
  it("shows one Page routing card with the five steps in flow order, numbered 1 to 5", () => {
    renderPanel();
    expect(screen.getByRole("region", { name: "Page routing" })).toBeInTheDocument();
    expect(stepHeadings().map((heading) => heading.textContent)).toEqual(STEP_HEADINGS);
  });

  it("shows the OCR fallback and routing unit rows above step 1", () => {
    renderPanel();
    const fallback = screen.getByTestId("row-ocr_fallback_enabled");
    const unit = screen.getByTestId("row-ocr_routing_unit");
    expect(precedes(fallback, unit)).toBe(true);
    expect(precedes(unit, heading(1))).toBe(true);
    expect(step(1).contains(fallback)).toBe(false);
  });

  it("asks for each row once, in flow order, and puts each row in its step", () => {
    const asked = renderPanel();
    expect(asked).toEqual([...TOP_KEYS, ...STEP_KEYS.flat()]);
    STEP_KEYS.forEach((keys, index) => expect(rowsIn(step(index + 1))).toEqual(keys));
  });

  it("puts the cut boxes in step 4 after the local backends list", () => {
    renderPanel();
    const cuts = within(step(4)).getByTestId("cuts");
    expect(precedes(within(step(4)).getByTestId("row-ocr_local_backends"), cuts)).toBe(true);
  });

  it("shows the fixed-order line in step 2 only, with no move buttons", () => {
    renderPanel();
    expect(within(step(2)).getByText(FIXED_ORDER)).toBeInTheDocument();
    expect(screen.getAllByText(FIXED_ORDER)).toHaveLength(1);
    expect(within(step(2)).queryAllByRole("button")).toHaveLength(0);
  });

  it("says in step 1 that pypdfium2 is optional and also draws page images", () => {
    renderPanel();
    expect(within(step(1)).getByText(PYPDFIUM2, { exact: false })).toBeInTheDocument();
  });

  it("says above step 2 that OCR is off, and keeps every row", () => {
    renderPanel({ ocrFallbackEnabled: false });
    const line = screen.getByText(OCR_OFF);
    expect(precedes(heading(1), line)).toBe(true);
    expect(precedes(line, heading(2))).toBe(true);
    for (const key of [...TOP_KEYS, ...STEP_KEYS.flat()]) expect(screen.getByTestId(`row-${key}`)).toBeInTheDocument();
    expect(screen.getByTestId("cuts")).toBeInTheDocument();
  });

  it("shows no OCR-off line while OCR fallback is on", () => {
    renderPanel({ ocrFallbackEnabled: true });
    expect(screen.queryByText(OCR_OFF)).not.toBeInTheDocument();
  });

  it("renders each step's extra content inside that step, after its rows", () => {
    renderPanel({ renderExtra: (number) => (number === 1 || number === 5 ? <p data-testid={`extra-${number}`}>extra {number}</p> : null) });
    expect(precedes(within(step(1)).getByTestId("row-pdf_readers"), within(step(1)).getByTestId("extra-1"))).toBe(true);
    expect(precedes(within(step(5)).getByTestId("row-ocr_engines"), within(step(5)).getByTestId("extra-5"))).toBe(true);
    expect(screen.queryAllByTestId(/^extra-/)).toHaveLength(2);
  });

  it("shows the description line under the title, above step 1, and none without one", () => {
    renderPanel({ description: "A line for the host." });
    const line = screen.getByText("A line for the host.");
    expect(precedes(screen.getByText("Page routing"), line)).toBe(true);
    expect(precedes(line, screen.getByTestId("row-ocr_fallback_enabled"))).toBe(true);
  });

  it("shows no description line when none is given", () => {
    renderPanel();
    expect(document.querySelector("[data-slot='card-description']")).toBeNull();
  });

  it("has no Learn more link and no link to the page routing guide", () => {
    renderPanel();
    expect(screen.queryByText(/learn more/i)).not.toBeInTheDocument();
    for (const link of screen.queryAllByRole("link")) expect(link.getAttribute("href") ?? "").not.toContain("page-routing");
    expect(document.body.innerHTML).not.toContain("docs/guides/page-routing.md");
  });
});
