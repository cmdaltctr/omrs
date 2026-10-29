import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { LlamacppServerStatus } from "../api/llamacppServer";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { choiceStatus, SERVER_MANAGED, settingsServer } from "./test/fixtures";

const NOTE = "omrs starts and stops only this server. It never touches a server you started yourself.";

const PROGRAM_RULE = "The program must be the absolute path of an executable file named llama-server, not a script or a program in a hidden folder.";

/** A session that holds the `credentials` scope, which the program path needs. */
const WITH_CREDENTIALS = { "GET /v1/session": () => ({ status: "ok", kind: "session", scopes: ["credentials", "files", "graph", "read", "run"], workspace: "/home/u/.omrs/workspace" }) };

const SHARED = "Classification goes to OMRS's own Chat server, which loads only the Chat model. The Text model is not used. Set a Classification address, for example the Llama app, to keep them apart.";

/** A status with OMRS's own server chosen and Chat on llama.cpp; the panel shows only for this choice. */
function serverStatus(change: Parameters<typeof choiceStatus>[1] = {}, saved: Parameters<typeof choiceStatus>[2] = {}) {
  return choiceStatus("managed", { chat_model: SERVER_MANAGED.chat_model, ...change }, saved);
}

async function open(handlers = {}) {
  const server = settingsServer({ ...WITH_CREDENTIALS, "GET /v1/llamacpp/server": () => SERVER_MANAGED, ...handlers });
  startApp("#/settings/providers", server);
  await screen.findByRole("heading", { level: 3, name: "llama.cpp" });
  const panel = () => screen.getByRole("group", { name: "Local server" });
  await screen.findByRole("group", { name: "Local server" });
  return { server, user: userEvent.setup(), panel };
}

const RUNNING = serverStatus({ state: "running", pid_running: true, running_with: { context_window: 16384, model_kind: "file" } });

