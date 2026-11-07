import type { LlamacppRouterStatus } from "../api/llamacppRouter";
import { statusLine } from "./llamacppRouterWords";

/** Said while a Start waits for the automatic downloads: the router is `starting` with the reason `not-downloaded`. */
export const DOWNLOADING_LINE = "Downloading models. The router starts when they are ready.";

/**
 * The state line of the Router panel. A Start that waits only for the downloads of listed models is
 * not a failure, so it says "Downloading"; every other state keeps the words of `statusLine`.
 */
export function routerStateLine(status: LlamacppRouterStatus): string {
  return status.state === "starting" && status.reason === "not-downloaded" ? DOWNLOADING_LINE : statusLine(status);
}
