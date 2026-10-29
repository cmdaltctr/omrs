import { describe, expect, it } from "vitest";
import { FILES, IDLE, REVISION, searchReply, searchResult } from "../settings/test/downloadFixtures";
import { documentsServer } from "../test/fakeDocumentsServer";
import { createApiClient } from "./client";
import { cancelModelDownload, getModelDownload, listModelFiles, searchModels, startModelDownload } from "./modelDownloads";

function setup(handlers: Parameters<typeof documentsServer>[0]) {
  const server = documentsServer(handlers);
  return { server, api: createApiClient(server.fetchImpl) };
}

describe("model download API", () => {
  it("searches with the provider and the text in the query string", async () => {
    const { api, server } = setup({ "GET /v1/model-downloads/search": () => searchReply("llamacpp", [searchResult({ id: "a/b" })]) });
    const reply = await searchModels(api, "llamacpp", "qwen 3");
    expect(reply.results[0]?.id).toBe("a/b");
    expect(server.calls[0]?.path).toBe("/v1/model-downloads/search?provider=llamacpp&q=qwen+3");
  });

  it("lists the files of one repo", async () => {
    const { api, server } = setup({ "GET /v1/model-downloads/files": () => FILES });
    const list = await listModelFiles(api, "llamacpp", "unsloth/Qwen3-4B-GGUF");
    expect(list.revision).toBe(REVISION);
    expect(server.calls[0]?.path).toBe("/v1/model-downloads/files?provider=llamacpp&repo=unsloth%2FQwen3-4B-GGUF");
  });

  it("starts a download with only the keys it is given", async () => {
    const { api, server } = setup({ "POST /v1/model-downloads": () => IDLE });
    await startModelDownload(api, { provider: "ollama", name: "qwen3" });
    await startModelDownload(api, { provider: "llamacpp", repo: "a/b", revision: REVISION, label: "Q4_K_M" });
    expect(server.find("POST", "/v1/model-downloads").map((call) => call.body)).toEqual([
      { provider: "ollama", name: "qwen3" },
      { provider: "llamacpp", repo: "a/b", revision: REVISION, label: "Q4_K_M" },
    ]);
  });

  it("reads and cancels the current download", async () => {
    const { api, server } = setup({ "GET /v1/model-downloads/current": () => IDLE, "DELETE /v1/model-downloads/current": () => ({ ...IDLE, state: "cancelled" }) });
    await expect(getModelDownload(api)).resolves.toMatchObject({ state: "idle" });
    await expect(cancelModelDownload(api)).resolves.toMatchObject({ state: "cancelled" });
    expect(server.find("DELETE", "/v1/model-downloads/current")).toHaveLength(1);
  });
});