describe("Local server block on the llama.cpp card", () => {
  it("shows the note, three setting rows, the Chat model row and a Stopped status with Start enabled and Stop disabled", async () => {
    const { panel } = await open();
    expect(panel()).toHaveTextContent(NOTE);
    for (const label of ["Program path", "Context window (tokens)", "Idle sleep (seconds)"]) {
      expect(within(panel()).getByRole("button", { name: `Edit ${label}` })).toBeInTheDocument();
    }
    expect(within(panel()).queryByRole("textbox")).toBeNull();
    expect(within(panel()).getByText("16384")).toBeInTheDocument();
    expect(within(panel()).getByText("300")).toBeInTheDocument();
    expect(within(panel()).getAllByText("Not set")).toHaveLength(1);
    expect(within(panel()).getAllByText("default")).toHaveLength(3);
    expect(within(panel()).getByRole("status")).toHaveTextContent("Stopped");
    expect(within(panel()).getByRole("button", { name: "Start" })).toBeEnabled();
    expect(within(panel()).getByRole("button", { name: "Stop" })).toBeDisabled();
    expect(within(panel()).getByRole("button", { name: "Restart" })).toBeDisabled();
  });

  it("states that the embedding server is not managed", async () => {
    const { panel } = await open();
    expect(panel()).toHaveTextContent(/embedding server is not managed/i);
  });

  it("offers no Model row to edit, and shows the Chat model read-only with a link to Settings > Chat", async () => {
    const { panel } = await open();
    expect(within(panel()).queryByRole("button", { name: "Edit Model" })).toBeNull();
    expect(within(panel()).queryByText("Model")).toBeNull();
    const row = within(panel()).getByText("Chat model").closest("[data-slot='card-inset']") as HTMLElement;
    expect(within(row).getByText("Qwen/Qwen3-4B-GGUF:Q4_K_M")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Change in Settings > Chat" })).toHaveAttribute("href", "#/settings/chat");
    expect(within(row).queryByRole("button")).toBeNull();
  });

  it("shows Not set in the Chat model row while Chat uses another provider", async () => {
    const { panel } = await open({ "GET /v1/llamacpp/server": () => serverStatus({ chat_model: { provider: "openrouter", model: "deepseek/deepseek-v4-flash-0731", usable: false } }) });
    const row = within(panel()).getByText("Chat model").closest("[data-slot='card-inset']") as HTMLElement;
    expect(within(row).getByText("Not set")).toBeInTheDocument();
    expect(row).not.toHaveTextContent("deepseek");
  });

  it("shows file values with the omrs.jsonc words and keeps them editable", async () => {
    const { panel } = await open({
      "GET /v1/llamacpp/server": () =>
        serverStatus({}, { binary: { value: "/opt/homebrew/bin/llama-server", source: "config-file" }, context_window: { value: 8192, source: "config-file" } }),
    });
    expect(within(panel()).getByText("/opt/homebrew/bin/llama-server")).toBeInTheDocument();
    expect(within(panel()).getAllByText("Saved in settings (omrs.jsonc)")).toHaveLength(2);
    expect(within(panel()).getByRole("button", { name: "Edit Program path" })).toBeInTheDocument();
  });

  it("opens the program path filled and saves it with the revision, then shows the source the server returns", async () => {
    const put: unknown[] = [];
    let saved = false;
    const { user, panel } = await open({
      "GET /v1/llamacpp/server": () => (saved ? serverStatus({}, { binary: { value: "/opt/llama/llama-server", source: "config-file" } }) : serverStatus({})),
      "PUT /v1/llamacpp/server": (body: unknown) => {
        put.push(body);
        saved = true;
        return { ...serverStatus({}, { binary: { value: "/opt/llama/llama-server", source: "config-file" } }), revision: "r2" };
      },
    });
    await user.click(within(panel()).getByRole("button", { name: "Edit Program path" }));
    const input = within(panel()).getByRole("textbox", { name: "Program path" });
    expect(input).toHaveValue("");
    await user.type(input, "/opt/llama/llama-server");
    await user.click(within(panel()).getByRole("button", { name: "Save" }));
    expect(put).toEqual([{ binary: "/opt/llama/llama-server", revision: "r1" }]);
    expect(await within(panel()).findByText("/opt/llama/llama-server")).toBeInTheDocument();
    expect(within(panel()).getByText("Saved in settings (omrs.jsonc)")).toBeInTheDocument();
    expect(within(panel()).queryByRole("textbox")).toBeNull();
  });

  it("opens an edit filled with the value in force", async () => {
    const { user, panel } = await open({
      "GET /v1/llamacpp/server": () => serverStatus({}, { binary: { value: "/opt/homebrew/bin/llama-server", source: "config-file" } }),
    });
    await user.click(within(panel()).getByRole("button", { name: "Edit Program path" }));
    expect(within(panel()).getByRole("textbox", { name: "Program path" })).toHaveValue("/opt/homebrew/bin/llama-server");
  });

  it("saves the program and the window as separate changes", async () => {
    const put: unknown[] = [];
    const { user, panel } = await open({
      "PUT /v1/llamacpp/server": (body: unknown) => {
        put.push(body);
        return serverStatus({});
      },
    });
    await user.click(within(panel()).getByRole("button", { name: "Edit Program path" }));
    await user.type(within(panel()).getByRole("textbox", { name: "Program path" }), "/opt/homebrew/bin/llama-server");
    await user.click(within(panel()).getByRole("button", { name: "Save" }));
    await user.click(within(panel()).getByRole("button", { name: "Edit Context window (tokens)" }));
    const window = within(panel()).getByRole("spinbutton", { name: "Context window (tokens)" });
    await user.clear(window);
    await user.type(window, "8192");
    await user.click(within(panel()).getByRole("button", { name: "Save" }));
    expect(put).toEqual([
      { binary: "/opt/homebrew/bin/llama-server", revision: "r1" },
      { context_window: 8192, revision: "r1" },
    ]);
  });

  it("saves the idle sleep in seconds and says what sleep does", async () => {
    const put: unknown[] = [];
    const { user, panel } = await open({
      "PUT /v1/llamacpp/server": (body: unknown) => {
        put.push(body);
        return serverStatus({});
      },
    });
    expect(panel()).toHaveTextContent(/frees the model after this many idle seconds/i);
    expect(panel()).toHaveTextContent(/0 turns sleep off/i);
    await user.click(within(panel()).getByRole("button", { name: "Edit Idle sleep (seconds)" }));
    const sleep = within(panel()).getByRole("spinbutton", { name: "Idle sleep (seconds)" });
    expect(sleep).toHaveValue(300);
    await user.clear(sleep);
    await user.type(sleep, "0");
    await user.click(within(panel()).getByRole("button", { name: "Save" }));
    expect(put).toEqual([{ idle_sleep: 0, revision: "r1" }]);
  });

  it("returns a file value to the default with null", async () => {
    const put: unknown[] = [];
    const { user, panel } = await open({
      "GET /v1/llamacpp/server": () => serverStatus({}, { context_window: { value: 8192, source: "config-file" } }),
      "PUT /v1/llamacpp/server": (body: unknown) => {
        put.push(body);
        return serverStatus({});
      },
    });
    await user.click(within(panel()).getByRole("button", { name: "Edit Context window (tokens)" }));
    await user.click(within(panel()).getByRole("button", { name: "Use default" }));
    expect(put).toEqual([{ context_window: null, revision: "r1" }]);
  });

  it.each([
    ["env", "Set in the environment. Change it there."],
    ["dotenv", "Set in .env. Change it there."],
  ] as const)("shows a value set by %s as read-only and says where", async (source, words) => {
    const { panel } = await open({
      "GET /v1/llamacpp/server": () =>
        serverStatus({}, { binary: { value: "/opt/homebrew/bin/llama-server", source, locked: true, lock_reason: "Remove LLAMACPP_SERVER_BINARY from the environment or .env to edit it here." } }),
    });
    expect(panel()).toHaveTextContent(words);
    expect(panel()).toHaveTextContent("LLAMACPP_SERVER_BINARY");
    expect(within(panel()).getByText("/opt/homebrew/bin/llama-server")).toBeInTheDocument();
    expect(within(panel()).queryByRole("button", { name: "Edit Program path" })).toBeNull();
  });

  it("makes the program path read-only and keeps the Chat model row read-only when the session lacks the credentials scope", async () => {
    const { panel } = await open({ "GET /v1/session": () => ({ status: "ok", kind: "session", scopes: ["files", "graph", "read", "run"], workspace: null }) });
    await waitFor(() => expect(within(panel()).queryByRole("button", { name: "Edit Program path" })).toBeNull());
    expect(within(panel()).getAllByText(/credentials session is needed/i)).toHaveLength(1);
    expect(within(within(panel()).getByText("Chat model").closest("[data-slot='card-inset']") as HTMLElement).queryByRole("button")).toBeNull();
    expect(within(panel()).getByRole("button", { name: "Edit Context window (tokens)" })).toBeInTheDocument();
    expect(within(panel()).getByRole("button", { name: "Edit Idle sleep (seconds)" })).toBeInTheDocument();
  });

  it("shows the program rule message in place of a generic line when a save is refused", async () => {
    const { user, panel } = await open({ "PUT /v1/llamacpp/server": () => json({ status: "error", message: PROGRAM_RULE }, 400) });
    await user.click(within(panel()).getByRole("button", { name: "Edit Program path" }));
    await user.type(within(panel()).getByRole("textbox", { name: "Program path" }), "~/.llama-app/llama");
    await user.click(within(panel()).getByRole("button", { name: "Save" }));
    const alert = await within(panel()).findByRole("alert");
    expect(alert).toHaveTextContent(PROGRAM_RULE);
    expect(alert).not.toHaveTextContent("The local server could not complete that request.");
  });

  it("shows the range message of the server for a context window out of range", async () => {
    const message = "The context window must be a whole number from 2048 to 262144.";
    const { user, panel } = await open({ "PUT /v1/llamacpp/server": () => json({ status: "error", message }, 400) });
    await user.click(within(panel()).getByRole("button", { name: "Edit Context window (tokens)" }));
    const window = within(panel()).getByRole("spinbutton", { name: "Context window (tokens)" });
    await user.clear(window);
    await user.type(window, "1000");
    await user.click(within(panel()).getByRole("button", { name: "Save" }));
    expect(await within(panel()).findByRole("alert")).toHaveTextContent(message);
  });

  it("shows the conflict with a Reload action when omrs.jsonc changed on disk", async () => {
    const message = "omrs.jsonc changed on disk. Reload to see the new values.";
    const { user, panel, server } = await open({ "PUT /v1/llamacpp/server": () => json({ status: "error", message }, 409) });
    await user.click(within(panel()).getByRole("button", { name: "Edit Program path" }));
    await user.type(within(panel()).getByRole("textbox", { name: "Program path" }), "/x/llama-server");
    await user.click(within(panel()).getByRole("button", { name: "Save" }));
    expect(await within(panel()).findByRole("alert")).toHaveTextContent(message);
    const reads = server.find("GET", "/v1/llamacpp/server").length;
    await user.click(within(panel()).getByRole("button", { name: "Reload" }));
    await waitFor(() => expect(server.find("GET", "/v1/llamacpp/server").length).toBe(reads + 1));
  });

  it("starts the server and shows Starting", async () => {
    let started = false;
    const { user, panel, server } = await open({
      "GET /v1/llamacpp/server": () => (started ? serverStatus({ state: "starting", pid_running: true }) : serverStatus({})),
      "POST /v1/llamacpp/server/start": () => {
        started = true;
        return serverStatus({ state: "starting", pid_running: true });
      },
    });
    await user.click(within(panel()).getByRole("button", { name: "Start" }));
    await waitFor(() => expect(within(panel()).getByRole("status")).toHaveTextContent("Starting"));
    expect(server.find("POST", "/v1/llamacpp/server/start")).toHaveLength(1);
    expect(within(panel()).getByRole("button", { name: "Stop" })).toBeEnabled();
    expect(within(panel()).getByRole("button", { name: "Start" })).toBeDisabled();
  });

  it("shows Running with Start disabled, Stop and Restart enabled, and no pending note", async () => {
    const { panel } = await open({ "GET /v1/llamacpp/server": () => RUNNING });
    expect(within(panel()).getByRole("status")).toHaveTextContent("Running");
    expect(within(panel()).getByRole("button", { name: "Stop" })).toBeEnabled();
    expect(within(panel()).getByRole("button", { name: "Restart" })).toBeEnabled();
    expect(within(panel()).getByRole("button", { name: "Start" })).toBeDisabled();
    expect(panel()).not.toHaveTextContent("Restart to apply");
  });

  it("keeps the server running and says Restart to apply when the saved values differ from the running ones", async () => {
    let saved = false;
    const { user, panel } = await open({
      "GET /v1/llamacpp/server": () => ({ ...RUNNING, pending_restart: saved, ...(saved ? { saved: serverStatus({}, { context_window: { value: 8192, source: "config-file" } }).saved } : {}) }),
      "PUT /v1/llamacpp/server": () => {
        saved = true;
        return { ...RUNNING, pending_restart: true, saved: serverStatus({}, { context_window: { value: 8192, source: "config-file" } }).saved };
      },
    });
    await user.click(within(panel()).getByRole("button", { name: "Edit Context window (tokens)" }));
    const window = within(panel()).getByRole("spinbutton", { name: "Context window (tokens)" });
    await user.clear(window);
    await user.type(window, "8192");
    await user.click(within(panel()).getByRole("button", { name: "Save" }));
    expect(await within(panel()).findByText("Restart to apply")).toBeInTheDocument();
    expect(within(panel()).getByRole("status")).toHaveTextContent("Running");
  });

  it("stops and restarts through POST", async () => {
    const { user, panel, server } = await open({
      "GET /v1/llamacpp/server": () => RUNNING,
      "POST /v1/llamacpp/server/stop": () => serverStatus({}),
      "POST /v1/llamacpp/server/restart": () => RUNNING,
    });
    await user.click(within(panel()).getByRole("button", { name: "Restart" }));
    await waitFor(() => expect(server.find("POST", "/v1/llamacpp/server/restart")).toHaveLength(1));
    await user.click(within(panel()).getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(server.find("POST", "/v1/llamacpp/server/stop")).toHaveLength(1));
  });

  it.each([
    ["not-configured", "Set the program path first."],
    ["binary-invalid", "The program path is not a runnable file named llama-server."],
    ["model-invalid", "The Chat model is not an existing .gguf file or a Hugging Face id."],
    ["not-loopback", "The chat address is not on this machine, so omrs will not start a server for it."],
    ["port-in-use", "Another program already uses the chat port. omrs did not touch it."],
    ["timeout", "The server did not become ready in time and was stopped."],
  ] as const)("shows a friendly sentence for %s", async (reason, sentence) => {
    const { panel } = await open({ "GET /v1/llamacpp/server": () => serverStatus({ state: "failed", reason }) });
    const status = within(panel()).getByRole("status");
    expect(status).toHaveTextContent("Failed");
    expect(status).toHaveTextContent(sentence);
    expect(within(panel()).getByRole("button", { name: "Start" })).toBeEnabled();
  });

  it("sends the user to Settings > Chat when the program is set but Chat has no llama.cpp model", async () => {
    const { panel } = await open({
      "GET /v1/llamacpp/server": () =>
        serverStatus({ state: "failed", reason: "not-configured", chat_model: { provider: "openrouter", model: "x/y", usable: false } }, { binary: { value: "/opt/llama/llama-server", source: "config-file" } }),
    });
    expect(within(panel()).getByRole("status")).toHaveTextContent("Failed: Choose llama.cpp and a Chat model in Settings > Chat first.");
  });

  it("shows one plain line when Start is refused because the Chat server is the user's own", async () => {
    const { user, panel } = await open({
      "POST /v1/llamacpp/server/start": () => json({ status: "error", message: "The Chat server choice is external.", reason: "external-server" }, 409),
    });
    await user.click(within(panel()).getByRole("button", { name: "Start" }));
    expect(await within(panel()).findByRole("alert")).toHaveTextContent(/^OMRS does not start a server while the Chat server is the Llama app or another server you run\.$/);
  });

  it("warns in the panel and in the Classification block when classification shares OMRS's own Chat server", async () => {
    const { panel } = await open({ "GET /v1/llamacpp/server": () => serverStatus({ shared_with_classification: true }) });
    expect(within(panel()).getByText(SHARED)).toBeInTheDocument();
    const classification = within(screen.getByRole("region", { name: "llama.cpp" })).getByRole("group", { name: "Classification (metadata)" });
    expect(within(classification).getByText(SHARED)).toBeInTheDocument();
  });

  it("does not warn when classification has its own address", async () => {
    const { panel } = await open();
    expect(screen.queryByText(SHARED)).toBeNull();
    expect(panel()).not.toHaveTextContent("The Text model is not used.");
  });

  it("shows Set the program path first after Start when nothing is set", async () => {
    let started = false;
    const { user, panel } = await open({
      "GET /v1/llamacpp/server": () => serverStatus(started ? { state: "failed", reason: "not-configured" } : {}),
      "POST /v1/llamacpp/server/start": () => {
        started = true;
        return serverStatus({ state: "failed", reason: "not-configured" });
      },
    });
    await user.click(within(panel()).getByRole("button", { name: "Start" }));
    await waitFor(() => expect(within(panel()).getByRole("status")).toHaveTextContent("Failed: Set the program path first."));
  });

  it("shows the exit code for exited", async () => {
    const { panel } = await open({ "GET /v1/llamacpp/server": () => serverStatus({ state: "failed", reason: "exited", exit_code: 3 }) });
    expect(within(panel()).getByRole("status")).toHaveTextContent("The server stopped by itself with exit code 3. See llamacpp-server.log in the workspace folder.");
  });

  it("never puts raw log or process text in the page", async () => {
    const hostile = { ...serverStatus({ state: "failed", reason: "exited", exit_code: 1 }), log: "SECRET-CHILD-TEXT", output: "SECRET-CHILD-TEXT" } as LlamacppServerStatus;
    await open({ "GET /v1/llamacpp/server": () => hostile });
    expect(document.body.textContent).not.toContain("SECRET-CHILD-TEXT");
  });
});
