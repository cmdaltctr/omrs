import type { Experiment, ExperimentEdit, FileEntry, Finding, Notebook, NotebookEntry, Project, Reserved } from "../../api/experimentLibrary";
import { json, type Call, type Handler } from "../../test/fakeDocumentsServer";

/** The library as fixture data. Keys of `files`, `texts` and `output` are `<project>/<folder>[/<name>]`. */
export interface LibraryState {
  projects: Project[];
  experiments: Record<string, Experiment[]>;
  reserved: Record<string, Reserved[]>;
  projectFindings: Record<string, Finding[]>;
  files: Record<string, FileEntry[]>;
  texts: Record<string, string>;
  output: Record<string, string[] | null>;
  /** Newest app save of a file, by `<project>/<folder>/<name>`. */
  lastEdited?: Record<string, ExperimentEdit>;
  /** File keys the server reports as not editable although the name allows it. */
  uneditable?: string[];
  /** User notebooks only; project notebooks come from `projects`. */
  notebooks: Notebook[];
  entries: Record<string, { project_id: string; folder: string; added_at: string }[]>;
}

export function project(id: string, name: string, available = true): Project {
  return { project_id: id, name, root: `/work/${id}`, added_at: "2026-10-20T10:00:00+00:00", available, experiment_count: available ? 0 : null };
}

export function experiment(folder: string, status: string, overrides: Partial<Experiment> = {}): Experiment {
  const [number = "", ...rest] = folder.split("-");
  return {
    folder,
    number,
    title: `Title of ${rest.slice(0, -3).join(" ") || folder}`,
    date: rest.slice(-3).join("-"),
    category: "retrieval",
    size: "Standard",
    purpose: "optimisation",
    status,
    superseded_by: null,
    finding: `Finding of ${folder}.`,
    refs: null,
    migrated: false,
    findings: [],
    ...overrides,
  };
}

export const RERANKER = "1-reranker-threshold-2026-05-12";
export const OVERLAP = "2-chunk-overlap-2026-06-01";
export const OLD_GRAPH = "3-old-graph-2026-04-01";
export const OCR = "1-ocr-quality-2026-07-01";

export const PROTOCOL = [
  "# Protocol",
  "",
  "## Hypothesis",
  "",
  "A threshold of 0.3 keeps recall. See [the report](./report.md) and [the plan](plan.json).",
  "",
  "Read [the paper](https://example.org/paper) and [a sibling](../2-chunk-overlap-2026-06-01/report.md).",
  "",
  "<script>alert(1)</script> and <b>not bold</b>",
  "",
  "| Factor | Levels |",
  "| --- | --- |",
  "| threshold | 0.2, 0.3 |",
].join("\n");

export function emptyLibrary(): LibraryState {
  return { projects: [], experiments: {}, reserved: {}, projectFindings: {}, files: {}, texts: {}, output: {}, notebooks: [], entries: {} };
}

