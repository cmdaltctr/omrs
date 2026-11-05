import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { DecisionModelEntry } from "../api/routerMaps";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { settingsServer } from "./test/fixtures";
import { CLEF_LOCAL, decisionModels, JEV, OLLAMA_ENTRY } from "./test/routerFixtures";

const RUNNING = { id: "decision-clef-local", role: "decision", mode: "managed", state: "running", reason: null, reason_text: null, memory_bytes: null, clients: "none", used_by: [], address: "127.0.0.1:8090", files_checked: true };

async function openCard(handlers = {}) {
  const server = settingsServer({ "GET /v1/settings/decision-models": () => decisionModels([CLEF_LOCAL, JEV, OLLAMA_ENTRY]), ...handlers });
  startApp("#/settings/providers", server);
  const card = await screen.findByRole("region", { name: "Decision models" });
  await within(card).findByRole("listitem", { name: "clef-local" });
  return { server, card, user: userEvent.setup() };
}

const entry = (name: string) => screen.getByRole("listitem", { name });

describe("Decision models card", () => {
  it("lists each entry with kind, model, image flag, place and key state, and never a key", async () => {
    await openCard();
    const local = entry("clef-local");
    expect(local).toHaveTextContent("llama.cpp");
    expect(local).toHaveTextContent("clef-flash");
    expect(local).toHaveTextContent("Images");
    expect(local).toHaveTextContent("Local");
    expect(local).toHaveTextContent("Key: not needed");
    expect(local).toHaveTextContent("Not tested");
    expect(local).toHaveTextContent("Used by router: handwriting");
    const jev = entry("jev");
    expect(jev).toHaveTextContent("Hosted");
    expect(jev).toHaveTextContent("Key: set");
    expect(entry("ollama-clef")).toHaveTextContent("Key: missing");
  });

  it("labels a kind with no recorded live request Not yet tested", async () => {
    await openCard();
    expect(within(entry("ollama-clef")).getByText("Not yet tested")).toBeInTheDocument();
    expect(within(entry("jev")).queryByText("Not yet tested")).toBeNull();
  });

  it("shows the managed files and the runtime state when the runtime is listed", async () => {
    await openCard({ "GET /v1/runtimes": () => ({ status: "ok", runtimes: [RUNNING] }) });
    const local = entry("clef-local");
    expect(local).toHaveTextContent("Model file: ~/models/clef-flash-Q8_0.gguf");
    expect(local).toHaveTextContent("Projector file: ~/models/mmproj-clef-flash.gguf");
    expect(await within(local).findByText("Runtime: Running")).toBeInTheDocument();
    expect(entry("jev")).not.toHaveTextContent("Model file:");
  });

  it("adds a managed local entry and saves it with the revision", async () => {
    const { card, user, server } = await openCard({ "PUT /v1/settings/decision-models/:name": () => decisionModels([CLEF_LOCAL, JEV]) });
    await user.click(within(card).getByRole("button", { name: "Add decision model" }));
    const form = within(card).getByRole("form", { name: "New decision model" });
    await user.click(within(form).getByRole("combobox", { name: "Kind" }));
    const kinds = screen.getAllByRole("option").map((option) => option.textContent);
    expect(kinds).toEqual(["Cloudflare Workers AI (Not yet tested)", "llama.cpp", "Ollama (Not yet tested)", "TypeSafe"]);
    await user.click(screen.getByRole("option", { name: "llama.cpp" }));
    await user.type(within(form).getByLabelText("Name"), "clef-new");
    await user.type(within(form).getByLabelText("Model"), "clef-flash");
    await user.click(within(form).getByRole("checkbox", { name: "Sees page images" }));
    await user.click(within(form).getByRole("combobox", { name: "Server" }));
    await user.click(screen.getByRole("option", { name: "Managed by OMRS" }));
    await user.type(within(form).getByLabelText("Model file"), "~/m/clef-Q8_0.gguf");
    await user.type(within(form).getByLabelText("Projector file"), "~/m/mmproj.gguf");
    await user.click(within(form).getByRole("button", { name: "Save" }));
    const expected: DecisionModelEntry = { kind: "llamacpp", address: "http://127.0.0.1:8090", model: "clef-flash", images: true, server: "managed", model_file: "~/m/clef-Q8_0.gguf", projector_file: "~/m/mmproj.gguf" };
    await waitFor(() => expect(server.find("PUT", "/v1/settings/decision-models/").map((call) => [call.path, call.body])).toEqual([["/v1/settings/decision-models/clef-new", { entry: expected, revision: "r1" }]]));
  });

  it("refuses a literal key and sends a reference", async () => {
    const { card, user, server } = await openCard({ "PUT /v1/settings/decision-models/:name": () => decisionModels() });
    await user.click(within(entry("jev")).getByRole("button", { name: "Edit jev" }));
    const form = within(card).getByRole("form", { name: "Edit jev" });
    expect(form).toHaveTextContent("The saved reference is not shown. Leave the field blank to keep it.");
    const key = within(form).getByLabelText("Key reference");
    await user.type(key, "sk-live-123");
    expect(form).toHaveTextContent("Type a reference only");
    expect(within(form).getByRole("button", { name: "Save" })).toBeDisabled();
    await user.clear(key);
    await user.type(key, "env://TYPESAFE_API_KEY");
    await user.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/decision-models/jev").map((call) => call.body)).toEqual([{ entry: { kind: "typesafe", address: "https://api.typesafe.ai", model: "jev", images: true, key: "env://TYPESAFE_API_KEY" }, revision: "r1" }]));
    expect(document.body).not.toHaveTextContent("sk-live-123");
  });

  it("tests an entry and shows the result, quantisation, projector and build lines", async () => {
    const result = { status: "ok", name: "clef-local", result: "ok", quantisation: "Quantisation Q8_0", projector: "Projector smoke test passed", build: "llama.cpp build b11510" };
    const { user, server } = await openCard({ "POST /v1/settings/decision-models/clef-local/test": () => result });
    await user.click(within(entry("clef-local")).getByRole("button", { name: "Test clef-local" }));
    const local = entry("clef-local");
    expect(await within(local).findByText("Working")).toBeInTheDocument();
    expect(local).toHaveTextContent("Quantisation Q8_0");
    expect(local).toHaveTextContent("Projector smoke test passed");
    expect(local).toHaveTextContent("llama.cpp build b11510");
    expect(within(local).queryByText("Not tested")).toBeNull();
    expect(server.find("POST", "/v1/settings/decision-models/clef-local/test")).toHaveLength(1);
  });

  it("shows a failed test as its reason", async () => {
    const result = { status: "ok", name: "clef-local", result: "quantisation-refused", quantisation: "Quantisation Q4_K_M", projector: null, build: null };
    const { user } = await openCard({ "POST /v1/settings/decision-models/clef-local/test": () => result });
    await user.click(within(entry("clef-local")).getByRole("button", { name: "Test clef-local" }));
    const local = entry("clef-local");
    expect(await within(local).findByText("Not working")).toBeInTheDocument();
    expect(local).toHaveTextContent("The model file is below 8-bit, so it is refused.");
    expect(local).toHaveTextContent("Quantisation Q4_K_M");
  });

  it("names the router when the removal of an entry in use is refused", async () => {
    const refused = { status: "error", message: "The router handwriting names this decision model. Change it first.", reason: "in-use" };
    const { user, server } = await openCard({ "DELETE /v1/settings/decision-models/clef-local": () => json(refused, 409) });
    await user.click(within(entry("clef-local")).getByRole("button", { name: "Remove clef-local" }));
    const alert = await within(entry("clef-local")).findByRole("alert");
    expect(alert).toHaveTextContent("The router handwriting names this decision model.");
    expect(server.find("DELETE", "/v1/settings/decision-models/clef-local").map((call) => call.body)).toEqual([{ revision: "r1" }]);
  });

  it("removes an unused entry", async () => {
    const { user } = await openCard({ "DELETE /v1/settings/decision-models/jev": () => decisionModels([CLEF_LOCAL, OLLAMA_ENTRY]) });
    await user.click(within(entry("jev")).getByRole("button", { name: "Remove jev" }));
    await waitFor(() => expect(screen.queryByRole("listitem", { name: "jev" })).toBeNull());
  });
});
