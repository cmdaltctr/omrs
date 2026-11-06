import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { DocumentReadingState } from "../api/settingsDocumentReading";
import { startApp } from "../test/startApp";
import { readingState, settingsServer } from "./test/fixtures";

/** Settings › Document reading edits `ocr_local_backends` like the PDF reader list (change local-ocr-backends, task 6.4). */
async function openSection(handlers = {}) {
  const server = settingsServer(handlers);
  startApp("#/settings/document-reading", server);
  const section = await screen.findByRole("region", { name: "Document reading" });
  await within(section).findByRole("group", { name: "Local OCR backends" });
  return { server, section, user: userEvent.setup() };
}

const row = () => screen.getByRole("group", { name: "Local OCR backends" });

function savingServer(start: DocumentReadingState) {
  let state = start;
  return {
    "GET /v1/settings/document-reading": () => state,
    "PUT /v1/settings/document-reading": (body: Record<string, unknown>) => {
      const values = body.values as Record<string, unknown>;
      state = {
        ...state,
        revision: "r2",
        // The real route removes the retired key in the same write as a save of the cuts.
        retired_keys: "ocr_local_cuts" in values ? [] : state.retired_keys,
        settings: state.settings.map((setting) => {
          if (!(setting.key in values)) return setting;
          const saved = values[setting.key] as never;
          return { ...setting, saved, restart_pending: saved !== null && JSON.stringify(saved) !== JSON.stringify(setting.value) };
        }),
      };
      return state;
    },
  };
}

const TWO = readingState({}, {
  local_ocr_backends: [
    { name: "pp-ocrv6-small", available: true, reason: null, default_cut: 0.92 },
    { name: "indra", available: false, reason: "Not installed.", default_cut: 0.94 },
  ],
});

