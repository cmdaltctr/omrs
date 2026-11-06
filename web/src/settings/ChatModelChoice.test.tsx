import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ChatSettings } from "../api/settings";
import { startApp } from "../test/startApp";
import { downloadStatus, FILES } from "./test/downloadFixtures";
import { CHAT_READY, EMBED_ENTRY, routerEntry, routerStatus, settingsServer, TEXT_ENTRY, TEXT_MODEL, WITH_CREDENTIALS } from "./test/fixtures";

/** A fresh install: Chat on llama.cpp with no model chosen. */
const FRESH: ChatSettings = { ...CHAT_READY, provider: "llamacpp", model: "", source: "default", ready: false, reason: "no-model" };
const SHARED: ChatSettings = { ...CHAT_READY, provider: "llamacpp", model: TEXT_MODEL, source: "config-file" };
const CHAT_ENTRY = routerEntry({ roles: ["classification", "chat"] });

async function openChat(handlers = {}) {
  const server = settingsServer({ ...WITH_CREDENTIALS, "GET /v1/settings/chat": () => FRESH, ...handlers });
  startApp("#/settings/chat", server);
  await screen.findByRole("region", { name: "Chat" });
  await waitFor(() => expect(screen.queryByText("Loading Chat settings.")).toBeNull());
  return { server, user: userEvent.setup() };
}

const section = () => screen.getByRole("region", { name: "Chat" });

