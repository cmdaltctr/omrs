import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Connection, ConnectionList, ProviderField } from "../api/settings";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { CONFIG_DIR, CONNECTIONS, LLAMACPP, OLLAMA, OPENROUTER, SERVER_MANAGED, settingsServer, urlField } from "./test/fixtures";

const KEY = "sk-or-secret-1234567890-wxyz"; // gitleaks:allow

function list(...connections: Connection[]): ConnectionList {
  return { ...CONNECTIONS, connections };
}

function openrouter(change: Partial<ProviderField>): Connection {
  return { ...OPENROUTER, fields: [{ ...OPENROUTER.fields[0]!, ...change }] };
}

const NO_KEY: Partial<ProviderField> = { set: false, last4: null, source: "none" };

/** OMRS runs the Chat server and its program path is set, so nothing needs attention. */
const SERVER_READY = { ...SERVER_MANAGED, saved: { ...SERVER_MANAGED.saved, binary: { ...SERVER_MANAGED.saved.binary, value: "/opt/llama/llama-server" } } };

const FIVE = () =>
  list(
    OLLAMA,
    LLAMACPP,
    OPENROUTER,
    { ...OPENROUTER, provider: "openai_compatible", display_name: "OpenAI-compatible" },
    { ...OPENROUTER, provider: "anthropic", display_name: "Anthropic" },
  );

async function openProviders(handlers = {}) {
  const server = settingsServer(handlers);
  startApp("#/settings/providers", server);
  await screen.findByRole("heading", { level: 3, name: "Ollama" });
  return { server, user: userEvent.setup() };
}

function card(name: string) {
  return screen.getByRole("region", { name });
}

