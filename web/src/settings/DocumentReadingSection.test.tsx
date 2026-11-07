import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { DocumentReadingState } from "../api/settingsDocumentReading";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { readingState, settingsServer } from "./test/fixtures";

const RESTART_NOTE = "These settings apply after a restart of omrs web. Saving does not change the reading in force.";
const IDENTITY_NOTE = "These settings are part of the index identity. After a restart, the next ingest can read existing files again.";

async function openSection(handlers = {}) {
  const server = settingsServer(handlers);
  startApp("#/settings/document-reading", server);
  const section = await screen.findByRole("region", { name: "Document reading" });
  await within(section).findByRole("group", { name: "PDF readers" });
  return { server, section, user: userEvent.setup() };
}

function row(name: string) {
  return screen.getByRole("group", { name });
}

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

describe("Document reading", () => {
  it("shows each reading setting as a compact row, with no mini card", async () => {
    const { section } = await openSection();
    for (const name of ["PDF readers", "OCR fallback", "OCR routing unit"]) {
      expect(row(name)).toHaveAttribute("data-slot", "setting-row");
    }
    expect(section.querySelector("[data-slot='card-inset']")).toBeNull();
  });

  it("opens from its address with its chip selected, straight before Configuration", async () => {
    await openSection();
    const chips = within(screen.getByRole("group", { name: "Sections" })).getAllByRole("button").map((button) => button.textContent);
    expect(chips.indexOf("Document reading")).toBe(chips.indexOf("Configuration") - 1);
    expect(screen.getByRole("button", { name: "Document reading" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows one row for each key the page edits with the value in force, its source and the default", async () => {
    const { section } = await openSection();
    const names = ["PDF readers", "OCR fallback", "OCR routing unit", "OCR engines", "Maths routing"];
    for (const name of names) expect(within(section).getByRole("group", { name })).toBeInTheDocument();
    for (const old of ["PDF reader", "Primary engine", "Fallback engine"]) expect(within(section).queryByRole("group", { name: old })).toBeNull();
    const readers = row("PDF readers");
    expect(within(readers).getByText("pdf_inspector, liteparse, pypdf", { selector: "code" })).toBeInTheDocument();
    expect(readers).toHaveTextContent("Default: pdf_inspector, liteparse, pypdf");
    expect(within(row("OCR fallback")).getByText("On", { selector: "code" })).toBeInTheDocument();
    expect(within(row("OCR routing unit")).getByText("page", { selector: "code" })).toBeInTheDocument();
    expect(row("OCR routing unit")).toHaveTextContent("default");
    expect(within(section).queryByText("Restart to apply")).toBeNull();
  });

  it("says the settings apply after a restart, that they are part of the index identity, and that a pipeline step can choose its reader", async () => {
    const { section } = await openSection();
    expect(section).toHaveTextContent(RESTART_NOTE);
    expect(section).toHaveTextContent(IDENTITY_NOTE);
    expect(section).toHaveTextContent("A Read document step in a pipeline can choose its own reader.");
  });

  it("shows a list saved but not yet in force with Restart to apply, and the reader in use when it is not the first", async () => {
    await openSection({
      "GET /v1/settings/document-reading": () =>
        readingState({ pdf_readers: { saved: ["liteparse", "pypdf"], source: "config-file", restart_pending: true } }, { pdf_reader_in_use: "liteparse" }),
    });
    const readers = row("PDF readers");
    expect(within(readers).getByText("pdf_inspector, liteparse, pypdf", { selector: "code" })).toBeInTheDocument();
    expect(readers).toHaveTextContent("Saved for the next launch: liteparse, pypdf");
    expect(within(readers).getByText("Restart to apply")).toBeInTheDocument();
    expect(readers).toHaveTextContent("In use: liteparse");
  });

  it("says nothing about the reader in use when it is the first in the list", async () => {
    await openSection();
    expect(row("PDF readers")).not.toHaveTextContent("In use:");
  });

  it("makes a key from the environment read-only and names its variable", async () => {
    const lock = "Remove OCR_ROUTING_UNIT from the environment or .env to edit it here.";
    await openSection({
      "GET /v1/settings/document-reading": () => readingState({ ocr_routing_unit: { value: "page", source: "dotenv", locked: true, lock_reason: lock } }),
    });
    const unit = row("OCR routing unit");
    expect(within(unit).queryByRole("button", { name: /Edit/ })).toBeNull();
    expect(unit).toHaveTextContent(lock);
    expect(within(row("PDF readers")).getByRole("button", { name: "Edit PDF readers" })).toBeInTheDocument();
  });

  it("edits the readers as an ordered list and writes only the list key", async () => {
    const { user, server } = await openSection(savingServer(readingState()));
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Edit PDF readers" }));
    const list = within(row("PDF readers")).getByRole("list", { name: "PDF readers" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Move pypdf up" }));
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(server.find("PUT", "/v1/settings/document-reading").map((call) => call.body)).toEqual([{ values: { pdf_readers: ["pdf_inspector", "pypdf", "liteparse"] }, revision: "r1" }]),
    );
    const dialog = await screen.findByRole("dialog", { name: "Restart to apply?" });
    expect(dialog).toHaveTextContent("PDF readers applies after a restart.");
  });

  it("keeps Save off until the list changes", async () => {
    const { user } = await openSection();
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Edit PDF readers" }));
    expect(within(row("PDF readers")).getByRole("button", { name: "Save" })).toBeDisabled();
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Move pypdf up" }));
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Move pypdf down" }));
    expect(within(row("PDF readers")).getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("shows no row for an old single-value key, even when the server still sends one", async () => {
    const base = readingState();
    const old = (key: "pdf_reader" | "ocr_engine_primary" | "ocr_engine_fallback", value: string) => ({ ...base.settings[0]!, key, value, default: value });
    await openSection({
      "GET /v1/settings/document-reading": () => ({ ...base, settings: [...base.settings, old("pdf_reader", "pypdf"), old("ocr_engine_primary", "dots-mocr"), old("ocr_engine_fallback", "paddleocr-vl")] }),
    });
    const panel = screen.getByRole("region", { name: "Page routing" });
    const rows = within(panel).getAllByRole("group").flatMap((group) => group.getAttribute("aria-label") ?? []);
    expect(rows).toEqual(["OCR fallback", "OCR routing unit", "PDF readers", "Skip blank pages", "Maths routing", "Non-Latin routing", "Host router", "Local OCR backends", "OCR engines"]);
    for (const name of ["PDF reader", "Primary engine", "Fallback engine"]) expect(screen.queryByRole("group", { name })).toBeNull();
  });

  it("makes a locked engine list read-only and names the variable", async () => {
    const lock = "Remove OCR_ENGINES from the environment or .env to edit it here.";
    await openSection({
      "GET /v1/settings/document-reading": () => readingState({ ocr_engines: { source: "env", locked: true, lock_reason: lock } }),
    });
    const engines = row("OCR engines");
    expect(within(engines).queryByRole("button", { name: /Edit/ })).toBeNull();
    expect(engines).toHaveTextContent(lock);
  });

  it("marks a listed PDF reader that is not installed with a link to Integrations, and offers only the others to add", async () => {
    const { user } = await openSection(savingServer(readingState({ pdf_readers: { value: ["pdf_inspector", "pypdfium2"], default: ["pdf_inspector", "liteparse", "pypdf"] } })));
    expect(row("PDF readers")).toHaveTextContent("pypdfium2: Not installed.");
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Edit PDF readers" }));
    expect(within(row("PDF readers")).getByRole("link", { name: "See PDF readers in Integrations" })).toHaveAttribute("href", "#/integrations/pdf-readers");
    await user.click(within(row("PDF readers")).getByRole("combobox", { name: "Add reader" }));
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual(["pypdf", "liteparse"]);
  });

  it("does not let a reader that is not installed be added", async () => {
    const { user } = await openSection(savingServer(readingState({ pdf_readers: { value: ["pdf_inspector"] } })));
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Edit PDF readers" }));
    await user.click(within(row("PDF readers")).getByRole("combobox", { name: "Add reader" }));
    expect(await screen.findByRole("option", { name: "pypdfium2 (optional, not installed)" })).toHaveAttribute("aria-disabled", "true");
  });

  it("refuses an empty reader list", async () => {
    const { user, server } = await openSection(savingServer(readingState({ pdf_readers: { value: ["pdf_inspector", "pypdf"] } })));
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Edit PDF readers" }));
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Remove pdf_inspector" }));
    expect(within(row("PDF readers")).getByRole("button", { name: "Remove pypdf" })).toBeDisabled();
    expect(row("PDF readers")).toHaveTextContent("The list needs at least one reader.");
    expect(server.find("PUT", "/v1/settings/document-reading")).toHaveLength(0);
  });

  it("warns when pdf_inspector is the only reader, because a PDF with no text layer then indexes nothing", async () => {
    const { user } = await openSection();
    expect(row("PDF readers")).not.toHaveTextContent("indexes nothing");
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Edit PDF readers" }));
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Remove liteparse" }));
    expect(row("PDF readers")).not.toHaveTextContent("indexes nothing");
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Remove pypdf" }));
    expect(row("PDF readers")).toHaveTextContent("pdf_inspector alone has no retry: a PDF with no text layer indexes nothing. Add liteparse or pypdf.");
  });

  it("shows the warning outside edit mode when the list in force is pdf_inspector alone", async () => {
    await openSection({ "GET /v1/settings/document-reading": () => readingState({ pdf_readers: { value: ["pdf_inspector"] } }) });
    expect(row("PDF readers")).toHaveTextContent("indexes nothing");
  });

  it("shows no warning for a single reader that is not pdf_inspector", async () => {
    await openSection({ "GET /v1/settings/document-reading": () => readingState({ pdf_readers: { value: ["pypdf"] } }) });
    expect(row("PDF readers")).not.toHaveTextContent("indexes nothing");
  });

  it("lists the engines in order and says Not provisioned on an engine that cannot run yet", async () => {
    await openSection();
    const engines = row("OCR engines");
    expect(within(engines).getByText("dots-mocr, paddleocr-vl", { selector: "code" })).toBeInTheDocument();
    expect(engines).toHaveTextContent("paddleocr-vl: Not provisioned. Run python3 ocr-workers/provision.py paddleocr-vl.");
  });

  it("never says that a worker command replaces an engine, because the setting is gone", async () => {
    await openSection({ "GET /v1/settings/document-reading": () => readingState({}, { ocr: { ...readingState().ocr, worker_command_set: true } as never }) });
    expect(row("OCR engines")).not.toHaveTextContent("OCR_WORKER_COMMAND");
  });

  it("removes the fallback engine to run with one engine, and writes only the list key", async () => {
    const { user, server } = await openSection(savingServer(readingState()));
    await user.click(within(row("OCR engines")).getByRole("button", { name: "Edit OCR engines" }));
    await user.click(within(row("OCR engines")).getByRole("button", { name: "Remove paddleocr-vl" }));
    await user.click(within(row("OCR engines")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/document-reading").map((call) => call.body)).toEqual([{ values: { ocr_engines: ["dots-mocr"] }, revision: "r1" }]));
    const dialog = await screen.findByRole("dialog", { name: "Restart to apply?" });
    expect(dialog).toHaveTextContent("OCR engines applies after a restart.");
    expect(dialog).toHaveTextContent(IDENTITY_NOTE);
    await user.click(within(dialog).getByRole("button", { name: "Later" }));
    const engines = row("OCR engines");
    expect(within(engines).getByText("Restart to apply")).toBeInTheDocument();
    expect(engines).toHaveTextContent("Saved for the next launch: dots-mocr");
  });

  it("adds an engine that is not provisioned, because a later engine only runs when the ones above cannot", async () => {
    const { user, server } = await openSection(savingServer(readingState({ ocr_engines: { value: ["dots-mocr"] } })));
    await user.click(within(row("OCR engines")).getByRole("button", { name: "Edit OCR engines" }));
    await user.click(within(row("OCR engines")).getByRole("combobox", { name: "Add engine" }));
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual(["paddleocr-vl (not provisioned)"]);
    await user.click(screen.getByRole("option", { name: "paddleocr-vl (not provisioned)" }));
    expect(row("OCR engines")).toHaveTextContent("Not provisioned. Run python3 ocr-workers/provision.py paddleocr-vl.");
    await user.click(within(row("OCR engines")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/document-reading").map((call) => call.body)).toEqual([{ values: { ocr_engines: ["dots-mocr", "paddleocr-vl"] }, revision: "r1" }]));
  });

  it("offers page as the only routing unit", async () => {
    const { user } = await openSection();
    await user.click(within(row("OCR routing unit")).getByRole("button", { name: "Edit OCR routing unit" }));
    await user.click(within(row("OCR routing unit")).getByRole("combobox", { name: "OCR routing unit" }));
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual(["page"]);
  });

  it("offers off, detect and always for Non-Latin routing and says what detect cannot see", async () => {
    const { user } = await openSection();
    const routing = row("Non-Latin routing");
    expect(within(routing).getByText("off", { selector: "code" })).toBeInTheDocument();
    expect(routing).toHaveTextContent("default");
    expect(routing).toHaveTextContent("detect sees only text that already exists");
    expect(routing).toHaveTextContent("does not catch scanned pages");
    expect(routing).toHaveTextContent("Use always for a collection you know is non-Latin.");
    await user.click(within(routing).getByRole("button", { name: "Edit Non-Latin routing" }));
    await user.click(within(routing).getByRole("combobox", { name: "Non-Latin routing" }));
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual(["off (default)", "detect", "always"]);
  });

  it("saves always for Non-Latin routing and asks for a restart", async () => {
    const { user, server } = await openSection(savingServer(readingState()));
    await user.click(within(row("Non-Latin routing")).getByRole("button", { name: "Edit Non-Latin routing" }));
    await user.click(within(row("Non-Latin routing")).getByRole("combobox", { name: "Non-Latin routing" }));
    await user.click(await screen.findByRole("option", { name: "always" }));
    await user.click(within(row("Non-Latin routing")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/document-reading").map((call) => call.body)).toEqual([{ values: { ocr_non_latin_routing: "always" }, revision: "r1" }]));
    const dialog = await screen.findByRole("dialog", { name: "Restart to apply?" });
    expect(dialog).toHaveTextContent("Non-Latin routing applies after a restart.");
    await user.click(within(dialog).getByRole("button", { name: "Later" }));
    expect(within(row("Non-Latin routing")).getByText("Restart to apply")).toBeInTheDocument();
  });

  it("makes Non-Latin routing read-only when the environment holds it", async () => {
    const lock = "Remove OCR_NON_LATIN_ROUTING from the environment or .env to edit it here.";
    await openSection({
      "GET /v1/settings/document-reading": () => readingState({ ocr_non_latin_routing: { value: "detect", source: "env", locked: true, lock_reason: lock } }),
    });
    expect(within(row("Non-Latin routing")).queryByRole("button", { name: /Edit/ })).toBeNull();
    expect(row("Non-Latin routing")).toHaveTextContent(lock);
  });

  it("saves a switch as true or false", async () => {
    const { user, server } = await openSection(savingServer(readingState()));
    await user.click(within(row("Maths routing")).getByRole("button", { name: "Edit Maths routing" }));
    const toggle = within(row("Maths routing")).getByRole("switch", { name: "Maths routing" });
    expect(toggle).toHaveAttribute("aria-checked", "true");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-checked", "false");
    await user.click(within(row("Maths routing")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/document-reading").map((call) => call.body)).toEqual([{ values: { ocr_maths_routing_enabled: false }, revision: "r1" }]));
  });

  it("sends null for Use default, so the key leaves omrs.jsonc", async () => {
    const { user, server } = await openSection(savingServer(readingState({ ocr_engines: { value: ["dots-mocr", "paddleocr-vl"], saved: ["dots-mocr"], source: "default", restart_pending: true } })));
    await user.click(within(row("OCR engines")).getByRole("button", { name: "Edit OCR engines" }));
    await user.click(within(row("OCR engines")).getByRole("button", { name: "Use default" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/document-reading").map((call) => call.body)).toEqual([{ values: { ocr_engines: null }, revision: "r1" }]));
    await waitFor(() => expect(within(row("OCR engines")).queryByText("Restart to apply")).toBeNull());
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("offers no Use default for a key the file does not hold", async () => {
    const { user } = await openSection();
    await user.click(within(row("OCR routing unit")).getByRole("button", { name: "Edit OCR routing unit" }));
    expect(within(row("OCR routing unit")).queryByRole("button", { name: "Use default" })).toBeNull();
  });

  it("shows the server message of a refused save and leaves the row unchanged", async () => {
    const { user } = await openSection({
      "PUT /v1/settings/document-reading": () => json({ status: "error", message: "pdf_readers: The list cannot hold a name twice." }, 400),
    });
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Edit PDF readers" }));
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Move pypdf up" }));
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Save" }));
    expect(await within(row("PDF readers")).findByRole("alert")).toHaveTextContent("pdf_readers: The list cannot hold a name twice.");
    await user.click(within(row("PDF readers")).getByRole("button", { name: "Cancel" }));
    expect(within(row("PDF readers")).getByText("pdf_inspector, liteparse, pypdf", { selector: "code" })).toBeInTheDocument();
    expect(row("PDF readers")).not.toHaveTextContent("Restart to apply");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("offers Reload after a file conflict and reads the section again", async () => {
    const { user, server } = await openSection({
      "PUT /v1/settings/document-reading": () => json({ status: "error", message: "omrs.jsonc changed on disk. Reload to see the new values." }, 409),
    });
    await user.click(within(row("Maths routing")).getByRole("button", { name: "Edit Maths routing" }));
    await user.click(within(row("Maths routing")).getByRole("switch", { name: "Maths routing" }));
    await user.click(within(row("Maths routing")).getByRole("button", { name: "Save" }));
    const alert = await within(row("Maths routing")).findByRole("alert");
    expect(alert).toHaveTextContent("omrs.jsonc changed on disk. Reload to see the new values.");
    expect(server.find("GET", "/v1/settings/document-reading")).toHaveLength(1);
    await user.click(within(alert).getByRole("button", { name: "Reload" }));
    await waitFor(() => expect(server.find("GET", "/v1/settings/document-reading")).toHaveLength(2));
  });

  it("shows one friendly line with Retry when the section cannot load", async () => {
    const server = settingsServer({ "GET /v1/settings/document-reading": () => json({ status: "error", message: "Traceback boom" }, 500) });
    startApp("#/settings/document-reading", server);
    const section = await screen.findByRole("region", { name: "Document reading" });
    expect(await within(section).findByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByText(/Traceback/)).toBeNull();
  });
});
