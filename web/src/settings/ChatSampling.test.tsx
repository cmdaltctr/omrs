import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ChatSettings, JudgeSettings } from "../api/settings";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { CHAT_READY, CONNECTIONS, JUDGE_SAVED, OLLAMA, OPENROUTER, settingsServer } from "./test/fixtures";

const GLM = "z-ai/glm-5.3-flash";
const EMPTY = { temperature: null, seed: null, allowed_hosts: "", sampling_locked: [], sampling_lock_reason: null, sampling_ignored: [] };
const CHAT: ChatSettings = { ...CHAT_READY, provider: "openrouter", model: GLM, reasoning: "", ...EMPTY };
const JUDGE: JudgeSettings = { ...JUDGE_SAVED, model: GLM, ...EMPTY };

async function open(handlers = {}) {
  const server = settingsServer({
    "GET /v1/connections": () => ({ ...CONNECTIONS, connections: [OLLAMA, OPENROUTER] }),
    "GET /v1/settings/chat": () => CHAT,
    "GET /v1/settings/judge": () => JUDGE,
    "GET /v1/settings/chat/reasoning-levels": () => ({ status: "ok", known: false }),
    ...handlers,
  });
  startApp("#/settings/chat", server);
  await screen.findByRole("region", { name: "Chat" });
  await waitFor(() => expect(screen.queryByText("Loading Chat settings.")).toBeNull());
  return { server, user: userEvent.setup() };
}

function model() {
  return screen.getByRole("region", { name: "Answer model" });
}

function judge() {
  return screen.getByRole("region", { name: "Claim check judge" });
}

