import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Integration } from "../api/integrations";
import type { ModelRuntime } from "../api/modelRuntimes";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { GIB, ROUTER_TITLE, RUNTIMES, runtimeItem, SESSION_READ_ONLY, SESSION_WITH_MANAGE } from "./test/modelRuntimeFixtures";

const EXTERNAL_OCR = "External server. Model files are not checked.";
const NO_CLIENT = "Running, no OMRS process uses it";

const ENTRY: Integration = {
  id: "llamacpp",
  name: "llama.cpp provider",
  purpose: "Purpose of llamacpp.",
  extra: "llamacpp",
  install_command: "uv sync --extra llamacpp",
  pip_command: null,
  availability: "available",
  installable: false,
  install_reason: "not-installable-here",
  packages: [],
  install_caution: null,
  base: true,
  uninstallable: false,
  uninstall_reason: "not-uninstallable-here",
  uninstall_setting: null,
  removes: [],
  keeps: [],
  lasting_uninstall_command: null,
  pending_restart: null,
  uninstall_profile: null,
};

function serve(runtimes: ModelRuntime[] = RUNTIMES, handlers: Parameters<typeof documentsServer>[0] = {}) {
  return documentsServer({
    "GET /v1/integrations": () => ({ status: "ok", install_type: "checkout", integrations: [ENTRY], tools: [] }),
    "GET /v1/runtimes": () => ({ runtimes }),
    "GET /v1/session": () => SESSION_WITH_MANAGE,
    ...handlers,
  });
}

const section = async () => screen.findByRole("region", { name: "Model runtimes" });
const row = async (title: string) => {
  const items = await within(await section()).findAllByRole("listitem");
  const found = items.find((entry) => within(entry).queryByRole("heading", { name: title }) !== null);
  if (found === undefined) throw new Error(`No row ${title}`);
  return found;
};

afterEach(() => vi.restoreAllMocks());

