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
      state = { ...state, revision: "r2", settings: state.settings.map((setting) => (setting.key in values ? { ...setting, saved: values[setting.key] as never, restart_pending: true } : setting)) };
      return state;
    },
  };
}

const TWO = readingState({}, {
  local_ocr_backends: [
    { name: "pp-ocrv6-small", available: true, reason: null },
    { name: "indra", available: false, reason: "Not installed." },
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

  it("edits the backends as an ordered list and writes only the list key", async () => {
    const { user, server } = await openSection(savingServer(readingState({ ocr_local_backends: { value: ["pp-ocrv6-small", "indra"] } }, TWO)));
    await user.click(within(row()).getByRole("button", { name: "Edit Local OCR backends" }));
    expect(within(within(row()).getByRole("list", { name: "Local OCR backends" })).getAllByRole("listitem")).toHaveLength(2);
    await user.click(within(row()).getByRole("button", { name: "Move indra up" }));
    await user.click(within(row()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/document-reading").map((call) => call.body)).toEqual([{ values: { ocr_local_backends: ["indra", "pp-ocrv6-small"] }, revision: "r1" }]));
    const dialog = await screen.findByRole("dialog", { name: "Restart to apply?" });
    expect(dialog).toHaveTextContent("Local OCR backends applies after a restart.");
  });

  it("does not let a backend that is not installed be added", async () => {
    const { user } = await openSection({ "GET /v1/settings/document-reading": () => readingState({}, TWO) });
    await user.click(within(row()).getByRole("button", { name: "Edit Local OCR backends" }));
    await user.click(within(row()).getByRole("combobox", { name: "Add backend" }));
    expect(await screen.findByRole("option", { name: "indra (not installed)" })).toHaveAttribute("aria-disabled", "true");
  });

  it("names a listed backend that is not installed", async () => {
    await openSection({ "GET /v1/settings/document-reading": () => readingState({ ocr_local_backends: { value: ["indra", "pp-ocrv6-small"] } }, TWO) });
    expect(row()).toHaveTextContent("indra: Not installed.");
  });
});
