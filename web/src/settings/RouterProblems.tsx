import type { RouterProblem } from "../api/llamacppRouter";
import { PROBLEM_ACTION } from "./llamacppRouterWords";
import { ServerCallout } from "./ServerCallout";

/**
 * One plain line for each role that no list entry can serve. The text is the
 * server's own line, so the page keeps no list of reasons. Nothing shows for an
 * empty array.
 */
export function RouterProblems({ problems }: { problems: RouterProblem[] }) {
  return (
    <>
      {problems.map((problem) => (
        <div key={`${problem.role}-${problem.reason}`} data-testid="router-problem">
          <ServerCallout tone="warning" text={`${problem.text} ${PROBLEM_ACTION}`} />
        </div>
      ))}
    </>
  );
}
