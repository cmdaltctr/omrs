import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Integration } from "../api/integrations";
import type { LlamacppBuild } from "../api/llamacppInstall";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { routerStatus } from "../settings/test/llamacppFixtures";
import { SESSION_READ_ONLY, SESSION_WITH_MANAGE } from "./test/modelRuntimeFixtures";

const ENTRY: Integration = {
  id: "llamacpp",
  name: "llama.cpp provider",
  purpose: "Local models through llama.cpp.",
  extra: "llamacpp",
  install_command: "uv sync --extra llamacpp",
  pip_command: null,
  availability: "available",
  installable: false,
  install_reason: "not-installable-here",
  packages: [],
  install_caution: null,
  base: true,
  uninstallable: false,
  uninstall_reason: "not-uninstallable-here",
  uninstall_setting: null,
  removes: [],
  keeps: [],
  lasting_uninstall_command: null,
  pending_restart: null,
  uninstall_profile: null,
};

const IDLE = { state: "idle", flavour: null, line: null, reason: null, message: null } as const;

const LINUX_CUDA: LlamacppBuild = { status: "ok", build: "b11941", detected: "cuda", choices: ["cpu", "cuda"], installed_path: null, job: IDLE };
const MACOS: LlamacppBuild = { status: "ok", build: "b11941", detected: "metal", choices: [], installed_path: null, job: IDLE };

function serve(build: LlamacppBuild, handlers: Parameters<typeof documentsServer>[0] = {}) {
  return documentsServer({
    "GET /v1/integrations": () => ({ status: "ok", install_type: "checkout", integrations: [ENTRY], tools: [] }),
    "GET /v1/session": () => SESSION_WITH_MANAGE,
    "GET /v1/llamacpp/router/install": () => build,
    ...handlers,
  });
}

async function card(server: ReturnType<typeof serve>) {
  startApp("#/integrations", server);
  const list = await screen.findByRole("list", { name: "Integrations" });
  const found = within(list).getAllByRole("listitem").find((entry) => within(entry).queryByRole("heading", { name: "llama.cpp provider" }));
  if (found === undefined) throw new Error("No llama.cpp card");
  await waitFor(() => expect(found).toHaveTextContent("llama.cpp build"));
  return found;
}