/** Two available projects, one whose folder is gone, and one user notebook with a missing entry. */
export function defaultLibrary(): LibraryState {
  const omrs = RERANKER;
  return {
    projects: [project("p1", "OMRS"), project("p2", "Paper"), project("p3", "Gone", false)],
    experiments: {
      p1: [
        experiment(RERANKER, "PASS", {
          findings: [
            { severity: "warning", code: "report-missing-status", folder: RERANKER, message: "report.md has no status line." },
            { severity: "error", code: "record-invalid", folder: RERANKER, message: "experiment.json has a bad date." },
          ],
          refs: { adrs: ["ADR-018"], changes: [], tasks: [] },
        }),
        experiment(OVERLAP, "FAIL", { category: "ingestion" }),
        experiment(OLD_GRAPH, "SUPERSEDED", { category: "graph", superseded_by: omrs }),
      ],
      p2: [experiment(OCR, "PLANNED", { category: "ingestion", size: "Quick", purpose: "publication" })],
    },
    reserved: { p1: [{ number: "4", reason: "Planned rerun of experiment 2.", ref: "openspec/changes/x" }], p2: [] },
    projectFindings: {
      p1: [
        { severity: "warning", code: "index-stale", folder: null, message: "The EXP_README.md index is out of date." },
        { severity: "error", code: "record-missing", folder: "5-broken-2026-02-01", message: "experiment.json is missing." },
      ],
      p2: [],
    },
    files: {
      [`p1/${RERANKER}`]: [
        { name: "experiment.json", size: 400, viewable: true },
        { name: "plan.json", size: 120, viewable: true },
        { name: "protocol.md", size: 900, viewable: true },
        { name: "report.md", size: 2048, viewable: true },
        { name: "review.html", size: 5120, viewable: false },
      ],
      [`p1/${OVERLAP}`]: [
        { name: "experiment.json", size: 400, viewable: true },
        { name: "results.md", size: 300, viewable: true },
      ],
    },
    texts: {
      [`p1/${RERANKER}/protocol.md`]: PROTOCOL,
      [`p1/${RERANKER}/plan.json`]: '{"factors":["threshold"],"seeds":3}',
      [`p1/${RERANKER}/report.md`]: "# Report\n\nRecall held at **0.91**.",
      [`p1/${RERANKER}/experiment.json`]: '{"format":"omrs-experiment/1"}',
      [`p1/${OVERLAP}/results.md`]: "# Results\n\nOverlap 100 lost recall.",
    },
    output: { [`p1/${RERANKER}`]: ["eval_results.json", "runs"], [`p1/${OVERLAP}`]: null },
    notebooks: [{ notebook_id: "n1", name: "Paper 1", kind: "user", project_id: null, entry_count: 2, created_at: "2026-10-21T09:00:00+00:00" }],
    entries: {
      n1: [
        { project_id: "p2", folder: OCR, added_at: "2026-10-21T09:01:00+00:00" },
        { project_id: "p1", folder: "9-renamed-2026-01-01", added_at: "2026-10-21T09:02:00+00:00" },
      ],
    },
  };
}

/** The time the fake server stamps on every save. */
export const SAVED_AT = "2026-10-26T14:05:00Z";

/** A stand-in for the SHA-256 revision: any change to the text changes it. */
export function fakeRevision(text: string): string {
  let hash = 5381;
  for (const char of text) hash = ((hash * 33) ^ char.charCodeAt(0)) >>> 0;
  return `rev-${hash.toString(16)}-${text.length}`;
}

function segments(call: Call): string[] {
  return call.path.split("?")[0]!.split("/").slice(2).map(decodeURIComponent);
}

const refuse = (message: string, status = 400) => json({ status: "error", message }, status);

