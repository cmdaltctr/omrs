/**
 * llama.cpp router state and writes. Every write puts the status the server
 * returned into the cache, so the page shows what the router holds.
 */
import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "./ApiProvider";
import type { ApiClient } from "./client";
import {
  deleteLlamacppRouterModel,
  getLlamacppRouter,
  restartLlamacppRouter,
  saveLlamacppRouter,
  saveLlamacppRouterModel,
  startLlamacppRouter,
  stopLlamacppRouter,
  type LlamacppRouterChange,
  type LlamacppRouterStatus,
  type RouterModelChange,
} from "./llamacppRouter";
import { currentRevision, rememberRevision, settingsWritten } from "./settingsRevision";

export const llamacppRouterKey = ["llamacpp-router"] as const;

/** Milliseconds between reads while the router starts or a model loads. */
export const STARTING_POLL_MS = 1000;

export const llamacppRouterQuery = (api: ApiClient) =>
  queryOptions({
    queryKey: llamacppRouterKey,
    queryFn: ({ client, signal }) => getLlamacppRouter(api, { signal }).then((status) => rememberRevision(client, status)),
    // Poll only while the router starts or a model loads: both move on by themselves.
    refetchInterval: (query) => (query.state.data?.state === "starting" || query.state.data?.models.some((entry) => entry.state === "loading") === true ? STARTING_POLL_MS : false),
  });

export function useLlamacppRouter() {
  return useQuery(llamacppRouterQuery(useApi()));
}

function useStatusMutation<V>(call: (api: ApiClient, variables: V) => Promise<LlamacppRouterStatus>) {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: V) => call(api, variables),
    onSuccess: (status) => queryClient.setQueryData(llamacppRouterKey, settingsWritten(queryClient, status)),
  });
}

export function useSaveLlamacppRouter() {
  const queryClient = useQueryClient();
  return useStatusMutation<LlamacppRouterChange>((api, change) => saveLlamacppRouter(api, change, { revision: currentRevision(queryClient) }));
}

/** Sets fields of list entry `id`; an `id` that is not in the list adds the entry. */
export function useSaveRouterModel() {
  const queryClient = useQueryClient();
  return useStatusMutation<{ id: string; change: RouterModelChange }>((api, { id, change }) => saveLlamacppRouterModel(api, id, change, { revision: currentRevision(queryClient) }));
}

export function useDeleteRouterModel() {
  const queryClient = useQueryClient();
  return useStatusMutation<string>((api, id) => deleteLlamacppRouterModel(api, id, { revision: currentRevision(queryClient) }));
}

export const useStartLlamacppRouter = () => useStatusMutation<void>((api) => startLlamacppRouter(api));
export const useStopLlamacppRouter = () => useStatusMutation<void>((api) => stopLlamacppRouter(api));
export const useRestartLlamacppRouter = () => useStatusMutation<void>((api) => restartLlamacppRouter(api));
