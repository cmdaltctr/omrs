import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AnswerResult } from "../api/documents";
import { failureLine } from "./answerStatus";

function failed(extra: Partial<AnswerResult> = {}): AnswerResult {
  return {
    status: "error", query: "q", answer: null, citations: [], evidence: [],
    failure_stage: "generation", error: "Generation failed: something", completion_source: "server", ...extra,
  };
}

describe("failureLine", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  it("tells the user to wait, then retry, when the provider is limiting requests", () => {
    const line = failureLine(failed({ rate_limited: { kind: "rate_limit", http_status: 429, retry_after_seconds: 7 } }));
    expect(line).toMatch(/limiting requests/);
    expect(line).toMatch(/[Ww]ait/);
    expect(line).toMatch(/Retry/);
  });

  it("tells the user to top up when the provider account is out of credit", () => {
    const line = failureLine(failed({ rate_limited: { kind: "out_of_credit", http_status: 402, retry_after_seconds: null } }));
    expect(line).toMatch(/[Tt]op up the provider account/);
    expect(line).not.toMatch(/[Ww]ait/);
  });

  it("keeps today's lines when the result has no record", () => {
    expect(failureLine(failed())).toBe("The model could not write an answer from the evidence.");
    expect(failureLine(failed({ failure_stage: "retrieval" }))).toBe("The knowledge base could not search for evidence.");
    expect(failureLine(failed({ failure_stage: null }))).toBe("The answer could not be completed.");
  });
});
