import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { downloadStatus } from "./test/downloadFixtures";
import { serverStatus, settingsServer } from "./test/fixtures";

const WITH_CREDENTIALS = { "GET /v1/session": () => ({ status: "ok", kind: "session", scopes: ["credentials", "files", "graph", "read", "run"], workspace: "/home/u/.omrs/workspace" }) };

const LLAMA_DONE = downloadStatus({
  state: "succeeded",
  provider: "llamacpp",
  model: "unsloth/Qwen3-4B-GGUF:Q4_K_M",
  model_value: "unsloth/Qwen3-4B-GGUF:Q4_K_M",
  bytes_done: 10,
  bytes_total: 10,
  cache_folder: "~/.cache/huggingface/hub",
});
const OLD_MODEL = { model: { value: "old/model:Q2_K", source: "config-file" as const } };
const RUNNING = serverStatus({ state: "running", pid_running: true, running_with: { context_window: 16384, model_kind: "hf" } }, OLD_MODEL);

async function open(handlers = {}, provider = "llama.cpp") {
  const server = settingsServer(handlers);
  startApp("#/settings/providers", server);
  await screen.findByRole("heading", { level: 3, name: provider });
  const panel = () => within(screen.getByRole("region", { name: provider })).getByRole("group", { name: "Get a model" });
  return { server, user: userEvent.setup(), panel };
}

describe("llama.cpp download finished, server run by omrs", () => {
  it("saves the model value with Use this model, then offers the existing Restart", async () => {
    const puts: unknown[] = [];
    let status = RUNNING;
    const restarts: number[] = [];
    const { user, panel } = await open({
      ...WITH_CREDENTIALS,
      "GET /v1/model-downloads/current": () => LLAMA_DONE,
      "GET /v1/llamacpp/server": () => status,
      "PUT /v1/llamacpp/server": (body: unknown) => {
        puts.push(body);
        return (status = serverStatus({ ...RUNNING, pending_restart: true }, { model: { value: "unsloth/Qwen3-4B-GGUF:Q4_K_M", source: "config-file" } }));
      },
      "POST /v1/llamacpp/server/restart": () => (restarts.push(1), RUNNING),
    });
    await user.click(await within(panel()).findByRole("button", { name: "Use this model" }));
    expect(puts).toEqual([{ model: "unsloth/Qwen3-4B-GGUF:Q4_K_M", revision: "r1" }]);
    await user.click(await within(panel()).findByRole("button", { name: "Restart server to load it" }));
    expect(restarts).toHaveLength(1);
  });

  it("also offers Use this model while the server is starting", async () => {
    const { panel } = await open({ ...WITH_CREDENTIALS, "GET /v1/model-downloads/current": () => LLAMA_DONE, "GET /v1/llamacpp/server": () => serverStatus({ state: "starting", pid_running: true }, OLD_MODEL) });
    const button = await within(panel()).findByRole("button", { name: "Use this model" });
    await waitFor(() => expect(button).toBeEnabled());
  });

  it("shows the credentials refusal, sends nothing and keeps the old model when the session lacks credentials", async () => {
    const { server, panel } = await open({ "GET /v1/model-downloads/current": () => LLAMA_DONE, "GET /v1/llamacpp/server": () => RUNNING });
    const button = await within(panel()).findByRole("button", { name: "Use this model" });
    expect(await within(panel()).findByText("A credentials session is needed to change this.")).toBeInTheDocument();
    expect(button).toBeDisabled();
    expect(server.find("PUT", "/v1/llamacpp/server")).toHaveLength(0);
    expect(screen.getByText("old/model:Q2_K")).toBeInTheDocument();
  });

  it("shows one friendly line and keeps the old model when the server refuses the save", async () => {
    const { user, panel } = await open({
      ...WITH_CREDENTIALS,
      "GET /v1/model-downloads/current": () => LLAMA_DONE,
      "GET /v1/llamacpp/server": () => RUNNING,
      "PUT /v1/llamacpp/server": () => json({ status: "error", message: "Needs credentials." }, 403),
    });
    await user.click(await within(panel()).findByRole("button", { name: "Use this model" }));
    expect(await within(panel()).findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("old/model:Q2_K")).toBeInTheDocument();
  });
});

