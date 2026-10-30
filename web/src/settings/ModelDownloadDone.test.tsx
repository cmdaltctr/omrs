import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { downloadStatus } from "./test/downloadFixtures";
import { CHAT_READY, choiceStatus, serverStatus, settingsServer } from "./test/fixtures";

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
const CHAT_OLD = { ...CHAT_READY, provider: "llamacpp", model: "old/model:Q2_K" };
const MANAGED_RUNNING = choiceStatus("managed", { state: "running", pid_running: true, running_with: { context_window: 16384, model_kind: "hf" }, chat_model: { provider: "llamacpp", model: "old/model:Q2_K", usable: true } });
const MANAGED_STOPPED = choiceStatus("managed", { chat_model: { provider: "llamacpp", model: "old/model:Q2_K", usable: true } });

async function open(handlers = {}, provider = "llama.cpp") {
  const server = settingsServer({ "GET /v1/settings/chat": () => CHAT_OLD, ...handlers });
  startApp("#/settings/providers", server);
  await screen.findByRole("heading", { level: 3, name: provider });
  const panel = () => within(screen.getByRole("region", { name: provider })).getByRole("group", { name: "Get a model" });
  return { server, user: userEvent.setup(), panel };
}

describe("llama.cpp download finished, OMRS runs the Chat server", () => {
  it("saves the model value as the llama.cpp Chat model with Use this model, then offers Restart", async () => {
    let chat = CHAT_OLD;
    let status = MANAGED_RUNNING;
    const restarts: number[] = [];
    const { user, panel, server } = await open({
      ...WITH_CREDENTIALS,
      "GET /v1/model-downloads/current": () => LLAMA_DONE,
      "GET /v1/settings/chat": () => chat,
      "GET /v1/llamacpp/server": () => status,
      "PUT /v1/settings/chat": (body: { model: string }) => {
        chat = { ...CHAT_OLD, model: body.model };
        status = { ...MANAGED_RUNNING, pending_restart: true, chat_model: { provider: "llamacpp", model: body.model, usable: true } };
        return { status: "ok", revision: "r2" };
      },
      "POST /v1/llamacpp/server/restart": () => (restarts.push(1), MANAGED_RUNNING),
    });
    await user.click(await within(panel()).findByRole("button", { name: "Use this model" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/chat")).toHaveLength(1));
    expect(server.find("PUT", "/v1/settings/chat")[0]?.body).toEqual({ provider: "llamacpp", model: "unsloth/Qwen3-4B-GGUF:Q4_K_M", revision: "r1" });
    expect(server.find("PUT", "/v1/llamacpp/server")).toHaveLength(0);
    expect(await within(panel()).findByText("Saved as the Chat model. The server loads it after a restart.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("group", { name: "Local server" })).toHaveTextContent("Restart to apply"));
    await user.click(within(panel()).getByRole("button", { name: "Restart server to load it" }));
    expect(restarts).toHaveLength(1);
    await waitFor(() => expect(within(panel()).queryByText("Saved as the Chat model. The server loads it after a restart.")).toBeNull());
  });

  it("offers Use this model while the server is stopped and keeps Restart disabled", async () => {
    const { user, panel } = await open({
      ...WITH_CREDENTIALS,
      "GET /v1/model-downloads/current": () => LLAMA_DONE,
      "GET /v1/llamacpp/server": () => MANAGED_STOPPED,
      "PUT /v1/settings/chat": () => ({ status: "ok", revision: "r2" }),
    });
    const button = await within(panel()).findByRole("button", { name: "Use this model" });
    await waitFor(() => expect(button).toBeEnabled());
    expect(within(panel()).queryByRole("button", { name: "Refresh models" })).toBeNull();
    await user.click(button);
    expect(await within(panel()).findByRole("button", { name: "Restart server to load it" })).toBeDisabled();
  });

  it("shows the read error, not the own-server note, when the server status cannot be read", async () => {
    const { panel } = await open({ ...WITH_CREDENTIALS, "GET /v1/model-downloads/current": () => LLAMA_DONE, "GET /v1/llamacpp/server": () => json({ status: "error", message: "Broken." }, 500) });
    expect(await within(panel()).findByRole("alert")).toBeInTheDocument();
    expect(within(panel()).queryByRole("button", { name: "Refresh models" })).toBeNull();
    expect(within(panel()).queryByText(/Llama app/)).toBeNull();
  });

  it("shows the credentials refusal, sends nothing and keeps the old Chat model when the session lacks credentials", async () => {
    const { server, panel } = await open({ "GET /v1/model-downloads/current": () => LLAMA_DONE, "GET /v1/llamacpp/server": () => MANAGED_RUNNING });
    const button = await within(panel()).findByRole("button", { name: "Use this model" });
    expect(await within(panel()).findByText("A credentials session is needed to change this.")).toBeInTheDocument();
    expect(button).toBeDisabled();
    expect(server.find("PUT", "/v1/settings/chat")).toHaveLength(0);
    expect(screen.getAllByText("old/model:Q2_K").length).toBeGreaterThan(0);
  });

  it("shows one friendly line and keeps the old Chat model when the server refuses the save", async () => {
    const { user, panel } = await open({
      ...WITH_CREDENTIALS,
      "GET /v1/model-downloads/current": () => LLAMA_DONE,
      "GET /v1/llamacpp/server": () => MANAGED_RUNNING,
      "PUT /v1/settings/chat": () => json({ status: "error", message: "Needs credentials." }, 403),
    });
    await user.click(await within(panel()).findByRole("button", { name: "Use this model" }));
    expect(await within(panel()).findByRole("alert")).toBeInTheDocument();
    expect(screen.getAllByText("old/model:Q2_K").length).toBeGreaterThan(0);
  });
});

describe("llama.cpp download finished, the user runs the Chat server", () => {
  async function external(state: "stopped" | "running" = "stopped") {
    return open({ ...WITH_CREDENTIALS, "GET /v1/model-downloads/current": () => LLAMA_DONE, "GET /v1/llamacpp/server": () => serverStatus({ state }) });
  }

  it("names the cache folder and the Llama app note, and offers no Use this model", async () => {
    const { panel } = await external();
    expect(await within(panel()).findByText("~/.cache/huggingface/hub")).toBeInTheDocument();
    expect(within(panel()).getByText(/The Llama app lists new models only when it starts, so quit and reopen it, then press Refresh models\./)).toBeInTheDocument();
    expect(within(panel()).queryByRole("button", { name: "Use this model" })).toBeNull();
    expect(within(panel()).getByRole("button", { name: "Refresh models" })).toBeInTheDocument();
  });

  it("follows the saved choice, not the server state, so a running server still gets the cache folder steps", async () => {
    const { panel } = await external("running");
    expect(await within(panel()).findByRole("button", { name: "Refresh models" })).toBeInTheDocument();
    expect(within(panel()).queryByRole("button", { name: "Use this model" })).toBeNull();
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
  it("uses Ollama words when Ollama does not list the model yet, and reads the list again on Refresh models", async () => {
    let listed = false;
    const { server, user, panel } = await open(
      {
        "GET /v1/model-downloads/current": () => downloadStatus({ state: "succeeded", provider: "ollama", model: "qwen3", model_value: "qwen3", bytes_done: 5, bytes_total: 5 }),
        "POST /v1/connections/ollama/models": () => ({ status: "ok", reachable: true, reason: null, models: listed ? ["qwen3:latest"] : [], truncated: false }),
      },
      "Ollama",
    );
    expect(await within(panel()).findByText(/Ollama does not list it yet/)).toBeInTheDocument();
    expect(within(panel()).queryByText(/Llama app|Your server/)).toBeNull();
    listed = true;
    await user.click(within(panel()).getByRole("button", { name: "Refresh models" }));
    expect(await within(panel()).findByText("Ollama lists qwen3.")).toBeInTheDocument();
    expect(server.exact("POST", "/v1/connections/ollama/models")).toHaveLength(2);
  });

  it("uses Ollama words when Ollama does not answer", async () => {
    const { panel } = await open(
      {
        "GET /v1/model-downloads/current": () => downloadStatus({ state: "succeeded", provider: "ollama", model: "qwen3", model_value: "qwen3", bytes_done: 5, bytes_total: 5 }),
        "POST /v1/connections/ollama/models": () => ({ status: "ok", reachable: false, reason: "refused", models: [], truncated: false }),
      },
      "Ollama",
    );
    expect(await within(panel()).findByText(/Ollama did not answer/)).toBeInTheDocument();
    expect(within(panel()).queryByText(/chat address|Your server/)).toBeNull();
  });

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