describe("The Integrations page provisions the pinned llama.cpp build", () => {
  it("Not provisioned: shows the pinned build, Not installed and the Get llama.cpp button", async () => {
    const entry = await card(serve(LINUX_CUDA));
    expect(entry).toHaveTextContent("llama.cpp build b11941");
    expect(entry).toHaveTextContent("Not installed");
    expect(await within(entry).findByRole("button", { name: "Get llama.cpp" })).toBeEnabled();
  });

  it("Detected flavour shown: CUDA 12.8 is the default and CPU is the other choice", async () => {
    const entry = await card(serve(LINUX_CUDA));
    const choice = within(entry).getByRole("radiogroup", { name: "Build to install" });
    expect(within(choice).getByRole("radio", { name: "CUDA 12.8 (detected)" })).toBeChecked();
    expect(within(choice).getByRole("radio", { name: "CPU" })).not.toBeChecked();
  });

  it("Flavour chosen before install: the request names cpu", async () => {
    const server = serve(LINUX_CUDA, { "POST /v1/llamacpp/router/install": () => ({ ...LINUX_CUDA, job: { ...IDLE, state: "running", flavour: "cpu", line: "Downloading llama-b11941-bin-ubuntu-x64.tar.gz" } }) });
    const user = userEvent.setup();
    const entry = await card(server);
    await user.click(within(entry).getByRole("radio", { name: "CPU" }));
    await user.click(await within(entry).findByRole("button", { name: "Get llama.cpp" }));
    await waitFor(() => expect(server.find("POST", "/v1/llamacpp/router/install")).toHaveLength(1));
    expect(server.find("POST", "/v1/llamacpp/router/install")[0]?.body).toEqual({ flavour: "cpu" });
    expect(await within(entry).findByText("Downloading llama-b11941-bin-ubuntu-x64.tar.gz")).toBeInTheDocument();
    expect(within(entry).getByRole("button", { name: "Get llama.cpp" })).toBeDisabled();
  });

  it("names the detected flavour in the request when the user picks nothing", async () => {
    const server = serve(LINUX_CUDA, { "POST /v1/llamacpp/router/install": () => LINUX_CUDA });
    const user = userEvent.setup();
    const entry = await card(server);
    await user.click(await within(entry).findByRole("button", { name: "Get llama.cpp" }));
    await waitFor(() => expect(server.find("POST", "/v1/llamacpp/router/install")).toHaveLength(1));
    expect(server.find("POST", "/v1/llamacpp/router/install")[0]?.body).toEqual({ flavour: "cuda" });
  });

  it("No choice on macOS: the card shows no flavour choice and sends no flavour", async () => {
    const server = serve(MACOS, { "POST /v1/llamacpp/router/install": () => MACOS });
    const user = userEvent.setup();
    const entry = await card(server);
    expect(within(entry).queryByRole("radiogroup")).toBeNull();
    expect(within(entry).queryByRole("radio")).toBeNull();
    await user.click(await within(entry).findByRole("button", { name: "Get llama.cpp" }));
    await waitFor(() => expect(server.find("POST", "/v1/llamacpp/router/install")).toHaveLength(1));
    expect(server.find("POST", "/v1/llamacpp/router/install")[0]?.body).toEqual({});
  });

  it("Hash failure shown: Failed with one reason line, and the binary is not shown as provisioned", async () => {
    const failed = { ...LINUX_CUDA, job: { state: "failed", flavour: "cuda", line: null, reason: "file-changed", message: "The archive llama-b11941-bin-ubuntu-x64.tar.gz does not match its recorded SHA-256, so it was not used." } } as const;
    const entry = await card(serve(failed));
    expect(entry).toHaveTextContent("Failed: The archive llama-b11941-bin-ubuntu-x64.tar.gz does not match its recorded SHA-256, so it was not used.");
    expect(entry).toHaveTextContent("Not installed");
    expect(entry).not.toHaveTextContent("Installed at");
    expect(await within(entry).findByRole("button", { name: "Get llama.cpp" })).toBeEnabled();
  });

  it.each([
    ["binary-check-failed", "The build did not run on this system."],
    ["cuda-device-missing", "No NVIDIA device was found, so the CUDA build cannot run here. Choose CPU, or install the driver."],
    ["download-failed", "The archive could not be downloaded. Check the connection, then try again."],
    ["not-supported", "OMRS has no pinned build for this system. Install llama.cpp yourself and set the program path."],
  ] as const)("shows the %s reason as plain text, from the fixed table when the server sends no line", async (reason, sentence) => {
    const failed: LlamacppBuild = { ...LINUX_CUDA, job: { state: "failed", flavour: null, line: null, reason, message: null } };
    const entry = await card(serve(failed));
    expect(entry).toHaveTextContent(`Failed: ${sentence}`);
  });

  it("shows where the provisioned program sits once the job has placed it", async () => {
    const entry = await card(serve({ ...LINUX_CUDA, installed_path: "/data/omrs/llamacpp/b11941-cuda/llama-server", job: { ...IDLE, state: "succeeded", flavour: "cuda" } }));
    expect(entry).toHaveTextContent("Installed at /data/omrs/llamacpp/b11941-cuda/llama-server");
    expect(within(entry).queryByRole("button", { name: "Get llama.cpp" })).toBeNull();
  });

  it("Own program set: says it uses that program, with no Not installed line and no Get llama.cpp button", async () => {
    const own = routerStatus({ program: { path: "/opt/llama/llama-server", source: "user" } });
    const server = serve(LINUX_CUDA, { "GET /v1/llamacpp/router": () => own });
    startApp("#/integrations", server);
    const list = await screen.findByRole("list", { name: "Integrations" });
    const entry = within(list).getAllByRole("listitem").find((item) => within(item).queryByRole("heading", { name: "llama.cpp provider" }));
    if (entry === undefined) throw new Error("No llama.cpp card");
    await waitFor(() => expect(entry).toHaveTextContent("Uses your own program: /opt/llama/llama-server"));
    expect(entry).not.toHaveTextContent("Not installed");
    expect(entry).not.toHaveTextContent("llama.cpp build");
    expect(within(entry).queryByRole("button", { name: "Get llama.cpp" })).toBeNull();
    expect(within(entry).queryByRole("radiogroup")).toBeNull();
  });

  it("Provisioned or no program in force: the card keeps the pinned build line and the Get llama.cpp button", async () => {
    const none = routerStatus({ program: { path: "", source: "none" } });
    const entry = await card(serve(LINUX_CUDA, { "GET /v1/llamacpp/router": () => none }));
    expect(entry).toHaveTextContent("Not installed");
    expect(entry).not.toHaveTextContent("Uses your own program");
    expect(await within(entry).findByRole("button", { name: "Get llama.cpp" })).toBeEnabled();
  });

  it("Read-only session: the card shows no Get llama.cpp button", async () => {
    const server = serve(LINUX_CUDA, { "GET /v1/session": () => SESSION_READ_ONLY });
    const entry = await card(server);
    await waitFor(() => expect(server.exact("GET", "/v1/session")).toHaveLength(1));
    await waitFor(() => expect(within(entry).queryByRole("button", { name: "Get llama.cpp" })).toBeNull());
    expect(entry).toHaveTextContent("Not installed");
  });

  it("says in plain words that an install job is already running", async () => {
    const busy = json({ status: "error", message: "raw text", reason: "busy" }, 409);
    const user = userEvent.setup();
    const entry = await card(serve(LINUX_CUDA, { "POST /v1/llamacpp/router/install": () => busy }));
    await user.click(await within(entry).findByRole("button", { name: "Get llama.cpp" }));
    const alert = await within(entry).findByRole("alert");
    expect(alert).toHaveTextContent("An install is already running. Wait for it to finish.");
    expect(alert).not.toHaveTextContent("raw text");
  });
});
