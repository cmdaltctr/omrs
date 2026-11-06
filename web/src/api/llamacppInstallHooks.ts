/**
 * The pinned llama.cpp build and its install job. The build is read once and
 * then every second while the job runs. A start puts the answer into the
 * cache, and a finished job makes the router status stale: the program in
 * force may have changed.
 */
import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "./ApiProvider";
import type { ApiClient } from "./client";
import { getLlamacppBuild, installLlamacppBuild, type LlamacppBuild, type LlamacppFlavour } from "./llamacppInstall";
import { llamacppRouterKey } from "./llamacppRouterHooks";

export const llamacppBuildKey = ["llamacpp-build"] as const;

/** Milliseconds between reads while the install job runs. */
export const INSTALL_POLL_MS = 1000;

export const llamacppBuildQuery = (api: ApiClient) =>
  queryOptions({
    queryKey: llamacppBuildKey,
    queryFn: ({ client, signal }) =>
      getLlamacppBuild(api, { signal }).then((build) => {
        // A finished job may have placed the program, so the router status is read again.
        if (build.job.state === "succeeded") void client.invalidateQueries({ queryKey: llamacppRouterKey });
        return build;
      }),
    refetchInterval: (query) => (query.state.data?.job.state === "running" ? INSTALL_POLL_MS : false),
  });

export function useLlamacppBuild() {
  return useQuery(llamacppBuildQuery(useApi()));
}

export function useInstallLlamacppBuild() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (flavour: LlamacppFlavour | null) => installLlamacppBuild(api, flavour),
    onSuccess: (build: LlamacppBuild) => {
      queryClient.setQueryData(llamacppBuildKey, build);
      void queryClient.invalidateQueries({ queryKey: llamacppRouterKey });
    },
  });
}
