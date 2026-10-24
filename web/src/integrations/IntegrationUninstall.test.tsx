import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Integration, IntegrationInstall } from "../api/integrations";
import { documentsServer, json, type Handler } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";

const SOURCE = "~/src/omrs";

/** An installed entry the server can uninstall now. */
function installed(id: string, name: string, change: Partial<Integration> = {}): Integration {
  return {
    id,
    name,
    purpose: `Purpose of ${id}.`,
    extra: id,
    install_command: `uv tool install --reinstall "omrs[web,${id}] @ ${SOURCE}"`,
    pip_command: `pip install "omrs[${id}]"`,
    availability: "available",
    installable: false,
    install_reason: "already-installed",
    packages: [`package-for-${id}>=1.0`],
    install_caution: null,
    base: false,
    uninstallable: true,
    uninstall_reason: null,
    uninstall_setting: null,
    removes: [`package-for-${id}`],
    keeps: [],
    lasting_uninstall_command: null,
    pending_restart: null,
    ...change,
  };
}

const CHROMA = installed("chroma", "Chroma vector store", { removes: ["chromadb", "llama-index-vector-stores-chroma"] });
const AZURE: Integration = {
  ...installed("azure", "Azure Document Intelligence"),
  availability: "not-installed",
  installable: true,
  install_reason: null,
  uninstallable: false,
  uninstall_reason: "not-installed",
  removes: [],
};
const MAGIKA: Integration = {
  ...installed("magika", "Magika file detection"),
  extra: null,
  install_command: null,
  pip_command: null,
  packages: [],
  base: true,
  install_reason: "not-installable-here",
  uninstallable: false,
  uninstall_reason: "not-uninstallable-here",
  removes: [],
};
const PDF_INSPECTOR: Integration = { ...installed("pdf-inspector", "PDF reader: pdf-inspector"), base: true, install_command: null, uninstallable: false, uninstall_reason: "not-uninstallable-here", removes: [] };

const IDLE: IntegrationInstall = { state: "idle", action: null, extra: null, started_at: null, finished_at: null, reason: null, exit_code: null, output: [] };
const RUNNING: IntegrationInstall = { ...IDLE, state: "running", action: "uninstall", extra: "chroma", started_at: "2026-10-24T10:00:00Z", output: ["Uninstalling"] };
const SUCCEEDED: IntegrationInstall = { ...RUNNING, state: "succeeded", finished_at: "2026-10-24T10:00:10Z", exit_code: 0, output: ["Uninstalled 2 packages"] };
const FAILED: IntegrationInstall = { ...RUNNING, state: "failed", finished_at: "2026-10-24T10:00:10Z", reason: "exit-code", exit_code: 1, output: ["error: cannot remove chromadb"] };

/** A server whose job state the test moves on by hand. */
function uninstallServer(options: { install?: IntegrationInstall; catalogue?: Integration[]; post?: Handler } = {}) {
  const state = { install: options.install ?? IDLE, catalogue: options.catalogue ?? [CHROMA, AZURE, MAGIKA, PDF_INSPECTOR] };
  const server = documentsServer({
    "GET /v1/integrations": () => ({ status: "ok", install_type: "uv-tool", integrations: state.catalogue }),
    "GET /v1/integrations/install": () => ({ status: "ok", install: state.install }),
    "POST /v1/integrations/:extra/install": (_body, call) => {
      state.install = { ...RUNNING, action: "install", extra: call.path.split("/")[3] ?? null };
      return json({ status: "ok", install: state.install }, 202);
    },
    "POST /v1/integrations/:extra/uninstall":
      options.post ??
      ((_body, call) => {
        state.install = { ...RUNNING, extra: call.path.split("/")[3] ?? null };
        return json({ status: "ok", install: state.install }, 202);
      }),
    "GET /v1/server/power": () => ({ managed: true }),
  });
  return { server, state };
}

const card = async (name: string) => {
  const list = await screen.findByRole("list", { name: "Integrations" });
  const item = within(list).getAllByRole("listitem").find((entry) => within(entry).queryByRole("heading", { name }) !== null);
  if (item === undefined) throw new Error(`No card named ${name}`);
  return item;
};

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