describe("Providers", () => {
  it("shows each setting of a provider card as a compact row, with no mini card", async () => {
    await openProviders({ "GET /v1/llamacpp/server": () => SERVER_READY });
    const row = (element: HTMLElement) => element.closest("[data-slot='setting-row']");
    const ollama = card("Ollama");
    expect(row(within(ollama).getByText("Address"))).not.toBeNull();
    expect(row(within(ollama).getByText("qwen3"))).not.toBeNull();
    expect(row(within(ollama).getByText("Address"))).not.toBe(row(within(ollama).getByText("qwen3")));
    expect(row(within(card("OpenRouter")).getByText(/Key set/))).not.toBeNull();
    const server = await within(card("llama.cpp")).findByRole("heading", { level: 5, name: "Local server" });
    expect(server.closest("details")!.querySelectorAll("[data-slot='setting-row']").length).toBeGreaterThan(1);
    for (const region of screen.getAllByRole("region")) expect(region.querySelector("[data-slot='card-inset']")).toBeNull();
  });

  it("lists a card per server entry with Local and Cloud badges in text and the roles", async () => {
    await openProviders();
    expect(screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)).toEqual(["Ollama", "llama.cpp", "OpenRouter"]);
    expect(within(card("Ollama")).getByText("Local")).toHaveAttribute("data-slot", "badge");
    expect(within(card("OpenRouter")).getByText("Cloud")).toHaveAttribute("data-slot", "badge");
    expect(within(card("Ollama")).getByText("Answers")).toBeInTheDocument();
    expect(within(card("Ollama")).queryByText("Embeddings")).toBeNull();
    expect(within(card("llama.cpp")).getAllByText("Embeddings").some((element) => element.getAttribute("data-slot") === "badge")).toBe(true);
  });

  it("puts local providers full width above a grid of cloud cards", async () => {
    await openProviders({ "GET /v1/connections": FIVE });
    const local = screen.getByRole("group", { name: "On this machine" });
    const cloud = screen.getByRole("group", { name: "Cloud" });
    expect(within(local).getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)).toEqual(["Ollama", "llama.cpp"]);
    const grid = cloud.querySelector("[data-slot='cloud-grid']") as HTMLElement;
    expect(within(grid).getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)).toEqual(["OpenRouter", "OpenAI-compatible", "Anthropic"]);
    expect(local.compareDocumentPosition(cloud) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByTestId("masonry")).toBeNull();
  });

  it("splits a local card into two columns: addresses and models left, Chat and Get a model right", async () => {
    await openProviders({ "GET /v1/llamacpp/server": () => SERVER_READY });
    const llamacpp = card("llama.cpp");
    const [left, right] = Array.from(llamacpp.querySelector("[data-slot='provider-columns']")!.children) as HTMLElement[];
    expect(within(left!).getByRole("heading", { level: 4, name: "Embeddings" })).toBeInTheDocument();
    expect(within(left!).getByRole("heading", { level: 4, name: "Classification (metadata)" })).toBeInTheDocument();
    expect(within(right!).getByRole("heading", { level: 4, name: "Chat" })).toBeInTheDocument();
    expect(within(right!).getByRole("heading", { level: 4, name: "Get a model" })).toBeInTheDocument();
    expect(within(llamacpp).getAllByRole("button", { name: "Test" })).toHaveLength(1);
    expect(llamacpp.querySelector("[data-slot='provider-columns'] button[aria-label='Test']")).toBeNull();
    expect(card("OpenRouter").querySelector("[data-slot='provider-columns']")).toBeNull();
  });

  it("starts the Local server and Get a model panels closed, with the server state on the toggle row", async () => {
    const { user } = await openProviders({ "GET /v1/llamacpp/server": () => SERVER_READY });
    const llamacpp = card("llama.cpp");
    const server = (await within(llamacpp).findByRole("heading", { level: 5, name: "Local server" })).closest("details")!;
    const model = within(llamacpp).getByRole("heading", { level: 4, name: "Get a model" }).closest("details")!;
    expect(server.open).toBe(false);
    expect(model.open).toBe(false);
    expect(server.querySelector("summary")).toHaveTextContent("Stopped");
    await user.click(server.querySelector("summary")!);
    expect(server.open).toBe(true);
  });

  it("opens the Local server panel by itself while the program path is missing", async () => {
    await openProviders({ "GET /v1/llamacpp/server": () => SERVER_MANAGED });
    const server = await within(card("llama.cpp")).findByRole("heading", { level: 5, name: "Local server" });
    expect(server.closest("details")!.open).toBe(true);
  });

  it("shows read-only values as read-only and a link to Integrations, not a command, when not installed", async () => {
    await openProviders({
      "GET /v1/connections": () => list(OLLAMA, { ...LLAMACPP, installed: false, install_hint: "uv sync --extra llamacpp" }, OPENROUTER),
    });
    const llamacpp = card("llama.cpp");
    expect(within(llamacpp).getByText("Embedding model")).toBeInTheDocument();
    expect(within(llamacpp).getByText("bge-small")).toBeInTheDocument();
    expect(within(llamacpp).getAllByText("(Read-only)").length).toBeGreaterThan(0);
    expect(within(llamacpp).getByRole("link", { name: "Install llama.cpp from Integrations" })).toHaveAttribute("href", "#/integrations/llamacpp");
    expect(llamacpp).not.toHaveTextContent(/uv sync/);
    expect(within(card("Ollama")).queryByRole("link", { name: /from Integrations/ })).toBeNull();
  });

  it("names the omrs.jsonc path, says saves are written there, and shows no restart banner", async () => {
    await openProviders();
    const section = screen.getByRole("region", { name: "Providers" });
    expect(section).toHaveTextContent("~/.config/omrs/omrs.jsonc");
    expect(section).toHaveTextContent(/saves are written to .*omrs\.jsonc/i);
    expect(section).toHaveTextContent(/apply at once to this web server/i);
    expect(screen.queryByText(/restart to apply/i)).toBeNull();
  });

  it("shows an address with the default word and an Edit button, and no input until Edit", async () => {
    await openProviders();
    const ollama = card("Ollama");
    expect(within(ollama).getByText("http://127.0.0.1:11434")).toBeInTheDocument();
    expect(within(ollama).getByText("default")).toBeInTheDocument();
    expect(within(ollama).queryByRole("textbox", { name: "Address" })).toBeNull();
    expect(within(ollama).getByRole("button", { name: "Edit Address" })).toBeInTheDocument();
  });

  it("shows an environment address as read-only with the variable named", async () => {
    const locked = { ...OLLAMA, fields: [urlField("base_url", "Address", "http://env-host:11434", "env", "Remove OLLAMA_BASE_URL from the environment or .env to edit it here.")] };
    await openProviders({ "GET /v1/connections": () => list(locked, LLAMACPP, OPENROUTER) });
    const ollama = card("Ollama");
    expect(within(ollama).getByText("Set in the environment. Change it there.")).toBeInTheDocument();
    expect(ollama).toHaveTextContent("OLLAMA_BASE_URL");
    expect(within(ollama).getByText("http://env-host:11434")).toBeInTheDocument();
    expect(within(ollama).queryByRole("textbox", { name: "Address" })).toBeNull();
    expect(within(ollama).queryByRole("button", { name: /^Edit/ })).toBeNull();
  });

  it("shows a .env address as read-only with the variable and the .env path", async () => {
    const locked = { ...OLLAMA, fields: [urlField("base_url", "Address", "http://env-host:11434", "dotenv", "Remove OLLAMA_BASE_URL from the environment or .env to edit it here.")] };
    await openProviders({ "GET /v1/connections": () => list(locked, LLAMACPP, OPENROUTER) });
    const ollama = card("Ollama");
    expect(ollama).toHaveTextContent("Set in .env. Change it there.");
    expect(ollama).toHaveTextContent("OLLAMA_BASE_URL");
    expect(ollama).toHaveTextContent(`${CONFIG_DIR}/.env`);
    expect(within(ollama).queryByRole("button", { name: /^Edit/ })).toBeNull();
  });

  it("shows an address from the config file with its words and keeps it editable", async () => {
    await openProviders({
      "GET /v1/connections": () => list({ ...OLLAMA, fields: [urlField("base_url", "Address", "http://cfg-host:11434", "config-file")] }, LLAMACPP, OPENROUTER),
    });
    const ollama = card("Ollama");
    expect(within(ollama).getByText("http://cfg-host:11434")).toBeInTheDocument();
    expect(within(ollama).getByText("Saved in settings (omrs.jsonc)")).toBeInTheDocument();
    expect(within(ollama).getByRole("button", { name: "Edit Address" })).toBeInTheDocument();
  });

  it("opens the input filled with the address, saves it and shows the address and source the server returns", async () => {
    let value = "http://127.0.0.1:11434";
    let source: "default" | "config-file" = "default";
    const { user, server } = await openProviders({
      "GET /v1/connections": () => list({ ...OLLAMA, fields: [urlField("base_url", "Address", value, source)] }, LLAMACPP, OPENROUTER),
      "PUT /v1/connections/ollama": (body: Record<string, unknown>) => {
        value = (body.fields as Record<string, string>).base_url!;
        source = "config-file";
        return { status: "ok", revision: "r2" };
      },
    });
    const ollama = card("Ollama");
    await user.click(within(ollama).getByRole("button", { name: "Edit Address" }));
    const input = within(ollama).getByRole("textbox", { name: "Address" });
    expect(input).toHaveValue("http://127.0.0.1:11434");
    expect(within(ollama).getByRole("button", { name: "Save" })).toBeDisabled();
    await user.clear(input);
    await user.type(input, "http://gpu-box.local:11434");
    await user.click(within(ollama).getByRole("button", { name: "Save" }));
    expect(await within(ollama).findByText("Saved in settings (omrs.jsonc)")).toBeInTheDocument();
    expect(within(ollama).getByText("http://gpu-box.local:11434")).toBeInTheDocument();
    expect(within(ollama).queryByRole("textbox", { name: "Address" })).toBeNull();
    expect(server.find("PUT", "/v1/connections/ollama")[0]?.body).toEqual({ fields: { base_url: "http://gpu-box.local:11434" }, revision: "r1" });
  });

  it("returns a file address to the default with null", async () => {
    const { user, server } = await openProviders({
      "GET /v1/connections": () => list({ ...OLLAMA, fields: [urlField("base_url", "Address", "http://gpu:11434", "config-file")] }, LLAMACPP, OPENROUTER),
      "PUT /v1/connections/ollama": () => ({ status: "ok", revision: "r2" }),
    });
    await user.click(within(card("Ollama")).getByRole("button", { name: "Edit Address" }));
    await user.click(within(card("Ollama")).getByRole("button", { name: "Use default" }));
    expect(server.find("PUT", "/v1/connections/ollama")[0]?.body).toEqual({ fields: { base_url: null }, revision: "r1" });
  });

  it("states that text leaves this machine for a Cloud card and for a non-loopback address", async () => {
    await openProviders({
      "GET /v1/connections": () => list({ ...OLLAMA, fields: [urlField("base_url", "Address", "http://gpu-box.local:11434", "config-file")] }, LLAMACPP, OPENROUTER),
    });
    expect(card("OpenRouter")).toHaveTextContent(/leaves this machine/i);
    expect(card("Ollama")).toHaveTextContent(/leaves this machine/i);
    expect(card("llama.cpp")).not.toHaveTextContent(/leaves this machine/i);
  });

  it("gives the Cloud card its own sentence and a local card the address sentence", async () => {
    await openProviders();
    expect(card("OpenRouter")).toHaveTextContent("Text you send to this provider leaves this machine.");
    expect(card("Ollama")).not.toHaveTextContent("Text you send to this provider leaves this machine.");
  });

  it("shows no leaves-this-machine line for a loopback address", async () => {
    await openProviders();
    expect(card("Ollama")).not.toHaveTextContent(/leaves this machine/i);
  });

  it("shows a keychain key as a summary row with Replace and Remove, and never a full key", async () => {
    await openProviders({
      "GET /v1/connections": () => list(OLLAMA, LLAMACPP, { ...OPENROUTER, fields: [{ ...OPENROUTER.fields[0]!, api_key: KEY } as never] }),
    });
    const openrouter = card("OpenRouter");
    expect(within(openrouter).getByText("Key set · ending wxyz · in system keychain")).toBeInTheDocument();
    expect(within(openrouter).getByRole("button", { name: "Replace API key" })).toBeInTheDocument();
    expect(within(openrouter).getByRole("button", { name: "Remove API key" })).toBeInTheDocument();
    expect(within(openrouter).queryByLabelText("API key")).toBeNull();
    expect(document.body.textContent).not.toContain(KEY);
    expect(document.body.textContent).not.toContain("secret-1234");
  });

  it("shows a key from .env with its words and no button", async () => {
    await openProviders({ "GET /v1/connections": () => list(OLLAMA, LLAMACPP, openrouter({ source: "dotenv", locked: true, lock_reason: "Remove OPENROUTER_API_KEY from the environment or .env to edit it here." })) });
    const card_ = card("OpenRouter");
    expect(within(card_).getByText("Key set · ending wxyz · Set in .env. Change it there.")).toBeInTheDocument();
    expect(within(card_).queryByRole("button", { name: /Replace|Remove/ })).toBeNull();
    expect(within(card_).queryByLabelText("API key")).toBeNull();
  });

  it("shows a key from the environment with its words and no button", async () => {
    await openProviders({ "GET /v1/connections": () => list(OLLAMA, LLAMACPP, openrouter({ source: "env", locked: true, lock_reason: "Remove OPENROUTER_API_KEY from the environment or .env to edit it here." })) });
    const card_ = card("OpenRouter");
    expect(within(card_).getByText("Key set · ending wxyz · Set in the environment. Change it there.")).toBeInTheDocument();
    expect(within(card_).queryByRole("button", { name: /Replace|Remove/ })).toBeNull();
  });

  it("shows a key from a key file with the file, offers Replace and no Remove", async () => {
    await openProviders({ "GET /v1/connections": () => list(OLLAMA, LLAMACPP, openrouter({ source: "key-file" })) });
    const card_ = card("OpenRouter");
    expect(within(card_).getByText("Key set · ending wxyz · from key file secrets/openrouter.key")).toBeInTheDocument();
    expect(within(card_).getByRole("button", { name: "Replace API key" })).toBeInTheDocument();
    expect(within(card_).queryByRole("button", { name: /^Remove/ })).toBeNull();
  });

  it("replaces a key: the input closes, the summary shows the new ending and the key is never shown again", async () => {
    let saved = false;
    const { user, server } = await openProviders({
      "GET /v1/connections": () => list(OLLAMA, LLAMACPP, saved ? openrouter({ last4: "9999" }) : openrouter({ last4: "wxyz" })),
      "PUT /v1/connections/openrouter/key": () => {
        saved = true;
        return { status: "ok", revision: "r2" };
      },
    });
    const card_ = card("OpenRouter");
    await user.click(within(card_).getByRole("button", { name: "Replace API key" }));
    const input = within(card_).getByLabelText("API key");
    expect(input).toHaveValue("");
    expect(input).toHaveAttribute("type", "password");
    expect(input).toHaveAttribute("autocomplete", "off");
    await user.type(input, KEY);
    await user.click(within(card_).getByRole("button", { name: "Save key" }));
    expect(await within(card_).findByText("Key set · ending 9999 · in system keychain")).toBeInTheDocument();
    expect(within(card_).queryByLabelText("API key")).toBeNull();
    expect(server.find("PUT", "/v1/connections/openrouter/key")[0]?.body).toEqual({ api_key: KEY, revision: "r1" });
    expect(document.body.textContent).not.toContain(KEY);
  });

  it("removes a key kept in the keychain", async () => {
    const { user, server } = await openProviders({ "DELETE /v1/connections/openrouter/key": () => ({ status: "ok", revision: "r2" }) });
    await user.click(within(card("OpenRouter")).getByRole("button", { name: "Remove API key" }));
    expect(server.find("DELETE", "/v1/connections/openrouter/key")).toHaveLength(1);
    expect(server.find("DELETE", "/v1/connections/openrouter/key")[0]?.body).toEqual({ revision: "r1" });
  });

  it("shows a key input with the placeholder and the key file hint when no key is set", async () => {
    await openProviders({ "GET /v1/connections": () => list(OLLAMA, LLAMACPP, openrouter(NO_KEY)) });
    const card_ = card("OpenRouter");
    expect(within(card_).getByLabelText("API key")).toHaveAttribute("placeholder", "Paste key (saved to the system keychain)");
    expect(within(card_).getByText("Or put it in secrets/openrouter.key")).toBeInTheDocument();
    expect(within(card_).queryByText(/Key set/)).toBeNull();
  });

  it("shows an optional key as optional with no error", async () => {
    const optional: Connection = { ...OPENROUTER, provider: "openai_compatible", display_name: "OpenAI-compatible", fields: [{ ...OPENROUTER.fields[0]!, ...NO_KEY, required: false }] };
    await openProviders({ "GET /v1/connections": () => list(OLLAMA, LLAMACPP, optional) });
    const card_ = card("OpenAI-compatible");
    expect(within(card_).getByText("Optional")).toBeInTheDocument();
    expect(within(card_).queryByRole("alert")).toBeNull();
  });

  it("replaces the key input with one line when no keychain is available", async () => {
    await openProviders({ "GET /v1/connections": () => ({ ...list(OLLAMA, LLAMACPP, openrouter(NO_KEY)), keychain: "unavailable" }) });
    const card_ = card("OpenRouter");
    expect(card_).toHaveTextContent(/no system keychain/i);
    expect(card_.textContent?.match(/no system keychain/gi)).toHaveLength(1);
    expect(card_).toHaveTextContent("secrets/openrouter.key");
    expect(card_).toHaveTextContent("OPENROUTER_API_KEY");
    expect(within(card_).queryByLabelText("API key")).toBeNull();
    expect(within(card_).queryByRole("button", { name: "Save key" })).toBeNull();
  });

  it.each([
    ["keychain-missing", /removed from the keychain/i],
    ["keychain-unreadable", /could not be read/i],
  ])("explains the key state %s", async (state, words) => {
    await openProviders({ "GET /v1/connections": () => list(OLLAMA, LLAMACPP, openrouter({ ...NO_KEY, state })) });
    expect(card("OpenRouter")).toHaveTextContent(words);
  });

  it("sends no provider request until Test is pressed", async () => {
    const { server } = await openProviders();
    expect(server.calls.filter((call) => call.method !== "GET")).toHaveLength(0);
  });

  it("tests a typed address without saving it", async () => {
    const { user, server } = await openProviders({
      "POST /v1/connections/ollama/test": () => ({ status: "ok", reachable: false, reason: "refused" }),
    });
    const ollama = card("Ollama");
    await user.click(within(ollama).getByRole("button", { name: "Edit Address" }));
    const input = within(ollama).getByRole("textbox", { name: "Address" });
    await user.clear(input);
    await user.type(input, "http://gpu:11434");
    await user.click(within(ollama).getByRole("button", { name: "Test" }));
    const result = await within(ollama).findByRole("status");
    expect(within(result).getByText("Not reachable")).toBeInTheDocument();
    expect(within(result).getByText("refused")).toHaveAttribute("data-slot", "badge");
    expect(result).toHaveTextContent(/connection was refused/i);
    expect(server.find("POST", "/v1/connections/ollama/test")[0]?.body).toEqual({ fields: { base_url: "http://gpu:11434" } });
    expect(server.find("PUT", "/v1/connections")).toHaveLength(0);
  });

  it("tests a typed key and sends it only in the test body", async () => {
    const { user, server } = await openProviders({
      "POST /v1/connections/openrouter/test": () => ({ status: "ok", reachable: false, reason: "unauthorised" }),
    });
    const card_ = card("OpenRouter");
    await user.click(within(card_).getByRole("button", { name: "Replace API key" }));
    await user.type(within(card_).getByLabelText("API key"), KEY);
    await user.click(within(card_).getByRole("button", { name: "Test" }));
    expect(await within(card_).findByText("unauthorised")).toBeInTheDocument();
    expect(server.find("POST", "/v1/connections/openrouter/test")[0]?.body).toEqual({ fields: { api_key: KEY } });
    expect(document.body.textContent).not.toContain(KEY);
  });

  it("tests the saved values with an empty body when nothing is typed", async () => {
    const { user, server } = await openProviders({ "POST /v1/connections/ollama/test": () => ({ status: "ok", reachable: true, reason: null }) });
    await user.click(within(card("Ollama")).getByRole("button", { name: "Test" }));
    expect(await within(card("Ollama")).findByText("Reachable")).toHaveAttribute("data-slot", "badge");
    expect(server.find("POST", "/v1/connections/ollama/test")[0]?.body).toEqual({ fields: {} });
  });

  it("stops testing a typed address after Cancel", async () => {
    const { user, server } = await openProviders({ "POST /v1/connections/ollama/test": () => ({ status: "ok", reachable: true, reason: null }) });
    const ollama = card("Ollama");
    await user.click(within(ollama).getByRole("button", { name: "Edit Address" }));
    await user.type(within(ollama).getByRole("textbox", { name: "Address" }), "x");
    await user.click(within(ollama).getByRole("button", { name: "Cancel" }));
    await user.click(within(ollama).getByRole("button", { name: "Test" }));
    expect(await within(ollama).findByText("Reachable")).toBeInTheDocument();
    expect(server.find("POST", "/v1/connections/ollama/test")[0]?.body).toEqual({ fields: {} });
  });

  it("never shows a reason outside the fixed set as raw text", async () => {
    const { user } = await openProviders({
      "POST /v1/connections/ollama/test": () => ({ status: "ok", reachable: false, reason: "Traceback: boom at /srv/app.py" }),
    });
    await user.click(within(card("Ollama")).getByRole("button", { name: "Test" }));
    expect(await within(card("Ollama")).findByText("Not reachable")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("Traceback");
  });

  it("shows the rule message when a save is refused with 400, in place of the generic line", async () => {
    const message = "The address must start with http:// or https://.";
    const { user } = await openProviders({ "PUT /v1/connections/ollama": () => json({ status: "error", message }, 400) });
    const ollama = card("Ollama");
    await user.click(within(ollama).getByRole("button", { name: "Edit Address" }));
    await user.type(within(ollama).getByRole("textbox", { name: "Address" }), "x");
    await user.click(within(ollama).getByRole("button", { name: "Save" }));
    expect(await within(ollama).findByRole("alert")).toHaveTextContent(message);
    expect(screen.queryByText(/could not complete/i)).toBeNull();
  });

  it("shows the conflict with a Reload action when omrs.jsonc changed on disk, and reads the cards again on Reload", async () => {
    const message = "omrs.jsonc changed on disk. Reload to see the new values.";
    const { user, server } = await openProviders({ "PUT /v1/connections/ollama": () => json({ status: "error", message }, 409) });
    const ollama = card("Ollama");
    await user.click(within(ollama).getByRole("button", { name: "Edit Address" }));
    await user.type(within(ollama).getByRole("textbox", { name: "Address" }), "x");
    await user.click(within(ollama).getByRole("button", { name: "Save" }));
    expect(await within(ollama).findByRole("alert")).toHaveTextContent(message);
    const reads = server.find("GET", "/v1/connections").length;
    await user.click(within(ollama).getByRole("button", { name: "Reload" }));
    await waitFor(() => expect(server.find("GET", "/v1/connections").length).toBe(reads + 1));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the generic line for a failure that is not a refused value", async () => {
    const { user } = await openProviders({ "PUT /v1/connections/ollama": () => json({ status: "error", message: "boom at /srv/x" }, 500) });
    const ollama = card("Ollama");
    await user.click(within(ollama).getByRole("button", { name: "Edit Address" }));
    await user.type(within(ollama).getByRole("textbox", { name: "Address" }), "x");
    await user.click(within(ollama).getByRole("button", { name: "Save" }));
    expect(await within(ollama).findByRole("alert")).toHaveTextContent(/could not complete/i);
    expect(screen.queryByText(/\/srv\/x/)).toBeNull();
  });

  it("shows a friendly line with Retry when the providers cannot load", async () => {
    startApp("#/settings/providers", settingsServer({ "GET /v1/connections": () => json({ status: "error", message: "boom" }, 500) }));
    expect(await screen.findByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
