import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { JudgeSettings } from "../api/settings";
import { startApp } from "../test/startApp";
import { CHAT_READY, CONNECTIONS, JUDGE_SAVED, OLLAMA, OPENROUTER, settingsServer } from "./test/fixtures";

const STRATEGY = { judge: "chat", judges: ["chat", "clef_flash", "granite_guardian"], judge_locked: false, judge_lock_reason: null };
const JUDGE: JudgeSettings = { ...JUDGE_SAVED, ...STRATEGY };

async function open(handlers = {}) {
  const server = settingsServer({
    "GET /v1/connections": () => ({ ...CONNECTIONS, connections: [OLLAMA, OPENROUTER] }),
    "GET /v1/settings/chat": () => CHAT_READY,
    "GET /v1/settings/judge": () => JUDGE,
    "GET /v1/settings/chat/reasoning-levels": () => ({ status: "ok", known: false }),
    ...handlers,
  });
  startApp("#/settings/chat", server);
  await screen.findByRole("region", { name: "Claim check judge" });
  return { server, user: userEvent.setup() };
}

function judge() {
  return screen.getByRole("region", { name: "Claim check judge" });
}

describe("Claim judge strategy on the Judge panel", () => {
  it("shows the strategy in force with the registered strategies as options", async () => {
    const { user } = await open();
    const select = await within(judge()).findByRole("combobox", { name: "Judge type" });
    expect(select).toHaveTextContent("Chat model");
    await user.click(select);
    expect(screen.getByRole("option", { name: "Clef-Flash decision model" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Granite Guardian" })).toBeInTheDocument();
  });

  it("lists a strategy name the web does not know, from the server", async () => {
    const { user } = await open({ "GET /v1/settings/judge": () => ({ ...JUDGE, judges: [...STRATEGY.judges, "future_judge"] }) });
    await user.click(await within(judge()).findByRole("combobox", { name: "Judge type" }));
    expect(screen.getByRole("option", { name: "future_judge" })).toBeInTheDocument();
  });

  it("saves the strategy alone on the judge route", async () => {
    let state = JUDGE;
    const { user, server } = await open({
      "GET /v1/settings/judge": () => state,
      "PUT /v1/settings/judge": (body: Record<string, unknown>) => {
        state = { ...state, judge: body.judge as string };
        return { status: "ok", revision: "r2" };
      },
    });
    await user.click(await within(judge()).findByRole("combobox", { name: "Judge type" }));
    await user.click(screen.getByRole("option", { name: "Clef-Flash decision model" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/judge")).toHaveLength(1));
    expect(server.find("PUT", "/v1/settings/judge")[0]?.body).toEqual({ judge: "clef_flash", revision: "r1" });
    await waitFor(() => expect(within(judge()).getByRole("combobox", { name: "Judge type" })).toHaveTextContent("Clef-Flash"));
  });

  it("shows a locked strategy read-only with the reason", async () => {
    const reason = "Set by ANSWER__VERIFY_JUDGE in the environment or .env. Remove it to edit here.";
    await open({ "GET /v1/settings/judge": () => ({ ...JUDGE, judge: "granite_guardian", judge_locked: true, judge_lock_reason: reason }) });
    await waitFor(() => expect(judge()).toHaveTextContent("Judge type: Granite Guardian"));
    expect(within(judge()).queryByRole("combobox", { name: "Judge type" })).toBeNull();
    expect(judge()).toHaveTextContent(reason);
  });
});
