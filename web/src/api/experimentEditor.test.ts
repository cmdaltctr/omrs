import { describe, expect, it } from "vitest";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { createApiClient } from "./client";
import { openExperimentEditor, type ExperimentEditorOpened } from "./experimentEditor";
import { listPlugins } from "./plugins";

const OPENED: ExperimentEditorOpened = {
  status: "ok",
  launch_id: "launch_7",
  plugin: "marimo",
  project_id: "p:1",
  folder: "34-worker sample-2026-09-19",
  notebook: "analysis.marimo.py",
  notebook_state: "converted",
  source_newer: false,
  environment: { kind: "project", python: "3.14", marimo_in_project: false, shadowed: ["starlette"] },
  url_without_token: "http://127.0.0.1:2719/",
  token_delivery: { method: "response_body_once", token: "editor-secret" },
  trust_notice: "Trust text.",
};

describe("experiment editor client", () => {
  it("posts consent to the encoded editor path and returns the 201 body", async () => {
    const server = documentsServer({ "POST /v1/experiment-projects/:id/experiments/:folder/editor": () => json(OPENED, 201) });
    const api = createApiClient(server.fetchImpl);
    const opened = await openExperimentEditor(api, "p:1", "34-worker sample-2026-09-19");
    expect(opened).toEqual(OPENED);
    expect(server.calls).toHaveLength(1);
    expect(server.calls[0]!.method).toBe("POST");
    expect(server.calls[0]!.path).toBe("/v1/experiment-projects/p%3A1/experiments/34-worker%20sample-2026-09-19/editor");
    expect(server.calls[0]!.body).toEqual({ consent: true });
  });

  it("keeps a folder with a slash in one path segment", async () => {
    const server = documentsServer({ "POST /v1/experiment-projects/:id/experiments/:folder/editor": () => json(OPENED, 201) });
    await openExperimentEditor(createApiClient(server.fetchImpl), "p1", "a/b");
    expect(server.calls[0]!.path).toBe("/v1/experiment-projects/p1/experiments/a%2Fb/editor");
  });

  it("reads the shipped manifests and the Library fields of running editors", async () => {
    const editor = { launch_id: "l1", plugin: "marimo", notebook: "/w/p1/experiments/x/analysis.marimo.py", experiment_context: null, url_without_token: "http://127.0.0.1:2719/", project_id: "p1", folder: "x" };
    const server = documentsServer({
      "GET /v1/plugins": () => ({ status: "ok", plugins: [], editors: [editor], install_hint: "h", trust_notice: "t", shipped_manifests: ["/site/omrs/core/plugins/shipped/marimo/manifest.json"], detected_executables: {} }),
    });
    const list = await listPlugins(createApiClient(server.fetchImpl));
    expect(list.shipped_manifests).toEqual(["/site/omrs/core/plugins/shipped/marimo/manifest.json"]);
    expect(list.editors[0]!.project_id).toBe("p1");
    expect(list.editors[0]!.folder).toBe("x");
  });
});
