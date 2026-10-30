import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ChatSettings } from "../api/settings";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { CHAT_READY, settingsServer } from "./test/fixtures";

async function chatBlock(chat: () => unknown) {
  startApp("#/settings/providers", settingsServer({ "GET /v1/settings/chat": chat }));
  await screen.findByRole("heading", { level: 3, name: "llama.cpp" });
  return within(screen.getByRole("region", { name: "llama.cpp" })).getByRole("group", { name: "Chat" });
}

const chatOn = (provider: string, model: string): ChatSettings => ({ ...CHAT_READY, provider, model });

describe("The Chat block of the llama.cpp card", () => {
  it("names the provider and the model when Chat uses another provider, with a link to Settings > Chat", async () => {
    const block = await chatBlock(() => chatOn("openrouter", "deepseek/deepseek-v4-flash-0731"));
    expect(await within(block).findByText("Chat uses OpenRouter (deepseek/deepseek-v4-flash-0731)")).toBeInTheDocument();
    expect(within(block).getByRole("link", { name: "Change in Settings > Chat" })).toHaveAttribute("href", "#/settings/chat");
    expect(within(block).queryByText("Chat model")).toBeNull();
  });

  it("shows the Chat model as a read-only row with the link and no Edit when Chat uses llama.cpp", async () => {
    const block = await chatBlock(() => chatOn("llamacpp", "Qwen/Qwen3-4B-GGUF:Q4_K_M"));
    const row = (await within(block).findByText("Chat model")).closest("[data-slot='setting-row']") as HTMLElement;
    expect(within(row).getByText("Qwen/Qwen3-4B-GGUF:Q4_K_M")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Change in Settings > Chat" })).toHaveAttribute("href", "#/settings/chat");
    expect(within(block).queryByRole("button", { name: /Edit Chat model/ })).toBeNull();
    expect(within(block).queryByRole("textbox", { name: /model/i })).toBeNull();
    expect(block).not.toHaveTextContent("Chat uses");
  });

  it("shows Not set for an empty llama.cpp Chat model", async () => {
    const block = await chatBlock(() => chatOn("llamacpp", ""));
    const row = (await within(block).findByText("Chat model")).closest("[data-slot='setting-row']") as HTMLElement;
    expect(within(row).getByText("Not set")).toBeInTheDocument();
  });

  it("shows one friendly line with Retry when the Chat settings cannot be read", async () => {
    const block = await chatBlock(() => json({ status: "error", message: "boom" }, 500));
    expect(await within(block).findByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(block).not.toHaveTextContent("boom");
  });
});
