import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { settingsServer, WITH_CREDENTIALS } from "./test/fixtures";
import { DOWNLOADS_NEEDED_BOTH, DOWNLOADS_NEEDED_NONE, DOWNLOADS_NEEDED_UNKNOWN, ROUTER_DOWNLOADING, ROUTER_STOPPED } from "./test/llamacppFixtures";

const NEEDED = "GET /v1/llamacpp/router/downloads-needed";
const START = "POST /v1/llamacpp/router/start";

async function open(handlers = {}) {
  const server = settingsServer({ ...WITH_CREDENTIALS, ...handlers });
  startApp("#/settings/providers", server);
  await screen.findByRole("heading", { level: 3, name: "llama.cpp" });
  const panel = () => within(screen.getByRole("region", { name: "llama.cpp" })).getByRole("group", { name: "Router" });
  await waitFor(() => expect(within(panel()).getByRole("status")).toBeInTheDocument());
  return { server, user: userEvent.setup(), panel };
}

async function pressStart(panel: () => HTMLElement, user: ReturnType<typeof userEvent.setup>) {
  const button = within(panel()).getByRole("button", { name: "Start" });
  await waitFor(() => expect(button).toBeEnabled());
  await user.click(button);
}

const starts = (server: Awaited<ReturnType<typeof open>>["server"]) => server.find("POST", "/v1/llamacpp/router/start");

describe("Start asks before it downloads a large model", () => {
  it("names the models and the total size, and starts nothing until Download", async () => {
    const { panel, user, server } = await open({ [NEEDED]: () => DOWNLOADS_NEEDED_BOTH, [START]: () => ROUTER_DOWNLOADING });
    await pressStart(panel, user);

    const dialog = await screen.findByRole("dialog", { name: "Download 2 models, 6.5 GiB?" });
    expect(dialog).toHaveTextContent("Qwen/Qwen3-Embedding-4B-GGUF:Q8_0");
    expect(dialog).toHaveTextContent("4.0 GiB");
    expect(dialog).toHaveTextContent("Qwen/Qwen3-4B-GGUF:Q8_0");
    expect(dialog).toHaveTextContent("2.5 GiB");
    expect(starts(server)).toHaveLength(0);

    await user.click(within(dialog).getByRole("button", { name: "Download" }));

    await waitFor(() => expect(starts(server)).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("Cancel starts nothing and closes the dialog", async () => {
    const { panel, user, server } = await open({ [NEEDED]: () => DOWNLOADS_NEEDED_BOTH });
    await pressStart(panel, user);
    const dialog = await screen.findByRole("dialog");

    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(starts(server)).toHaveLength(0);
    expect(within(panel()).getByRole("status")).toHaveTextContent("Stopped");
  });

  it("shows no dialog and starts at once when every file is present", async () => {
    const { panel, user, server } = await open({ [NEEDED]: () => DOWNLOADS_NEEDED_NONE, [START]: () => ROUTER_STOPPED });
    await pressStart(panel, user);

    await waitFor(() => expect(starts(server)).toHaveLength(1));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("says the size is unknown when the model host gave none, and still names the models", async () => {
    const { panel, user } = await open({ [NEEDED]: () => DOWNLOADS_NEEDED_UNKNOWN });
    await pressStart(panel, user);

    const dialog = await screen.findByRole("dialog", { name: "Download 2 models?" });
    expect(dialog).toHaveTextContent("The size is unknown.");
    expect(dialog).toHaveTextContent("Qwen/Qwen3-Embedding-4B-GGUF:Q8_0");
    expect(dialog).toHaveTextContent("Qwen/Qwen3-4B-GGUF:Q8_0");
  });

  it("uses the singular for one model", async () => {
    const one = { ...DOWNLOADS_NEEDED_BOTH, models: DOWNLOADS_NEEDED_BOTH.models.slice(0, 1), total_bytes: DOWNLOADS_NEEDED_BOTH.models[0]!.size_bytes };
    const { panel, user } = await open({ [NEEDED]: () => one });
    await pressStart(panel, user);

    expect(await screen.findByRole("dialog", { name: "Download 1 model, 4.0 GiB?" })).toBeInTheDocument();
  });

  it("does not read the sizes before Start is pressed", async () => {
    const { server } = await open({ [NEEDED]: () => DOWNLOADS_NEEDED_BOTH });

    expect(server.find("GET", "/v1/llamacpp/router/downloads-needed")).toHaveLength(0);
  });

  it("starts nothing and says why when the sizes cannot be read at all", async () => {
    const { panel, user, server } = await open({ [NEEDED]: () => json({ status: "error", message: "raw server text" }, 500) });
    await pressStart(panel, user);

    expect(await within(panel()).findByRole("alert")).not.toHaveTextContent("raw server text");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(starts(server)).toHaveLength(0);
  });

  it("gives the plain external-server line when the mode changed under the page", async () => {
    const refused = json({ status: "error", message: "raw server text", reason: "external-server" }, 409);
    const { panel, user } = await open({ [NEEDED]: () => refused });
    await pressStart(panel, user);

    expect(await within(panel()).findByRole("alert")).toHaveTextContent("OMRS does not start a router while the mode is Use this address.");
  });
});

describe("The state line while a Start waits for the downloads", () => {
  it("says Downloading, not Failed, and offers Stop", async () => {
    const { panel } = await open({ "GET /v1/llamacpp/router": () => ROUTER_DOWNLOADING });

    await waitFor(() => expect(within(panel()).getByRole("status")).toHaveTextContent("Downloading"));
    expect(within(panel()).getByRole("status")).not.toHaveTextContent("Failed");
    expect(within(panel()).getByRole("button", { name: "Start" })).toBeDisabled();
    expect(within(panel()).getByRole("button", { name: "Stop" })).toBeEnabled();
  });

  it("still says Failed with the server line when a download failed", async () => {
    const failed = { ...ROUTER_STOPPED, state: "failed" as const, reason: "not-downloaded" as const, reason_text: "No model is downloaded yet." };
    const { panel } = await open({ "GET /v1/llamacpp/router": () => failed });

    await waitFor(() => expect(within(panel()).getByRole("status")).toHaveTextContent("Failed: No model is downloaded yet."));
  });

  it("says Starting, with no reason, for a start that does not wait", async () => {
    const { panel } = await open({ "GET /v1/llamacpp/router": () => ({ ...ROUTER_STOPPED, state: "starting" as const }) });

    await waitFor(() => expect(within(panel()).getByRole("status")).toHaveTextContent(/^Starting$/));
  });
});
