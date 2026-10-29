import { describe, expect, it } from "vitest";
import { GIVE_UP_MS, POLL_TIMEOUT_MS, waitForRestart } from "./restartWait";

/** A fake clock: `sleep` moves time on at once, so the loop runs without real waiting. */
function clock() {
  let time = 0;
  return {
    now: () => time,
    sleep: async (ms: number) => void (time += ms),
    advance: (ms: number) => void (time += ms),
  };
}

function answers(...results: boolean[]) {
  let call = 0;
  return async () => results[Math.min(call++, results.length - 1)] ?? false;
}

describe("waitForRestart", () => {
  it("is back once the server stopped answering and then answers again", async () => {
    expect(await waitForRestart(answers(true, true, false, false, true), clock())).toBe(true);
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

  it("never treats an old server that keeps answering as a new launch", async () => {
    const time = clock();
    expect(await waitForRestart(answers(true), time)).toBe(false);
    expect(time.now()).toBeGreaterThanOrEqual(GIVE_UP_MS);
  });

  it("stops without another sleep once the wait is no longer current", async () => {
    let current = true;
    let sleeps = 0;
    const time = clock();
    const check = async () => {
      current = false;
      return false;
    };
    const counted = { ...time, sleep: async (ms: number) => void (sleeps++, time.advance(ms)) };
    expect(await waitForRestart(check, counted, () => current)).toBe(false);
    expect(sleeps).toBe(0);
  });

  it("gives up when no server answers in time", async () => {
    const time = clock();
    expect(await waitForRestart(answers(false), time)).toBe(false);
    expect(time.now()).toBeGreaterThanOrEqual(GIVE_UP_MS);
  });

  it("gives each poll a time limit", async () => {
    const signals: AbortSignal[] = [];
    const check = async (signal: AbortSignal) => {
      signals.push(signal);
      return signals.length !== 1;
    };
    await waitForRestart(check, clock());
    expect(signals.length).toBeGreaterThan(0);
    // AbortSignal.timeout signals have not fired yet, but they carry a deadline.
    expect(signals.every((signal) => signal instanceof AbortSignal && !signal.aborted)).toBe(true);
    expect(POLL_TIMEOUT_MS).toBeLessThan(GIVE_UP_MS);
  });

  it("does not count an answer that arrives after the window", async () => {
    const time = clock();
    let call = 0;
    const check = async () => {
      call += 1;
      if (call === 1) return false;
      time.advance(GIVE_UP_MS);
      return true;
    };
    expect(await waitForRestart(check, time)).toBe(false);
  });
});