describe("Document reading local OCR backends", () => {
  it("shows the list in its own Local OCR block, before the engines", async () => {
    const { section } = await openSection();
    const ocr = within(section).getByRole("region", { name: "OCR" });
    const block = within(ocr).getByRole("group", { name: "Local OCR" });
    expect(within(block).getAllByRole("group").map((group) => group.getAttribute("aria-label"))).toEqual(["Local OCR backends"]);
    expect(within(row()).getByText("pp-ocrv6-small", { selector: "code" })).toBeInTheDocument();
    expect(row()).toHaveTextContent("Default: pp-ocrv6-small");
  });

  it("edits the backends as an ordered list and writes the list with the cuts in one request", async () => {
    const { user, server } = await openSection(savingServer(readingState({ ocr_local_backends: { value: ["pp-ocrv6-small", "indra"] } }, TWO)));
    await user.click(within(row()).getByRole("button", { name: "Edit Local OCR backends" }));
    expect(within(within(row()).getByRole("list", { name: "Local OCR backends" })).getAllByRole("listitem")).toHaveLength(2);
    await user.click(within(row()).getByRole("button", { name: "Move indra up" }));
    await user.click(within(row()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/document-reading").map((call) => call.body)).toEqual([{ values: { ocr_local_backends: ["indra", "pp-ocrv6-small"], ocr_local_cuts: null }, revision: "r1" }]));
    const dialog = await screen.findByRole("dialog", { name: "Restart to apply?" });
    expect(dialog).toHaveTextContent("Local OCR backends applies after a restart.");
  });

  it("does not let a backend that is not installed be added", async () => {
    const { user } = await openSection({ "GET /v1/settings/document-reading": () => readingState({}, TWO) });
    await user.click(within(row()).getByRole("button", { name: "Edit Local OCR backends" }));
    await user.click(within(row()).getByRole("combobox", { name: "Add backend" }));
    expect(await screen.findByRole("option", { name: "indra (not installed)" })).toHaveAttribute("aria-disabled", "true");
  });

  it("offers a backend that an installed package adds, from the server list", async () => {
    const added = readingState({}, { local_ocr_backends: [...TWO.local_ocr_backends, { name: "fake-ocr", available: true, reason: null, default_cut: 0.9 }] });
    const { user, server } = await openSection(savingServer(added));
    await user.click(within(row()).getByRole("button", { name: "Edit Local OCR backends" }));
    await user.click(within(row()).getByRole("combobox", { name: "Add backend" }));
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual(["indra (not installed)", "fake-ocr"]);
    await user.click(screen.getByRole("option", { name: "fake-ocr" }));
    await user.click(within(row()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/document-reading").map((call) => call.body)).toEqual([{ values: { ocr_local_backends: ["pp-ocrv6-small", "fake-ocr"], ocr_local_cuts: null }, revision: "r1" }]));
  });

  it("names a listed backend that is not installed", async () => {
    await openSection({ "GET /v1/settings/document-reading": () => readingState({ ocr_local_backends: { value: ["indra", "pp-ocrv6-small"] } }, TWO) });
    expect(row()).toHaveTextContent("indra: Not installed.");
  });
});

const BOTH = readingState({ ocr_local_backends: { value: ["pp-ocrv6-small", "indra"] } }, TWO);
const INVALID = "The cut must be a number from 0 to 1.";
const puts = (server: Awaited<ReturnType<typeof openSection>>["server"]) => server.find("PUT", "/v1/settings/document-reading").map((call) => call.body);
const cut = (name: string) => within(row()).getByRole("spinbutton", { name: `Confidence cut for ${name}` });
const edit = (user: ReturnType<typeof userEvent.setup>) => user.click(within(row()).getByRole("button", { name: "Edit Local OCR backends" }));

describe("Document reading local OCR confidence cuts", () => {
  it("shows an empty cut input with the default in each listed backend row", async () => {
    await openSection({ "GET /v1/settings/document-reading": () => BOTH });
    expect(cut("pp-ocrv6-small")).toHaveValue(null);
    expect(cut("pp-ocrv6-small")).toHaveAttribute("placeholder", "Default 0.92");
    expect(cut("indra")).toHaveAttribute("placeholder", "Default 0.94");
    expect(cut("indra")).toHaveAttribute("readonly");
  });

  it("shows a set cut in its row", async () => {
    await openSection({ "GET /v1/settings/document-reading": () => readingState({ ocr_local_backends: { value: ["pp-ocrv6-small", "indra"] }, ocr_local_cuts: { value: { indra: 0.95 }, saved: { indra: 0.95 }, source: "config-file" } }, TWO) });
    expect(cut("indra")).toHaveValue(0.95);
    expect(cut("pp-ocrv6-small")).toHaveValue(null);
  });

  it("saves a typed cut with the list in one request", async () => {
    const { user, server } = await openSection(savingServer(BOTH));
    await edit(user);
    await user.type(cut("indra"), "0.95");
    await user.click(within(row()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(puts(server)).toEqual([{ values: { ocr_local_backends: ["pp-ocrv6-small", "indra"], ocr_local_cuts: { indra: 0.95 } }, revision: "r1" }]));
    expect(await screen.findByRole("dialog", { name: "Restart to apply?" })).toBeInTheDocument();
  });

  it("sends null when the last cut is cleared", async () => {
    const saved = readingState({ ocr_local_backends: { value: ["pp-ocrv6-small", "indra"] }, ocr_local_cuts: { value: { indra: 0.95 }, saved: { indra: 0.95 }, source: "config-file" } }, TWO);
    const { user, server } = await openSection(savingServer(saved));
    await edit(user);
    await user.clear(cut("indra"));
    await user.click(within(row()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(puts(server)).toEqual([{ values: { ocr_local_backends: ["pp-ocrv6-small", "indra"], ocr_local_cuts: null }, revision: "r1" }]));
  });

  it("keeps the cut of a backend that is not listed", async () => {
    const saved = readingState({ ocr_local_cuts: { value: { indra: 0.95 }, saved: { indra: 0.95 }, source: "config-file" } }, TWO);
    const { user, server } = await openSection(savingServer(saved));
    await edit(user);
    await user.type(cut("pp-ocrv6-small"), "0.9");
    await user.click(within(row()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(puts(server)).toEqual([{ values: { ocr_local_backends: ["pp-ocrv6-small"], ocr_local_cuts: { indra: 0.95, "pp-ocrv6-small": 0.9 } }, revision: "r1" }]));
  });

  it.each(["1.5", "-0.1"])("refuses %s beside the input and sends nothing", async (text) => {
    const { user, server } = await openSection(savingServer(BOTH));
    await edit(user);
    await user.type(cut("indra"), text);
    expect(within(row()).getByText(INVALID)).toBeInTheDocument();
    expect(within(row()).getByRole("button", { name: "Save" })).toBeDisabled();
    expect(puts(server)).toEqual([]);
  });

  it("accepts the save again once the bad value is replaced", async () => {
    const { user, server } = await openSection(savingServer(BOTH));
    await edit(user);
    await user.type(cut("indra"), "1.5");
    await user.clear(cut("indra"));
    await user.type(cut("indra"), "0.95");
    expect(within(row()).queryByText(INVALID)).toBeNull();
    await user.click(within(row()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(puts(server)).toHaveLength(1));
  });

  it("makes every cut input read-only and names the variable when OCR_LOCAL_CUTS locks the map", async () => {
    const lock = "Remove OCR_LOCAL_CUTS from the environment or .env to edit it here.";
    const locked = readingState({ ocr_local_backends: { value: ["pp-ocrv6-small", "indra"] }, ocr_local_cuts: { value: { indra: 0.95 }, source: "env", locked: true, lock_reason: lock } }, TWO);
    const { user, server } = await openSection(savingServer(locked));
    expect(row()).toHaveTextContent(lock);
    expect(cut("indra")).toHaveAttribute("readonly");
    await edit(user);
    expect(cut("indra")).toHaveAttribute("readonly");
    await user.click(within(row()).getByRole("button", { name: "Move indra up" }));
    await user.click(within(row()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(puts(server)).toEqual([{ values: { ocr_local_backends: ["indra", "pp-ocrv6-small"] }, revision: "r1" }]));
  });

  it("offers no Edit when the environment locks both the list and the cuts", async () => {
    await openSection({
      "GET /v1/settings/document-reading": () => readingState({ ocr_local_backends: { source: "env", locked: true, lock_reason: "Remove OCR_LOCAL_BACKENDS from the environment or .env to edit it here." }, ocr_local_cuts: { source: "env", locked: true, lock_reason: "Remove OCR_LOCAL_CUTS from the environment or .env to edit it here." } }),
    });
    expect(within(row()).queryByRole("button", { name: /Edit/ })).toBeNull();
    expect(row()).toHaveTextContent("Remove OCR_LOCAL_CUTS from the environment or .env to edit it here.");
  });
});

describe("Document reading retired cut key", () => {
  const NOTICE = "omrs.jsonc holds ocr_local_min_confidence. OMRS ignores it. Each backend now has its own cut.";
  const retired = readingState({}, { retired_keys: ["ocr_local_min_confidence"] });

  it("shows no notice when the file does not hold the key", async () => {
    await openSection();
    expect(row()).not.toHaveTextContent("ocr_local_min_confidence");
  });

  it("removes the key with one request that leaves the cuts as saved, and the notice goes", async () => {
    const { user, server } = await openSection(savingServer(retired));
    expect(row()).toHaveTextContent(NOTICE);
    await user.click(within(row()).getByRole("button", { name: "Remove it" }));
    await waitFor(() => expect(puts(server)).toEqual([{ values: { ocr_local_cuts: null }, revision: "r1" }]));
    await waitFor(() => expect(row()).not.toHaveTextContent("ocr_local_min_confidence"));
  });

  it("sends the saved cuts back so they stay", async () => {
    const withCuts = readingState({ ocr_local_cuts: { value: { indra: 0.95 }, saved: { indra: 0.95 }, source: "config-file" } }, { ...TWO, retired_keys: ["ocr_local_min_confidence"] });
    const { user, server } = await openSection(savingServer(withCuts));
    await user.click(within(row()).getByRole("button", { name: "Remove it" }));
    await waitFor(() => expect(puts(server)).toEqual([{ values: { ocr_local_cuts: { indra: 0.95 } }, revision: "r1" }]));
  });

  it("goes away when a save of the cuts removes the key", async () => {
    const { user } = await openSection(savingServer(readingState({}, { ...TWO, retired_keys: ["ocr_local_min_confidence"] })));
    await edit(user);
    await user.type(cut("pp-ocrv6-small"), "0.9");
    await user.click(within(row()).getByRole("button", { name: "Save" }));
    await user.click(await screen.findByRole("button", { name: "Later" }));
    expect(row()).not.toHaveTextContent("ocr_local_min_confidence");
  });
});
