import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { installIntegration, installTool, uninstallIntegration, uninstallTool, type IntegrationInstall, type IntegrationList } from "../api/integrations";
import { integrationInstallQuery, queryKeys } from "../api/queries";

export interface InstallControl {
  /** The running or last install or uninstall job of this launch, once read. */
  install: IntegrationInstall | undefined;
  /** True while a job runs or any start request is in flight. Every Install and Uninstall button is then disabled. */
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
  /** The external tool whose install start request is in flight. */
  toolStarting: string | null;
  /** Starts an install of the external `tool`. */
  startTool: (tool: string) => void;
  /** The refused install start of `tool`, or `null`. */
  toolRefusal: (tool: string) => unknown;
  /** The external tool whose uninstall start request is in flight. */
  toolUninstalling: string | null;
  /** Starts an uninstall of the external `tool`. */
  uninstallTool: (tool: string) => void;
  /** The refused uninstall start of `tool`, or `null`. */
  toolUninstallRefusal: (tool: string) => unknown;
  /** Clears every refusal and reads the catalogue again. */
  recheck: () => void;
}

/** True when this server can run a job: an extras job needs a `uv tool` server, a tool job needs only `uv` (design D11). */
function canRunJob(list: IntegrationList | undefined): boolean {
  if (list === undefined) return false;
  return list.install_type === "uv-tool" || list.tools.some((tool) => tool.availability !== "unknown");
}

/**
 * The job state and the start actions of the Integrations page.
 *
 * The status is read once when the page opens, and only when the server can
 * run a job. It is then polled every second only while a job runs
 * (`integrationInstallQuery`). The one read on open finds a job that started
 * before the page loaded. Extras and external tools share the one job.
 */
export function useIntegrationInstall(list: IntegrationList | undefined): InstallControl {
  const api = useApi();
  const queryClient = useQueryClient();
  const status = useQuery({ ...integrationInstallQuery(api), enabled: canRunJob(list) });
  const onSuccess = (install: IntegrationInstall) => queryClient.setQueryData(queryKeys.integrationInstall(), install);
  const install = useMutation({ mutationFn: (extra: string) => installIntegration(api, extra), onSuccess });
  const uninstall = useMutation({ mutationFn: (extra: string) => uninstallIntegration(api, extra), onSuccess });
  const toolInstall = useMutation({ mutationFn: (tool: string) => installTool(api, tool), onSuccess });
  const toolUninstall = useMutation({ mutationFn: (tool: string) => uninstallTool(api, tool), onSuccess });
  const starting = install.isPending ? (install.variables ?? null) : null;
  const uninstalling = uninstall.isPending ? (uninstall.variables ?? null) : null;
  const toolStarting = toolInstall.isPending ? (toolInstall.variables ?? null) : null;
  const toolUninstalling = toolUninstall.isPending ? (toolUninstall.variables ?? null) : null;
  const pending = [starting, uninstalling, toolStarting, toolUninstalling].some((name) => name !== null);
  return {
    install: status.data,
    busy: status.data?.state === "running" || pending,
    starting,
    start: (extra) => install.mutate(extra),
    refusal: (extra) => (install.isError && install.variables === extra ? install.error : null),
    uninstalling,
    uninstall: (extra) => uninstall.mutate(extra),
    uninstallRefusal: (extra) => (uninstall.isError && uninstall.variables === extra ? uninstall.error : null),
    toolStarting,
    startTool: (tool) => toolInstall.mutate(tool),
    toolRefusal: (tool) => (toolInstall.isError && toolInstall.variables === tool ? toolInstall.error : null),
    toolUninstalling,
    uninstallTool: (tool) => toolUninstall.mutate(tool),
    toolUninstallRefusal: (tool) => (toolUninstall.isError && toolUninstall.variables === tool ? toolUninstall.error : null),
    recheck: () => {
      install.reset();
      uninstall.reset();
      toolInstall.reset();
      toolUninstall.reset();
      void queryClient.invalidateQueries({ queryKey: queryKeys.integrations() });
    },
  };
}
