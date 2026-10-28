import { describe, expect, it } from "vitest";
import { waitForRestart } from "./restartWait";

/** A fake clock: `sleep` moves time on at once, so the loop runs without real waiting. */
function clock() {
  let time = 0;
  return { now: () => time, sleep: async (ms: number) => void (time += ms) };
}

function answers(...results: boolean[]) {
  let call = 0;
  return async () => results[Math.min(call++, results.length - 1)] ?? false;
}

describe("waitForRestart", () => {
  it("is back once the server stopped answering and then answers again", async () => {
    const check = answers(true, true, false, false, true);
    expect(await waitForRestart(check, clock())).toBe(true);
  });

  it("keeps waiting while the old server still answers", async () => {
    const results: boolean[] = [];
    const check = async () => {
      const answer = results.length !== 2;
      results.push(answer);
      return answer;
    };
    expect(await waitForRestart(check, clock())).toBe(true);
    expect(results).toEqual([true, true, false, true]);
  });

  it("accepts an answering server when the restart was too quick to see it stop", async () => {
    const time = clock();
    expect(await waitForRestart(answers(true), time)).toBe(true);
    expect(time.now()).toBeGreaterThanOrEqual(15_000);
  });

  it("gives up when no server answers in time", async () => {
    const time = clock();
    expect(await waitForRestart(answers(false), time)).toBe(false);
    expect(time.now()).toBeGreaterThanOrEqual(90_000);
  });
});