describe("The Chat section asks for a Chat model when none is chosen", () => {
  it("Fresh install Chat page: shows Choose a Chat model and a picker that lists the shipped entries without the embedding entry", async () => {
    const { user } = await openChat();
    expect(await within(section()).findByRole("heading", { name: "Choose a Chat model" })).toBeInTheDocument();
    await user.click(within(section()).getByRole("combobox", { name: "Chat model to use" }));
    const options = (await screen.findAllByRole("option")).map((option) => option.textContent);
    expect(options).toEqual([expect.stringContaining(TEXT_MODEL)]);
    expect(options.join(" ")).not.toContain("Embedding");
  });

  it("Pick a model: saves answer.model with the picked entry and the entry then lists Chat and classification", async () => {
    let chat = FRESH;
    let models = [EMBED_ENTRY, TEXT_ENTRY];
    const { user, server } = await openChat({
      "GET /v1/settings/chat": () => chat,
      "GET /v1/llamacpp/router": () => routerStatus({ models }),
      "PUT /v1/settings/chat": (body: { provider: string; model: string }) => {
        chat = { ...SHARED, model: body.model };
        models = [EMBED_ENTRY, CHAT_ENTRY];
        return { status: "ok", revision: "r2" };
      },
    });
    await user.click(await within(section()).findByRole("combobox", { name: "Chat model to use" }));
    await user.click(await screen.findByRole("option", { name: new RegExp(TEXT_MODEL) }));
    await user.click(within(section()).getByRole("button", { name: "Use as Chat model" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/chat")).toHaveLength(1));
    expect(server.find("PUT", "/v1/settings/chat")[0]?.body).toMatchObject({ provider: "llamacpp", model: TEXT_MODEL });
    await waitFor(() => expect(within(section()).queryByRole("heading", { name: "Choose a Chat model" })).toBeNull());
    await waitFor(() => expect(server.find("GET", "/v1/llamacpp/router").length).toBeGreaterThan(1));
  });

  it("offers Get this model for an entry that has no file, and not for one that has", async () => {
    const { user, server } = await openChat({
      "GET /v1/llamacpp/router": () => routerStatus({ models: [EMBED_ENTRY, TEXT_ENTRY, routerEntry({ id: "small", model: "Qwen/Qwen3-1.7B-GGUF:Q8_0", file: "/cache/small.gguf", state: "unloaded", roles: [] })] }),
      "GET /v1/model-downloads/files": () => ({ ...FILES, repo: "Qwen/Qwen3-4B-GGUF" }),
      "POST /v1/model-downloads": () => downloadStatus({ state: "running", provider: "llamacpp", model: TEXT_MODEL, bytes_done: 1, bytes_total: 10 }),
    });
    const picker = await within(section()).findByRole("combobox", { name: "Chat model to use" });
    await user.click(picker);
    await user.click(await screen.findByRole("option", { name: /Qwen3-1\.7B/ }));
    expect(within(section()).queryByRole("button", { name: /^Get this model/ })).toBeNull();
    await user.click(picker);
    await user.click(await screen.findByRole("option", { name: new RegExp(TEXT_MODEL) }));
    await user.click(within(section()).getByRole("button", { name: `Get this model ${TEXT_MODEL}` }));
    await waitFor(() => expect(server.find("POST", "/v1/model-downloads")).toHaveLength(1));
  });

  it("does not choose the classification model for the user", async () => {
    const { server } = await openChat();
    await within(section()).findByRole("heading", { name: "Choose a Chat model" });
    expect(server.find("PUT", "/v1/settings/chat")).toHaveLength(0);
    expect(within(section()).getByRole("button", { name: "Use as Chat model" })).toBeDisabled();
  });

  it("is not shown when a model is chosen, or when Chat uses another provider", async () => {
    await openChat({ "GET /v1/settings/chat": () => ({ ...SHARED, model: "other/model:Q4_K_M" }) });
    expect(within(section()).queryByRole("heading", { name: "Choose a Chat model" })).toBeNull();
  });

  it("is not shown when Chat uses another provider and no model is chosen", async () => {
    await openChat({ "GET /v1/settings/chat": () => ({ ...FRESH, provider: "openrouter" }) });
    await within(section()).findByText("OpenRouter");
    expect(within(section()).queryByRole("heading", { name: "Choose a Chat model" })).toBeNull();
  });

  it("leaves the picker read-only when the environment sets the Chat choice", async () => {
    const locked = { ...FRESH, locked: true, source: "env" as const, lock_reason: "Remove ANSWER__PROVIDER from the environment or .env to edit it here." };
    await openChat({ "GET /v1/settings/chat": () => locked });
    const picker = await within(section()).findByRole("combobox", { name: "Chat model to use" });
    expect(picker).toBeDisabled();
  });
});

describe("The Chat section warns when Chat shares the classification model", () => {
  const shared = { "GET /v1/settings/chat": () => SHARED, "GET /v1/llamacpp/router": () => routerStatus({ models: [EMBED_ENTRY, CHAT_ENTRY] }) };

  it("Chat picks the classification model: the section says they share the model and does not block Save", async () => {
    await openChat(shared);
    const note = await within(section()).findByText("Chat and classification share this model. A long Chat answer can slow classification during an ingest. A context size change reloads the model for both.");
    expect(note.closest("[role='note']")).toHaveClass("border-status-warning");
    expect(within(section()).getByRole("button", { name: "Edit Chat model" })).toBeEnabled();
  });

  it("The note lists three ways out: another local model, the OpenAI-compatible provider, a hosted provider", async () => {
    const { user } = await openChat(shared);
    await within(section()).findByText(/Chat and classification share this model/);
    const links = within(section()).getByRole("list", { name: "Ways to keep them apart" });
    expect(within(links).getByRole("button", { name: "Choose another local model on the router" })).toBeInTheDocument();
    expect(links).toHaveTextContent("Use your own llama.cpp server for Chat through the OpenAI-compatible provider. OMRS does not run it.");
    expect(within(links).getByRole("link", { name: "OpenAI-compatible provider" })).toHaveAttribute("href", "#/settings/providers");
    expect(links).toHaveTextContent("Use a hosted provider such as OpenRouter.");
    expect(within(links).getByRole("link", { name: "hosted provider" })).toHaveAttribute("href", "#/settings/providers");
    await user.click(within(links).getByRole("button", { name: "Choose another local model on the router" }));
    expect(within(section()).getByRole("combobox", { name: "Chat provider and model" })).toBeInTheDocument();
  });

  it("Chat uses another model: the section shows no warning", async () => {
    await openChat({ ...shared, "GET /v1/settings/chat": () => ({ ...SHARED, model: "other/model:Q4_K_M" }) });
    await within(section()).findByText("other/model:Q4_K_M");
    expect(within(section()).queryByText(/share this model/)).toBeNull();
  });

  it("Chat uses another provider with the same model name: the section shows no warning", async () => {
    await openChat({ ...shared, "GET /v1/settings/chat": () => ({ ...SHARED, provider: "openrouter" }) });
    await within(section()).findByText("OpenRouter");
    expect(within(section()).queryByText(/share this model/)).toBeNull();
  });
});
