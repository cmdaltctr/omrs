/**
 * The queries and mutations of the "Get a model" panel. The current download
 * is read once and then every second while it runs. A start or a cancel puts
 * the status the server returned into the cache, so the panel shows it at once.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { cancelModelDownload, modelDownloadKeys, modelDownloadQuery, modelFilesQuery, modelSearchQuery, providerModelsQuery, startModelDownload, type ModelDownloadStatus, type StartModelDownload } from "../api/modelDownloads";

export function useModelDownload() {
  return useQuery(modelDownloadQuery(useApi()));
}

export function useStartModelDownload() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: StartModelDownload) => startModelDownload(api, request),
    onSuccess: (status: ModelDownloadStatus) => queryClient.setQueryData(modelDownloadKeys.current(), status),
  });
}

export function useCancelModelDownload() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelModelDownload(api),
    onSuccess: (status: ModelDownloadStatus) => queryClient.setQueryData(modelDownloadKeys.current(), status),
  });
}

/** Search results for settled text. Sends nothing when `text` is `null`. */
export function useModelSearch(provider: string, text: string | null) {
  const api = useApi();
  return useQuery({ ...modelSearchQuery(api, provider, text ?? ""), enabled: text !== null });
}

/** The quantisation labels of one repo. Sends nothing when `repo` is `null`. */
export function useModelFiles(provider: string, repo: string | null) {
  const api = useApi();
  return useQuery({ ...modelFilesQuery(api, provider, repo ?? ""), enabled: repo !== null });
}

/**
 * The models the provider lists now. It contacts the provider, so it runs only
 * when `enabled`; an enabled query reads the list again each time it mounts.
 * A disabled one reads it on `refetch()`.
 */
export function useProviderModels(provider: string, enabled: boolean) {
  const api = useApi();
  return useQuery({ ...providerModelsQuery(api, provider), enabled, refetchOnMount: "always" });
}
