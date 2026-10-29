import type { DownloadState } from "../api/modelDownloads";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { REASON_SENTENCES } from "./modelDownloadWords";
import { downloadStatus, FILES, REVISION, searchReply, searchResult } from "./test/downloadFixtures";
import { settingsServer } from "./test/fixtures";

async function open(handlers = {}) {
  const server = settingsServer(handlers);
  startApp("#/settings/providers", server);
  await screen.findByRole("heading", { level: 3, name: "llama.cpp" });
  const card = (name: string) => screen.getByRole("region", { name });
  const panel = (name: string) => within(card(name)).getByRole("group", { name: "Get a model" });
  return { server, user: userEvent.setup(), card, panel };
}

const LLAMA_SEARCH = { "GET /v1/model-downloads/search": () => searchReply("llamacpp", [searchResult({ id: "unsloth/Qwen3-4B-GGUF" })]), "GET /v1/model-downloads/files": () => FILES };

describe("Get a model panel on the provider cards", () => {
  it("shows on the Ollama and llama.cpp cards and not on the OpenRouter card", async () => {
    const { card } = await open();
    expect(within(card("Ollama")).getByRole("group", { name: "Get a model" })).toBeInTheDocument();
    expect(within(card("llama.cpp")).getByRole("group", { name: "Get a model" })).toBeInTheDocument();
    expect(within(card("OpenRouter")).queryByRole("group", { name: "Get a model" })).toBeNull();
    expect(within(card("OpenRouter")).queryByText("Search for a model")).toBeNull();
  });

  it("searches, lists the files and starts the llama.cpp download with the revision", async () => {
    const posts: unknown[] = [];
    const { user, panel } = await open({
      ...LLAMA_SEARCH,
      "POST /v1/model-downloads": (body: unknown) => {
        posts.push(body);
        return json(downloadStatus({ state: "running", provider: "llamacpp", model: "unsloth/Qwen3-4B-GGUF:Q4_K_M", bytes_done: 1024 ** 3, bytes_total: 4 * 1024 ** 3 }), 202);
      },
    });
    await user.type(within(panel("llama.cpp")).getByRole("textbox", { name: "Search for a model" }), "qwen");
    await user.click(await within(panel("llama.cpp")).findByRole("button", { name: /unsloth\/Qwen3-4B-GGUF/ }));
    await user.click(await within(panel("llama.cpp")).findByRole("button", { name: "Download" }));
    expect(posts).toEqual([{ provider: "llamacpp", repo: "unsloth/Qwen3-4B-GGUF", revision: REVISION, label: "Q4_K_M" }]);
    expect(await within(panel("llama.cpp")).findByRole("progressbar", { name: "Download progress" })).toHaveAttribute("aria-valuenow", "25");
  });

  it("does not show an old cancelled job after the page loads", async () => {
    const { panel } = await open({ "GET /v1/model-downloads/current": () => downloadStatus({ state: "cancelled", provider: "llamacpp", model: "unsloth/Qwen3-4B-GGUF:Q4_K_M" }) });
    await within(panel("llama.cpp")).findByRole("textbox", { name: "Search for a model" });
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(within(panel("llama.cpp")).queryByText("The download stopped.")).toBeNull();
  });

  it("says the download stopped after the person presses Cancel", async () => {
    let state: DownloadState = "running";
    const { user, panel } = await open({
      "GET /v1/model-downloads/current": () => downloadStatus({ state, provider: "llamacpp", model: "unsloth/Qwen3-4B-GGUF:Q4_K_M", bytes_done: 1, bytes_total: 4 }),
      "DELETE /v1/model-downloads/current": () => ((state = "cancelled"), downloadStatus({ state: "cancelled", provider: "llamacpp", model: "unsloth/Qwen3-4B-GGUF:Q4_K_M" })),
    });
    await user.click(await within(panel("llama.cpp")).findByRole("button", { name: "Cancel" }));
    expect(await within(panel("llama.cpp")).findByText("The download stopped.")).toBeInTheDocument();
  });

  it("shows an error when Cancel fails", async () => {
    const { user, panel } = await open({
      "GET /v1/model-downloads/current": () => downloadStatus({ state: "running", provider: "llamacpp", model: "unsloth/Qwen3-4B-GGUF:Q4_K_M", bytes_done: 1, bytes_total: 4 }),
      "DELETE /v1/model-downloads/current": () => json({ status: "error", message: "No model download running." }, 409),
    });
    await user.click(await within(panel("llama.cpp")).findByRole("button", { name: "Cancel" }));
    expect(await within(panel("llama.cpp")).findByRole("alert")).toBeInTheDocument();
  });

  it("pulls a typed Ollama name with a tag", async () => {
    const posts: unknown[] = [];
    const { user, panel } = await open({
      "GET /v1/model-downloads/search": () => searchReply("ollama", []),
      "POST /v1/model-downloads": (body: unknown) => (posts.push(body), downloadStatus({ state: "running", provider: "ollama", model: "smollm2:135m" })),
    });
    await user.type(within(panel("Ollama")).getByRole("textbox", { name: "Search for a model" }), "smollm2:135m");
    await user.click(await within(panel("Ollama")).findByRole("button", { name: /smollm2:135m/ }));
    expect(within(panel("Ollama")).getByText("Ollama pulls this tag.")).toBeInTheDocument();
    await user.click(within(panel("Ollama")).getByRole("button", { name: "Download" }));
    expect(posts).toEqual([{ provider: "ollama", name: "smollm2:135m" }]);
  });

  it("offers no typed name on the llama.cpp card", async () => {
    const { user, panel } = await open({ "GET /v1/model-downloads/search": () => searchReply("llamacpp", []) });
    await user.type(within(panel("llama.cpp")).getByRole("textbox", { name: "Search for a model" }), "smollm2:135m");
    expect(await within(panel("llama.cpp")).findByText("No model matches that search.")).toBeInTheDocument();
    expect(within(panel("llama.cpp")).queryByText("Typed name")).toBeNull();
  });

  it("pulls an Ollama library name by name alone", async () => {
    const posts: unknown[] = [];
    const { user, panel } = await open({
      "GET /v1/model-downloads/search": () => searchReply("ollama", [searchResult({ id: "qwen3", source: "ollama-library", downloads: null, likes: null, last_modified: null })]),
      "POST /v1/model-downloads": (body: unknown) => (posts.push(body), downloadStatus({ state: "running", provider: "ollama", model: "qwen3" })),
    });
    await user.type(within(panel("Ollama")).getByRole("textbox", { name: "Search for a model" }), "qwen");
    await user.click(await within(panel("Ollama")).findByRole("button", { name: /qwen3/ }));
    await user.click(await within(panel("Ollama")).findByRole("button", { name: "Download" }));
    expect(posts).toEqual([{ provider: "ollama", name: "qwen3" }]);
    expect(await within(panel("Ollama")).findByText("Size known after the pull starts")).toBeInTheDocument();
  });

  it("opens the file list of an hf.co result with org/name and pulls repo and label", async () => {
    const posts: unknown[] = [];
    const { server, user, panel } = await open({
      "GET /v1/model-downloads/search": () => searchReply("ollama", [searchResult({ id: "hf.co/unsloth/Qwen3-4B-GGUF" })]),
      "GET /v1/model-downloads/files": () => FILES,
      "POST /v1/model-downloads": (body: unknown) => (posts.push(body), downloadStatus({ state: "running", provider: "ollama", model: "hf.co/unsloth/Qwen3-4B-GGUF:Q4_K_M" })),
    });
    await user.type(within(panel("Ollama")).getByRole("textbox", { name: "Search for a model" }), "qwen");
    await user.click(await within(panel("Ollama")).findByRole("button", { name: /hf\.co\/unsloth\/Qwen3-4B-GGUF/ }));
    await user.click(await within(panel("Ollama")).findByRole("button", { name: "Download" }));
    expect(server.exact("GET", "/v1/model-downloads/files")[0]?.path).toBe("/v1/model-downloads/files?provider=ollama&repo=unsloth%2FQwen3-4B-GGUF");
    expect(posts).toEqual([{ provider: "ollama", repo: "unsloth/Qwen3-4B-GGUF", label: "Q4_K_M" }]);
  });

  it("shows the busy line when the server refuses a start", async () => {
    const { user, panel } = await open({
      ...LLAMA_SEARCH,
      "POST /v1/model-downloads": () => json({ status: "error", message: "A download is running.", reason: "busy" }, 409),
    });
    await user.type(within(panel("llama.cpp")).getByRole("textbox", { name: "Search for a model" }), "qwen");
    await user.click(await within(panel("llama.cpp")).findByRole("button", { name: /unsloth\/Qwen3-4B-GGUF/ }));
    await user.click(await within(panel("llama.cpp")).findByRole("button", { name: "Download" }));
    expect(await within(panel("llama.cpp")).findByRole("alert")).toHaveTextContent(REASON_SENTENCES.busy);
  });

  it("shows a download that already runs and cancels it", async () => {
    let state = downloadStatus({ state: "running", provider: "llamacpp", model: "a/b:Q4_K_M", bytes_done: 10, bytes_total: 100 });
    const { server, user, panel } = await open({
      "GET /v1/model-downloads/current": () => state,
      "DELETE /v1/model-downloads/current": () => (state = downloadStatus({ state: "cancelled", provider: "llamacpp", model: "a/b:Q4_K_M" })),
    });
    await user.click(await within(panel("llama.cpp")).findByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(server.exact("DELETE", "/v1/model-downloads/current")).toHaveLength(1));
    expect(await within(panel("llama.cpp")).findByText("The download stopped.")).toBeInTheDocument();
  });

  it("does not show another provider's download on this card, and disables Download while it runs", async () => {
    const { user, panel } = await open({
      ...LLAMA_SEARCH,
      "GET /v1/model-downloads/current": () => downloadStatus({ state: "running", provider: "ollama", model: "qwen3", bytes_done: 1, bytes_total: 10 }),
    });
    expect(within(panel("llama.cpp")).queryByRole("progressbar")).toBeNull();
    await user.type(within(panel("llama.cpp")).getByRole("textbox", { name: "Search for a model" }), "qwen");
    await user.click(await within(panel("llama.cpp")).findByRole("button", { name: /unsloth\/Qwen3-4B-GGUF/ }));
    expect(await within(panel("llama.cpp")).findByRole("button", { name: "Download" })).toBeDisabled();
  });
});
