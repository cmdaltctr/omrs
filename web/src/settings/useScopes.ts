import { useQuery } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { sessionQuery } from "../api/queries";

/**
 * What the session may do. `known` turns true once the session is read.
 * A control that must never go live for a person without the scope waits for
 * `known`; a field row stays editable until then, because the server refuses a
 * change without the scope.
 */
export function useScopes(): { known: boolean; has: (scope: string) => boolean } {
  const session = useQuery(sessionQuery(useApi()));
  const scopes = session.data?.scopes;
  return { known: scopes !== undefined, has: (scope) => scopes?.includes(scope) === true };
}