describe("Model runtimes section", () => {
  it("has a chip on the Integrations page that opens the section", async () => {
    const user = userEvent.setup();
    startApp("#/integrations", serve());
    await user.click(await screen.findByRole("button", { name: "Model runtimes" }));
    expect(await section()).toBeInTheDocument();
    expect(window.location.hash).toBe("#/integrations/model-runtimes");
  });

  it("tells where the router is set and where OCR is set, with a link to Providers", async () => {
    startApp("#/integrations/model-runtimes", serve());
    const note = within(await section())
      .getAllByRole("note")
      .find((element) => /Router panel/i.test(element.textContent ?? ""));
    if (note === undefined) throw new Error("No Providers note");
    expect(note).toHaveTextContent(
      "Who runs llama.cpp, its address and its models are set in the Router panel of the llama.cpp card in Settings › Providers, where you can also start OMRS's own router. The OCR runtimes are set in the environment, .env or omrs.jsonc.",
    );
    expect(within(note).getByRole("link", { name: "Settings › Providers" })).toHaveAttribute("href", "#/settings/providers");
    expect(note).toHaveClass("border-status-info");
  });

  it("shows one row for the router and one for each OCR runtime, with role, mode, status and address", async () => {
    startApp("#/integrations/model-runtimes", serve());
    const router = await row(ROUTER_TITLE);
    expect(within(router).getByText("Managed", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(within(router).getByText("Running", { selector: "[data-slot=badge]" })).toHaveClass("text-status-success-label");
    expect(router).toHaveTextContent("127.0.0.1:8080");
    expect(router).toHaveTextContent("Serves embeddings, classification and Chat for OMRS.");
    const ocr = await row("OCR: dots-mocr-llamacpp");
    expect(within(ocr).getByText("Failed", { selector: "[data-slot=badge]" })).toHaveClass("text-status-error-label");
    const external = await row("OCR: paddleocr-vl-llamacpp");
    expect(within(external).getByText("External", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(await within(await section()).findAllByRole("listitem")).toHaveLength(3);
  });

  it("shows memory and what uses the runtime", async () => {
    startApp("#/integrations/model-runtimes", serve());
    const router = await row(ROUTER_TITLE);
    expect(router).toHaveTextContent("6.0 GiB");
    expect(within(router).getByText("embed_provider")).toBeInTheDocument();
  });

  it("Failed OCR runtime: shows Failed and one reason line that names the changed file", async () => {
    startApp("#/integrations/model-runtimes", serve());
    const ocr = await row("OCR: dots-mocr-llamacpp");
    expect(ocr).toHaveTextContent("dots-mocr-Q8_0.gguf");
    expect(within(ocr).getAllByText(/dots-mocr-Q8_0\.gguf/)).toHaveLength(1);
  });

  it("External OCR runtime: shows External, says model files are not checked, and shows no Stop button", async () => {
    startApp("#/integrations/model-runtimes", serve());
    const external = await row("OCR: paddleocr-vl-llamacpp");
    expect(within(external).getByText("External", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(external).toHaveTextContent(EXTERNAL_OCR);
    expect(within(external).queryByRole("button", { name: /Stop/ })).toBeNull();
  });

  it("does not say the model files are not checked for a managed runtime", async () => {
    startApp("#/integrations/model-runtimes", serve());
    expect(await row("OCR: dots-mocr-llamacpp")).not.toHaveTextContent(EXTERNAL_OCR);
    expect(await row(ROUTER_TITLE)).not.toHaveTextContent(EXTERNAL_OCR);
  });

  it("External Chat runtime: the router row shows External and no Stop button", async () => {
    startApp("#/integrations/model-runtimes", serve([runtimeItem("router", { mode: "external", state: "running", address: "127.0.0.1:9931" })]));
    const router = await row(ROUTER_TITLE);
    expect(within(router).getByText("External", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(router).not.toHaveTextContent(EXTERNAL_OCR);
    expect(within(router).queryByRole("button", { name: /Stop/ })).toBeNull();
  });

  it("Router models under the row: lists the loaded embedding model and the unloaded Chat model with roles and states", async () => {
    const models = [
      { model: "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0", roles: ["embeddings" as const], state: "loaded" as const, reason: null, memory_bytes: 4 * GIB },
      { model: "Qwen/Qwen3-1.7B-GGUF:Q8_0", roles: ["chat" as const], state: "unloaded" as const, reason: null, memory_bytes: null },
    ];
    startApp("#/integrations/model-runtimes", serve([runtimeItem("router", { state: "running", models })]));
    const group = within(await row(ROUTER_TITLE)).getByRole("group", { name: "Models" });
    const embedding = within(group).getByText("Qwen/Qwen3-Embedding-4B-GGUF:Q8_0").parentElement as HTMLElement;
    expect(embedding).toHaveTextContent("Embeddings");
    expect(embedding).toHaveTextContent("Loaded");
    expect(embedding).toHaveTextContent("4.0 GiB");
    const chat = within(group).getByText("Qwen/Qwen3-1.7B-GGUF:Q8_0").parentElement as HTMLElement;
    expect(chat).toHaveTextContent("Chat");
    expect(chat).toHaveTextContent("Unloaded");
  });

  it("shows no model lines under an OCR row", async () => {
    startApp("#/integrations/model-runtimes", serve());
    expect(within(await row("OCR: dots-mocr-llamacpp")).queryByRole("group", { name: "Models" })).toBeNull();
  });

  it("says a running managed runtime with no client has no OMRS process using it", async () => {
    startApp("#/integrations/model-runtimes", serve());
    expect(await row(ROUTER_TITLE)).toHaveTextContent(NO_CLIENT);
    expect(await row("OCR: dots-mocr-llamacpp")).not.toHaveTextContent(NO_CLIENT);
    expect(await row("OCR: paddleocr-vl-llamacpp")).not.toHaveTextContent(NO_CLIENT);
  });

  it("Phone width: rows, model lines, reason lines and Stop wrap long text and stack", async () => {
    startApp("#/integrations/model-runtimes", serve());
    const router = await row(ROUTER_TITLE);
    expect(router.className).toContain("grid-cols-1");
    expect(within(router).getByText("Qwen/Qwen3-Embedding-4B-GGUF:Q8_0").className).toContain("[overflow-wrap:anywhere]");
    expect(within(router).getByRole("button", { name: `Stop ${ROUTER_TITLE}` })).toBeInTheDocument();
    expect((await row("OCR: dots-mocr-llamacpp")).querySelector("p.\\[overflow-wrap\\:anywhere\\]")).not.toBeNull();
  });
});

describe("Stop", () => {
  it("stops a managed running runtime that no other process uses, without asking", async () => {
    const user = userEvent.setup();
    const server = serve(RUNTIMES, {
      "POST /v1/runtimes/router/stop": () => ({ ...RUNTIMES[0], state: "stopped", memory_bytes: null }),
    });
    startApp("#/integrations/model-runtimes", server);
    await user.click(await within(await row(ROUTER_TITLE)).findByRole("button", { name: `Stop ${ROUTER_TITLE}` }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(server.exact("POST", "/v1/runtimes/router/stop")).toHaveLength(1));
    expect(await within(await row(ROUTER_TITLE)).findByText("Stopped", { selector: "[data-slot=badge]" })).toBeInTheDocument();
  });

  it("offers Stop on a managed runtime that is starting", async () => {
    startApp("#/integrations/model-runtimes", serve([runtimeItem("router", { state: "starting" })]));
    expect(await within(await row(ROUTER_TITLE)).findByRole("button", { name: `Stop ${ROUTER_TITLE}` })).toBeInTheDocument();
  });

  it("offers no Stop on a managed runtime that is stopped or failed", async () => {
    startApp("#/integrations/model-runtimes", serve());
    const failed = await row("OCR: dots-mocr-llamacpp");
    expect(within(failed).queryByRole("button", { name: /Stop/ })).toBeNull();
  });

  it("offers no Stop on a managed runtime that is stopped", async () => {
    startApp("#/integrations/model-runtimes", serve([runtimeItem("router", { state: "stopped" })]));
    const stopped = await row(ROUTER_TITLE);
    expect(within(stopped).getByText("Stopped", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(within(stopped).queryByRole("button", { name: /Stop/ })).toBeNull();
  });

  it("offers no Stop to a session without manage", async () => {
    const server = serve(RUNTIMES, { "GET /v1/session": () => SESSION_READ_ONLY });
    startApp("#/integrations/model-runtimes", server);
    await row(ROUTER_TITLE);
    await waitFor(() => expect(server.exact("GET", "/v1/session")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("button", { name: /^Stop/ })).toBeNull());
    expect(await within(await section()).findAllByRole("listitem")).toHaveLength(3);
  });

  it("offers no Stop until the session read has finished", async () => {
    startApp("#/integrations/model-runtimes", serve(RUNTIMES, { "GET /v1/session": () => json({ status: "error", message: "no" }, 500) }));
    await row(ROUTER_TITLE);
    expect(screen.queryByRole("button", { name: /^Stop/ })).toBeNull();
  });

  it("asks first when another OMRS process uses the router, says what fails, and sends nothing until the user confirms", async () => {
    const user = userEvent.setup();
    const some = [{ ...RUNTIMES[0]!, clients: "some" as const, other_clients: "some" as const }, ...RUNTIMES.slice(1)];
    const server = serve(some, {
      "POST /v1/runtimes/router/stop": () => ({ ...some[0], state: "stopped", clients: "none", other_clients: "none" }),
    });
    startApp("#/integrations/model-runtimes", server);
    await user.click(await within(await row(ROUTER_TITLE)).findByRole("button", { name: `Stop ${ROUTER_TITLE}` }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Another OMRS process uses this runtime");
    expect(dialog).toHaveTextContent("Requests in progress fail");
    expect(dialog).toHaveTextContent("Requests for the router's models fail until it starts again.");
    expect(dialog).not.toHaveTextContent("OCR");
    expect(dialog).not.toHaveTextContent("fallback");
    expect(server.exact("POST", "/v1/runtimes/router/stop")).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "Stop runtime" }));
    await waitFor(() => expect(server.exact("POST", "/v1/runtimes/router/stop")).toHaveLength(1));
    expect(await within(await row(ROUTER_TITLE)).findByText("Stopped", { selector: "[data-slot=badge]" })).toBeInTheDocument();
  });

  it("asks first when another OMRS process uses an OCR runtime, and says OCR uses the fallback engine", async () => {
    const user = userEvent.setup();
    const ocr = runtimeItem("ocr-dots-mocr-llamacpp", { state: "running", clients: "some", other_clients: "some", used_by: ["ocr_engine_primary"] });
    startApp("#/integrations/model-runtimes", serve([ocr]));
    await user.click(await within(await row("OCR: dots-mocr-llamacpp")).findByRole("button", { name: "Stop OCR: dots-mocr-llamacpp" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Another OMRS process uses this runtime");
    expect(dialog).toHaveTextContent("OCR uses the fallback engine");
    expect(dialog).not.toHaveTextContent("router's models");
  });

  it("stops without asking when only this process holds the router", async () => {
    const user = userEvent.setup();
    const own = [{ ...RUNTIMES[0]!, clients: "some" as const, other_clients: "none" as const }, ...RUNTIMES.slice(1)];
    const server = serve(own, { "POST /v1/runtimes/router/stop": () => ({ ...own[0], state: "stopped", clients: "none" }) });
    startApp("#/integrations/model-runtimes", server);
    await user.click(await within(await row(ROUTER_TITLE)).findByRole("button", { name: `Stop ${ROUTER_TITLE}` }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(server.exact("POST", "/v1/runtimes/router/stop")).toHaveLength(1));
  });

  it("sends nothing when the user cancels the confirmation", async () => {
    const user = userEvent.setup();
    const some = [{ ...RUNTIMES[0]!, clients: "some" as const, other_clients: "some" as const }, ...RUNTIMES.slice(1)];
    const server = serve(some);
    startApp("#/integrations/model-runtimes", server);
    await user.click(await within(await row(ROUTER_TITLE)).findByRole("button", { name: `Stop ${ROUTER_TITLE}` }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(server.exact("POST", "/v1/runtimes/router/stop")).toHaveLength(0);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("says the runtime is external when the server refuses with external-runtime", async () => {
    const user = userEvent.setup();
    startApp(
      "#/integrations/model-runtimes",
      serve(RUNTIMES, { "POST /v1/runtimes/router/stop": () => json({ status: "error", message: "raw server text", reason: "external-runtime" }, 409) }),
    );
    await user.click(await within(await row(ROUTER_TITLE)).findByRole("button", { name: `Stop ${ROUTER_TITLE}` }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This runtime is an external server. OMRS does not stop it.");
    expect(alert).not.toHaveTextContent("raw server text");
  });

  it("shows one friendly line for any other failure", async () => {
    const user = userEvent.setup();
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    startApp("#/integrations/model-runtimes", serve(RUNTIMES, { "POST /v1/runtimes/router/stop": () => json({ status: "error", message: "Traceback boom" }, 500) }));
    await user.click(await within(await row(ROUTER_TITLE)).findByRole("button", { name: `Stop ${ROUTER_TITLE}` }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(alert).not.toHaveTextContent("Traceback");
  });
});

describe("Loading and failure", () => {
  it("says when the list fails to load, with a retry action", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    startApp("#/integrations/model-runtimes", serve(RUNTIMES, { "GET /v1/runtimes": () => json({ status: "error", message: "x" }, 500) }));
    expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("says when no runtime is in force", async () => {
    startApp("#/integrations/model-runtimes", serve([]));
    expect(await screen.findByText("No local model runtime is in force.")).toBeInTheDocument();
  });
});
