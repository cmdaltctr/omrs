import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DocumentReadingState } from "../api/settingsDocumentReading";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { readingState, settingsServer } from "./test/fixtures";
import { IDLE_INSTALL, integrationsBody, PYPDFIUM2_CHECKOUT, PYPDFIUM2_ENTRY, PYPDFIUM2_RESTART, RUNNING_INSTALL, SUCCEEDED_INSTALL } from "./test/pdfReaderFixtures";
import { documentRouters, HANDWRITING } from "./test/routerFixtures";

const SKIP_BLANK_HELP = "On: a flagged page with no ink keeps its native text and costs no OCR. Off: blank pages go to OCR like any flagged page.";
const OCR_OFF = "OCR fallback is off. No page goes to OCR, so steps 2 to 5 have no effect.";

async function openPanel(handlers = {}) {
  const server = settingsServer(handlers);
  startApp("#/settings/document-reading", server);
  const panel = await screen.findByRole("region", { name: "Page routing" });
  await within(panel).findByRole("group", { name: "PDF readers" });
  return { server, panel, user: userEvent.setup() };
}

/** The step with this number, found by its heading. */
function step(number: number): HTMLElement {
  const heading = screen.getAllByRole("heading", { level: 4 })[number - 1]!;
  return heading.closest<HTMLElement>("[data-slot='page-routing-step']")!;
}

const rowsOf = (element: HTMLElement) => within(element).getAllByRole("group").map((group) => group.getAttribute("aria-label"));
const row = (name: string) => screen.getByRole("group", { name });
const puts = (server: Awaited<ReturnType<typeof openPanel>>["server"]) => server.find("PUT", "/v1/settings/document-reading").map((call) => call.body);

/** A fake server that holds the state and applies each PUT, as the real route does. */
function savingServer(start: DocumentReadingState) {
  let state = start;
  return {
    "GET /v1/settings/document-reading": () => state,
    "PUT /v1/settings/document-reading": (body: Record<string, unknown>) => {
      const values = body.values as Record<string, unknown>;
      state = {
        ...state,
        revision: "r2",
        settings: state.settings.map((setting) => {
          if (!(setting.key in values)) return setting;
          const saved = values[setting.key] as DocumentReadingState["settings"][number]["saved"];
          return { ...setting, saved, restart_pending: saved !== null && saved !== setting.value };
        }),
      };
      return state;
    },
  };
}

const TWO_BACKENDS = readingState(
  { ocr_local_backends: { value: ["pp-ocrv6-small", "indra"], default: ["pp-ocrv6-small"] } },
  {
    local_ocr_backends: [
      { name: "pp-ocrv6-small", available: true, reason: null, default_cut: 0.92 },
      { name: "indra", available: true, reason: null, default_cut: 0.94 },
    ],
  },
);

