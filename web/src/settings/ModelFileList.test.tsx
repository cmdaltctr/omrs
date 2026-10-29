import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { json, documentsServer } from "../test/fakeDocumentsServer";
import { renderWithProviders } from "../test/providers";
import { ModelFileList } from "./ModelFileList";
import { FILES, REVISION } from "./test/downloadFixtures";

function setup(list: unknown = FILES, props: Partial<Parameters<typeof ModelFileList>[0]> = {}) {
  const server = documentsServer({ "GET /v1/model-downloads/files": () => (list instanceof Response ? list : list) });
  const onStart = vi.fn();
  renderWithProviders(<ModelFileList provider="llamacpp" repo="unsloth/Qwen3-4B-GGUF" source="huggingface-gguf" disabled={false} onStart={onStart} {...props} />, { fetchImpl: server.fetchImpl });
  return { server, onStart, user: userEvent.setup() };
}

describe("ModelFileList", () => {
  it("shows each label with a human size and preselects Q4_K_M", async () => {
    setup();
    expect(await screen.findByRole("radio", { name: /Q2_K.*1\.5 GiB/ })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: /Q4_K_M.*2\.5 GiB/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /Q8_0.*4\.2 GiB/ })).not.toBeChecked();
  });

  it("names its radio group after the provider, so two cards with one repo do not share it", async () => {
    setup();
    expect(await screen.findByRole("radio", { name: /Q4_K_M/ })).toHaveAttribute("name", "quant-llamacpp-unsloth/Qwen3-4B-GGUF");
  });

  it("marks Q8_0 as closest to full quality", async () => {
    setup();
    const q8 = await screen.findByRole("radio", { name: /Q8_0/ });
    expect(q8.closest("label")).toHaveTextContent("closest to full quality");
    expect(screen.getByRole("radio", { name: /Q4_K_M/ }).closest("label")).not.toHaveTextContent("closest to full quality");
  });

  it("starts the picked label with the repo, the revision and the label for llama.cpp", async () => {
    const { user, onStart } = setup();
    await user.click(await screen.findByRole("radio", { name: /Q8_0/ }));
    await user.click(screen.getByRole("button", { name: "Download" }));
    expect(onStart).toHaveBeenCalledWith({ provider: "llamacpp", repo: "unsloth/Qwen3-4B-GGUF", revision: REVISION, label: "Q8_0" });
  });

  it("starts the recommended label when the person picks nothing", async () => {
    const { user, onStart } = setup();
    await user.click(await screen.findByRole("button", { name: "Download" }));
    expect(onStart.mock.calls[0]?.[0]).toMatchObject({ label: "Q4_K_M" });
  });

  it("starts an Ollama pull of a Hugging Face file with the repo and the label, without a revision", async () => {
    const { user, onStart, server } = setup(FILES, { provider: "ollama", source: "ollama-pull" });
    await user.click(await screen.findByRole("button", { name: "Download" }));
    expect(onStart).toHaveBeenCalledWith({ provider: "ollama", repo: "unsloth/Qwen3-4B-GGUF", label: "Q4_K_M" });
    expect(server.calls[0]?.path).toContain("provider=ollama");
  });

  it("disables Download while another download runs", async () => {
    setup(FILES, { disabled: true });
    expect(await screen.findByRole("button", { name: "Download" })).toBeDisabled();
  });

  it("shows a Gated badge and the token line for a gated repo", async () => {
    setup({ ...FILES, gated: true });
    expect(await screen.findByText("Gated")).toBeInTheDocument();
    expect(screen.getByText(/needs a Hugging Face access token/)).toBeInTheDocument();
  });

  it("says so when Hugging Face does not answer, and offers no Download", async () => {
    setup({ ...FILES, entries: [], revision: null, reason: "network" });
    expect(await screen.findByText("The model host could not be reached. Check the connection, then try again.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Download" })).toBeNull();
  });

  it("shows the not-found line for a repo with no GGUF file", async () => {
    setup(json({ status: "error", message: "No GGUF files.", reason: "not-found" }, 404));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Hugging Face has no such model or no GGUF file in it. Search again."));
  });
});