/** Handlers for the library routes, as `METHOD /path` keys with `:name` segments. */
export function libraryHandlers(state: LibraryState): Record<string, Handler> {
  const withCount = (item: Project): Project => (item.available ? { ...item, experiment_count: (state.experiments[item.project_id] ?? []).length } : item);
  const findProject = (id: string) => state.projects.find((item) => item.project_id === id);
  const findExperiment = (projectId: string, folder: string) => (state.experiments[projectId] ?? []).find((item) => item.folder === folder);
  const projectNotebook = (item: Project): Notebook => ({
    notebook_id: `project:${item.project_id}`,
    name: item.name,
    kind: "project",
    project_id: item.project_id,
    entry_count: (state.experiments[item.project_id] ?? []).length,
    created_at: null,
  });
  const entryOf = (raw: { project_id: string; folder: string; added_at: string }): NotebookEntry => {
    const found = findExperiment(raw.project_id, raw.folder) ?? null;
    return { ...raw, project_name: findProject(raw.project_id)?.name ?? raw.project_id, missing: found === null, experiment: found };
  };
  const editable = (id: string, folder: string, name: string): boolean => {
    const key = `${id}/${folder}`;
    if ((state.uneditable ?? []).includes(`${key}/${name}`)) return false;
    if (name === "protocol.md" || name === "report.md") return true;
    return name === "results.md" && state.texts[`${key}/report.md`] === undefined;
  };
  const notebookOf = (id: string): Notebook | null => {
    if (id.startsWith("project:")) {
      const item = findProject(id.slice("project:".length));
      return item ? projectNotebook(item) : null;
    }
    const item = state.notebooks.find((candidate) => candidate.notebook_id === id);
    return item ? { ...item, entry_count: (state.entries[id] ?? []).length } : null;
  };

  return {
    "GET /v1/experiment-projects": () => ({ status: "ok", projects: state.projects.map(withCount) }),
    "POST /v1/experiment-projects": (body) => {
      const path = String(body.path ?? "");
      if (!path.startsWith("/")) return refuse("Enter an absolute folder path.");
      if (path.endsWith("/none")) return refuse(`${path} has no experiments directory.`);
      if (state.projects.some((item) => item.root === path)) return refuse("That folder is already a project.", 409);
      const added: Project = { project_id: `p${state.projects.length + 1}`, name: String(body.name ?? ""), root: path, added_at: "t", available: true, experiment_count: 0 };
      state.projects = [...state.projects, added];
      return json({ status: "ok", project: added }, 201);
    },
    "DELETE /v1/experiment-projects/:id": (_body, call) => {
      const [, id] = segments(call);
      state.projects = state.projects.filter((item) => item.project_id !== id);
      return { status: "ok", removed: true };
    },
    "GET /v1/experiment-projects/:id/experiments": (_body, call) => {
      const [, id] = segments(call);
      const item = findProject(id!);
      if (!item) return refuse("Unknown project.", 404);
      if (!item.available) return refuse("The project folder is unavailable.", 404);
      return { status: "ok", project: withCount(item), experiments: state.experiments[id!] ?? [], reserved: state.reserved[id!] ?? [], findings: state.projectFindings[id!] ?? [] };
    },
    "POST /v1/experiment-projects/:id/experiments": (body, call) => {
      const [, id] = segments(call);
      const slug = String(body.slug ?? "");
      if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) return refuse(`The slug ${slug} must be lower-case letters and digits joined by single hyphens.`);
      const list = state.experiments[id!] ?? [];
      const number = body.follow_up ? `${String(body.follow_up)}.1` : String(list.length + 1);
      const folder = `${number}-${slug}-2026-10-25`;
      if (slug === "taken") return refuse(`The folder ${folder} already exists.`);
      state.experiments[id!] = [...list, experiment(folder, "PLANNED", { title: String(body.title), category: String(body.category), size: String(body.size), purpose: body.purpose === "publication" ? "publication" : "optimisation" })];
      if (slug === "bad-readme") {
        const message = "The experiment folder was created, but the index in EXP_README.md was not updated. Run `omrs experiments index --write` to update it.";
        return json({ status: "ok", folder, index: "failed", message }, 201);
      }
      return json({ status: "ok", folder, index: id === "p2" ? "no-readme" : "written" }, 201);
    },
    "GET /v1/experiment-projects/:id/experiments/:folder": (_body, call) => {
      const [, id, , folder] = segments(call);
      const item = findProject(id!);
      const found = findExperiment(id!, folder!);
      if (!item || !found) return refuse("Unknown experiment.", 404);
      const key = `${id}/${folder}`;
      return { status: "ok", project: withCount(item), experiment: found, files: state.files[key] ?? [], output: state.output[key] ?? null };
    },
    "GET /v1/experiment-projects/:id/experiments/:folder/files/:name": (_body, call) => {
      const [, id, , folder, , name] = segments(call);
      const text = state.texts[`${id}/${folder}/${name}`];
      if (text === undefined) return refuse("Unknown file.", 404);
      const truncated = name === "report.md" && text.includes("CUT");
      const key = `${id}/${folder}/${name}`;
      return {
        status: "ok",
        name,
        text,
        truncated,
        size: text.length,
        revision: truncated ? null : fakeRevision(text),
        editable: !truncated && editable(id!, folder!, name!),
        last_edited: state.lastEdited?.[key] ?? null,
      };
    },
    "PUT /v1/experiment-projects/:id/experiments/:folder/files/:name": (body, call) => {
      const [, id, , folder, , name] = segments(call);
      const key = `${id}/${folder}/${name}`;
      const text = state.texts[key];
      const found = findExperiment(id!, folder!);
      if (text === undefined || !found || !editable(id!, folder!, name!)) return refuse("The workspace edits only an existing protocol.md or report file.");
      if (body.base_revision !== fakeRevision(text)) {
        return json({ status: "error", message: "RAW changed on disk", reason: "changed_on_disk" }, 409);
      }
      const next = String(body.text);
      if (next === text) {
        return { status: "ok", name, revision: fakeRevision(text), size: text.length, changed: false, last_edited: state.lastEdited?.[key] ?? null };
      }
      state.texts[key] = next;
      const edit: ExperimentEdit = { edited_at: SAVED_AT, status: found.status, converted: found.migrated };
      state.lastEdited = { ...state.lastEdited, [key]: edit };
      return { status: "ok", name, revision: fakeRevision(next), size: next.length, changed: true, last_edited: edit };
    },
    "GET /v1/notebooks": () => ({ status: "ok", notebooks: [...state.projects.map(projectNotebook), ...state.notebooks.map((item) => notebookOf(item.notebook_id)!)] }),
    "POST /v1/notebooks": (body) => {
      const name = String(body.name ?? "").trim();
      if (name === "") return refuse("Enter a notebook name.");
      if (state.notebooks.some((item) => item.name === name)) return refuse(`A notebook named ${name} already exists.`, 409);
      const created: Notebook = { notebook_id: `n${state.notebooks.length + 1}`, name, kind: "user", project_id: null, entry_count: 0, created_at: "t" };
      state.notebooks = [...state.notebooks, created];
      state.entries[created.notebook_id] = [];
      return json({ status: "ok", notebook: created }, 201);
    },
    "GET /v1/notebooks/:id": (_body, call) => {
      const [, id] = segments(call);
      const notebook = notebookOf(id!);
      if (notebook === null) return refuse("Unknown notebook.", 404);
      const raw =
        notebook.kind === "project"
          ? (state.experiments[notebook.project_id!] ?? []).map((item) => ({ project_id: notebook.project_id!, folder: item.folder, added_at: "t" }))
          : (state.entries[id!] ?? []);
      return { status: "ok", notebook, entries: raw.map(entryOf) };
    },
    "PATCH /v1/notebooks/:id": (body, call) => {
      const [, id] = segments(call);
      if (id!.startsWith("project:")) return refuse("A project notebook cannot be renamed.");
      const name = String(body.name ?? "").trim();
      if (state.notebooks.some((item) => item.name === name && item.notebook_id !== id)) return refuse(`A notebook named ${name} already exists.`, 409);
      state.notebooks = state.notebooks.map((item) => (item.notebook_id === id ? { ...item, name } : item));
      return { status: "ok", notebook: notebookOf(id!) };
    },
    "DELETE /v1/notebooks/:id": (_body, call) => {
      const [, id] = segments(call);
      state.notebooks = state.notebooks.filter((item) => item.notebook_id !== id);
      delete state.entries[id!];
      return { status: "ok", removed: true };
    },
    "PUT /v1/notebooks/:id/entries": (body, call) => {
      const [, id] = segments(call);
      const raw = { project_id: String(body.project_id), folder: String(body.folder), added_at: "t" };
      const list = state.entries[id!] ?? [];
      if (!list.some((item) => item.project_id === raw.project_id && item.folder === raw.folder)) state.entries[id!] = [...list, raw];
      return { status: "ok", entry: entryOf(raw) };
    },
    "DELETE /v1/notebooks/:id/entries/:project/:folder": (_body, call) => {
      const [, id, , projectId, folder] = segments(call);
      state.entries[id!] = (state.entries[id!] ?? []).filter((item) => !(item.project_id === projectId && item.folder === folder));
      return { status: "ok", removed: true };
    },
  };
}
