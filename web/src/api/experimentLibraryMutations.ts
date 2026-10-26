/**
 * Writes for the experiment library. A project or experiment change refreshes
 * every key under `["experiment-projects"]` and the notebooks, because each
 * project is also a notebook. A notebook change refreshes `["notebooks"]` only.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useApi } from "./ApiProvider";
import { openExperimentEditor } from "./experimentEditor";
import {
  addExperimentProject,
  addNotebookEntry,
  createLibraryExperiment,
  createNotebook,
  deleteNotebook,
  removeExperimentProject,
  removeNotebookEntry,
  renameNotebook,
  type NewExperiment,
} from "./experimentLibrary";
import { queryKeys } from "./queries";

function useRefreshProjects() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.experimentProjects() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.notebooks() }),
    ]);
}

function useRefreshNotebooks() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.notebooks() });
}

export function useAddExperimentProject() {
  const api = useApi();
  const refresh = useRefreshProjects();
  return useMutation({ mutationFn: (input: { path: string; name: string }) => addExperimentProject(api, input), onSuccess: refresh });
}

export function useRemoveExperimentProject() {
  const api = useApi();
  const refresh = useRefreshProjects();
  return useMutation({ mutationFn: (projectId: string) => removeExperimentProject(api, projectId), onSuccess: refresh });
}

export function useCreateLibraryExperiment() {
  const api = useApi();
  const refresh = useRefreshProjects();
  return useMutation({
    mutationFn: (input: { projectId: string; experiment: NewExperiment }) => createLibraryExperiment(api, input.projectId, input.experiment),
    onSuccess: refresh,
  });
}

export function useCreateNotebook() {
  const api = useApi();
  const refresh = useRefreshNotebooks();
  return useMutation({ mutationFn: (name: string) => createNotebook(api, name), onSuccess: refresh });
}

export function useRenameNotebook() {
  const api = useApi();
  const refresh = useRefreshNotebooks();
  return useMutation({
    mutationFn: (input: { notebookId: string; name: string }) => renameNotebook(api, input.notebookId, input.name),
    onSuccess: refresh,
  });
}

export function useDeleteNotebook() {
  const api = useApi();
  const refresh = useRefreshNotebooks();
  return useMutation({ mutationFn: (notebookId: string) => deleteNotebook(api, notebookId), onSuccess: refresh });
}

export function useAddNotebookEntry() {
  const api = useApi();
  const refresh = useRefreshNotebooks();
  return useMutation({
    mutationFn: (input: { notebookId: string; projectId: string; folder: string }) =>
      addNotebookEntry(api, input.notebookId, { project_id: input.projectId, folder: input.folder }),
    onSuccess: refresh,
  });
}

export function useRemoveNotebookEntry() {
  const api = useApi();
  const refresh = useRefreshNotebooks();
  return useMutation({
    mutationFn: (input: { notebookId: string; projectId: string; folder: string }) => removeNotebookEntry(api, input.notebookId, input.projectId, input.folder),
    onSuccess: refresh,
  });
}

/**
 * Opens the experiment in marimo. The response holds the editor token, so the
 * mutation cache keeps nothing (`gcTime: 0`). A refusal can name an editor
 * that already runs, so the plugin list refreshes either way.
 */
export function useOpenExperimentEditor() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    gcTime: 0,
    mutationFn: (input: { projectId: string; folder: string }) => openExperimentEditor(api, input.projectId, input.folder),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.plugins() }),
  });
}
