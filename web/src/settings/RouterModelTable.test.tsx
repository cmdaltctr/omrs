import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { downloadStatus, FILES } from "./test/downloadFixtures";
import { EMBED_ENTRY, EMBED_MODEL, ROUTER_EXTERNAL, routerEntry, routerStatus, settingsServer, TEXT_ENTRY, TEXT_MODEL, WITH_CREDENTIALS } from "./test/fixtures";

const CHAT_ENTRY = routerEntry({ roles: ["classification", "chat"] });
const GOT = {
  ...routerEntry({ file: "/cache/Qwen3-4B-Q8_0.gguf", state: "unloaded" }),
};

async function open(handlers = {}) {
  const server = settingsServer({ ...WITH_CREDENTIALS, ...handlers });
  startApp("#/settings/providers", server);
  await screen.findByRole("heading", { level: 3, name: "llama.cpp" });
  const table = () => within(screen.getByRole("region", { name: "llama.cpp" })).getByRole("table", { name: "Router models" });
  await waitFor(() => expect(table()).toBeInTheDocument());
  const row = (model: string) => within(table()).getAllByRole("row").find((element) => element.textContent?.includes(model)) as HTMLElement;
  return { server, user: userEvent.setup(), table, row };
}

describe("The Router panel lists the models in a table", () => {
  it("Shipped list on a fresh install: the embedding entry with Embeddings, the text entry with Classification only, both Not downloaded", async () => {
    const { row } = await open();
    expect(row(EMBED_MODEL)).toHaveTextContent("Embeddings");
    expect(row(EMBED_MODEL)).toHaveTextContent("Not downloaded");
    expect(row(TEXT_MODEL)).toHaveTextContent("Classification");
    expect(row(TEXT_MODEL)).not.toHaveTextContent("Chat");
    expect(row(TEXT_MODEL)).toHaveTextContent("Not downloaded");
  });

  it("Unit is stated: the column heading says Context size (tokens)", async () => {
    const { table } = await open();
    expect(within(table()).getByRole("columnheader", { name: "Context size (tokens)" })).toBeInTheDocument();
  });

  it("Edit context size: sends the whole preset with 16384 and shows 16,384", async () => {
    const put: unknown[] = [];
    const { row, user } = await open({
      "GET /v1/llamacpp/router": () => routerStatus({ models: [EMBED_ENTRY, CHAT_ENTRY] }),
      "PUT /v1/llamacpp/router/models/qwen3-4b": (body: unknown) => {
        put.push(body);
        return { ...routerStatus({ models: [EMBED_ENTRY, { ...CHAT_ENTRY, ctx_size: 16384, preset: { "ctx-size": 16384, parallel: 2 } }] }), revision: "r2" };
      },
    });
    await waitFor(() => expect(row(TEXT_MODEL)).toHaveTextContent("32,768"));
    await user.click(within(row(TEXT_MODEL)).getByRole("button", { name: `Edit ${TEXT_MODEL}` }));
    const input = screen.getByRole("spinbutton", { name: "Context size (tokens)" });
    expect(input).toHaveValue(32768);
    await user.clear(input);
    await user.type(input, "16384");
    await user.click(screen.getByRole("button", { name: "Save model" }));
    await waitFor(() => expect(row(TEXT_MODEL)).toHaveTextContent("16,384"));
    expect(put).toEqual([{ preset: { "ctx-size": 16384, parallel: 2 }, revision: "r1" }]);
  });

  it("Edit offers one control for each allow-listed preset value and sends a cleared value as left out", async () => {
    const put: unknown[] = [];
    const { row, user } = await open({
      "PUT /v1/llamacpp/router/models/qwen3-4b": (body: unknown) => {
        put.push(body);
        return routerStatus({});
      },
    });
    await user.click(within(row(TEXT_MODEL)).getByRole("button", { name: `Edit ${TEXT_MODEL}` }));
    const labels = [
      "Context size (tokens)", "Batch size", "Micro-batch size", "Parallel requests", "Embeddings only", "Pooling", "Embedding normalisation", "Unified KV cache", "Flash attention",
      "GPU layers", "Fit to memory", "Key cache type", "Value cache type", "Prompt cache", "Cache reuse (tokens)", "Image minimum tokens", "Image maximum tokens",
    ];
    for (const label of labels) expect(screen.getByLabelText(label)).toBeInTheDocument();
    await user.clear(screen.getByRole("spinbutton", { name: "Parallel requests" }));
    await user.click(screen.getByRole("button", { name: "Save model" }));
    await waitFor(() => expect(put).toEqual([{ preset: { "ctx-size": 32768 }, revision: "r1" }]));
  });

  it("Edit refuses a value outside its range and sends nothing", async () => {
    const { row, server, user } = await open();
    await user.click(within(row(TEXT_MODEL)).getByRole("button", { name: `Edit ${TEXT_MODEL}` }));
    const input = screen.getByRole("spinbutton", { name: "Context size (tokens)" });
    await user.clear(input);
    await user.type(input, "100");
    await user.click(screen.getByRole("button", { name: "Save model" }));
    expect(await screen.findByText("Enter 512 to 262,144.")).toBeInTheDocument();
    expect(server.find("PUT", "/v1/llamacpp/router/models")).toHaveLength(0);
  });

  it("Remove refused for a used entry: a row that holds a role offers no Remove", async () => {
    const { row } = await open({ "GET /v1/llamacpp/router": () => routerStatus({ models: [EMBED_ENTRY, CHAT_ENTRY, routerEntry({ id: "spare", model: "Qwen/Qwen3-1.7B-GGUF:Q8_0", roles: [] })] }) });
    await waitFor(() => expect(row("Qwen3-1.7B")).toBeDefined());
    expect(within(row(TEXT_MODEL)).queryByRole("button", { name: /^Remove/ })).toBeNull();
    expect(within(row(EMBED_MODEL)).queryByRole("button", { name: /^Remove/ })).toBeNull();
    expect(within(row("Qwen3-1.7B")).getByRole("button", { name: "Remove Qwen/Qwen3-1.7B-GGUF:Q8_0" })).toBeInTheDocument();
  });

  it("removes an entry that holds no role, and says why a refused removal failed", async () => {
    const spare = routerEntry({ id: "spare", model: "Qwen/Qwen3-1.7B-GGUF:Q8_0", roles: [] });
    const refused = json({ status: "error", message: "raw server text", reason: "in-use" }, 409);
    const { row, user, server } = await open({
      "GET /v1/llamacpp/router": () => routerStatus({ models: [EMBED_ENTRY, TEXT_ENTRY, spare] }),
      "DELETE /v1/llamacpp/router/models/spare": () => refused,
    });
    await waitFor(() => expect(row("Qwen3-1.7B")).toBeDefined());
    await user.click(within(row("Qwen3-1.7B")).getByRole("button", { name: "Remove Qwen/Qwen3-1.7B-GGUF:Q8_0" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This model holds a role. Give the role to another model first.");
    expect(alert).not.toHaveTextContent("raw server text");
    expect(server.find("DELETE", "/v1/llamacpp/router/models/spare")).toHaveLength(1);
  });

  it("Reload pending: a changed row of a running router says so", async () => {
    const { row } = await open({ "GET /v1/llamacpp/router": () => routerStatus({ state: "running", models: [EMBED_ENTRY, { ...TEXT_ENTRY, reload_pending: true }] }) });
    await waitFor(() => expect(row(TEXT_MODEL)).toHaveTextContent("Reload pending"));
    expect(row(EMBED_MODEL)).not.toHaveTextContent("Reload pending");
  });

  it("shows each model state, and the plain reason line of a failed model", async () => {
    const failed = { ...TEXT_ENTRY, state: "failed" as const, reason: "model-load-failed" as const, reason_text: "The model could not be loaded." };
    const { row } = await open({ "GET /v1/llamacpp/router": () => routerStatus({ models: [{ ...EMBED_ENTRY, file: "/cache/e.gguf", state: "loaded" }, failed] }) });
    await waitFor(() => expect(row(EMBED_MODEL)).toHaveTextContent("Loaded"));
    expect(row(TEXT_MODEL)).toHaveTextContent("Failed");
    expect(row(TEXT_MODEL)).toHaveTextContent("The model could not be loaded.");
  });

  it("links each role to the setting that gives it", async () => {
    const { row } = await open({ "GET /v1/llamacpp/router": () => routerStatus({ models: [EMBED_ENTRY, CHAT_ENTRY] }) });
    await waitFor(() => expect(within(row(TEXT_MODEL)).getByRole("link", { name: "Chat" })).toHaveAttribute("href", "#/settings/chat"));
    expect(within(row(TEXT_MODEL)).getByRole("link", { name: "Classification" })).toHaveAttribute("href", "#/settings/configuration");
    expect(within(row(EMBED_MODEL)).getByRole("link", { name: "Embeddings" })).toHaveAttribute("href", "#/settings/configuration");
  });

  it("Shared by Chat and classification: the row of the shared entry shows a one-line warning", async () => {
    const { row } = await open({ "GET /v1/llamacpp/router": () => routerStatus({ models: [EMBED_ENTRY, CHAT_ENTRY] }) });
    await waitFor(() => expect(row(TEXT_MODEL)).toHaveTextContent("Shared by Chat and classification"));
    expect(row(EMBED_MODEL)).not.toHaveTextContent("Shared by");
  });

  it("External mode: names models and roles, and offers no Edit or Get this model", async () => {
    const { row } = await open({ "GET /v1/llamacpp/router": () => ROUTER_EXTERNAL });
    await waitFor(() => expect(row(TEXT_MODEL)).toBeDefined());
    expect(within(row(TEXT_MODEL)).queryByRole("button", { name: /^Edit/ })).toBeNull();
    expect(within(row(TEXT_MODEL)).queryByRole("button", { name: "Get this model" })).toBeNull();
  });

  it("Phone width: the table and its rows stack in the panel width and wrap long names", async () => {
    const { table, row } = await open();
    expect(table().className).toContain("@container");
    for (const model of [EMBED_MODEL, TEXT_MODEL]) {
      expect(row(model).className).toContain("grid-cols-1");
      expect(row(model).className).toMatch(/@2xl:grid-cols-/);
      expect(within(row(model)).getByText(model).className).toContain("[overflow-wrap:anywhere]");
      expect(within(row(model)).getByRole("button", { name: `Edit ${model}` })).toBeInTheDocument();
    }
  });
});

describe("Get this model", () => {
  const FILE_LIST = { ...FILES, repo: "Qwen/Qwen3-4B-GGUF" };
  const DONE = downloadStatus({
    state: "succeeded",
    provider: "llamacpp",
    model: TEXT_MODEL,
    model_value: TEXT_MODEL,
    bytes_done: 10,
    bytes_total: 10,
    cache_folder: "~/.cache/huggingface/hub",
    file_path: "/cache/Qwen3-4B-Q8_0.gguf",
    sha256: "a".repeat(64),
  });

  it("downloads the file of the entry's quantisation at the listed revision", async () => {
    const { row, user, server } = await open({
      "GET /v1/model-downloads/files": () => FILE_LIST,
      "POST /v1/model-downloads": () => downloadStatus({ state: "running", provider: "llamacpp", model: TEXT_MODEL, bytes_done: 1, bytes_total: 10 }),
    });
    await user.click(within(row(TEXT_MODEL)).getByRole("button", { name: `Get this model ${TEXT_MODEL}` }));
    await waitFor(() => expect(server.find("POST", "/v1/model-downloads")).toHaveLength(1));
    expect(server.find("POST", "/v1/model-downloads")[0]?.body).toEqual({ provider: "llamacpp", repo: "Qwen/Qwen3-4B-GGUF", revision: FILE_LIST.revision, label: "Q8_0" });
    expect(await within(row(TEXT_MODEL)).findByRole("progressbar", { name: "Download progress" })).toBeInTheDocument();
    expect(within(row(EMBED_MODEL)).queryByRole("progressbar")).toBeNull();
  });

  it("offers Use this model when the download of the entry ends, and saves the file and its hash", async () => {
    const put: unknown[] = [];
    const { row, user } = await open({
      "GET /v1/model-downloads/current": () => DONE,
      "PUT /v1/llamacpp/router/models/qwen3-4b": (body: unknown) => {
        put.push(body);
        return routerStatus({ models: [EMBED_ENTRY, GOT] });
      },
    });
    await user.click(await within(row(TEXT_MODEL)).findByRole("button", { name: "Use this model" }));
    await waitFor(() => expect(put).toEqual([{ model: TEXT_MODEL, file: "/cache/Qwen3-4B-Q8_0.gguf", sha256: "a".repeat(64), revision: "r1" }]));
    await waitFor(() => expect(within(row(TEXT_MODEL)).queryByRole("button", { name: `Get this model ${TEXT_MODEL}` })).toBeNull());
  });

  it("says in plain words why a download could not start", async () => {
    const busy = json({ status: "error", message: "raw text", reason: "busy" }, 409);
    const { row, user } = await open({ "GET /v1/model-downloads/files": () => FILE_LIST, "POST /v1/model-downloads": () => busy });
    await user.click(within(row(TEXT_MODEL)).getByRole("button", { name: `Get this model ${TEXT_MODEL}` }));
    const alert = await within(row(TEXT_MODEL)).findByRole("alert");
    expect(alert).toHaveTextContent("Another model download is already running.");
    expect(alert).not.toHaveTextContent("raw text");
  });
});
