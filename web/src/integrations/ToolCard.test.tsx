import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ExternalTool, Integration, IntegrationInstall } from "../api/integrations";
import { documentsServer, json, type Handler } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";

const INSTALL_COMMAND = 'uv tool install "marimo>=0.25.1,<0.26.0" --with jupytext';
const CAUTION = "Install replaces your marimo 0.27.0 tool environment with marimo >=0.25.1,<0.26.0 and jupytext.";
const PATH = "/home/u/.local/bin/marimo";

const MARIMO: ExternalTool = {
  id: "marimo",
  name: "marimo",
  purpose: "Notebook editor for the Library and the Code editor. It goes into its own uv tool environment, outside OMRS.",
  availability: "not-installed",
  version: null,
  jupytext: false,
  executable: null,
  requirement: "marimo>=0.25.1,<0.26.0",
  install_command: INSTALL_COMMAND,
  uninstall_command: "uv tool uninstall marimo",
  installable: true,
  install_reason: null,
  install_caution: null,
  uninstallable: false,
  uninstall_reason: "not-installed",
  plugin_status: null,
};

const READY: ExternalTool = { ...MARIMO, availability: "ready", version: "0.25.1", jupytext: true, executable: PATH, installable: false, install_reason: "already-installed" };
const OWN_READY: ExternalTool = { ...READY, uninstallable: true, uninstall_reason: null };
const NO_JUPYTEXT: ExternalTool = { ...MARIMO, availability: "needs-jupytext", version: "0.25.1", executable: PATH, install_caution: CAUTION.replace("0.27.0", "0.25.1"), uninstall_reason: "not-installed-by-app" };
const OUTSIDE: ExternalTool = { ...MARIMO, availability: "outside-range", version: "0.27.0", jupytext: true, executable: PATH, install_caution: CAUTION, uninstall_reason: "not-installed-by-app" };
const UNKNOWN: ExternalTool = { ...MARIMO, availability: "unknown", installable: false, install_reason: "uv-not-found", uninstall_reason: "uv-not-found" };

const CHROMA: Integration = {
  id: "chroma",
  name: "Chroma vector store",
  purpose: "Purpose of chroma.",
  extra: "chroma",
  install_command: 'uv tool install --reinstall "omrs[web,chroma] @ ~/src/omrs"',
  pip_command: 'pip install "omrs[chroma]"',
  availability: "not-installed",
  installable: true,
  install_reason: null,
  packages: ["chromadb>=1.0"],
  install_caution: null,
  base: false,
  uninstallable: false,
  uninstall_reason: "not-installed",
  uninstall_setting: null,
  removes: [],
  keeps: [],
  lasting_uninstall_command: null,
  pending_restart: null,
  uninstall_profile: null,
};

const IDLE: IntegrationInstall = { state: "idle", action: null, extra: null, tool: null, started_at: null, finished_at: null, reason: null, exit_code: null, output: [] };
const TOOL_RUNNING: IntegrationInstall = { ...IDLE, state: "running", action: "install", tool: "marimo", started_at: "2026-10-26T10:00:00Z", output: ["Resolving"] };
const TOOL_SUCCEEDED: IntegrationInstall = { ...TOOL_RUNNING, state: "succeeded", finished_at: "2026-10-26T10:00:30Z", exit_code: 0, output: ["Installed 2 executables"] };
const TOOL_FAILED: IntegrationInstall = { ...TOOL_RUNNING, state: "failed", finished_at: "2026-10-26T10:00:30Z", reason: "exit-code", exit_code: 1, output: ["error: no network", "line 2"] };
const EXTRA_RUNNING: IntegrationInstall = { ...IDLE, state: "running", action: "install", extra: "chroma", started_at: "2026-10-26T10:00:00Z", output: ["Resolving"] };

interface Options {
  tool?: ExternalTool;
  install?: IntegrationInstall;
  installType?: "uv-tool" | "checkout";
  post?: Handler;
  postUninstall?: Handler;
}

