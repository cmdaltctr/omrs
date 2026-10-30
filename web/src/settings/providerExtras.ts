import type { ComponentType } from "react";
import type { ProviderGroup } from "../api/settings";
import { LlamacppChatBlock } from "./LlamacppChatBlock";
import { LlamacppSharedWarning } from "./LlamacppSharedWarning";

/** A panel a provider card shows at the end of one block. */
export interface ProviderExtra {
  group: ProviderGroup;
  Component: ComponentType;
}

/**
 * Extra panels of a provider card, by provider id, each in the block of its
 * group. The llama.cpp Classification block warns when classification shares
 * OMRS's own Chat server; its Chat block shows the Chat model and the server
 * that `omrs web` can start and own. A card with no entry shows nothing extra.
 */
export const PROVIDER_EXTRAS: Record<string, readonly ProviderExtra[] | undefined> = {
  llamacpp: [
    { group: "metadata", Component: LlamacppSharedWarning },
    { group: "answers", Component: LlamacppChatBlock },
  ],
};
