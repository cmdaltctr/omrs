import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { defaultLibrary, fakeRevision, OCR, OVERLAP, PROTOCOL, RERANKER, type LibraryState } from "../test/libraryServer";
import { openExperiments } from "../test/openExperiments";
import { formatEdited } from "./FileEditor";

const PROTOCOL_PATH = `/v1/experiment-projects/p1/experiments/${RERANKER}/files/protocol.md`;

function openPage(folder = RERANKER, library: LibraryState = defaultLibrary(), project = "p1") {
  return openExperiments({ library }, {}, `#/experiments/library/${project}/${encodeURIComponent(folder)}`);
}

const tab = (name: string) => within(screen.getByRole("group", { name: "Experiment tabs" })).getByRole("button", { name: new RegExp(`^${name}`) });
const editor = (name = "protocol.md") => screen.getByRole("textbox", { name: `Text of ${name}` });

async function startEditing(user: ReturnType<typeof openPage>["user"], name = "protocol.md") {
  await user.click(await screen.findByRole("button", { name: `Edit ${name}` }));
  return editor(name);
}

function unloadPrevented(): boolean {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}

describe("file editor", () => {
  it("formats the last edit in local time as day, short month, year, hour and minute", () => {
    expect(formatEdited("2026-10-26T14:05:00Z")).toMatch(/^\d{1,2} Oct 2026, \d{2}:\d{2}$/);
  });

  it("opens the editor with the loaded text, saves with the loaded revision and shows the last edit", async () => {
    const { user, server } = openPage();
    const field = await startEditing(user);
    expect(field).toHaveValue(PROTOCOL);
    expect(screen.queryByRole("heading", { name: "Hypothesis" })).toBeNull();
    await user.clear(field);
    await user.type(field, "# Protocol{Enter}{Enter}New text.");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(server.find("PUT", PROTOCOL_PATH)).toHaveLength(1));
    expect(server.find("PUT", PROTOCOL_PATH)[0]!.body).toEqual({ text: "# Protocol\n\nNew text.", base_revision: fakeRevision(PROTOCOL) });
    expect(await screen.findByText("Saved.")).toHaveAttribute("role", "status");
    expect(await screen.findByText(`Last edited ${formatEdited("2026-10-26T14:05:00Z")}`)).toBeInTheDocument();
    expect(await screen.findByText("New text.")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Text of protocol.md" })).toBeNull();
    // Focus goes back to the Edit button when the editor closes.
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit protocol.md" })).toHaveFocus());
  });

  it("keeps the text on a changed file, then Reload loads the new revision", async () => {
    const library = defaultLibrary();
    const { user, server } = openPage(RERANKER, library);
    const field = await startEditing(user);
    await user.type(field, " Mine.");
    library.texts[`p1/${RERANKER}/protocol.md`] = "# Protocol\n\nChanged in a terminal.";
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("This file changed on disk after you opened it. Copy your text, select Reload, then add your changes again.")).toBeInTheDocument();
    expect(editor()).toHaveValue(`${PROTOCOL} Mine.`);
    await user.click(screen.getByRole("button", { name: "Reload" }));
    await waitFor(() => expect(editor()).toHaveValue("# Protocol\n\nChanged in a terminal."));
    await user.type(editor(), " Again.");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", PROTOCOL_PATH)).toHaveLength(2));
    expect(server.find("PUT", PROTOCOL_PATH)[1]!.body).toEqual({
      text: "# Protocol\n\nChanged in a terminal. Again.",
      base_revision: fakeRevision("# Protocol\n\nChanged in a terminal."),
    });
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  it("asks before Cancel discards changes, and Keep editing keeps the text", async () => {
    const { user } = openPage();
    const field = await startEditing(user);
    await user.type(field, " Draft.");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    const dialog = await screen.findByRole("dialog", { name: "Discard your changes to protocol.md?" });
    await user.click(within(dialog).getByRole("button", { name: "Keep editing" }));
    expect(editor()).toHaveValue(`${PROTOCOL} Draft.`);

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Discard" }));
    expect(screen.queryByRole("textbox", { name: "Text of protocol.md" })).toBeNull();
    expect(await screen.findByRole("heading", { name: "Hypothesis" })).toBeInTheDocument();
  });

  it("leaves without a dialog when nothing changed", async () => {
    const { user } = openPage();
    await startEditing(user);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByRole("textbox", { name: "Text of protocol.md" })).toBeNull();
  });

  it("asks before a tab switch discards changes", async () => {
    const { user } = openPage();
    await user.type(await startEditing(user), " Draft.");
    await user.click(tab("Plan"));
    const dialog = await screen.findByRole("dialog", { name: "Discard your changes to protocol.md?" });
    await user.click(within(dialog).getByRole("button", { name: "Keep editing" }));
    expect(tab("Protocol")).toHaveAttribute("aria-pressed", "true");
    expect(editor()).toHaveValue(`${PROTOCOL} Draft.`);

    await user.click(tab("Plan"));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Discard" }));
    expect(tab("Plan")).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText(/"seeds": 3/)).toBeInTheDocument();
  });

  it("asks before an in-app link discards changes", async () => {
    const { user } = openPage();
    await user.type(await startEditing(user), " Draft.");
    await user.click(screen.getAllByRole("link", { name: "Back to Experiments" })[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Discard your changes to protocol.md?" });
    await user.click(within(dialog).getByRole("button", { name: "Keep editing" }));
    expect(window.location.hash).toBe(`#/experiments/library/p1/${RERANKER}`);
    expect(editor()).toHaveValue(`${PROTOCOL} Draft.`);
  });

  it("sets the browser leave prompt only while there are unsaved changes", async () => {
    const { user } = openPage();
    const field = await startEditing(user);
    expect(unloadPrevented()).toBe(false);
    await user.type(field, "x");
    expect(unloadPrevented()).toBe(true);
    await user.type(field, "{Backspace}");
    expect(unloadPrevented()).toBe(false);
  });

  it("warns on a finished experiment and names its status", async () => {
    const { user } = openPage();
    await user.click(await screen.findByRole("button", { name: /^Report/ }));
    await startEditing(user, "report.md");
    expect(screen.getByText(/This experiment is finished \(PASS\)\. Its protocol and report are part of the record\./)).toHaveTextContent(
      "This experiment is finished (PASS). Its protocol and report are part of the record. Saving changes the file on disk. Git keeps the old text, and the app records the save in edits.jsonl.",
    );
  });

  it("warns on a converted record that is not finished", async () => {
    const library = defaultLibrary();
    library.experiments.p2 = [{ ...library.experiments.p2![0]!, migrated: true }];
    library.files[`p2/${OCR}`] = [{ name: "protocol.md", size: 10, viewable: true }];
    library.texts[`p2/${OCR}/protocol.md`] = "# Protocol";
    const { user } = openPage(OCR, library, "p2");
    await startEditing(user);
    expect(screen.getByText(/^This is a converted record\./)).toHaveTextContent(
      "This is a converted record. Saving changes the file on disk. Git keeps the old text, and the app records the save in edits.jsonl.",
    );
  });

  it("shows no warning on a planned experiment without a migration note", async () => {
    const library = defaultLibrary();
    library.files[`p2/${OCR}`] = [{ name: "protocol.md", size: 10, viewable: true }];
    library.texts[`p2/${OCR}/protocol.md`] = "# Protocol";
    const { user } = openPage(OCR, library, "p2");
    await startEditing(user);
    expect(screen.queryByText(/This experiment is finished|This is a converted record/)).toBeNull();
  });

  it("edits results.md in the Report tab of an older folder", async () => {
    const { user, server } = openPage(OVERLAP);
    const field = await startEditing(user, "results.md");
    await user.type(field, " More.");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", `/v1/experiment-projects/p1/experiments/${OVERLAP}/files/results.md`)).toHaveLength(1));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  it("shows the server line when a save is not recorded", async () => {
    const { user } = openExperiments(
      { library: defaultLibrary() },
      { [`PUT ${PROTOCOL_PATH}`]: () => new Response(JSON.stringify({ status: "error", message: "The file was not saved, because the app could not record the edit in edits.jsonl." }), { status: 500, headers: { "content-type": "application/json" } }) },
      `#/experiments/library/p1/${RERANKER}`,
    );
    await user.type(await startEditing(user), " Draft.");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The file was not saved, because the app could not record the edit in edits.jsonl.");
    expect(editor()).toHaveValue(`${PROTOCOL} Draft.`);
  });
});
