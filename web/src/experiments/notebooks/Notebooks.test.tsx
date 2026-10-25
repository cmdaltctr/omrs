import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { defaultLibrary, OCR, RERANKER } from "../test/libraryServer";
import { openExperiments, openSection } from "../test/openExperiments";

const openNotebooks = () => openSection("Notebooks", { library: defaultLibrary() });
const openNotebook = (id: string) => openExperiments({ library: defaultLibrary() }, {}, `#/experiments/notebooks/${encodeURIComponent(id)}`);
const row = (name: string) => screen.findByRole("group", { name: `Notebook ${name}` });

describe("notebooks", () => {
  it("lists the user's notebooks and one notebook per project", async () => {
    await openNotebooks();
    const paper = await row("Paper 1");
    expect(within(paper).getByRole("link", { name: "Paper 1" })).toHaveAttribute("href", "#/experiments/notebooks/n1");
    expect(within(paper).getByText("2 experiments")).toBeInTheDocument();
    const projects = screen.getByRole("list", { name: "Project notebooks" });
    expect(within(projects).getByRole("link", { name: "OMRS" })).toHaveAttribute("href", "#/experiments/notebooks/project%3Ap1");
    expect(within(projects).getByText("3 experiments")).toBeInTheDocument();
    expect(within(projects).queryByRole("button", { name: /Rename|Delete/ })).toBeNull();
  });

  it("creates a notebook and refuses a duplicate name with the server's reason", async () => {
    const { user, server } = await openNotebooks();
    const form = await screen.findByRole("form", { name: "Create a notebook" });
    await user.type(within(form).getByLabelText("Notebook name"), "Paper 2");
    await user.click(within(form).getByRole("button", { name: "Create notebook" }));
    expect(await row("Paper 2")).toBeInTheDocument();
    expect(within(form).getByRole("status")).toHaveTextContent("Created Paper 2.");

    await user.type(within(form).getByLabelText("Notebook name"), "Paper 1");
    await user.click(within(form).getByRole("button", { name: "Create notebook" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("A notebook named Paper 1 already exists.");
    expect(server.state.library.notebooks.map((item) => item.name)).toEqual(["Paper 1", "Paper 2"]);
  });

  it("renames a notebook", async () => {
    const { user, server } = await openNotebooks();
    await user.click(within(await row("Paper 1")).getByRole("button", { name: "Rename Paper 1" }));
    const form = screen.getByRole("form", { name: "Rename Paper 1" });
    await user.clear(within(form).getByLabelText("New name"));
    await user.type(within(form).getByLabelText("New name"), "Thesis");
    await user.click(within(form).getByRole("button", { name: "Save name" }));
    expect(await row("Thesis")).toBeInTheDocument();
    expect(server.find("PATCH", "/v1/notebooks/n1")[0]!.body).toEqual({ name: "Thesis" });
  });

  it("deletes a notebook only after confirmation", async () => {
    const { user, server } = await openNotebooks();
    const paper = await row("Paper 1");
    await user.click(within(paper).getByRole("button", { name: "Delete Paper 1" }));
    expect(within(paper).getByText(/No experiment file changes/)).toBeInTheDocument();
    await user.click(within(paper).getByRole("button", { name: "Keep notebook" }));
    expect(server.find("DELETE", "/v1/notebooks")).toHaveLength(0);
    await user.click(within(paper).getByRole("button", { name: "Delete Paper 1" }));
    await user.click(within(paper).getByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(server.find("DELETE", "/v1/notebooks/n1")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("group", { name: "Notebook Paper 1" })).toBeNull());
    expect(screen.getByText(/You have no notebook yet/)).toBeInTheDocument();
  });

  it("shows a user notebook's entries from any project, with a missing entry kept until removed", async () => {
    const { user, server } = openNotebook("n1");
    expect(await screen.findByRole("heading", { level: 1, name: "Paper 1" })).toBeInTheDocument();
    const ocr = await screen.findByRole("group", { name: `Experiment ${OCR}` });
    expect(within(ocr).getByText("PLANNED")).toBeInTheDocument();
    expect(within(ocr).getByText("Experiment 1 · 2026-07-01 · Paper")).toBeInTheDocument();
    const gone = screen.getByRole("group", { name: "Experiment 9-renamed-2026-01-01" });
    expect(within(gone).getByText("Missing")).toBeInTheDocument();
    expect(within(gone).getByText("OMRS")).toBeInTheDocument();

    await user.click(within(gone).getByRole("button", { name: "Remove 9-renamed-2026-01-01 from Paper 1" }));
    expect(server.find("DELETE", "/v1/notebooks/n1/entries")).toHaveLength(0);
    await user.click(within(gone).getByRole("button", { name: "Confirm remove" }));
    await waitFor(() => expect(server.find("DELETE", "/v1/notebooks/n1/entries/p1/9-renamed-2026-01-01")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("group", { name: "Experiment 9-renamed-2026-01-01" })).toBeNull());
    expect(screen.getByRole("group", { name: `Experiment ${OCR}` })).toBeInTheDocument();
  });

  it("shows a project notebook with every experiment and no remove action", async () => {
    openNotebook("project:p1");
    expect(await screen.findByRole("heading", { level: 1, name: "OMRS" })).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Notebook entries" });
    expect(within(list).getAllByRole("group", { name: /^Experiment / })).toHaveLength(3);
    expect(within(list).getByRole("link", { name: "Title of reranker threshold" })).toHaveAttribute("href", `#/experiments/library/p1/${RERANKER}`);
    expect(within(list).queryByRole("button", { name: /^Remove/ })).toBeNull();
  });

  it("collects experiments from two projects in one new notebook", async () => {
    const { user, server } = await openNotebooks();
    const form = await screen.findByRole("form", { name: "Create a notebook" });
    await user.type(within(form).getByLabelText("Notebook name"), "Review");
    await user.click(within(form).getByRole("button", { name: "Create notebook" }));
    await row("Review");
    window.location.hash = `#/experiments/library/p1/${RERANKER}`;
    await user.click(await screen.findByRole("button", { name: "Add to notebook" }));
    await user.click(await screen.findByRole("button", { name: "Review" }));
    await screen.findByText("Added to Review.");
    window.location.hash = `#/experiments/library/p2/${OCR}`;
    await screen.findByRole("heading", { level: 1, name: /ocr quality/ });
    await user.click(await screen.findByRole("button", { name: "Add to notebook" }));
    await user.click(await screen.findByRole("button", { name: "Review" }));
    await screen.findByText("Added to Review.");
    expect(server.find("PUT", "/v1/notebooks/n2/entries").map((call) => call.body)).toEqual([
      { project_id: "p1", folder: RERANKER },
      { project_id: "p2", folder: OCR },
    ]);
    window.location.hash = "#/experiments/notebooks/n2";
    const list = await screen.findByRole("list", { name: "Notebook entries" });
    expect(within(list).getByText("Experiment 1 · 2026-05-12 · OMRS")).toBeInTheDocument();
    expect(within(list).getByText("Experiment 1 · 2026-07-01 · Paper")).toBeInTheDocument();
  });

  it("shows a way back for a notebook the server does not know", async () => {
    openNotebook("n404");
    expect(await screen.findByText('The notebook "n404" could not be found.')).toBeInTheDocument();
  });
});
