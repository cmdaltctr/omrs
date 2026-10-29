import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { documentsServer } from "../test/fakeDocumentsServer";
import { renderWithProviders } from "../test/providers";
import { ModelSearchField } from "./ModelSearchField";
import { searchReply, searchResult } from "./test/downloadFixtures";

const SEARCH = "GET /v1/model-downloads/search";

function setup(reply = searchReply("llamacpp", [searchResult({ id: "unsloth/Qwen3-4B-GGUF" })]), provider = "llamacpp") {
  const server = documentsServer({ [SEARCH]: () => reply });
  const onChoose = vi.fn();
  renderWithProviders(<ModelSearchField provider={provider} selectedId={null} onChoose={onChoose} />, { fetchImpl: server.fetchImpl });
  const searches = () => server.exact("GET", "/v1/model-downloads/search");
  return { server, searches, onChoose, user: userEvent.setup(), input: () => screen.getByRole("textbox", { name: "Search for a model" }) };
}

describe("ModelSearchField", () => {
  it("sends one search after the typing stops for 400 ms, not one per key", async () => {
    const { user, input, searches } = setup();
    await user.type(input(), "qwen");
    expect(searches()).toHaveLength(0);
    await waitFor(() => expect(searches()).toHaveLength(1));
    expect(searches()[0]?.path).toBe("/v1/model-downloads/search?provider=llamacpp&q=qwen");
  });

  it("sends nothing for one character", async () => {
    const { user, input, searches } = setup();
    await user.type(input(), "q");
    await new Promise((resolve) => setTimeout(resolve, 700));
    expect(searches()).toHaveLength(0);
    expect(screen.getByText("Type at least 2 characters to search.")).toBeInTheDocument();
  });

  it("lists each result with its downloads and a Gated badge only on a gated repo", async () => {
    const { user, input } = setup(
      searchReply("llamacpp", [searchResult({ id: "unsloth/Qwen3-4B-GGUF", downloads: 1200 }), searchResult({ id: "meta/Llama-gated", downloads: 5, gated: true })]),
    );
    await user.type(input(), "qwen");
    const list = await screen.findByRole("list", { name: "Search results" });
    const [open, gated] = within(list).getAllByRole("listitem");
    expect(open).toHaveTextContent("unsloth/Qwen3-4B-GGUF");
    expect(open).toHaveTextContent("1.2k downloads");
    expect(within(open!).queryByText("Gated")).toBeNull();
    expect(gated).toHaveTextContent("meta/Llama-gated");
    expect(within(gated!).getByText("Gated")).toBeInTheDocument();
  });

  it("marks a built-in Ollama library name", async () => {
    const { user, input } = setup(searchReply("ollama", [searchResult({ id: "qwen3", source: "ollama-library", downloads: null, likes: null, last_modified: null })]), "ollama");
    await user.type(input(), "qwen");
    const item = await screen.findByRole("listitem");
    expect(item).toHaveTextContent("qwen3");
    expect(item).toHaveTextContent("Ollama library");
  });

  it("hands the chosen result to the panel", async () => {
    const { user, input, onChoose } = setup();
    await user.type(input(), "qwen");
    await user.click(await screen.findByRole("button", { name: /unsloth\/Qwen3-4B-GGUF/ }));
    expect(onChoose).toHaveBeenCalledWith(expect.objectContaining({ id: "unsloth/Qwen3-4B-GGUF" }));
  });

  it("says so when no model matches and when the host does not answer", async () => {
    const empty = setup(searchReply("llamacpp", []));
    await empty.user.type(empty.input(), "zzz");
    expect(await screen.findByText("No model matches that search.")).toBeInTheDocument();
  });

  it("shows one line when Hugging Face does not answer", async () => {
    const { user, input } = setup(searchReply("llamacpp", [], "network"));
    await user.type(input(), "qwen");
    expect(await screen.findByText("The model host could not be reached. Check the connection, then try again.")).toBeInTheDocument();
  });
});
