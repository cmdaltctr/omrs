import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { downloadStatus } from "./test/downloadFixtures";
import { CHAT_READY, EMBED_ENTRY, ROUTER_EXTERNAL, ROUTER_STOPPED, routerStatus, settingsServer, TEXT_ENTRY, WITH_CREDENTIALS } from "./test/fixtures";

const NEW_MODEL = "Qwen/Qwen3-1.7B-GGUF:Q8_0";
const HASH = "b".repeat(64);

const LLAMA_DONE = downloadStatus({
  state: "succeeded",
  provider: "llamacpp",
  model: NEW_MODEL,
  model_value: NEW_MODEL,
  bytes_done: 10,
  bytes_total: 10,
  cache_folder: "~/.cache/huggingface/hub",
  file_path: "/cache/Qwen3-1.7B-Q8_0.gguf",
  sha256: HASH,
});
const CHAT_OLD = { ...CHAT_READY, provider: "llamacpp", model: "old/model:Q2_K" };
const ADDED = routerStatus({ models: [EMBED_ENTRY, TEXT_ENTRY, { ...TEXT_ENTRY, id: "qwen-qwen3-1-7b-gguf-q8-0", model: NEW_MODEL, file: "/cache/Qwen3-1.7B-Q8_0.gguf", roles: [] }] });

async function open(handlers = {}, provider = "llama.cpp") {
  const server = settingsServer({ "GET /v1/settings/chat": () => CHAT_OLD, ...handlers });
  startApp("#/settings/providers", server);
  await screen.findByRole("heading", { level: 3, name: provider });
  const panel = () => within(screen.getByRole("region", { name: provider })).getByRole("group", { name: "Get a model" });
  return { server, user: userEvent.setup(), panel };
}

describe("Use this model adds or replaces a router list entry", () => {
  it("Adds a list entry: Add as a new model sends the model, the cache path and the hash, and leaves the Chat model alone", async () => {
    const { user, panel, server } = await open({
      ...WITH_CREDENTIALS,
      "GET /v1/model-downloads/current": () => LLAMA_DONE,
      "PUT /v1/llamacpp/router/models/qwen-qwen3-1-7b-gguf-q8-0": () => ADDED,
    });
    expect(await within(panel()).findByRole("combobox", { name: "Where to put this model" })).toHaveTextContent("Add as a new model");
    await user.click(await within(panel()).findByRole("button", { name: "Use this model" }));
    await waitFor(() => expect(server.find("PUT", "/v1/llamacpp/router/models/")).toHaveLength(1));
    expect(server.find("PUT", "/v1/llamacpp/router/models/")[0]?.body).toEqual({ model: NEW_MODEL, file: "/cache/Qwen3-1.7B-Q8_0.gguf", sha256: HASH, revision: "r1" });
    expect(server.find("PUT", "/v1/settings/chat")).toHaveLength(0);
    expect(await within(panel()).findByText("Saved to the router list. Choose it in Settings > Chat if it should answer.")).toBeInTheDocument();
  });

  it("Replaces an entry's file: picking qwen3-4b changes its model, file and hash and sends no preset", async () => {
    const { user, panel, server } = await open({
      ...WITH_CREDENTIALS,
      "GET /v1/model-downloads/current": () => LLAMA_DONE,
      "PUT /v1/llamacpp/router/models/qwen3-4b": () => ADDED,
    });
    await user.click(await within(panel()).findByRole("combobox", { name: "Where to put this model" }));
    await user.click(await screen.findByRole("option", { name: /^Replace qwen3-4b/ }));
    await user.click(within(panel()).getByRole("button", { name: "Use this model" }));
    await waitFor(() => expect(server.find("PUT", "/v1/llamacpp/router/models/qwen3-4b")).toHaveLength(1));
    expect(server.find("PUT", "/v1/llamacpp/router/models/qwen3-4b")[0]?.body).toEqual({ model: NEW_MODEL, file: "/cache/Qwen3-1.7B-Q8_0.gguf", sha256: HASH, revision: "r1" });
  });

  it("Download changes no setting: nothing is saved until the user presses Use this model", async () => {
    const { server, panel } = await open({ ...WITH_CREDENTIALS, "GET /v1/model-downloads/current": () => LLAMA_DONE });
    await within(panel()).findByRole("button", { name: "Use this model" });
    expect(server.calls.filter((call) => call.method !== "GET" && call.method !== "POST")).toHaveLength(0);
    expect(server.find("PUT", "/v1")).toHaveLength(0);
  });

  it("No credentials: a session with manage but not credentials sees the refusal and no request goes out", async () => {
    const manageOnly = { "GET /v1/session": () => ({ status: "ok", kind: "session", scopes: ["manage", "read"], workspace: null }) };
    const { server, panel } = await open({ ...manageOnly, "GET /v1/model-downloads/current": () => LLAMA_DONE });
    const button = await within(panel()).findByRole("button", { name: "Use this model" });
    expect(await within(panel()).findByText("Changing this needs a session with the credentials scope.")).toBeInTheDocument();
    expect(button).toBeDisabled();
    expect(server.find("PUT", "/v1/llamacpp/router/models/")).toHaveLength(0);
  });

  it("shows one friendly line and keeps the list when the server refuses the save", async () => {
    const { user, panel } = await open({
      ...WITH_CREDENTIALS,
      "GET /v1/model-downloads/current": () => LLAMA_DONE,
      "PUT /v1/llamacpp/router/models/qwen-qwen3-1-7b-gguf-q8-0": () => json({ status: "error", message: "Needs credentials." }, 403),
    });
    await user.click(await within(panel()).findByRole("button", { name: "Use this model" }));
    expect(await within(panel()).findByRole("alert")).toBeInTheDocument();
    expect(within(panel()).queryByText("Saved to the router list. Choose it in Settings > Chat if it should answer.")).toBeNull();
  });

  it("Managed choice with a stopped server: offers Use this model, and no Refresh models", async () => {
    const { panel } = await open({ ...WITH_CREDENTIALS, "GET /v1/model-downloads/current": () => LLAMA_DONE, "GET /v1/llamacpp/router": () => ROUTER_STOPPED });
    const button = await within(panel()).findByRole("button", { name: "Use this model" });
    await waitFor(() => expect(button).toBeEnabled());
    expect(within(panel()).queryByRole("button", { name: "Refresh models" })).toBeNull();
  });

  it("shows the read error, not the cache folder steps, when the router status cannot be read", async () => {
    const { panel } = await open({ ...WITH_CREDENTIALS, "GET /v1/model-downloads/current": () => LLAMA_DONE, "GET /v1/llamacpp/router": () => json({ status: "error", message: "Broken." }, 500) });
    expect(await within(panel()).findByRole("alert")).toBeInTheDocument();
    expect(within(panel()).queryByRole("button", { name: "Refresh models" })).toBeNull();
    expect(within(panel()).queryByText(/Llama app/)).toBeNull();
  });
});