async function pressUninstall(name: string) {
  const user = setup();
  await user.click(within(await card(name)).getByRole("button", { name: `Uninstall ${name}` }));
  const dialog = await screen.findByRole("dialog", { name: `Uninstall ${name}?` });
  return { user, dialog };
}

describe("Uninstall from the Integrations page (spec scenarios)", () => {
  it("Uninstall Chroma: the dialog lists the Chroma packages, then the card shows Removed, restart to apply", async () => {
    const { server, state } = uninstallServer();
    startApp("#/integrations", server);
    const { user, dialog } = await pressUninstall("Chroma vector store");
    const removes = within(dialog).getByRole("list", { name: "Packages to remove" });
    expect(removes).toHaveTextContent("chromadb");
    expect(removes).toHaveTextContent("llama-index-vector-stores-chroma");
    expect(within(dialog).queryByRole("list", { name: "Packages to keep" })).toBeNull();
    expect(dialog).toHaveTextContent("Packages that only these pulled in stay until you reinstall OMRS without this extra.");
    await user.click(within(dialog).getByRole("button", { name: "Uninstall" }));

    await waitFor(() => expect(server.exact("POST", "/v1/integrations/chroma/uninstall")).toHaveLength(1));
    const chroma = await card("Chroma vector store");
    expect(await within(chroma).findByRole("status")).toHaveTextContent("Uninstalling chroma.");

    state.install = SUCCEEDED;
    state.catalogue = [{ ...CHROMA, availability: "restart-needed", uninstallable: false, uninstall_reason: "not-installed", removes: [] }, AZURE, MAGIKA, PDF_INSPECTOR];
    await advance(1100);
    await waitFor(() => expect(within(chroma).getByText("Removed, restart to apply", { selector: "[data-slot=badge]" })).toBeInTheDocument());
    expect(within(chroma).queryByText("Installed, restart to use")).toBeNull();
    expect(within(chroma).queryByText("Restart the server to use it.")).toBeNull();
    await user.click(within(chroma).getByRole("button", { name: "Restart" }));
    expect(await screen.findByRole("dialog", { name: "Restart to apply?" })).toHaveTextContent("Chroma vector store applies after a restart.");
  });

  it("In use: the Chroma card names vector_store and has no Uninstall", async () => {
    const inUse = { ...CHROMA, uninstallable: false, uninstall_reason: "in-use" as const, uninstall_setting: "vector_store" };
    const { server } = uninstallServer({ catalogue: [inUse, AZURE] });
    startApp("#/integrations", server);
    const chroma = await card("Chroma vector store");
    expect(chroma).toHaveTextContent("vector_store uses this extra. Change that setting before you uninstall it.");
    expect(within(chroma).getByText("vector_store").tagName).toBe("CODE");
    expect(within(chroma).queryByRole("button", { name: /^Uninstall/ })).toBeNull();
  });

  it("Base entry: Magika and pdf-inspector have no Uninstall, while Chroma has one", async () => {
    const { server } = uninstallServer();
    startApp("#/integrations", server);
    expect(within(await card("Chroma vector store")).getByRole("button", { name: "Uninstall Chroma vector store" })).toBeInTheDocument();
    expect(within(await card("Magika file detection")).queryByRole("button", { name: /^Uninstall/ })).toBeNull();
    expect(within(await card("PDF reader: pdf-inspector")).queryByRole("button", { name: /^Uninstall/ })).toBeNull();
  });

  it("Extra in the receipt: the Hybrid card shows Uninstall and the lasting command without hybrid", async () => {
    const lasting = `uv tool install --reinstall "omrs[web] @ ${SOURCE}"`;
    const hybrid = installed("hybrid", "Hybrid search", { removes: ["rank-bm25"], lasting_uninstall_command: lasting });
    const { server } = uninstallServer({ catalogue: [hybrid, CHROMA] });
    startApp("#/integrations", server);
    const card_ = await card("Hybrid search");
    expect(within(card_).getByRole("button", { name: "Uninstall Hybrid search" })).toBeInTheDocument();
    expect(within(card_).getByText(lasting)).toBeInTheDocument();
    expect(within(card_).getByRole("button", { name: "Copy reinstall command without Hybrid search" })).toBeInTheDocument();
    expect(card_).toHaveTextContent(/so a later reinstall does not add it back/);
    // Chroma is not in the receipt, so it has no lasting command.
    expect(within(await card("Chroma vector store")).queryByRole("button", { name: /^Copy reinstall command/ })).toBeNull();
  });
});

