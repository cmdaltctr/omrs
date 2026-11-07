import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Connection, ConnectionList } from "../api/settings";
import { startApp } from "../test/startApp";
import { CONNECTIONS, LLAMACPP, OLLAMA, settingsServer, urlField } from "./test/fixtures";

/** A provider whose fields and values sit in the three card blocks (the server still supports them). */
const GROUPED: Connection = {
  ...OLLAMA,
  provider: "grouped",
  display_name: "Grouped",
  model_source: null,
  fields: [
    { ...urlField("embed_url", "Embedding address", "http://127.0.0.1:8081/v1"), group: "embeddings" },
    { ...urlField("chat_url", "Chat address", "http://127.0.0.1:8082/v1"), group: "answers" },
    { ...urlField("classify_url", "Classification address", "http://127.0.0.1:8082/v1"), group: "metadata", follows: "chat_url" },
  ],
  read_only: [{ label: "Embedding model", value: "bge-small", group: "embeddings" }],
};

const list = (...connections: Connection[]): ConnectionList => ({ ...CONNECTIONS, connections });

async function open(connections: Connection[]) {
  startApp("#/settings/providers", settingsServer({ "GET /v1/connections": () => list(...connections) }));
  await screen.findByRole("heading", { level: 3, name: connections[0]!.display_name });
  return userEvent.setup();
}

const card = (name: string) => screen.getByRole("region", { name });
const block = (provider: string, name: string) => within(card(provider)).getByRole("group", { name });

describe("Blocks on a provider card", () => {
  it("shows Embeddings, Classification (metadata) and Chat in that order for a provider whose values have groups", async () => {
    await open([GROUPED]);
    const titles = within(card("Grouped")).getAllByRole("heading", { level: 4 }).map((heading) => heading.textContent);
    expect(titles).toEqual(["Embeddings", "Classification (metadata)", "Chat"]);
  });

  it("puts each value in the block of its group", async () => {
    await open([GROUPED]);
    expect(within(block("Grouped", "Embeddings")).getByText("Embedding address")).toBeInTheDocument();
    expect(within(block("Grouped", "Embeddings")).getByText("bge-small")).toBeInTheDocument();
    expect(within(block("Grouped", "Classification (metadata)")).getByText("Classification address")).toBeInTheDocument();
    expect(within(block("Grouped", "Chat")).getByText("Chat address")).toBeInTheDocument();
  });

  it("shows a following address with the source default and says so", async () => {
    const user = await open([GROUPED]);
    const classification = block("Grouped", "Classification (metadata)");
    expect(within(classification).getByText("default")).toBeInTheDocument();
    expect(classification).toHaveTextContent("Uses the Chat address until you set one.");
    await user.click(within(classification).getByRole("button", { name: "Edit Classification address" }));
    expect(within(classification).getByRole("textbox", { name: "Classification address" })).toHaveValue("http://127.0.0.1:8082/v1");
  });

  it("drops the follow line once a source sets the address", async () => {
    const pinned = { ...GROUPED, fields: GROUPED.fields.map((field) => (field.id === "classify_url" ? { ...field, value: "http://127.0.0.1:9931/v1", source: "config-file" as const } : field)) };
    await open([pinned]);
    const classification = block("Grouped", "Classification (metadata)");
    expect(within(classification).getByText("http://127.0.0.1:9931/v1")).toBeInTheDocument();
    expect(classification).not.toHaveTextContent("Uses the Chat address until you set one.");
  });

  it("shows no block titles on the llama.cpp card, which has one Router panel instead", async () => {
    await open([LLAMACPP]);
    const llamacpp = card("llama.cpp");
    expect(within(llamacpp).queryByRole("group", { name: "Chat" })).toBeNull();
    expect(within(llamacpp).queryByRole("group", { name: "Embeddings" })).toBeNull();
    expect(await within(llamacpp).findByRole("group", { name: "Router" })).toBeInTheDocument();
    expect(within(llamacpp).getAllByRole("heading", { level: 4 }).map((heading) => heading.textContent)).toEqual(["Get a model", "Router"]);
  });

  it("shows the router address once, in the Router panel, and the roles' models as read-only values", async () => {
    await open([LLAMACPP]);
    const llamacpp = card("llama.cpp");
    const panel = await within(llamacpp).findByRole("group", { name: "Router" });
    expect(within(llamacpp).getAllByText("Router address")).toHaveLength(1);
    expect(panel).toContainElement(within(llamacpp).getByText("Router address"));
    expect(within(llamacpp).queryByText("Router mode")).toBeNull();
    expect(within(llamacpp).getByText("Embedding model")).toBeInTheDocument();
    expect(within(llamacpp).getByText("Text model (classification)")).toBeInTheDocument();
  });

  it("shows no block titles on the OpenRouter card", async () => {
    await open([{ ...CONNECTIONS.connections[2]! }]);
    expect(within(card("OpenRouter")).queryAllByRole("heading", { level: 4 })).toHaveLength(0);
    expect(within(card("OpenRouter")).queryByRole("group", { name: "Chat" })).toBeNull();
  });
});