describe("Document reading: Page routing panel", () => {
  it("shows one Page routing card and no PDF reading card, OCR card or old block", async () => {
    await openPanel();
    const section = screen.getByRole("region", { name: "Document reading" });
    for (const name of ["PDF reading", "OCR"]) expect(within(section).queryByRole("region", { name })).toBeNull();
    for (const name of ["When to use OCR", "Maths pages", "Local OCR", "Engines"]) {
      expect(within(section).queryByRole("group", { name })).toBeNull();
      expect(within(section).queryByRole("heading", { name })).toBeNull();
    }
    expect(screen.getAllByRole("heading", { level: 4 }).map((heading) => heading.textContent)).toEqual([
      "1 PDF readers",
      "2 Pages with no usable text",
      "3 Pages that look fine",
      "4 Local OCR backends",
      "5 OCR engines",
    ]);
  });

  it("puts each key's row in its step, in flow order", async () => {
    const { panel } = await openPanel();
    expect(rowsOf(panel)).toEqual(["OCR fallback", "OCR routing unit", "PDF readers", "Skip blank pages", "Maths routing", "Non-Latin routing", "Host router", "Local OCR backends", "OCR engines"]);
    expect(rowsOf(step(1))).toEqual(["PDF readers"]);
    expect(rowsOf(step(2))).toEqual(["Skip blank pages", "Maths routing", "Non-Latin routing"]);
    expect(rowsOf(step(3))).toEqual(["Host router"]);
    expect(rowsOf(step(4))).toEqual(["Local OCR backends"]);
    expect(rowsOf(step(5))).toEqual(["OCR engines"]);
  });

  it("shows Skip blank pages as On with its help line, source and default", async () => {
    await openPanel();
    const blank = row("Skip blank pages");
    expect(within(blank).getByText("On", { selector: "code" })).toBeInTheDocument();
    expect(blank).toHaveTextContent(SKIP_BLANK_HELP);
    expect(blank).toHaveTextContent("default");
    expect(blank).toHaveTextContent("Default: On");
  });

  it("saves Skip blank pages Off as false and shows Restart to apply", async () => {
    const { user, server } = await openPanel(savingServer(readingState()));
    await user.click(within(row("Skip blank pages")).getByRole("button", { name: "Edit Skip blank pages" }));
    await user.click(within(row("Skip blank pages")).getByRole("switch", { name: "Skip blank pages" }));
    await user.click(within(row("Skip blank pages")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(puts(server)).toEqual([{ values: { ocr_skip_blank_pages: false }, revision: "r1" }]));
    const dialog = await screen.findByRole("dialog", { name: "Restart to apply?" });
    expect(dialog).toHaveTextContent("Skip blank pages applies after a restart.");
    await user.click(within(dialog).getByRole("button", { name: "Later" }));
    expect(within(row("Skip blank pages")).getByText("Restart to apply")).toBeInTheDocument();
  });

  it("makes Skip blank pages read-only and names OCR_SKIP_BLANK_PAGES when the environment sets it", async () => {
    const lock = "Remove OCR_SKIP_BLANK_PAGES from the environment or .env to edit it here.";
    await openPanel({
      "GET /v1/settings/document-reading": () => readingState({ ocr_skip_blank_pages: { value: false, source: "env", locked: true, lock_reason: lock } }),
    });
    const blank = row("Skip blank pages");
    expect(within(blank).queryByRole("button", { name: /Edit/ })).toBeNull();
    expect(blank).toHaveTextContent(lock);
    expect(within(blank).getByText("Off", { selector: "code" })).toBeInTheDocument();
  });

  it("offers off (default), detect and always for Non-Latin routing", async () => {
    const { user } = await openPanel();
    await user.click(within(row("Non-Latin routing")).getByRole("button", { name: "Edit Non-Latin routing" }));
    await user.click(within(row("Non-Latin routing")).getByRole("combobox", { name: "Non-Latin routing" }));
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual(["off (default)", "detect", "always"]);
  });

  it("shows no move button for the page rules and says they run in a fixed order", async () => {
    await openPanel();
    expect(within(step(2)).queryByRole("button", { name: /Move/ })).toBeNull();
    expect(step(2)).toHaveTextContent("These checks run in a fixed order. Blank pages are checked first.");
  });

  it("says OCR is off above step 2 and keeps every row editable", async () => {
    await openPanel({ "GET /v1/settings/document-reading": () => readingState({ ocr_fallback_enabled: { value: false, default: true } }) });
    expect(screen.getByRole("note")).toHaveTextContent(OCR_OFF);
    for (const name of ["Skip blank pages", "Maths routing", "Non-Latin routing"]) expect(within(row(name)).getByRole("button", { name: `Edit ${name}` })).toBeInTheDocument();
  });

  it("holds the host router choice in step 3, with a link to the Router section that scrolls to it", async () => {
    const scroll = vi.spyOn(Element.prototype, "scrollIntoView");
    const { user } = await openPanel({ "GET /v1/settings/document-routers": () => documentRouters([HANDWRITING]) });
    expect(within(step(3)).getByText("No router", { selector: "code" })).toBeInTheDocument();
    const link = within(step(3)).getByRole("link", { name: "Define routers in the Router section" });
    await user.click(link);
    expect(scroll).toHaveBeenCalledTimes(1);
    expect(scroll.mock.contexts[0]).toHaveAttribute("id", "reading-router");
    expect(window.location.hash).toBe("#/settings/document-reading");
    await user.click(within(row("Host router")).getByRole("button", { name: "Edit Host router" }));
    await user.click(within(row("Host router")).getByRole("combobox", { name: "Host router" }));
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual(["No router", "handwriting"]);
  });

  it("keeps the named routers in the Router card and gives it no host row", async () => {
    await openPanel({ "GET /v1/settings/document-routers": () => documentRouters([HANDWRITING]) });
    const card = screen.getByRole("region", { name: "Router" });
    expect(await within(card).findByRole("listitem", { name: "handwriting" })).toBeInTheDocument();
    expect(within(card).queryByRole("group", { name: "Host router" })).toBeNull();
    expect(within(card).queryByRole("button", { name: "Edit Host router" })).toBeNull();
  });

  it("shows a confidence cut box for each listed local OCR backend in step 4", async () => {
    await openPanel({ "GET /v1/settings/document-reading": () => TWO_BACKENDS });
    const backends = step(4);
    for (const name of ["pp-ocrv6-small", "indra"]) expect(within(backends).getByRole("spinbutton", { name: `Confidence cut for ${name}` })).toBeInTheDocument();
    expect(within(backends).getAllByRole("spinbutton")).toHaveLength(2);
  });

  it("shows the OCR engines folder in step 5, or says no engine can run without it", async () => {
    await openPanel();
    expect(step(5)).toHaveTextContent("OCR engines folder: ~/ocr-workers");
  });

  it("says OCR_WORKERS_DIR is not set when there is no engines folder", async () => {
    await openPanel({ "GET /v1/settings/document-reading": () => readingState({}, { ocr: { ...readingState().ocr, workers_dir: null } }) });
    expect(step(5)).toHaveTextContent("OCR_WORKERS_DIR is not set, so no OCR engine can run.");
  });
});

describe("Document reading: optional pypdfium2 reader", () => {
  const OPTION = "pypdfium2 (optional, not installed)";

  /** Opens the panel and the PDF readers editor. The add choice stays closed, because an open choice hides the rest of the page from the queries. */
  async function editReaders(handlers = {}) {
    const opened = await openPanel(handlers);
    await opened.user.click(within(row("PDF readers")).getByRole("button", { name: "Edit PDF readers" }));
    return opened;
  }

  const openChoice = (user: ReturnType<typeof userEvent.setup>) => user.click(within(row("PDF readers")).getByRole("combobox", { name: "Add reader" }));

  it("offers pypdfium2 as optional and not installed, disabled, with an Integrations link and an Install button", async () => {
    const { user } = await editReaders();
    expect(within(row("PDF readers")).getByRole("link", { name: "See PDF readers in Integrations" })).toHaveAttribute("href", "#/integrations/pdf-readers");
    expect(await within(step(1)).findByRole("button", { name: "Install PDF reader: pypdfium2" })).toBeEnabled();
    expect(step(1)).toHaveTextContent("pypdfium2 is optional. OMRS also uses it to draw page images for the router and the dots-mocr engine; that is not a reading step.");
    await openChoice(user);
    expect(await screen.findByRole("option", { name: OPTION })).toHaveAttribute("aria-disabled", "true");
  });

  it("lets the user add pypdfium2 when it is installed, and marks it optional", async () => {
    const readers = readingState().pdf_readers.map((reader) => (reader.name === "pypdfium2" ? { ...reader, available: true, reason: null } : reader));
    const { server, user } = await editReaders({
      ...savingServer(readingState({ pdf_readers: { value: ["pdf_inspector"] } }, { pdf_readers: readers })),
      "GET /v1/integrations": () => integrationsBody({ ...PYPDFIUM2_ENTRY, availability: "available", installable: false, install_reason: "already-installed" }),
    });
    expect(within(step(1)).queryByRole("button", { name: /^Install/ })).toBeNull();
    expect(within(step(1)).queryByRole("button", { name: /^Copy install command/ })).toBeNull();
    expect(step(1)).not.toHaveTextContent("Restart the server to use it");
    await openChoice(user);
    expect(await screen.findByRole("option", { name: "pypdfium2 (optional)" })).not.toHaveAttribute("aria-disabled", "true");
    await user.click(screen.getByRole("option", { name: "pypdfium2 (optional)" }));
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(puts(server)).toEqual([{ values: { pdf_readers: ["pdf_inspector", "pypdfium2"] }, revision: "r1" }]));
  });

  it("posts the install for the extra of the reader and shows the running state", async () => {
    let install = IDLE_INSTALL;
    const { server, user } = await openPanel({
      "GET /v1/integrations/install": () => ({ status: "ok", install }),
      "POST /v1/integrations/:extra/install": () => {
        install = RUNNING_INSTALL;
        return json({ status: "ok", install }, 202);
      },
    });
    await user.click(await within(step(1)).findByRole("button", { name: "Install PDF reader: pypdfium2" }));
    const dialog = await screen.findByRole("dialog", { name: "Install PDF reader: pypdfium2?" });
    expect(dialog).toHaveTextContent("pdf-pypdfium2");
    await user.click(within(dialog).getByRole("button", { name: "Install" }));
    await waitFor(() => expect(server.find("POST", "/v1/integrations/pdf-pypdfium2/install")).toHaveLength(1));
    expect(await within(step(1)).findByRole("status")).toHaveTextContent("Installing pdf-pypdfium2.");
    expect(within(step(1)).queryByRole("button", { name: /^Install/ })).toBeNull();
  });

  it("says Installed, restart OMRS to use it, and keeps the choice disabled while the readers block still says not installed", async () => {
    const { user } = await editReaders({
      "GET /v1/integrations": () => integrationsBody(PYPDFIUM2_RESTART),
      "GET /v1/integrations/install": () => ({ status: "ok", install: SUCCEEDED_INSTALL }),
    });
    expect(await within(step(1)).findByText("Restart to apply")).toBeInTheDocument();
    expect(step(1)).toHaveTextContent("Installed. Restart OMRS to use it.");
    expect(within(step(1)).queryByRole("button", { name: /^Install/ })).toBeNull();
    await openChoice(user);
    expect(await screen.findByRole("option", { name: OPTION })).toHaveAttribute("aria-disabled", "true");
  });

  it("shows Restart to apply and lets the user add the reader once the readers block reports it installed", async () => {
    const readers = readingState().pdf_readers.map((reader) => (reader.name === "pypdfium2" ? { ...reader, available: true, reason: null } : reader));
    const { user } = await editReaders({
      ...savingServer(readingState({}, { pdf_readers: readers })),
      "GET /v1/integrations": () => integrationsBody(PYPDFIUM2_RESTART),
      "GET /v1/integrations/install": () => ({ status: "ok", install: SUCCEEDED_INSTALL }),
    });
    expect(await within(step(1)).findByText("Restart to apply")).toBeInTheDocument();
    expect(step(1)).not.toHaveTextContent("Installed. Restart OMRS to use it.");
    await openChoice(user);
    expect(await screen.findByRole("option", { name: "pypdfium2 (optional)" })).not.toHaveAttribute("aria-disabled", "true");
  });

  it("shows the reason and a copy command, and no Install button, when the extra cannot be installed here", async () => {
    await openPanel({ "GET /v1/integrations": () => integrationsBody(PYPDFIUM2_CHECKOUT, "checkout") });
    const reason = await within(step(1)).findByText("This server was not installed with uv tool, so it cannot install from the app. Run the command instead.");
    expect(reason).toBeInTheDocument();
    expect(within(step(1)).getByText("uv sync --extra pdf-pypdfium2")).toBeInTheDocument();
    expect(within(step(1)).getByRole("button", { name: "Copy install command for PDF reader: pypdfium2" })).toBeInTheDocument();
    expect(within(step(1)).queryByRole("button", { name: /^Install/ })).toBeNull();
  });

  it("shows the refusal line when another install is running", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { user } = await openPanel({
      "POST /v1/integrations/:extra/install": () => json({ status: "error", message: "Refused <raw> detail", reason: "install-running" }, 409),
    });
    await user.click(await within(step(1)).findByRole("button", { name: "Install PDF reader: pypdfium2" }));
    const dialog = await screen.findByRole("dialog", { name: "Install PDF reader: pypdfium2?" });
    await user.click(within(dialog).getByRole("button", { name: "Install" }));
    const alert = await within(step(1)).findByRole("alert");
    expect(alert).toHaveTextContent("Another install is running. Wait for it to finish, then try again.");
    expect(alert).not.toHaveTextContent("Refused");
  });
});

