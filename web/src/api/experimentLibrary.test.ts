import { describe, expect, it, vi } from "vitest";
import { createApiClient } from "./client";
import {
  addExperimentProject,
  addNotebookEntry,
  createLibraryExperiment,
  createNotebook,
  deleteNotebook,
  getExperimentFile,
  getNotebook,
  getProjectExperiment,
  listExperimentProjects,
  listNotebooks,
  listProjectExperiments,
  removeExperimentProject,
  removeNotebookEntry,
  renameNotebook,
  type Experiment,
  type Notebook,
  type Project,
} from "./experimentLibrary";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function setup(body: unknown, status = 200) {
  const fetchImpl = vi.fn(async (input: string, init?: RequestInit) => {
    void input;
    void init;
    return json(body, status);
  });
  return { fetchImpl, api: createApiClient(fetchImpl) };
}

const PROJECT: Project = { project_id: "p1", name: "OMRS", root: "/work/omrs", added_at: "t", available: true, experiment_count: 2 };
const EXPERIMENT: Experiment = {
  folder: "1-a-2026-01-01",
  number: "1",
  title: "A",
  date: "2026-01-01",
  category: "retrieval",
  size: "Standard",
  status: "PASS",
  superseded_by: null,
  finding: "It worked.",
  refs: null,
  migrated: false,
  findings: [],
};
const NOTEBOOK: Notebook = { notebook_id: "n1", name: "Paper 1", kind: "user", project_id: null, entry_count: 0, created_at: "t" };

describe("experiment library API client", () => {
  it("lists, adds and removes projects", async () => {
    const listed = setup({ status: "ok", projects: [PROJECT] });
    expect(await listExperimentProjects(listed.api)).toEqual([PROJECT]);
    expect(listed.fetchImpl.mock.calls[0]![0]).toBe("/v1/experiment-projects");

    const added = setup({ status: "ok", project: PROJECT }, 201);
    expect(await addExperimentProject(added.api, { path: "/work/omrs", name: "OMRS" })).toEqual(PROJECT);
    const [path, init] = added.fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/experiment-projects");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ path: "/work/omrs", name: "OMRS" });

    const removed = setup({ status: "ok", removed: true });
    await removeExperimentProject(removed.api, "a/b");
    expect(removed.fetchImpl.mock.calls[0]![0]).toBe("/v1/experiment-projects/a%2Fb");
    expect(removed.fetchImpl.mock.calls[0]![1]?.method).toBe("DELETE");
  });

  it("lists a project's experiments with reserved numbers and project findings", async () => {
    const body = { project: PROJECT, experiments: [EXPERIMENT], reserved: [{ number: "9", reason: "r", ref: "x" }], findings: [] };
    const { api, fetchImpl } = setup({ status: "ok", ...body });
    expect(await listProjectExperiments(api, "p1")).toEqual(body);
    expect(fetchImpl.mock.calls[0]![0]).toBe("/v1/experiment-projects/p1/experiments");
  });

  it("reads one experiment and one file, encoding every segment", async () => {
    const one = setup({ status: "ok", project: PROJECT, experiment: EXPERIMENT, files: [{ name: "report.md", size: 3, viewable: true }], output: null });
    expect((await getProjectExperiment(one.api, "p1", "a b")).output).toBeNull();
    expect(one.fetchImpl.mock.calls[0]![0]).toBe("/v1/experiment-projects/p1/experiments/a%20b");

    const file = setup({ status: "ok", name: "report.md", text: "# R", truncated: false, size: 3 });
    expect(await getExperimentFile(file.api, "p1", "f", "report.md")).toEqual({ name: "report.md", text: "# R", truncated: false, size: 3 });
    expect(file.fetchImpl.mock.calls[0]![0]).toBe("/v1/experiment-projects/p1/experiments/f/files/report.md");
  });

  it("creates an experiment and leaves out a blank follow-up", async () => {
    const { api, fetchImpl } = setup({ status: "ok", folder: "51-ocr-2026-10-25", index: "written" }, 201);
    const created = await createLibraryExperiment(api, "p1", { slug: "ocr", title: "OCR", category: "ingestion", size: "Standard", follow_up: " " });
    expect(created).toEqual({ folder: "51-ocr-2026-10-25", index: "written" });
    const [path, init] = fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/experiment-projects/p1/experiments");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ slug: "ocr", title: "OCR", category: "ingestion", size: "Standard" });

    const follow = setup({ status: "ok", folder: "12.1-ocr-2026-10-25", index: "no-markers" }, 201);
    await createLibraryExperiment(follow.api, "p1", { slug: "ocr", title: "OCR", category: "ingestion", size: "Quick", follow_up: " 12 " });
    expect(JSON.parse(String(follow.fetchImpl.mock.calls[0]![1]?.body))).toMatchObject({ follow_up: "12" });

    const failed = setup({ status: "ok", folder: "52-ocr-2026-10-25", index: "failed", message: "Run `omrs experiments index --write`." }, 201);
    expect(await createLibraryExperiment(failed.api, "p1", { slug: "ocr", title: "OCR", category: "ingestion", size: "Quick" })).toEqual({
      folder: "52-ocr-2026-10-25",
      index: "failed",
      message: "Run `omrs experiments index --write`.",
    });
  });

  it("lists, creates, renames and deletes notebooks; a project notebook id is encoded", async () => {
    const listed = setup({ status: "ok", notebooks: [NOTEBOOK] });
    expect(await listNotebooks(listed.api)).toEqual([NOTEBOOK]);
    expect(listed.fetchImpl.mock.calls[0]![0]).toBe("/v1/notebooks");

    const created = setup({ status: "ok", notebook: NOTEBOOK }, 201);
    expect(await createNotebook(created.api, "Paper 1")).toEqual(NOTEBOOK);
    expect(JSON.parse(String(created.fetchImpl.mock.calls[0]![1]?.body))).toEqual({ name: "Paper 1" });

    const renamed = setup({ status: "ok", notebook: { ...NOTEBOOK, name: "Paper 2" } });
    expect((await renameNotebook(renamed.api, "n1", "Paper 2")).name).toBe("Paper 2");
    expect(renamed.fetchImpl.mock.calls[0]![1]?.method).toBe("PATCH");

    const deleted = setup({ status: "ok", removed: true });
    await deleteNotebook(deleted.api, "n1");
    expect(deleted.fetchImpl.mock.calls[0]![1]?.method).toBe("DELETE");

    const read = setup({ status: "ok", notebook: NOTEBOOK, entries: [] });
    expect(await getNotebook(read.api, "project:p1")).toEqual({ notebook: NOTEBOOK, entries: [] });
    expect(read.fetchImpl.mock.calls[0]![0]).toBe("/v1/notebooks/project%3Ap1");
  });

  it("adds and removes a notebook entry", async () => {
    const entry = { project_id: "p1", project_name: "OMRS", folder: "f", added_at: "t", missing: false, experiment: EXPERIMENT };
    const added = setup({ status: "ok", entry });
    expect(await addNotebookEntry(added.api, "n1", { project_id: "p1", folder: "f" })).toEqual(entry);
    const [path, init] = added.fetchImpl.mock.calls[0]!;
    expect(path).toBe("/v1/notebooks/n1/entries");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ project_id: "p1", folder: "f" });

    const removed = setup({ status: "ok", removed: true });
    await removeNotebookEntry(removed.api, "n1", "p1", "a b");
    expect(removed.fetchImpl.mock.calls[0]![0]).toBe("/v1/notebooks/n1/entries/p1/a%20b");
    expect(removed.fetchImpl.mock.calls[0]![1]?.method).toBe("DELETE");
  });
});
