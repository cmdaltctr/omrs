/**
 * The model runtime list and the stop action. A stop puts the item the server
 * returned into the list, so the row shows what the server holds.
 */
import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "./ApiProvider";
import type { ApiClient } from "./client";
import { listModelRuntimes, stopModelRuntime, type ModelRuntime } from "./modelRuntimes";

export const modelRuntimesKey = ["model-runtimes"] as const;

/** Milliseconds between reads while a runtime starts. */
export const STARTING_POLL_MS = 1000;

export const modelRuntimesQuery = (api: ApiClient) =>
  queryOptions({
    queryKey: modelRuntimesKey,
    queryFn: ({ signal }) => listModelRuntimes(api, { signal }),
    // Poll only while a runtime starts: it moves to running or failed on its own.
    refetchInterval: (query) => (query.state.data?.some((item) => item.state === "starting") === true ? STARTING_POLL_MS : false),
  });

export function useModelRuntimes() {
  return useQuery(modelRuntimesQuery(useApi()));
}

export function useStopModelRuntime() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => stopModelRuntime(api, id),
    onSuccess: (item) =>
      queryClient.setQueryData<ModelRuntime[]>(modelRuntimesKey, (list) => list?.map((entry) => (entry.id === item.id ? item : entry))),
  });
}
