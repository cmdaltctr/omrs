import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { RouterReason } from "../api/llamacppRouter";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { ROUTER_EXTERNAL, ROUTER_RUNNING, ROUTER_STOPPED, routerStatus, settingsServer, WITH_CREDENTIALS } from "./test/fixtures";

const EXTERNAL_NOTE = "External server: OMRS does not check model files or presets";
// A program in force keeps the panel closed unless a problem opens it.
const HAS_PROGRAM = { path: "/opt/omrs/llama-server", source: "provisioned" } as const;
const NOTE_PATTERN = /External server: OMRS does not check model files or presets/;

async function open(handlers = {}) {
  const server = settingsServer({ ...WITH_CREDENTIALS, ...handlers });
  startApp("#/settings/providers", server);
  await screen.findByRole("heading", { level: 3, name: "llama.cpp" });
  const panel = () => within(screen.getByRole("region", { name: "llama.cpp" })).getByRole("group", { name: "Router" });
  await waitFor(() => expect(within(panel()).getByRole("status")).toBeInTheDocument());
  return { server, user: userEvent.setup(), panel };
}

describe("The llama.cpp card shows one Router panel", () => {
  it("Managed and stopped: Start is enabled, Stop and Restart are disabled", async () => {
    const { panel } = await open();
    expect(within(panel()).getByRole("status")).toHaveTextContent("Stopped");
    await waitFor(() => expect(within(panel()).getByRole("button", { name: "Start" })).toBeEnabled());
    expect(within(panel()).getByRole("button", { name: "Stop" })).toBeDisabled();
    expect(within(panel()).getByRole("button", { name: "Restart" })).toBeDisabled();
  });

  it("Managed and running: Start is disabled, Stop and Restart are enabled", async () => {
    const { panel } = await open({ "GET /v1/llamacpp/router": () => ROUTER_RUNNING });
    await waitFor(() => expect(within(panel()).getByRole("status")).toHaveTextContent("Running"));
    expect(within(panel()).getByRole("button", { name: "Start" })).toBeDisabled();
    expect(within(panel()).getByRole("button", { name: "Stop" })).toBeEnabled();
    expect(within(panel()).getByRole("button", { name: "Restart" })).toBeEnabled();
  });

  it("External mode: shows the address and the note, and no Start, Stop or Restart", async () => {
    const { panel } = await open({ "GET /v1/llamacpp/router": () => ROUTER_EXTERNAL });
    await waitFor(() => expect(panel()).toHaveTextContent(EXTERNAL_NOTE));
    expect(within(panel()).getByText("http://127.0.0.1:9931/v1")).toBeInTheDocument();
    for (const name of ["Start", "Stop", "Restart"]) expect(within(panel()).queryByRole("button", { name })).toBeNull();
  });

  it("Restart to apply: shows beside Restart when the saved limits differ from the running router", async () => {
    const { panel } = await open({ "GET /v1/llamacpp/router": () => ({ ...ROUTER_RUNNING, pending_restart: true }) });
    expect(await within(panel()).findByText("Restart to apply")).toBeInTheDocument();
  });

  it("Restart to apply: is not shown when nothing differs", async () => {
    const { panel } = await open({ "GET /v1/llamacpp/router": () => ROUTER_RUNNING });
    await waitFor(() => expect(within(panel()).getByRole("status")).toHaveTextContent("Running"));
    expect(within(panel()).queryByText("Restart to apply")).toBeNull();
  });

  it("Locked address: shows a lock and names the variable, and offers no edit", async () => {
    const lock = "Remove LLAMACPP_ROUTER_URL from the environment or .env to edit it here.";
    const { panel } = await open({ "GET /v1/llamacpp/router": () => routerStatus({}, { router_url: { source: "env", locked: true, lock_reason: lock } }) });
    expect(await within(panel()).findByText(lock)).toBeInTheDocument();
    expect(within(panel()).getByLabelText("Locked")).toBeInTheDocument();
    expect(within(panel()).queryByRole("button", { name: "Edit Router address" })).toBeNull();
  });

  it("Mode and address rows: show OMRS runs llama.cpp selected and the default address on a fresh install", async () => {
    const { panel } = await open();
    expect(within(panel()).getByRole("combobox", { name: "Who runs llama.cpp" })).toHaveTextContent("OMRS runs llama.cpp");
    expect(within(panel()).getByText("http://127.0.0.1:8080/v1")).toBeInTheDocument();
    expect(within(panel()).getByRole("button", { name: "Edit Router address" })).toBeInTheDocument();
  });

  it("saves a new router address with the manage scope and shows the saved value", async () => {
    const put: unknown[] = [];
    const { panel, user } = await open({
      "PUT /v1/llamacpp/router": (body: unknown) => {
        put.push(body);
        return { ...routerStatus({}, { router_url: { value: "http://127.0.0.1:9000/v1", source: "config-file" } }), revision: "r2" };
      },
    });
    await user.click(within(panel()).getByRole("button", { name: "Edit Router address" }));
    const input = within(panel()).getByRole("textbox", { name: "Router address" });
    await user.clear(input);
    await user.type(input, "http://127.0.0.1:9000/v1");
    await user.click(within(panel()).getByRole("button", { name: "Save" }));
    expect(await within(panel()).findByText("http://127.0.0.1:9000/v1")).toBeInTheDocument();
    expect(put).toEqual([{ router_url: "http://127.0.0.1:9000/v1", revision: "r1" }]);
  });

  it("picks the other mode with one save", async () => {
    const put: unknown[] = [];
    const { panel, user } = await open({
      "PUT /v1/llamacpp/router": (body: unknown) => {
        put.push(body);
        return ROUTER_EXTERNAL;
      },
    });
    await user.click(within(panel()).getByRole("combobox", { name: "Who runs llama.cpp" }));
    await user.click(await screen.findByRole("option", { name: "Use this address" }));
    await waitFor(() => expect(put).toEqual([{ router_server: "external", revision: "r1" }]));
    expect(await within(panel()).findByText(NOTE_PATTERN)).toBeInTheDocument();
  });

  it("leaves the mode and the program read-only without the credentials scope", async () => {
    const manageOnly = { "GET /v1/session": () => ({ status: "ok", kind: "session", scopes: ["manage", "read"], workspace: null }) };
    const { panel } = await open(manageOnly);
    await waitFor(() => expect(within(panel()).getByRole("combobox", { name: "Who runs llama.cpp" })).toBeDisabled());
    expect(within(panel()).queryByRole("button", { name: "Edit Program path" })).toBeNull();
    expect(within(panel()).getByRole("button", { name: "Edit Router address" })).toBeInTheDocument();
  });

  const READ_ONLY = { "GET /v1/session": () => ({ status: "ok", kind: "session", scopes: ["read"], workspace: null }) };

  it("disables Start for a session without the manage scope", async () => {
    const { panel, server } = await open(READ_ONLY);
    await waitFor(() => expect(server.exact("GET", "/v1/session")).toHaveLength(1));
    expect(within(panel()).getByRole("button", { name: "Start" })).toBeDisabled();
  });

  it("disables Stop and Restart for a session without the manage scope", async () => {
    const { panel, server } = await open({ ...READ_ONLY, "GET /v1/llamacpp/router": () => ROUTER_RUNNING });
    await waitFor(() => expect(within(panel()).getByRole("status")).toHaveTextContent("Running"));
    await waitFor(() => expect(server.exact("GET", "/v1/session")).toHaveLength(1));
    for (const name of ["Stop", "Restart"]) expect(within(panel()).getByRole("button", { name })).toBeDisabled();
  });

  it("shows the program in force, and where to get one when there is none", async () => {
    const { panel } = await open();
    expect(panel()).toHaveTextContent("No program yet");
    expect(within(panel()).getByRole("link", { name: "Get llama.cpp" })).toHaveAttribute("href", "#/integrations/llamacpp");
  });

  it("names the provisioned build as the program in force", async () => {
    const { panel } = await open({ "GET /v1/llamacpp/router": () => ROUTER_RUNNING });
    await waitFor(() => expect(panel()).toHaveTextContent("/opt/omrs/llama-server (provisioned build)"));
  });

  it("lists each role that no list entry can serve as one plain line at the top, and opens the panel", async () => {
    const problems = [
      { role: "embeddings" as const, reason: "model-not-listed" as const, text: "The embeddings model is not in the list." },
      { role: "classification" as const, reason: "role-mismatch" as const, text: "An embedding entry cannot serve the classification role." },
    ];
    const { panel } = await open({ "GET /v1/llamacpp/router": () => routerStatus({ problems, program: HAS_PROGRAM }) });
    const lines = await within(panel()).findAllByTestId("router-problem");
    expect(lines).toHaveLength(2);
    expect(lines[0]).toHaveTextContent("The embeddings model is not in the list. Edit the list below or choose another model.");
    expect(lines[1]).toHaveTextContent("An embedding entry cannot serve the classification role. Edit the list below or choose another model.");
    expect(panel()).toHaveAttribute("open");
    // The lines come before the router rows.
    const text = panel().textContent ?? "";
    expect(text.indexOf("The embeddings model is not in the list.")).toBeLessThan(text.indexOf("Who runs llama.cpp"));
  });

  it("shows no problem line when the server sends an empty array", async () => {
    const { panel } = await open({ "GET /v1/llamacpp/router": () => routerStatus({ program: HAS_PROGRAM }) });
    await waitFor(() => expect(within(panel()).getByRole("status")).toHaveTextContent("Stopped"));
    expect(within(panel()).queryByTestId("router-problem")).toBeNull();
    expect(panel()).not.toHaveAttribute("open");
  });

  it("shows a failed router with one plain reason line", async () => {
    const failed = routerStatus({ state: "failed", reason: "port-in-use", reason_text: "Another program already uses port 8080. OMRS did not touch it." });
    const { panel } = await open({ "GET /v1/llamacpp/router": () => failed });
    await waitFor(() => expect(within(panel()).getByRole("status")).toHaveTextContent("Failed: Another program already uses port 8080. OMRS did not touch it."));
  });

  // Every word that `rules.REASONS` in the backend can put on a failed router. The page shows the server's own line.
  const ROUTER_REASONS: RouterReason[] = [
    "binary-invalid",
    "model-invalid",
    "not-loopback",
    "port-in-use",
    "exited",
    "timeout",
    "not-configured",
    "not-supported",
    "version-busy",
    "wrong-build",
    "file-changed",
    "bind-failed",
    "not-provisioned",
    "not-downloaded",
  ];

  it.each(ROUTER_REASONS)("shows the server line for the router reason %s", async (reason) => {
    const failed = routerStatus({ state: "failed", reason, reason_text: `The line for ${reason}.` });
    const { panel } = await open({ "GET /v1/llamacpp/router": () => failed });
    await waitFor(() => expect(within(panel()).getByRole("status")).toHaveTextContent(`Failed: The line for ${reason}.`));
  });

  it("starts the router and shows the state the server returned", async () => {
    const { panel, user, server } = await open({ "POST /v1/llamacpp/router/start": () => routerStatus({ state: "starting" }) });
    await user.click(within(panel()).getByRole("button", { name: "Start" }));
    await waitFor(() => expect(within(panel()).getByRole("status")).toHaveTextContent("Starting"));
    expect(server.find("POST", "/v1/llamacpp/router/start")).toHaveLength(1);
  });

  it("stops and restarts a running router", async () => {
    const { panel, user, server } = await open({
      "GET /v1/llamacpp/router": () => ROUTER_RUNNING,
      "POST /v1/llamacpp/router/stop": () => ROUTER_STOPPED,
      "POST /v1/llamacpp/router/restart": () => ROUTER_RUNNING,
    });
    await waitFor(() => expect(within(panel()).getByRole("button", { name: "Stop" })).toBeEnabled());
    await user.click(within(panel()).getByRole("button", { name: "Restart" }));
    await waitFor(() => expect(server.find("POST", "/v1/llamacpp/router/restart")).toHaveLength(1));
    await user.click(within(panel()).getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(server.find("POST", "/v1/llamacpp/router/stop")).toHaveLength(1));
  });

  it("says why a start is refused in external mode, with one plain line", async () => {
    const refused = json({ status: "error", message: "raw server text", reason: "external-server" }, 409);
    const { panel, user } = await open({ "POST /v1/llamacpp/router/start": () => refused });
    await user.click(within(panel()).getByRole("button", { name: "Start" }));
    const alert = await within(panel()).findByRole("alert");
    expect(alert).toHaveTextContent("OMRS does not start a router while the mode is Use this address.");
    expect(alert).not.toHaveTextContent("raw server text");
  });
});
