import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Integration, RuntimeComponents, RuntimeItem } from "../api/integrations";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";

const LICENCE_FIX = "python3 ocr-workers/provision.py dots-mocr --accept-model-licence";

function item(name: string, status: RuntimeItem["status"], extra: Partial<RuntimeItem> = {}): RuntimeItem {
  return { name, purpose: `Purpose of ${name}.`, status, reason: null, fix: null, used_by: [], ...extra };
}

const RUNTIME: RuntimeComponents = {
  ocr_engines: [
    item("dots-mocr", "missing", {
      reason: "Not provisioned. The model licence adds terms. Read LICENCE-NOTES.md in the engine folder before you accept it.",
      fix: LICENCE_FIX,
      used_by: ["ocr_engine_primary"],
    }),
    item("paddleocr-vl", "ready"),
  ],
  model_files: [],
  local_servers: [item("llama.cpp chat server", "not-running", { reason: "No server answers at http://localhost:8081/v1." })],
};

function entry(id: string, name: string, readiness?: Integration["readiness"]): Integration {
  return {
    id,
    name,
    purpose: `Purpose of ${id}.`,
    extra: id,
    install_command: `uv sync --extra ${id}`,
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
    ...(readiness ? { readiness } : {}),
  };
}

const CATALOGUE = [
  entry("llamacpp", "llama.cpp provider", { ready: false, line: "Not running at http://localhost:8081/v1" }),
  entry("openrouter", "OpenRouter provider", { ready: false, line: "No key set" }),
];

function workersRow(source = "default", value = "") {
  return {
    key: "ocr_workers_dir",
    value,
    source,
    applies: "restart",
    restart_pending: false,
    saved: null as string | null,
    editable: source !== "env",
    read_only_reason: null,
    kind: "text",
    choices: null,
    min: null,
    max: null,
    nullable: true,
  };
}

function configuration(row = workersRow()) {
  return { path: "~/.config/omrs/omrs.jsonc", revision: "r1", settings: [row], problems: [], handover: { pending: false, folder: null } };
}

function serve(runtime: RuntimeComponents = RUNTIME, handlers: Parameters<typeof documentsServer>[0] = {}) {
  return documentsServer({
    "GET /v1/integrations": () => ({ status: "ok", install_type: "checkout", integrations: CATALOGUE, tools: [], runtime }),
    "GET /v1/settings/configuration": () => configuration(),
    ...handlers,
  });
}

const group = async (name: string) => screen.findByRole("region", { name });
const row = async (groupName: string, name: string) => {
  const items = within(await group(groupName)).getAllByRole("listitem");
  const found = items.find((entry) => within(entry).queryByText(name, { selector: "h3" }) !== null);
  if (found === undefined) throw new Error(`No row ${name}`);
  return found;
};

afterEach(() => vi.restoreAllMocks());

describe("Runtime groups", () => {
  it("shows a used, missing engine in red with its reason and copy command", async () => {
    startApp("#/integrations", serve());
    const dots = await row("OCR engines", "dots-mocr");
    const badge = within(dots).getByText("Missing", { selector: "[data-slot=badge]" });
    expect(badge).toHaveClass("text-status-error-label");
    expect(dots).toHaveTextContent("LICENCE-NOTES.md");
    expect(dots).toHaveTextContent("ocr_engine_primary");
    expect(within(dots).getByText(LICENCE_FIX)).toBeInTheDocument();
    expect(within(dots).getByRole("button", { name: "Copy fix command for dots-mocr" })).toBeInTheDocument();
  });

  it("shows an unused server that is not running without red", async () => {
    startApp("#/integrations", serve());
    const llama = await row("Local servers", "llama.cpp chat server");
    const badge = within(llama).getByText("Not running", { selector: "[data-slot=badge]" });
    expect(badge).not.toHaveClass("text-status-error-label");
  });

  it("lays each group out like the integration cards: one card per part, in masonry columns", async () => {
    startApp("#/integrations", serve());
    const engines = await group("OCR engines");
    // The group is a heading and a card area, not a card that holds cards.
    expect(engines).not.toHaveAttribute("data-slot", "card");
    expect(engines.closest("[data-slot=card]")).toBeNull();
    const masonry = within(engines).getByTestId("masonry");
    for (const name of ["dots-mocr", "paddleocr-vl"]) {
      const card = await row("OCR engines", name);
      expect(card.querySelector("[data-slot=card]") ?? card).toHaveAttribute("data-slot", "card");
      expect(masonry).toContainElement(card);
    }
    // The workers folder sits in a card of its own in the same columns.
    const folder = await within(engines).findByText("OCR workers folder");
    expect(masonry).toContainElement(folder.closest("[data-slot=card]") as HTMLElement);
  });

  it("says when a group is empty", async () => {
    startApp("#/integrations", serve());
    expect(await group("Model files")).toHaveTextContent("Nothing to show in this group.");
  });
});

