import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { DocumentReadingState } from "../api/settingsDocumentReading";
import { startApp } from "../test/startApp";
import { readingState, settingsServer } from "./test/fixtures";
import { documentRouters, HANDWRITING, HOSTED } from "./test/routerFixtures";

const COST = "The router judges every unflagged page with text: about 3.6 s per judged page with the local model. In Experiment 43 it sent about 2.7% of healthy pages (15 of 565) to OCR.";

/** A fake server that holds the state and applies each PUT, as the real route does. */
function savingServer(start: DocumentReadingState) {
  let state = start;
  return {
    "GET /v1/settings/document-reading": () => state,
    "PUT /v1/settings/document-reading": (body: Record<string, unknown>) => {
      const values = body.values as Record<string, string | null>;
      state = {
        ...state,
        revision: "r2",
        settings: state.settings.map((setting) => {
          if (!(setting.key in values)) return setting;
          const saved = values[setting.key] ?? null;
          return { ...setting, saved, restart_pending: saved !== null && saved !== setting.value };
        }),
      };
      return state;
    },
  };
}

async function openHost(handlers = {}) {
  const server = settingsServer({ "GET /v1/settings/document-routers": () => documentRouters([HANDWRITING, HOSTED]), ...handlers });
  startApp("#/settings/document-reading", server);
  const card = await screen.findByRole("region", { name: "Page routing" });
  const host = await within(card).findByRole("group", { name: "Host router" });
  return { server, card, host, user: userEvent.setup() };
}

describe("Host router row", () => {
  it("shows No router by default with the cost of judging pages", async () => {
    const { host } = await openHost();
    expect(within(host).getByText("No router", { selector: "code" })).toBeInTheDocument();
    expect(host).toHaveTextContent(COST);
  });

  it("offers No router and each router of the file, and saves the chosen name", async () => {
    const { host, user, server } = await openHost(savingServer(readingState()));
    await user.click(within(host).getByRole("button", { name: "Edit Host router" }));
    await user.click(within(host).getByRole("combobox", { name: "Host router" }));
    const names = screen.getAllByRole("option").map((option) => option.textContent);
    expect(names).toEqual(["No router", "handwriting", "hosted-check"]);
    await user.click(screen.getByRole("option", { name: "handwriting" }));
    await user.click(within(host).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/document-reading").map((call) => call.body)).toEqual([{ values: { document_router: "handwriting" }, revision: "r1" }]));
    await screen.findByRole("dialog", { name: "Restart to apply?" });
    expect(within(host).getByText("Restart to apply")).toBeInTheDocument();
    expect(host).toHaveTextContent("Saved for the next launch: handwriting");
  });

  it("removes the saved router when the user picks No router", async () => {
    const start = readingState({ document_router: { saved: "handwriting", source: "default", restart_pending: true } });
    const { host, user, server } = await openHost(savingServer(start));
    await user.click(within(host).getByRole("button", { name: "Edit Host router" }));
    await user.click(within(host).getByRole("combobox", { name: "Host router" }));
    await user.click(screen.getByRole("option", { name: "No router" }));
    await user.click(within(host).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/document-reading").map((call) => call.body)).toEqual([{ values: { document_router: null }, revision: "r1" }]));
  });

  it("is read-only and names the variable when the environment sets it", async () => {
    const lock = "Remove DOCUMENT_ROUTER from the environment or .env to edit it here.";
    const { host } = await openHost({
      "GET /v1/settings/document-reading": () => readingState({ document_router: { value: "handwriting", source: "env", locked: true, lock_reason: lock } }),
    });
    expect(within(host).queryByRole("button", { name: /Edit/ })).toBeNull();
    expect(host).toHaveTextContent(lock);
    expect(within(host).getByText("handwriting", { selector: "code" })).toBeInTheDocument();
  });
});
