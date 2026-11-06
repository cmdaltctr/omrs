import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { routerStatus, settingsServer } from "../settings/test/fixtures";
import { ApiProvider } from "./ApiProvider";
import { RUNTIMES } from "../integrations/test/modelRuntimeFixtures";
import { llamacppRouterKey, useDeleteRouterModel, useLlamacppRouter, useRestartLlamacppRouter, useSaveLlamacppRouter, useSaveRouterModel, useStartLlamacppRouter, useStopLlamacppRouter } from "./llamacppRouterHooks";
import { useModelRuntimes } from "./modelRuntimesHooks";
import { createQueryClient } from "./queries";
import { currentRevision, rememberRevision } from "./settingsRevision";

function setup(handlers = {}) {
  const server = settingsServer(handlers);
  const queryClient = createQueryClient({ retry: false });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ApiProvider fetchImpl={server.fetchImpl}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ApiProvider>
  );
  return { server, queryClient, wrapper };
}

describe("llama.cpp router hooks", () => {
  it("reads the status", async () => {
    const { wrapper } = setup();
    const { result } = renderHook(() => useLlamacppRouter(), { wrapper });
    await waitFor(() => expect(result.current.data?.state).toBe("stopped"));
  });

  it("puts the status a write returned into the cache", async () => {
    const { wrapper, queryClient } = setup({ "POST /v1/llamacpp/router/start": () => routerStatus({ state: "starting" }) });
    const { result } = renderHook(() => useStartLlamacppRouter(), { wrapper });
    act(() => result.current.mutate());
    await waitFor(() => expect(queryClient.getQueryData(llamacppRouterKey)).toMatchObject({ state: "starting" }));
  });

  it("sends a change and caches the answer", async () => {
    const { wrapper, queryClient, server } = setup({ "PUT /v1/llamacpp/router": () => routerStatus({}, { models_max: { value: 2, source: "config-file" } }) });
    const { result } = renderHook(() => useSaveLlamacppRouter(), { wrapper });
    act(() => result.current.mutate({ models_max: 2 }));
    await waitFor(() => expect(queryClient.getQueryData(llamacppRouterKey)).toMatchObject({ saved: { models_max: { value: 2 } } }));
    expect(server.find("PUT", "/v1/llamacpp/router")[0]?.body).toEqual({ models_max: 2 });
  });

  it("sends the remembered revision with a save and remembers the one that comes back", async () => {
    const { wrapper, queryClient, server } = setup({ "PUT /v1/llamacpp/router": () => ({ ...routerStatus({}), revision: "r2" }) });
    rememberRevision(queryClient, { revision: "r1" });
    const { result } = renderHook(() => useSaveLlamacppRouter(), { wrapper });
    act(() => result.current.mutate({ router_server: "external" }));
    await waitFor(() => expect(currentRevision(queryClient)).toBe("r2"));
    expect(server.find("PUT", "/v1/llamacpp/router")[0]?.body).toEqual({ router_server: "external", revision: "r1" });
  });

  it("saves and removes one list entry through its own routes", async () => {
    const { wrapper, queryClient, server } = setup({
      "PUT /v1/llamacpp/router/models/qwen3-4b": () => routerStatus({}),
      "DELETE /v1/llamacpp/router/models/qwen3-4b": () => routerStatus({ state: "running" }),
    });
    rememberRevision(queryClient, { revision: "r1" });
    const save = renderHook(() => useSaveRouterModel(), { wrapper });
    act(() => save.result.current.mutate({ id: "qwen3-4b", change: { preset: { "ctx-size": 16384 } } }));
    await waitFor(() => expect(server.find("PUT", "/v1/llamacpp/router/models/qwen3-4b")).toHaveLength(1));
    expect(server.find("PUT", "/v1/llamacpp/router/models/qwen3-4b")[0]?.body).toEqual({ preset: { "ctx-size": 16384 }, revision: "r1" });
    const remove = renderHook(() => useDeleteRouterModel(), { wrapper });
    act(() => remove.result.current.mutate("qwen3-4b"));
    await waitFor(() => expect(queryClient.getQueryData(llamacppRouterKey)).toMatchObject({ state: "running" }));
  });

  it.each([
    ["Start", "start", useStartLlamacppRouter],
    ["Stop", "stop", useStopLlamacppRouter],
    ["Restart", "restart", useRestartLlamacppRouter],
  ])("reads the model runtimes again after %s succeeds, so that page is not stale", async (_name, action, useAction) => {
    const { wrapper, server } = setup({
      "GET /v1/runtimes": () => ({ runtimes: RUNTIMES }),
      [`POST /v1/llamacpp/router/${action}`]: () => routerStatus({ state: "running" }),
    });
    const { result: list } = renderHook(() => useModelRuntimes(), { wrapper });
    await waitFor(() => expect(list.current.data).toBeDefined());
    expect(server.exact("GET", "/v1/runtimes")).toHaveLength(1);
    const { result } = renderHook(() => useAction(), { wrapper });
    act(() => result.current.mutate());
    await waitFor(() => expect(server.exact("GET", "/v1/runtimes")).toHaveLength(2));
  });

  it("does not read the model runtimes again after a save that is not a start, stop or restart", async () => {
    const { wrapper, server } = setup({ "GET /v1/runtimes": () => ({ runtimes: RUNTIMES }), "PUT /v1/llamacpp/router": () => routerStatus({}) });
    const { result: list } = renderHook(() => useModelRuntimes(), { wrapper });
    await waitFor(() => expect(list.current.data).toBeDefined());
    const { result } = renderHook(() => useSaveLlamacppRouter(), { wrapper });
    act(() => result.current.mutate({ models_max: 2 }));
    await waitFor(() => expect(server.exact("PUT", "/v1/llamacpp/router")).toHaveLength(1));
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(server.exact("GET", "/v1/runtimes")).toHaveLength(1);
  });

  it("polls while the router is starting and stops when it runs", async () => {
    let reads = 0;
    const { wrapper } = setup({
      "GET /v1/llamacpp/router": () => {
        reads += 1;
        return routerStatus({ state: reads < 3 ? "starting" : "running" });
      },
    });
    const { result } = renderHook(() => useLlamacppRouter(), { wrapper });
    await waitFor(() => expect(result.current.data?.state).toBe("running"), { timeout: 5000 });
    const seen = reads;
    await new Promise((resolve) => setTimeout(resolve, 1300));
    expect(reads).toBe(seen);
  });
});
