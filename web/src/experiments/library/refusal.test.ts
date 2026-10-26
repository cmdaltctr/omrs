import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
import { EDITOR_REFUSALS, editorRefusalLine, refusalLaunchId } from "./refusal";

function refused(reason: string | undefined, message = "RAW server text", extra: Record<string, unknown> = {}, status = 409): ApiError {
  const body = { status: "error", message, ...(reason === undefined ? {} : { reason }), ...extra };
  return new ApiError("http", message, "/v1/experiment-projects/p1/experiments/x/editor", status, body);
}

const FIXED = [
  "editor_unavailable",
  "editor_unsupported",
  "no_project_environment",
  "project_config_runs_on_open",
  "notebook_not_regular",
  "editor_running",
  "conversion_failed",
  "no_free_port",
  "launch_failed",
] as const;

afterEach(() => vi.restoreAllMocks());

describe("editor refusal lines", () => {
  it.each(FIXED)("maps %s to its own plain line and logs the server text", (reason) => {
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const line = editorRefusalLine(refused(reason));
    expect(line).toBe(EDITOR_REFUSALS[reason]);
    expect(line).not.toContain("RAW");
    expect(line).not.toContain("—");
    expect(log).toHaveBeenCalled();
  });

  it("gives every fixed reason a different line", () => {
    const lines = FIXED.map((reason) => EDITOR_REFUSALS[reason]);
    expect(new Set(lines).size).toBe(FIXED.length);
  });

  it("names uv sync for a project without a virtual environment", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(editorRefusalLine(refused("no_project_environment"))).toContain("uv sync");
  });

  it.each(["python_mismatch", "converter_missing"])("shows the server line for %s, because it names versions or a command", (reason) => {
    const message = reason === "python_mismatch" ? "The project .venv uses Python 3.12 and marimo runs on Python 3.14." : 'Run `uv tool install "marimo>=0.25.1,<0.26" --with jupytext` outside OMRS.';
    expect(editorRefusalLine(refused(reason, message))).toBe(message);
  });

  it("keeps the generic friendly line for a server failure", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(editorRefusalLine(refused(undefined, "RAW trace", {}, 500))).toBe("The local server could not complete that request.");
  });

  it("reads the launch id of a running editor only from an editor_running refusal", () => {
    expect(refusalLaunchId(refused("editor_running", "m", { launch_id: "launch_9" }))).toBe("launch_9");
    expect(refusalLaunchId(refused("no_free_port", "m", { launch_id: "launch_9" }))).toBeNull();
    expect(refusalLaunchId(new Error("x"))).toBeNull();
  });
});
