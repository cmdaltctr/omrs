import { useEffect } from "react";
import { getHealth } from "../api/settings";
import type { ApiClient } from "../api/client";

const POLL_MS = 500;
/** One health poll waits at most this long, so a hung request cannot hold the wait open. */
export const POLL_TIMEOUT_MS = 2_000;
export const GIVE_UP_MS = 90_000;

export interface RestartClock {
  now: () => number;
  sleep: (ms: number) => Promise<void>;
}

const realClock: RestartClock = {
  now: () => Date.now(),
  sleep: (ms) => new Promise((resolve) => window.setTimeout(resolve, ms)),
};

/**
 * Waits for the server to come back after a restart was accepted. The server
 * answers 202 before it restarts, and the old process can answer for a few
 * seconds, so a server counts as back only after a poll has failed and a later
 * poll succeeds. Returns false at `GIVE_UP_MS`, also when no poll ever failed:
 * then nothing shows that a new launch answers.
 */
export async function waitForRestart(
  answers: (signal: AbortSignal) => Promise<boolean>,
  clock: RestartClock = realClock,
): Promise<boolean> {
  const start = clock.now();
  let stopped = false;
  while (clock.now() - start < GIVE_UP_MS) {
    const up = await answers(AbortSignal.timeout(POLL_TIMEOUT_MS));
    // A late answer after the window does not count.
    if (clock.now() - start >= GIVE_UP_MS) return false;
    if (up && stopped) return true;
    if (!up) stopped = true;
    await clock.sleep(POLL_MS);
  }
  return false;
}

/** Reloads the page. A separate object so tests can watch it; jsdom cannot reload. */
export const page = { reload: () => window.location.reload() };

/** Only the wait for the latest accepted restart may reload the page. */
let latest = 0;

/**
 * Reloads the page once the server is back after an accepted restart, so the
 * page shows what the new launch reads instead of the old answers. `accepted`
 * identifies one accepted restart (for example the mutation's `submittedAt`):
 * each new value starts its own wait and replaces the one before. The wait
 * keeps running when the dialog closes or the view changes.
 */
export function useReloadAfterRestart(api: ApiClient, accepted: number | null): void {
  useEffect(() => {
    if (accepted === null) return;
    const id = ++latest;
    const answers = (signal: AbortSignal) =>
      getHealth(api, { signal }).then(
        () => true,
        () => false,
      );
    void waitForRestart(answers).then((back) => {
      if (back && id === latest) page.reload();
    });
  }, [api, accepted]);
}
