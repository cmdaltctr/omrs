import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { RUNTIMES, runtimeItem } from "../integrations/test/modelRuntimeFixtures";
import { documentsServer } from "../test/fakeDocumentsServer";
import { ApiProvider } from "./ApiProvider";
import { modelRuntimesKey, useModelRuntimes, useStopModelRuntime } from "./modelRuntimesHooks";
import { createQueryClient } from "./queries";

function setup(handlers = {}) {
  const server = documentsServer({ "GET /v1/runtimes": () => ({ runtimes: RUNTIMES }), ...handlers });
  const queryClient = createQueryClient({ retry: false });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ApiProvider fetchImpl={server.fetchImpl}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ApiProvider>
  );
  return { server, queryClient, wrapper };
}

describe("model runtime hooks", () => {
  it("reads the list", async () => {
    const { wrapper } = setup();
    const { result } = renderHook(() => useModelRuntimes(), { wrapper });
    await waitFor(() => expect(result.current.data).toHaveLength(RUNTIMES.length));
  });

  it("puts the item a stop returned into the list", async () => {
    const stopped = { ...RUNTIMES[0]!, state: "stopped" as const, memory_bytes: null };
    const { wrapper, queryClient, server } = setup({ "POST /v1/runtimes/router/stop": () => stopped });
    const { result: list } = renderHook(() => useModelRuntimes(), { wrapper });
    await waitFor(() => expect(list.current.data).toBeDefined());
    const { result } = renderHook(() => useStopModelRuntime(), { wrapper });
    act(() => result.current.mutate("router"));
    await waitFor(() => expect(queryClient.getQueryData<typeof RUNTIMES>(modelRuntimesKey)?.find((item) => item.id === "router")?.state).toBe("stopped"));
    expect(queryClient.getQueryData<typeof RUNTIMES>(modelRuntimesKey)?.find((item) => item.id === "ocr-paddleocr-vl-llamacpp")?.state).toBe("running");
    expect(server.exact("POST", "/v1/runtimes/router/stop")).toHaveLength(1);
  });

  it("polls while a runtime is starting and stops when none is", async () => {
    let reads = 0;
    const { wrapper } = setup({
      "GET /v1/runtimes": () => {
        reads += 1;
        return { runtimes: [runtimeItem("router", { state: reads < 3 ? "starting" : "running" })] };
      },
    });
    const { result } = renderHook(() => useModelRuntimes(), { wrapper });
    await waitFor(() => expect(result.current.data?.[0]?.state).toBe("running"), { timeout: 5000 });
    const seen = reads;
    await new Promise((resolve) => setTimeout(resolve, 1300));
    expect(reads).toBe(seen);
  });
});
