import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { startApp } from "../test/startApp";
import { ROUTER_RUNNING, ROUTER_STOPPED, routerStatus, settingsServer, WITH_CREDENTIALS } from "./test/fixtures";

const LIMIT = "Models loaded at once";
const MARGIN = "Free memory margin (MiB)";

async function open(handlers = {}) {
  const server = settingsServer({ ...WITH_CREDENTIALS, ...handlers });
  startApp("#/settings/providers", server);
  await screen.findByRole("heading", { level: 3, name: "llama.cpp" });
  const panel = () => within(screen.getByRole("region", { name: "llama.cpp" })).getByRole("group", { name: "Router" });
  await waitFor(() => expect(within(panel()).getByRole("status")).toBeInTheDocument());
  const row = (label: string) => within(panel()).getByText(label).closest("[data-slot='setting-row']") as HTMLElement;
  return { server, user: userEvent.setup(), panel, row };
}

describe("The Router panel shows and edits the model limit and the memory margin", () => {
  it("Defaults shown: 4 and 8,192 with source default, their defaults and one help line each", async () => {
    const { row } = await open();
    expect(row(LIMIT)).toHaveTextContent("4");
    expect(row(LIMIT)).toHaveTextContent("default");
    expect(row(LIMIT)).toHaveTextContent("Default 4");
    expect(row(LIMIT)).toHaveTextContent("How many models the router keeps in memory at the same time.");
    expect(row(MARGIN)).toHaveTextContent("8,192");
    expect(row(MARGIN)).toHaveTextContent("Default 8,192");
    expect(row(MARGIN)).toHaveTextContent("Memory that the router leaves free, in MiB.");
  });

  it("Edit and save the model limit: sends 2, shows source omrs.jsonc and Restart to apply", async () => {
    const put: unknown[] = [];
    const { row, panel, user } = await open({
      "GET /v1/llamacpp/router": () => ROUTER_RUNNING,
      "PUT /v1/llamacpp/router": (body: unknown) => {
        put.push(body);
        return { ...routerStatus({ ...ROUTER_RUNNING, pending_restart: true }, { models_max: { value: 2, source: "config-file" } }), revision: "r2" };
      },
    });
    await waitFor(() => expect(within(panel()).getByRole("status")).toHaveTextContent("Running"));
    await user.click(within(row(LIMIT)).getByRole("button", { name: `Edit ${LIMIT}` }));
    const input = within(row(LIMIT)).getByRole("spinbutton", { name: LIMIT });
    await user.clear(input);
    await user.type(input, "2");
    await user.click(within(row(LIMIT)).getByRole("button", { name: "Save" }));
    expect(await within(panel()).findByText("Restart to apply")).toBeInTheDocument();
    expect(put).toEqual([{ models_max: 2, revision: "r1" }]);
    expect(row(LIMIT)).toHaveTextContent("Saved in settings (omrs.jsonc)");
  });

  it("Use default: removes the key and shows 8,192 with source default", async () => {
    const put: unknown[] = [];
    const saved = { memory_margin_mib: { value: 16384, source: "config-file" as const } };
    const { row, user } = await open({
      "GET /v1/llamacpp/router": () => routerStatus({}, saved),
      "PUT /v1/llamacpp/router": (body: unknown) => {
        put.push(body);
        return ROUTER_STOPPED;
      },
    });
    expect(await screen.findByText("16,384")).toBeInTheDocument();
    await user.click(within(row(MARGIN)).getByRole("button", { name: `Edit ${MARGIN}` }));
    await user.click(within(row(MARGIN)).getByRole("button", { name: "Use default" }));
    await waitFor(() => expect(row(MARGIN)).toHaveTextContent("8,192"));
    expect(put).toEqual([{ memory_margin_mib: null, revision: "r1" }]);
    expect(row(MARGIN)).not.toHaveTextContent("Saved in settings");
  });

  it("Out of range refused: shows the accepted range and sends nothing", async () => {
    const { row, server, user } = await open();
    await user.click(within(row(LIMIT)).getByRole("button", { name: `Edit ${LIMIT}` }));
    const input = within(row(LIMIT)).getByRole("spinbutton", { name: LIMIT });
    await user.clear(input);
    await user.type(input, "17");
    await user.click(within(row(LIMIT)).getByRole("button", { name: "Save" }));
    expect(await within(row(LIMIT)).findByText("Enter 1 to 16.")).toBeInTheDocument();
    await user.click(within(row(LIMIT)).getByRole("button", { name: "Cancel" }));
    await user.click(within(row(MARGIN)).getByRole("button", { name: `Edit ${MARGIN}` }));
    const margin = within(row(MARGIN)).getByRole("spinbutton", { name: MARGIN });
    await user.clear(margin);
    await user.type(margin, "262145");
    await user.click(within(row(MARGIN)).getByRole("button", { name: "Save" }));
    expect(await within(row(MARGIN)).findByText("Enter 0 to 262,144.")).toBeInTheDocument();
    expect(server.find("PUT", "/v1/llamacpp/router")).toHaveLength(0);
  });

  it("Locked by environment: shows a lock and the variable name, and offers no edit", async () => {
    const lock = "Remove LLAMACPP_ROUTER_MODELS_MAX from the environment or .env to edit it here.";
    const { row } = await open({ "GET /v1/llamacpp/router": () => routerStatus({}, { models_max: { value: 3, source: "env", locked: true, lock_reason: lock } }) });
    await waitFor(() => expect(row(LIMIT)).toHaveTextContent(lock));
    expect(within(row(LIMIT)).getByLabelText("Locked")).toBeInTheDocument();
    expect(within(row(LIMIT)).queryByRole("button", { name: `Edit ${LIMIT}` })).toBeNull();
    expect(within(row(MARGIN)).getByRole("button", { name: `Edit ${MARGIN}` })).toBeInTheDocument();
  });
});