describe("Chat temperature, seed and allowed hosts", () => {
  it("shows the empty values read-only with what empty means", async () => {
    await open();
    expect(model()).toHaveTextContent("Temperature: Library default");
    expect(model()).toHaveTextContent("Seed: None sent");
    expect(model()).toHaveTextContent("Allowed hosts: Any host");
  });

  it("shows saved values read-only", async () => {
    await open({ "GET /v1/settings/chat": () => ({ ...CHAT, temperature: 0, seed: 20261101, allowed_hosts: "Fireworks,DeepInfra" }) });
    expect(model()).toHaveTextContent("Temperature: 0");
    expect(model()).toHaveTextContent("Seed: 20261101");
    expect(model()).toHaveTextContent("Allowed hosts: Fireworks,DeepInfra");
  });

  it("saves the values with the choice in one write and shows them after", async () => {
    let state = CHAT;
    const { user, server } = await open({
      "GET /v1/settings/chat": () => state,
      "PUT /v1/settings/chat": (body: Record<string, unknown>) => {
        state = { ...state, temperature: body.temperature as number, seed: body.seed as number, allowed_hosts: body.allowed_hosts as string };
        return { status: "ok", revision: "r2" };
      },
    });
    await user.click(within(model()).getByRole("button", { name: "Edit Chat model" }));
    await user.type(within(model()).getByRole("spinbutton", { name: "Temperature" }), "0");
    await user.type(within(model()).getByRole("spinbutton", { name: "Seed" }), "20261101");
    await user.type(within(model()).getByRole("textbox", { name: "Allowed hosts" }), "Fireworks");
    await user.click(within(model()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/chat")).toHaveLength(1));
    expect(server.find("PUT", "/v1/settings/chat")[0]?.body).toEqual({
      provider: "openrouter",
      model: GLM,
      reasoning: "",
      temperature: 0,
      seed: 20261101,
      allowed_hosts: "Fireworks",
      revision: "r1",
    });
    expect(await within(model()).findByText(/Seed:/)).toHaveTextContent("Seed: 20261101");
  });

  it("sends only the values that changed, and null for a cleared one", async () => {
    const { user, server } = await open({
      "GET /v1/settings/chat": () => ({ ...CHAT, temperature: 0.2, seed: 7 }),
      "PUT /v1/settings/chat": () => ({ status: "ok", revision: "r2" }),
    });
    await user.click(within(model()).getByRole("button", { name: "Edit Chat model" }));
    await user.clear(within(model()).getByRole("spinbutton", { name: "Seed" }));
    await user.click(within(model()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/chat")).toHaveLength(1));
    const body = server.find("PUT", "/v1/settings/chat")[0]?.body as Record<string, unknown>;
    expect(body.seed).toBeNull();
    expect(body).not.toHaveProperty("temperature");
    expect(body).not.toHaveProperty("allowed_hosts");
  });

  it("refuses an out-of-range value before any request", async () => {
    const { user, server } = await open();
    await user.click(within(model()).getByRole("button", { name: "Edit Chat model" }));
    await user.type(within(model()).getByRole("spinbutton", { name: "Temperature" }), "3");
    expect(within(model()).getByText("Temperature must be a number from 0 to 2.")).toBeInTheDocument();
    expect(within(model()).getByRole("button", { name: "Save" })).toBeDisabled();
    await user.clear(within(model()).getByRole("spinbutton", { name: "Temperature" }));
    await user.type(within(model()).getByRole("spinbutton", { name: "Seed" }), "1.5");
    expect(within(model()).getByText("Seed must be a whole number from 0 to 2147483647.")).toBeInTheDocument();
    expect(server.find("PUT", "/v1/settings/chat")).toHaveLength(0);
  });

  it("notes beside each value the provider ignores", async () => {
    const { user } = await open({ "GET /v1/settings/chat": () => ({ ...CHAT, provider: "ollama", model: "m", sampling_ignored: ["allowed_hosts"] }) });
    await user.click(within(model()).getByRole("button", { name: "Edit Chat model" }));
    expect(model()).toHaveTextContent(/This provider ignores the host list/);
    expect(model()).not.toHaveTextContent(/This provider ignores the seed/);
  });

  it("shows a locked value read-only with the variable named and leaves it out of the save", async () => {
    const lock = "Set by ANSWER__SEED in the environment or .env. Remove it to edit here.";
    const { user, server } = await open({
      "GET /v1/settings/chat": () => ({ ...CHAT, seed: 5, sampling_locked: ["seed"], sampling_lock_reason: lock }),
      "PUT /v1/settings/chat": () => ({ status: "ok", revision: "r2" }),
    });
    expect(model()).toHaveTextContent("ANSWER__SEED");
    await user.click(within(model()).getByRole("button", { name: "Edit Chat model" }));
    const seed = within(model()).getByRole("spinbutton", { name: "Seed" });
    expect(seed).toHaveAttribute("readonly");
    await user.type(seed, "9");
    expect(seed).toHaveValue(5);
    await user.type(within(model()).getByRole("spinbutton", { name: "Temperature" }), "0");
    await user.click(within(model()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/chat")).toHaveLength(1));
    const body = server.find("PUT", "/v1/settings/chat")[0]?.body as Record<string, unknown>;
    expect(body).not.toHaveProperty("seed");
    expect(body.temperature).toBe(0);
  });

  it("shows the 409 that names the variable when a save is refused", async () => {
    const message = "Set by ANSWER__TEMPERATURE in the environment or .env. Remove it to edit here.";
    const { user } = await open({ "PUT /v1/settings/chat": () => json({ status: "error", message }, 409) });
    await user.click(within(model()).getByRole("button", { name: "Edit Chat model" }));
    await user.type(within(model()).getByRole("spinbutton", { name: "Temperature" }), "0");
    await user.click(within(model()).getByRole("button", { name: "Save" }));
    expect(await within(model()).findByRole("alert")).toHaveTextContent("ANSWER__TEMPERATURE");
  });
});

describe("Judge temperature, seed and allowed hosts", () => {
  it("has its own fields and saves them on the judge route only", async () => {
    const { user, server } = await open({
      "GET /v1/settings/judge": () => ({ ...JUDGE, seed: 3 }),
      "PUT /v1/settings/judge": () => ({ status: "ok", revision: "r2" }),
    });
    await waitFor(() => expect(judge()).toHaveTextContent("Seed: 3"));
    await user.click(within(judge()).getByRole("button", { name: "Edit claim check judge" }));
    await user.type(within(judge()).getByRole("spinbutton", { name: "Temperature" }), "0");
    await user.type(within(judge()).getByRole("textbox", { name: "Allowed hosts" }), "z-ai");
    await user.click(within(judge()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/judge")).toHaveLength(1));
    expect(server.find("PUT", "/v1/settings/judge")[0]?.body).toEqual({
      provider: "openrouter",
      model: GLM,
      reasoning: "",
      temperature: 0,
      allowed_hosts: "z-ai",
      revision: "r1",
    });
    expect(server.find("PUT", "/v1/settings/chat")).toHaveLength(0);
  });
});