describe("OCR workers folder", () => {
  it("saves the folder and says it applies at the next launch, with the restart action", async () => {
    const user = userEvent.setup();
    const sent: unknown[] = [];
    startApp(
      "#/integrations",
      serve(RUNTIME, {
        "PUT /v1/settings/configuration": (body) => {
          sent.push(body);
          return configuration({ ...workersRow("default"), restart_pending: true, saved: "~/workers" });
        },
      }),
    );
    const engines = await group("OCR engines");
    await user.click(await within(engines).findByRole("button", { name: "Edit OCR workers folder" }));
    const field = within(engines).getByRole("textbox", { name: "OCR workers folder" });
    await user.type(field, "~/workers");
    await user.click(within(engines).getByRole("button", { name: "Save" }));
    expect(sent).toEqual([{ revision: "r1", changes: { ocr_workers_dir: "~/workers" } }]);
    expect(await within(engines).findByText(/applies at the next launch/i)).toBeInTheDocument();
    expect(await screen.findByRole("dialog")).toHaveTextContent(/OCR workers folder/);
  });

  it("shows the server's reason when it refuses the folder", async () => {
    const user = userEvent.setup();
    startApp(
      "#/integrations",
      serve(RUNTIME, {
        "PUT /v1/settings/configuration": () =>
          json({ status: "error", message: "ocr_workers_dir: The folder must be a full path to an existing folder that holds an engines folder." }, 400),
      }),
    );
    const engines = await group("OCR engines");
    await user.click(await within(engines).findByRole("button", { name: "Edit OCR workers folder" }));
    await user.type(within(engines).getByRole("textbox", { name: "OCR workers folder" }), "/tmp/bare");
    await user.click(within(engines).getByRole("button", { name: "Save" }));
    expect(await within(engines).findByRole("alert")).toHaveTextContent("holds an engines folder");
  });

  it("keeps an environment value read-only and names the variable", async () => {
    startApp(
      "#/integrations",
      serve(RUNTIME, { "GET /v1/settings/configuration": () => configuration(workersRow("env", "~/workers")) }),
    );
    const engines = await group("OCR engines");
    expect(await within(engines).findByText(/Remove OCR_WORKERS_DIR/)).toBeInTheDocument();
    expect(within(engines).queryByRole("button", { name: "Edit OCR workers folder" })).not.toBeInTheDocument();
  });
});

describe("Provider readiness", () => {
  it("shows the readiness line on the llama.cpp and OpenRouter cards next to Base default", async () => {
    startApp("#/integrations", serve());
    const list = await screen.findByRole("list", { name: "Integrations" });
    const llama = within(list).getAllByRole("listitem").find((entry) => within(entry).queryByRole("heading", { name: "llama.cpp provider" }));
    const openrouter = within(list).getAllByRole("listitem").find((entry) => within(entry).queryByRole("heading", { name: "OpenRouter provider" }));
    expect(llama).toHaveTextContent("Not running at http://localhost:8081/v1");
    expect(llama).toHaveTextContent("Base default");
    expect(llama).not.toHaveTextContent(/^Ready$/);
    expect(openrouter).toHaveTextContent("No key set");
  });
});
