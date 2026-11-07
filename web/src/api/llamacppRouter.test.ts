import { describe, expect, it } from "vitest";
import { documentsServer } from "../test/fakeDocumentsServer";
import { ROUTER_STOPPED } from "../settings/test/fixtures";
import { DOWNLOADS_NEEDED_BOTH } from "../settings/test/llamacppFixtures";
import { createApiClient } from "./client";
import { deleteLlamacppRouterModel, getLlamacppRouter, getLlamacppRouterDownloads, restartLlamacppRouter, saveLlamacppRouter, saveLlamacppRouterModel, startLlamacppRouter, stopLlamacppRouter } from "./llamacppRouter";

function setup(handlers: Parameters<typeof documentsServer>[0]) {
  const server = documentsServer(handlers);
  return { server, api: createApiClient(server.fetchImpl) };
}

describe("llama.cpp router API", () => {
  it("reads the status and the model list", async () => {
    const { api } = setup({ "GET /v1/llamacpp/router": () => ROUTER_STOPPED });
    const status = await getLlamacppRouter(api);
    expect(status).toMatchObject({ state: "stopped", reason: null, mode: "managed" });
    expect(status.models.map((entry) => entry.id)).toEqual(["qwen3-embedding-4b", "qwen3-4b"]);
  });

  it("reads the downloads a Start needs with GET and no body", async () => {
    const { api, server } = setup({ "GET /v1/llamacpp/router/downloads-needed": () => DOWNLOADS_NEEDED_BOTH });
    const needed = await getLlamacppRouterDownloads(api);
    expect(needed.models.map((item) => item.id)).toEqual(["qwen3-embedding-4b", "qwen3-4b"]);
    expect(needed.total_bytes).toBe(DOWNLOADS_NEEDED_BOTH.total_bytes);
    expect(server.find("GET", "/v1/llamacpp/router/downloads-needed")).toHaveLength(1);
  });

  it("saves only the keys it is given", async () => {
    const { api, server } = setup({ "PUT /v1/llamacpp/router": () => ROUTER_STOPPED });
    await saveLlamacppRouter(api, { models_max: 2 });
    await saveLlamacppRouter(api, { memory_margin_mib: null }, { revision: "r1" });
    expect(server.find("PUT", "/v1/llamacpp/router").map((call) => call.body)).toEqual([{ models_max: 2 }, { memory_margin_mib: null, revision: "r1" }]);
  });

  it("saves one list entry by id and sends the revision", async () => {
    const { api, server } = setup({ "PUT /v1/llamacpp/router/models/qwen3-4b": () => ROUTER_STOPPED });
    await saveLlamacppRouterModel(api, "qwen3-4b", { preset: { "ctx-size": 16384 } }, { revision: "r1" });
    expect(server.find("PUT", "/v1/llamacpp/router/models/qwen3-4b")[0]?.body).toEqual({ preset: { "ctx-size": 16384 }, revision: "r1" });
  });

  it("removes one list entry and sends the revision as a query", async () => {
    const { api, server } = setup({ "DELETE /v1/llamacpp/router/models/qwen3-4b": () => ROUTER_STOPPED });
    await deleteLlamacppRouterModel(api, "qwen3-4b", { revision: "r1" });
    expect(server.find("DELETE", "/v1/llamacpp/router/models/qwen3-4b")).toHaveLength(1);
  });

  it("starts, stops and restarts with POST and no body", async () => {
    const { api, server } = setup({
      "POST /v1/llamacpp/router/start": () => ROUTER_STOPPED,
      "POST /v1/llamacpp/router/stop": () => ROUTER_STOPPED,
      "POST /v1/llamacpp/router/restart": () => ROUTER_STOPPED,
    });
    await startLlamacppRouter(api);
    await stopLlamacppRouter(api);
    await restartLlamacppRouter(api);
    expect(server.find("POST", "/v1/llamacpp/router/start")).toHaveLength(1);
    expect(server.find("POST", "/v1/llamacpp/router/stop")).toHaveLength(1);
    expect(server.find("POST", "/v1/llamacpp/router/restart")).toHaveLength(1);
  });
});
