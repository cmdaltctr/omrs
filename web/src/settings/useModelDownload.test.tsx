import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { ApiProvider } from "../api/ApiProvider";
import { createQueryClient } from "../api/queries";
import { documentsServer } from "../test/fakeDocumentsServer";
import { downloadStatus } from "./test/downloadFixtures";
import { useCancelModelDownload, useModelDownload, useStartModelDownload } from "./useModelDownload";

function setup(handlers = {}) {
  const server = documentsServer(handlers);
  const queryClient = createQueryClient({ retry: false });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ApiProvider fetchImpl={server.fetchImpl}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ApiProvider>
  );
  return { server, queryClient, wrapper };
}

const reads = (server: ReturnType<typeof setup>["server"]) => server.exact("GET", "/v1/model-downloads/current").length;

describe("useModelDownload", () => {
  it("polls every second while the state is running and stops once it succeeds", async () => {
    let count = 0;
    const { server, wrapper } = setup({
      "GET /v1/model-downloads/current": () => {
        count += 1;
        return count < 3 ? downloadStatus({ state: "running", provider: "ollama", bytes_done: count }) : downloadStatus({ state: "succeeded", provider: "ollama", model_value: "qwen3" });
      },
    });
    const { result } = renderHook(() => useModelDownload(), { wrapper });
    await waitFor(() => expect(result.current.data?.state).toBe("succeeded"), { timeout: 5000 });
    expect(reads(server)).toBe(3);
    await new Promise((resolve) => setTimeout(resolve, 1300));
    expect(reads(server)).toBe(3);
  });

  it("does not poll when the state is idle", async () => {
    const { server, wrapper } = setup({ "GET /v1/model-downloads/current": () => downloadStatus({}) });
    const { result } = renderHook(() => useModelDownload(), { wrapper });
    await waitFor(() => expect(result.current.data?.state).toBe("idle"));
    await new Promise((resolve) => setTimeout(resolve, 1300));
    expect(reads(server)).toBe(1);
  });

  it("puts the status a start returned into the cache, so polling begins at once", async () => {
    const { queryClient, wrapper } = setup({
      "GET /v1/model-downloads/current": () => downloadStatus({}),
      "POST /v1/model-downloads": () => downloadStatus({ state: "running", provider: "ollama", model: "qwen3" }),
    });
    const { result } = renderHook(() => ({ read: useModelDownload(), start: useStartModelDownload() }), { wrapper });
    await waitFor(() => expect(result.current.read.data?.state).toBe("idle"));
    act(() => result.current.start.mutate({ provider: "ollama", name: "qwen3" }));
    await waitFor(() => expect(queryClient.getQueryData(["model-downloads", "current"])).toMatchObject({ state: "running" }));
  });

  it("puts the status a cancel returned into the cache", async () => {
    const { queryClient, wrapper } = setup({ "DELETE /v1/model-downloads/current": () => downloadStatus({ state: "cancelled", provider: "ollama" }) });
    const { result } = renderHook(() => useCancelModelDownload(), { wrapper });
    act(() => result.current.mutate());
    await waitFor(() => expect(queryClient.getQueryData(["model-downloads", "current"])).toMatchObject({ state: "cancelled" }));
  });
});
