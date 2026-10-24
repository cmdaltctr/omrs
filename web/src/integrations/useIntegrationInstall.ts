import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { installIntegration, uninstallIntegration, type IntegrationInstall, type InstallType } from "../api/integrations";
import { integrationInstallQuery, queryKeys } from "../api/queries";

export interface InstallControl {
  /** The running or last install or uninstall job of this launch, once read. */
  install: IntegrationInstall | undefined;
  /** True while a job runs or a start request is in flight. Every Install and Uninstall button is then disabled. */
  busy: boolean;
  /** The extra whose install start request is in flight. */
  starting: string | null;
  /** Starts an install of `extra`. */
  start: (extra: string) => void;
  /** The refused install start of `extra`, or `null`. */
  refusal: (extra: string) => unknown;
  /** The extra whose uninstall start request is in flight. */
  uninstalling: string | null;
  /** Starts an uninstall of `extra`. */
  uninstall: (extra: string) => void;
  /** The refused uninstall start of `extra`, or `null`. */
  uninstallRefusal: (extra: string) => unknown;
  /** Clears both refusals and reads the catalogue again. */
  recheck: () => void;
}

/**
 * The job state and the start actions of the Integrations page.
 *
 * The status is read once when the page opens, and only when the server is a
 * `uv tool` install, because no other install type can run a job. It is then
 * polled every second only while a job runs (`integrationInstallQuery`). The
 * one read on open finds a job that started before the page loaded.
 */
export function useIntegrationInstall(installType: InstallType | undefined): InstallControl {
  const api = useApi();
  const queryClient = useQueryClient();
  const status = useQuery({ ...integrationInstallQuery(api), enabled: installType === "uv-tool" });
  const onSuccess = (install: IntegrationInstall) => queryClient.setQueryData(queryKeys.integrationInstall(), install);
  const install = useMutation({ mutationFn: (extra: string) => installIntegration(api, extra), onSuccess });
  const uninstall = useMutation({ mutationFn: (extra: string) => uninstallIntegration(api, extra), onSuccess });
  const starting = install.isPending ? (install.variables ?? null) : null;
  const uninstalling = uninstall.isPending ? (uninstall.variables ?? null) : null;
  return {
    install: status.data,
    busy: status.data?.state === "running" || starting !== null || uninstalling !== null,
    starting,
    start: (extra) => install.mutate(extra),
    refusal: (extra) => (install.isError && install.variables === extra ? install.error : null),
    uninstalling,
    uninstall: (extra) => uninstall.mutate(extra),
    uninstallRefusal: (extra) => (uninstall.isError && uninstall.variables === extra ? uninstall.error : null),
    recheck: () => {
      install.reset();
      uninstall.reset();
      void queryClient.invalidateQueries({ queryKey: queryKeys.integrations() });
    },
  };
}