describe("llama.cpp download finished, server not run by omrs", () => {
  async function external() {
    return open({ ...WITH_CREDENTIALS, "GET /v1/model-downloads/current": () => LLAMA_DONE, "GET /v1/llamacpp/server": () => serverStatus({ state: "stopped" }) });
  }

  it("names the cache folder and the Llama app note, and offers no Use this model", async () => {
    const { panel } = await external();
    expect(await within(panel()).findByText("~/.cache/huggingface/hub")).toBeInTheDocument();
    expect(within(panel()).getByText(/The Llama app lists new models only when it starts, so quit and reopen it, then press Refresh models\./)).toBeInTheDocument();
    expect(within(panel()).queryByRole("button", { name: "Use this model" })).toBeNull();
    expect(within(panel()).getByRole("button", { name: "Refresh models" })).toBeInTheDocument();
  });

  it("reads the llama.cpp model list again on Refresh models and says whether the server lists the model", async () => {
    let listed = false;
    const { server, user, panel } = await open({
      ...WITH_CREDENTIALS,
      "GET /v1/model-downloads/current": () => LLAMA_DONE,
      "GET /v1/llamacpp/server": () => serverStatus({ state: "stopped" }),
      "POST /v1/connections/llamacpp/models": () => ({ status: "ok", reachable: true, reason: null, models: listed ? ["unsloth/Qwen3-4B-GGUF:Q4_K_M"] : ["old/model:Q2_K"], truncated: false }),
    });
    const button = await within(panel()).findByRole("button", { name: "Refresh models" });
    expect(server.exact("POST", "/v1/connections/llamacpp/models")).toHaveLength(0);
    await user.click(button);
    expect(await within(panel()).findByText(/does not list it yet/)).toBeInTheDocument();
    listed = true;
    await user.click(within(panel()).getByRole("button", { name: "Refresh models" }));
    expect(await within(panel()).findByText("Your server lists unsloth/Qwen3-4B-GGUF:Q4_K_M.")).toBeInTheDocument();
    expect(server.exact("POST", "/v1/connections/llamacpp/models")).toHaveLength(2);
  });

  it("says so when the server does not answer", async () => {
    const { user, panel } = await open({
      ...WITH_CREDENTIALS,
      "GET /v1/model-downloads/current": () => LLAMA_DONE,
      "GET /v1/llamacpp/server": () => serverStatus({ state: "stopped" }),
      "POST /v1/connections/llamacpp/models": () => ({ status: "ok", reachable: false, reason: "refused", models: [], truncated: false }),
    });
    await user.click(await within(panel()).findByRole("button", { name: "Refresh models" }));
    expect(await within(panel()).findByText(/did not answer/)).toBeInTheDocument();
  });
});

describe("Ollama download finished", () => {
  it("reads the Ollama model list again and says Ollama lists the model", async () => {
    const { server, panel } = await open(
      {
        "GET /v1/model-downloads/current": () => downloadStatus({ state: "succeeded", provider: "ollama", model: "qwen3", model_value: "qwen3", bytes_done: 5, bytes_total: 5 }),
        "POST /v1/connections/ollama/models": () => ({ status: "ok", reachable: true, reason: null, models: ["qwen3:latest"], truncated: false }),
      },
      "Ollama",
    );
    expect(await within(panel()).findByText("Ollama lists qwen3.")).toBeInTheDocument();
    await waitFor(() => expect(server.exact("POST", "/v1/connections/ollama/models")).toHaveLength(1));
    expect(within(panel()).queryByRole("button", { name: "Use this model" })).toBeNull();
  });
});
