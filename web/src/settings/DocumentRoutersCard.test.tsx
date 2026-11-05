import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { DocumentRouterEntry } from "../api/routerMaps";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { settingsServer } from "./test/fixtures";
import { decisionModels, documentRouters, HANDWRITING, HOSTED } from "./test/routerFixtures";

const COST = "The router judges every unflagged page with text: about 3.6 s per judged page with the local model. In Experiment 43 it sent about 2.7% of healthy pages (15 of 565) to OCR.";
const WARNING = "Page text and page images go to TypeSafe at api.typesafe.ai, a third party off this machine.";

async function openRouters(handlers = {}) {
  const server = settingsServer({
    "GET /v1/settings/decision-models": () => decisionModels(),
    "GET /v1/settings/document-routers": () => documentRouters([{ ...HANDWRITING, host: true, used_by: ["Scanned theses"] }, HOSTED]),
    "PUT /v1/settings/document-routers/:name": () => documentRouters(),
    ...handlers,
  });
  startApp("#/settings/document-reading", server);
  const card = await screen.findByRole("region", { name: "Router" });
  await within(card).findByRole("listitem", { name: "handwriting" });
  return { server, card, user: userEvent.setup() };
}

const row = (name: string) => screen.getByRole("listitem", { name });
const puts = (server: Awaited<ReturnType<typeof openRouters>>["server"]) => server.find("PUT", "/v1/settings/document-routers/").map((call) => [call.path, call.body]);

