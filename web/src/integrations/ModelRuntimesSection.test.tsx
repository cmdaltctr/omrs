import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Integration } from "../api/integrations";
import type { ModelRuntime } from "../api/modelRuntimes";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { RUNTIMES, runtimeItem, SESSION_READ_ONLY, SESSION_WITH_MANAGE } from "./test/modelRuntimeFixtures";

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

  it("shows one row for each runtime with its role, mode, status and address", async () => {
    startApp("#/integrations/model-runtimes", serve());
    const chat = await row("Chat");
    expect(within(chat).getByText("Managed", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(within(chat).getByText("Running", { selector: "[data-slot=badge]" })).toHaveClass("text-status-success-label");
    expect(chat).toHaveTextContent("127.0.0.1:8081");
    const embeddings = await row("Embeddings");
    expect(within(embeddings).getByText("Managed", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    const ocr = await row("OCR: dots-mocr-llamacpp");
    expect(within(ocr).getByText("Failed", { selector: "[data-slot=badge]" })).toHaveClass("text-status-error-label");
    const external = await row("OCR: paddleocr-vl-llamacpp");
    expect(within(external).getByText("External", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(await within(await section()).findAllByRole("listitem")).toHaveLength(4);
  });

  it("shows memory and what uses the runtime", async () => {
    startApp("#/integrations/model-runtimes", serve());
    const chat = await row("Chat");
    expect(chat).toHaveTextContent("6.0 GiB");
    expect(within(chat).getByText("llamacpp_chat_server")).toBeInTheDocument();
    expect(await row("Embeddings")).toHaveTextContent("512.0 MiB");
  });

  it("shows one reason line for a failed runtime and names the changed file", async () => {
    startApp("#/integrations/model-runtimes", serve());
    const ocr = await row("OCR: dots-mocr-llamacpp");
    expect(ocr).toHaveTextContent("dots-mocr-Q8_0.gguf");
    expect(within(ocr).getAllByText(/dots-mocr-Q8_0\.gguf/)).toHaveLength(1);
  });

  it("says an external OCR server's model files are not checked, and shows no Stop button", async () => {
    startApp("#/integrations/model-runtimes", serve());
    const external = await row("OCR: paddleocr-vl-llamacpp");
    expect(external).toHaveTextContent(EXTERNAL_OCR);
    expect(within(external).queryByRole("button", { name: /Stop/ })).toBeNull();
  });

  it("does not say the model files are not checked for a managed runtime", async () => {
    startApp("#/integrations/model-runtimes", serve());
    expect(await row("OCR: dots-mocr-llamacpp")).not.toHaveTextContent(EXTERNAL_OCR);
  });

  it("shows an external Chat runtime without a Stop button", async () => {
    startApp("#/integrations/model-runtimes", serve([runtimeItem("chat", { mode: "external", state: "running", address: "127.0.0.1:9931" })]));
    const chat = await row("Chat");
    expect(within(chat).getByText("External", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(chat).not.toHaveTextContent(EXTERNAL_OCR);
    expect(within(chat).queryByRole("button", { name: /Stop/ })).toBeNull();
  });

  it("says a running managed runtime with no client has no OMRS process using it", async () => {
    startApp("#/integrations/model-runtimes", serve());
    expect(await row("Chat")).toHaveTextContent(NO_CLIENT);
    expect(await row("Embeddings")).not.toHaveTextContent(NO_CLIENT);
    expect(await row("OCR: dots-mocr-llamacpp")).not.toHaveTextContent(NO_CLIENT);
    expect(await row("OCR: paddleocr-vl-llamacpp")).not.toHaveTextContent(NO_CLIENT);
  });
});

describe("Stop", () => {
  it("stops a managed running runtime that no other process uses, without asking", async () => {
    const user = userEvent.setup();
    const server = serve(RUNTIMES, {
      "POST /v1/runtimes/chat/stop": () => ({ ...RUNTIMES[0], state: "stopped", memory_bytes: null }),
    });
    startApp("#/integrations/model-runtimes", server);
    await user.click(await within(await row("Chat")).findByRole("button", { name: "Stop Chat" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(server.exact("POST", "/v1/runtimes/chat/stop")).toHaveLength(1));
    expect(await within(await row("Chat")).findByText("Stopped", { selector: "[data-slot=badge]" })).toBeInTheDocument();
  });

  it("offers Stop on a managed runtime that is starting", async () => {
    startApp("#/integrations/model-runtimes", serve([runtimeItem("chat", { state: "starting" })]));
    expect(await within(await row("Chat")).findByRole("button", { name: "Stop Chat" })).toBeInTheDocument();
  });

  it("offers no Stop on a managed runtime that is stopped or failed", async () => {
    startApp("#/integrations/model-runtimes", serve());
    const failed = await row("OCR: dots-mocr-llamacpp");
    expect(within(failed).queryByRole("button", { name: /Stop/ })).toBeNull();
  });

  it("offers no Stop on a managed runtime that is stopped", async () => {
    startApp("#/integrations/model-runtimes", serve([runtimeItem("embeddings", { state: "stopped" })]));
    const stopped = await row("Embeddings");
    expect(within(stopped).getByText("Stopped", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(within(stopped).queryByRole("button", { name: /Stop/ })).toBeNull();
  });

  it("offers no Stop to a session without manage", async () => {
    const server = serve(RUNTIMES, { "GET /v1/session": () => SESSION_READ_ONLY });
    startApp("#/integrations/model-runtimes", server);
    await row("Chat");
    await waitFor(() => expect(server.exact("GET", "/v1/session")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("button", { name: /^Stop/ })).toBeNull());
    expect(await within(await section()).findAllByRole("listitem")).toHaveLength(4);
  });

  it("offers no Stop until the session read has finished", async () => {
    startApp("#/integrations/model-runtimes", serve(RUNTIMES, { "GET /v1/session": () => json({ status: "error", message: "no" }, 500) }));
    await row("Chat");
    expect(screen.queryByRole("button", { name: /^Stop/ })).toBeNull();
  });

  it("asks first when another OMRS process uses the runtime, and sends nothing until the user confirms", async () => {
    const user = userEvent.setup();
    const server = serve(RUNTIMES, {
      "POST /v1/runtimes/embeddings/stop": () => ({ ...RUNTIMES[1], state: "stopped", clients: "none" }),
    });
    startApp("#/integrations/model-runtimes", server);
    await user.click(await within(await row("Embeddings")).findByRole("button", { name: "Stop Embeddings" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Another OMRS process uses this runtime");
    expect(dialog).toHaveTextContent("Requests in progress fail");
    expect(dialog).toHaveTextContent("OCR uses the fallback engine");
    expect(server.exact("POST", "/v1/runtimes/embeddings/stop")).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "Stop runtime" }));
    await waitFor(() => expect(server.exact("POST", "/v1/runtimes/embeddings/stop")).toHaveLength(1));
    expect(await within(await row("Embeddings")).findByText("Stopped", { selector: "[data-slot=badge]" })).toBeInTheDocument();
  });

  it("sends nothing when the user cancels the confirmation", async () => {
    const user = userEvent.setup();
    const server = serve();
    startApp("#/integrations/model-runtimes", server);
    await user.click(await within(await row("Embeddings")).findByRole("button", { name: "Stop Embeddings" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(server.exact("POST", "/v1/runtimes/embeddings/stop")).toHaveLength(0);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("says the runtime is external when the server refuses with external-runtime", async () => {
    const user = userEvent.setup();
    startApp(
      "#/integrations/model-runtimes",
      serve(RUNTIMES, { "POST /v1/runtimes/chat/stop": () => json({ status: "error", message: "raw server text", reason: "external-runtime" }, 409) }),
    );
    await user.click(await within(await row("Chat")).findByRole("button", { name: "Stop Chat" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This runtime is an external server. OMRS does not stop it.");
    expect(alert).not.toHaveTextContent("raw server text");
  });

  it("shows one friendly line for any other failure", async () => {
    const user = userEvent.setup();
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    startApp("#/integrations/model-runtimes", serve(RUNTIMES, { "POST /v1/runtimes/chat/stop": () => json({ status: "error", message: "Traceback boom" }, 500) }));
    await user.click(await within(await row("Chat")).findByRole("button", { name: "Stop Chat" }));
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
