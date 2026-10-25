import { describeSaveError } from "../../lib/errors";

/**
 * One line for a refused library request. A 400 or 409 shows the server's
 * reason, which names the rule (for example a missing `experiments`
 * directory or a folder that exists). Every other failure keeps the generic
 * friendly line, and the raw text goes to the console.
 */
export function refusalLine(error: unknown): string {
  return describeSaveError(error).message;
}