describe("Router section", () => {
  it("shows one row per router with its model, question, threshold, image flag, host state and users", async () => {
    const { card } = await openRouters();
    const local = row("handwriting");
    expect(local).toHaveTextContent("clef-local");
    expect(local).toHaveTextContent("Does the text match the text written or printed on the page image?");
    expect(local).toHaveTextContent("Threshold: 0.172");
    expect(local).toHaveTextContent("Images");
    expect(within(local).getByText("Host router")).toBeInTheDocument();
    expect(local).toHaveTextContent("Used by profile: Scanned theses");
    expect(local).not.toHaveTextContent("third party");
    expect(card).toHaveTextContent(COST);
  });

  it("warns on a hosted router, marks a hosted image router experimental and says it will not run without the opt-in", async () => {
    await openRouters();
    const hosted = row("hosted-check");
    expect(hosted).toHaveTextContent(WARNING);
    expect(within(hosted).getByText(/experimental/i)).toBeInTheDocument();
    expect(hosted).toHaveTextContent("Will not run: Send pages off this machine is off.");
    expect(within(row("handwriting")).queryByText(/experimental/i)).toBeNull();
    expect(row("handwriting")).not.toHaveTextContent("Will not run");
  });

  it("creates a router from the template with the Experiment 43 values and the not confirmed note", async () => {
    const { card, user, server } = await openRouters();
    await user.click(within(card).getByRole("button", { name: "New from template: Text matches the page image" }));
    const form = within(card).getByRole("form", { name: "New router" });
    expect(within(form).getByLabelText("Question")).toHaveValue("Does the text match the text written or printed on the page image?");
    expect(within(form).getByRole("checkbox", { name: "Sees the page image" })).toBeChecked();
    expect(within(form).getByLabelText("Characters sent")).toHaveValue(2000);
    expect(within(form).getByLabelText("Threshold")).toHaveValue(0.172);
    expect(form).toHaveTextContent("Fitted on Experiment 33 documents, not confirmed.");
    expect(form).toHaveTextContent(COST);
    await user.type(within(form).getByLabelText("Name"), "pages");
    await user.click(within(form).getByRole("button", { name: "Save" }));
    const entry: DocumentRouterEntry = { model: "clef-local", question: "Does the text match the text written or printed on the page image?", threshold: 0.172, images: true, max_chars: 2000, send_off_machine: false };
    await waitFor(() => expect(puts(server)).toEqual([["/v1/settings/document-routers/pages", { entry, revision: "r1" }]]));
  });

  it("creates a blank router on a hosted model with the warning and the opt-in off by default", async () => {
    const { card, user, server } = await openRouters();
    await user.click(within(card).getByRole("button", { name: "New router" }));
    const form = within(card).getByRole("form", { name: "New router" });
    expect(within(form).queryByRole("checkbox", { name: "Send pages off this machine" })).toBeNull();
    await user.type(within(form).getByLabelText("Name"), "remote");
    await user.click(within(form).getByRole("combobox", { name: "Decision model" }));
    await user.click(screen.getByRole("option", { name: "jev" }));
    await user.type(within(form).getByLabelText("Question"), "Is this page typed?");
    expect(form).toHaveTextContent("Page text goes to TypeSafe at api.typesafe.ai, a third party off this machine.");
    const optIn = within(form).getByRole("checkbox", { name: "Send pages off this machine" });
    expect(optIn).not.toBeChecked();
    await user.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(puts(server)).toEqual([["/v1/settings/document-routers/remote", { entry: { model: "jev", question: "Is this page typed?", threshold: 0.5, images: false, max_chars: 2000, send_off_machine: false }, revision: "r1" }]]));
  });

  it("edits a router and saves the new threshold", async () => {
    const { user, server } = await openRouters();
    await user.click(within(row("handwriting")).getByRole("button", { name: "Edit handwriting" }));
    const form = within(row("handwriting")).getByRole("form", { name: "Edit handwriting" });
    const threshold = within(form).getByLabelText("Threshold");
    await user.clear(threshold);
    await user.type(threshold, "0.2");
    await user.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(puts(server)).toEqual([["/v1/settings/document-routers/handwriting", { entry: { ...{ model: "clef-local", question: HANDWRITING.question, images: true, max_chars: 2000, send_off_machine: false }, threshold: 0.2 }, revision: "r1" }]]));
  });

  it("refuses the name none, which means no router", async () => {
    const { card, user } = await openRouters();
    await user.click(within(card).getByRole("button", { name: "New from template: Text matches the page image" }));
    const form = within(card).getByRole("form", { name: "New router" });
    await user.type(within(form).getByLabelText("Name"), "pages");
    expect(within(form).getByRole("button", { name: "Save" })).toBeEnabled();
    await user.clear(within(form).getByLabelText("Name"));
    await user.type(within(form).getByLabelText("Name"), "none");
    expect(form).toHaveTextContent('The name "none" means no router.');
    expect(within(form).getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("keeps Save off while the threshold is outside 0 to 1", async () => {
    const { user } = await openRouters();
    await user.click(within(row("handwriting")).getByRole("button", { name: "Edit handwriting" }));
    const form = within(row("handwriting")).getByRole("form", { name: "Edit handwriting" });
    const threshold = within(form).getByLabelText("Threshold");
    await user.clear(threshold);
    await user.type(threshold, "1.5");
    expect(within(form).getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("renames a router", async () => {
    const { user, server } = await openRouters({ "POST /v1/settings/document-routers/hosted-check/rename": () => documentRouters([HANDWRITING, { ...HOSTED, name: "remote" }]) });
    await user.click(within(row("hosted-check")).getByRole("button", { name: "Rename hosted-check" }));
    const name = within(row("hosted-check")).getByLabelText("New name");
    await user.clear(name);
    await user.type(name, "remote");
    await user.click(within(row("hosted-check")).getByRole("button", { name: "Save name" }));
    await waitFor(() => expect(server.find("POST", "/v1/settings/document-routers/hosted-check/rename").map((call) => call.body)).toEqual([{ new_name: "remote", revision: "r1" }]));
    expect(await screen.findByRole("listitem", { name: "remote" })).toBeInTheDocument();
  });

  it("names the profile when the delete of a router in use is refused", async () => {
    const refused = { status: "error", message: "The saved profile Scanned theses names this router. Change it first.", reason: "in-use" };
    const { user } = await openRouters({ "DELETE /v1/settings/document-routers/handwriting": () => json(refused, 409) });
    await user.click(within(row("handwriting")).getByRole("button", { name: "Delete handwriting" }));
    expect(await within(row("handwriting")).findByRole("alert")).toHaveTextContent("The saved profile Scanned theses names this router.");
  });

  it("deletes an unused router", async () => {
    const { user, server } = await openRouters({ "DELETE /v1/settings/document-routers/hosted-check": () => documentRouters([HANDWRITING]) });
    await user.click(within(row("hosted-check")).getByRole("button", { name: "Delete hosted-check" }));
    await waitFor(() => expect(screen.queryByRole("listitem", { name: "hosted-check" })).toBeNull());
    expect(server.find("DELETE", "/v1/settings/document-routers/hosted-check").map((call) => call.body)).toEqual([{ revision: "r1" }]);
  });
});
