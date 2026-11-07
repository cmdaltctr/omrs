/**
 * The words and the key order of the Page routing panel (change
 * page-routing-panel, design D1, D2, D6 and D8). Row labels and help lines
 * stay in `settings/documentReadingWords.ts`. `tests/unit/test_reading_parts_drift.py`
 * reads `PANEL_STEPS` and `OPTIONAL_READERS` as text, so keep each a plain array.
 */

export interface PanelStep {
  title: string;
  /** One or two plain lines on what the step does to a page. */
  intro: string;
  /** The setting keys of the step's rows, in the order they show. */
  keys: readonly string[];
}

/** The rows above step 1: they describe the whole flow, not one step. */
export const TOP_KEYS = ["ocr_fallback_enabled", "ocr_routing_unit"] as const;

/** The five steps in the order a page meets them. Step 2 follows the page rule order, which cannot change. */
export const PANEL_STEPS = [
  {
    title: "PDF readers",
    intro:
      "A reader takes the text of each PDF. A page scan then flags the pages that need OCR. pypdfium2 is optional. OMRS also uses it to draw page images for the router and the dots-mocr engine; that is not a reading step.",
    keys: ["pdf_readers"],
  },
  {
    title: "Pages with no usable text",
    intro: "These rules decide what happens to each flagged page before local OCR.",
    keys: ["ocr_skip_blank_pages", "ocr_maths_routing_enabled", "ocr_non_latin_routing"],
  },
  {
    title: "Pages that look fine",
    intro: "A router can check the pages that were not flagged. A page it rejects goes to the OCR engines.",
    keys: ["document_router"],
  },
  {
    title: "Local OCR backends",
    intro: "Local models read the flagged pages that no rule sent on. A page below every cut goes to the OCR engines.",
    keys: ["ocr_local_backends"],
  },
  {
    title: "OCR engines",
    intro: "The engines read every page sent to them.",
    keys: ["ocr_engines"],
  },
] as const satisfies readonly PanelStep[];

/** A key the panel asks its renderer to show. */
export type PanelKey = (typeof TOP_KEYS)[number] | (typeof PANEL_STEPS)[number]["keys"][number];

/** PDF readers that need an optional extra. The reader options carry no `extra` field, so this list says which are optional. */
export const OPTIONAL_READERS = ["pypdfium2"] as const;

export const PAGE_ROUTING_WORDS = {
  title: "Page routing",
  fixedOrder: "These checks run in a fixed order. Blank pages are checked first.",
  ocrOff: "OCR fallback is off. No page goes to OCR, so steps 2 to 5 have no effect.",
} as const;
