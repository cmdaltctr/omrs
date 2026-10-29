import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { DownloadReason } from "../api/modelDownloads";
import { ModelDownloadProgress } from "./ModelDownloadProgress";
import { REASON_SENTENCES } from "./modelDownloadWords";
import { downloadStatus } from "./test/downloadFixtures";

const GIB = 1024 ** 3;

const REASONS: DownloadReason[] = ["busy", "no-space", "gated", "not-found", "network", "stalled", "ollama-unreachable", "failed"];

describe("ModelDownloadProgress", () => {
  it("shows a bar with the share done, and the bytes in words", () => {
    render(<ModelDownloadProgress status={downloadStatus({ state: "running", provider: "llamacpp", model: "a/b:Q4_K_M", bytes_done: GIB, bytes_total: 4 * GIB })} onCancel={vi.fn()} cancelling={false} />);
    const bar = screen.getByRole("progressbar", { name: "Download progress" });
    expect(bar).toHaveAttribute("aria-valuenow", "25");
    expect(screen.getByText("1.0 GiB of 4.0 GiB")).toBeInTheDocument();
    expect(screen.getByText(/Downloading/)).toHaveTextContent("a/b:Q4_K_M");
  });

  it("says the size is known after the pull starts while an Ollama total is missing", () => {
    render(<ModelDownloadProgress status={downloadStatus({ state: "running", provider: "ollama", model: "qwen3", bytes_done: 0, bytes_total: null })} onCancel={vi.fn()} cancelling={false} />);
    expect(screen.getByText("Size known after the pull starts")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Download progress" })).not.toHaveAttribute("aria-valuenow");
  });

  it("calls Cancel, and disables it while the cancel is sent", async () => {
    const onCancel = vi.fn();
    const status = downloadStatus({ state: "running", provider: "ollama", model: "qwen3" });
    const { rerender } = render(<ModelDownloadProgress status={status} onCancel={onCancel} cancelling={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    rerender(<ModelDownloadProgress status={status} onCancel={onCancel} cancelling />);
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });

  it.each(REASONS)("shows one plain line for the reason %s", (reason) => {
    render(<ModelDownloadProgress status={downloadStatus({ state: "failed", provider: "ollama", model: "qwen3", reason })} onCancel={vi.fn()} cancelling={false} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(REASON_SENTENCES[reason]);
    expect(alert.querySelectorAll("p")).toHaveLength(1);
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("gives every reason its own line", () => {
    expect(new Set(REASONS.map((reason) => REASON_SENTENCES[reason])).size).toBe(REASONS.length);
  });

  it("says only that the download stopped after a cancel", () => {
    render(<ModelDownloadProgress status={downloadStatus({ state: "cancelled", provider: "ollama", model: "qwen3" })} onCancel={vi.fn()} cancelling={false} />);
    expect(screen.getByRole("status")).toHaveTextContent(/^The download stopped\.$/);
  });
});