describe("Document reading: install job ends", () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it("reads the reader state again and shows Restart to apply when the job ends", async () => {
    let finished = false;
    const reading = () => {
      const readers = readingState().pdf_readers.map((reader) => (reader.name === "pypdfium2" && finished ? { ...reader, available: true, reason: null } : reader));
      return readingState({}, { pdf_readers: readers });
    };
    const server = settingsServer({
      "GET /v1/settings/document-reading": reading,
      "GET /v1/integrations": () => integrationsBody(finished ? PYPDFIUM2_RESTART : PYPDFIUM2_ENTRY),
      "GET /v1/integrations/install": () => ({ status: "ok", install: finished ? SUCCEEDED_INSTALL : RUNNING_INSTALL }),
    });
    startApp("#/settings/document-reading", server);
    await within(await screen.findByRole("region", { name: "Page routing" })).findByRole("group", { name: "PDF readers" });
    expect(await within(step(1)).findByRole("status")).toHaveTextContent("Installing pdf-pypdfium2.");
    expect(server.find("GET", "/v1/settings/document-reading")).toHaveLength(1);
    finished = true;
    await act(async () => void (await vi.advanceTimersByTimeAsync(1100)));
    expect(await within(step(1)).findByText("Restart to apply")).toBeInTheDocument();
    await waitFor(() => expect(server.find("GET", "/v1/settings/document-reading").length).toBeGreaterThan(1));
  });
});
