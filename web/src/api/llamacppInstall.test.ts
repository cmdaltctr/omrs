import { describe, expect, it } from "vitest";
import { documentsServer } from "../test/fakeDocumentsServer";
import { createApiClient } from "./client";
import { getLlamacppBuild, installLlamacppBuild, type LlamacppBuild } from "./llamacppInstall";

export const BUILD: LlamacppBuild = {
  status: "ok",
  build: "b11941",
  detected: "cuda",
  choices: ["cpu", "cuda"],
  installed_path: null,
  job: { state: "idle", flavour: null, line: null, reason: null, message: null },
};

function setup(handlers: Parameters<typeof documentsServer>[0]) {
  const server = documentsServer(handlers);
  return { server, api: createApiClient(server.fetchImpl) };
}

describe("llama.cpp build API", () => {
  it("reads the pinned build and the detected flavour", async () => {
    const { api } = setup({ "GET /v1/llamacpp/router/install": () => BUILD });
    await expect(getLlamacppBuild(api)).resolves.toMatchObject({ build: "b11941", detected: "cuda", choices: ["cpu", "cuda"] });
  });

  it("names the flavour in the install request, and sends an empty body for the detected one", async () => {
    const { api, server } = setup({ "POST /v1/llamacpp/router/install": () => BUILD });
    await installLlamacppBuild(api, "cpu");
    await installLlamacppBuild(api, null);
    expect(server.find("POST", "/v1/llamacpp/router/install").map((call) => call.body)).toEqual([{ flavour: "cpu" }, {}]);
  });
});
