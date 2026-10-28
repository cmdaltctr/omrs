import { useEffect, useRef } from "react";
import { getHealth } from "../api/settings";
import type { ApiClient } from "../api/client";

const POLL_MS = 500;
/** A restart this quick can pass between two polls; after this long an answering server counts as the new one. */
const ASSUME_BACK_MS = 15_000;
const GIVE_UP_MS = 90_000;

export interface RestartClock {
  now: () => number;
  sleep: (ms: number) => Promise<void>;
}

const realClock: RestartClock = {
  now: () => Date.now(),
  sleep: (ms) => new Promise((resolve) => window.setTimeout(resolve, ms)),
};

/**
 * Waits for the server to come back after a restart was accepted. The old
 * server can still answer for a moment, so a server counts as back only after
 * a poll has failed, or after `ASSUME_BACK_MS`. Returns false after
 * `GIVE_UP_MS` without an answer.
 */
export async function waitForRestart(answers: () => Promise<boolean>, clock: RestartClock = realClock): Promise<boolean> {
  const start = clock.now();
  let stopped = false;
  while (clock.now() - start < GIVE_UP_MS) {
    const up = await answers();
    if (up && (stopped || clock.now() - start >= ASSUME_BACK_MS)) return true;
    if (!up) stopped = true;
    await clock.sleep(POLL_MS);
  }
  return false;
}

/** Reloads the page. A separate object so tests can watch it; jsdom cannot reload. */
export const page = { reload: () => window.location.reload() };

/**
 * Reloads the page once the server is back after an accepted restart, so the
 * page shows what the new launch reads instead of the old answers.
 */
export function useReloadAfterRestart(api: ApiClient, accepted: boolean): void {
  const started = useRef(false);
  useEffect(() => {
    if (!accepted || started.current) return;
    started.current = true;
    const answers = () => getHealth(api).then(() => true, () => false);
    void waitForRestart(answers).then((back) => {
      if (back) page.reload();
    });
  }, [api, accepted]);
}
