/**
 * Reads and writes of the decision models and document routers. Each write
 * puts the list the server returned into the cache and marks the other list
 * stale, because a router shows the state of its model and a model shows the
 * routers that name it.
 */
import { queryOptions, useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useApi } from "./ApiProvider";
import type { ApiClient } from "./client";
import {
  deleteDecisionModel,
  deleteDocumentRouter,
  listDecisionModels,
  listDocumentRouters,
  renameDocumentRouter,
  saveDecisionModel,
  saveDocumentRouter,
  testDecisionModel,
  type DecisionModelEntry,
  type DecisionModelList,
  type DocumentRouterEntry,
  type DocumentRouterList,
} from "./routerMaps";
import { currentRevision, rememberRevision, settingsWritten } from "./settingsRevision";

// Under "settings", so a reload after a file conflict reads them again.
export const decisionModelsKey = ["settings", "decision-models"] as const;
export const documentRoutersKey = ["settings", "document-routers"] as const;

export const decisionModelsQuery = (api: ApiClient) =>
  queryOptions({ queryKey: decisionModelsKey, queryFn: ({ client, signal }) => listDecisionModels(api, { signal }).then((data) => rememberRevision(client, data)) });

export const documentRoutersQuery = (api: ApiClient) =>
  queryOptions({ queryKey: documentRoutersKey, queryFn: ({ client, signal }) => listDocumentRouters(api, { signal }).then((data) => rememberRevision(client, data)) });

function keepModels(queryClient: QueryClient, list: DecisionModelList) {
  queryClient.setQueryData(decisionModelsKey, settingsWritten(queryClient, list));
  return queryClient.invalidateQueries({ queryKey: documentRoutersKey });
}

function keepRouters(queryClient: QueryClient, list: DocumentRouterList) {
  queryClient.setQueryData(documentRoutersKey, settingsWritten(queryClient, list));
  return queryClient.invalidateQueries({ queryKey: decisionModelsKey });
}

export function useSaveDecisionModel() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, entry }: { name: string; entry: DecisionModelEntry }) => saveDecisionModel(api, name, entry, { revision: currentRevision(queryClient) }),
    onSuccess: (list) => keepModels(queryClient, list),
  });
}

export function useDeleteDecisionModel() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => deleteDecisionModel(api, name, { revision: currentRevision(queryClient) }),
    onSuccess: (list) => keepModels(queryClient, list),
  });
}

/** The result is kept only while the row shows it (`gcTime: 0`). */
export function useTestDecisionModel() {
  const api = useApi();
  return useMutation({ mutationFn: (name: string) => testDecisionModel(api, name), gcTime: 0 });
}

export function useSaveDocumentRouter() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, entry }: { name: string; entry: DocumentRouterEntry }) => saveDocumentRouter(api, name, entry, { revision: currentRevision(queryClient) }),
    onSuccess: (list) => keepRouters(queryClient, list),
  });
}

export function useDeleteDocumentRouter() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => deleteDocumentRouter(api, name, { revision: currentRevision(queryClient) }),
    onSuccess: (list) => keepRouters(queryClient, list),
  });
}

export function useRenameDocumentRouter() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, newName }: { name: string; newName: string }) => renameDocumentRouter(api, name, newName, { revision: currentRevision(queryClient) }),
    onSuccess: (list) => keepRouters(queryClient, list),
  });
}
