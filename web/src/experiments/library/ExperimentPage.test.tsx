import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { json } from "../../test/fakeDocumentsServer";
import { defaultLibrary, OLD_GRAPH, OVERLAP, RERANKER } from "../test/libraryServer";
import { openExperiments } from "../test/openExperiments";

function openPage(folder = RERANKER, extra = {}) {
  return openExperiments({ library: defaultLibrary() }, extra, `#/experiments/library/p1/${encodeURIComponent(folder)}`);
}

const tab = (name: string) => within(screen.getByRole("group", { name: "Experiment tabs" })).getByRole("button", { name: new RegExp(`^${name}`) });

describe("experiment page", () => {
  it("opens from its address with the record header and the Protocol tab", async () => {
    openPage();
    expect(await screen.findByRole("heading", { level: 1, name: "1. Title of reranker threshold" })).toBeInTheDocument();
    expect(screen.getByText("Experiment in OMRS")).toBeInTheDocument();
    expect(screen.getByText("PASS")).toBeInTheDocument();
    expect(screen.getByText("Standard")).toBeInTheDocument();
    expect(screen.getByText("Optimisation")).toBeInTheDocument();
    expect(screen.getByText("ADR-018")).toBeInTheDocument();
    expect(tab("Protocol")).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByRole("heading", { name: "Hypothesis" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "0.2, 0.3" })).toBeInTheDocument();
  });

  it("shows HTML in Markdown as text and runs none of it", async () => {
    openPage();
    expect(await screen.findByText(/<script>alert\(1\)<\/script>/)).toBeInTheDocument();
    expect(screen.getByText(/<b>not bold<\/b>/)).toBeInTheDocument();
    expect(document.querySelector("main script")).toBeNull();
    expect(document.querySelector("main b")).toBeNull();
  });

  it("opens a relative link to another file in the page and a web link in a new tab", async () => {
    const { user } = openPage();
    await screen.findByRole("heading", { name: "Hypothesis" });
    const web = screen.getByRole("link", { name: "the paper" });
    expect(web).toHaveAttribute("href", "https://example.org/paper");
    expect(web).toHaveAttribute("target", "_blank");
    expect(web).toHaveAttribute("rel", "noopener noreferrer");
    // A path into another folder would change the app address, so it stays text.
    expect(screen.getByText("a sibling").closest("a")).toBeNull();
    expect(screen.queryByRole("button", { name: "a sibling" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "the report" }));
    expect(tab("Report")).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText("0.91")).toBeInTheDocument();
    await user.click(tab("Protocol"));
    await user.click(await screen.findByRole("button", { name: "the plan" }));
    expect(tab("Plan")).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText(/"seeds": 3/)).toBeInTheDocument();
  });

  it("shows results.md in the Report tab of an older folder and says what is missing", async () => {
    const { user } = openPage(OVERLAP);
    expect(await screen.findByRole("heading", { level: 1, name: "2. Title of chunk overlap" })).toBeInTheDocument();
    // No protocol.md, so the page opens on the report.
    expect(tab("Report")).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByRole("heading", { name: "Report (results.md)" })).toBeInTheDocument();
    expect(await screen.findByText("Overlap 100 lost recall.")).toBeInTheDocument();
    await user.click(tab("Protocol"));
    expect(screen.getByText("This experiment has no protocol file.")).toBeInTheDocument();
    await user.click(tab("Files"));
    expect(screen.getByText("This experiment has no output folder.")).toBeInTheDocument();
  });

  it("lists every file with its size, does not open an HTML page and lists the output names", async () => {
    const { user, server } = openPage();
    await user.click(await screen.findByRole("button", { name: /^Files/ }));
    const files = screen.getByRole("list", { name: "Files" });
    const review = within(files).getByText("review.html").closest("li")!;
    expect(review).toHaveTextContent("5.0 KiB. Not opened in the app");
    expect(within(review).queryByRole("button")).toBeNull();
    expect(within(screen.getByRole("list", { name: "Output" })).getByText("eval_results.json")).toBeInTheDocument();

    await user.click(within(files).getByRole("button", { name: "experiment.json" }));
    const view = await screen.findByRole("region", { name: "File experiment.json" });
    expect(await within(view).findByText(/"format": "omrs-experiment\/1"/)).toBeInTheDocument();
    expect(server.calls.some((call) => call.path.includes("review.html"))).toBe(false);
  });

  it("lists the checker findings with their severity", async () => {
    const { user } = openPage();
    await user.click(await screen.findByRole("button", { name: "Checks (2)" }));
    const checks = screen.getByRole("list", { name: "Checks" });
    expect(within(checks).getByText("report.md has no status line.")).toBeInTheDocument();
    expect(within(checks).getByText("error")).toBeInTheDocument();
    expect(within(checks).getByText("record-invalid")).toBeInTheDocument();
  });

  it("links a superseded experiment to the one that replaces it", async () => {
    openPage(OLD_GRAPH);
    expect(await screen.findByText("SUPERSEDED")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: RERANKER })).toHaveAttribute("href", `#/experiments/library/p1/${RERANKER}`);
  });

  it("adds the experiment to a notebook from the menu", async () => {
    const { user, server } = openPage();
    await user.click(await screen.findByRole("button", { name: "Add to notebook" }));
    await user.click(await screen.findByRole("button", { name: "Paper 1" }));
    await waitFor(() => expect(server.find("PUT", "/v1/notebooks/n1/entries")).toHaveLength(1));
    expect(server.find("PUT", "/v1/notebooks/n1/entries")[0]!.body).toEqual({ project_id: "p1", folder: RERANKER });
    expect(await screen.findByRole("status")).toHaveTextContent("Added to Paper 1.");
  });

  it("shows a way back for a folder the server does not find", async () => {
    openPage("99-gone-2026-01-01");
    expect(await screen.findByText('The experiment "99-gone-2026-01-01" could not be found.')).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Back to Experiments" })[0]).toHaveAttribute("href", "#/experiments");
  });

  it("offers Edit on the Protocol and Report tabs, never on the Plan tab", async () => {
    const { user } = openPage();
    expect(await screen.findByRole("button", { name: "Edit protocol.md" })).toBeInTheDocument();
    await user.click(tab("Plan"));
    expect(await screen.findByText(/"seeds": 3/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Edit/ })).toBeNull();
    await user.click(tab("Report"));
    expect(await screen.findByRole("button", { name: "Edit report.md" })).toBeInTheDocument();
  });

  it("shows no Edit button for a file the server marks not editable", async () => {
    const library = defaultLibrary();
    library.uneditable = [`p1/${RERANKER}/protocol.md`];
    openExperiments({ library }, {}, `#/experiments/library/p1/${RERANKER}`);
    expect(await screen.findByRole("heading", { name: "Hypothesis" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Edit/ })).toBeNull();
  });

  it("shows one friendly line when a file cannot be read", async () => {
    openPage(RERANKER, {
      [`GET /v1/experiment-projects/p1/experiments/${RERANKER}/files/protocol.md`]: () => json({ status: "error", message: "RAW read error" }, 500),
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("The local server could not complete that request.");
    expect(document.body.textContent).not.toContain("RAW read error");
  });
});