describe("Uninstall details", () => {
  it("never shows Uninstall on a base entry, even when the catalogue calls it uninstallable", async () => {
    const { server } = uninstallServer({ catalogue: [{ ...PDF_INSPECTOR, uninstallable: true, uninstall_reason: null }, CHROMA] });
    startApp("#/integrations", server);
    await card("Chroma vector store");
    expect(within(await card("PDF reader: pdf-inspector")).queryByRole("button", { name: /^Uninstall/ })).toBeNull();
  });

  it("lists the kept packages in their own block", async () => {
    const { server } = uninstallServer({ catalogue: [{ ...CHROMA, keeps: ["numpy"] }] });
    startApp("#/integrations", server);
    const { dialog } = await pressUninstall("Chroma vector store");
    const keeps = within(dialog).getByRole("list", { name: "Packages to keep" });
    expect(keeps).toHaveTextContent("numpy");
    expect(dialog).toHaveTextContent(/keeps these packages, because something else needs them/);
  });

  it("calls nothing when the dialog is cancelled", async () => {
    const { server } = uninstallServer();
    startApp("#/integrations", server);
    const { user, dialog } = await pressUninstall("Chroma vector store");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await advance(2000);
    expect(posts(server)).toHaveLength(0);
  });

  it("shows Uninstalling, not Installing, while an uninstall runs", async () => {
    const { server } = uninstallServer({ install: RUNNING });
    startApp("#/integrations", server);
    const chroma = await card("Chroma vector store");
    expect(await within(chroma).findByRole("status")).toHaveTextContent("Uninstalling chroma.");
    expect(chroma).not.toHaveTextContent(/Installing/);
  });

  it("disables every Install and Uninstall button while an uninstall runs", async () => {
    const hybrid = installed("hybrid", "Hybrid search");
    const { server } = uninstallServer({ install: RUNNING, catalogue: [CHROMA, AZURE, hybrid] });
    startApp("#/integrations", server);
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Integrations" })).getByRole("button", { name: "Install Azure Document Intelligence" })).toBeDisabled());
    expect(within(await card("Hybrid search")).getByRole("button", { name: "Uninstall Hybrid search" })).toBeDisabled();
  });

  it("shows progress and disables Install while the uninstall start request is in flight", async () => {
    const { server } = uninstallServer({ post: () => new Promise(() => undefined) });
    startApp("#/integrations", server);
    const { user, dialog } = await pressUninstall("Chroma vector store");
    await user.click(within(dialog).getByRole("button", { name: "Uninstall" }));
    expect(await within(await card("Chroma vector store")).findByRole("status")).toHaveTextContent("Uninstalling chroma.");
    expect(within(await card("Azure Document Intelligence")).getByRole("button", { name: "Install Azure Document Intelligence" })).toBeDisabled();
  });

  it("shows a failed uninstall with its output and no install Retry", async () => {
    const { server } = uninstallServer({ install: FAILED });
    startApp("#/integrations", server);
    const chroma = await card("Chroma vector store");
    const alert = await within(chroma).findByRole("alert");
    expect(alert).toHaveTextContent("The uninstall failed. The last output lines are below.");
    expect(alert).not.toHaveTextContent("The install failed");
    expect(within(chroma).getByLabelText("Uninstall output for Chroma vector store")).toHaveTextContent("error: cannot remove chromadb");
    expect(within(chroma).queryByRole("button", { name: /^Install/ })).toBeNull();
    await setup().click(within(alert).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(server.exact("POST", "/v1/integrations/chroma/uninstall")).toHaveLength(1));
    expect(server.find("POST", "/v1/integrations/chroma/install")).toHaveLength(0);
  });

  it("says the packages left behind clash when the check after the uninstall fails, with no Retry", async () => {
    const { server } = uninstallServer({ install: { ...FAILED, reason: "check-failed" } });
    startApp("#/integrations", server);
    const alert = await within(await card("Chroma vector store")).findByRole("alert");
    expect(alert).toHaveTextContent(/packages left behind clash/);
    expect(within(alert).queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("says nothing can be removed when other packages need every package of the extra, with no Uninstall", async () => {
    const torch = installed("torch", "PyTorch reranker", {
      uninstallable: false,
      uninstall_reason: "nothing-to-remove",
      removes: [],
      keeps: ["sentence-transformers", "transformers"],
    });
    const { server } = uninstallServer({ catalogue: [torch, CHROMA] });
    startApp("#/integrations", server);
    const card_ = await card("PyTorch reranker");
    expect(card_).toHaveTextContent("Other installed packages need every package of this extra (sentence-transformers, transformers), so the app cannot remove it.");
    expect(within(card_).queryByRole("button", { name: /^Uninstall/ })).toBeNull();
  });

  it("explains a nothing-to-remove refusal from the server", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { server } = uninstallServer({
      post: () => json({ status: "error", message: "Refused <raw> detail", reason: "nothing-to-remove" }, 409),
    });
    startApp("#/integrations", server);
    const { user, dialog } = await pressUninstall("Chroma vector store");
    await user.click(within(dialog).getByRole("button", { name: "Uninstall" }));
    const alert = await within(await card("Chroma vector store")).findByRole("alert");
    expect(alert).toHaveTextContent("Other installed packages need every package of this extra, so the app cannot remove it.");
    expect(within(alert).getByRole("button", { name: "Check again" })).toBeInTheDocument();
  });

  it("names the setting when the server refuses the uninstall with in-use", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { server } = uninstallServer({
      post: () => json({ status: "error", message: "Refused <raw> detail", reason: "in-use", setting: "vector_store" }, 409),
    });
    startApp("#/integrations", server);
    const { user, dialog } = await pressUninstall("Chroma vector store");
    await user.click(within(dialog).getByRole("button", { name: "Uninstall" }));
    const alert = await within(await card("Chroma vector store")).findByRole("alert");
    expect(alert).toHaveTextContent("vector_store uses this extra. Change that setting before you uninstall it.");
    expect(alert).not.toHaveTextContent("Refused");
    expect(within(alert).getByRole("button", { name: "Check again" })).toBeInTheDocument();
  });

  it("says another job is running when the server refuses the uninstall with install-running", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { server } = uninstallServer({ post: () => json({ status: "error", message: "Refused", reason: "install-running" }, 409) });
    startApp("#/integrations", server);
    const { user, dialog } = await pressUninstall("Chroma vector store");
    await user.click(within(dialog).getByRole("button", { name: "Uninstall" }));
    const alert = await within(await card("Chroma vector store")).findByRole("alert");
    expect(alert).toHaveTextContent("Another install or uninstall is running. Wait for it to finish, then try again.");
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(server.exact("POST", "/v1/integrations/chroma/uninstall")).toHaveLength(2));
  });

  it("trusts the server after a restart: a removed entry the catalogue calls not installed shows Install again", async () => {
    const { server } = uninstallServer({ install: SUCCEEDED, catalogue: [{ ...AZURE, ...{ id: "chroma", name: "Chroma vector store", extra: "chroma" } }] });
    startApp("#/integrations", server);
    const chroma = await card("Chroma vector store");
    await waitFor(() => expect(server.find("GET", "/v1/integrations/install")).toHaveLength(1));
    expect(within(chroma).getByText("Not installed", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(within(chroma).queryByText("Removed, restart to apply")).toBeNull();
    expect(within(chroma).getByRole("button", { name: "Install Chroma vector store" })).toBeInTheDocument();
  });
});
