/**
 * Typed client for opening a Library experiment in marimo.
 *
 * Shapes follow design D5 of `openspec/changes/open-experiment-in-marimo` and
 * `src/omrs/transports/api/routes/experiment_editor.py`. The request names no
 * path, flag or argument: the server finds the notebook from the project and
 * folder. The token arrives once in the response body and never in a URL.
 */
import type { ApiClient, CallOptions } from "./client";
import type { TokenDelivery } from "./plugins";

/** Whether the server converted `analysis.py`, created an empty notebook or opened one that was there. */
export type NotebookState = "converted" | "created" | "existing";

export interface KernelEnvironment {
  kind: "project";
  python: string;
  marimo_in_project: boolean;
  /** Packages that marimo's own environment shadows with a different version. */
  shadowed: string[];
}

export interface ExperimentEditorOpened {
  status: "ok";
  launch_id: string;
  plugin: string;
  project_id: string;
  folder: string;
  notebook: string;
  notebook_state: NotebookState;
  /** True when `analysis.py` changed after the notebook was made. */
  source_newer: boolean;
  environment: KernelEnvironment;
  url_without_token: string;
  token_delivery: TokenDelivery;
  trust_notice: string;
}

const segment = encodeURIComponent;

/** Opening runs notebook Python with the user's full access, so the page calls this only after consent. */
export function openExperimentEditor(api: ApiClient, projectId: string, folder: string, options: CallOptions = {}): Promise<ExperimentEditorOpened> {
  const path = `/v1/experiment-projects/${segment(projectId)}/experiments/${segment(folder)}/editor`;
  return api.request<ExperimentEditorOpened>("POST", path, { body: { consent: true }, signal: options.signal });
}
