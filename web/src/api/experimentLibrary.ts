/**
 * Typed client for the experiment library routes: projects, their experiment
 * folders and files, and notebooks.
 *
 * Shapes follow design D5 of `openspec/changes/archive/2026-10-25-experiments-in-web-workspace`
 * and `src/omrs/transports/api/routes/experiment_library.py`. Every path
 * segment is percent-encoded, so a project notebook id such as `project:p1`
 * stays one segment.
 */
import type { ApiClient, CallOptions } from "./client";

export interface Project {
  project_id: string;
  name: string;
  root: string;
  added_at: string;
  /** False when the stored folder is gone; the library then lists no experiments for it. */
  available: boolean;
  experiment_count: number | null;
}

export type FindingSeverity = "error" | "warning" | "info";

export interface Finding {
  severity: FindingSeverity;
  code: string;
  /** Null for a project-level finding. */
  folder: string | null;
  message: string;
}

export interface ExperimentRefs {
  adrs: string[];
  changes: string[];
  tasks: string[];
}

export interface Experiment {
  folder: string;
  number: string;
  title: string;
  date: string;
  category: string | null;
  size: string | null;
  status: string;
  superseded_by: string | null;
  finding: string;
  refs: ExperimentRefs | null;
  migrated: boolean;
  findings: Finding[];
}

export interface Reserved {
  number: string;
  reason: string;
  ref: string;
}

export interface FileEntry {
  name: string;
  size: number;
  /** False for files the app never opens, such as HTML review pages. */
  viewable: boolean;
}

export interface ProjectExperiments {
  project: Project;
  experiments: Experiment[];
  reserved: Reserved[];
  /** Project-level findings: `folder` is null. */
  findings: Finding[];
}

export interface ExperimentDetail {
  project: Project;
  experiment: Experiment;
  files: FileEntry[];
  /** The top-level names in `output/`, or null when the folder has none. */
  output: string[] | null;
}

export interface ExperimentFile {
  name: string;
  text: string;
  /** True when the file is over 1 MiB and `text` holds only its first 1 MiB. */
  truncated: boolean;
  size: number;
}

export interface NewExperiment {
  slug: string;
  title: string;
  category: string;
  size: string;
  follow_up?: string;
}

export type IndexOutcome = "written" | "no-markers" | "no-readme" | "failed";

export interface CreatedExperiment {
  folder: string;
  index: IndexOutcome;
  /** Only with `failed`: the folder exists, but the index was not updated. Names the command that fixes it. */
  message?: string;
}

export interface Notebook {
  notebook_id: string;
  name: string;
  kind: "project" | "user";
  project_id: string | null;
  entry_count: number;
  created_at: string | null;
}

export interface NotebookEntry {
  project_id: string;
  project_name: string;
  folder: string;
  added_at: string;
  /** True when the folder is no longer found; `experiment` is then null. */
  missing: boolean;
  experiment: Experiment | null;
}

export interface NotebookDetail {
  notebook: Notebook;
  entries: NotebookEntry[];
}

const segment = encodeURIComponent;
const projectPath = (projectId: string): string => `/v1/experiment-projects/${segment(projectId)}`;
const experimentPath = (projectId: string, folder: string): string => `${projectPath(projectId)}/experiments/${segment(folder)}`;
const notebookPath = (notebookId: string): string => `/v1/notebooks/${segment(notebookId)}`;

export async function listExperimentProjects(api: ApiClient, options: CallOptions = {}): Promise<Project[]> {
  return (await api.request<{ projects: Project[] }>("GET", "/v1/experiment-projects", { signal: options.signal })).projects;
}

/** Adds a project folder that holds an `experiments/` directory. A refusal is a 400 or 409 with a message. */
export async function addExperimentProject(api: ApiClient, input: { path: string; name: string }, options: CallOptions = {}): Promise<Project> {
  return (await api.request<{ project: Project }>("POST", "/v1/experiment-projects", { body: input, signal: options.signal })).project;
}

