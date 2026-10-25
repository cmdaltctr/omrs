import { screen, waitFor, within } from "@testing-library/react";
import type userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { defaultLibrary } from "../test/libraryServer";
import { openExperiments } from "../test/openExperiments";

type User = ReturnType<typeof userEvent.setup>;

async function choose(user: User, field: string, option: string, scope: HTMLElement = document.body) {
  await user.click(within(scope).getByRole("combobox", { name: field }));
  await user.click(await screen.findByRole("option", { name: option }));
}

async function openForm(project = "OMRS") {
  const opened = openExperiments({ library: defaultLibrary() });
  await screen.findByRole("list", { name: "Experiments" });
  await opened.user.click(screen.getByRole("button", { name: "New experiment" }));
  const form = screen.getByRole("form", { name: "New experiment" });
  await choose(opened.user, "Project", project, form);
  return { ...opened, form };
}

describe("new experiment", () => {
  it("creates a Standard experiment, links its folder and lists it as PLANNED", async () => {
    const { user, server, form } = await openForm();
    await user.type(within(form).getByLabelText("Slug"), "ocr-text-quality");
    await user.type(within(form).getByLabelText("Title"), "OCR text quality");
    await choose(user, "Category", "ingestion", form);
    await user.click(within(form).getByRole("button", { name: "Create experiment" }));

    await waitFor(() => expect(server.find("POST", "/v1/experiment-projects/p1/experiments")).toHaveLength(1));
    expect(server.find("POST", "/v1/experiment-projects/p1/experiments")[0]!.body).toEqual({
      slug: "ocr-text-quality",
      title: "OCR text quality",
      category: "ingestion",
      size: "Standard",
    });
    const status = await within(form).findByRole("status");
    expect(status).toHaveTextContent("Created 4-ocr-text-quality-2026-10-25. The index in EXP_README.md is updated.");
    expect(within(status).getByRole("link", { name: "4-ocr-text-quality-2026-10-25" })).toHaveAttribute("href", "#/experiments/library/p1/4-ocr-text-quality-2026-10-25");
    const created = await screen.findByRole("group", { name: "Experiment 4-ocr-text-quality-2026-10-25" });
    expect(within(created).getByText("PLANNED")).toBeInTheDocument();
    expect(within(form).getByLabelText("Slug")).toHaveValue("");
  });

  it("sends the size and follow-up number, and says when the project has no EXP_README.md", async () => {
    const { user, server, form } = await openForm("Paper");
    await user.type(within(form).getByLabelText("Slug"), "ocr-retry");
    await user.type(within(form).getByLabelText("Title"), "OCR retry");
    await choose(user, "Size", "Quick", form);
    await user.type(within(form).getByLabelText("Follow-up of (optional)"), "1");
    await user.click(within(form).getByRole("button", { name: "Create experiment" }));
    await waitFor(() => expect(server.find("POST", "/v1/experiment-projects/p2/experiments")).toHaveLength(1));
    expect(server.find("POST", "/v1/experiment-projects/p2/experiments")[0]!.body).toMatchObject({ size: "Quick", follow_up: "1" });
    expect(await within(form).findByRole("status")).toHaveTextContent("The project has no EXP_README.md, so no index is written.");
  });

  it("says when the folder is created but the index is not updated", async () => {
    const { user, form } = await openForm();
    await user.type(within(form).getByLabelText("Slug"), "bad-readme");
    await user.type(within(form).getByLabelText("Title"), "Bad readme");
    await user.click(within(form).getByRole("button", { name: "Create experiment" }));
    const status = await within(form).findByRole("status");
    expect(status).toHaveTextContent("Created 4-bad-readme-2026-10-25. The experiment folder was created, but the index in EXP_README.md was not updated.");
    expect(status).toHaveTextContent("omrs experiments index --write");
    expect(within(form).queryByRole("alert")).toBeNull();
  });

  it("checks the slug, title and follow-up number before it sends anything", async () => {
    const { user, server, form } = await openForm();
    await user.type(within(form).getByLabelText("Slug"), "Bad Slug");
    await user.type(within(form).getByLabelText("Follow-up of (optional)"), "twelve");
    await user.click(within(form).getByRole("button", { name: "Create experiment" }));
    const alerts = within(form).getAllByRole("alert").map((line) => line.textContent);
    expect(alerts).toEqual([expect.stringMatching(/lower-case letters and digits/), "Enter a title.", expect.stringMatching(/experiment number/)]);
    expect(within(form).getByLabelText("Slug")).toHaveAttribute("aria-invalid", "true");
    expect(server.find("POST", "/v1/experiment-projects/p1/experiments")).toHaveLength(0);
  });

  it("shows the server's refusal in plain words and creates nothing", async () => {
    const { user, server, form } = await openForm();
    await user.type(within(form).getByLabelText("Slug"), "taken");
    await user.type(within(form).getByLabelText("Title"), "Taken");
    await user.click(within(form).getByRole("button", { name: "Create experiment" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("The folder 4-taken-2026-10-25 already exists.");
    expect(server.state.library.experiments.p1).toHaveLength(3);
    expect(within(form).queryByRole("status")).toBeNull();
  });
});
