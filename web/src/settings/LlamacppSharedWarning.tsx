import { useLlamacppServer } from "../api/llamacppServerHooks";
import { SHARED_ADDRESS_WARNING } from "./llamacppServerWords";
import { ServerCallout } from "./ServerCallout";

/**
 * The warning in the Classification block while classification goes to
 * OMRS's own Chat server, which loads only the Chat model (design D6).
 */
export function LlamacppSharedWarning() {
  const status = useLlamacppServer().data;
  return status?.shared_with_classification ? <ServerCallout tone="warning" text={SHARED_ADDRESS_WARNING} /> : null;
}
