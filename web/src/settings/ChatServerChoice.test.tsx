import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { LlamacppServerStatus } from "../api/llamacppServer";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { choiceStatus, SERVER_STOPPED, settingsServer } from "./test/fixtures";

// The exact callouts of design D9. A changed word in chatServerWords.ts must fail these tests.
const EXTERNAL =
  "Context size: set ctx-size for this model in the Llama app's models.user.ini, then relaunch the Llama app. The relaunch pauses embeddings and anything else on that port. OMRS does not edit this file or restart the app.";
const MANAGED =
  "OMRS's own server needs a program named exactly llama-server. The Llama app's own llama program does not qualify. Install one with Homebrew: brew install llama.cpp. Then set the program path, for example /opt/homebrew/bin/llama-server.";
const STOP_FIRST = "Stop OMRS's own server first, then choose another server.";

const WITH_CREDENTIALS = { "GET /v1/session": () => ({ status: "ok", kind: "session", scopes: ["credentials", "files", "graph", "read", "run"], workspace: "/home/u/.omrs/workspace" }) };

async function open(handlers = {}) {
  const server = settingsServer(handlers);
  startApp("#/settings/providers", server);
  await screen.findByRole("heading", { level: 3, name: "llama.cpp" });
  await within(chat()).findByRole("combobox", { name: "Who runs the Chat server" });
  return { server, user: userEvent.setup() };
}

function chat() {
  return within(screen.getByRole("region", { name: "llama.cpp" })).getByRole("group", { name: "Chat" });
}

function choice() {
  return within(chat()).getByRole("combobox", { name: "Who runs the Chat server" });
}

describe("Who runs the Chat server", () => {
  it("offers the two choices, with the user's own server as the default and its source", async () => {
    const { user } = await open(WITH_CREDENTIALS);
    expect(choice()).toHaveTextContent("The Llama app or another server you run");
    expect(choice().closest("[data-slot='card-inset']")).toHaveTextContent("default");
    await waitFor(() => expect(choice()).toBeEnabled());
    await user.click(choice());
    expect(await screen.findByRole("option", { name: "The Llama app or another server you run" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "OMRS's own llama-server" })).toBeInTheDocument();
  });

  it("shows the Llama app callout and no context window row or Local server panel for the user's own server", async () => {
    await open();
    expect(within(chat()).getByText(EXTERNAL)).toBeInTheDocument();
    expect(within(chat()).queryByText(MANAGED)).toBeNull();
    expect(within(chat()).queryByText("Context window (tokens)")).toBeNull();
    expect(within(chat()).queryByRole("group", { name: "Local server" })).toBeNull();
    expect(within(chat()).queryByRole("button", { name: "Start" })).toBeNull();
  });

  it("shows the OMRS server callout for OMRS's own server, and again above the program path row while no path is set", async () => {
    await open({ "GET /v1/llamacpp/server": () => choiceStatus("managed") });
    expect(choice()).toHaveTextContent("OMRS's own llama-server");
    expect(within(chat()).queryByText(EXTERNAL)).toBeNull();
    expect(within(chat()).getAllByText(MANAGED)).toHaveLength(2);
    const panel = await within(chat()).findByRole("group", { name: "Local server" });
    const callout = within(panel).getByText(MANAGED);
    const program = within(panel).getByText("Program path");
    expect(callout.compareDocumentPosition(program) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows the OMRS server callout once when the program path is set", async () => {
    await open({ "GET /v1/llamacpp/server": () => choiceStatus("managed", {}, { binary: { value: "/opt/homebrew/bin/llama-server", source: "config-file" } }) });
    await within(chat()).findByRole("group", { name: "Local server" });
    expect(within(chat()).getAllByText(MANAGED)).toHaveLength(1);
  });

  it("shows the OMRS server callout above the program path again when the program fails the rule", async () => {
    const failed = choiceStatus("managed", { state: "failed", reason: "binary-invalid" }, { binary: { value: "/opt/llama-app/llama", source: "config-file" } });
    await open({ "GET /v1/llamacpp/server": () => failed });
    const panel = await within(chat()).findByRole("group", { name: "Local server" });
    expect(within(panel).getByText(MANAGED)).toBeInTheDocument();
  });

  it("saves the choice with PUT chat_server and the revision, then shows the Local server panel", async () => {
    let status: LlamacppServerStatus = SERVER_STOPPED;
    const puts: unknown[] = [];
    const { user } = await open({
      ...WITH_CREDENTIALS,
      "GET /v1/llamacpp/server": () => status,
      "PUT /v1/llamacpp/server": (body: unknown) => {
        puts.push(body);
        return (status = { ...choiceStatus("managed"), revision: "r2" });
      },
    });
    await waitFor(() => expect(choice()).toBeEnabled());
    await user.click(choice());
    await user.click(await screen.findByRole("option", { name: "OMRS's own llama-server" }));
    expect(puts).toEqual([{ chat_server: "managed", revision: "r1" }]);
    expect(await within(chat()).findByRole("group", { name: "Local server" })).toBeInTheDocument();
    expect(choice().closest("[data-slot='card-inset']")).toHaveTextContent("Saved in settings (omrs.jsonc)");
  });

  it("makes a locked choice read-only and names the variable and .env", async () => {
    const locked = serverChoiceLocked();
    await open({ ...WITH_CREDENTIALS, "GET /v1/llamacpp/server": () => locked });
    const row = choice().closest("[data-slot='card-inset']") as HTMLElement;
    expect(choice()).toBeDisabled();
    expect(row).toHaveTextContent("Set in .env. Change it there.");
    expect(row).toHaveTextContent("LLAMACPP_CHAT_SERVER");
  });

  it("makes the choice read-only and says why when the session lacks the credentials scope", async () => {
    const { server } = await open();
    const row = choice().closest("[data-slot='card-inset']") as HTMLElement;
    await waitFor(() => expect(row).toHaveTextContent("A credentials session is needed to change this."));
    expect(choice()).toBeDisabled();
    expect(server.find("PUT", "/v1/llamacpp/server")).toHaveLength(0);
  });

  it("keeps OMRS's own server and shows one plain line when the server runs and the user picks their own server", async () => {
    const running = choiceStatus("managed", { state: "running", pid_running: true, running_with: { context_window: 16384, model_kind: "hf" } });
    const { user } = await open({
      ...WITH_CREDENTIALS,
      "GET /v1/llamacpp/server": () => running,
      "PUT /v1/llamacpp/server": () => json({ status: "error", message: "The server runs. Stop it first.", reason: "server-running" }, 409),
    });
    await waitFor(() => expect(choice()).toBeEnabled());
    await user.click(choice());
    await user.click(await screen.findByRole("option", { name: "The Llama app or another server you run" }));
    const alert = await within(chat()).findByRole("alert");
    expect(alert).toHaveTextContent(new RegExp(`^${STOP_FIRST}$`));
    await waitFor(() => expect(choice()).toHaveTextContent("OMRS's own llama-server"));
    expect(within(chat()).getByRole("group", { name: "Local server" })).toBeInTheDocument();
  });
});

function serverChoiceLocked(): LlamacppServerStatus {
  return choiceStatus("external", {}, { chat_server: { value: "external", source: "dotenv", locked: true, lock_reason: "Remove LLAMACPP_CHAT_SERVER from .env to edit it here." } });
}
