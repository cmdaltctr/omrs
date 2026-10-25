import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Handler } from "../../test/fakeDocumentsServer";
import { startApp } from "../../test/startApp";
import { experimentsServer, type ServerState } from "./experimentsServer";

/** Renders the whole app at an Experiments hash against the fixture server. */
export function openExperiments(initial: Partial<ServerState> = {}, extra: Record<string, Handler> = {}, hash = "#/experiments") {
  const server = experimentsServer(initial, extra);
  startApp(hash, server);
  return { server, user: userEvent.setup() };
}

/** Opens Experiments and switches to one section by its chip. */
export async function openSection(name: string, initial: Partial<ServerState> = {}, extra: Record<string, Handler> = {}) {
  const opened = openExperiments(initial, extra);
  await opened.user.click(await screen.findByRole("button", { name }));
  return opened;
}

/** Opens the Sandboxes section: experiment contexts grouped under folders. */
export function openSandboxes(initial: Partial<ServerState> = {}, extra: Record<string, Handler> = {}) {
  return openSection("Sandboxes", initial, extra);
}