/** Removes the project from the list. The files on disk are not touched. */
export async function removeExperimentProject(api: ApiClient, projectId: string, options: CallOptions = {}): Promise<void> {
  await api.request("DELETE", projectPath(projectId), { signal: options.signal });
}

export async function listProjectExperiments(api: ApiClient, projectId: string, options: CallOptions = {}): Promise<ProjectExperiments> {
  const body = await api.request<ProjectExperiments>("GET", `${projectPath(projectId)}/experiments`, { signal: options.signal });
  return { project: body.project, experiments: body.experiments, reserved: body.reserved, findings: body.findings };
}

export async function getProjectExperiment(api: ApiClient, projectId: string, folder: string, options: CallOptions = {}): Promise<ExperimentDetail> {
  const body = await api.request<ExperimentDetail>("GET", experimentPath(projectId, folder), { signal: options.signal });
  return { project: body.project, experiment: body.experiment, files: body.files, output: body.output };
}

/** The text of one top-level file. The server refuses names outside the folder and suffixes it does not serve. */
export async function getExperimentFile(api: ApiClient, projectId: string, folder: string, name: string, options: CallOptions = {}): Promise<ExperimentFile> {
  const body = await api.request<ExperimentFile>("GET", `${experimentPath(projectId, folder)}/files/${segment(name)}`, { signal: options.signal });
  return { name: body.name, text: body.text, truncated: body.truncated, size: body.size };
}

/** Creates an experiment folder with today's date. A blank follow-up number is left out. */
export async function createLibraryExperiment(api: ApiClient, projectId: string, input: NewExperiment, options: CallOptions = {}): Promise<CreatedExperiment> {
  const { follow_up, ...rest } = input;
  const followUp = follow_up?.trim() ?? "";
  const request = followUp === "" ? rest : { ...rest, follow_up: followUp };
  const body = await api.request<CreatedExperiment>("POST", `${projectPath(projectId)}/experiments`, { body: request, signal: options.signal });
  return body.message === undefined ? { folder: body.folder, index: body.index } : { folder: body.folder, index: body.index, message: body.message };
}

/** Project notebooks first, then user notebooks. */
export async function listNotebooks(api: ApiClient, options: CallOptions = {}): Promise<Notebook[]> {
  return (await api.request<{ notebooks: Notebook[] }>("GET", "/v1/notebooks", { signal: options.signal })).notebooks;
}

export async function createNotebook(api: ApiClient, name: string, options: CallOptions = {}): Promise<Notebook> {
  return (await api.request<{ notebook: Notebook }>("POST", "/v1/notebooks", { body: { name }, signal: options.signal })).notebook;
}

export async function renameNotebook(api: ApiClient, notebookId: string, name: string, options: CallOptions = {}): Promise<Notebook> {
  return (await api.request<{ notebook: Notebook }>("PATCH", notebookPath(notebookId), { body: { name }, signal: options.signal })).notebook;
}

/** Deletes a user notebook and its entries. No experiment file changes. */
export async function deleteNotebook(api: ApiClient, notebookId: string, options: CallOptions = {}): Promise<void> {
  await api.request("DELETE", notebookPath(notebookId), { signal: options.signal });
}

export async function getNotebook(api: ApiClient, notebookId: string, options: CallOptions = {}): Promise<NotebookDetail> {
  const body = await api.request<NotebookDetail>("GET", notebookPath(notebookId), { signal: options.signal });
  return { notebook: body.notebook, entries: body.entries };
}

export async function addNotebookEntry(api: ApiClient, notebookId: string, input: { project_id: string; folder: string }, options: CallOptions = {}): Promise<NotebookEntry> {
  return (await api.request<{ entry: NotebookEntry }>("PUT", `${notebookPath(notebookId)}/entries`, { body: input, signal: options.signal })).entry;
}

export async function removeNotebookEntry(api: ApiClient, notebookId: string, projectId: string, folder: string, options: CallOptions = {}): Promise<void> {
  await api.request("DELETE", `${notebookPath(notebookId)}/entries/${segment(projectId)}/${segment(folder)}`, { signal: options.signal });
}
