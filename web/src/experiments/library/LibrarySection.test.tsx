import { screen, waitFor, within } from "@testing-library/react";
import type userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { json } from "../../test/fakeDocumentsServer";
import { defaultLibrary, experiment, OCR, OLD_GRAPH, OVERLAP, project, RERANKER, type LibraryState } from "../test/libraryServer";
import { openExperiments } from "../test/openExperiments";

type User = ReturnType<typeof userEvent.setup>;

function openLibrary(library: LibraryState = defaultLibrary(), extra = {}) {
  return openExperiments({ library }, extra);
}

async function choose(user: User, field: string, option: string) {
  await user.click(await screen.findByRole("combobox", { name: field }));
  await user.click(await screen.findByRole("option", { name: option }));
}

const cards = () => within(screen.getByRole("list", { name: "Experiments" })).getAllByRole("group", { name: /^Experiment / });
const card = (folder: string) => screen.getByRole("group", { name: `Experiment ${folder}` });

describe("experiment library", () => {
  it("lists the experiments of every available project as cards with status badges and checker counts", async () => {
    const { server } = openLibrary();
    await screen.findByRole("list", { name: "Experiments" });
    expect(cards()).toHaveLength(4);
    const reranker = card(RERANKER);
    expect(within(reranker).getByText("PASS")).toBeInTheDocument();
    expect(within(reranker).getByText("1 error")).toBeInTheDocument();
    expect(within(reranker).getByText("1 warning")).toBeInTheDocument();
    expect(within(reranker).getByText("Finding of 1-reranker-threshold-2026-05-12.")).toBeInTheDocument();
    expect(within(reranker).getByText("Experiment 1 · 2026-05-12 · OMRS")).toBeInTheDocument();
    expect(within(reranker).getByRole("link", { name: "Title of reranker threshold" })).toHaveAttribute("href", `#/experiments/library/p1/${RERANKER}`);
    expect(within(card(OCR)).getByText("Experiment 1 · 2026-07-01 · Paper")).toBeInTheDocument();
    expect(within(card(OVERLAP)).getByText("FAIL")).toBeInTheDocument();
    expect(within(card(OVERLAP)).queryByRole("group", { name: "Checker findings" })).toBeNull();
    expect(screen.getByText("Showing 4 experiments of 4.")).toBeInTheDocument();
    // The title link stays; every card also has an Open button to the same page.
    for (const item of cards()) {
      const title = within(item).getByRole("heading").textContent ?? "";
      const open = within(item).getByRole("link", { name: `Open ${title}` });
      expect(open).toHaveTextContent("Open");
      expect(open).toHaveClass("bg-primary-tint", "text-primary-label");
      expect(open).toHaveAttribute("href", within(item).getByRole("link", { name: title }).getAttribute("href"));
    }
    // The project whose folder is gone is named, and its experiments are not asked for.
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(server.find("GET", "/v1/experiment-projects/p3")).toHaveLength(0);
  });

  it("shows fifty cards for a project of fifty records", async () => {
    const library = defaultLibrary();
    library.projects = [project("p1", "OMRS")];
    library.experiments = { p1: Array.from({ length: 50 }, (_, i) => experiment(`${i + 1}-run-2026-01-01`, i % 2 ? "PASS" : "FAIL")) };
    openLibrary(library);
    await screen.findByRole("list", { name: "Experiments" });
    expect(cards()).toHaveLength(50);
    expect(screen.getAllByText("PASS")).toHaveLength(25);
  });

  it("filters by status and category and searches the number, title and finding", async () => {
    const { user } = openLibrary();
    await screen.findByRole("list", { name: "Experiments" });
    await choose(user, "Status", "FAIL");
    expect(cards().map((item) => item.getAttribute("aria-label"))).toEqual([`Experiment ${OVERLAP}`]);
    await choose(user, "Status", "Any status");
    await choose(user, "Category", "ingestion");
    expect(cards()).toHaveLength(2);
    await user.type(screen.getByRole("searchbox", { name: "Search" }), "ocr");
    expect(cards().map((item) => item.getAttribute("aria-label"))).toEqual([`Experiment ${OCR}`]);
    await user.clear(screen.getByRole("searchbox", { name: "Search" }));
    await user.type(screen.getByRole("searchbox", { name: "Search" }), "nothing like this");
    expect(screen.getByText("No experiment matches these filters.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(cards()).toHaveLength(4);
  });

  it("shows one project with its folder, reserved numbers and project checks", async () => {
    const { user, server } = openLibrary();
    await screen.findByRole("list", { name: "Experiments" });
    await choose(user, "Project", "OMRS");
    await waitFor(() => expect(cards()).toHaveLength(3));
    expect(screen.getByText("/work/p1")).toBeInTheDocument();
    expect(screen.getByText("Planned rerun of experiment 2.")).toBeInTheDocument();
    const checks = screen.getByRole("list", { name: "Project checks" });
    expect(within(checks).getByText("The EXP_README.md index is out of date.")).toBeInTheDocument();
    expect(within(checks).getByText("warning")).toBeInTheDocument();
    // A folder whose record did not load is named in the project checks.
    const broken = within(checks).getByText("experiment.json is missing.", { exact: false }).closest("li")!;
    expect(broken).toHaveTextContent("Folder 5-broken-2026-02-01: experiment.json is missing.");
    // A card for one project does not repeat the project name.
    expect(within(card(OLD_GRAPH)).getByText("Experiment 3 · 2026-04-01")).toBeInTheDocument();
    expect(server.find("GET", "/v1/experiment-projects/p2/experiments").length).toBeGreaterThan(0);
  });

  it("adds a project, shows the server's refusal beside the path and stores nothing on a refusal", async () => {
    const { user, server } = openLibrary();
    await user.click(await screen.findByRole("button", { name: "Add project" }));
    const form = screen.getByRole("form", { name: "Add a project" });
    await user.type(within(form).getByLabelText("Folder path"), "/work/none");
    await user.type(within(form).getByLabelText("Name"), "None");
    await user.click(within(form).getByRole("button", { name: "Add project" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("/work/none has no experiments directory.");
    expect(within(form).getByLabelText("Folder path")).toHaveAttribute("aria-invalid", "true");
    expect(server.state.library.projects).toHaveLength(3);

    await user.clear(within(form).getByLabelText("Folder path"));
    await user.type(within(form).getByLabelText("Folder path"), "/work/new");
    await user.click(within(form).getByRole("button", { name: "Add project" }));
    await waitFor(() => expect(screen.queryByRole("form", { name: "Add a project" })).toBeNull());
    expect(server.find("POST", "/v1/experiment-projects").at(-1)!.body).toEqual({ path: "/work/new", name: "None" });
    expect(await screen.findByText("No experiment folder exists in this project yet.")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Project" })).toHaveTextContent("None");
  });

  it("asks for both fields before it sends anything", async () => {
    const { user, server } = openLibrary();
    await user.click(await screen.findByRole("button", { name: "Add project" }));
    const form = screen.getByRole("form", { name: "Add a project" });
    await user.click(within(form).getByRole("button", { name: "Add project" }));
    expect(within(form).getAllByRole("alert").map((line) => line.textContent)).toEqual(["Enter the folder path.", "Enter a name."]);
    expect(server.find("POST", "/v1/experiment-projects")).toHaveLength(0);
  });

  it("shows an empty state with one action when no project exists", async () => {
    const { user } = openLibrary({ ...defaultLibrary(), projects: [] });
    expect(await screen.findByText(/No experiment project yet/)).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Project" })).toBeNull();
    await user.click(within(screen.getByTestId("empty-state")).getByRole("button", { name: "Add project" }));
    expect(screen.getByRole("form", { name: "Add a project" })).toBeInTheDocument();
  });

  it("removes a project only after confirmation", async () => {
    const { user, server } = openLibrary();
    await screen.findByRole("list", { name: "Experiments" });
    await choose(user, "Project", "Paper");
    await user.click(await screen.findByRole("button", { name: "Remove project Paper" }));
    expect(server.find("DELETE", "/v1/experiment-projects")).toHaveLength(0);
    expect(screen.getByText(/files on disk are not touched/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm remove" }));
    await waitFor(() => expect(server.find("DELETE", "/v1/experiment-projects/p2")).toHaveLength(1));
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Project" })).toHaveTextContent("All projects"));
    expect(cards()).toHaveLength(3);
  });

  it("shows one friendly line when a listing fails, never the server text", async () => {
    openLibrary(defaultLibrary(), { "GET /v1/experiment-projects/p1/experiments": () => json({ status: "error", message: "RAW boom <html>" }, 500) });
    expect(await screen.findByRole("alert")).toHaveTextContent("The local server could not complete that request.");
    expect(document.body.textContent).not.toContain("RAW boom");
    expect(await screen.findByRole("group", { name: `Experiment ${OCR}` })).toBeInTheDocument();
  });

  it("keeps the chosen project and filters after a visit to an experiment page", async () => {
    const { user } = openLibrary();
    await screen.findByRole("list", { name: "Experiments" });
    await choose(user, "Status", "FAIL");
    await user.click(within(card(OVERLAP)).getByRole("link", { name: "Open Title of chunk overlap" }));
    expect(await screen.findByRole("heading", { level: 1, name: "2. Title of chunk overlap" })).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Back to Experiments" }));
    await screen.findByRole("list", { name: "Experiments" });
    expect(screen.getByRole("combobox", { name: "Status" })).toHaveTextContent("FAIL");
    expect(cards()).toHaveLength(1);
  });
});