/** A server whose catalogue and job the test moves on by hand. */
function toolServer(options: Options = {}) {
  const state = { tool: options.tool ?? MARIMO, install: options.install ?? IDLE, catalogue: [CHROMA] };
  const server = documentsServer({
    "GET /v1/integrations": () => ({ status: "ok", install_type: options.installType ?? "uv-tool", integrations: state.catalogue, tools: [state.tool] }),
    "GET /v1/integrations/install": () => ({ status: "ok", install: state.install }),
    "POST /v1/integrations/tools/marimo/install":
      options.post ??
      (() => {
        state.install = TOOL_RUNNING;
        return json({ status: "ok", install: state.install }, 202);
      }),
    "POST /v1/integrations/tools/marimo/uninstall":
      options.postUninstall ??
      (() => {
        state.install = { ...TOOL_RUNNING, action: "uninstall" };
        return json({ status: "ok", install: state.install }, 202);
      }),
    "POST /v1/integrations/:extra/install": () => {
      state.install = EXTRA_RUNNING;
      return json({ status: "ok", install: state.install }, 202);
    },
    "GET /v1/server/power": () => ({ managed: true }),
  });
  startApp("#/integrations", server);
  return { server, state };
}

const toolCard = async () => {
  const list = await screen.findByRole("list", { name: "External tools" });
  return within(list).getByRole("listitem");
};
const extraCard = async () => within(await screen.findByRole("list", { name: "Integrations" })).getByRole("listitem");
const badge = (card: HTMLElement, text: string) => within(card).getByText(text, { selector: "[data-slot=badge]" });
const advance = (ms: number) => act(async () => void (await vi.advanceTimersByTimeAsync(ms)));
const posts = (server: ReturnType<typeof documentsServer>) => server.calls.filter((call) => call.method === "POST");

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function setup() {
  return userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) });
}

async function pressInstall() {
  const user = setup();
  await user.click(within(await toolCard()).getByRole("button", { name: "Install marimo" }));
  return { user, dialog: await screen.findByRole("dialog", { name: "Install marimo?" }) };
}