describe("An external llama.cpp server is told, not controlled", () => {
  async function external() {
    return open({ ...WITH_CREDENTIALS, "GET /v1/model-downloads/current": () => LLAMA_DONE, "GET /v1/llamacpp/router": () => ROUTER_EXTERNAL });
  }

  it("Llama app after a download: names the cache folder and the Llama app note, and offers no Use this model", async () => {
    const { panel } = await external();
    expect(await within(panel()).findByText("~/.cache/huggingface/hub")).toBeInTheDocument();
    expect(within(panel()).getByText(/The Llama app lists new models only when it starts, so quit and reopen it, then press Refresh models\./)).toBeInTheDocument();
    expect(within(panel()).queryByRole("button", { name: "Use this model" })).toBeNull();
    expect(within(panel()).getByRole("button", { name: "Refresh models" })).toBeInTheDocument();
  });

  it("follows the saved mode, not the router state, so a running router still gets the cache folder steps", async () => {
    const { panel } = await open({ ...WITH_CREDENTIALS, "GET /v1/model-downloads/current": () => LLAMA_DONE, "GET /v1/llamacpp/router": () => ({ ...ROUTER_EXTERNAL, state: "running" }) });
    expect(await within(panel()).findByRole("button", { name: "Refresh models" })).toBeInTheDocument();
    expect(within(panel()).queryByRole("button", { name: "Use this model" })).toBeNull();
  });

  it("New model shows after the server lists it: Refresh models reads the list again and says whether the server lists the model", async () => {
    let listed = false;
    const { server, user, panel } = await open({
      ...WITH_CREDENTIALS,
      "GET /v1/model-downloads/current": () => LLAMA_DONE,
      "GET /v1/llamacpp/router": () => ROUTER_EXTERNAL,
      "POST /v1/connections/llamacpp/models": () => ({ status: "ok", reachable: true, reason: null, models: listed ? [NEW_MODEL] : ["old/model:Q2_K"], truncated: false }),
    });
    const button = await within(panel()).findByRole("button", { name: "Refresh models" });
    expect(server.exact("POST", "/v1/connections/llamacpp/models")).toHaveLength(0);
    await user.click(button);
    expect(await within(panel()).findByText(/does not list it yet/)).toBeInTheDocument();
    listed = true;
    await user.click(within(panel()).getByRole("button", { name: "Refresh models" }));
    expect(await within(panel()).findByText(`Your server lists ${NEW_MODEL}.`)).toBeInTheDocument();
    expect(server.exact("POST", "/v1/connections/llamacpp/models")).toHaveLength(2);
  });

  it("says so when the server does not answer", async () => {
    const { user, panel } = await open({
      ...WITH_CREDENTIALS,
      "GET /v1/model-downloads/current": () => LLAMA_DONE,
      "GET /v1/llamacpp/router": () => ROUTER_EXTERNAL,
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
