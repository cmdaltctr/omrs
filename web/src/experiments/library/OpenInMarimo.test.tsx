import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { EditorInfo } from "../../api/plugins";
import { json, type Handler } from "../../test/fakeDocumentsServer";
import { EDITOR_TOKEN, libraryEditorOpened, MARIMO, type ServerState } from "../test/experimentsServer";
import { defaultLibrary, OVERLAP, RERANKER } from "../test/libraryServer";
import { openExperiments } from "../test/openExperiments";

const EDITOR_PATH = `/v1/experiment-projects/p1/experiments/${RERANKER}/editor`;
const CONSENT =
  "This opens analysis.marimo.py in marimo in a new tab. The notebook runs in this project's Python environment with your full file and network access, like any program you start. OMRS does not sandbox it. Cells do not run until you run them. OMRS adds analysis.marimo.py and marimo adds __marimo__/ in the experiment folder. Add both to your .gitignore.";

function openPage(initial: Partial<ServerState> = {}, extra: Record<string, Handler> = {}) {
  return openExperiments({ library: defaultLibrary(), plugins: [MARIMO], ...initial }, extra, `#/experiments/library/p1/${RERANKER}`);
}

function libraryEditor(folder = RERANKER, launchId = "launch_2"): EditorInfo {
  return {
    launch_id: launchId,
    plugin: "marimo",
    notebook: `/work/p1/experiments/${folder}/analysis.marimo.py`,
    experiment_context: null,
    url_without_token: "http://127.0.0.1:2720/",
    project_id: "p1",
    folder,
  };
}

const trigger = () => screen.findByRole("button", { name: "Open in marimo" });
const dialog = () => screen.findByRole("dialog", { name: "Open in marimo" });

async function consentAndOpen(user: ReturnType<typeof openPage>["user"]) {
  await user.click(await trigger());
  const box = await dialog();
  await user.click(within(box).getByRole("checkbox", { name: "I understand this notebook runs with my full access" }));
  await user.click(within(box).getByRole("button", { name: "Open in marimo" }));
}

afterEach(() => vi.restoreAllMocks());

