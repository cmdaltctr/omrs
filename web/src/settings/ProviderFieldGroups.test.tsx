import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { startApp } from "../test/startApp";
import { CHAT_READY, LLAMACPP, SERVER_MANAGED, settingsServer } from "./test/fixtures";

const CHAT_ON_LLAMACPP = { ...CHAT_READY, provider: "llamacpp", model: "Qwen/Qwen3-4B-GGUF:Q4_K_M" };

async function open(handlers = {}) {
  startApp("#/settings/providers", settingsServer(handlers));
  await screen.findByRole("heading", { level: 3, name: "llama.cpp" });
  return userEvent.setup();
}

function card(name: string) {
  return screen.getByRole("region", { name });
}

function block(name: string) {
  return within(card("llama.cpp")).getByRole("group", { name });
}

describe("Blocks on a provider card", () => {
  it("shows Embeddings, Classification (metadata) and Chat on the llama.cpp card, in that order, before Get a model", async () => {
    await open();
    const titles = within(card("llama.cpp")).getAllByRole("heading", { level: 4 }).map((heading) => heading.textContent);
    expect(titles).toEqual(["Embeddings", "Classification (metadata)", "Chat", "Get a model"]);
  });

  it("puts each value in the block of its group", async () => {
    await open();
    expect(within(block("Embeddings")).getByText("Embedding address")).toBeInTheDocument();
    expect(within(block("Embeddings")).getByText("bge-small")).toBeInTheDocument();
    expect(within(block("Classification (metadata)")).getByText("Classification address")).toBeInTheDocument();
    expect(within(block("Chat")).getByText("Chat address")).toBeInTheDocument();
  });

  it("shows Text model (classification) with its value in the Classification block", async () => {
    await open();
    const classification = block("Classification (metadata)");
    expect(within(classification).getByText("Text model (classification)")).toBeInTheDocument();
    expect(within(classification).getByText("Qwen/Qwen3-0.6B-GGUF:Q8_0")).toBeInTheDocument();
  });

  it("labels no row outside the Chat block Chat model", async () => {
    await open({ "GET /v1/settings/chat": () => CHAT_ON_LLAMACPP, "GET /v1/llamacpp/server": () => SERVER_MANAGED });
    const chat = block("Chat");
    await waitFor(() => expect(within(chat).getAllByText("Chat model").length).toBeGreaterThan(0));
    for (const row of within(card("llama.cpp")).getAllByText("Chat model")) expect(chat).toContainElement(row);
  });

  it("shows no block titles on the OpenRouter card", async () => {
    await open();
    expect(within(card("OpenRouter")).queryAllByRole("heading", { level: 4 })).toHaveLength(0);
    expect(within(card("OpenRouter")).queryByRole("group", { name: "Chat" })).toBeNull();
  });

  it("shows a following Classification address as the Chat address with the source default and says so", async () => {
    const user = await open();
    const classification = block("Classification (metadata)");
    expect(within(classification).getByText("http://127.0.0.1:8082/v1")).toBeInTheDocument();
    expect(within(classification).getByText("default")).toBeInTheDocument();
    expect(classification).toHaveTextContent("Uses the Chat address until you set one.");
    await user.click(within(classification).getByRole("button", { name: "Edit Classification address" }));
    expect(within(classification).getByRole("textbox", { name: "Classification address" })).toHaveValue("http://127.0.0.1:8082/v1");
  });

  it("drops the follow line once a source sets the Classification address", async () => {
    const pinned = { ...LLAMACPP, fields: LLAMACPP.fields.map((field) => (field.id === "classify_url" ? { ...field, value: "http://127.0.0.1:9931/v1", source: "config-file" as const } : field)) };
    await open({ "GET /v1/connections": () => ({ status: "ok", revision: "r1", config_dir: "/srv", user_config_dir: "~/.config/omrs", keychain: "available", connections: [pinned] }) });
    const classification = block("Classification (metadata)");
    expect(within(classification).getByText("http://127.0.0.1:9931/v1")).toBeInTheDocument();
    expect(classification).not.toHaveTextContent("Uses the Chat address until you set one.");
  });
});