describe("the marimo card", () => {
  it("sits in an External tools group below the extras, with a red Not installed badge and the copy command", async () => {
    toolServer();
    const heading = await screen.findByRole("heading", { level: 2, name: "External tools" });
    const extras = await screen.findByRole("list", { name: "Integrations" });
    expect(extras.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const card = await toolCard();
    expect(within(card).getByRole("heading", { name: "marimo" })).toBeInTheDocument();
    expect(card).toHaveTextContent(MARIMO.purpose);
    expect(badge(card, "Not installed")).toHaveClass("text-status-error-label");
    expect(card).toHaveTextContent(INSTALL_COMMAND);
    expect(within(card).getByRole("button", { name: "Install marimo" })).toBeEnabled();
  });

  it("shows Installed, the version and the executable path when ready, and no Install button", async () => {
    toolServer({ tool: READY });
    const card = await toolCard();
    expect(badge(card, "Installed")).toHaveClass("text-status-success-label");
    expect(card).toHaveTextContent("0.25.1");
    expect(within(card).getByText(PATH)).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Install marimo" })).toBeNull();
  });

  it("says jupytext is missing, shows the red caution before Install, and the dialog repeats it", async () => {
    toolServer({ tool: NO_JUPYTEXT });
    const card = await toolCard();
    expect(card).toHaveTextContent(/jupytext is missing/);
    expect(card).toHaveTextContent(/Library cannot convert analysis\.py without it/);
    const caution = card.querySelector("[data-slot=install-caution]");
    expect(caution).toHaveTextContent(NO_JUPYTEXT.install_caution!);
    const button = within(card).getByRole("button", { name: "Install marimo" });
    expect(caution!.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const { dialog } = await pressInstall();
    expect(dialog).toHaveTextContent(NO_JUPYTEXT.install_caution!);
  });

  it("names the installed version outside the range in a red caution", async () => {
    toolServer({ tool: OUTSIDE });
    const card = await toolCard();
    expect(card.querySelector("[data-slot=install-caution]")).toHaveTextContent(CAUTION);
    expect(card).toHaveTextContent("0.27.0");
  });

  it("shows the copy command and no Install or Uninstall button when the state is unknown", async () => {
    toolServer({ tool: UNKNOWN });
    const card = await toolCard();
    expect(badge(card, "Unknown")).toBeInTheDocument();
    expect(card).toHaveTextContent(INSTALL_COMMAND);
    expect(within(card).queryByRole("button", { name: "Install marimo" })).toBeNull();
    expect(within(card).queryByRole("button", { name: "Uninstall marimo" })).toBeNull();
  });

  it("can be reached as #/integrations/marimo", async () => {
    const server = documentsServer({
      "GET /v1/integrations": () => ({ status: "ok", install_type: "uv-tool", integrations: [CHROMA], tools: [MARIMO] }),
      "GET /v1/integrations/install": () => ({ status: "ok", install: IDLE }),
    });
    startApp("#/integrations/marimo", server);
    const card = await toolCard();
    await waitFor(() => expect(within(card).getByRole("heading", { name: "marimo" }).closest("[tabindex='-1']")).toHaveFocus());
  });
});

describe("install marimo", () => {
  it("names the command, its own tool environment and no restart, and Cancel calls nothing", async () => {
    const { server } = toolServer();
    const { user, dialog } = await pressInstall();
    expect(dialog).toHaveTextContent(INSTALL_COMMAND);
    expect(dialog).toHaveTextContent(/its own uv tool environment, outside OMRS/);
    expect(dialog).toHaveTextContent(/No restart is needed/);
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await advance(1500);
    expect(posts(server)).toHaveLength(0);
  });

  it("posts, shows progress, then Installed with a link to register marimo in the Code editor", async () => {
    const { server, state } = toolServer({ installType: "checkout" });
    const { user, dialog } = await pressInstall();
    await user.click(within(dialog).getByRole("button", { name: "Install" }));
    await waitFor(() => expect(server.find("POST", "/v1/integrations/tools/marimo/install")).toHaveLength(1));
    const card = await toolCard();
    expect(await within(card).findByRole("status")).toHaveTextContent(/Installing marimo/);
    // An extras card does not react to a tool job.
    expect(within(await extraCard()).queryByRole("status")).toBeNull();

    state.install = TOOL_SUCCEEDED;
    state.tool = OWN_READY;
    await advance(1100);
    await waitFor(() => expect(badge(card, "Installed")).toBeInTheDocument());
    const link = within(card).getByRole("link", { name: "Code editor" });
    expect(link).toHaveAttribute("href", "#/experiments/code-editor");
    expect(link.closest("p")).toHaveTextContent("Register marimo in Experiments, Code editor.");
    expect(card).not.toHaveTextContent(/restart/i);
  });

  it("says Recheck marimo in Code editor after an install when marimo is registered", async () => {
    toolServer({ tool: { ...OWN_READY, plugin_status: "unchecked" }, install: TOOL_SUCCEEDED });
    const card = await toolCard();
    const link = await within(card).findByRole("link", { name: "Code editor" });
    expect(link.closest("p")).toHaveTextContent("Recheck marimo in Code editor.");
  });

  it("shows the output lines and Retry when the install fails", async () => {
    const { server } = toolServer({ install: TOOL_FAILED });
    const card = await toolCard();
    expect(await within(card).findByRole("alert")).toHaveTextContent("The install failed.");
    expect(within(card).getByLabelText("Install output for marimo")).toHaveTextContent("error: no network");
    await setup().click(within(card).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(server.find("POST", "/v1/integrations/tools/marimo/install")).toHaveLength(1));
  });

  it("gives the editor-running refusal its own line", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    toolServer({ post: () => json({ status: "error", message: "RAW", reason: "editor-running" }, 409) });
    const { user, dialog } = await pressInstall();
    await user.click(within(dialog).getByRole("button", { name: "Install" }));
    const card = await toolCard();
    expect(await within(card).findByRole("alert")).toHaveTextContent("A marimo editor that OMRS started is running. Stop it in Experiments, Code editor, then try again.");
    expect(document.body.textContent).not.toContain("RAW");
  });
});

describe("one job at a time", () => {
  it("disables the marimo Install button while an extras job runs, from the job alone", async () => {
    // The tool entry still says installable, so only the page's busy state can disable the button.
    toolServer({ tool: MARIMO, install: EXTRA_RUNNING });
    const card = await toolCard();
    await waitFor(() => expect(within(card).getByRole("button", { name: "Install marimo" })).toBeDisabled());
    expect(within(card).queryByRole("status")).toBeNull();
  });

  it("disables the marimo Uninstall button while an extras job runs, from the job alone", async () => {
    toolServer({ tool: OWN_READY, install: EXTRA_RUNNING });
    const card = await toolCard();
    await waitFor(() => expect(within(card).getByRole("button", { name: "Uninstall marimo" })).toBeDisabled());
  });

  it("disables every extras Install button while the marimo job runs", async () => {
    toolServer({ install: TOOL_RUNNING });
    const chroma = await extraCard();
    await waitFor(() => expect(within(chroma).getByRole("button", { name: "Install Chroma vector store" })).toBeDisabled());
    expect(within(chroma).queryByRole("status")).toBeNull();
    expect(await within(await toolCard()).findByRole("status")).toHaveTextContent(/Installing marimo/);
  });
});

describe("uninstall marimo", () => {
  it("shows Uninstall only when uninstallable, warns about the whole environment and the registration, then posts", async () => {
    const { server, state } = toolServer({ tool: OWN_READY });
    const user = setup();
    const card = await toolCard();
    await user.click(within(card).getByRole("button", { name: "Uninstall marimo" }));
    const dialog = await screen.findByRole("dialog", { name: "Uninstall marimo?" });
    expect(dialog).toHaveTextContent("uv tool uninstall marimo");
    expect(dialog).toHaveTextContent(/whole marimo tool environment/);
    expect(dialog).toHaveTextContent(/Code editor then shows as unavailable/);
    await user.click(within(dialog).getByRole("button", { name: "Uninstall" }));
    await waitFor(() => expect(server.find("POST", "/v1/integrations/tools/marimo/uninstall")).toHaveLength(1));
    expect(await within(card).findByRole("status")).toHaveTextContent(/Uninstalling marimo/);

    state.install = { ...TOOL_SUCCEEDED, action: "uninstall" };
    state.tool = MARIMO;
    await advance(1100);
    await waitFor(() => expect(badge(card, "Not installed")).toBeInTheDocument());
  });

  it("shows no Uninstall button on a ready marimo that the card did not install", async () => {
    toolServer({ tool: { ...READY, uninstall_reason: "not-installed-by-app" } });
    const card = await toolCard();
    expect(within(card).queryByRole("button", { name: "Uninstall marimo" })).toBeNull();
    expect(within(card).getByRole("button", { name: "Copy uninstall command for marimo" })).toBeInTheDocument();
    expect(card).toHaveTextContent("uv tool uninstall marimo");
  });

  it.each([
    ["editor-running", "A marimo editor that OMRS started is running. Stop it in Experiments, Code editor, then try again."],
    ["not-installed-by-app", "This marimo was not installed from this card, so the app does not remove it. Use the command on the card in a terminal."],
  ])("gives the uninstall refusal %s its own line", async (reason, line) => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    toolServer({ tool: OWN_READY, postUninstall: () => json({ status: "error", message: "RAW", reason }, 409) });
    const user = setup();
    const card = await toolCard();
    await user.click(within(card).getByRole("button", { name: "Uninstall marimo" }));
    await user.click(within(await screen.findByRole("dialog", { name: "Uninstall marimo?" })).getByRole("button", { name: "Uninstall" }));
    expect(await within(card).findByRole("alert")).toHaveTextContent(line);
  });
});