describe("open an experiment in marimo", () => {
  it("is disabled with a hint that links to the Code editor section when no launchable marimo exists", async () => {
    const { user } = openPage({ plugins: [{ ...MARIMO, status: "incompatible", launchable: false }] });
    await screen.findByRole("heading", { level: 1, name: "1. Title of reranker threshold" });
    const link = await screen.findByRole("link", { name: "Code editor" });
    expect(link.closest("p")).toHaveTextContent("Register marimo in Experiments, Code editor, to open notebooks.");
    expect(await trigger()).toBeDisabled();
    expect(link).toHaveAttribute("href", "#/experiments/code-editor");
    await user.click(link);
    expect(await screen.findByRole("button", { name: "Code editor", pressed: true })).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "Plugins" })).toBeInTheDocument();
  });

  it("needs the consent box before it sends anything, and Cancel returns focus to the button", async () => {
    const { server, user } = openPage();
    const button = await trigger();
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);
    const box = await dialog();
    expect(box.textContent).toContain(CONSENT);
    expect(within(box).getAllByText("analysis.marimo.py")[0]!.tagName).toBe("CODE");
    expect(within(box).getByText("__marimo__/").tagName).toBe("CODE");
    expect(within(box).getByText(".gitignore").tagName).toBe("CODE");
    const confirm = within(box).getByRole("button", { name: "Open in marimo" });
    expect(confirm).toBeDisabled();
    await user.click(confirm);
    await user.click(within(box).getByRole("checkbox", { name: "I understand this notebook runs with my full access" }));
    expect(confirm).toBeEnabled();
    await user.click(within(box).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(server.find("POST", EDITOR_PATH)).toHaveLength(0);
    await waitFor(() => expect(button).toHaveFocus());
  });

  it("clears the consent box every time the dialog opens", async () => {
    vi.spyOn(window, "open").mockReturnValue(null);
    const { user } = openPage();
    await waitFor(async () => expect(await trigger()).toBeEnabled());
    await user.click(await trigger());
    await user.click(within(await dialog()).getByRole("checkbox", { name: /I understand/ }));
    await user.click(within(await dialog()).getByRole("button", { name: "Cancel" }));
    await user.click(await trigger());
    expect(within(await dialog()).getByRole("checkbox", { name: /I understand/ })).not.toBeChecked();
    await user.click(within(await dialog()).getByRole("checkbox", { name: /I understand/ }));
    await user.click(within(await dialog()).getByRole("button", { name: "Open in marimo" }));
    await screen.findByRole("heading", { name: "marimo is open in a new tab" });
    await user.click(await trigger());
    expect(within(await dialog()).getByRole("checkbox", { name: /I understand/ })).not.toBeChecked();
  });

  it("shows a busy confirm button and a polite status while the server opens marimo", async () => {
    vi.spyOn(window, "open").mockReturnValue(null);
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => (release = resolve));
    const { user } = openPage({}, { [`POST ${EDITOR_PATH}`]: async () => (await held, json(libraryEditorOpened(), 201)) });
    await waitFor(async () => expect(await trigger()).toBeEnabled());
    await consentAndOpen(user);
    const busy = await within(await dialog()).findByRole("button", { name: "Opening marimo" });
    expect(busy).toHaveAttribute("aria-busy", "true");
    expect(busy).toBeDisabled();
    expect(screen.getAllByRole("status").some((node) => node.textContent === "Opening marimo")).toBe(true);
    release();
    await screen.findByRole("heading", { name: "marimo is open in a new tab" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens a new tab with noopener and shows the token once, the notebook state, the stale note and shadowed packages", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const opened = libraryEditorOpened({ source_newer: true, environment: { kind: "project", python: "3.14", marimo_in_project: false, shadowed: ["anyio", "starlette"] } });
    const { server, user } = openPage({}, { [`POST ${EDITOR_PATH}`]: () => json(opened, 201) });
    await waitFor(async () => expect(await trigger()).toBeEnabled());
    await consentAndOpen(user);
    const card = await screen.findByRole("region", { name: "marimo editor" });
    expect(server.find("POST", EDITOR_PATH)[0]!.body).toEqual({ consent: true });
    expect(open).toHaveBeenCalledWith("http://127.0.0.1:2719/", "_blank", "noopener,noreferrer");
    expect(within(card).getByRole("heading", { name: "marimo is open in a new tab" })).toBeInTheDocument();
    expect(within(card).getAllByText("http://127.0.0.1:2719/").length).toBeGreaterThan(0);
    expect(within(card).getByText(EDITOR_TOKEN)).toBeInTheDocument();
    expect(within(card).getByText("Paste it into the marimo sign-in page.")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Open the editor tab again" })).toHaveAttribute("href", "http://127.0.0.1:2719/");
    expect(within(card).getByText("Converted from analysis.py.")).toBeInTheDocument();
    expect(within(card).getByText("analysis.py changed after this notebook was made. Delete analysis.marimo.py to make a new copy.")).toBeInTheDocument();
    expect(within(card).getByText(/anyio, starlette/)).toBeInTheDocument();
    expect(JSON.stringify({ ...localStorage })).not.toContain(EDITOR_TOKEN);
    expect(JSON.stringify({ ...sessionStorage })).not.toContain(EDITOR_TOKEN);
    expect(window.location.href).not.toContain(EDITOR_TOKEN);
    await user.click(within(card).getByRole("button", { name: "Hide token" }));
    expect(screen.queryByText(EDITOR_TOKEN)).toBeNull();
    expect(within(card).getByRole("heading", { name: "marimo is open in a new tab" })).toBeInTheDocument();
  });

  it.each([
    ["created", "Created an empty notebook."],
    ["existing", "Opened the existing notebook."],
  ] as const)("says the notebook was %s and shows no stale note or shadow warning without cause", async (state, line) => {
    vi.spyOn(window, "open").mockReturnValue(null);
    const opened = libraryEditorOpened({ notebook_state: state, environment: { kind: "project", python: "3.14", marimo_in_project: true, shadowed: [] } });
    const { user } = openPage({}, { [`POST ${EDITOR_PATH}`]: () => json(opened, 201) });
    await waitFor(async () => expect(await trigger()).toBeEnabled());
    await consentAndOpen(user);
    const card = await screen.findByRole("region", { name: "marimo editor" });
    expect(within(card).getByText(line)).toBeInTheDocument();
    expect(card.textContent).not.toContain("changed after this notebook was made");
    expect(card.textContent).not.toContain("shadow");
  });

  it("shows the running editor without a token after a reload, and only for this experiment", async () => {
    openPage({ editors: [libraryEditor(OVERLAP, "launch_3"), libraryEditor()] });
    const card = await screen.findByRole("region", { name: "marimo editor" });
    expect(within(card).getByRole("heading", { name: "marimo is running for this experiment" })).toBeInTheDocument();
    expect(within(card).getAllByText("http://127.0.0.1:2720/").length).toBeGreaterThan(0);
    expect(within(card).getByRole("button", { name: "Stop editor launch_2" })).toBeInTheDocument();
    expect(within(card).queryByText(EDITOR_TOKEN)).toBeNull();
    expect(within(card).queryByRole("button", { name: "Copy token" })).toBeNull();
    expect(within(card).queryByRole("button", { name: "Stop editor launch_3" })).toBeNull();
  });

  it("stops the editor after confirmation and refreshes the plugin list", async () => {
    const { server, user } = openPage({ editors: [libraryEditor()] });
    const card = await screen.findByRole("region", { name: "marimo editor" });
    await user.click(within(card).getByRole("button", { name: "Stop editor launch_2" }));
    expect(server.find("DELETE", "/v1/plugin-editors/")).toHaveLength(0);
    expect(within(card).getByText(/Notebook files are kept/)).toBeInTheDocument();
    const listsBefore = server.find("GET", "/v1/plugins").length;
    await user.click(within(card).getByRole("button", { name: "Confirm stop" }));
    await waitFor(() => expect(server.find("DELETE", "/v1/plugin-editors/launch_2")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("region", { name: "marimo editor" })).toBeNull());
    expect(server.find("GET", "/v1/plugins").length).toBeGreaterThan(listsBefore);
  });

  it("stops an editor it has just opened and removes its card", async () => {
    vi.spyOn(window, "open").mockReturnValue(null);
    const { server, user } = openPage();
    await waitFor(async () => expect(await trigger()).toBeEnabled());
    await consentAndOpen(user);
    const card = await screen.findByRole("region", { name: "marimo editor" });
    await user.click(within(card).getByRole("button", { name: "Stop editor launch_2" }));
    await user.click(within(card).getByRole("button", { name: "Confirm stop" }));
    await waitFor(() => expect(server.find("DELETE", "/v1/plugin-editors/launch_2")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("region", { name: "marimo editor" })).toBeNull());
  });

  it.each([
    ["no_project_environment", /uv sync/],
    ["python_mismatch", /^The project \.venv uses Python 3\.12 and marimo runs on Python 3\.14\.$/],
    ["no_free_port", /2719 to 2721/],
  ])("shows one plain line for the refusal %s and opens no tab", async (reason, line) => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const message = reason === "python_mismatch" ? "The project .venv uses Python 3.12 and marimo runs on Python 3.14." : "RAW server text";
    const { user } = openPage({}, { [`POST ${EDITOR_PATH}`]: () => json({ status: "error", reason, message }, 409) });
    await waitFor(async () => expect(await trigger()).toBeEnabled());
    await consentAndOpen(user);
    const alert = await screen.findByRole("alert");
    expect(alert.querySelector("p")!.textContent).toMatch(line);
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(document.body.textContent).not.toContain("RAW");
    expect(open).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it.each([
    ["converter_missing", /^marimo needs jupytext to convert analysis\.py\./],
    ["tool_install_running", /^marimo is being installed or removed on the Integrations page\./],
  ])("links the refusal %s to the marimo card", async (reason, line) => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const message = reason === "converter_missing" ? "marimo needs jupytext to convert analysis.py. Install marimo with jupytext from the marimo card." : "RAW server text";
    const { user } = openPage({}, { [`POST ${EDITOR_PATH}`]: () => json({ status: "error", reason, message }, 409) });
    await waitFor(async () => expect(await trigger()).toBeEnabled());
    await consentAndOpen(user);
    const alert = await screen.findByRole("alert");
    expect(alert.querySelector("p")!.textContent).toMatch(line);
    expect(within(alert).getByRole("link", { name: "Open the marimo card" })).toHaveAttribute("href", "#/integrations/marimo");
  });

  it("gives other refusals no marimo card link", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { user } = openPage({}, { [`POST ${EDITOR_PATH}`]: () => json({ status: "error", reason: "no_free_port", message: "RAW" }, 409) });
    await waitFor(async () => expect(await trigger()).toBeEnabled());
    await consentAndOpen(user);
    expect(within(await screen.findByRole("alert")).queryByRole("link")).toBeNull();
  });

  it("shows the running editor when the server says one already runs", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const editors: EditorInfo[] = [];
    const { user } = openPage({ editors }, {
      [`POST ${EDITOR_PATH}`]: () => {
        editors.push(libraryEditor());
        return json({ status: "error", reason: "editor_running", message: "RAW running", launch_id: "launch_2" }, 409);
      },
    });
    await waitFor(async () => expect(await trigger()).toBeEnabled());
    await consentAndOpen(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("marimo is already open for this experiment.");
    const card = await screen.findByRole("region", { name: "marimo editor" });
    expect(within(card).getByRole("heading", { name: "marimo is running for this experiment" })).toBeInTheDocument();
  });

  it("clears the editor_running line when that editor is stopped", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const editors: EditorInfo[] = [];
    const { server, user } = openPage({ editors }, {
      [`POST ${EDITOR_PATH}`]: () => {
        editors.push(libraryEditor());
        return json({ status: "error", reason: "editor_running", message: "RAW running", launch_id: "launch_2" }, 409);
      },
    });
    await waitFor(async () => expect(await trigger()).toBeEnabled());
    await consentAndOpen(user);
    await screen.findByRole("alert");
    const card = await screen.findByRole("region", { name: "marimo editor" });
    await user.click(within(card).getByRole("button", { name: "Stop editor launch_2" }));
    editors.length = 0;
    await user.click(within(card).getByRole("button", { name: "Confirm stop" }));
    await waitFor(() => expect(server.find("DELETE", "/v1/plugin-editors/launch_2")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });
});
